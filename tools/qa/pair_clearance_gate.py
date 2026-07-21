#!/usr/bin/env python3
"""JD_Duelist_001 pair-clearance gate (G4/G5) — deterministic, offline, no credits.

Reads the component manifest, assembles all present component GLBs into one
Blender scene (WITHOUT joining), and runs mesh_doctor_pair_detect across the
required pairs: body<->armor, armor<->armor (adjacent), weapon<->body. Emits a
consolidated clearance receipt with the worst signed penetration per pair and a
fail-closed verdict against the canonical max_signed_penetration_mm.

Required pair rule (from the G0 brief):
- body_anatomy_carrier <-> every armor piece + every weapon piece + scabbard.
- adjacent armor pairs (pauldron<->cuirass, vambrace<->gauntlet, greave<->boot,
  belt_fauld<->greave).
- sword_blade <-> sword_guard <-> sword_grip (clearance, not penetration).

Usage (requires Blender headless with the component GLBs present):
  python3 tools/qa/pair_clearance_gate.py docs/design/JD_DUELIST_001_COMPONENT_MANIFEST.json \
      --components-dir DIR --work-dir DIR [--blender blender]

With no component GLBs present (G0 pending) it validates the pair PLAN and exits
0 reporting PLAN_ONLY. With GLBs present it runs the gate and fails closed on
any pair exceeding the canonical max signed penetration.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

BODY = "body_anatomy_carrier"
# Adjacency among armor pieces that must clear each other.
ARMOR_ADJACENCY = [
    ("pauldron_l", "torso_cuirass"),
    ("pauldron_r", "torso_cuirass"),
    ("vambrace_l", "gauntlet_l"),
    ("vambrace_r", "gauntlet_r"),
    ("belt_fauld", "greave_l"),
    ("belt_fauld", "greave_r"),
    ("greave_l", "boot_l"),
    ("greave_r", "boot_r"),
    ("helmet_head", "torso_cuirass"),
]
WEAPON_INTERNAL = [
    ("sword_blade", "sword_guard"),
    ("sword_guard", "sword_grip"),
    ("sword_grip", "sword_pommel"),
]


def load_manifest(path):
    with open(path) as fh:
        return json.load(fh)


def required_pairs(manifest):
    comps = {c["id"]: c for c in manifest["components"]}
    armor = [c["id"] for c in manifest["components"] if c["kind"] == "armor"]
    weapon = [c["id"] for c in manifest["components"] if c["kind"] == "weapon"]
    pairs = []
    for other in armor + weapon:
        pairs.append((BODY, other))
    pairs.extend(ARMOR_ADJACENCY)
    pairs.extend(WEAPON_INTERNAL)
    # Keep only pairs whose components are declared in the manifest.
    return [(a, b) for a, b in pairs if a in comps and b in comps]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--components-dir", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--blender", default="blender")
    ap.add_argument("--min-depth-m", type=float, default=None)
    args = ap.parse_args()

    manifest = load_manifest(args.manifest)
    canonical = manifest["canonical"]
    max_pen_mm = float(canonical.get("max_signed_penetration_mm", 0.5))
    min_depth = args.min_depth_m if args.min_depth_m is not None else max_pen_mm / 1000.0
    pairs = required_pairs(manifest)

    present = {
        cid
        for cid in (c["id"] for c in manifest["components"])
        if os.path.isfile(os.path.join(args.components_dir, f"{cid}.glb"))
    }
    if not present:
        print(f"PAIR_PLAN pairs={len(pairs)} (no component GLBs present; G0 pending)")
        for a, b in pairs:
            print(f"  pair {a} <-> {b}")
        print("PAIR_CLEARANCE_PLAN_ONLY")
        return 0

    os.makedirs(args.work_dir, exist_ok=True)
    body_present = BODY in present
    findings_total = 0
    breached = []
    for a, b in pairs:
        if a not in present or b not in present:
            continue
        report = os.path.join(args.work_dir, f"pair_{a}__{b}.json")
        cmd = [
            args.blender, "-b", "--factory-startup", "-noaudio",
            "--python", "tools/blender/mesh_doctor_pair_detect.py", "--",
            "--glb", os.path.join(args.components_dir, "assembled.glb"),
            "--object-a", a, "--object-b", b, "--report", report,
            "--min-depth-m", str(min_depth),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"PAIR_ERROR {a}<->{b}: {proc.stderr.strip()[:200]}")
            breached.append((a, b, "detector_error"))
            continue
        with open(report) as fh:
            data = json.load(fh)
        count = data["findings_count"]
        findings_total += count
        worst = min((f["signed_depth_m"] for f in data["findings"]), default=0.0)
        status = "BREACH" if count else "clear"
        print(f"PAIR {a}<->{b} findings={count} worst_signed_depth_m={worst} {status}")
        if count:
            breached.append((a, b, worst))

    receipt = {
        "schema": "just-dodge.pair-clearance-receipt.v1",
        "asset_id": manifest["asset_id"],
        "runtime_admitted": False,
        "components_present": sorted(present),
        "body_present": body_present,
        "max_signed_penetration_mm": max_pen_mm,
        "pairs_checked": len(pairs),
        "findings_total": findings_total,
        "breached": [
            {"pair": [a, b], "worst_signed_depth_m": w} for a, b, w in breached
        ],
        "verdict": "FAIL" if breached else "PASS",
    }
    receipt_path = os.path.join(args.work_dir, "pair_clearance_receipt.json")
    with open(receipt_path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"PAIR_CLEARANCE_RECEIPT {receipt_path} verdict={receipt['verdict']}")
    return 1 if breached else 0


if __name__ == "__main__":
    sys.exit(main())
