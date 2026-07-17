#!/usr/bin/env python3
"""Render dynamic combat demo frames as skeleton contact sheets for visual QA.

Reads the demo summary and produces PNG contact sheets showing the skeleton
trajectory for each (move, variant) pair. Pure matplotlib, no GPU required.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT_ROOT = Path("/home/vdubrov/Projects/r6k-dynamic-combat-demo")
FRAMES = 64

# G1 34-joint parent chain (simplified for skeleton plotting)
BONES = [
    (0, 1), (1, 2), (2, 3), (3, 4),  # left leg
    (0, 5), (5, 6), (6, 7), (7, 8),  # right leg
    (0, 9), (9, 10), (10, 11),       # spine
    (11, 12), (12, 13), (13, 14), (14, 15),  # left arm
    (11, 16), (16, 17), (17, 18), (18, 19),  # right arm
]


def unpack_pos(arr: np.ndarray) -> np.ndarray:
    """Unpack [T, 413] feature array into [T, 34, 3] joint positions."""
    pos = np.empty((arr.shape[0], 34, 3), dtype=np.float32)
    pos[:, 0] = arr[:, :3]
    for j in range(1, 34):
        pos[:, j] = arr[:, :3] + arr[:, 5 + (j - 1) * 3 : 5 + j * 3]
    return pos


def plot_frame(ax, pos, title):
    """Plot one frame of the skeleton."""
    ax.clear()
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-0.1, 2.2)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=8)
    ax.axis("off")
    for a, b in BONES:
        ax.plot(
            [pos[a, 0], pos[b, 0]],
            [pos[a, 1], pos[b, 1]],
            "o-",
            markersize=2,
            linewidth=1.5,
        )
    # Mark hands and feet
    ax.plot(pos[15, 0], pos[15, 1], "ro", markersize=6, label="LHand")
    ax.plot(pos[19, 0], pos[19, 1], "bo", markersize=6, label="RHand")
    ax.plot(pos[3, 0], pos[3, 1], "gs", markersize=4)
    ax.plot(pos[7, 0], pos[7, 1], "gs", markersize=4)


def render_example(pos: np.ndarray, move_id: str, variant_id: str, out_path: Path) -> None:
    """Render a 4x4 contact sheet of the trajectory."""
    fig, axes = plt.subplots(4, 4, figsize=(12, 12))
    indices = np.linspace(0, len(pos) - 1, 16).astype(int)
    # Center the skeleton in the plot
    offset = pos[:, 0].copy()  # root position
    for idx, ax in zip(indices, axes.flat):
        centered = pos[idx].copy()
        centered[:, 0] -= offset[idx, 0]
        centered[:, 2] -= offset[idx, 2]
        plot_frame(ax, centered, f"{move_id} f{idx}")
    fig.suptitle(f"{move_id} / {variant_id}", fontsize=14)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", default=OUT_ROOT / "demo_summary.json")
    parser.add_argument("--poses", default=OUT_ROOT / "rendered_poses.npy")
    parser.add_argument("--out", default=OUT_ROOT / "frames")
    parser.add_argument("--max-examples", type=int, default=12)
    args = parser.parse_args()

    summary = json.loads(Path(args.summary).read_text())
    results = summary["results"][: args.max_examples]
    poses = np.load(args.poses)

    for i, r in enumerate(results):
        move_id = r["move_id"]
        variant_id = r["variant_id"]
        pos = poses[i]
        out_path = Path(args.out) / f"{move_id}_{variant_id}.png"
        render_example(pos, move_id, variant_id, out_path)
        print(f"rendered {out_path}")

    print(f"RENDER_COMPLETE={len(results)} frames to {args.out}")


if __name__ == "__main__":
    main()
