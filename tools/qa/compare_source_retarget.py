#!/usr/bin/env python3
"""Render raw CMU BVH versus the retargeted G1 output to diagnose scale/pose issues.

This script regenerates the retargeted G1 clip using the current retarget_to_g1.py
implementation before rendering, so the comparison always reflects the latest code.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from retarget_to_g1 import _parse_bvh, _forward_kinematics, retarget

BVH = PROJECT_ROOT / "data" / "cmu" / "140_06.bvh"
RETARGETED = PROJECT_ROOT / "data" / "cmu" / "140_06_retargeted.npy"

# Always regenerate the retargeted clip with the current retargeter.
retarget(str(BVH), "bvh", str(RETARGETED), target_fps=30.0)

# Load source CMU positions (centimeters -> convert to meters)
with open(BVH, "r", encoding="utf-8") as f:
    text = f.read()
root, motion, frame_time = _parse_bvh(text)
frame = min(0, motion.shape[0] - 1)
pos, _ = _forward_kinematics(root, motion)
cmu_positions = {k: v[frame] / 100.0 for k, v in pos.items()}  # cm -> m

# Load retargeted G1 positions
ret = np.load(RETARGETED, allow_pickle=True).item()
print(f"retargeted keys: {ret.keys()}, positions shape: {ret['joint_positions'].shape}")
g1_positions_all = ret["joint_positions"]
if g1_positions_all.ndim == 3 and g1_positions_all.shape[1] == 34:
    g1_positions = g1_positions_all[0]
else:
    raise ValueError(f"unexpected retargeted positions shape {g1_positions_all.shape}")

# CMU parent structure for visualization
cmu_joints = []


def visit(j):
    cmu_joints.append(j)
    for c in j.children:
        visit(c)


visit(root)

fig, axes = plt.subplots(1, 2, figsize=(10, 5))

# Plot raw CMU
ax = axes[0]
for j in cmu_joints:
    if j.parent is not None:
        p0 = cmu_positions[j.parent.name]
        p1 = cmu_positions[j.name]
        ax.plot([p0[0], p1[0]], [p0[1], p1[1]], "k-", linewidth=1)
for j in cmu_joints:
    p = cmu_positions[j.name]
    ax.scatter([p[0]], [p[1]], s=8, c="red")
ax.set_aspect("equal")
ax.set_title("Raw CMU 140_06 frame 0 (meters)")
ax.set_xlabel("X")
ax.set_ylabel("Y")

# Plot retargeted G1
ax = axes[1]
parents = [
    -1, 0, 1, 2, 3, 4, 5, 6, 0, 8, 9, 10, 11, 12, 13, 0, 15, 16, 17, 18,
    19, 20, 21, 22, 23, 24, 17, 26, 27, 28, 29, 30, 31, 32,
]
for i, p in enumerate(parents):
    if p >= 0:
        ax.plot(
            [g1_positions[p, 0], g1_positions[i, 0]],
            [g1_positions[p, 1], g1_positions[i, 1]],
            "k-",
            linewidth=1,
        )
ax.scatter(g1_positions[:, 0], g1_positions[:, 1], s=8, c="red")
ax.set_aspect("equal")
ax.set_title("Retargeted G1 frame 0")
ax.set_xlabel("X")
ax.set_ylabel("Y")

plt.tight_layout()

ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
out_dir = PROJECT_ROOT / "qa_runs" / f"retarget_comparison_{ts}"
out_dir.mkdir(parents=True, exist_ok=True)
out = out_dir / "source_vs_retarget.png"
plt.savefig(out, dpi=150)
print(f"saved {out}")
