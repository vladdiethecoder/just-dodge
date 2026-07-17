#!/usr/bin/env python3
"""Gate G6: rerun Grab-07 capture and fail on the first deterministic divergence.

``--capture-command`` is an argv-style command string containing exactly one
``{output_dir}`` placeholder.  It must invoke the pinned capture executable and
write capture.jsonl/findings.jsonl beneath that directory.  The verifier copies
only immutable phase/camera/repair inputs into an isolated temporary run, builds
a second receipt there, then compares capture values and receipt bytes.
"""
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from grab07_common import ContractError, canonical_bytes, parse_capture, parse_findings, require, sha256_file

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_DIR = ROOT / "qa_runs/grab07_promotion"
BUILDER = Path(__file__).with_name("build_grab07_receipt.py")


def first_difference(left: Any, right: Any, path: str = "") -> str | None:
    if type(left) is not type(right):
        return path or "value_type"
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                return f"{path}.{key}".strip(".")
            result = first_difference(left[key], right[key], f"{path}.{key}".strip("."))
            if result is not None:
                return result
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}.length"
        for index, (item_left, item_right) in enumerate(zip(left, right)):
            result = first_difference(item_left, item_right, f"{path}[{index}]")
            if result is not None:
                return result
        return None
    return None if left == right else (path or "value")


def capture_divergence(baseline: list[dict[str, Any]], rerun: list[dict[str, Any]]) -> tuple[int | None, str] | None:
    """Compare capture records (one unique record per physics tick)."""
    by_tick_left = {record["physics_tick"]: record for record in baseline}
    by_tick_right = {record["physics_tick"]: record for record in rerun}
    for tick in sorted(set(by_tick_left) | set(by_tick_right)):
        if tick not in by_tick_left or tick not in by_tick_right:
            return tick, "record_missing"
        field = first_difference(by_tick_left[tick], by_tick_right[tick])
        if field is not None:
            return tick, field
    return None


def findings_divergence(baseline: list[dict[str, Any]], rerun: list[dict[str, Any]]) -> tuple[int | None, str] | None:
    """Compare all Mesh Doctor findings; several valid findings may share a tick."""
    def grouped(records: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
        groups: dict[int, list[dict[str, Any]]] = {}
        for record in records:
            groups.setdefault(record["physics_tick"], []).append(record)
        for group in groups.values():
            group.sort(key=canonical_bytes)
        return groups

    left_groups, right_groups = grouped(baseline), grouped(rerun)
    for tick in sorted(set(left_groups) | set(right_groups)):
        if tick not in left_groups or tick not in right_groups:
            return tick, "finding_missing"
        left, right = left_groups[tick], right_groups[tick]
        if len(left) != len(right):
            return tick, "findings.length"
        for index, (left_finding, right_finding) in enumerate(zip(left, right)):
            field = first_difference(left_finding, right_finding)
            if field is not None:
                return tick, f"findings[{index}].{field}"
    return None


def write_result(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--capture-command", required=True, help="argv string containing {output_dir}")
    parser.add_argument("--executable", type=Path, default=None, help="required if capture metadata lacks executable_sha256")
    parser.add_argument("--out", type=Path, default=None, help="defaults to RUN_DIR/determinism.json")
    args = parser.parse_args()
    run_dir = args.run_dir
    result_path = args.out or run_dir / "determinism.json"
    result: dict[str, Any] = {"schema": "grab07-determinism-v1", "status": "FAIL"}
    try:
        require("{output_dir}" in args.capture_command, "--capture-command must contain {output_dir}")
        baseline_capture = parse_capture(run_dir / "capture.jsonl")
        baseline_findings = parse_findings(run_dir / "findings.jsonl", baseline_capture)
        baseline_receipt_path = run_dir / "receipt.json"
        baseline_receipt = json.loads(baseline_receipt_path.read_text(encoding="utf-8"))
        require(isinstance(baseline_receipt, dict), "receipt.json must be object")
        result.update({
            "baseline_receipt_sha256": sha256_file(baseline_receipt_path),
            "baseline_deterministic_rerun_sha256": baseline_receipt.get("deterministic_rerun_sha256"),
        })
        with tempfile.TemporaryDirectory(prefix="grab07-determinism-") as temp_name:
            temp_run = Path(temp_name) / "run"
            temp_run.mkdir(parents=True)
            # The capture binary owns phases/cameras and may clear its output directory;
            # copy them for synthetic runners that only emit JSONL.  Immutable repair
            # artifacts are copied *after* capture so an output-directory reset cannot
            # erase them.
            for name in ("phases.json", "cameras.json"):
                source = run_dir / name
                if source.is_file():
                    shutil.copy2(source, temp_run / name)
            command = [part.replace("{output_dir}", str(temp_run)) for part in shlex.split(args.capture_command)]
            completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
            result["capture_command_returncode"] = completed.returncode
            if completed.returncode:
                result["capture_command_stderr"] = completed.stderr[-2000:]
                raise ContractError(f"capture command failed with exit {completed.returncode}")
            for name in ("repair_receipt.json", "repair_candidate.glb"):
                source = run_dir / name
                if source.is_file():
                    shutil.copy2(source, temp_run / name)
            rerun_capture = parse_capture(temp_run / "capture.jsonl")
            rerun_findings = parse_findings(temp_run / "findings.jsonl", rerun_capture)
            builder_command = [
                sys.executable, str(BUILDER), "--run-dir", str(temp_run),
                "--motion-sha256", str(baseline_receipt["inputs"]["motion_sha256"]),
                "--mesh-sha256", str(baseline_receipt["inputs"]["mesh_sha256"]),
                "--opponent-root-offset", ",".join(str(item) for item in baseline_receipt["inputs"]["opponent_root_offset"]),
            ]
            if args.executable is not None:
                builder_command.extend(["--executable", str(args.executable)])
            receipt_build = subprocess.run(builder_command, cwd=ROOT, text=True, capture_output=True)
            result["receipt_build_returncode"] = receipt_build.returncode
            if receipt_build.returncode:
                result["receipt_build_stderr"] = receipt_build.stderr[-2000:]
                raise ContractError("rerun receipt build failed")
            rerun_receipt_path = temp_run / "receipt.json"
            rerun_receipt = json.loads(rerun_receipt_path.read_text(encoding="utf-8"))
            divergence = capture_divergence(baseline_capture, rerun_capture)
            if divergence is None:
                # Findings carry the Mesh Doctor contact metrics that are not in capture records.
                divergence = findings_divergence(baseline_findings, rerun_findings)
            result.update({
                "rerun_receipt_sha256": sha256_file(rerun_receipt_path),
                "rerun_deterministic_rerun_sha256": rerun_receipt.get("deterministic_rerun_sha256"),
            })
            if divergence is not None:
                tick, field = divergence
                result["first_divergence"] = {"physics_tick": tick, "field": field}
                raise ContractError(f"first divergence physics_tick={tick} field={field}")
            if result["baseline_receipt_sha256"] != result["rerun_receipt_sha256"]:
                field = first_difference(baseline_receipt, rerun_receipt) or "receipt_bytes"
                result["first_divergence"] = {"physics_tick": None, "field": f"receipt.{field}"}
                raise ContractError(f"receipt hash differs; first field {field}")
            if result["baseline_deterministic_rerun_sha256"] != result["rerun_deterministic_rerun_sha256"]:
                result["first_divergence"] = {"physics_tick": None, "field": "deterministic_rerun_sha256"}
                raise ContractError("deterministic_rerun_sha256 differs")
        result["status"] = "PASS"
        write_result(result_path, result)
        print(f"GRAB07_DETERMINISM=PASS receipt_sha256={result['baseline_receipt_sha256']}")
        return 0
    except (ContractError, OSError, ValueError, json.JSONDecodeError) as exc:
        result["error"] = str(exc)
        write_result(result_path, result)
        print(f"GRAB07_DETERMINISM=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
