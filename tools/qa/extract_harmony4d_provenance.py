#!/usr/bin/env python3
"""Extract per-frame paired SMPL provenance from Harmony4D raw data.

For each sequence in train/03_grappling2/:
- Loads the per-frame SMPL .npy files from processed_data/smpl/
- Records: dataset revision, source sequence, camera, frame, both actors,
  SMPL params (betas, body_pose, global_orient, transl),
  raw hash, generated vertex hash, topology, units, coordinate transforms,
  license evidence.
- Produces an immutable raw-to-training manifest for the G3 gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np


REPO_ID = "Jyun-Ting/Harmony4D"
REPO_TYPE = "dataset"
REPO_REVISION = "3fedb23fd9d1a92541d98ccbce025c695bd752e4"
DATASET_CITATION = "arXiv 2410.20294, NeurIPS 2024, CMU"
LICENSE = "CC BY 4.0 (Harmony4D dataset, https://huggingface.co/datasets/Jyun-Ting/Harmony4D)"
TOPOLOGY = "SMPL 24-joint, 6890 vertices"
UNITS = "meters"
COORDINATE_FRAME = "world (COLMAP-aligned, see colmap_from_aria_transforms.pkl per sequence)"
SMPL_VERTEX_COUNT = 6890
SMPL_JOINT_COUNT = 24


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_array(arr: np.ndarray) -> str:
    return hashlib.sha256(arr.tobytes()).hexdigest()


def extract_sequence_provenance(
    sequence_dir: Path,
    sequence_name: str,
) -> list[dict[str, Any]]:
    """Extract per-frame SMPL provenance for one sequence."""
    smpl_dir = sequence_dir / "processed_data" / "smpl"
    if not smpl_dir.is_dir():
        return []

    # Load COLMAP transforms for coordinate-frame provenance
    colmap_transforms_hash = None
    colmap_dir = sequence_dir / "colmap"
    if colmap_dir.is_dir():
        transforms_file = colmap_dir / "colmap_from_aria_transforms.pkl"
        if transforms_file.exists():
            colmap_transforms_hash = sha256_file(transforms_file)

    # Load camera intrinsics for calibration provenance
    cameras_file = colmap_dir / "cameras.txt" if colmap_dir.is_dir() else None
    calibration_hash = None
    camera_count = 0
    if cameras_file and cameras_file.exists():
        calibration_hash = sha256_file(cameras_file)
        with open(cameras_file) as f:
            camera_count = sum(1 for line in f if not line.startswith("#") and line.strip())

    frames = []
    smpl_files = sorted(smpl_dir.glob("*.npy"))
    for smpl_file in smpl_files:
        frame_id = smpl_file.stem
        raw_bytes = smpl_file.read_bytes()
        raw_hash = sha256_bytes(raw_bytes)

        # Safe: loading Harmony4D's own published per-frame SMPL .npy files
        # from the authoritative HuggingFace dataset (dict of SMPL params).
        smpl_data = np.load(smpl_file, allow_pickle=True).item()

        per_frame: dict[str, Any] = {
            "frame_id": f"{sequence_name}_{frame_id}",
            "sequence": sequence_name,
            "frame_index": int(frame_id),
            "dataset_revision": REPO_REVISION,
            "source_uri": f"huggingface.co/datasets/{REPO_ID}/resolve/{REPO_REVISION}/train/03_grappling2.zip",
            "sequence_path": str(sequence_dir.relative_to(sequence_dir.parents[3])),
            "actors": {},
            "calibration": {
                "cameras_file": str(cameras_file.relative_to(sequence_dir)) if cameras_file and cameras_file.exists() else None,
                "camera_count": camera_count,
                "colmap_transforms_hash": colmap_transforms_hash,
                "calibration_hash": calibration_hash,
            },
            "topology": TOPOLOGY,
            "units": UNITS,
            "coordinate_transform": COORDINATE_FRAME,
            "raw_sha256": raw_hash,
            "license": LICENSE,
            "reconstruction_code": {
                "repo": "jyuntins/harmony4d",
                "commit": "88065b1b0b89b92b824615e1ea930f317e5b1367",
                "script": "tools/ego_exo/2_vis_smpl_ego_exo.py",
                "method": "Harmony4D markerless multi-view SMPL fitting (HMR2.0 fine-tuned on Harmony4D)",
            },
        }

        for actor_name, actor_smpl in smpl_data.items():
            vertices = np.asarray(actor_smpl.get("vertices", []), dtype=np.float32)
            betas = np.asarray(actor_smpl.get("betas", []), dtype=np.float32)
            body_pose = np.asarray(actor_smpl.get("body_pose", []), dtype=np.float32)
            global_orient = np.asarray(actor_smpl.get("global_orient", []), dtype=np.float32)
            transl = np.asarray(actor_smpl.get("transl", []), dtype=np.float32)

            actor_record = {
                "vertex_count": int(vertices.shape[0]) if vertices.size > 0 else 0,
                "vertex_sha256": sha256_array(vertices) if vertices.size > 0 else None,
                "betas_sha256": sha256_array(betas) if betas.size > 0 else None,
                "body_pose_sha256": sha256_array(body_pose) if body_pose.size > 0 else None,
                "global_orient_sha256": sha256_array(global_orient) if global_orient.size > 0 else None,
                "transl_sha256": sha256_array(transl) if transl.size > 0 else None,
                "has_vertices": vertices.size > 0,
                "has_pose_params": body_pose.size > 0 and global_orient.size > 0,
            }
            per_frame["actors"][actor_name] = actor_record

        frames.append(per_frame)

    return frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True, help="Root of Harmony4D data (containing train/)")
    parser.add_argument("--output", type=Path, required=True, help="Output manifest JSON")
    parser.add_argument("--big-sequence", default="03_grappling2", help="Big sequence name (e.g. 03_grappling2)")
    args = parser.parse_args()

    train_dir = args.data_root / "train"
    all_frames: list[dict[str, Any]] = []
    sequences_found: list[str] = []

    # The zip contains sequences like 025_grappling2/, 028_grappling2/, etc.
    big_seq_dir = train_dir / args.big_sequence
    if big_seq_dir.is_dir():
        # Sequences are subdirectories
        for seq_dir in sorted(big_seq_dir.iterdir()):
            if seq_dir.is_dir() and "grappling" in seq_dir.name.lower():
                sequences_found.append(seq_dir.name)
                frames = extract_sequence_provenance(seq_dir, seq_dir.name)
                all_frames.extend(frames)
                print(f"  {seq_dir.name}: {len(frames)} frames")
    else:
        # Maybe the zip extracts directly to numbered sequences
        for seq_dir in sorted(train_dir.iterdir()):
            if seq_dir.is_dir() and "grappling" in seq_dir.name.lower():
                sequences_found.append(seq_dir.name)
                frames = extract_sequence_provenance(seq_dir, seq_dir.name)
                all_frames.extend(frames)
                print(f"  {seq_dir.name}: {len(frames)} frames")

    manifest: dict[str, Any] = {
        "schema": "just-dodge-harmony4d-raw-to-training-manifest-v1",
        "gate": "PVP005-GRAB07-TRUTH-AND-EVIDENCE-RESET-004/G3",
        "date": "2026-07-19",
        "dataset": {
            "repo_id": REPO_ID,
            "repo_type": REPO_TYPE,
            "revision": REPO_REVISION,
            "citation": DATASET_CITATION,
            "license": LICENSE,
            "url": f"https://huggingface.co/datasets/{REPO_ID}",
        },
        "reconstruction_code": {
            "repo": "jyuntins/harmony4d",
            "commit": "88065b1b0b89b92b824615e1ea930f317e5b1367",
            "method": "Harmony4D markerless multi-view SMPL fitting",
        },
        "topology": TOPOLOGY,
        "units": UNITS,
        "coordinate_transform": COORDINATE_FRAME,
        "sequences_found": sequences_found,
        "total_frames": len(all_frames),
        "frames": all_frames,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    args.output.write_bytes(manifest_bytes)
    manifest_hash = sha256_bytes(manifest_bytes)

    print(f"\nManifest: {args.output}")
    print(f"  sequences: {len(sequences_found)}")
    print(f"  total frames: {len(all_frames)}")
    print(f"  manifest sha256: {manifest_hash}")
    print(f"  schema: {manifest['schema']}")


if __name__ == "__main__":
    main()
