#!/usr/bin/env python3
"""Structurally screen ARDY G1 combat teacher candidates and draw contact sheets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


PARENTS = (-1, 0, 1, 2, 3, 4, 5, 6, 0, 8, 9, 10, 11, 12, 13, 0, 15,
           16, 17, 18, 19, 20, 21, 22, 23, 24, 17, 26, 27, 28, 29, 30, 31, 32)
REQUIRED = ("root_positions", "posed_joints", "global_rot_mats", "foot_contacts")


def inspect(path: Path) -> tuple[dict, np.ndarray]:
    archive = np.load(path)
    missing = [key for key in REQUIRED if key not in archive]
    if missing:
        raise RuntimeError(f"{path}: missing {missing}")
    positions = np.asarray(archive["posed_joints"], dtype=np.float32)
    rotations = np.asarray(archive["global_rot_mats"], dtype=np.float32)
    if positions.ndim != 3 or positions.shape[1:] != (34, 3):
        raise RuntimeError(f"{path}: posed_joints {positions.shape}")
    if rotations.shape != (len(positions), 34, 3, 3):
        raise RuntimeError(f"{path}: global_rot_mats {rotations.shape}")
    if not np.isfinite(positions).all() or not np.isfinite(rotations).all():
        raise RuntimeError(f"{path}: non-finite transforms")
    root = positions[:, 0]
    hands = positions[:, [25, 33]]
    metric = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "frames": len(positions),
        "max_abs_m": float(np.abs(positions).max()),
        "root_height_min_m": float(root[:, 1].min()),
        "root_height_max_m": float(root[:, 1].max()),
        "two_hand_height_range_m": float(np.ptp(hands[:, :, 1].mean(1))),
        "two_hand_forward_range_m": float(np.ptp(hands[:, :, 2].mean(1))),
        "two_hand_separation_min_m": float(
            np.linalg.norm(hands[:, 0] - hands[:, 1], axis=1).min()
        ),
        "two_hand_separation_max_m": float(
            np.linalg.norm(hands[:, 0] - hands[:, 1], axis=1).max()
        ),
    }
    return metric, positions


def draw(action: str, motions: list[tuple[Path, np.ndarray]], output: Path) -> None:
    columns = 6
    figure, axes = plt.subplots(
        len(motions), columns, figsize=(15, 3 * len(motions)), constrained_layout=True
    )
    axes = np.atleast_2d(axes)
    for row, (path, motion) in enumerate(motions):
        samples = np.rint(np.linspace(0, len(motion) - 1, columns)).astype(int)
        for column, frame in enumerate(samples):
            pose = motion[frame]
            axis = axes[row, column]
            for joint, parent in enumerate(PARENTS):
                if parent >= 0:
                    axis.plot(
                        [pose[parent, 0], pose[joint, 0]],
                        [pose[parent, 1], pose[joint, 1]],
                        color="black",
                        linewidth=1.5,
                    )
            axis.set_aspect("equal")
            axis.set_xlim(-1.0, 1.0)
            axis.set_ylim(0.1, 2.0)
            axis.axis("off")
            axis.set_title(f"{path.stem} f{frame}", fontsize=8)
    figure.suptitle(f"{action} candidates", fontsize=14)
    figure.savefig(output, dpi=130)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("qa_runs/m3_contact_truth_001/b14t_combat_dataset"),
    )
    args = parser.parse_args()
    all_metrics: dict[str, list[dict]] = {}
    for action in ("block", "grab"):
        candidates = sorted((args.root / action / action).glob(f"{action}_*.npz"))
        if not candidates:
            raise RuntimeError(f"no {action} candidates under {args.root}")
        rows: list[tuple[Path, np.ndarray]] = []
        metrics: list[dict] = []
        for candidate in candidates:
            metric, positions = inspect(candidate)
            metrics.append(metric)
            rows.append((candidate, positions))
        all_metrics[action] = metrics
        draw(action, rows, args.root / f"{action}_candidate_sheet.png")
    (args.root / "candidate_metrics.json").write_text(
        json.dumps(all_metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: len(value) for key, value in all_metrics.items()}, sort_keys=True))
    print("B14T_CANDIDATE_SCREEN_STRUCTURAL=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
