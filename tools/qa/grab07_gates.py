#!/usr/bin/env python3
"""Evaluate Grab-07 promotion gates G1--G6 without auto-approving human gates.

Exit 1 when any automatically evaluated, fail-closed gate is FAIL.  G4 and G5
remain PENDING_HUMAN because automatic tooling may prioritize visual review but
may never approve it; the receipt's human_decision is displayed separately.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from grab07_common import ContractError, evaluate_gates, parse_capture, parse_findings, require

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_DIR = ROOT / "qa_runs/grab07_promotion"


def load_optional_determinism(path: Path) -> dict | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: determinism result must be object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--receipt", type=Path, default=None)
    parser.add_argument("--determinism", type=Path, default=None, help="defaults to RUN_DIR/determinism.json")
    args = parser.parse_args()
    run_dir = args.run_dir
    try:
        receipt_path = args.receipt or run_dir / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        require(isinstance(receipt, dict) and receipt.get("schema") == "grab07-promotion-receipt-v1", "receipt: unsupported schema")
        capture = parse_capture(run_dir / "capture.jsonl")
        findings = parse_findings(run_dir / "findings.jsonl", capture)
        determinism = load_optional_determinism(args.determinism or run_dir / "determinism.json")
        gates = evaluate_gates(receipt, capture, findings, determinism)
        print("GATE  STATUS         MEASURED VALUE")
        for gate_id in ("G1", "G2", "G3", "G4", "G5", "G6"):
            gate = gates[gate_id]
            print(f"{gate_id:<5} {gate['status']:<14} {gate['measured_value']}")
        print(f"HUMAN_DECISION {receipt.get('human_decision', 'missing')}")
        failures = [gate_id for gate_id, gate in gates.items() if gate["status"] == "FAIL"]
        pending = [gate_id for gate_id, gate in gates.items() if gate["status"] == "PENDING_HUMAN"]
        overall = "FAIL" if failures else ("BLOCKED_PENDING_HUMAN" if pending else "PASS")
        suffix = " failed=" + ",".join(failures) if failures else (" pending=" + ",".join(pending) if pending else "")
        print("GRAB07_GATES=" + overall + suffix)
        return 0 if not failures else 1
    except (ContractError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"GRAB07_GATES=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
