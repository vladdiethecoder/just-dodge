#!/usr/bin/env python3
"""Reduce SG02 platform receipts into one fail-closed parity verdict."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

RECEIPT_SCHEMA = "just-dodge-sg02-platform-receipt-v1"
EXPECTED_SCHEMA = "just-dodge-sg02-golden-hashes-v1"
VALID_LABELS = {"Linux", "Windows", "SteamDeck"}
PLATFORM_SYSTEM = {"Linux": "Linux", "Windows": "Windows", "SteamDeck": "Linux"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def read_expected(path: Path) -> tuple[dict[str, str], str]:
    document = json.loads(path.read_bytes())
    if document.get("schema") != EXPECTED_SCHEMA:
        raise ValueError(f"unsupported expected-hash schema: {path}")
    scenarios = document.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios:
        raise ValueError("expected scenarios must be a nonempty object")
    if not all(
        isinstance(name, str) and isinstance(value, str) and re.fullmatch(r"[0-9a-f]{16}", value)
        for name, value in scenarios.items()
    ):
        raise ValueError("expected scenarios contain invalid truth hashes")
    return scenarios, sha256_bytes(canonical_bytes(document))


def read_receipt(path: Path, expected: dict[str, str], expected_sha256: str) -> dict[str, Any]:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise ValueError(f"{path}: unsupported receipt schema")
    label = receipt.get("platform_label")
    if label not in VALID_LABELS:
        raise ValueError(f"{path}: unsupported platform label")
    if receipt.get("observed_system") != PLATFORM_SYSTEM[label]:
        raise ValueError(f"{path}: observed system does not match platform label")
    if receipt.get("golden_match_args") != ["--print-hashes"]:
        raise ValueError(f"{path}: unexpected golden_match arguments")
    if not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("golden_match_sha256", ""))):
        raise ValueError(f"{path}: invalid golden_match digest")
    if not isinstance(receipt.get("rustc_version"), str) or not receipt["rustc_version"].startswith(
        "rustc "
    ):
        raise ValueError(f"{path}: missing rustc version")
    if receipt.get("expected_hashes_sha256") != expected_sha256:
        raise ValueError(f"{path}: expected-hash file digest mismatch")
    if receipt.get("scenario_hashes") != expected:
        raise ValueError(f"{path}: scenario hashes do not match expected baseline")
    revision = receipt.get("source_revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError(f"{path}: invalid source revision")
    receipt_sha256 = receipt.get("receipt_sha256")
    if not isinstance(receipt_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt_sha256):
        raise ValueError(f"{path}: invalid receipt digest")
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256")
    if sha256_bytes(canonical_bytes(unsigned)) != receipt_sha256:
        raise ValueError(f"{path}: receipt digest mismatch")
    if label == "SteamDeck":
        attestation = receipt.get("steamdeck_attestation")
        if not isinstance(attestation, dict) or not re.fullmatch(
            r"[0-9a-f]{64}", str(attestation.get("os_release_sha256", ""))
        ):
            raise ValueError(f"{path}: missing Steam Deck attestation")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", required=True, type=Path)
    parser.add_argument("--receipt", required=True, action="append", type=Path)
    parser.add_argument("--require", required=True, action="append", choices=sorted(VALID_LABELS))
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    expected, expected_sha256 = read_expected(args.expected)
    required = set(args.require)
    receipts = [read_receipt(path, expected, expected_sha256) for path in args.receipt]
    by_label = {receipt["platform_label"]: receipt for receipt in receipts}
    if len(by_label) != len(receipts):
        parser.error("duplicate platform receipt")
    missing = required - set(by_label)
    if missing:
        parser.error(f"missing required platform receipts: {sorted(missing)}")
    revisions = {receipt["source_revision"] for receipt in receipts}
    if len(revisions) != 1:
        parser.error(f"source revision mismatch: {sorted(revisions)}")

    report = {
        "schema": "just-dodge-sg02-cross-platform-parity-v1",
        "status": "pass",
        "source_revision": revisions.pop(),
        "required_platforms": sorted(required),
        "receipt_digests": {label: by_label[label]["receipt_sha256"] for label in sorted(by_label)},
        "scenario_hashes": expected,
    }
    report["report_sha256"] = sha256_bytes(canonical_bytes(report))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(
        "SG02_CROSS_PLATFORM_PARITY=PASS "
        f"platforms={','.join(sorted(required))} scenarios={len(expected)} "
        f"report_sha256={report['report_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
