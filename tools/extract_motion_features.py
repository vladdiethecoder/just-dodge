#!/usr/bin/env python3
"""Extract MotionBricks GlobalRootGlobalJoints features from retargeted G1 poses."""
import argparse

import numpy as np


def rot6d_from_matrix(rot_mats: np.ndarray) -> np.ndarray:
    """Convert [T, J, 3, 3] rotation matrices to [T, J, 6] continuous 6D rotations.

    Uses the first two columns orthonormalized with Gram-Schmidt.
    """
    T, J = rot_mats.shape[:2]
    out = np.zeros((T, J, 6), dtype=rot_mats.dtype)
    for j in range(J):
        v0 = rot_mats[:, j, :, 0]
        v1 = rot_mats[:, j, :, 1]
        norm0 = np.linalg.norm(v0, axis=1, keepdims=True) + 1e-8
        v0n = v0 / norm0
        v1p = v1 - v0n * np.sum(v0n * v1, axis=1, keepdims=True)
        norm1 = np.linalg.norm(v1p, axis=1, keepdims=True) + 1e-8
        v1n = v1p / norm1
        out[:, j, :3] = v0n
        out[:, j, 3:] = v1n
    return out


def extract_features(joint_positions: np.ndarray, joint_rotations: np.ndarray, fps: int = 30) -> np.ndarray:
    """
    joint_positions: [T, 34, 3] in world meters.
    joint_rotations: [T, 34, 3, 3] rotation matrices.
    Returns: [T, 414] feature vector (global root + global joints subset).
    """
    T = joint_positions.shape[0]
    root_pos = joint_positions[:, 0, :]  # [T, 3]
    root_heading = np.arctan2(joint_rotations[:, 0, 0, 2], joint_rotations[:, 0, 2, 2])
    root_heading_cs = np.stack([np.cos(root_heading), np.sin(root_heading)], axis=-1)  # [T, 2]

    # ric_data: root-relative positions for joints 1..33.
    ric_data = (joint_positions[:, 1:, :] - root_pos[:, None, :]).reshape(T, -1)  # [T, 99]

    # global_rot_data: 34 * 6D continuous rotations.
    rot6d = rot6d_from_matrix(joint_rotations).reshape(T, -1)  # [T, 204]

    # local_vel and foot_contacts are unused by the current pipeline; zero them.
    local_vel = np.zeros((T, 34 * 3), dtype=joint_positions.dtype)  # [T, 102]
    foot_contacts = np.zeros((T, 4), dtype=joint_positions.dtype)  # [T, 4]

    features = np.concatenate(
        [root_pos, root_heading_cs, ric_data, rot6d, local_vel, foot_contacts],
        axis=-1,
    )
    assert features.shape[-1] == 414, features.shape
    return features


def run_smoke_test():
    dummy = np.zeros((30, 34, 3))
    dummy[:, 0, 1] = 0.9
    rots = np.tile(np.eye(3), (30, 34, 1, 1))
    f = extract_features(dummy, rots)
    assert f.shape == (30, 414), f.shape
    print("feature shape:", f.shape)


def main():
    parser = argparse.ArgumentParser(description="Extract MotionBricks features from retargeted G1 clip")
    parser.add_argument("source", nargs="?", help="Input .npy containing 'joint_positions' and 'joint_rotations'")
    parser.add_argument("--out", help="Output .npy path")
    parser.add_argument("--fps", type=int, default=30, help="Clip frame rate (informational only)")
    args = parser.parse_args()

    if args.source is None and args.out is None:
        run_smoke_test()
        return
    if not args.source or not args.out:
        parser.error("source and --out are required together")

    data = np.load(args.source, allow_pickle=True).item()
    features = extract_features(data["joint_positions"], data["joint_rotations"], fps=args.fps)
    np.save(args.out, features)
    print("feature shape:", features.shape)


if __name__ == "__main__":
    main()
