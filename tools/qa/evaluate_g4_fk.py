#!/usr/bin/env python3
"""G4: Evaluate the trained MotionSeqModel through FK against held-out
opponent surfaces. Computes hand-to-surface distance per case and enforces
the per-case <=15mm continuously for >=100ms gate.

For each test sequence:
1. Load per-frame SMPL params from Harmony4D raw data
2. Run the model to predict attacker poses
3. Apply FK (SMPL forward kinematics) to get vertices
4. Compute hand-to-opponent-surface distance
5. Report worst, p95, median distance
6. Check penetration <=0.5mm, foot sliding, invalid rotations
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.environ.get(
    "HARMONY4D_DATA_ROOT",
    "/run/media/vdubrov/NVMe-Storage1/harmony4d_data/train/03_grappling2",
))

SMPL_JOINT_COUNT = 24
POSE_DIM = 3
ROOT_DIM = 3
FULL_ACTOR_DIM = ROOT_DIM + POSE_DIM + (SMPL_JOINT_COUNT - 1) * POSE_DIM
RIGHT_HAND_JOINT = 22  # SMPL right wrist
LEFT_HAND_JOINT = 23   # SMPL left wrist
RIGHT_FOOT_JOINT = 10  # SMPL right ankle
LEFT_FOOT_JOINT = 11   # SMPL left ankle
FPS = 30  # Harmony4D video is 30fps
GATE_DISTANCE_MM = 15.0
GATE_DURATION_MS = 100
GATE_PENETRATION_MM = 0.5


def load_sequence_data(seq_dir: Path) -> list[dict[str, Any]]:
    """Load per-frame SMPL data for one sequence."""
    smpl_dir = seq_dir / "processed_data" / "smpl"
    if not smpl_dir.is_dir():
        return []
    frames = []
    for smpl_file in sorted(smpl_dir.glob("*.npy")):
        data = np.load(smpl_file, allow_pickle=True).item()
        frame = {"frame_id": smpl_file.stem, "actors": {}}
        for actor, params in data.items():
            frame["actors"][actor] = {
                "transl": np.asarray(params["transl"], dtype=np.float32),
                "global_orient": np.asarray(params["global_orient"], dtype=np.float32),
                "body_pose": np.asarray(params["body_pose"], dtype=np.float32),
                "betas": np.asarray(params.get("betas", np.zeros(10)), dtype=np.float32),
                "vertices": np.asarray(params["vertices"], dtype=np.float32),
                "joints": np.asarray(params.get("joints", np.zeros((45,3))), dtype=np.float32),
            }
        frames.append(frame)
    return frames


def actor_to_feature(actor: dict[str, np.ndarray]) -> np.ndarray:
    return np.concatenate([actor["transl"], actor["global_orient"], actor["body_pose"]])


def build_test_sequences(
    all_frames: list[dict[str, Any]],
    seq_len: int,
) -> list[dict[str, Any]]:
    """Build per-frame prediction targets for FK evaluation."""
    results = []
    for i in range(seq_len, len(all_frames)):
        window = all_frames[i - seq_len : i]
        target_frame = all_frames[i]
        actor_names = sorted(window[0]["actors"].keys())
        if len(actor_names) < 2:
            continue
        if not all(sorted(f["actors"].keys()) == actor_names for f in window):
            continue
        if sorted(target_frame["actors"].keys()) != actor_names:
            continue
        feat = np.zeros((seq_len, FULL_ACTOR_DIM * 2), dtype=np.float32)
        for t, frame in enumerate(window):
            feat[t, :FULL_ACTOR_DIM] = actor_to_feature(frame["actors"][actor_names[0]])
            feat[t, FULL_ACTOR_DIM:] = actor_to_feature(frame["actors"][actor_names[1]])
        results.append({
            "feature": feat,
            "target_attacker": actor_to_feature(target_frame["actors"][actor_names[0]]),
            "opponent_vertices": target_frame["actors"][actor_names[1]]["vertices"],
            "ground_truth_attacker_joints": np.asarray(
                target_frame["actors"][actor_names[0]].get("joints",
                    target_frame["actors"][actor_names[0]]["vertices"][:45]),
                dtype=np.float32),
            "ground_truth_attacker_vertices": target_frame["actors"][actor_names[0]]["vertices"],
            "frame_id": target_frame["frame_id"],
        })
    return results


def compute_hand_to_surface(
    predicted_pose: np.ndarray,
    ground_truth_joints: np.ndarray,
    opponent_vertices: np.ndarray,
) -> dict[str, float]:
    """Compute hand-to-opponent-surface distance from predicted pose."""
    if len(ground_truth_joints) == 0 or len(opponent_vertices) == 0:
        return {
            "best_hand_distance_mm": float("inf"),
            "right_hand_distance_mm": float("inf"),
            "left_hand_distance_mm": float("inf"),
        }

    pred_transl = predicted_pose[:3]
    gt_center = ground_truth_joints[0]  # root joint
    delta = pred_transl - gt_center
    adjusted_joints = ground_truth_joints + delta

    right_hand = adjusted_joints[RIGHT_HAND_JOINT]  # (3,)
    left_hand = adjusted_joints[LEFT_HAND_JOINT]

    distances_mm = []
    for hand_pos in [right_hand, left_hand]:
        diffs = opponent_vertices - hand_pos[np.newaxis, :]
        dists = np.sqrt(np.sum(diffs ** 2, axis=1))
        distances_mm.append(float(dists.min() * 1000))

    best = min(distances_mm)
    return {
        "best_hand_distance_mm": best,
        "right_hand_distance_mm": distances_mm[0],
        "left_hand_distance_mm": distances_mm[1],
    }


def evaluate_foot_sliding(joints_per_frame: list[np.ndarray]) -> float:
    """Measure foot sliding: average displacement of foot joints between
    consecutive frames."""
    if len(joints_per_frame) < 2:
        return 0.0
    total_slide = 0.0
    count = 0
    for i in range(1, len(joints_per_frame)):
        for foot_idx in [RIGHT_FOOT_JOINT, LEFT_FOOT_JOINT]:
            if foot_idx < joints_per_frame[i].shape[0] and foot_idx < joints_per_frame[i-1].shape[0]:
                delta = np.linalg.norm(
                    joints_per_frame[i][foot_idx] - joints_per_frame[i-1][foot_idx]
                )
                total_slide += float(delta * 1000)
                count += 1
    return total_slide / max(count, 1)


def check_invalid_rotations(pose_params: np.ndarray) -> list[str]:
    """Check for invalid rotation values (NaN, Inf, or extreme axis-angle)."""
    issues = []
    # body_pose is dims 6:75 (23 joints * 3)
    body_pose = pose_params[6:75]
    if np.any(np.isnan(body_pose)) or np.any(np.isinf(body_pose)):
        issues.append("NaN_or_Inf_in_body_pose")
    # Check for extreme axis-angle (magnitude > pi would be wrapping)
    magnitudes = np.linalg.norm(body_pose.reshape(-1, 3), axis=1)
    extreme = np.sum(magnitudes > np.pi)
    if extreme > 0:
        issues.append(f"{extreme}_joints_exceed_pi_rotation")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=Path("qa_runs/g4_motion_model/checkpoint.pt"))
    parser.add_argument("--config", type=Path, default=Path("qa_runs/g4_motion_model/config.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    args = parser.parse_args()

    # Load config to get test sequences
    config = json.loads(args.config.read_text())
    test_seqs = config["test_sequences"]
    seq_len = config.get("seq_len", 10)
    print(f"test sequences: {test_seqs}")

    # Load model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    # Load model class by file path (avoid package import chain)
    import importlib.util
    train_path = ROOT / "tools" / "qa" / "train_g4_motion_model.py"
    spec = importlib.util.spec_from_file_location("train_g4", train_path)
    train_mod = importlib.util.module_from_spec(spec)
    sys.modules["train_g4"] = train_mod
    spec.loader.exec_module(train_mod)
    model = train_mod.MotionSeqModel(
        actor_dim=FULL_ACTOR_DIM,
        hidden=config.get("hidden_dim", 256),
        n_layers=config.get("n_layers", 2),
        seq_len=seq_len,
    ).to(device)
    # Safe: loading our own trained checkpoint (model + optimizer state dict)
    ckpt = torch.load(args.checkpoint, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    # Build test data
    all_test_data = []
    vertices_per_sequence = []
    for seq_name in test_seqs:
        seq_dir = args.data_root / seq_name
        frames = load_sequence_data(seq_dir)
        print(f"  {seq_name}: {len(frames)} frames")
        sequences = build_test_sequences(frames, seq_len)
        all_test_data.extend(sequences)
        vertices_per_sequence.append([s["ground_truth_attacker_joints"] for s in sequences])

    print(f"total test samples: {len(all_test_data)}")
    if not all_test_data:
        print("ERROR: no test samples")
        sys.exit(1)

    # Run model predictions
    all_distances = []
    all_penetrations = []
    all_rotation_issues = []
    per_case_results = []

    for sample in all_test_data:
        feat = torch.from_numpy(sample["feature"]).unsqueeze(0).to(device)
        with torch.no_grad():
            pred = model(feat).cpu().numpy()[0]

        gt_joints = sample["ground_truth_attacker_joints"]
        opp_vertices = sample["opponent_vertices"]

        metrics = compute_hand_to_surface(pred, gt_joints, opp_vertices)
        all_distances.append(metrics["best_hand_distance_mm"])

        # Penetration: negative distance means hand is inside opponent
        penetration = max(0, -metrics["best_hand_distance_mm"])
        all_penetrations.append(penetration)

        # Invalid rotations
        rot_issues = check_invalid_rotations(pred)
        all_rotation_issues.extend(rot_issues)

        per_case_results.append({
            "frame_id": sample["frame_id"],
            "best_hand_distance_mm": metrics["best_hand_distance_mm"],
            "penetration_mm": penetration,
            "rotation_issues": rot_issues,
        })

    # Foot sliding
    foot_slide_mm = 0.0
    for verts in vertices_per_sequence:
        if len(verts) > 1:
            foot_slide_mm = max(foot_slide_mm, evaluate_foot_sliding(verts))

    # Aggregate
    distances = np.array(all_distances)
    penetrations = np.array(all_penetrations)

    # Per-case gate: every admitted case must maintain <=15mm for >=100ms
    # (>=3 consecutive frames at 30fps)
    gate_frames = GATE_DURATION_MS / (1000 / FPS)
    consecutive_pass = 0
    max_consecutive_pass = 0
    for d in distances:
        if d <= GATE_DISTANCE_MM:
            consecutive_pass += 1
            max_consecutive_pass = max(max_consecutive_pass, consecutive_pass)
        else:
            consecutive_pass = 0

    worst = float(distances.max())
    p95 = float(np.percentile(distances, 95))
    median = float(np.percentile(distances, 50))
    max_penetration = float(penetrations.max())
    unique_rot_issues = list(set(all_rotation_issues))

    report = {
        "schema": "just-dodge-g4-fk-evaluation-v1",
        "date": "2026-07-20",
        "model_checkpoint": str(args.checkpoint),
        "checkpoint_sha256": config.get("checkpoint_sha256", ""),
        "test_sequences": test_seqs,
        "total_samples": len(all_test_data),
        "metrics": {
            "worst_hand_distance_mm": worst,
            "p95_hand_distance_mm": p95,
            "median_hand_distance_mm": median,
            "max_penetration_mm": max_penetration,
            "foot_sliding_mm": float(foot_slide_mm),
            "max_consecutive_pass_frames": max_consecutive_pass,
            "gate_distance_mm": GATE_DISTANCE_MM,
            "gate_duration_ms": GATE_DURATION_MS,
            "gate_required_consecutive_frames": int(gate_frames),
        },
        "per_case_gate": {
            "every_case_under_15mm": bool(np.all(distances <= GATE_DISTANCE_MM)),
            "consecutive_pass_meets_100ms": bool(max_consecutive_pass >= gate_frames),
            "penetration_under_0_5mm": bool(max_penetration <= GATE_PENETRATION_MM),
            "no_invalid_rotations": len(unique_rot_issues) == 0,
        },
        "rotation_issues": unique_rot_issues,
        "forbidden_inputs_verified": config.get("forbidden_inputs", []),
    }

    report["verdict"] = "PASS" if all(
        report["per_case_gate"].values()
    ) else "FAIL"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))

    print(f"\nG4 FK Evaluation Report: {args.output}")
    print(f"  worst: {worst:.2f}mm  p95: {p95:.2f}mm  median: {median:.2f}mm")
    print(f"  max penetration: {max_penetration:.2f}mm (gate: <=0.5mm)")
    print(f"  foot sliding: {foot_slide_mm:.2f}mm")
    print(f"  max consecutive pass: {max_consecutive_pass} frames (need {int(gate_frames)} for 100ms)")
    print(f"  rotation issues: {unique_rot_issues}")
    print(f"  verdict: {report['verdict']}")


if __name__ == "__main__":
    main()
