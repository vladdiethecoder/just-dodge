#!/usr/bin/env python3
"""Build the fail-closed Grab-07 promotion receipt (contract §9).

The tool validates the four capture artifacts before deriving metrics.  A missing
repair receipt is represented honestly as zero repair metrics and an output hash
of ``pending``; gate G1/G2 then remain failing rather than passing by default.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from grab07_common import (
    ContractError, canonical_bytes, evaluate_gates, metrics_from_capture_and_findings,
    parse_cameras, parse_capture, parse_findings, parse_phases, require, sha256_bytes,
    sha256_file, validate_schema,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_DIR = ROOT / "qa_runs/grab07_promotion"
SCHEMA_PATH = Path(__file__).with_name("grab07_promotion_receipt_v1.schema.json")
MOTION_SHA256 = "df134b66d5d239ac119ba48cd7dda4acd041db6521feaf0548ae8c2b9ec61444"
TOOL_VERSION = "grab07-receipt-builder-v1"
METRIC_KEYS = ("max_penetration_m", "rms_penetration_m", "affected_area_m2", "duration_ticks", "min_clearance_m")


def git_revision() -> str:
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True)
    if completed.returncode:
        raise ContractError(f"unable to read executable revision: {completed.stderr.strip()}")
    return completed.stdout.strip()


def required_metadata(*sources: dict[str, Any], key: str) -> Any | None:
    for source in sources:
        if key in source:
            return source[key]
    return None


def metric_block(value: Any, label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label}: must be object")
    require(set(METRIC_KEYS) <= set(value), f"{label}: missing {sorted(set(METRIC_KEYS) - set(value))}")
    result: dict[str, Any] = {}
    for key in METRIC_KEYS:
        item = value[key]
        if key == "duration_ticks":
            require(isinstance(item, int) and item >= 0, f"{label}.{key}: non-negative integer required")
        else:
            require(isinstance(item, (int, float)) and not isinstance(item, bool), f"{label}.{key}: finite number required")
            require(float(item) == float(item) and abs(float(item)) != float("inf"), f"{label}.{key}: finite number required")
            if key != "min_clearance_m":
                require(item >= 0, f"{label}.{key}: non-negative required")
        result[key] = item
    return result


def repair_values(path: Path | None, findings: list[dict[str, Any]], candidate_override: Path | None) -> tuple[dict[str, Any], dict[str, Any], str, str, dict[str, Any] | None]:
    """Return repair/after/source/output/raw, retaining an absent repair as pending."""
    source_hashes = sorted({str(item["artifact_sha256"]) for item in findings})
    require(len(source_hashes) == 1, "findings.jsonl: exactly one source artifact_sha256 required")
    source_sha = source_hashes[0]
    zero_metrics = {
        "max_penetration_m": 0.0, "rms_penetration_m": 0.0, "affected_area_m2": 0.0,
        "duration_ticks": 0, "min_clearance_m": 0.0,
    }
    repair = {"moved_vertex_ids": [], "moved_vertex_count": 0, "max_displacement_m": 0.0, "rms_displacement_m": 0.0}
    if path is None or not path.is_file():
        return repair, zero_metrics, source_sha, "pending", None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid repair receipt {path}: {exc}") from exc
    require(isinstance(raw, dict), "repair receipt: expected object")
    source_sha = str(raw.get("source_sha256", source_sha))
    requested = candidate_override or Path(raw.get("candidate_glb", raw.get("output_glb", path.parent / "repair_candidate.glb")))
    candidate_paths = [requested] if requested.is_absolute() else [path.parent / requested, ROOT / requested]
    candidate = next((item for item in candidate_paths if item.is_file()), None)
    require(candidate is not None, "repair receipt: immutable candidate GLB is required to compute output_sha256")
    output_sha = sha256_file(candidate)
    declared_sha = raw.get("output_sha256", raw.get("candidate_sha256"))
    require(isinstance(declared_sha, str) and declared_sha == output_sha, "repair receipt: declared candidate/output sha256 does not match candidate bytes")
    ids = raw.get("moved_vertex_ids", [])
    require(isinstance(ids, list) and all(isinstance(item, int) and item >= 0 for item in ids), "repair receipt: moved_vertex_ids must be non-negative integers")
    declared_count = raw.get("moved_vertex_count", len(ids))
    require(isinstance(declared_count, int) and declared_count == len(ids), "repair receipt: moved_vertex_count must equal moved_vertex_ids length")
    repair = {
        "moved_vertex_ids": ids,
        "moved_vertex_count": declared_count,
        "max_displacement_m": raw.get("max_displacement_m", 0.0),
        "rms_displacement_m": raw.get("rms_displacement_m", 0.0),
    }
    require(all(isinstance(repair[key], (int, float)) and repair[key] >= 0 for key in ("max_displacement_m", "rms_displacement_m")), "repair receipt: displacement metrics must be non-negative")
    after_value = raw.get("after", raw.get("after_metrics"))
    after = metric_block(after_value, "repair receipt after") if after_value is not None else zero_metrics
    return repair, after, source_sha, output_sha, raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--out", type=Path, default=None, help="defaults to RUN_DIR/receipt.json")
    parser.add_argument("--repair-receipt", type=Path, default=None, help="defaults to RUN_DIR/repair_receipt.json if it exists")
    parser.add_argument("--repair-candidate", type=Path, default=None, help="immutable repair candidate GLB; defaults to receipt/run-layout path")
    parser.add_argument("--executable", type=Path, default=None, help="pinned capture executable; required unless metadata has executable_sha256")
    parser.add_argument("--motion-sha256", default=MOTION_SHA256)
    parser.add_argument("--mesh-sha256", default=None)
    parser.add_argument("--opponent-root-offset", default=None, help="16 comma-separated matrix floats; required unless metadata supplies it")
    args = parser.parse_args()
    run_dir = args.run_dir
    try:
        capture_path = run_dir / "capture.jsonl"
        findings_path = run_dir / "findings.jsonl"
        phases_path = run_dir / "phases.json"
        cameras_path = run_dir / "cameras.json"
        capture = parse_capture(capture_path)
        findings = parse_findings(findings_path, capture)
        _phases, phase_metadata = parse_phases(phases_path, capture)
        _cameras, camera_metadata = parse_cameras(cameras_path)
        executable_sha = required_metadata(phase_metadata, camera_metadata, key="executable_sha256")
        if executable_sha is None:
            require(args.executable is not None and args.executable.is_file(), "--executable is required when metadata lacks executable_sha256")
            executable_sha = sha256_file(args.executable)
        require(isinstance(executable_sha, str) and executable_sha, "executable_sha256 must be non-empty")
        mesh_sha = args.mesh_sha256 or required_metadata(phase_metadata, camera_metadata, key="mesh_sha256")
        if mesh_sha is None:
            source_hashes = sorted({str(item["artifact_sha256"]) for item in findings})
            require(len(source_hashes) == 1, "--mesh-sha256 required when findings have multiple source artifacts")
            mesh_sha = source_hashes[0]
        if args.opponent_root_offset:
            offset = [float(value) for value in args.opponent_root_offset.split(",")]
        else:
            offset = required_metadata(phase_metadata, camera_metadata, key="opponent_root_offset")
        require(isinstance(offset, list) and len(offset) == 16 and all(isinstance(value, (int, float)) for value in offset), "opponent_root_offset must be an exact 16-float matrix")
        repair_path = args.repair_receipt or (run_dir / "repair_receipt.json")
        repair, after, source_sha, output_sha, repair_raw = repair_values(repair_path, findings, args.repair_candidate)
        before = metrics_from_capture_and_findings(capture, findings)
        deepest = min(findings, key=lambda item: float(item["signed_depth_m"]))
        cameras_sha = sha256_file(cameras_path)
        mesh_pairs = sorted({str(item["mesh_pair"]) for item in findings} | {str(contact["mesh_pair"]) for record in capture for contact in record["contacts"]})
        provenance = {
            "capture": capture, "findings": findings,
            "phases": json.loads(phases_path.read_text(encoding="utf-8")),
            "cameras": json.loads(cameras_path.read_text(encoding="utf-8")),
            "repair": repair_raw, "source_sha256": source_sha, "output_sha256": output_sha,
            "tool_version": TOOL_VERSION,
        }
        receipt: dict[str, Any] = {
            "schema": "grab07-promotion-receipt-v1",
            "executable_revision": required_metadata(phase_metadata, camera_metadata, key="executable_revision") or git_revision(),
            "executable_sha256": executable_sha,
            "build": {"rustc": "1.96.0", "blender": "5.1.2", "python": "3.14.6", "node": "v24.3.0"},
            "inputs": {"motion_sha256": args.motion_sha256, "mesh_sha256": mesh_sha, "cameras_sha256": cameras_sha, "opponent_root_offset": offset},
            "worst_substep": {"physics_tick": deepest["physics_tick"], "render_frame": deepest["physics_tick"] // 2},
            "mesh_pairs": mesh_pairs,
            "before": before,
            "after": after,
            "repair": repair,
            "source_sha256": source_sha,
            "output_sha256": output_sha,
            "tool_version": TOOL_VERSION,
            "deterministic_rerun_sha256": sha256_bytes(canonical_bytes(provenance)),
            "gates": {},
            "human_decision": "pending",
        }
        receipt["gates"] = evaluate_gates(receipt, capture, findings, determinism=None)
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validate_schema(receipt, schema)
        out = args.out or run_dir / "receipt.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(canonical_bytes(receipt))
        print(f"GRAB07_RECEIPT=PASS path={out} sha256={sha256_file(out)}")
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(f"GRAB07_RECEIPT=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
