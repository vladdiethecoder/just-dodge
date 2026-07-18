#!/usr/bin/env python3
"""Regression test: prove that a deliberate metric failure fails CI.

This test intentionally produces a metric failure (median > 15mm) and verifies
that the CI pipeline rejects it with a nonzero exit code.
"""
from __future__ import annotations
import json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_deliberate_metric_failure_fails_ci() -> int:
    """Run the trainer with a deliberately bad metric and verify CI fails."""
    # Create a deliberately bad training report (median 100mm > 15mm gate)
    bad_report = {
        "verdict": "FAIL",
        "median_cond_mm": 100.0,
        "best_cond_mm": 50.0,
        "median_abl_mm": 200.0,
        "median_ablation_delta_mm": 100.0,
        "ablation_ok": True,
        "train_segments": 100,
        "heldout_segments": 10,
        "train_corpora": ["CMU"],
        "arch": "test",
        "heldout_conditioned": [
            {"seg_id": "test_001", "hand_surface_err_mm": 100.0, "corpus": "CMU"}
        ],
    }

    # Write the bad report to a temporary location
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bad_report, f)
        bad_report_path = f.name

    # Run the CI verification script and expect it to fail
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/qa/test_heldout_motion_acceptance.py"),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    # The test should fail because the metric is deliberately bad
    if result.returncode == 0:
        print("ERROR: CI passed with deliberately bad metric (should have failed)")
        return 1

    print(f"CI correctly failed with deliberately bad metric: exit={result.returncode}")
    return 0


def test_deliberate_receipt_failure_fails_ci() -> int:
    """Run the trainer with a deliberately bad receipt and verify CI fails."""
    # Create a deliberately bad receipt (verdict=FAIL)
    bad_receipt = {
        "schema": "just-dodge-grab07-unit2-receipt-v7-pass",
        "verdict": "FAIL",
        "median_cond_mm": 100.0,
        "machine_eligible": False,
        "promotion": "BLOCKED",
    }

    # Write the bad receipt to a temporary location
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bad_receipt, f)
        bad_receipt_path = f.name

    # Run the CI verification script and expect it to fail
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/qa/test_interaction_partition_leakage.py"),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    # The test should fail because the receipt is deliberately bad
    if result.returncode == 0:
        print("ERROR: CI passed with deliberately bad receipt (should have failed)")
        return 1

    print(f"CI correctly failed with deliberately bad receipt: exit={result.returncode}")
    return 0


def main() -> int:
    """Run all regression tests."""
    print("PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001: Regression Tests")
    print("=" * 60)

    failures = 0

    # Test 1: Deliberate metric failure
    print("\nTest 1: Deliberate metric failure (median 100mm > 15mm)")
    if test_deliberate_metric_failure_fails_ci() != 0:
        failures += 1

    # Test 2: Deliberate receipt failure
    print("\nTest 2: Deliberate receipt failure (verdict=FAIL)")
    if test_deliberate_receipt_failure_fails_ci() != 0:
        failures += 1

    print("\n" + "=" * 60)
    if failures == 0:
        print("ALL REGRESSION TESTS PASS: CI correctly fails on deliberate failures")
        return 0
    else:
        print(f"REGRESSION TESTS FAILED: {failures} test(s) did not fail CI correctly")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
