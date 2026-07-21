#!/usr/bin/env python3
"""Fail-closed SG01 evidence/canon boundary validator."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CURRENT_AUDIT = Path("docs/evidence_quarantine/SG01-EVIDENCE-CANON-RESET-002/baseline_audit.json")
CLEAN_RECEIPT = Path("docs/evidence_quarantine/SG01-EVIDENCE-CANON-RESET-002/clean_checkout_receipt.json")
HISTORICAL_AUDIT = Path(
    "docs/evidence_quarantine/PVP005-GRAB07-TRUTH-AND-EVIDENCE-RESET-004/sg01_audit.json"
)
UNIT2_QUARANTINE = Path(
    "docs/evidence_quarantine/PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001/quarantine_manifest.json"
)
PVP005_BASELINE = Path("docs/reports/PVP005_REVISION_BASELINE.json")
PVP005_VISUAL = Path("assets/qa/pvp005_visual_harness_v1.json")
PVP005_ARDY_AUTHORIZATION = Path("assets/qa/pvp005_ardy_v4_generation_authorization_v1.json")
RETIRED_ASSETS = Path("docs/provenance/RETIRED_ASSET_CORPUS_20260720.json")
RETIRED_QA = Path("docs/provenance/RETIRED_QA_CORPUS_20260721.json")
CURRENT_STATUS_FILES = (
    Path("README.md"),
    Path(".hermes/atomic_ledger.md"),
    Path("docs/design/AAA_FINISH_BACKLOG.md"),
)
FORBIDDEN_CURRENT_CLAIMS = (
    "MACHINE PASS (v13)",
    "G4 leakage-free MotionSeqModel retrained",
    '"sg01_can_proceed_to_sg02": true',
    "owner_visual_acceptance=true",
    "PROMOTION=PASS",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def forbidden_claims(documents: dict[str, str]) -> list[str]:
    return [
        f"{name}: {marker}"
        for name, text in documents.items()
        for marker in FORBIDDEN_CURRENT_CLAIMS
        if marker in text
    ]


def validate_quarantined_files(root: Path, manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for entry in manifest.get("quarantined_files", []):
        relative = Path(entry["quarantine"])
        path = root / relative
        if not path.is_file():
            failures.append(f"missing quarantined file: {relative}")
            continue
        if sha256(path) != entry["sha256"]:
            failures.append(f"quarantined file hash mismatch: {relative}")
        if path.stat().st_size != entry["size"]:
            failures.append(f"quarantined file size mismatch: {relative}")
    return failures


def git_blob(root: Path, revision: str, relative: str) -> bytes | None:
    completed = subprocess.run(
        ("git", "show", f"{revision}:{relative}"),
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.stdout if completed.returncode == 0 else None


def validate_retired_manifest(root: Path, manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    revision = manifest["source_revision"]
    external = set(manifest.get("external_untracked_hash_only", []))
    seen: set[str] = set()
    for entry in manifest["files"]:
        relative = entry["path"]
        if relative in seen:
            failures.append(f"duplicate retired path: {relative}")
            continue
        seen.add(relative)
        if (root / relative).exists():
            failures.append(f"retired path reappeared: {relative}")
        blob = git_blob(root, revision, relative)
        if relative in external:
            if blob is not None:
                failures.append(f"external hash-only path unexpectedly tracked: {relative}")
            continue
        if blob is None:
            failures.append(f"retired path unavailable at source revision: {relative}")
            continue
        if len(blob) != entry["bytes"]:
            failures.append(f"retired source size mismatch: {relative}")
        if hashlib.sha256(blob).hexdigest() != entry["sha256"]:
            failures.append(f"retired source hash mismatch: {relative}")
    if external - seen:
        failures.append("external hash-only inventory is not present in retired files")
    return failures


def validate_clean_receipt(clean_receipt: dict[str, Any], expected_stages: dict[str, str]) -> None:
    require(clean_receipt.get("verdict") == "SG01_PASS", "SG01 clean receipt verdict drift")
    require(clean_receipt.get("sg01_can_proceed_to_sg02") is True, "SG01 clean receipt blocks SG02")
    require(
        clean_receipt.get("promotion") == "SG01_PASS_G4_G5_BLOCKED",
        "SG01 clean receipt promotion boundary drift",
    )
    require(clean_receipt.get("human_decision") == "PENDING", "SG01 clean receipt fabricated human approval")
    require(clean_receipt.get("evidence_stages") == expected_stages, "SG01 clean receipt collapsed evidence stages")

    revision = clean_receipt.get("subject_revision")
    require(
        isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision) is not None,
        "invalid SG01 subject revision",
    )
    tree = clean_receipt.get("subject_tree")
    require(
        isinstance(tree, str) and re.fullmatch(r"[0-9a-f]{40}", tree) is not None,
        "invalid SG01 subject tree",
    )
    clean = clean_receipt.get("clean_checkout", {})
    require(clean.get("detached") is True, "SG01 receipt was not produced from a detached checkout")
    require(clean.get("initial_status_porcelain") == "", "SG01 checkout was initially dirty")
    require(clean.get("final_status_porcelain") == "", "SG01 checkout was finally dirty")
    require(
        re.fullmatch(r"[0-9a-f]{64}", str(clean.get("full_log_sha256", ""))) is not None,
        "invalid SG01 clean-checkout log digest",
    )

    remote = clean_receipt.get("remote_ci", {})
    require(remote.get("subject_published") is True, "SG01 subject is not published")
    require(remote.get("same_commit_checks_observed") is True, "SG01 receipt lacks same-commit CI")
    require(remote.get("existing_pr_head") == revision, "SG01 CI head does not match subject revision")
    require(remote.get("status") == "PASS", "SG01 remote CI is not green")
    runs = remote.get("runs")
    require(isinstance(runs, list) and len(runs) >= 2, "SG01 receipt lacks push and pull-request CI runs")
    require({run.get("event") for run in runs} >= {"push", "pull_request"}, "SG01 CI event coverage drift")
    for run in runs:
        require(isinstance(run.get("run_id"), int) and run["run_id"] > 0, "invalid SG01 CI run id")
        for gate in ("receipt_reduction", "linux_golden", "windows_golden", "verify"):
            require(run.get(gate) == "PASS", f"SG01 CI run {run['run_id']} failed {gate}")


def validate(root: Path = ROOT) -> None:
    audit = json.loads((root / CURRENT_AUDIT).read_text(encoding="utf-8"))
    require(audit.get("schema") == "just-dodge-sg01-baseline-audit-v2", "bad SG01 audit schema")
    require(audit.get("verdict") == "FAIL_BLOCKED_RECONCILIATION_REQUIRED", "SG01 baseline must fail closed")
    require(audit.get("sg01_can_proceed_to_sg02") is False, "SG01 baseline improperly permits SG02")
    require(audit.get("sg02_implementation_blocked") is True, "SG02 implementation block drift")
    require(audit.get("promotion") == "BLOCKED", "promotion boundary drift")
    require(audit.get("human_decision") == "PENDING", "human decision was fabricated")
    expected_stages = {
        "model_prediction": "BLOCKED_INVALID_EVIDENCE",
        "runtime_contact": "BLOCKED_MACHINE",
        "human_promotion": "PENDING",
    }
    require(
        audit.get("evidence_stages") == expected_stages,
        "model/runtime/human evidence stages were conflated",
    )
    runtime = audit.get("runtime_path", {})
    require(runtime.get("playable_runtime_admitted") is False, "blocked runtime path was admitted")
    require(runtime.get("forbidden_fixed_presentation_present") is True, "fixed presentation blocker was hidden")
    require(runtime.get("deleted_dependencies_present") is True, "deleted runtime dependencies were hidden")

    clean_receipt = json.loads((root / CLEAN_RECEIPT).read_text(encoding="utf-8"))
    validate_clean_receipt(clean_receipt, expected_stages)

    historical = json.loads((root / HISTORICAL_AUDIT).read_text(encoding="utf-8"))
    require(historical.get("verdict") == "SUPERSEDED_NOT_CURRENT_AUTHORITY", "historical SG01 receipt still claims current authority")
    require(historical.get("sg01_can_proceed_to_sg02") is False, "historical SG01 receipt still permits SG02")
    require(historical.get("superseded_by") == CURRENT_AUDIT.as_posix(), "historical SG01 supersession drift")

    baseline = json.loads((root / PVP005_BASELINE).read_text(encoding="utf-8"))
    candidate = baseline.get("candidate_packet", {})
    require(baseline.get("authority") == "historical_reachability_only", "historical PVP-005 baseline claims current authority")
    require(baseline.get("current_status_authority") == CLEAN_RECEIPT.as_posix(), "PVP-005 current authority drift")
    require(candidate.get("retired") is True and candidate.get("runtime_promoted") is False, "retired candidate promotion drift")
    require(not (root / candidate["manifest"]).exists(), "retired candidate manifest reappeared")

    documents = {
        relative.as_posix(): (root / relative).read_text(encoding="utf-8")
        for relative in CURRENT_STATUS_FILES
    }
    claims = forbidden_claims(documents)
    require(not claims, "forbidden current claims: " + "; ".join(claims))
    for relative, text in documents.items():
        require(CLEAN_RECEIPT.as_posix() in text, f"current SG01 authority missing from {relative}")

    quarantine = json.loads((root / UNIT2_QUARANTINE).read_text(encoding="utf-8"))
    require(quarantine.get("verdict") == "INVALID_EVIDENCE", "UNIT-2 quarantine verdict drift")
    require(quarantine.get("g4") == "PENDING_HUMAN", "historical UNIT-2 G4 field drift")
    require(quarantine.get("g5") == "BLOCKED_MACHINE", "UNIT-2 runtime-contact block drift")
    failures = validate_quarantined_files(root, quarantine)
    require(not failures, "; ".join(failures))

    retired_assets = json.loads((root / RETIRED_ASSETS).read_text(encoding="utf-8"))
    require(retired_assets.get("schema") == "just-dodge.retired-asset-corpus.v1", "retired asset schema drift")
    require(retired_assets.get("runtime_admissible") is False, "retired asset corpus became runtime-admissible")
    require(retired_assets.get("promotion") == "BLOCKED", "retired asset promotion drift")
    retired_qa = json.loads((root / RETIRED_QA).read_text(encoding="utf-8"))
    require(retired_qa.get("schema") == "just-dodge-retired-qa-corpus-v1", "retired QA schema drift")
    require(retired_qa.get("promotion") == "BLOCKED", "retired QA promotion drift")
    asset_failures = validate_retired_manifest(root, retired_assets)
    qa_failures = validate_retired_manifest(root, retired_qa)
    require(not asset_failures, "; ".join(asset_failures))
    require(not qa_failures, "; ".join(qa_failures))
    asset_paths = {entry["path"] for entry in retired_assets["files"]}
    qa_paths = {entry["path"] for entry in retired_qa["files"]}
    require(not (asset_paths & qa_paths), "retired asset/QA manifests overlap")

    visual = json.loads((root / PVP005_VISUAL).read_text(encoding="utf-8"))
    require(visual.get("status") == "retired_not_current_evidence", "historical visual harness was reactivated")
    require(visual.get("runtime_admissible") is False, "historical visual harness became runtime-admissible")
    require(visual.get("retirement_manifest") == RETIRED_ASSETS.as_posix(), "visual harness retirement authority drift")

    ardy_authorization = json.loads((root / PVP005_ARDY_AUTHORIZATION).read_text(encoding="utf-8"))
    require(
        ardy_authorization.get("status") == "retired_consumed_not_current_authority",
        "consumed ARDY authorization was reactivated",
    )
    require(
        ardy_authorization.get("retirement_manifest") == RETIRED_QA.as_posix(),
        "ARDY authorization retirement authority drift",
    )
    require(ardy_authorization.get("runtime_admission") is False, "retired ARDY output became runtime-admitted")

    print("SG01_EVIDENCE_BOUNDARIES=PASS")
    print("MODEL_PREDICTION=BLOCKED_INVALID_EVIDENCE")
    print("RUNTIME_CONTACT=BLOCKED_MACHINE")
    print("HUMAN_PROMOTION=PENDING")
    print("SG02_IMPLEMENTATION=AUTHORIZED_NEXT_WAVE")
    print(f"RETIRED_CORPUS_FILES={len(asset_paths) + len(qa_paths)}")


if __name__ == "__main__":
    validate()
