#!/usr/bin/env python3
"""Regression tests for the SG01 evidence/canon boundary validator."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("validate_sg01_evidence_boundaries.py")
SPEC = importlib.util.spec_from_file_location("validate_sg01_evidence_boundaries", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Sg01EvidenceBoundaryTests(unittest.TestCase):
    def test_current_repository_boundaries_pass(self) -> None:
        MODULE.validate()

    def test_forbidden_current_claim_is_detected(self) -> None:
        findings = MODULE.forbidden_claims(
            {"status.md": "Interaction-conditioned grab — MACHINE PASS (v13)"}
        )
        self.assertEqual(findings, ["status.md: MACHINE PASS (v13)"])

    def test_quarantine_hash_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sg01-quarantine-test-") as raw:
            root = Path(raw)
            artifact = root / "quarantine" / "bad.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("{}", encoding="utf-8")
            manifest = {
                "quarantined_files": [
                    {
                        "quarantine": "quarantine/bad.json",
                        "sha256": "0" * 64,
                        "size": 2,
                    }
                ]
            }
            failures = MODULE.validate_quarantined_files(root, manifest)
            self.assertEqual(
                failures,
                ["quarantined file hash mismatch: quarantine/bad.json"],
            )

    def test_evidence_stage_schema_cannot_collapse_to_one_pass(self) -> None:
        audit = json.loads((MODULE.ROOT / MODULE.CURRENT_AUDIT).read_text())
        self.assertEqual(
            audit["evidence_stages"],
            {
                "model_prediction": "BLOCKED_INVALID_EVIDENCE",
                "runtime_contact": "BLOCKED_MACHINE",
                "human_promotion": "PENDING",
            },
        )
        self.assertFalse(audit["sg01_can_proceed_to_sg02"])
        self.assertFalse(audit["runtime_path"]["playable_runtime_admitted"])

    def test_sg01_pass_receipt_requires_same_commit_green_ci(self) -> None:
        receipt = json.loads((MODULE.ROOT / MODULE.CLEAN_RECEIPT).read_text())
        expected_stages = {
            "model_prediction": "BLOCKED_INVALID_EVIDENCE",
            "runtime_contact": "BLOCKED_MACHINE",
            "human_promotion": "PENDING",
        }
        MODULE.validate_clean_receipt(receipt, expected_stages)

        receipt["remote_ci"]["same_commit_checks_observed"] = False
        with self.assertRaisesRegex(SystemExit, "lacks same-commit CI"):
            MODULE.validate_clean_receipt(receipt, expected_stages)

    def test_retired_source_hash_mismatch_fails(self) -> None:
        manifest = {
            "source_revision": "a" * 40,
            "files": [
                {
                    "path": "retired.bin",
                    "bytes": 2,
                    "sha256": "0" * 64,
                }
            ],
        }
        with tempfile.TemporaryDirectory(prefix="sg01-retired-test-") as raw:
            with mock.patch.object(MODULE, "git_blob", return_value=b"{}"):
                failures = MODULE.validate_retired_manifest(Path(raw), manifest)
        self.assertEqual(failures, ["retired source hash mismatch: retired.bin"])


if __name__ == "__main__":
    unittest.main()
