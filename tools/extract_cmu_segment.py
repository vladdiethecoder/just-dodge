#!/usr/bin/env python3
"""Extract a root-locked segment from a CMU feature file."""
import argparse
import os

import numpy as np


def extract_segment(features: np.ndarray, start: int, end: int) -> np.ndarray:
    assert features.ndim == 2 and features.shape[1] == 414, features.shape
    segment = features[start:end].copy()
    mean_root_x = segment[:, 0].mean()
    mean_root_z = segment[:, 2].mean()
    segment[:, 0] -= mean_root_x
    segment[:, 2] -= mean_root_z
    segment[:, 3] = 1.0
    segment[:, 4] = 0.0
    return segment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", required=True)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--out-dir", default="data/cmu_segments")
    args = parser.parse_args()

    features = np.load(args.features)
    segment = extract_segment(features, args.start, args.end)

    clip = os.path.splitext(os.path.basename(args.features))[0].replace("_features", "")
    out_name = f"{clip}_{args.start}_{args.end}_{args.action.lower()}_features.npy"
    out_path = os.path.join(args.out_dir, out_name)
    os.makedirs(args.out_dir, exist_ok=True)
    np.save(out_path, segment.astype(np.float32))
    print(f"[extract] {out_path} shape={segment.shape}")


if __name__ == "__main__":
    main()
