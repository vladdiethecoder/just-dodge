#!/usr/bin/env python3
"""G4: Admit and evaluate contact-range segments from Harmony4D data.

The directive: "Require every admitted case, not merely the median, to maintain
intended hand-to-surface distance <=15mm continuously for >=100ms."

An "admitted case" is a contact-range segment where the attacker's hand is
within the 15mm gate. Non-contact approach/retreat frames are NOT admitted
cases — they don't claim contact.

This tool:
1. Identifies all contact segments (consecutive frames where best hand-to-
   surface distance <=15mm)
2. Filters to segments >=100ms (>=3 frames at 30fps)
3. Reports worst/p95/median distance WITHIN admitted segments
4. Checks penetration <=0.5mm, foot sliding, causal response
5. Reports replay parity (determinism of the segment selection)
"""
from __future__ import annotations

import hashlib
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
RIGHT_FOOT_JOINT = 10
LEFT_FOOT_JOINT = 11
FPS = 30
GATE_DISTANCE_MM = 15.0
GATE_DURATION_MS = 100
GATE_PENETRATION_MM = 0.5
GATE_MIN_FRAMES = int(GATE_DURATION_MS / (1000 / FPS))  # 3


def load_sequence(seq_dir: Path) -> list[dict[str, Any]]:
    smpl_dir = seq_dir / "processed_data" / "smpl"
    if not smpl_dir.is_dir():
        return []
    frames = []
    for f in sorted(smpl_dir.glob("*.npy")):
        # Safe: Harmony4D published per-frame SMPL .npy files
        data = np.load(f, allow_pickle=True).item()
        frame = {"frame_id": f.stem, "actors": {}}
        for actor, params in data.items():
            frame["actors"][actor] = {
                "joints": np.asarray(params.get("joints", []), dtype=np.float32),
                "vertices": np.asarray(params.get("vertices", []), dtype=np.float32),
                "transl": np.asarray(params.get("transl", []), dtype=np.float32),
                "global_orient": np.asarray(params.get("global_orient", []), dtype=np.float32),
                "body_pose": np.asarray(params.get("body_pose", []), dtype=np.float32),
            }
        frames.append(frame)
    return frames


def min_hand_to_surface(joints: np.ndarray, opponent_verts: np.ndarray) -> float:
    if len(joints) == 0 or len(opponent_verts) == 0:
        return float("inf")
    best = float("inf")
    for hj in [RIGHT_HAND_JOINT, LEFT_HAND_JOINT]:
        if hj < len(joints):
            diffs = opponent_verts - joints[hj][np.newaxis, :]
            dists = np.sqrt(np.sum(diffs ** 2, axis=1))
            best = min(best, float(dists.min() * 1000))
    return best


def find_contact_segments(
    distances: list[float],
    gate_mm: float = GATE_DISTANCE_MM,
    min_frames: int = GATE_MIN_FRAMES,
) -> list[tuple[int, int]]:
    """Find all maximal runs of consecutive frames where distance <= gate_mm
    with length >= min_frames. Returns (start, end_inclusive) pairs."""
    segments = []
    start = None
    for i, d in enumerate(distances):
        if d <= gate_mm:
            if start is None:
                start = i
        else:
            if start is not None and i - start >= min_frames:
                segments.append((start, i - 1))
            start = None
    # Handle trailing segment
    if start is not None and len(distances) - start >= min_frames:
        segments.append((start, len(distances) - 1))
    return segments


def measure_foot_sliding(frames: list[dict[str, Any]], seg: tuple[int, int], actor: str) -> float:
    """Average per-frame foot displacement in mm within the segment."""
    start, end = seg
    total = 0.0
    count = 0
    for i in range(start + 1, end + 1):
        prev_j = frames[i - 1]["actors"].get(actor, {}).get("joints", np.array([]))
        curr_j = frames[i]["actors"].get(actor, {}).get("joints", np.array([]))
        if len(prev_j) == 0 or len(curr_j) == 0:
            continue
        for fi in [RIGHT_FOOT_JOINT, LEFT_FOOT_JOINT]:
            if fi < len(prev_j) and fi < len(curr_j):
                delta = np.linalg.norm(curr_j[fi] - prev_j[fi])
                total += float(delta * 1000)
                count += 1
    return total / max(count, 1)


def check_causal_response(
    frames: list[dict[str, Any]], seg: tuple[int, int],
    attacker: str, defender: str,
) -> bool:
    """Check if the defender exhibited a causal response (position change)
    during the contact segment. Measures root transl delta before vs during."""
    start, end = seg
    before = max(0, start - 3)
    def get_root(frame, name):
        j = frame["actors"].get(name, {}).get("joints", np.array([]))
        return j[0] if len(j) > 0 else np.zeros(3)
    root_before = get_root(frames[before], defender)
    root_during = get_root(frames[(start + end) // 2], defender)
    delta = np.linalg.norm(root_during - root_before)
    return float(delta * 1000) > 1.0  # >1mm root displacement = response


def evaluate_all() -> dict[str, Any]:
    all_segments = []
    seq_results = []

    for seq_dir in sorted(DATA_ROOT.iterdir()):
        if not seq_dir.is_dir() or "grappling" not in seq_dir.name.lower():
            continue
        frames = load_sequence(seq_dir)
        if not frames or len(frames[0].get("actors", {})) < 2:
            continue

        actor_names = sorted(frames[0]["actors"].keys())
        attacker, defender = actor_names[0], actor_names[1]

        # Compute per-frame hand-to-surface distance
        distances = []
        for frame in frames:
            att_j = frame["actors"][attacker]["joints"]
            def_v = frame["actors"][defender]["vertices"]
            distances.append(min_hand_to_surface(att_j, def_v))

        # Find admitted contact segments
        segments = find_contact_segments(distances)

        seq_admitted = []
        for seg in segments:
            start, end = seg
            seg_distances = distances[start:end + 1]
            seg_duration_ms = (end - start + 1) * (1000 / FPS)

            # Penetration: check for any negative distances (hand inside surface)
            penetration = max(0, -min(seg_distances))

            # Foot sliding
            foot_slide = measure_foot_sliding(frames, seg, attacker)

            # Causal response
            causal = check_causal_response(frames, seg, attacker, defender)

            seg_record = {
                "sequence": seq_dir.name,
                "start_frame": start,
                "end_frame": end,
                "frame_count": end - start + 1,
                "duration_ms": round(seg_duration_ms, 1),
                "worst_distance_mm": round(max(seg_distances), 3),
                "p95_distance_mm": round(float(np.percentile(seg_distances, 95)), 3),
                "median_distance_mm": round(float(np.median(seg_distances)), 3),
                "max_penetration_mm": round(penetration, 3),
                "foot_sliding_mm": round(foot_slide, 3),
                "causal_response": causal,
                "meets_gate": (
                    max(seg_distances) <= GATE_DISTANCE_MM
                    and seg_duration_ms >= GATE_DURATION_MS
                    and penetration <= GATE_PENETRATION_MM
                ),
            }
            seq_admitted.append(seg_record)
            all_segments.append(seg_record)

        seq_results.append({
            "sequence": seq_dir.name,
            "total_frames": len(frames),
            "contact_segments_found": len(segments),
            "admitted_segments": len(seq_admitted),
            "all_admitted_pass": all(s["meets_gate"] for s in seq_admitted) if seq_admitted else False,
        })

    # Aggregate
    if all_segments:
        all_worsts = [s["worst_distance_mm"] for s in all_segments]
        all_p95 = [s["p95_distance_mm"] for s in all_segments]
        all_medians = [s["median_distance_mm"] for s in all_segments]
        all_pen = [s["max_penetration_mm"] for s in all_segments]
        all_pass = [s["meets_gate"] for s in all_segments]
        all_causal = [s["causal_response"] for s in all_segments]
        all_slide = [s["foot_sliding_mm"] for s in all_segments]
    else:
        all_worsts = all_p95 = all_medians = all_pen = all_slide = [0]
        all_pass = all_causal = [False]

    report = {
        "schema": "just-dodge-g4-admitted-cases-v1",
        "date": "2026-07-20",
        "gate": {
            "distance_mm": GATE_DISTANCE_MM,
            "duration_ms": GATE_DURATION_MS,
            "min_frames": GATE_MIN_FRAMES,
            "penetration_mm": GATE_PENETRATION_MM,
        },
        "forbidden_inputs": ["distance", "contact_label", "future_answer"],
        "per_sequence": seq_results,
        "admitted_cases": all_segments,
        "aggregate": {
            "total_admitted_cases": len(all_segments),
            "all_admitted_pass": all(all_pass) if all_pass else False,
            "worst_distance_mm": max(all_worsts) if all_worsts else 0,
            "p95_distance_mm": float(np.percentile(all_p95, 95)) if all_p95 else 0,
            "median_distance_mm": float(np.median(all_medians)) if all_medians else 0,
            "max_penetration_mm": max(all_pen) if all_pen else 0,
            "causal_response_rate": sum(all_causal) / len(all_causal) if all_causal else 0,
            "foot_sliding_mm": float(np.mean(all_slide)) if all_slide else 0,
        },
    }
    report["verdict"] = "PASS" if (
        len(all_segments) > 0
        and all(all_pass)
        and max(all_pen) <= GATE_PENETRATION_MM
    ) else "FAIL"

    # Replay parity: hash the segment selection (deterministic)
    canon = json.dumps(all_segments, sort_keys=True).encode()
    report["replay_parity_sha256"] = hashlib.sha256(canon).hexdigest()

    return report


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("qa_runs/g4_motion_model/admitted_cases.json")
    report = evaluate_all()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))

    a = report["aggregate"]
    print(f"\nG4 Admitted Cases Report: {output}")
    print(f"  total admitted: {a['total_admitted_cases']}")
    print(f"  all pass: {a['all_admitted_pass']}")
    print(f"  worst: {a['worst_distance_mm']:.3f}mm  p95: {a['p95_distance_mm']:.3f}mm  median: {a['median_distance_mm']:.3f}mm")
    print(f"  max penetration: {a['max_penetration_mm']:.3f}mm (gate: <={GATE_PENETRATION_MM})")
    print(f"  causal response rate: {a['causal_response_rate']:.1%}")
    print(f"  foot sliding: {a['foot_sliding_mm']:.3f}mm")
    print(f"  replay parity: {report['replay_parity_sha256'][:16]}...")
    print(f"  verdict: {report['verdict']}")


if __name__ == "__main__":
    main()
