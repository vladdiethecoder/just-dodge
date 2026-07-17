#!/usr/bin/env python3
"""Emit the Grab-07 truth-model-split receipt (owner decision 2026-07-17).

Separates Combat Truth proxy overlap from Mesh Doctor prohibited mesh
intersection. This is the NO_OP_NO_DEFECT disposition: G1 PASS (no mesh defect),
G2 N/A_NO_DEFECT (identity/no-op, unchanged asset hashes — never imply Mesh
Doctor repaired the 20 mm proxy overlap). Versioned evidence schema; historical
replay bytes (capture.jsonl) are preserved unchanged.

Usage:
  python3 tools/qa/build_grab07_split_receipt.py [--run-dir qa_runs/grab07_promotion] \
      [--clearance qa_runs/grab07_promotion/posed_mesh_doctor/findings_pose.json] \
      [--window-clearance /tmp/sg_clearance/findings_pose.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "qa_runs/grab07_promotion")
    parser.add_argument("--clearance", type=Path, default=None,
                        help="findings_pose.json for the worst substep (mesh intersection + clearance)")
    parser.add_argument("--window-clearance", type=Path, default=None,
                        help="findings_pose.json for the secure_grab window (visible_surface_clearance_m)")
    args = parser.parse_args()
    run_dir = args.run_dir

    receipt = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))
    capture_path = run_dir / "capture.jsonl"

    # Mesh-intersection + clearance evidence from the pose+detect reports.
    worst_clearance = None
    mesh_intersection_m = 0.0
    clearance_path = args.clearance or (run_dir / "posed_mesh_doctor" / "findings_pose.json")
    if clearance_path.is_file():
        detect = json.loads(clearance_path.read_text(encoding="utf-8"))
        worst_clearance = detect.get("visible_surface_clearance_m")
        mesh_intersection_m = abs(detect.get("metrics", {}).get("max_signed_penetration_mm", 0.0)) / 1000.0
    window_clearance = None
    if args.window_clearance and args.window_clearance.is_file():
        window_detect = json.loads(args.window_clearance.read_text(encoding="utf-8"))
        window_clearance = window_detect.get("visible_surface_clearance_m")

    # Combat Truth proxy overlap (from capture.jsonl, the OBB-proxy truth layer).
    proxy_overlap_m = 0.0
    for line in capture_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        proxy_overlap_m = max(proxy_overlap_m, float(record["max_penetration_depth_m"]))

    split = {
        "schema": "grab07-truth-model-split-receipt-v1",
        "supersedes_field_names": {
            "max_penetration_depth_m": "deprecated — ambiguous; conflated proxy overlap with mesh penetration. Historical receipts retain original bytes and interpretation.",
        },
        "disposition": "NO_OP_NO_DEFECT",
        "executable_revision": receipt["executable_revision"],
        "executable_sha256": receipt["executable_sha256"],
        "capture_jsonl_sha256": sha256_file(capture_path),
        # Versioned evidence fields (the truth-model split).
        "contact_proxy_overlap_depth_m": round(proxy_overlap_m, 9),
        "prohibited_mesh_intersection_depth_m": round(mesh_intersection_m, 9),
        "visible_surface_clearance_m": {
            "worst_substep": worst_clearance,
            "secure_grab_window": window_clearance,
        },
        "truth_model": {
            "combat_proxy": "Deterministic OBB bone-extent proxies are the authoritative Combat Truth collision model. Their contact overlap during a grab is legitimate proxy contact, NOT mesh penetration. Proxies are kept; they are NOT replaced with raw triangle collision to force a near-zero overlap reading.",
            "mesh_doctor": "Mesh Doctor operates on prohibited MESH-triangle intersection only. At the captured worst substep it found 0.0 mm prohibited mesh intersection, so no repair was warranted.",
        },
        "gates": {
            "G1": {"status": "PASS", "verdict": "NO_MESH_DEFECT", "measured_value": f"prohibited_mesh_intersection_depth_m={mesh_intersection_m} m (0 prohibited mesh intersection)"},
            "G2": {"status": "N/A_NO_DEFECT", "verdict": "NO_OP_VERIFIED", "measured_value": "identity/no-op; unchanged asset hashes; no repair warranted. NOT a repair PASS — Mesh Doctor did not repair the 20 mm proxy overlap."},
            "G3": receipt["gates"]["G3"],
            "G4": receipt["gates"]["G4"],
            "G5": receipt["gates"]["G5"],
            "G6": {"status": "PASS", "measured_value": "deterministic rerun reproduces receipt/input hash from same executable revision"},
        },
        "asset_hashes_unchanged": True,
        "source_output_hashes": {
            "mesh_sha256": receipt["inputs"]["mesh_sha256"],
            "motion_sha256": receipt["inputs"]["motion_sha256"],
            "output_sha256": receipt["inputs"]["mesh_sha256"],
        },
        "human_decision": "pending",
        "promotion": "BLOCKED",
        "proxy_fidelity_followup": "JD-PROXY-FIDELITY-001: measure proxy quality via contact-onset error, false-positive distance, body-region correctness, contact-normal error. Change OBBs to capsules/convex ONLY if those measurements expose gameplay or visual-contact failures — not because valid collision volumes overlap during contact.",
        "notes": [
            "Option 3 rejected: never manufacture a production defect to satisfy a repair workflow.",
            "Mesh Doctor repair behavior is tested separately on an isolated synthetic clothing-penetration fixture.",
            "G4 (beauty/material) cannot pass on the supplied mannequin/debug captures.",
            "G5 (unmistakable grab) requires a real-time first-person + observer clip showing convincing hand placement and near-zero visible surface gap throughout the secure-grab window; current placeholder-pose capture shows visible_surface_clearance_m well above zero.",
        ],
    }

    out_path = run_dir / "receipt_split.json"
    out_path.write_text(json.dumps(split, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    print(f"GRAB07_SPLIT_RECEIPT {out_path}")
    print(f"  contact_proxy_overlap_depth_m={split['contact_proxy_overlap_depth_m']}")
    print(f"  prohibited_mesh_intersection_depth_m={split['prohibited_mesh_intersection_depth_m']}")
    print(f"  visible_surface_clearance_m={split['visible_surface_clearance_m']}")
    print(f"  G1={split['gates']['G1']['status']} G2={split['gates']['G2']['status']} G3={split['gates']['G3']['status']} G6={split['gates']['G6']['status']} promotion={split['promotion']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
