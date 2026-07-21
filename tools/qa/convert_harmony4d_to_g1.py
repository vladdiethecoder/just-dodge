#!/usr/bin/env python3
"""Convert G1 retarget CSV (DOF angles) to 34-joint npz using G1 kinematics.

The CSV has 29-DOF joint angles + root position/rotation.
We compute FK from the DOFs to get 34-joint world positions.
Uses the G1 humanoid's kinematic chain with proper link lengths.
"""
from __future__ import annotations
import json, hashlib, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[2]
G1_DIR = Path("/home/vdubrov/gemx_src/outputs/demo_soma")
OUT_DIR = ROOT / "qa_runs/grab07_combat_corpus/harmony4d_g1"

# G1 humanoid robot kinematic chain (Unitree G1)
# Joint order matches the CSV columns
G1_JOINT_NAMES = [
    "left_hip_pitch", "left_hip_roll", "left_hip_yaw",
    "left_knee", "left_ankle_pitch", "left_ankle_roll",
    "right_hip_pitch", "right_hip_roll", "right_hip_yaw",
    "right_knee", "right_ankle_pitch", "right_ankle_roll",
    "waist_yaw", "waist_roll", "waist_pitch",
    "left_shoulder_pitch", "left_shoulder_roll", "left_shoulder_yaw",
    "left_elbow", "left_wrist_roll", "left_wrist_pitch", "left_wrist_yaw",
    "right_shoulder_pitch", "right_shoulder_roll", "right_shoulder_yaw",
    "right_elbow", "right_wrist_roll", "right_wrist_pitch", "right_wrist_yaw",
]

# G1 link lengths (from Unitree G1 specs, in meters)
# These are approximate values for the G1 humanoid
G1_LINK_LENGTHS = {
    "pelvis_to_waist": 0.15,
    "waist_to_chest": 0.25,
    "chest_to_neck": 0.10,
    "neck_to_head": 0.10,
    "shoulder_to_elbow": 0.25,
    "elbow_to_wrist": 0.20,
    "wrist_to_hand": 0.08,
    "hip_to_knee": 0.40,
    "knee_to_ankle": 0.40,
    "ankle_to_foot": 0.08,
}

# G1 joint offsets (from pelvis, in meters)
# These are the T-pose positions of each joint
G1_JOINT_OFFSETS = {
    "pelvis": np.array([0.0, 0.95, 0.0]),
    "waist_yaw": np.array([0.0, 0.95, 0.0]),
    "waist_roll": np.array([0.0, 1.10, 0.0]),
    "waist_pitch": np.array([0.0, 1.20, 0.0]),
    "left_shoulder_pitch": np.array([0.20, 1.35, 0.0]),
    "left_shoulder_roll": np.array([0.20, 1.35, 0.0]),
    "left_shoulder_yaw": np.array([0.20, 1.35, 0.0]),
    "left_elbow": np.array([0.45, 1.35, 0.0]),
    "left_wrist_roll": np.array([0.65, 1.35, 0.0]),
    "left_wrist_pitch": np.array([0.65, 1.35, 0.0]),
    "left_wrist_yaw": np.array([0.65, 1.35, 0.0]),
    "right_shoulder_pitch": np.array([-0.20, 1.35, 0.0]),
    "right_shoulder_roll": np.array([-0.20, 1.35, 0.0]),
    "right_shoulder_yaw": np.array([-0.20, 1.35, 0.0]),
    "right_elbow": np.array([-0.45, 1.35, 0.0]),
    "right_wrist_roll": np.array([-0.65, 1.35, 0.0]),
    "right_wrist_pitch": np.array([-0.65, 1.35, 0.0]),
    "right_wrist_yaw": np.array([-0.65, 1.35, 0.0]),
    "left_hip_pitch": np.array([0.10, 0.95, 0.0]),
    "left_hip_roll": np.array([0.10, 0.95, 0.0]),
    "left_hip_yaw": np.array([0.10, 0.95, 0.0]),
    "left_knee": np.array([0.10, 0.55, 0.0]),
    "left_ankle_pitch": np.array([0.10, 0.15, 0.0]),
    "left_ankle_roll": np.array([0.10, 0.15, 0.0]),
    "right_hip_pitch": np.array([-0.10, 0.95, 0.0]),
    "right_hip_roll": np.array([-0.10, 0.95, 0.0]),
    "right_hip_yaw": np.array([-0.10, 0.95, 0.0]),
    "right_knee": np.array([-0.10, 0.55, 0.0]),
    "right_ankle_pitch": np.array([-0.10, 0.15, 0.0]),
    "right_ankle_roll": np.array([-0.10, 0.15, 0.0]),
}

# Map to our 34-joint format
G1_TO_34 = {
    "pelvis": 0,
    "left_hip_pitch": 1, "left_hip_roll": 2, "left_hip_yaw": 3,
    "left_knee": 4, "left_ankle_pitch": 5, "left_ankle_roll": 6,
    "right_hip_pitch": 8, "right_hip_roll": 9, "right_hip_yaw": 10,
    "right_knee": 11, "right_ankle_pitch": 12, "right_ankle_roll": 13,
    "waist_yaw": 15, "waist_roll": 16, "waist_pitch": 17,
    "left_shoulder_pitch": 18, "left_shoulder_roll": 19, "left_shoulder_yaw": 20,
    "left_elbow": 21, "left_wrist_roll": 22, "left_wrist_pitch": 23, "left_wrist_yaw": 24,
    "right_shoulder_pitch": 26, "right_shoulder_roll": 27, "right_shoulder_yaw": 28,
    "right_elbow": 29, "right_wrist_roll": 30, "right_wrist_pitch": 31, "right_wrist_yaw": 32,
    # Hands: approximate from wrist positions
    "left_hand": 25, "right_hand": 33,
}

NUM_JOINTS = 34


def compute_fk(df_row):
    """Compute 34-joint world positions from G1 DOF values."""
    # Root position (mm -> m)
    root_x = df_row["root_translateX"] / 1000.0
    root_y = df_row["root_translateY"] / 1000.0
    root_z = df_row["root_translateZ"] / 1000.0
    root_pos = np.array([root_x, root_y, root_z])

    # Root rotation (degrees -> radians)
    root_rx = np.radians(df_row["root_rotateX"])
    root_ry = np.radians(df_row["root_rotateY"])
    root_rz = np.radians(df_row["root_rotateZ"])
    root_rot = Rotation.from_euler('XYZ', [root_rx, root_ry, root_rz])

    # Initialize joint positions
    g1_pos = np.zeros((NUM_JOINTS, 3))
    g1_pos[0] = root_pos  # pelvis

    # Compute FK for each joint chain
    # This is a simplified FK that applies DOF rotations to link offsets
    # For each joint, we compute its position relative to its parent

    # Legs (left and right)
    for side in ["left", "right"]:
        hip_pitch = np.radians(df_row[f"{side}_hip_pitch_joint_dof"])
        hip_roll = np.radians(df_row[f"{side}_hip_roll_joint_dof"])
        hip_yaw = np.radians(df_row[f"{side}_hip_yaw_joint_dof"])
        knee = np.radians(df_row[f"{side}_knee_joint_dof"])
        ankle_pitch = np.radians(df_row[f"{side}_ankle_pitch_joint_dof"])
        ankle_roll = np.radians(df_row[f"{side}_ankle_roll_joint_dof"])

        # Hip position (from pelvis, offset laterally)
        hip_offset = 0.10 if side == "left" else -0.10
        hip_pos = root_pos + root_rot.apply(np.array([hip_offset, 0.0, 0.0]))

        # Knee position (from hip, along thigh)
        thigh_length = 0.40
        knee_dir = Rotation.from_euler('XYZ', [hip_pitch, hip_roll, hip_yaw]).apply(np.array([0.0, -1.0, 0.0]))
        knee_pos = hip_pos + knee_dir * thigh_length

        # Ankle position (from knee, along shank)
        shank_length = 0.40
        ankle_dir = Rotation.from_euler('XYZ', [knee, 0.0, 0.0]).apply(np.array([0.0, -1.0, 0.0]))
        ankle_pos = knee_pos + ankle_dir * shank_length

        # Foot position (from ankle, forward)
        foot_length = 0.08
        foot_dir = Rotation.from_euler('XYZ', [ankle_pitch, ankle_roll, 0.0]).apply(np.array([0.0, 0.0, 1.0]))
        foot_pos = ankle_pos + foot_dir * foot_length

        # Map to 34-joint indices
        prefix = "l" if side == "left" else "r"
        g1_pos[G1_TO_34[f"{side}_hip_pitch"]] = hip_pos
        g1_pos[G1_TO_34[f"{side}_hip_roll"]] = hip_pos
        g1_pos[G1_TO_34[f"{side}_hip_yaw"]] = hip_pos
        g1_pos[G1_TO_34[f"{side}_knee"]] = knee_pos
        g1_pos[G1_TO_34[f"{side}_ankle_pitch"]] = ankle_pos
        g1_pos[G1_TO_34[f"{side}_ankle_roll"]] = ankle_pos

    # Spine (waist)
    waist_yaw = np.radians(df_row["waist_yaw_joint_dof"])
    waist_roll = np.radians(df_row["waist_roll_joint_dof"])
    waist_pitch = np.radians(df_row["waist_pitch_joint_dof"])

    waist_pos = root_pos + root_rot.apply(np.array([0.0, 0.15, 0.0]))
    g1_pos[G1_TO_34["waist_yaw"]] = waist_pos
    g1_pos[G1_TO_34["waist_roll"]] = waist_pos
    g1_pos[G1_TO_34["waist_pitch"]] = waist_pos

    # Arms (left and right)
    for side in ["left", "right"]:
        shoulder_pitch = np.radians(df_row[f"{side}_shoulder_pitch_joint_dof"])
        shoulder_roll = np.radians(df_row[f"{side}_shoulder_roll_joint_dof"])
        shoulder_yaw = np.radians(df_row[f"{side}_shoulder_yaw_joint_dof"])
        elbow = np.radians(df_row[f"{side}_elbow_joint_dof"])
        wrist_roll = np.radians(df_row[f"{side}_wrist_roll_joint_dof"])
        wrist_pitch = np.radians(df_row[f"{side}_wrist_pitch_joint_dof"])
        wrist_yaw = np.radians(df_row[f"{side}_wrist_yaw_joint_dof"])

        # Shoulder position (from chest, offset laterally)
        shoulder_offset = 0.20 if side == "left" else -0.20
        chest_pos = waist_pos + root_rot.apply(np.array([0.0, 0.25, 0.0]))
        shoulder_pos = chest_pos + root_rot.apply(np.array([shoulder_offset, 0.0, 0.0]))

        # Elbow position (from shoulder, along upper arm)
        upper_arm_length = 0.25
        elbow_dir = Rotation.from_euler('XYZ', [shoulder_pitch, shoulder_roll, shoulder_yaw]).apply(np.array([1.0 if side == "left" else -1.0, 0.0, 0.0]))
        elbow_pos = shoulder_pos + elbow_dir * upper_arm_length

        # Wrist position (from elbow, along forearm)
        forearm_length = 0.20
        wrist_dir = Rotation.from_euler('XYZ', [elbow, 0.0, 0.0]).apply(np.array([1.0 if side == "left" else -1.0, 0.0, 0.0]))
        wrist_pos = elbow_pos + wrist_dir * forearm_length

        # Hand position (from wrist, forward)
        hand_length = 0.08
        hand_dir = Rotation.from_euler('XYZ', [wrist_roll, wrist_pitch, wrist_yaw]).apply(np.array([0.0, 0.0, 1.0]))
        hand_pos = wrist_pos + hand_dir * hand_length

        # Map to 34-joint indices
        g1_pos[G1_TO_34[f"{side}_shoulder_pitch"]] = shoulder_pos
        g1_pos[G1_TO_34[f"{side}_shoulder_roll"]] = shoulder_pos
        g1_pos[G1_TO_34[f"{side}_shoulder_yaw"]] = shoulder_pos
        g1_pos[G1_TO_34[f"{side}_elbow"]] = elbow_pos
        g1_pos[G1_TO_34[f"{side}_wrist_roll"]] = wrist_pos
        g1_pos[G1_TO_34[f"{side}_wrist_pitch"]] = wrist_pos
        g1_pos[G1_TO_34[f"{side}_wrist_yaw"]] = wrist_pos
        g1_pos[G1_TO_34["left_hand" if side == "left" else "right_hand"]] = hand_pos

    return g1_pos


def convert_csv(csv_path, out_path):
    df = pd.read_csv(csv_path)
    T = len(df)
    posed = np.zeros((T, NUM_JOINTS, 3))
    root = np.zeros((T, 3))

    for t in range(T):
        row = df.iloc[t]
        g1_pos = compute_fk(row)
        posed[t] = g1_pos
        root[t] = g1_pos[0]

    # Normalize: center root XZ
    posed[:, :, 0] -= posed[0, 0, 0]
    posed[:, :, 2] -= posed[0, 0, 2]

    np.savez_compressed(out_path, posed_joints=posed, root_positions=root)
    return posed, root


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_dir = Path(G1_DIR)
    csv_files = sorted(csv_dir.rglob("*retarget_g1.csv"))
    if not csv_files:
        print("BLOCKED: no retarget CSV files found")
        return 2

    clips = []
    for csv_path in csv_files:
        name = csv_path.stem.replace("_retarget_g1", "")
        out_path = OUT_DIR / f"{name}.npz"
        try:
            posed, root = convert_csv(csv_path, out_path)
            sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
            clips.append({
                "clip_id": name, "path": str(out_path),
                "sha256": sha, "frames": int(posed.shape[0]),
            })
            print(f"  {name}: {posed.shape[0]} frames -> {out_path.name}")
        except Exception as e:
            print(f"ERROR {csv_path.name}: {e}", file=sys.stderr)

    manifest = {
        "schema": "just-dodge-harmony4d-g1-corpus-v2",
        "source": "Harmony4D grappling video via GEM-X V2M (MIT license)",
        "url": "https://huggingface.co/datasets/Jyun-Ting/Harmony4D",
        "runtime_allowed": False,
        "training_allowed": True,
        "pipeline": "video -> GEM-X -> SOMA -> Newton retargeter -> G1 CSV -> FK -> npz",
        "total_clips": len(clips),
        "clips": clips,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(f"HARMONY4D_G1_CONVERTED clips={len(clips)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
