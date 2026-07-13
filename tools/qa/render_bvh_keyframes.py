#!/usr/bin/env python3
"""Render front/side keyframes of a raw CMU BVH clip."""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retarget_to_g1 import _parse_bvh, _forward_kinematics


CMU_BONES = [
    ("Hips", "LeftUpLeg"), ("LeftUpLeg", "LeftLeg"), ("LeftLeg", "LeftFoot"), ("LeftFoot", "LeftToeBase"),
    ("Hips", "RightUpLeg"), ("RightUpLeg", "RightLeg"), ("RightLeg", "RightFoot"), ("RightFoot", "RightToeBase"),
    ("Hips", "LowerBack"), ("LowerBack", "Spine"), ("Spine", "Spine1"),
    ("Spine1", "Neck"), ("Neck", "Neck1"), ("Neck1", "Head"),
    ("Spine1", "LeftShoulder"), ("LeftShoulder", "LeftArm"), ("LeftArm", "LeftForeArm"),
    ("LeftForeArm", "LeftHand"), ("LeftHand", "LeftFingerBase"),
    ("Spine1", "RightShoulder"), ("RightShoulder", "RightArm"), ("RightArm", "RightForeArm"),
    ("RightForeArm", "RightHand"), ("RightHand", "RightFingerBase"),
]


def render_pose(ax, positions: dict, title: str, view: str):
    ax.set_title(title, fontsize=8)
    ax.set_aspect("equal")

    for parent, child in CMU_BONES:
        if parent not in positions or child not in positions:
            continue
        p0 = positions[parent]
        p1 = positions[child]
        if view == "front":
            xs = [p0[0], p1[0]]
            ys = [p0[1], p1[1]]
        elif view == "side":
            xs = [p0[2], p1[2]]
            ys = [p0[1], p1[1]]
        else:  # top
            xs = [p0[0], p1[0]]
            ys = [p0[2], p1[2]]
        ax.plot(xs, ys, "k-", linewidth=1.2, alpha=0.7)

    all_pos = np.array(list(positions.values()))
    if view == "front":
        ax.scatter(all_pos[:, 0], all_pos[:, 1], s=10, c="red", zorder=5)
        ax.set_xlabel("X"); ax.set_ylabel("Y")
    elif view == "side":
        ax.scatter(all_pos[:, 2], all_pos[:, 1], s=10, c="red", zorder=5)
        ax.set_xlabel("Z"); ax.set_ylabel("Y")
    else:
        ax.scatter(all_pos[:, 0], all_pos[:, 2], s=10, c="red", zorder=5)
        ax.set_xlabel("X"); ax.set_ylabel("Z")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bvh", type=str)
    parser.add_argument("--out", "-o", type=str, required=True)
    parser.add_argument("--frames", type=int, nargs="+", default=None)
    args = parser.parse_args()

    text = Path(args.bvh).read_text()
    root, motion, frame_time = _parse_bvh(text)
    positions, _ = _forward_kinematics(root, motion)

    frames = args.frames if args.frames else [1, motion.shape[0] // 4, motion.shape[0] // 2, 3 * motion.shape[0] // 4, motion.shape[0] - 1]
    frames = [max(1, min(f, motion.shape[0] - 1)) for f in frames]

    fig, axes = plt.subplots(len(frames), 2, figsize=(8, 3 * len(frames)))
    if len(frames) == 1:
        axes = axes.reshape(1, 2)
    for row, idx in enumerate(frames):
        pos = {name: positions[name][idx] for name in positions}
        render_pose(axes[row, 0], pos, f"frame {idx} front", "front")
        render_pose(axes[row, 1], pos, f"frame {idx} side", "side")
    plt.tight_layout()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(args.out, dpi=150)
    plt.close()
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
