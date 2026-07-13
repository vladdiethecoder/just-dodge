#!/usr/bin/env python3
"""Extract canonicalized MotionBricks features from retargeted G1 poses."""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_motion_features import extract_features


def canonicalize(positions: np.ndarray, rotations: np.ndarray):
    """Center root XZ at origin and zero first-frame heading."""
    T = positions.shape[0]
    root_pos = positions[:, 0, :].copy()
    root_rot = rotations[:, 0, :, :]

    # Compute heading from first frame
    # Heading is Y rotation; in rot matrix, heading angle atan2(R[0,2], R[2,2])
    first_heading = np.arctan2(root_rot[0, 0, 2], root_rot[0, 2, 2])
    cos_h, sin_h = np.cos(-first_heading), np.sin(-first_heading)
    R_y = np.array([[cos_h, 0, sin_h], [0, 1, 0], [-sin_h, 0, cos_h]], dtype=np.float32)

    # Center root XZ (keep Y)
    offset = root_pos[0].copy()
    offset[1] = 0.0

    new_positions = positions.copy()
    new_rotations = rotations.copy()
    for t in range(T):
        # Rotate and translate root position
        p = positions[t] - offset[None, :]
        new_positions[t] = (R_y @ p[..., None]).squeeze(-1)
        # Rotate all joint rotations
        new_rotations[t] = R_y @ rotations[t]

    return new_positions, new_rotations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="Input .npy containing 'joint_positions' and 'joint_rotations'")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    data = np.load(args.source, allow_pickle=True).item()
    pos, rot = canonicalize(data["joint_positions"], data["joint_rotations"])
    features = extract_features(pos, rot, fps=30)
    np.save(args.out, features)
    print(f"Wrote {args.out}: {features.shape} min={features.min():.3f} max={features.max():.3f}")


if __name__ == "__main__":
    main()
