#!/usr/bin/env python3
"""Validate the Harmony4D raw-to-training manifest (G3 gate).

Checks that the manifest:
1. Has all required top-level fields (dataset, reconstruction_code, topology, etc.)
2. Every frame has: raw_sha256, actors with vertex_sha256, calibration, coordinate_transform
3. Every actor has SMPL pose parameters (not just vertices)
4. License evidence is present per frame
5. Dataset revision is pinned
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_TOP = {
    "schema", "gate", "dataset", "reconstruction_code", "topology",
    "units", "coordinate_transform", "sequences_found", "total_frames", "frames",
}
REQUIRED_DATASET = {"repo_id", "repo_type", "revision", "citation", "license", "url"}
REQUIRED_FRAME = {
    "frame_id", "sequence", "frame_index", "dataset_revision",
    "source_uri", "actors", "calibration", "topology", "units",
    "coordinate_transform", "raw_sha256", "license", "reconstruction_code",
}
REQUIRED_ACTOR = {
    "vertex_count", "vertex_sha256", "betas_sha256",
    "body_pose_sha256", "global_orient_sha256", "transl_sha256",
    "has_vertices", "has_pose_params",
}


def validate_manifest(path: Path) -> list[str]:
    errors: list[str] = []
    manifest = json.loads(path.read_text())

    # Top-level
    missing = REQUIRED_TOP - set(manifest.keys())
    if missing:
        errors.append(f"missing top-level fields: {missing}")

    # Dataset
    ds = manifest.get("dataset", {})
    missing_ds = REQUIRED_DATASET - set(ds.keys())
    if missing_ds:
        errors.append(f"missing dataset fields: {missing_ds}")

    # Revision must be pinned (40+ hex chars)
    rev = ds.get("revision", "")
    if len(rev) < 40:
        errors.append(f"dataset revision not pinned: {rev}")

    # Frames
    frames = manifest.get("frames", [])
    if not frames:
        errors.append("no frames in manifest")
        return errors

    for i, frame in enumerate(frames):
        missing_f = REQUIRED_FRAME - set(frame.keys())
        if missing_f:
            errors.append(f"frame {i} missing fields: {missing_f}")
            continue

        # Must have at least 2 actors (paired two-actor data)
        actors = frame.get("actors", {})
        if len(actors) < 2:
            errors.append(f"frame {i} ({frame['frame_id']}): only {len(actors)} actors (need >=2)")

        for actor_name, actor in actors.items():
            missing_a = REQUIRED_ACTOR - set(actor.keys())
            if missing_a:
                errors.append(f"frame {i} actor {actor_name} missing: {missing_a}")
            if not actor.get("has_pose_params"):
                errors.append(f"frame {i} actor {actor_name}: no SMPL pose parameters")
            if not actor.get("has_vertices"):
                errors.append(f"frame {i} actor {actor_name}: no vertices")

        # License must be present
        if not frame.get("license"):
            errors.append(f"frame {i}: no license")

    return errors


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to the manifest JSON")
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"FAIL: manifest not found: {args.manifest}")
        sys.exit(1)

    errors = validate_manifest(args.manifest)
    if errors:
        print(f"FAIL: {len(errors)} validation errors:")
        for e in errors[:20]:
            print(f"  {e}")
        sys.exit(1)

    manifest = json.loads(args.manifest.read_text())
    print(f"PASS: {manifest['total_frames']} frames, {len(manifest['sequences_found'])} sequences")
    print(f"  schema: {manifest['schema']}")
    print(f"  revision: {manifest['dataset']['revision'][:16]}...")
    print(f"  topology: {manifest['topology']}")


if __name__ == "__main__":
    main()
