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
    if report.get("schema") != "just-dodge-pvp005-revision-baseline-v1":
        raise SystemExit("unsupported PVP-005 revision baseline schema")

    baseline = report["published_feature_baseline"]
    public_main = report["public_main"]
    for revision in (baseline, public_main, *report["historical_evidence_revisions"].values()):
        run("git", "cat-file", "-e", f"{revision}^{{commit}}")
    require_ancestor(public_main, baseline, "public main is not baseline ancestor")
    for name, revision in report["historical_evidence_revisions"].items():
        require_ancestor(revision, baseline, f"{name} is not baseline ancestor")

    candidate = report["candidate_packet"]
    manifest_path = ROOT / candidate["manifest"]
    if sha256(manifest_path) != candidate["manifest_sha256"]:
        raise SystemExit("PVP-005 candidate manifest hash drift")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("status") != candidate["status"]:
        raise SystemExit("PVP-005 candidate status drift")
    if manifest.get("runtime_promoted") is not candidate["runtime_promoted"]:
        raise SystemExit("PVP-005 runtime promotion status drift")

    pvp004 = json.loads(
        (ROOT / "docs/reports/PVP004_PACKAGE_EVIDENCE.json").read_text()
    )
    if pvp004["evaluated_revision"] != report["historical_evidence_revisions"]["pvp004_package"]:
        raise SystemExit("PVP-004 evaluated revision was relabeled")
    reachability = pvp004.get("reachability", {})
    if reachability.get("published_feature_baseline") != baseline:
        raise SystemExit("PVP-004 reachability baseline mismatch")

    required_status = {
        "README.md": (baseline, report["published_branch"], "PLAYABLE-PROOF has not passed"),
        ".hermes/atomic_ledger.md": (baseline, report["published_branch"]),
        "docs/reports/CURRENT_STATE_AUDIT.md": (baseline, report["published_branch"]),
        "docs/reports/DEVELOPMENT_TASKLIST.md": (baseline, report["published_branch"]),
        "docs/reports/MILESTONE_03_FIRST_PLAYABLE_REPORT.md": (baseline,),
        "docs/design/IMPLEMENTATION_PLAN_3ACTION.md": (baseline, report["published_branch"]),
    }
    for relative, tokens in required_status.items():
        text = (ROOT / relative).read_text()
        missing = [token for token in tokens if token not in text]
        if missing:
            raise SystemExit(f"status reconciliation missing from {relative}: {missing}")

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
