#!/usr/bin/env python3
"""G4: Per-case data qualification — measure the actual contact-range quality
of the Harmony4D paired grappling data itself.

This evaluates whether the DATA (not the model) contains per-frame paired
surfaces where the attacker's hand maintains <=15mm to the opponent surface
for >=100ms continuously. This is the gate the directive requires: every
admitted case must maintain the distance.

If the DATA itself doesn't meet this gate, no model trained on it can.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

DATA_ROOT = Path(os.environ.get(
    "HARMONY4D_DATA_ROOT",
    "/run/media/vdubrov/NVMe-Storage1/harmony4d_data/train/03_grappling2",
))

RIGHT_HAND_JOINT = 22
LEFT_HAND_JOINT = 23
FPS = 30
GATE_DISTANCE_MM = 15.0
GATE_DURATION_MS = 100
GATE_PENETRATION_MM = 0.5


def load_sequence(seq_dir: Path) -> list[dict[str, Any]]:
    smpl_dir = seq_dir / "processed_data" / "smpl"
    if not smpl_dir.is_dir():
        return []
    frames = []
    for f in sorted(smpl_dir.glob("*.npy")):
        # Safe: Harmony4D published per-frame SMPL .npy files
        data = np.load(f, allow_pickle=True).item()
        frame = {"frame_id": f.stem}
        for actor, params in data.items():
            frame[actor] = {
                "joints": np.asarray(params.get("joints", []), dtype=np.float32),
                "vertices": np.asarray(params.get("vertices", []), dtype=np.float32),
            }
        frames.append(frame)
    return frames


def min_distance_to_surface(joint_pos: np.ndarray, surface: np.ndarray) -> float:
    """Min L2 distance from a joint position to the opponent's vertex surface."""
    if len(surface) == 0:
        return float("inf")
    diffs = surface - joint_pos[np.newaxis, :]
    dists = np.sqrt(np.sum(diffs ** 2, axis=1))
    return float(dists.min() * 1000)  # m -> mm


def evaluate_sequence(frames: list[dict[str, Any]], seq_name: str) -> dict[str, Any]:
    """Evaluate all frames in a sequence for contact-range quality."""
    actor_keys = sorted(frames[0].keys() - {"frame_id"}) if frames else []
    if len(actor_keys) < 2:
        return {"sequence": seq_name, "frames": 0, "admitted": False}

    attacker_name = actor_keys[0]
    defender_name = actor_keys[1]

    distances = []
    for frame in frames:
        att = frame.get(attacker_name, {})
        deff = frame.get(defender_name, {})
        att_joints = att.get("joints", np.array([]))
        deff_verts = deff.get("vertices", np.array([]))

        if len(att_joints) == 0 or len(deff_verts) == 0:
            distances.append(float("inf"))
            continue

        rh = att_joints[RIGHT_HAND_JOINT] if RIGHT_HAND_JOINT < len(att_joints) else att_joints[-1]
        lh = att_joints[LEFT_HAND_JOINT] if LEFT_HAND_JOINT < len(att_joints) else att_joints[-1]

        rh_dist = min_distance_to_surface(rh, deff_verts)
        lh_dist = min_distance_to_surface(lh, deff_verts)
        distances.append(min(rh_dist, lh_dist))

    distances = np.array(distances)
    finite = distances[np.isfinite(distances)]

    if len(finite) == 0:
        return {"sequence": seq_name, "frames": len(frames), "admitted": False}

    # Per-case gate: find consecutive runs where distance <= 15mm
    gate_frames_needed = int(GATE_DURATION_MS / (1000 / FPS))
    consecutive = 0
    max_consecutive = 0
    for d in distances:
        if d <= GATE_DISTANCE_MM:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0

    # Penetration check
    penetrations = finite[finite < 0]  # negative distance = inside
    max_penetration = float(abs(penetrations.min())) if len(penetrations) > 0 else 0.0

    # All cases under 15mm
    all_under = bool(np.all(finite <= GATE_DISTANCE_MM))
    meets_duration = bool(max_consecutive >= gate_frames_needed)

    return {
        "sequence": seq_name,
        "frames": len(frames),
        "median_distance_mm": float(np.median(finite)),
        "p95_distance_mm": float(np.percentile(finite, 95)),
        "worst_distance_mm": float(finite.max()),
        "max_penetration_mm": max_penetration,
        "max_consecutive_contact_frames": max_consecutive,
        "gate_frames_needed": gate_frames_needed,
        "all_cases_under_15mm": all_under,
        "meets_100ms_duration": meets_duration,
        "admitted": all_under and meets_duration and max_penetration <= GATE_PENETRATION_MM,
    }


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("qa_runs/g4_motion_model/data_qualification.json")

    all_results = []
    for seq_dir in sorted(DATA_ROOT.iterdir()):
        if not seq_dir.is_dir() or "grappling" not in seq_dir.name.lower():
            continue
        print(f"  {seq_dir.name}...", end=" ", flush=True)
        frames = load_sequence(seq_dir)
        result = evaluate_sequence(frames, seq_dir.name)
        all_results.append(result)
        print(f"{result['frames']} frames, median={result.get('median_distance_mm',0):.1f}mm, "
              f"max_contact={result.get('max_consecutive_contact_frames',0)}f, "
              f"admitted={result['admitted']}")

    # Aggregate
    all_medians = [r["median_distance_mm"] for r in all_results if "median_distance_mm" in r]
    admitted_count = sum(1 for r in all_results if r["admitted"])

    report = {
        "schema": "just-dodge-g4-data-qualification-v1",
        "date": "2026-07-20",
        "gate_distance_mm": GATE_DISTANCE_MM,
        "gate_duration_ms": GATE_DURATION_MS,
        "sequences": all_results,
        "aggregate": {
            "total_sequences": len(all_results),
            "admitted_sequences": admitted_count,
            "median_of_medians_mm": float(np.median(all_medians)) if all_medians else 0,
            "any_admitted": admitted_count > 0,
        },
    }
    report["verdict"] = "PASS" if admitted_count > 0 else "FAIL"

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))

    print(f"\nData Qualification Report: {output}")
    print(f"  sequences: {len(all_results)}, admitted: {admitted_count}")
    print(f"  verdict: {report['verdict']}")


if __name__ == "__main__":
    main()
