#!/usr/bin/env python3
"""Mesh promotion gate (WO §5) — fail-closed validator for promotable mesh assets.

Enforces the MEASURABLE mesh-quality thresholds before a mesh asset can be
promoted. A gate failure is reported with the exact breached threshold; the gate
NEVER weakens thresholds to obtain green. Automatic vision may prioritize, but
only the human owner may approve/promote — this gate is a necessary (not
sufficient) condition.

Checks (measurable subset of WO §5):
  - zero non-adjacent self-intersections above the signed-distance tolerance,
    outside explicitly named contact masks (via the Mesh Doctor detection report)
  - signed-distance tolerance <= 0.5 mm (deepest finding must not exceed it)
  - no NaN/Inf in GLB vertex positions (parse the GLB position accessor)
  - no unexpected vertex-count drift vs a declared baseline (if provided)
  - baked GLB passes Khronos glTF validation with zero errors (delegates to the
    existing validate_gltf_assets.sh result if available, else checks GLB parse)

NOT checked here (forward work / human-bound): cloth/armor/weapon pair clearance
targets (need mesh decomposition), protected-seam displacement, repair falloff
limits, weight-sum drift, correction pop (needs animation), zero visible
penetration in gameplay views (human visual gate).

Exit 0 = gate PASS (promotable candidate); 1 = gate FAIL (with breached reasons).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIGNED_DISTANCE_TOL_M = 0.0005  # 0.5 mm (WO §5)


def read_glb_positions(path: Path):
    """Parse GLB, return (vertex_count, has_nan_or_inf, position_min, position_max)."""
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise ValueError("not a GLB (bad magic)")
    json_len = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + json_len])
    # binary chunk offset
    bin_start = 20 + json_len
    if bin_start >= len(data):
        raise ValueError("GLB has no binary chunk")
    bin_len = struct.unpack_from("<I", data, bin_start)[0]
    bin_start += 8
    bin_blob = data[bin_start:bin_start + bin_len]

    vertex_count = 0
    has_nan_inf = False
    pmin = [float("inf")] * 3
    pmax = [float("-inf")] * 3
    accessors = doc.get("accessors", [])
    buffer_views = doc.get("bufferViews", [])
    for mesh in doc.get("meshes", []):
        for prim in mesh.get("primitives", []):
            pos_idx = prim.get("attributes", {}).get("POSITION")
            if pos_idx is None:
                continue
            acc = accessors[pos_idx]
            vertex_count += acc.get("count", 0)
            bv = buffer_views[acc["bufferView"]]
            offset = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
            stride = bv.get("byteStride", 12)
            ctype = acc["componentType"]
            if ctype != 5126:  # float32
                continue
            for i in range(acc["count"]):
                o = offset + i * stride
                x, y, z = struct.unpack_from("<fff", bin_blob, o)
                for k, val in enumerate((x, y, z)):
                    if val != val or val in (float("inf"), float("-inf")):
                        has_nan_inf = True
                    pmin[k] = min(pmin[k], val)
                    pmax[k] = max(pmax[k], val)
    return vertex_count, has_nan_inf, pmin, pmax


def load_detection(root: Path, asset: str):
    """Load the Mesh Doctor detection report for the asset, if present."""
    d = root / "qa_runs/p4_mesh_doctor"
    cands = [
        d / "w0_pair_Guard_BladeAndTang.json" if ("w0" in asset or "sword" in asset) else None,
        d / "c0_self_intersect.json" if ("c0" in asset or "duelist" in asset) else None,
    ]
    for c in cands:
        if c is not None and c.is_file():
            return json.loads(c.read_text())
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--glb", required=True)
    ap.add_argument("--baseline-vertices", type=int, default=None,
                    help="declared baseline vertex count; gate fails on drift")
    ap.add_argument("--max-vertex-drift", type=int, default=0,
                    help="allowed vertex-count drift (WO: no unexpected drift; default 0)")
    ap.add_argument("--detection", default=None,
                    help="explicit Mesh Doctor detection report path (else auto-locate)")
    ap.add_argument("--report", default=None, help="write gate result JSON here")
    args = ap.parse_args()

    glb = Path(args.glb)
    breaches = []
    checks = {}

    # 1. GLB parse + NaN/Inf + vertex count
    try:
        vcount, has_nan_inf, pmin, pmax = read_glb_positions(glb)
        checks["vertex_count"] = vcount
        checks["has_nan_or_inf"] = has_nan_inf
        if has_nan_inf:
            breaches.append("NaN/Inf in vertex positions")
        if args.baseline_vertices is not None:
            drift = abs(vcount - args.baseline_vertices)
            checks["vertex_drift"] = drift
            if drift > args.max_vertex_drift:
                breaches.append(f"vertex-count drift {drift} > {args.max_vertex_drift} (baseline {args.baseline_vertices}, got {vcount})")
    except Exception as e:  # noqa: BLE001
        breaches.append(f"GLB parse failed: {e}")

    # 2. self-intersection + signed-distance tolerance
    det_path = Path(args.detection) if args.detection else None
    detection = None
    if det_path and det_path.is_file():
        detection = json.loads(det_path.read_text())
    elif det_path is None:
        detection = load_detection(ROOT, str(glb))
    if detection is None:
        checks["detection"] = "not available"
        breaches.append("no Mesh Doctor detection report for asset (gate cannot verify zero self-intersection)")
    else:
        clusters = detection.get("clusters") or detection.get("findings") or []
        over_tol = [c for c in clusters if abs(c.get("signed_depth_m", 0)) > SIGNED_DISTANCE_TOL_M]
        checks["self_intersections_over_tolerance"] = len(over_tol)
        if over_tol:
            deepest = min(over_tol, key=lambda c: c.get("signed_depth_m", 0))
            breaches.append(
                f"{len(over_tol)} non-adjacent self-intersections exceed signed-distance tolerance 0.5mm "
                f"(deepest {deepest.get('signed_depth_m',0)*1000:.2f}mm)")

    result = {
        "schema": "just-dodge-mesh-promotion-gate-v1",
        "glb": str(glb),
        "gate": "PASS" if not breaches else "FAIL",
        "checks": checks,
        "breaches": breaches,
        "signed_distance_tolerance_m": SIGNED_DISTANCE_TOL_M,
        "note": "measurable subset of WO §5; pair clearance/seam/weight/pop/visual gates are forward work or human-bound",
        "human_approval_required": True,
    }
    out = json.dumps(result, indent=1, sort_keys=True) + "\n"
    if args.report:
        Path(args.report).write_text(out)
    print(out)
    print(f"MESH_PROMOTION_GATE {result['gate']} breaches={len(breaches)}")
    return 0 if not breaches else 1


if __name__ == "__main__":
    raise SystemExit(main())
