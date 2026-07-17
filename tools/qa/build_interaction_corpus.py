#!/usr/bin/env python3
"""Interaction-conditioned combat corpus generator for Just Dodge.

Generates diverse (intent, opponent-geometry, physical-state) training examples
for the MotionBricks interaction extension. Each example is a constraint packet
plus a paired interaction-conditioning tensor, not a clip.

The production model learns from these examples to synthesize novel,
context-appropriate motion at runtime. No example is ever a runtime asset.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path("/run/media/vdubrov/NVMe-Storage1/Just Dodge")
BATCH_SPEC = REPO / "assets/data/r6k_move_batch.json"
SCHEMA = "interaction-training-example.v1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def build_interaction_tensor(move: dict, variant: dict) -> dict:
    """Build one interaction-conditioning example from a move spec + variation."""
    intent = move["action"]
    opp = variant["opponent"]
    attack_origin = opp["origin"]
    attack_target = opp["target"]
    attack_direction = [
        attack_target[i] - attack_origin[i] for i in range(3)
    ]
    length = max(1e-8, float(np.linalg.norm(attack_direction)))
    attack_direction = [d / length for d in attack_direction]
    reach = float(opp.get("reach_m", length))
    velocity = float(opp.get("velocity_m_s", 3.0))
    contact_tick = int(opp.get("contact_tick", 24))

    legal = ["Strike", "Block", "Dodge", "Parry", "Grab"]
    if intent not in legal:
        legal.append(intent)

    return {
        "schema": SCHEMA,
        "move_id": move["id"],
        "variant_id": variant["id"],
        "actor_intent": intent,
        "opponent_intent": opp.get("intent", "Strike"),
        "legal_response_bits": sorted(legal),
        "emitter_role": opp.get("emitter_role", "WeaponEdge"),
        "target_role": opp.get("target_role", "Body"),
        "attack_origin_mm": [int(round(v * 1000)) for v in attack_origin],
        "attack_target_mm": [int(round(v * 1000)) for v in attack_target],
        "attack_direction_q15": [int(round(v * 32767)) for v in attack_direction],
        "attack_velocity_mm_s": [0, 0, int(round(velocity * 1000))],
        "attack_angular_velocity_mrad_s": [0, 0, 0],
        "reach_mm": int(round(reach * 1000)),
        "contact_tick_offset": contact_tick,
        "contact_window_start_tick_offset": contact_tick - 4,
        "contact_window_end_tick_offset": contact_tick + 4,
        "expected_impulse_milli_ns": int(opp.get("impulse_milli_ns", 2000)),
        "expected_energy_millijoules": int(opp.get("energy_millijoules", 500)),
        "actor_root_position_mm": [0, 0, 0],
        "actor_root_heading_q15": [32767, 0],
        "actor_root_velocity_mm_s": [0, 0, 0],
        "footing_bits": 0b11,
        "recovery_ticks_remaining": 0,
        "injury_q8": [0, 0, 0, 0],
        "clearance_mm": [2000, 2000, 2000, 2000, 2000, 2000],
        "prompt": move["prompt"],
        "key_frames": move["key_frames"],
        "grip_centers": move["grip_centers"],
        "grip_axes": move["grip_axes"],
    }


def build_variants(move: dict) -> list[dict]:
    """Generate opponent-geometry variants for one move spec."""
    variants = []
    heights = [
        ("high", 1.65, "Head"),
        ("mid", 1.30, "Body"),
        ("low", 0.85, "Legs"),
    ]
    sides = [
        ("center", 0.0),
        ("left", -0.35),
        ("right", 0.35),
    ]
    timings = [
        ("early", 16),
        ("nominal", 24),
        ("late", 32),
    ]
    for h_name, h_y, target_role in heights:
        for s_name, s_x in sides:
            for t_name, contact_tick in timings:
                variants.append({
                    "id": f"{h_name}_{s_name}_{t_name}",
                    "opponent": {
                        "intent": "Strike",
                        "origin": [s_x, h_y, -1.2],
                        "target": [0.0, 1.25, 0.0],
                        "reach_m": 1.35,
                        "velocity_m_s": 3.0 + (0.5 if t_name == "early" else -0.5 if t_name == "late" else 0.0),
                        "contact_tick": contact_tick,
                        "emitter_role": "WeaponEdge",
                        "target_role": target_role,
                        "impulse_milli_ns": 2000 + (500 if h_name == "high" else 0),
                        "energy_millijoules": 500 + (200 if h_name == "high" else 0),
                    },
                })
    return variants


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--moves", nargs="*", default=None)
    args = parser.parse_args()

    batch = json.loads(BATCH_SPEC.read_text())
    moves = batch["moves"]
    if args.moves:
        moves = [m for m in moves if m["id"] in args.moves]

    args.out.mkdir(parents=True, exist_ok=True)
    records = []
    for move in moves:
        for variant in build_variants(move):
            example = build_interaction_tensor(move, variant)
            example["example_sha256"] = sha256_bytes(canonical_json(example))
            records.append(example)

    manifest = {
        "schema": "interaction-corpus-manifest.v1",
        "count": len(records),
        "move_ids": [m["id"] for m in moves],
        "examples": records,
    }
    manifest["manifest_sha256"] = sha256_bytes(canonical_json(manifest))
    (args.out / "interaction_corpus.json").write_bytes(canonical_json(manifest) + b"\n")
    print(f"INTERACTION_CORPUS=PASS count={len(records)} out={args.out / 'interaction_corpus.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
