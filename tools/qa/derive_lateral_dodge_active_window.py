#!/usr/bin/env python3
"""Derive a presentation-only active source interval for a validated lateral Dodge.

The detector operates only on the ignored [N,413] G1 source stream. It emits a
reproducible JSON report, an active-window raw contact sheet, and the selected
window as a separate .413 stream. It does not modify runtime or combat truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.qa.screen_dodge_candidates import compute_metrics, render_contact_sheet
from tools.qa.visual_verify_primitives import G1_NAMES, parse_g1_frame

FRAME_FLOATS = 413
POSE_THRESHOLD_M = 0.040
ONSET_SUSTAIN_FRAMES = 10
RECOVERY_STABLE_FRAMES = 60
PRE_ROLL_FRAMES = 2
FOOT_HEIGHT_M = 0.025
FOOT_SPEED_M_PER_FRAME = 0.003
FOOT_NAMES = (
    "left_toe_end",
    "left_heel",
    "right_toe_end",
    "right_heel",
)


def true_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Return zero-based half-open runs of truth values."""
    edges = np.flatnonzero(np.diff(np.r_[False, mask, False].astype(np.int8)))
    return [(int(start), int(end)) for start, end in zip(edges[::2], edges[1::2])]


def first_sustained(mask: np.ndarray, minimum: int, start: int = 0) -> int:
    """Find first index at or after start with minimum contiguous true values."""
    for index in range(start, len(mask) - minimum + 1):
        if bool(mask[index : index + minimum].all()):
            return index
    raise ValueError(f"no sustained run of {minimum} frames from {start}")


def decode_positions(frames: np.ndarray) -> np.ndarray:
    return np.stack([parse_g1_frame(frame) for frame in frames])


def derive_active_window(frames: np.ndarray) -> tuple[dict, np.ndarray]:
    positions = decode_positions(frames)
    root = positions[:, 0]
    relative = positions[:, 1:] - root[:, None, :]
    reference = np.median(relative[:10], axis=0)
    pose_delta = np.sqrt(np.mean(np.sum((relative - reference) ** 2, axis=2), axis=1))

    onset_mask = pose_delta >= POSE_THRESHOLD_M
    onset = first_sustained(onset_mask, ONSET_SUSTAIN_FRAMES)
    peak = int(np.argmax(pose_delta))
    recovery_start = first_sustained(~onset_mask, RECOVERY_STABLE_FRAMES, peak + 1)
    active_start = max(0, onset - PRE_ROLL_FRAMES)
    # Include the first stable recovered source frame as the visible terminal pose.
    active_end_exclusive = recovery_start + 1

    if not (active_start < peak < active_end_exclusive <= len(frames)):
        raise ValueError(
            f"invalid active window [{active_start},{active_end_exclusive}) for peak {peak}"
        )

    velocities = np.linalg.norm(np.diff(positions, axis=0), axis=2)
    contacts: dict[str, list[list[int]]] = {}
    for name in FOOT_NAMES:
        joint = G1_NAMES.index(name)
        height = positions[:, joint, 1]
        speed = np.r_[0.0, velocities[:, joint]]
        baseline = float(np.percentile(height[:25], 20))
        airborne = (height > baseline + FOOT_HEIGHT_M) & (speed > FOOT_SPEED_M_PER_FRAME)
        contacts[name] = [
            [start, end]
            for start, end in true_runs(airborne)
            if end > active_start and start < active_end_exclusive
        ]

    mapped_ticks = np.linspace(
        active_start, active_end_exclusive - 1, 5, dtype=np.int64
    ).tolist()
    report = {
        "schema_version": 1,
        "source_frame_count": int(len(frames)),
        "thresholds": {
            "root_relative_pose_delta_m": POSE_THRESHOLD_M,
            "onset_sustain_frames": ONSET_SUSTAIN_FRAMES,
            "recovery_stable_frames": RECOVERY_STABLE_FRAMES,
            "pre_roll_frames": PRE_ROLL_FRAMES,
            "foot_height_above_baseline_m": FOOT_HEIGHT_M,
            "foot_speed_m_per_frame": FOOT_SPEED_M_PER_FRAME,
        },
        "pose_evidence": {
            "onset_frame": onset,
            "peak_frame": peak,
            "peak_pose_delta_m": float(pose_delta[peak]),
            "recovery_start_frame": recovery_start,
            "active_start_frame": active_start,
            "active_end_exclusive": active_end_exclusive,
            "active_frame_count": active_end_exclusive - active_start,
            "sample_source_frames": mapped_ticks,
        },
        "foot_airborne_runs_intersecting_active_window": contacts,
    }
    return report, positions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--motion-id", required=True)
    args = parser.parse_args()

    raw = args.source.read_bytes()
    frame_bytes = FRAME_FLOATS * 4
    if not raw or len(raw) % frame_bytes:
        raise ValueError(
            f"source must be a non-empty little-endian [N,{FRAME_FLOATS}] f32 stream"
        )
    frames = np.frombuffer(raw, dtype="<f4").reshape(-1, FRAME_FLOATS).copy()
    if not np.isfinite(frames).all():
        raise ValueError("source contains non-finite values")

    report, _ = derive_active_window(frames)
    report["motion_id"] = args.motion_id
    report["source_path"] = str(args.source)
    report["source_sha256"] = hashlib.sha256(raw).hexdigest()

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    start = report["pose_evidence"]["active_start_frame"]
    end = report["pose_evidence"]["active_end_exclusive"]
    active = frames[start:end]
    active_path = output / f"{args.motion_id}.active_{start}_{end}.413.f32"
    active_path.write_bytes(active.astype("<f4", copy=False).tobytes())
    report["active_window_path"] = str(active_path)
    report["active_window_sha256"] = hashlib.sha256(active_path.read_bytes()).hexdigest()

    # C0 calibration must retain the true neutral source reference at frame 0.
    # Prefix it once, then append the selected active interval so the existing
    # C0 probe samples reference + preparation/peak/recovery deterministically.
    c0_probe = np.concatenate((frames[:1], active), axis=0)
    c0_probe_path = output / f"{args.motion_id}.c0_probe_ref0_active_{start}_{end}.413.f32"
    c0_probe_path.write_bytes(c0_probe.astype("<f4", copy=False).tobytes())
    report["c0_probe_input_path"] = str(c0_probe_path)
    report["c0_probe_input_sha256"] = hashlib.sha256(c0_probe_path.read_bytes()).hexdigest()
    probe_sample_indices = [
        0,
        len(c0_probe) // 4,
        len(c0_probe) // 2,
        len(c0_probe) * 3 // 4,
        len(c0_probe) - 1,
    ]
    probe_sample_source_frames = [
        0 if index == 0 else start + index - 1
        for index in probe_sample_indices
    ]
    report["c0_probe_source_frame_mapping"] = {
        "probe_frame_0": 0,
        "probe_frame_i_for_i_ge_1": "active_start_frame + i - 1",
        "probe_frame_count": int(len(c0_probe)),
        "probe_sample_indices": probe_sample_indices,
        "probe_sample_source_frames": probe_sample_source_frames,
    }

    metrics = compute_metrics(active)
    sheet_path = output / f"{args.motion_id}.active_{start}_{end}_contact_sheet.png"
    render_contact_sheet(active, metrics, f"{args.motion_id} active [{start},{end})", sheet_path)
    report["active_window_contact_sheet"] = str(sheet_path)
    report["active_window_metrics"] = metrics

    report_path = output / f"{args.motion_id}.active_window.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
