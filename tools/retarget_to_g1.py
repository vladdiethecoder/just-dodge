#!/usr/bin/env python3
"""Retarget a source FBX/BVH clip to G1Skeleton34 and export numpy features."""
import argparse
import json
import numpy as np


def load_retarget_map():
    with open("tools/data/g1_retarget_map.json") as f:
        return json.load(f)


def generate_synthetic_clip(frames: int = 60, joint_count: int = 34, seed: int = 0):
    """Deterministic test fixture: neutral standing pose with small sway."""
    rng = np.random.default_rng(seed)
    positions = np.zeros((frames, joint_count, 3), dtype=np.float32)
    # Pelvis height around 0.9 m.
    positions[:, 0, 1] = 0.9
    # Slight deterministic sway.
    t = np.arange(frames, dtype=np.float32) / frames
    positions[:, 0, 0] = np.sin(t * 2 * np.pi) * 0.05
    positions[:, 0, 2] = np.cos(t * 2 * np.pi) * 0.05
    # Add tiny noise to non-root joints so features are not all zeros.
    positions[:, 1:, :] = rng.normal(0.0, 0.02, (frames, joint_count - 1, 3)).astype(np.float32)
    rotations = np.tile(np.eye(3, dtype=np.float32), (frames, joint_count, 1, 1))
    return {"joint_positions": positions, "joint_rotations": rotations}


def retarget(source_path: str, source_format: str, out_path: str, synthetic: bool = False):
    """Retarget a source clip to G1Skeleton34.

    Real retargeting requires a source-specific bone map (source skeleton ->
    G1Skeleton34) plus a forward-kinematics / inverse-kinematics (FK/IK) solver
    to align joint positions, root trajectory, and end-effector contacts in a
    consistent world frame.

    Until mocap is acquired and that solver is implemented, use --synthetic to
    generate a deterministic test fixture for pipeline validation only.
    """
    if synthetic:
        clip = generate_synthetic_clip()
        np.save(out_path, clip)
        return

    # TODO(Data Phase 2): implement source-specific bone map + FK/IK solver once
    # mocap sources are available (see docs/plans/mocap-pipeline.md).
    raise NotImplementedError(
        f"Retargeting from {source_format} is not implemented. "
        "Use --synthetic to generate a test fixture, or implement the "
        "source-specific bone map and FK/IK solver (TODO: Data Phase 2)."
    )


def main():
    parser = argparse.ArgumentParser(description="Retarget mocap to G1Skeleton34")
    parser.add_argument("--source", help="Source clip path")
    parser.add_argument("--format", choices=["bvh", "fbx", "c3d"], help="Source format")
    parser.add_argument("--out", help="Output .npy path")
    parser.add_argument("--synthetic", action="store_true", help="Generate a deterministic test fixture instead of retargeting")
    args = parser.parse_args()
    if args.source is None and args.format is None and args.out is None:
        print("Retarget map loaded:", load_retarget_map()["g1_skeleton"]["joint_count"], "joints")
        return
    if not args.source or not args.format or not args.out:
        parser.error("--source, --format, and --out are required together")
    retarget(args.source, args.format, args.out, synthetic=args.synthetic)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
