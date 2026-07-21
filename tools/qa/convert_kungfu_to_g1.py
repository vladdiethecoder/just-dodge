#!/usr/bin/env python3
"""Convert KungfuAthleteBot G1 29-DOF MuJoCo data to G1 34-joint world positions.

KungfuAthleteBot provides 512 Wushu clips in MuJoCo G1 humanoid format:
  body_pos_w: [T, 53, 3] world-space body link positions
  body_quat_w: [T, 53, 4] world-space body orientations
  fps: 50

We map the 53 MuJoCo bodies to our 34-joint G1 skeleton and output:
  posed_joints: [T, 34, 3] world-space joint positions (hips == root)
  root_positions: [T, 3]
"""
from __future__ import annotations
import json, hashlib, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
KF_DIR = Path("/run/media/vdubrov/Bulk-SSD/combat_mocap_sources/kungfu_athlete_bot")
OUT_DIR = ROOT / "qa_runs/grab07_combat_corpus/kungfu_g1"

# MuJoCo G1 body name -> MotionBricks G1 joint index (34 joints)
# The G1 humanoid has 53 bodies. We map the key skeletal points.
MUJOCO_TO_G1 = {
    # Root/pelvis
    "pelvis": 0,
    # Spine
    "torso": 1, "chest": 2,
    # Neck/head
    "neck": 3, "head": 4,
    # Left arm
    "left_shoulder_pitch_link": 5, "left_shoulder_roll_link": 6,
    "left_elbow_link": 8, "left_wrist_roll_link": 9,
    # Left hand (end effector)
    "left_wrist_pitch_link": 25,
    # Right arm
    "right_shoulder_pitch_link": 10, "right_shoulder_roll_link": 11,
    "right_elbow_link": 13, "right_wrist_roll_link": 14,
    # Right hand (end effector)
    "right_wrist_pitch_link": 33,
    # Left leg
    "left_hip_pitch_link": 15, "left_hip_roll_link": 15,
    "left_knee_link": 17, "left_ankle_pitch_link": 18,
    "left_ankle_roll_link": 19,
    # Right leg
    "right_hip_pitch_link": 20, "right_hip_roll_link": 20,
    "right_knee_link": 22, "right_ankle_pitch_link": 23,
    "right_ankle_roll_link": 24,
}


def convert_clip(npz_path: Path) -> tuple[np.ndarray, np.ndarray, int]:
    d = np.load(npz_path)
    body_pos = d["body_pos_w"]  # [T, 53, 3]
    body_names = [str(b) for b in d["body_names"]]
    fps = int(d["fps"][0])
    T = body_pos.shape[0]

    # Build name -> body index map
    name_to_idx = {name: i for i, name in enumerate(body_names)}

    # MuJoCo uses Z-up; our system uses Y-up. Swap Y<->Z for all positions.
    body_pos = body_pos[:, :, [0, 2, 1]]  # X stays, Z->Y, Y->Z

    # Map to 34-joint G1
    g1_pos = np.zeros((T, 34, 3))
    filled = np.zeros(34, dtype=bool)

    for mj_name, g1_idx in MUJOCO_TO_G1.items():
        if mj_name in name_to_idx:
            g1_pos[:, g1_idx] = body_pos[:, name_to_idx[mj_name]]
            filled[g1_idx] = True

    # Fill gaps: interpolate from nearest filled joint
    for i in range(34):
        if not filled[i]:
            # Copy from nearest lower filled joint
            for j in range(i - 1, -1, -1):
                if filled[j]:
                    g1_pos[:, i] = g1_pos[:, j]
                    break
            else:
                g1_pos[:, i] = g1_pos[:, 0]

    root = g1_pos[:, 0, :].copy()
    return g1_pos, root, fps


def main():
    datasets_dir = KF_DIR / "kungfu_athlete_for_g1_29dof/datasets/org_smooth_mj"
    files = sorted(datasets_dir.glob("*.npz"))
    if not files:
        print("BLOCKED: no KungfuAthleteBot npz files found")
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    clips = []

    for npz_path in files:
        try:
            g1_pos, root, fps = convert_clip(npz_path)
            # Resample to 60fps if needed
            if fps != 60:
                T_old = g1_pos.shape[0]
                T_new = int(T_old * 60 / fps)
                idx = np.linspace(0, T_old - 1, T_new).astype(int)
                g1_pos = g1_pos[idx]
                root = root[idx]

            # Normalize: center root XZ at origin for first frame
            g1_pos[:, :, 0] -= g1_pos[0, 0, 0]
            g1_pos[:, :, 2] -= g1_pos[0, 0, 2]

            # Limit to 120 frames max (2s at 60fps)
            if g1_pos.shape[0] > 120:
                g1_pos = g1_pos[:120]
                root = root[:120]

            clip_id = npz_path.stem
            out_path = OUT_DIR / f"{clip_id}.npz"
            np.savez_compressed(out_path,
                                posed_joints=g1_pos.astype(np.float32),
                                root_positions=root.astype(np.float32))

            sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
            clips.append({"clip_id": clip_id, "path": str(out_path),
                          "sha256": sha, "frames": int(g1_pos.shape[0])})
        except Exception as e:
            print(f"ERROR {npz_path.name}: {e}", file=sys.stderr)

    manifest = {
        "schema": "just-dodge-kungfu-g1-corpus-v1",
        "source": "KungfuAthleteBot (Apache-2.0)",
        "url": "https://huggingface.co/datasets/silveroxides/KungfuAthleteBot",
        "runtime_allowed": False,
        "training_allowed": True,
        "format": "MuJoCo G1 29-DOF -> MotionBricks G1 34-joint world positions",
        "fps": 60,
        "total_clips": len(clips),
        "clips": clips,
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(f"KUNGFU_G1_CONVERTED clips={len(clips)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
