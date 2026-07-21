#!/usr/bin/env python3
"""Convert Kyokushin Karate C3D files to G1 34-joint world positions.

Kyokushin dataset: 1633 C3D files from 37 athletes, CC0 public domain.
Contains: punches, kicks, blocks, kumite (sparring), kata (forms).
C3D format: 3D marker positions from Vicon optical mocap.

Output: posed_joints [T, 34, 3] + root_positions [T, 3] at 60fps.
"""
from __future__ import annotations
import json, hashlib, sys, glob
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
C3D_DIR = Path("/run/media/vdubrov/Bulk-SSD/combat_mocap_sources/kyokushin_karate/extracted")
OUT_DIR = ROOT / "qa_runs/grab07_combat_corpus/kyokushin_g1"

# Vicon marker names -> G1 joint indices (approximate mapping)
# Kyokushin uses standard Vicon Plug-in Gait marker set
MARKER_TO_G1 = {
    # Pelvis/root
    "LASI": 0, "RASI": 0, "SACR": 0, "PSIS": 0,
    # Spine
    "T10": 1, "CLAV": 2, "STRN": 2, "C7": 2,
    # Head
    "HEAD": 4, "LFHD": 4, "RFHD": 4,
    # Left arm
    "LSHO": 5, "LBAM": 5, "LUPA": 6, "LELB": 8, "LFRM": 8,
    "LWRA": 9, "LWRB": 9, "LFIN": 25, "LWRE": 25,
    # Right arm
    "RSHO": 10, "RBAE": 10, "RUPA": 11, "RELB": 13, "RFRM": 13,
    "RWRA": 14, "RWRB": 14, "RFIN": 33, "RWRE": 33,
    # Left leg
    "LTHI": 15, "LKNE": 17, "LANK": 18, "LHEE": 19, "LTOE": 19,
    # Right leg
    "RTHI": 20, "RKNE": 22, "RANK": 23, "RHEE": 24, "RTOE": 24,
}

NUM_G1 = 34


def convert_c3d(c3d_path):
    """Convert one C3D file to G1 joint positions."""
    import ezc3d
    c = ezc3d.c3d(str(c3d_path))
    points = c["data"]["points"]  # [4, N_markers, T] (x,y,z,residual)
    marker_names = c["parameters"]["POINT"]["LABELS"]["value"]
    fps = c["header"]["points"]["frame_rate"]
    T = points.shape[2]

    if T < 10:
        return None, None, fps

    # Build marker name -> index (strip subject prefix like "B0367:")
    name_to_idx = {}
    for i, name in enumerate(marker_names):
        bare = name.split(":")[-1].upper()  # "B0367:LFHD" -> "LFHD"
        name_to_idx[bare] = i

    # Convert: points is [4, N, T], take xyz = first 3
    # Replace NaN (occluded markers) with 0 before processing
    raw_markers = np.nan_to_num(points[:3, :, :], nan=0.0).T  # [T, N, 3]

    # Map to G1 joints (average multiple markers per joint)
    g1_pos = np.zeros((T, NUM_G1, 3))
    counts = np.zeros(NUM_G1)

    for marker_name, g1_idx in MARKER_TO_G1.items():
        if marker_name in name_to_idx:
            idx = name_to_idx[marker_name]
            # Check residual (4th channel) for validity
            residual = points[3, idx, :]
            valid = residual > 0  # C3D residual: negative = occluded
            valid_mask = valid if len(valid.shape) == 1 else valid.flatten()
            if np.any(valid_mask):
                g1_pos[:, g1_idx] += raw_markers[:, idx]
                counts[g1_idx] += 1

    # Average markers
    for i in range(NUM_G1):
        if counts[i] > 0:
            g1_pos[:, i] /= counts[i]

    # Fill gaps from nearest valid joint
    for i in range(NUM_G1):
        if counts[i] == 0:
            for j in range(i - 1, -1, -1):
                if counts[j] > 0:
                    g1_pos[:, i] = g1_pos[:, j]
                    break
            else:
                g1_pos[:, i] = g1_pos[:, 0]

    # Convert mm to meters if needed (C3D typically uses mm)
    max_val = np.abs(g1_pos).max()
    if max_val > 100:  # likely mm
        g1_pos /= 1000.0

    # Vicon C3D uses Z-up; swap to Y-up for our convention
    # X stays, old_Z -> new_Y (up), old_Y -> new_Z (forward)
    g1_pos = g1_pos[:, :, [0, 2, 1]]

    root = g1_pos[:, 0, :].copy()

    # Resample to 60fps
    if abs(fps - 60) > 1 and fps > 0:
        T_old = g1_pos.shape[0]
        T_new = int(T_old * 60 / fps)
        idx = np.linspace(0, T_old - 1, T_new).astype(int)
        g1_pos = g1_pos[idx]
        root = root[idx]

    return g1_pos, root, 60


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    c3d_files = sorted(C3D_DIR.rglob("*.c3d")) if C3D_DIR.exists() else []
    if not c3d_files:
        print("BLOCKED: no C3D files found. Extraction may still be running.")
        return 2

    print(f"Found {len(c3d_files)} C3D files")
    clips = []
    errors = 0

    for i, c3d_path in enumerate(c3d_files):
        try:
            g1_pos, root, fps = convert_c3d(c3d_path)
            if g1_pos is None:
                continue
            T = g1_pos.shape[0]
            # Limit to 120 frames max
            if T > 120:
                g1_pos = g1_pos[:120]
                root = root[:120]

            # Normalize: center root XZ
            g1_pos[:, :, 0] -= g1_pos[0, 0, 0]
            g1_pos[:, :, 2] -= g1_pos[0, 0, 2]

            # Derive clip ID from path
            rel = c3d_path.relative_to(C3D_DIR)
            clip_id = str(rel).replace("/", "_").replace(".c3d", "")
            # Shorten: just athlete + session + exercise
            parts = clip_id.split("_")
            if len(parts) >= 3:
                clip_id = "_".join(parts[-4:])  # last 4 parts
            else:
                clip_id = f"kyokushin_{i:04d}"

            out_path = OUT_DIR / f"{clip_id}.npz"
            np.savez_compressed(out_path,
                                posed_joints=g1_pos.astype(np.float32),
                                root_positions=root.astype(np.float32))
            sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
            clips.append({"clip_id": clip_id, "path": str(out_path),
                          "sha256": sha, "frames": int(g1_pos.shape[0])})
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"ERROR {c3d_path.name}: {e}", file=sys.stderr)

    manifest = {
        "schema": "just-dodge-kyokushin-g1-corpus-v1",
        "source": "Kyokushin Karate Multimodal Dataset (CC0)",
        "url": "https://doi.org/10.6084/m9.figshare.12315629.v1",
        "license": "CC0 (public domain)",
        "runtime_allowed": False,
        "training_allowed": True,
        "format": "C3D Vicon markers -> G1 34-joint world positions",
        "fps": 60,
        "total_clips": len(clips),
        "errors": errors,
        "clips": clips,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(f"KYOKUSHIN_G1_CONVERTED clips={len(clips)} errors={errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
