#!/usr/bin/env python3
"""Verify that PVP-005 status and historical evidence share one reachable history."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/reports/PVP005_REVISION_BASELINE.json"


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def require_ancestor(ancestor: str, descendant: str, label: str) -> None:
    result = subprocess.run(
        ("git", "merge-base", "--is-ancestor", ancestor, descendant),
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"revision history mismatch: {label}")


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--remote",
        action="store_true",
        help="also require the published branch to exist on origin",
    )
    args = parser.parse_args()
    report = json.loads(REPORT.read_text())
    if report.get("schema") != "just-dodge-pvp005-revision-baseline-v2":
        raise SystemExit("unsupported PVP-005 revision baseline schema")
    if report.get("authority") != "historical_reachability_only":
        raise SystemExit("PVP-005 historical baseline was relabeled as current authority")
    current_status = ROOT / report["current_status_authority"]
    if not current_status.is_file():
        raise SystemExit("current SG01 status authority is missing")

    baseline = report["published_feature_baseline"]
    public_main = report["public_main"]
    for revision in (baseline, public_main, *report["historical_evidence_revisions"].values()):
        run("git", "cat-file", "-e", f"{revision}^{{commit}}")
    require_ancestor(public_main, baseline, "public main is not baseline ancestor")
    for name, revision in report["historical_evidence_revisions"].items():
        require_ancestor(revision, baseline, f"{name} is not baseline ancestor")

    candidate = report["candidate_packet"]
    manifest_path = ROOT / candidate["manifest"]
    if candidate.get("retired") is not True or candidate.get("manifest_required") is not False:
        raise SystemExit("PVP-005 candidate retirement boundary drift")
    if candidate.get("runtime_promoted") is not False:
        raise SystemExit("retired PVP-005 candidate cannot be runtime-promoted")
    if candidate.get("status") != "retired_not_current_evidence":
        raise SystemExit("PVP-005 candidate retirement status drift")
    if manifest_path.exists():
        raise SystemExit("retired PVP-005 candidate manifest reappeared outside quarantine")
    if len(candidate.get("historical_manifest_sha256", "")) != 64:
        raise SystemExit("PVP-005 historical candidate hash is missing")

    pvp004 = json.loads(
        (ROOT / "docs/reports/PVP004_PACKAGE_EVIDENCE.json").read_text()
    )
    if pvp004["evaluated_revision"] != report["historical_evidence_revisions"]["pvp004_package"]:
        raise SystemExit("PVP-004 evaluated revision was relabeled")
    reachability = pvp004.get("reachability", {})
    if reachability.get("published_feature_baseline") != baseline:
        raise SystemExit("PVP-004 reachability baseline mismatch")

    current_authority = report["current_status_authority"]
    required_status = {
        "README.md": ("SG01-EVIDENCE-CANON-RESET-002", current_authority, "SG01 is **not passed**"),
        ".hermes/atomic_ledger.md": ("SG01-EVIDENCE-CANON-RESET-002", "SG01 is not PASS"),
        "docs/reports/CURRENT_STATE_AUDIT.md": ("Historical State Audit", current_authority),
        "docs/reports/DEVELOPMENT_TASKLIST.md": ("Historical PVP-005", current_authority),
        "docs/reports/MILESTONE_03_FIRST_PLAYABLE_REPORT.md": ("Historical Milestone 3", current_authority),
        "docs/design/IMPLEMENTATION_PLAN_3ACTION.md": ("Historical Implementation Plan", current_authority),
    }
    for relative, tokens in required_status.items():
        text = (ROOT / relative).read_text()
        missing = [token for token in tokens if token not in text]
        if missing:
            raise SystemExit(f"status reconciliation missing from {relative}: {missing}")

    current = json.loads(current_status.read_text())
    if current.get("verdict") != "FAIL_BLOCKED_RECONCILIATION_REQUIRED":
        raise SystemExit("current SG01 baseline must remain fail-closed until clean-checkout closure")
    if current.get("sg01_can_proceed_to_sg02") is not False:
        raise SystemExit("current SG01 baseline improperly permits SG02")
    if current.get("promotion") != "BLOCKED" or current.get("human_decision") != "PENDING":
        raise SystemExit("current SG01 promotion/human boundary drift")

    if args.remote:
        output = run(
            "git",
            "ls-remote",
            "--heads",
            "origin",
            report["published_branch"],
        )
        if not output:
            raise SystemExit("published PVP-005 branch is absent on origin")
        remote_tip = output.split()[0]
        if remote_tip != baseline:
            run("git", "cat-file", "-e", f"{remote_tip}^{{commit}}")
            require_ancestor(baseline, remote_tip, "baseline is not reachable from remote tip")

    print(f"PVP005_REACHABLE_BASELINE={baseline}")
    print(
        "PVP005_REVISION_RECONCILIATION=PASS "
        f"historical_revisions={len(report['historical_evidence_revisions'])} "
        f"remote_checked={str(args.remote).lower()}"
    )


if __name__ == "__main__":
    main()
