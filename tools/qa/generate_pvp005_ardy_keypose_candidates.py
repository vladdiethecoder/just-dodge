#!/usr/bin/env python3
"""Generate fixed-seed PVP-005 proposals from pinned ARDY keypose constraints."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPEC = ROOT / "assets/qa/pvp005_ardy_keyposes_v1.json"
DEFAULT_ARDY = Path(os.environ.get("JUST_DODGE_ARDY_ROOT", "/run/media/vdubrov/NVMe-Storage1/ardy"))
PVP005_GENERATION_ENABLED = False
GENERATION_DISABLED_MESSAGE = "PVP-005 ARDY generation is disabled pending a content-addressed authorization certificate"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def build_constraints(model, keyframes: list[dict[str, object]], device: str):
    import torch
    from ardy.constraints import Root2DConstraintSet, create_pairs

    class PositionOnlyConstraintSet:
        def __init__(self, frame_indices, positions, joint_indices, root_y=None):
            self.frame_indices = frame_indices
            self.positions = positions
            self.joint_indices = torch.tensor(joint_indices)
            self.root_y = root_y

        def update_constraints(self, data_dict, index_dict):
            indices = create_pairs(self.frame_indices, self.joint_indices)
            data_dict["global_joints_positions"].append(
                self.positions[:, self.joint_indices].reshape(-1, 3)
            )
            index_dict["global_joints_positions"].append(indices)
            if self.root_y is not None:
                data_dict["root_y_pos"].append(self.root_y)
                index_dict["root_y_pos"].append(self.frame_indices)

    skeleton = model.skeleton
    frame_indices = torch.tensor([item["frame"] for item in keyframes])
    sparse_root_xz = torch.tensor(
        [item["root_xz_m"] for item in keyframes], dtype=torch.float32, device=device
    )
    frames = int(model.gen_horizon_len)
    dense_frames = torch.arange(frames)
    root_xz = torch.empty((frames, 2), dtype=torch.float32, device=device)
    for left, right in zip(range(len(keyframes) - 1), range(1, len(keyframes))):
        start = int(keyframes[left]["frame"])
        end = int(keyframes[right]["frame"])
        alpha = torch.linspace(0.0, 1.0, end - start + 1, device=device)[:, None]
        root_xz[start : end + 1] = sparse_root_xz[left].lerp(sparse_root_xz[right], alpha)
    roots = torch.cat(
        [
            sparse_root_xz[:, :1],
            torch.full((len(keyframes), 1), 0.78, device=device),
            sparse_root_xz[:, 1:],
        ],
        dim=1,
    )
    neutral = skeleton.neutral_joints.to(device=device, dtype=torch.float32)
    positions = neutral[None].repeat(len(keyframes), 1, 1)
    positions = positions + roots[:, None]

    names = skeleton.bone_index
    for index, item in enumerate(keyframes):
        for side in ("left", "right"):
            endpoint = torch.tensor(item[f"{side}_hand_m"], dtype=torch.float32, device=device)
            wrist = endpoint - torch.tensor([0.0, 0.0, 0.10], device=device)
            positions[index, names[f"{side}_wrist_yaw_skel"]] = wrist
            positions[index, names[f"{side}_hand_roll_skel"]] = endpoint

    heading = torch.zeros(frames, device=device)
    root_constraint = Root2DConstraintSet(
        skeleton,
        dense_frames,
        root_xz,
        global_root_heading=heading,
    )
    hand_indices = [
        names["pelvis_skel"],
        names["left_wrist_yaw_skel"],
        names["left_hand_roll_skel"],
        names["right_wrist_yaw_skel"],
        names["right_hand_roll_skel"],
    ]
    hands = PositionOnlyConstraintSet(frame_indices, positions, hand_indices)
    foot_indices = [
        names["pelvis_skel"],
        names["left_ankle_roll_skel"],
        names["left_toe_base"],
        names["right_ankle_roll_skel"],
        names["right_toe_base"],
    ]
    initial_root = torch.tensor([0.0, 0.78, 0.0], device=device)
    dense_positions = neutral[None].repeat(frames, 1, 1) + initial_root
    dense_positions[:, names["pelvis_skel"], 0] = root_xz[:, 0]
    dense_positions[:, names["pelvis_skel"], 1] = 0.78
    dense_positions[:, names["pelvis_skel"], 2] = root_xz[:, 1]
    feet = PositionOnlyConstraintSet(
        dense_frames,
        dense_positions,
        foot_indices,
        root_y=torch.full((frames,), 0.78, device=device),
    )
    return [root_constraint, hands, feet]


def main() -> None:
    if not PVP005_GENERATION_ENABLED:
        raise SystemExit(GENERATION_DISABLED_MESSAGE)

    import numpy as np

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--ardy-root", type=Path, default=DEFAULT_ARDY)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec_path = args.spec.resolve()
    ardy_root = args.ardy_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite ARDY proposal output: {output}")
    spec = json.loads(spec_path.read_text())
    if spec.get("schema") not in {
        "just-dodge-pvp005-ardy-keyposes-v1",
        "just-dodge-pvp005-ardy-keyposes-v2",
    }:
        raise SystemExit("unsupported ARDY keypose schema")
    revision = git_revision(ardy_root)
    if revision != spec["source_commit"]:
        raise SystemExit(f"ARDY revision drift: {revision} != {spec['source_commit']}")
    if spec.get("text_conditioning") is not False:
        raise SystemExit("PVP-005 ARDY proposals must disable text conditioning")

    sys.path.insert(0, str(ardy_root))
    import torch
    from ardy.model import load_model
    from ardy.motion_rep.tools import length_to_mask
    from ardy.tools import seed_everything
    from huggingface_hub import snapshot_download

    if not torch.cuda.is_available():
        raise SystemExit("pinned ARDY proposal generation requires CUDA")
    device = "cuda:0"
    model_snapshot = Path(
        snapshot_download(repo_id=f"nvidia/{spec['model']}", local_files_only=True)
    )
    with contextlib.redirect_stdout(sys.stderr):
        model = load_model(spec["model"], device=device, text_encoder=False)
    if type(model.skeleton).__name__ != "G1Skeleton34":
        raise SystemExit(f"unexpected ARDY skeleton: {type(model.skeleton).__name__}")
    if int(model.gen_horizon_len) != spec["frames"] or int(model.motion_rep.fps) != spec["fps"]:
        raise SystemExit("ARDY horizon/FPS drift from keypose contract")
    if int(model.diffusion.num_base_steps) != spec["diffusion_steps"]:
        raise SystemExit("ARDY diffusion-step contract drift")

    output.mkdir(parents=True)
    receipts = []
    frames = int(spec["frames"])
    lengths = torch.tensor([frames], device=device)
    pad_mask = length_to_mask(lengths)
    llm_dim = int(model.denoiser.llm_shape[-1])
    for action in ("strike", "block", "grab"):
        keyframes = spec["actions"][action]["keyframes"]
        constraints = build_constraints(model, keyframes, device)
        observed, motion_mask = model.motion_rep.create_conditions_from_constraints_batched(
            constraints,
            lengths,
            to_normalize=True,
            device=device,
        )
        action_root = output / action
        action_root.mkdir()
        for candidate_index, seed in enumerate(spec["seeds"]):
            seed_everything(int(seed))
            torch.cuda.synchronize()
            started = time.perf_counter()
            with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
                motion = model(
                    [""],
                    frames,
                    num_denoising_steps=int(spec["diffusion_steps"]),
                    pad_mask=pad_mask,
                    first_heading_angle=torch.zeros(1, device=device),
                    motion_mask=motion_mask,
                    observed_motion=observed,
                    cfg_weight=(0.0, float(spec["constraint_weight"])),
                    text_feat=torch.zeros(1, 1, llm_dim, device=device),
                    text_pad_mask=torch.zeros(1, 1, dtype=torch.bool, device=device),
                )
                decoded = model.motion_rep.inverse(motion, is_normalized=True)
            torch.cuda.synchronize()
            generation_ms = (time.perf_counter() - started) * 1000.0
            required = (
                "posed_joints",
                "global_rot_mats",
                "local_rot_mats",
                "root_positions",
                "foot_contacts",
                "global_root_heading",
            )
            missing = [name for name in required if name not in decoded]
            if missing:
                raise SystemExit(f"ARDY output missing {missing}")
            arrays = {
                name: decoded[name][0].detach().cpu().numpy()
                for name in required
            }
            if not all(np.isfinite(value).all() for value in arrays.values()):
                raise SystemExit(f"non-finite ARDY proposal: {action}/{candidate_index}")
            candidate = f"{action}_ardy_kp_{candidate_index:02d}"
            path = action_root / f"{candidate}.npz"
            np.savez_compressed(path, **arrays)
            receipts.append(
                {
                    "action": action,
                    "candidate": candidate,
                    "seed": seed,
                    "generation_ms": round(generation_ms, 3),
                    "path": str(path.relative_to(ROOT)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )

    manifest = {
        "schema": "just-dodge-pvp005-ardy-keypose-proposals-v1",
        "authority": "offline_motion_proposal_only",
        "admitted": False,
        "runtime_generation": False,
        "source_repository": "https://github.com/nv-tlabs/ardy",
        "source_commit": revision,
        "source_license_sha256": sha256(ardy_root / "LICENSE"),
        "model": spec["model"],
        "model_snapshot": model_snapshot.name,
        "model_license_sha256": sha256(model_snapshot / "LICENSE"),
        "model_config_sha256": sha256(model_snapshot / "config.yaml"),
        "model_denoiser_sha256": sha256(model_snapshot / "denoiser.safetensors"),
        "model_tokenizer_sha256": sha256(model_snapshot / "tokenizer.safetensors"),
        "skeleton": type(model.skeleton).__name__,
        "keypose_spec_path": str(spec_path.relative_to(ROOT)),
        "keypose_spec_sha256": sha256(spec_path),
        "text_conditioning": False,
        "candidates": receipts,
    }
    manifest_path = output / "generation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"PVP005_ARDY_KEYPOSE_MANIFEST_SHA256={sha256(manifest_path)}")
    print(f"PVP005_ARDY_KEYPOSE_PROPOSALS={len(receipts)}")


if __name__ == "__main__":
    main()
