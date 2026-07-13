#!/usr/bin/env python3
"""Fail-closed local QA for an extracted BONES-SEED G1 motion CSV.

The tool verifies provenance against the existing authorized-dataset audit and
archive-member index, converts raw Unitree/MuJoCo channels through NVIDIA's
own MotionBricks converter, then writes only ignored local derived artifacts.
It does not copy source data into tracked assets and does not wire any result
into truth or the runtime.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch
from matplotlib import pyplot as plt
from scipy.spatial.transform import Rotation

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from motionbricks_service.generate import _pack_413_frames, init_official_service
from tools.qa.visual_verify_primitives import G1_PARENTS, parse_g1_frame, render_pose

ROOT_COLUMNS = (
    "root_translateX",
    "root_translateY",
    "root_translateZ",
    "root_rotateX",
    "root_rotateY",
    "root_rotateZ",
)
EXPECTED_COLUMNS = 36
UNIT_SCALE_METERS_PER_CENTIMETER = 0.01
ROOT_EULER_ORDER = "xyz"
MAX_JOINT_STEP_METERS = 0.2
MAX_SEGMENT_DRIFT_METERS = 1.0e-4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_csv_as_mujoco_qpos(path: Path) -> np.ndarray:
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        header = reader.fieldnames
        rows = list(reader)
    if header is None or len(header) != EXPECTED_COLUMNS:
        raise ValueError(f"expected {EXPECTED_COLUMNS} CSV columns, got {len(header or [])}")
    if tuple(header[1:7]) != ROOT_COLUMNS:
        raise ValueError(f"unexpected root channels: {header[1:7]}")
    if len(rows) < 5:
        raise ValueError(f"need at least five motion frames, got {len(rows)}")
    expected_frames = list(range(len(rows)))
    frames = [int(row["Frame"]) for row in rows]
    if frames != expected_frames:
        raise ValueError("Frame column must be contiguous and start at zero")

    root_xyz_cm = np.array(
        [[float(row[name]) for name in ROOT_COLUMNS[:3]] for row in rows], dtype=np.float32
    )
    root_euler_deg = np.array(
        [[float(row[name]) for name in ROOT_COLUMNS[3:]] for row in rows], dtype=np.float32
    )
    joint_degrees = np.array(
        [[float(row[name]) for name in header[7:]] for row in rows], dtype=np.float32
    )
    if joint_degrees.shape[1] != 29:
        raise ValueError(f"expected 29 Unitree hinge channels, got {joint_degrees.shape[1]}")

    qpos = np.empty((len(rows), EXPECTED_COLUMNS), dtype=np.float32)
    qpos[:, :3] = root_xyz_cm * UNIT_SCALE_METERS_PER_CENTIMETER
    qpos[:, 3:7] = Rotation.from_euler(
        ROOT_EULER_ORDER, root_euler_deg, degrees=True
    ).as_quat(scalar_first=True).astype(np.float32)
    qpos[:, 7:] = np.deg2rad(joint_degrees).astype(np.float32)
    if not np.isfinite(qpos).all():
        raise ValueError("non-finite converted MuJoCo qpos")
    return qpos


def provenance_row(dataset_root: Path, motion_id: str) -> tuple[dict, dict, dict]:
    audit_path = dataset_root / "just_dodge_combat_audit.json"
    index_path = dataset_root / "just_dodge_g1_member_index.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    row = next((item for item in audit["selected"] if item["motion_id"] == motion_id), None)
    if row is None:
        raise ValueError(f"motion is not admitted by the provenance audit: {motion_id}")
    expected_members = row.get("g1_archive_members", [])
    indexed_members = index.get("members_by_motion_id", {}).get(motion_id, [])
    if not expected_members or expected_members != indexed_members:
        raise ValueError("audit/index exact G1 archive-member linkage is missing or inconsistent")
    return audit, index, row


def segment_drift(positions: np.ndarray) -> float:
    lengths = []
    for child, parent in enumerate(G1_PARENTS):
        if parent >= 0:
            lengths.append(np.linalg.norm(positions[:, child] - positions[:, parent], axis=1))
    values = np.stack(lengths, axis=1)
    return float(np.max(np.abs(values - values[0])))


def render_keyframes(frames: np.ndarray, output: Path, motion_id: str) -> None:
    indices = np.linspace(0, len(frames) - 1, 5, dtype=int)
    figure, axes = plt.subplots(2, len(indices), figsize=(3 * len(indices), 6))
    for column, index in enumerate(indices):
        positions = parse_g1_frame(frames[index])
        render_pose(axes[0, column], positions, f"frame {index}", "front")
        render_pose(axes[1, column], positions, f"frame {index}", "side")
    figure.suptitle(f"BONES-SEED {motion_id} — direct G1 via official converter")
    figure.tight_layout()
    figure.savefig(output, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--motion-id", required=True)
    parser.add_argument(
        "--derived-csv",
        type=Path,
        help="Defaults to <dataset-root>/derived/<motion-id>.csv; extraction is deliberately out of scope.",
    )
    args = parser.parse_args()

    dataset_root = args.dataset_root.resolve()
    derived_csv = (
        args.derived_csv.resolve()
        if args.derived_csv
        else dataset_root / "derived" / f"{args.motion_id}.csv"
    )
    if not derived_csv.is_file():
        parser.error(f"missing extracted local source CSV: {derived_csv}")
    audit, index, row = provenance_row(dataset_root, args.motion_id)
    qpos = load_csv_as_mujoco_qpos(derived_csv)

    service = init_official_service()
    converter = service["agent"]._converter
    with torch.no_grad():
        positions, rotations = converter.convert_mujoco_qpos_to_motion_transforms(
            torch.from_numpy(qpos)[None]
        )
    frames = _pack_413_frames(
        positions[0, :, 0, :].cpu().numpy(),
        positions[0].cpu().numpy(),
        rotations[0].cpu().numpy(),
    )
    global_positions = np.stack([parse_g1_frame(frame) for frame in frames])
    if not np.isfinite(frames).all() or not np.isfinite(global_positions).all():
        raise ValueError("official converted G1 output contains non-finite values")

    steps = np.linalg.norm(np.diff(global_positions, axis=0), axis=2)
    root_steps = np.linalg.norm(np.diff(global_positions[:, 0], axis=0), axis=1)
    max_step = float(np.max(steps))
    max_drift = segment_drift(global_positions)
    if max_step > MAX_JOINT_STEP_METERS:
        raise ValueError(f"G1 discontinuity {max_step:.6f}m/frame exceeds {MAX_JOINT_STEP_METERS}m")
    if max_drift > MAX_SEGMENT_DRIFT_METERS:
        raise ValueError(
            f"G1 segment drift {max_drift:.6g}m exceeds {MAX_SEGMENT_DRIFT_METERS}m"
        )

    out_dir = dataset_root / "derived"
    out_dir.mkdir(parents=True, exist_ok=True)
    frame_path = out_dir / f"{args.motion_id}.413.npy"
    raw_frame_path = out_dir / f"{args.motion_id}.413.f32"
    visual_path = out_dir / f"{args.motion_id}.keyframes.png"
    receipt_path = out_dir / f"{args.motion_id}.validation.json"
    np.save(frame_path, frames, allow_pickle=False)
    raw_frame_path.write_bytes(frames.astype("<f4", copy=False).tobytes())
    render_keyframes(frames, visual_path, args.motion_id)
    receipt = {
        "schema_version": 1,
        "dataset": "BONES-SEED",
        "motion_id": args.motion_id,
        "audit_sha256": sha256_file(dataset_root / "just_dodge_combat_audit.json"),
        "index_sha256": sha256_file(dataset_root / "just_dodge_g1_member_index.json"),
        "license_sha256": audit["license_file_sha256"],
        "archive_sha256": index["g1_archive_sha256"],
        "archive_member": row["g1_archive_members"][0],
        "source_csv_sha256": sha256_file(derived_csv),
        "converter": "motionbricks.helper.mujoco_helper.mujoco_qpos_converter",
        "root_units": "centimeters_to_meters",
        "root_euler_order": ROOT_EULER_ORDER,
        "frames": int(len(frames)),
        "root_path_m": float(np.sum(root_steps)),
        "max_root_step_m": float(np.max(root_steps)),
        "max_joint_step_m": max_step,
        "max_segment_drift_m": max_drift,
        "derived_frame_path": str(frame_path.resolve()),
        "derived_raw_frame_path": str(raw_frame_path.resolve()),
        "derived_raw_frame_sha256": sha256_file(raw_frame_path),
        "visual_path": str(visual_path.resolve()),
        "presentation_only": True,
        "runtime_or_truth_wiring": False,
        "raw_data_redistributed": False,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
