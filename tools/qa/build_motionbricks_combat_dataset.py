#!/usr/bin/env python3
"""Build the strict-canon MotionBricks Strike/Block/Grab training corpus."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from motionbricks_service.generate import init_service


OUTPUT = ROOT / "qa_runs/m3_contact_truth_001/b14t_combat_dataset/corpus"
TARGET_FPS = 30
ENTRIES = (
    ("strike_00", "strike", "train", "ardy", ROOT / "qa_runs/m3_contact_truth_001/b14k_ardy_constraints/generated/strike/strike_00.npz", 25),
    ("strike_01", "strike", "validation", "ardy", ROOT / "qa_runs/m3_contact_truth_001/b14k_ardy_constraints/generated/strike/strike_01.npz", 25),
    ("block_04", "block", "train", "ardy", ROOT / "qa_runs/m3_contact_truth_001/b14t_combat_dataset/block/block/block_04.npz", 25),
    ("B_Fence1", "block", "train", "g1_csv", ROOT / "qa_runs/m3_contact_truth_001/b14t_combat_dataset/external_block/B_Fence1.csv", 60),
    ("B_Fence2", "block", "validation", "g1_csv", ROOT / "qa_runs/m3_contact_truth_001/b14t_combat_dataset/external_block/B_Fence2.csv", 60),
    ("grab_02", "grab", "train", "ardy", ROOT / "qa_runs/m3_contact_truth_001/b14t_combat_dataset/grab/grab/grab_02.npz", 25),
    ("grab_03", "grab", "train", "ardy", ROOT / "qa_runs/m3_contact_truth_001/b14t_combat_dataset/grab/grab/grab_03.npz", 25),
    ("grab_06", "grab", "validation", "ardy", ROOT / "qa_runs/m3_contact_truth_001/b14t_combat_dataset/grab/grab/grab_06.npz", 25),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nearest_indices(frames: int, source_fps: int) -> np.ndarray:
    count = max(2, int(np.floor((frames - 1) * TARGET_FPS / source_fps)) + 1)
    return np.minimum(
        np.rint(np.arange(count) * source_fps / TARGET_FPS).astype(int),
        frames - 1,
    )


def load_ardy(path: Path, source_fps: int, device: str):
    archive = np.load(path)
    indices = nearest_indices(len(archive["posed_joints"]), source_fps)
    positions = torch.from_numpy(
        np.asarray(archive["posed_joints"][indices], dtype=np.float32)
    )[None].to(device)
    rotations = torch.from_numpy(
        np.asarray(archive["global_rot_mats"][indices], dtype=np.float32)
    )[None].to(device)
    contacts = torch.from_numpy(
        np.asarray(archive["foot_contacts"][indices], dtype=np.float32)
    )[None].to(device)
    return positions, rotations, contacts


def load_csv(path: Path, source_fps: int, service: dict):
    raw = np.loadtxt(path, delimiter=",", dtype=np.float32)
    if raw.ndim != 2 or raw.shape[1] != 36:
        raise RuntimeError(f"{path}: expected [N,36], got {raw.shape}")
    raw = raw[nearest_indices(len(raw), source_fps)]
    qpos = np.empty_like(raw)
    qpos[:, :3] = raw[:, :3]
    qpos[:, 3] = raw[:, 6]
    qpos[:, 4:7] = raw[:, 3:6]
    qpos[:, 7:] = raw[:, 7:]
    with torch.no_grad():
        positions, rotations = service["converter"].convert_mujoco_qpos_to_motion_transforms(
            torch.from_numpy(qpos)[None].to(service["device"])
        )
    contacts = torch.zeros(
        [1, len(raw), 4], dtype=torch.float32, device=service["device"]
    )
    return positions, rotations, contacts


def detect_phases(action: str, positions: np.ndarray) -> dict:
    hands = positions[:, [25, 33]]
    if action == "strike":
        signal = np.diff(hands[:, :, 1].mean(1), prepend=hands[:1, :, 1].mean())
        event = int(np.argmin(signal))
    elif action == "block":
        event = int(np.argmax(hands[:, :, 1].mean(1)))
    else:
        separation = np.linalg.norm(hands[:, 0] - hands[:, 1], axis=1)
        lo, hi = len(separation) // 5, len(separation) * 4 // 5
        event = lo + int(np.argmin(separation[lo:hi]))
    active_start = max(1, event - 4)
    active_end = min(len(positions) - 1, event + 5)
    tell_start = max(0, active_start - 10)
    return {
        "tell": [tell_start, active_start],
        "active": [active_start, active_end],
        "recovery": [active_end, len(positions)],
        "event_frame": event,
    }


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    features_dir = OUTPUT / "features"
    features_dir.mkdir(exist_ok=True)
    service = init_service()
    manifest = {
        "schema": "just-dodge-motionbricks-combat-corpus-v1",
        "fps": TARGET_FPS,
        "feature_width": 414,
        "license_policy": "teacher sources must be redistribution/training compatible; runtime contains MotionBricks weights only",
        "entries": [],
    }
    seen_ids: set[str] = set()
    for source_id, action, split, kind, path, source_fps in ENTRIES:
        if source_id in seen_ids:
            raise RuntimeError(f"duplicate source_id {source_id}")
        seen_ids.add(source_id)
        if kind == "ardy":
            positions, rotations, contacts = load_ardy(path, source_fps, service["device"])
        else:
            positions, rotations, contacts = load_csv(path, source_fps, service)
        lengths = torch.tensor([positions.shape[1]], device=service["device"])
        with torch.no_grad():
            features = service["motion_rep"](
                {
                    "posed_joints": positions,
                    "global_joint_rots": rotations,
                    "foot_contacts": contacts,
                },
                to_normalize=True,
                lengths=lengths,
            )[0].cpu().numpy().astype(np.float32)
        if features.shape != (positions.shape[1], 414) or not np.isfinite(features).all():
            raise RuntimeError(f"{source_id}: invalid features {features.shape}")
        feature_path = features_dir / f"{source_id}.npy"
        np.save(feature_path, features, allow_pickle=False)
        phases = detect_phases(action, positions[0].detach().cpu().numpy())
        manifest["entries"].append(
            {
                "source_id": source_id,
                "action": action,
                "split": split,
                "source_kind": kind,
                "source_path": str(path.relative_to(ROOT)),
                "source_sha256": digest(path),
                "source_fps": source_fps,
                "frames_30hz": len(features),
                "features_path": str(feature_path.relative_to(ROOT)),
                "features_sha256": digest(feature_path),
                "phases_30hz": phases,
            }
        )
    for action in ("strike", "block", "grab"):
        splits = {
            entry["split"]
            for entry in manifest["entries"]
            if entry["action"] == action
        }
        if splits != {"train", "validation"}:
            raise RuntimeError(f"{action}: incomplete splits {splits}")
    output_manifest = OUTPUT / "manifest.json"
    output_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"entries": len(manifest["entries"]), "manifest_sha256": digest(output_manifest)}, sort_keys=True))
    print("B14T_COMBAT_CORPUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
