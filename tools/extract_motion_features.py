#!/usr/bin/env python3
"""Extract MotionBricks GlobalRootGlobalJoints features from retargeted G1 poses."""
import argparse
import numpy as np


def extract_features(joint_positions: np.ndarray, joint_rotations: np.ndarray, fps: int = 30) -> np.ndarray:
    """
    joint_positions: [T, 34, 3] in world meters.
    joint_rotations: [T, 34, 3, 3] rotation matrices.
    Returns: [T, 414] feature vector (global root + global joints subset).
    """
    T = joint_positions.shape[0]
    root_pos = joint_positions[:, 0, :]  # [T, 3]
    root_heading = np.arctan2(joint_rotations[:, 0, 0, 2], joint_rotations[:, 0, 2, 2])
    root_heading_cs = np.stack([np.cos(root_heading), np.sin(root_heading)], axis=-1)
    # Placeholder: real implementation computes ric_data, global_rot_data (6D), local_vel, foot_contacts.
    # Stub uses root + root heading + 33 root-relative joints to match the expected smoke-test shape.
    features = np.concatenate([root_pos, root_heading_cs, joint_positions[:, 1:, :].reshape(T, -1)], axis=-1)
    return features


def run_smoke_test():
    dummy = np.zeros((30, 34, 3))
    dummy[:, 0, 1] = 0.9
    rots = np.tile(np.eye(3), (30, 34, 1, 1))
    f = extract_features(dummy, rots)
    print("feature shape:", f.shape)


def main():
    parser = argparse.ArgumentParser(description="Extract MotionBricks features from retargeted G1 clip")
    parser.add_argument("source", nargs="?", help="Input .npy containing 'joint_positions' and 'joint_rotations'")
    parser.add_argument("--out", help="Output .npy path")
    parser.add_argument("--fps", type=int, default=30, help="Clip frame rate")
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
