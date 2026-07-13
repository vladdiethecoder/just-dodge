#!/usr/bin/env python3
"""Visual QA for MotionBricks Strike/Idle primitives.

Generates clips via the production Python service, parses G1 world-space joint
positions, renders stick-figure keyframes, and reports quantitative motion
metrics.  This is evidence for the "no placeholders" gate.
"""

import json
import os
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt

# Project root is two levels up from tools/qa/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from motionbricks_service.generate import generate_clip

G1_PARENTS = np.array([
    -1, 0, 1, 2, 3, 4, 5, 6, 0, 8, 9, 10, 11, 12, 13, 0, 15, 16, 17, 18,
    19, 20, 21, 22, 23, 24, 17, 26, 27, 28, 29, 30, 31, 32,
], dtype=np.int32)

G1_NAMES = [
    "pelvis",
    "left_hip", "left_knee", "left_ankle", "left_foot", "left_toe",
    "left_toe_end", "left_heel",
    "right_hip", "right_knee", "right_ankle", "right_foot", "right_toe",
    "right_toe_end", "right_heel",
    "spine_low", "spine_mid", "spine_high",
    "neck", "head", "head_top",
    "left_shoulder", "left_elbow", "left_wrist", "left_hand",
    "left_index", "right_shoulder", "right_elbow", "right_wrist",
    "right_hand", "right_index",
]


def parse_g1_frame(rec: np.ndarray) -> np.ndarray:
    """Parse one [413] float32 frame into 34 world-space positions."""
    assert rec.shape == (413,), f"expected [413], got {rec.shape}"
    root = rec[0:3]
    # ric_data: 33 root-relative positions for joints 1..33
    ric = rec[5:104].reshape(33, 3)
    positions = np.zeros((34, 3), dtype=np.float32)
    positions[0] = root
    positions[1:] = root + ric
    return positions


def parse_clip_bytes(data: bytes, root_lock: bool = True) -> np.ndarray:
    """Return [N, 34, 3] positions from raw service bytes.

    When root_lock=True, subtract the first-frame root translation from every
    frame so metrics measure pose quality without runaway global root drift.
    """
    floats = np.frombuffer(data, dtype=np.float32)
    if floats.size % 413 != 0:
        raise ValueError(f"byte length {len(data)} not divisible by 413 floats")
    n = floats.size // 413
    frames = floats.reshape(n, 413)
    positions = np.stack([parse_g1_frame(f) for f in frames], axis=0)
    if root_lock and n > 0:
        root_offset = positions[0, 0, :].copy()
        positions[:, :, :] -= root_offset[None, None, :]
    return positions


def render_pose(ax, positions: np.ndarray, title: str, view: str):
    """Draw a stick figure on the given matplotlib axis."""
    ax.set_title(title, fontsize=8)
    ax.set_aspect("equal")

    # Draw bones
    for i, p in enumerate(G1_PARENTS):
        if p < 0:
            continue
        xs = [positions[p, 0], positions[i, 0]]
        zs = [positions[p, 2], positions[i, 2]] if view == "top" else [positions[p, 1], positions[i, 1]]
        ax.plot(xs, zs, "k-", linewidth=1.2, alpha=0.7)

    # Draw joints
    xs = positions[:, 0]
    ys = positions[:, 2] if view == "top" else positions[:, 1]
    ax.scatter(xs, ys, s=8, c="red", zorder=5)

    # Mark pelvis
    ax.scatter([positions[0, 0]], [positions[0, 2] if view == "top" else positions[0, 1]], s=30, c="blue", zorder=6)

    if view == "front":
        ax.set_xlabel("X"); ax.set_ylabel("Y")
    elif view == "side":
        ax.set_xlabel("Z"); ax.set_ylabel("Y")
    else:
        ax.set_xlabel("X"); ax.set_ylabel("Z")


def compute_metrics(positions: np.ndarray) -> dict:
    """Compute basic motion sanity metrics."""
    n = positions.shape[0]
    root = positions[:, 0, :]
    # Total root displacement
    root_path = float(np.sum(np.linalg.norm(np.diff(root, axis=0), axis=1)))
    # Max per-frame joint velocity (any joint)
    velocities = np.linalg.norm(np.diff(positions, axis=0), axis=2)
    max_velocity = float(np.max(velocities))
    mean_velocity = float(np.mean(velocities))
    # Bounding box over the whole clip
    bbox_min = positions.min(axis=(0, 1)).tolist()
    bbox_max = positions.max(axis=(0, 1)).tolist()
    # End-effector ranges
    left_hand = positions[:, 25, :]
    right_hand = positions[:, 30, :]
    return {
        "frames": n,
        "duration_seconds": round(n / 30.0, 3),
        "root_path_m": round(root_path, 4),
        "max_joint_velocity_m_per_frame": round(max_velocity, 4),
        "mean_joint_velocity_m_per_frame": round(mean_velocity, 4),
        "bbox_min": [round(x, 4) for x in bbox_min],
        "bbox_max": [round(x, 4) for x in bbox_max],
        "left_hand_range_m": round(float(np.linalg.norm(left_hand.max(axis=0) - left_hand.min(axis=0))), 4),
        "right_hand_range_m": round(float(np.linalg.norm(right_hand.max(axis=0) - right_hand.min(axis=0))), 4),
    }


def main():
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / "qa_runs" / f"visual_primitives_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[visual_verify_primitives] writing QA artifacts to {out_dir}")

    report = {"timestamp": ts, "actions": {}}

    for action in ["Idle", "Strike", "Block", "Thrust", "Grab", "Dodge"]:
        print(f"[visual_verify_primitives] generating {action}...")
        data = generate_clip(action, "Longsword", "Top", None, seed=1)
        raw_positions = parse_clip_bytes(data, root_lock=False)
        print(f"  -> {raw_positions.shape[0]} frames")

        # Sanity checks on world-space output before root-locking
        if not np.all(np.isfinite(raw_positions)):
            raise ValueError(f"{action}: generated joint positions contain non-finite values")
        root_height = raw_positions[:, 0, 1]
        if root_height.min() < 0.3 or root_height.max() > 2.0:
            raise ValueError(
                f"{action}: pelvis height {root_height.min():.3f}..{root_height.max():.3f}m "
                f"outside allowed range [0.3, 2.0]m"
            )

        # Root-lock for metrics/plots so they measure pose quality independent of drift
        positions = parse_clip_bytes(data, root_lock=True)
        metrics = compute_metrics(positions)
        report["actions"][action] = metrics

        # Pick keyframes: start, 25%, 50%, 75%, end
        n = positions.shape[0]
        key_indices = [0, n // 4, n // 2, 3 * n // 4, n - 1]

        fig, axes = plt.subplots(len(key_indices), 3, figsize=(9, 3 * len(key_indices)))
        if len(key_indices) == 1:
            axes = axes.reshape(1, 3)
        for row, idx in enumerate(key_indices):
            render_pose(axes[row, 0], positions[idx], f"{action} frame {idx} front", "front")
            render_pose(axes[row, 1], positions[idx], f"{action} frame {idx} side", "side")
            render_pose(axes[row, 2], positions[idx], f"{action} frame {idx} top", "top")
        plt.tight_layout()
        chart_path = out_dir / f"{action.lower()}_keyframes.png"
        plt.savefig(chart_path, dpi=150)
        plt.close()
        print(f"  -> saved {chart_path}")

        # Per-frame root trajectory
        fig, ax = plt.subplots(figsize=(6, 6))
        root = positions[:, 0, :]
        ax.plot(root[:, 0], root[:, 2], "b-o", markersize=2, linewidth=0.8)
        ax.set_aspect("equal")
        ax.set_title(f"{action} root trajectory (XZ)")
        ax.set_xlabel("X"); ax.set_ylabel("Z")
        traj_path = out_dir / f"{action.lower()}_root_trajectory.png"
        plt.savefig(traj_path, dpi=150)
        plt.close()

    report_path = out_dir / "report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[visual_verify_primitives] report saved to {report_path}")

    # Print summary verdict
    print("\n--- Visual QA Summary ---")
    for action, m in report["actions"].items():
        print(f"{action}: {m['frames']} frames, root_path={m['root_path_m']}m, max_vel={m['max_joint_velocity_m_per_frame']}m/f")


if __name__ == "__main__":
    main()
