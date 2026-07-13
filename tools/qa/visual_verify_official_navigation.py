#!/usr/bin/env python3
"""Fail-closed visual QA for NVIDIA's official MotionBricks navigation path.

This intentionally exercises only `generate_official_navigation_clip`: the
released checkpoint is locomotion/navigation-only and this tool must never be
used as evidence for combat-action semantics.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from motionbricks_service.generate import generate_official_navigation_clip
from visual_verify_primitives import G1_PARENTS, compute_metrics, parse_clip_bytes, render_pose


def validate_source(positions: np.ndarray) -> dict:
    if positions.shape[0] < 8:
        raise ValueError(f"official navigation emitted only {positions.shape[0]} frames")
    if not np.isfinite(positions).all():
        raise ValueError("official navigation contains non-finite G1 joint positions")

    root_height = positions[:, 0, 1]
    if root_height.min() < 0.3 or root_height.max() > 2.0:
        raise ValueError(
            f"official navigation pelvis height {root_height.min():.4f}.."
            f"{root_height.max():.4f}m outside [0.3, 2.0]m"
        )

    reference = []
    errors = []
    for joint, parent in enumerate(G1_PARENTS):
        if parent < 0:
            continue
        lengths = np.linalg.norm(positions[:, joint] - positions[:, parent], axis=1)
        reference.append(float(lengths[0]))
        errors.extend(np.abs(lengths - lengths[0]))
    max_segment_error = float(np.max(errors))
    if max_segment_error >= 1.0e-4:
        raise ValueError(f"G1 segment-length drift {max_segment_error:.6f}m exceeds 1e-4m")

    joint_steps = np.linalg.norm(np.diff(positions, axis=0), axis=2)
    max_joint_step = float(np.max(joint_steps))
    if max_joint_step >= 0.2:
        raise ValueError(f"G1 discontinuity {max_joint_step:.6f}m/frame exceeds 0.2m/frame")

    return {
        "root_height_min_m": round(float(root_height.min()), 6),
        "root_height_max_m": round(float(root_height.max()), 6),
        "max_segment_length_error_m": round(max_segment_error, 8),
        "max_joint_step_m_per_frame": round(max_joint_step, 6),
        "reference_segment_count": len(reference),
    }


def render_keyframes(positions: np.ndarray, output_path: Path) -> None:
    indices = [0, positions.shape[0] // 4, positions.shape[0] // 2, 3 * positions.shape[0] // 4, positions.shape[0] - 1]
    figure, axes = plt.subplots(len(indices), 3, figsize=(9, 3 * len(indices)))
    for row, frame in enumerate(indices):
        render_pose(axes[row, 0], positions[frame], f"official navigation frame {frame} front", "front")
        render_pose(axes[row, 1], positions[frame], f"official navigation frame {frame} side", "side")
        render_pose(axes[row, 2], positions[frame], f"official navigation frame {frame} top", "top")
    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or PROJECT_ROOT / "qa_runs" / f"official_navigation_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = generate_official_navigation_clip(args.seed)
    positions = parse_clip_bytes(payload, root_lock=False)
    source_metrics = validate_source(positions)
    metrics = compute_metrics(positions)
    render_keyframes(positions, output_dir / "official_navigation_keyframes.png")

    report = {
        "schema": 1,
        "timestamp_utc": timestamp,
        "source": "NVIDIA full_navigation_agent official random-controller path",
        "capability": "navigation_only_not_combat_action_motion",
        "seed": args.seed,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "source_metrics": source_metrics,
        "motion_metrics": metrics,
    }
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"OFFICIAL_NAVIGATION_QA_PASS output={output_dir}")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
