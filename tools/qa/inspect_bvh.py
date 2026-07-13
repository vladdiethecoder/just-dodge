#!/usr/bin/env python3
"""Inspect BVH clips: parse header and print motion summary."""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retarget_to_g1 import _parse_bvh, _forward_kinematics


def inspect(path: str, sample_frames: int = 5):
    text = Path(path).read_text()
    root, motion, frame_time = _parse_bvh(text)
    fps = 1.0 / frame_time
    T = motion.shape[0]

    # Collect joint names
    joints = []
    def visit(j):
        joints.append(j)
        for c in j.children: visit(c)
    visit(root)

    # Forward kinematics
    positions, rotations = _forward_kinematics(root, motion)

    # Root height / displacement stats
    root_pos = positions[root.name]
    root_y = root_pos[:, 1]
    min_h, max_h, mean_h = root_y.min(), root_y.max(), root_y.mean()

    # Foot movement (lowest y among 'lfoot'/'rfoot' like names)
    foot_names = [n for n in positions if 'toe' in n.lower() or 'foot' in n.lower() or 'ankle' in n.lower()]
    foot_disp = 0.0
    for n in foot_names:
        p = positions[n]
        foot_disp += np.linalg.norm(p[1:] - p[:-1], axis=1).sum()

    # Hand height variance / range (for strike detection)
    hand_names = [n for n in positions if 'hand' in n.lower() or 'wrist' in n.lower() or 'finger' in n.lower()]
    hand_ranges = []
    hand_y_ranges = []
    for n in hand_names:
        p = positions[n]
        hand_ranges.append(np.linalg.norm(p.max(axis=0) - p.min(axis=0)))
        hand_y_ranges.append(p[:,1].max() - p[:,1].min())
    hand_range = max(hand_ranges) if hand_ranges else 0.0
    hand_y_range = max(hand_y_ranges) if hand_y_ranges else 0.0

    # Body bounding box
    all_pos = np.stack(list(positions.values()), axis=1)  # T, J, 3
    bbox = all_pos.max(axis=(0,1)) - all_pos.min(axis=(0,1))

    # Sample frames
    idx = np.linspace(0, T-1, min(sample_frames, T), dtype=int)

    print(f"FILE: {path}")
    print(f"  frames={T}  fps={fps:.2f}  duration={T*frame_time:.2f}s  joints={len(joints)}")
    print(f"  root_y  min={min_h:.3f} max={max_h:.3f} mean={mean_h:.3f}")
    print(f"  foot_displacement={foot_disp:.3f}  hand_range={hand_range:.3f}  hand_y_range={hand_y_range:.3f}")
    print(f"  bbox XYZ={bbox[0]:.3f},{bbox[1]:.3f},{bbox[2]:.3f}")
    print(f"  sample_frames={list(idx)}")
    for i in idx:
        rh = [f"{positions[n][i,1]:.3f}" for n in hand_names[:2]]
        print(f"    frame {i}: root=({root_pos[i,0]:.3f},{root_pos[i,1]:.3f},{root_pos[i,2]:.3f}) hands_y={rh}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    for f in args.files:
        try:
            inspect(f)
        except Exception as e:
            print(f"ERROR in {f}: {e}", file=sys.stderr)
