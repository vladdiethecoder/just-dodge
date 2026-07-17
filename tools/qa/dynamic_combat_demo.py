#!/usr/bin/env python3
"""QUARANTINED EXPLORATORY-ONLY 162-example combat demo — NOT production evidence.

This script produces synthetic in-process targets and hard-masked constraint
outputs. Its zero-error measurements are therefore not evidence that the typed
interaction-conditioned MotionBricks forward path works. It must not be used
for runtime admission, model promotion, production claims, or replay/truth
validation. See docs/evidence_quarantine/DYNAMIC_COMBAT_DEMO_162_INVALID.md.

Any generated output is written only to the ignored quarantine evidence path.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import torch
from torch import nn

REPO = Path("/run/media/vdubrov/NVMe-Storage1/Just Dodge")
MB_DIR = Path("/run/media/vdubrov/NVMe-Storage1/gr00t/motionbricks")
BATCH_SPEC = REPO / "assets/data/r6k_move_batch.json"
CORPUS_TOOL = REPO / "tools/qa/build_interaction_corpus.py"
OUT_ROOT = REPO / "validation_evidence/quarantine/dynamic-combat-demo-162-invalid-exploratory-20260717"
SEED = 2026071701
FRAMES = 64
FPS = 30

CORE_JOINTS = [
    "Hips", "Spine", "Spine1", "Spine2", "Spine3", "Neck", "Head",
    "RightShoulder", "RightArm", "RightForeArm", "RightHand", "RightHandEnd", "RightHandThumb1",
    "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand", "LeftHandEnd", "LeftHandThumb1",
    "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase",
    "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
]

G1_DIRECT = {
    "pelvis_skel": "Hips",
    "left_hip_pitch_skel": "LeftUpLeg", "left_knee_skel": "LeftLeg",
    "left_ankle_pitch_skel": "LeftFoot", "left_toe_base": "LeftToeBase",
    "right_hip_pitch_skel": "RightUpLeg", "right_knee_skel": "RightLeg",
    "right_ankle_pitch_skel": "RightFoot", "right_toe_base": "RightToeBase",
    "left_shoulder_pitch_skel": "LeftShoulder", "left_elbow_skel": "LeftForeArm",
    "left_wrist_roll_skel": "LeftHand", "left_hand_roll_skel": "LeftHandEnd",
    "right_shoulder_pitch_skel": "RightShoulder", "right_elbow_skel": "RightForeArm",
    "right_wrist_roll_skel": "RightHand", "right_hand_roll_skel": "RightHandEnd",
}

INTENT_TO_ID = {"Strike": 0, "Block": 1, "Dodge": 2, "Parry": 3, "Grab": 4, "Thrust": 5, "Move": 6}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def deterministic_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(arrays):
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, np.asarray(arrays[name]), allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, buffer.getvalue(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def resample(a: np.ndarray, n: int) -> np.ndarray:
    x = np.linspace(0, len(a) - 1, n)
    lo = np.floor(x).astype(int)
    hi = np.minimum(lo + 1, len(a) - 1)
    t = (x - lo)[:, None]
    return a[lo] * (1 - t) + a[hi] * t


def _pack_413(root_pos: np.ndarray, posed_joints: np.ndarray, rot_mats: np.ndarray) -> np.ndarray:
    N = root_pos.shape[0]
    frames = np.zeros((N, 413), dtype=np.float32)
    frames[:, 0:3] = root_pos
    heading = np.arctan2(rot_mats[:, 0, 0, 2], rot_mats[:, 0, 2, 2])
    frames[:, 3] = np.cos(heading)
    frames[:, 4] = np.sin(heading)
    frames[:, 5:104] = (posed_joints[:, 1:] - root_pos[:, None, :]).reshape(N, -1)
    for j in range(34):
        v0 = rot_mats[:, j, :, 0]
        v1 = rot_mats[:, j, :, 1]
        norm0 = np.linalg.norm(v0, axis=1, keepdims=True) + 1e-8
        v0n = v0 / norm0
        v1p = v1 - v0n * np.sum(v0n * v1, axis=1, keepdims=True)
        norm1 = np.linalg.norm(v1p, axis=1, keepdims=True) + 1e-8
        v1n = v1p / norm1
        frames[:, 104 + j * 6 : 104 + j * 6 + 3] = v0n
        frames[:, 104 + j * 6 + 3 : 104 + j * 6 + 6] = v1n
    return frames


def build_target_from_example(example: dict, sk, q) -> tuple[np.ndarray, np.ndarray]:
    """Build a (T,34,3) target pose from an interaction example."""
    key_frames = example["key_frames"]
    centers = example["grip_centers"]
    axes = example["grip_axes"]
    grip_half = 0.08
    T = FRAMES
    root = np.zeros((T, 3), dtype=np.float32)
    root[:, 1] = 0.82
    pos = np.zeros((T, 34, 3), dtype=np.float32)
    pos[:, 0] = root

    lh, rh = q["left_hand_roll_skel"], q["right_hand_roll_skel"]
    kf = np.asarray(key_frames)
    scale = (T - 1) / max(kf.max(), 1)
    kf_scaled = np.rint(kf * scale).astype(int)
    for i, f in enumerate(kf_scaled):
        center = np.asarray(centers[i], dtype=np.float32)
        axis = np.asarray(axes[i], dtype=np.float32)
        axis = axis / np.linalg.norm(axis)
        pos[f, lh] = center - grip_half * axis
        pos[f, rh] = center + grip_half * axis
    for j in (lh, rh):
        pos[:, j] = resample(pos[kf_scaled, j], T)

    attack_origin = np.asarray(example["attack_origin_mm"], dtype=np.float32) / 1000.0
    attack_target = np.asarray(example["attack_target_mm"], dtype=np.float32) / 1000.0
    attack_dir = attack_target - attack_origin
    attack_dir = attack_dir / max(np.linalg.norm(attack_dir), 1e-8)
    contact_frame = min(int(example["contact_tick_offset"]), T - 1)
    for j in (lh, rh):
        current = pos[contact_frame, j].copy()
        correction = attack_origin + attack_dir * 0.5 - current
        pos[contact_frame, j] = current + correction * 0.3

    for t in range(T):
        mid = (pos[t, lh] + pos[t, rh]) / 2.0
        axis = pos[t, rh] - pos[t, lh]
        axis = axis / max(np.linalg.norm(axis), 1e-8)
        pos[t, lh] = mid - 0.08 * axis
        pos[t, rh] = mid + 0.08 * axis

    for j in range(1, 34):
        if j not in (lh, rh):
            for t in range(T):
                frac = j / 33.0
                pos[t, j] = pos[t, 0] + frac * (pos[t, lh] + pos[t, rh]) * 0.5

    feet = [q[n] for n in ("left_ankle_roll_skel", "left_toe_base", "right_ankle_roll_skel", "right_toe_base")]
    for j in feet:
        pos[:, j] = pos[0, j]
    return root, pos


class InteractionExtension(nn.Module):
    def __init__(self, cond_dim: int = 1241):
        super().__init__()
        self.inp = nn.Conv1d(cond_dim, 256, 5, padding=2)
        self.blocks = nn.ModuleList([nn.Conv1d(256, 256, 5, padding=2 * d, dilation=d) for d in (1, 2, 4, 8)])
        self.out = nn.Conv1d(256, 413, 1)

    def forward(self, base, constraint, mask, phase):
        x = torch.cat([base, constraint, mask, phase], -1).transpose(1, 2)
        x = torch.nn.functional.gelu(self.inp(x))
        for b in self.blocks:
            x = x + torch.nn.functional.gelu(b(x))
        raw = base + self.out(x).transpose(1, 2)
        return raw * (1 - mask) + constraint * mask


def build_conditioning(example: dict, target: np.ndarray, base: np.ndarray, sk, q) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Build (1,T,1241) conditioning tensors for one example."""
    T = FRAMES
    target_t = torch.from_numpy(target).cuda()
    base_t = torch.from_numpy(base).cuda()
    constraint = torch.zeros_like(target_t)
    mask = torch.zeros_like(target_t)
    keys = [0, 16, 32, 48, 63]
    for k in keys:
        constraint[k] = target_t[k]
        mask[k] = 1
    feet = [q[n] for n in ("left_ankle_roll_skel", "left_toe_base", "right_ankle_roll_skel", "right_toe_base")]
    lh, rh = q["left_hand_roll_skel"], q["right_hand_roll_skel"]
    dense = [*range(0, 5), *range(410, 413)]
    for j in [*feet, lh, rh]:
        if j > 0:
            dense += list(range(5 + (j - 1) * 3, 5 + j * 3))
        dense += list(range(104 + j * 6, 104 + (j + 1) * 6))
    constraint[:, dense] = target_t[:, dense]
    mask[:, dense] = 1
    phase = torch.stack(
        [torch.sin(torch.linspace(0, torch.pi * 2, T, device="cuda")),
         torch.cos(torch.linspace(0, torch.pi * 2, T, device="cuda"))], -1)
    return base_t[None], constraint[None], mask[None], phase[None]


def encode_interaction_features(example: dict) -> np.ndarray:
    """Encode one interaction example into a compact feature vector."""
    features = []
    features.append(float(INTENT_TO_ID.get(example["actor_intent"], 0)) / 6.0)
    features.append(float(INTENT_TO_ID.get(example["opponent_intent"], 0)) / 6.0)
    features.extend([v / 2000.0 for v in example["attack_origin_mm"]])
    features.extend([v / 2000.0 for v in example["attack_target_mm"]])
    features.extend([v / 32767.0 for v in example["attack_direction_q15"]])
    features.extend([v / 5000.0 for v in example["attack_velocity_mm_s"]])
    features.append(example["reach_mm"] / 3000.0)
    features.append(example["contact_tick_offset"] / 60.0)
    features.append(example["contact_window_start_tick_offset"] / 60.0)
    features.append(example["contact_window_end_tick_offset"] / 60.0)
    features.append(example["expected_impulse_milli_ns"] / 10000.0)
    features.append(example["expected_energy_millijoules"] / 2000.0)
    return np.asarray(features, dtype=np.float32)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moves", nargs="*", default=["strike_vertical", "block_high", "thrust", "dodge_lateral"])
    parser.add_argument("--variants-per-move", type=int, default=9)
    parser.add_argument("--steps", type=int, default=400)
    args = parser.parse_args()

    batch = json.loads(BATCH_SPEC.read_text())
    moves = [m for m in batch["moves"] if m["id"] in args.moves]
    if not moves:
        raise RuntimeError("no moves selected")

    sys.path.insert(0, str(REPO))
    from tools.qa.build_interaction_corpus import build_variants, build_interaction_tensor

    sys.path.insert(0, str(MB_DIR))
    from motionbricks.motionlib.core.skeletons.g1 import G1Skeleton34
    from motionbricks.motionlib.core.utils.torch_utils import batch_rigid_transform
    sk = G1Skeleton34(device="cuda")
    q = sk.bone_index

    base_seed_path = REPO / "assets/motion/pvp005_r6/hero_strike.motionbricks.413.f32"
    base_seed = np.fromfile(base_seed_path, dtype=np.float32).reshape(-1, 413)
    base = resample(base_seed, FRAMES).astype(np.float32)

    examples = []
    for move in moves:
        for variant in build_variants(move)[: args.variants_per_move]:
            example = build_interaction_tensor(move, variant)
            example["example_sha256"] = sha256_bytes(canonical_json(example))
            root, pos = build_target_from_example(example, sk, q)
            target = _pack_413(root, pos, np.zeros((FRAMES, 34, 3, 3), dtype=np.float32))
            conditioning = build_conditioning(example, target, base, sk, q)
            features = encode_interaction_features(example)
            examples.append({
                "example": example,
                "target": target,
                "conditioning": conditioning,
                "features": features,
            })

    print(f"Built {len(examples)} interaction examples from {len(moves)} moves")

    model = InteractionExtension().cuda()
    opt = torch.optim.AdamW(model.parameters(), lr=2e-4)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    np.random.seed(SEED)
    random.seed(SEED)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.set_default_dtype(torch.float32)

    for step in range(args.steps):
        opt.zero_grad(set_to_none=True)
        total_loss = torch.tensor(0.0, device="cuda")
        for ex in examples:
            base_t, constraint, mask, phase = ex["conditioning"]
            target_t = torch.from_numpy(ex["target"]).cuda()[None]
            pred = model(base_t, constraint, mask, phase)
            loss = torch.mean((pred - target_t).square())
            total_loss = total_loss + loss
        total_loss = total_loss / len(examples)
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 10)
        opt.step()
        if step % 50 == 0 or step + 1 == args.steps:
            print(f"step {step}: loss={float(total_loss.detach()):.6f}")

    model.eval()
    results = []
    rendered = []
    with torch.no_grad():
        for ex in examples:
            base_t, constraint, mask, phase = ex["conditioning"]
            pred = model(base_t, constraint, mask, phase)[0]
            arr = pred.cpu().numpy().astype(np.float32)
            pos = np.empty((FRAMES, 34, 3), np.float32)
            pos[:, 0] = arr[:, :3]
            for j in range(1, 34):
                pos[:, j] = arr[:, :3] + arr[:, 5 + (j - 1) * 3 : 5 + j * 3]
            feet = [q[n] for n in ("left_ankle_roll_skel", "left_toe_base", "right_ankle_roll_skel", "right_toe_base")]
            lh, rh = q["left_hand_roll_skel"], q["right_hand_roll_skel"]
            foot = {sk.bone_order_names[j]: float(np.linalg.norm(pos[:, j] - pos[0, j], axis=-1).max()) for j in feet}
            span = np.linalg.norm(pos[:, rh] - pos[:, lh], axis=-1)
            grip = float(np.abs(span - 0.16).max())
            hand = max(
                float(np.linalg.norm(pos[:, j] - (pos[:, 0] + ex["target"][:, 5 + (j - 1) * 3 : 5 + j * 3].reshape(FRAMES, 3)), axis=-1).max())
                for j in (lh, rh)
            )
            results.append({
                "move_id": ex["example"]["move_id"],
                "variant_id": ex["example"]["variant_id"],
                "foot_drift_m": foot,
                "grip_error_m": grip,
                "hand_error_m": hand,
                "features": ex["features"].tolist(),
            })
            rendered.append({
                "move_id": ex["example"]["move_id"],
                "variant_id": ex["example"]["variant_id"],
                "pos": pos.tolist(),
            })

    distinct = set()
    for r in results:
        key = (r["move_id"], r["variant_id"])
        distinct.add(key)
    print(f"Distinct (move, variant) pairs: {len(distinct)}")

    feature_variance = np.var([r["features"] for r in results], axis=0)
    print(f"Feature variance (first 5): {feature_variance[:5].tolist()}")

    summary = {
        "schema": "just-dodge-dynamic-combat-demo-v1",
        "examples": len(examples),
        "moves": [m["id"] for m in moves],
        "variants_per_move": args.variants_per_move,
        "steps": args.steps,
        "results": results,
        "feature_variance": feature_variance.tolist(),
        "distinct_pairs": len(distinct),
    }
    summary["summary_sha256"] = sha256_bytes(canonical_json(summary))
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    write_json(OUT_ROOT / "demo_summary.json", summary)
    print(f"SUMMARY={OUT_ROOT / 'demo_summary.json'}")

    np.save(OUT_ROOT / "rendered_poses.npy", np.asarray([r["pos"] for r in rendered], dtype=np.float32))
    write_json(OUT_ROOT / "rendered_manifest.json", {"schema": "just-dodge-rendered-manifest-v1", "count": len(rendered), "move_ids": sorted(set(r["move_id"] for r in rendered))})
    print(f"RENDERED_POSES={OUT_ROOT / 'rendered_poses.npy'}")


if __name__ == "__main__":
    main()
