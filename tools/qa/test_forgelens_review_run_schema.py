#!/usr/bin/env python3
"""Focused contract tests for the standalone ForgeLens ReviewRun v1 validator."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "tools" / "qa" / "validate_forgelens_review_run.py"
RUNTIME_PATH = REPO_ROOT / "tools" / "asset_review.py"
SCHEMA_PATH = REPO_ROOT / "tools" / "qa" / "forgelens_review_run_v1.schema.json"


def load_module(path: Path, name: str):
    if not path.is_file():
        raise AssertionError(f"module is missing: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def tool_profile_sha256() -> str:
    digest = hashlib.sha256()
    for path in (
        REPO_ROOT / "tools/asset_review.py",
        REPO_ROOT / "tools/asset_review/index.html",
        REPO_ROOT / "tools/asset_review/styles.css",
        REPO_ROOT / "tools/asset_review/app.js",
        REPO_ROOT / "docs/reports/FORGELENS_PHASE_A_READINESS_CONTRACT.json",
    ):
        payload = path.read_bytes()
        label = path.name.encode("utf-8")
        digest.update(struct.pack("<I", len(label)))
        digest.update(label)
        digest.update(struct.pack("<Q", len(payload)))
        digest.update(payload)
    return digest.hexdigest()


def file_identity(path: str, digest: str, *, state: str = "tracked-clean") -> dict:
    return {
        "schema": "forgelens.file/v1",
        "path": path,
        "sha256": digest,
        "bytes": 4096,
        "repositoryState": state,
        "relevantDiffSha256": None if state == "tracked-clean" else "e" * 64,
    }


def review_contract() -> dict:
    return {
        "schema": "just-dodge-forgelens-review-spine-contract-v1",
        "contract_version": 1,
        "workflow_revision": "pvp005-w0-review-workflow/v1",
        "states": [
            "awaiting_evidence",
            "awaiting_human",
            "submitted",
            "pass",
            "fail",
            "superseded",
            "expired",
        ],
        "transitions": {
            "awaiting_evidence": ["awaiting_human", "superseded", "expired"],
            "awaiting_human": ["submitted", "superseded", "expired"],
            "submitted": ["pass", "fail", "superseded", "expired"],
            "pass": [],
            "fail": [],
            "superseded": [],
            "expired": [],
        },
        "append_only": True,
        "human_attestation": {
            "required_for_submitted": True,
            "browser_actor_server_derived": True,
            "known_automation_patterns_rejected": True,
            "self_authorship_rejected": True,
            "blind_observation_must_precede_label_reveal": True,
        },
        "pass_eligibility": {
            "revision_must_be_full_reachable_commit": True,
            "code_and_declared_inputs_must_be_tracked_clean": True,
        },
    }


def refresh_identity(run: dict) -> dict:
    identity_fields = (
        "schema",
        "schemaVersion",
        "contract",
        "contractSha256",
        "createdAt",
        "lineage",
        "cameraInventory",
        "aovInventory",
        "requiredEvidence",
        "sourceAuthors",
    )
    fingerprint = hashlib.sha256(canonical_json_bytes({field: run[field] for field in identity_fields})).hexdigest()
    run["runId"] = fingerprint[:20]
    run["runFingerprintSha256"] = fingerprint
    return run


def clean_review_run() -> dict:
    empty_diff = hashlib.sha256(b"").hexdigest()
    empty_untracked_inventory = hashlib.sha256(b"[]").hexdigest()
    geometry_identity = "9" * 64
    camera_inventory = [
        {"profile": "duel-wide-v1", "revision": "camera-rig-v3", "width": 1920, "height": 1080}
    ]
    aov_inventory = [
        {
            "name": "beauty",
            "cameraProfile": "duel-wide-v1",
            "geometryCompatibilityGroup": "duel-geometry-v1",
        }
    ]
    contract = review_contract()
    produced = {
        **file_identity("qa/evidence/duel-wide-beauty.png", "8" * 64),
        "cameraProfile": "duel-wide-v1",
        "aov": "beauty",
        "kind": "image/png",
        "frame": 7,
        "tick60Hz": 7,
        "physicsTick120Hz": 14,
        "physicsSubstep": 0,
        "uncropped": True,
        "fullFrame": True,
        "width": 1920,
        "height": 1080,
        "captureRect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
        "geometryIdentitySha256": geometry_identity,
    }
    run = {
        "schema": "forgelens.review-run/v1",
        "schemaVersion": 1,
        "contract": contract,
        "contractSha256": hashlib.sha256(canonical_json_bytes(contract)).hexdigest(),
        "createdAt": "2026-07-15T12:00:00Z",
        "lineage": {
            "schema": "forgelens.artifact-lineage/v1",
            "code": {
                "schema": "forgelens.code-identity/v1",
                "revision": "a" * 40,
                "reachable": True,
                "trackedClean": True,
                "toolProfileSha256": tool_profile_sha256(),
                "workingTreeDiffSha256": empty_diff,
                "stagedDiffSha256": empty_diff,
                "untrackedInventorySha256": empty_untracked_inventory,
            },
            "build": file_identity("target/release/just-dodge", "1" * 64),
            "replay": file_identity("qa/replays/match-00.ron", "2" * 64),
            "verifier": file_identity("target/release/m3_match", "3" * 64),
            "truthHash": "d1a3cc1bfb9c2f67",
            "truthVerification": {
                "schema": "forgelens.truth-verification/v1",
                "commandProfile": "m3-match-verify-v1",
                "stdoutSha256": "4" * 64,
                "frames": 343,
                "winner": "Some(Player)",
                "replayHash": "d1a3cc1bfb9c2f67",
                "verdict": "PASS",
            },
            "canonicalPlanPacket": file_identity("qa/plans/match-00.json", "5" * 64),
            "evidenceManifest": file_identity("qa/evidence/manifest.json", "6" * 64),
            "workflowRevision": "pvp005-w0-review-workflow/v1",
            "generation": {
                "provider": file_identity("providers/ardy.json", "a" * 64),
                "checkpoint": file_identity("checkpoints/ardy.bin", "b" * 64),
                "retarget": file_identity("retarget/g1-to-c0.json", "c" * 64),
            },
            "producedArtifactInventory": [produced],
            "geometry": file_identity("assets/fighter.glb", "7" * 64),
            "geometryIdentitySha256": geometry_identity,
        },
        "cameraInventory": camera_inventory,
        "aovInventory": aov_inventory,
        "requiredEvidence": [{"cameraProfile": "duel-wide-v1", "aov": "beauty"}],
        "sourceAuthors": ["asset-author-7"],
        "decisionChainHeadSha256": None,
        "runId": "0" * 20,
        "runFingerprintSha256": "0" * 64,
    }
    return refresh_identity(run)


def git(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=15,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"git {' '.join(arguments)} failed ({completed.returncode}): "
            f"{completed.stderr.decode('utf-8', 'replace')}"
        )
    return completed.stdout


def materialize_clean_git_review_run(root: Path) -> dict:
    run = clean_review_run()
    lineage = run["lineage"]
    identities = [
        lineage["build"],
        lineage["replay"],
        lineage["verifier"],
        lineage["canonicalPlanPacket"],
        lineage["evidenceManifest"],
        lineage["generation"]["provider"],
        lineage["generation"]["checkpoint"],
        lineage["generation"]["retarget"],
        lineage["geometry"],
        *lineage["producedArtifactInventory"],
    ]
    for identity in identities:
        path = root / identity["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"tracked fixture for {identity['path']}\n".encode()
        path.write_bytes(payload)
        identity["sha256"] = hashlib.sha256(payload).hexdigest()
        identity["bytes"] = len(payload)
        identity["repositoryState"] = "tracked-clean"
        identity["relevantDiffSha256"] = None

    git(root, "init", "--quiet")
    git(root, "config", "user.name", "ForgeLens Test")
    git(root, "config", "user.email", "forgelens-test@example.invalid")
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "-m", "fixture")
    code = lineage["code"]
    code["revision"] = git(root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    code["reachable"] = True
    code["trackedClean"] = True
    code["workingTreeDiffSha256"] = hashlib.sha256(
        git(root, "diff", "--binary", "--no-ext-diff")
    ).hexdigest()
    code["stagedDiffSha256"] = hashlib.sha256(
        git(root, "diff", "--cached", "--binary", "--no-ext-diff")
    ).hexdigest()
    code["untrackedInventorySha256"] = hashlib.sha256(canonical_json_bytes([])).hexdigest()
    return refresh_identity(run)


class ReviewRunSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = load_module(MODULE_PATH, "validate_forgelens_review_run")
        cls.runtime = load_module(RUNTIME_PATH, "asset_review_schema_compatibility")

    def test_missing_truth_hash_is_rejected_fail_closed(self) -> None:
        run = clean_review_run()
        del run["lineage"]["truthHash"]

        ok, errors = self.validator.validate_review_run(run)

        self.assertFalse(ok)
        self.assertTrue(any("lineage.truthHash" in error and "required" in error for error in errors), errors)

    def test_fully_populated_clean_commit_run_is_pass_eligible(self) -> None:
        with tempfile.TemporaryDirectory(prefix="forgelens-review-run-") as directory:
            root = Path(directory)
            run = materialize_clean_git_review_run(root)

            ok, errors = self.validator.validate_review_run(run)
            pass_ok, pass_errors = self.validator.validate_pass_eligibility(run, root)

        self.assertTrue(ok, errors)
        self.assertEqual(errors, [])
        self.assertTrue(pass_ok, pass_errors)
        self.assertEqual(pass_errors, [])

    def test_pass_gate_requires_live_repository_evidence(self) -> None:
        run = clean_review_run()

        structural_ok, structural_errors = self.validator.validate_review_run(run)
        pass_ok, pass_errors = self.validator.validate_pass_eligibility(run)

        self.assertTrue(structural_ok, structural_errors)
        self.assertFalse(pass_ok)
        self.assertTrue(any("repository root" in error and "draft-only" in error for error in pass_errors), pass_errors)

    def test_pass_gate_rejects_forged_tool_profile_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="forgelens-review-run-") as directory:
            root = Path(directory)
            run = materialize_clean_git_review_run(root)
            run["lineage"]["code"]["toolProfileSha256"] = "f" * 64
            refresh_identity(run)

            pass_ok, pass_errors = self.validator.validate_pass_eligibility(run, root)

        self.assertFalse(pass_ok)
        self.assertTrue(any("toolProfileSha256" in error for error in pass_errors), pass_errors)

    def test_pass_gate_rejects_self_attested_unreachable_commit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="forgelens-review-run-") as directory:
            root = Path(directory)
            run = materialize_clean_git_review_run(root)
            run["lineage"]["code"]["revision"] = "0" * 40
            refresh_identity(run)

            pass_ok, pass_errors = self.validator.validate_pass_eligibility(run, root)

        self.assertFalse(pass_ok)
        self.assertTrue(any("revision" in error and "repository" in error for error in pass_errors), pass_errors)

    def test_pass_gate_remeasures_declared_tracked_clean_inputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="forgelens-review-run-") as directory:
            root = Path(directory)
            run = materialize_clean_git_review_run(root)
            (root / run["lineage"]["build"]["path"]).write_bytes(b"dirty after declaration\n")

            pass_ok, pass_errors = self.validator.validate_pass_eligibility(run, root)

        self.assertFalse(pass_ok)
        self.assertTrue(any("build" in error and "repository" in error for error in pass_errors), pass_errors)

    def test_dirty_tree_run_is_schema_valid_but_draft_only(self) -> None:
        run = clean_review_run()
        run["lineage"]["code"]["trackedClean"] = False
        run["lineage"]["code"]["workingTreeDiffSha256"] = "d" * 64
        run["lineage"]["build"] = file_identity(
            "target/release/just-dodge", "1" * 64, state="tracked-modified"
        )
        refresh_identity(run)

        draft_ok, draft_errors = self.validator.validate_review_run(run)
        pass_ok, pass_errors = self.validator.validate_pass_eligibility(run)

        self.assertTrue(draft_ok, draft_errors)
        self.assertEqual(draft_errors, [])
        self.assertFalse(pass_ok)
        self.assertTrue(any("draft-only" in error for error in pass_errors), pass_errors)

    def test_pass_gate_rejects_clean_flag_with_nonempty_staged_diff_identity(self) -> None:
        run = clean_review_run()
        run["lineage"]["code"]["stagedDiffSha256"] = "d" * 64
        refresh_identity(run)

        draft_ok, draft_errors = self.validator.validate_review_run(run)
        pass_ok, pass_errors = self.validator.validate_pass_eligibility(run)

        self.assertTrue(draft_ok, draft_errors)
        self.assertFalse(pass_ok)
        self.assertTrue(any("stagedDiffSha256" in error and "draft-only" in error for error in pass_errors), pass_errors)

    def test_untracked_input_is_schema_valid_but_not_pass_eligible(self) -> None:
        run = clean_review_run()
        run["lineage"]["generation"]["provider"] = file_identity(
            "providers/ardy.json", "a" * 64, state="untracked"
        )
        run["lineage"]["code"]["trackedClean"] = False
        refresh_identity(run)

        draft_ok, draft_errors = self.validator.validate_review_run(run)
        pass_ok, pass_errors = self.validator.validate_pass_eligibility(run)

        self.assertTrue(draft_ok, draft_errors)
        self.assertFalse(pass_ok)
        self.assertTrue(any("provider" in error and "tracked-clean" in error for error in pass_errors), pass_errors)

    def test_pass_gate_rejects_quarantined_162_demo_evidence(self) -> None:
        run = clean_review_run()
        run["lineage"]["evidenceManifest"] = file_identity(
            "validation_evidence/quarantine/dynamic-combat-demo-162-invalid-exploratory-20260717/demo_summary.json",
            "6" * 64,
        )
        refresh_identity(run)

        draft_ok, draft_errors = self.validator.validate_review_run(run)
        pass_ok, pass_errors = self.validator.validate_pass_eligibility(run)

        self.assertTrue(draft_ok, draft_errors)
        self.assertFalse(pass_ok)
        self.assertTrue(
            any("invalid-evidence" in error and "quarantined" in error for error in pass_errors),
            pass_errors,
        )

    def test_pass_gate_rejects_mocked_synthetic_evidence(self) -> None:
        for marker_path in (
            "qa/evidence/mocked_vlm_receipt.json",
            "qa/evidence/synthetic_contact_sheet.png",
            "qa/evidence/1x1_probe.png",
        ):
            run = clean_review_run()
            run["lineage"]["producedArtifactInventory"][0]["path"] = marker_path
            refresh_identity(run)

            pass_ok, pass_errors = self.validator.validate_pass_eligibility(run)

            self.assertFalse(pass_ok, marker_path)
            self.assertTrue(
                any("invalid-evidence" in error and "mocked/synthetic" in error for error in pass_errors),
                (marker_path, pass_errors),
            )

    def test_pass_gate_rejects_developer_machine_and_absolute_paths(self) -> None:
        # Absolute paths are already rejected structurally; this exercises
        # structurally-valid repository-relative paths that still carry a
        # developer-machine or mounted-volume marker.
        for bad_path in (
            "gr00t/motionbricks/checkpoints/motionbricks.ckpt",
            "third_party/vdubrov_local/cache/motion.onnx",
        ):
            run = clean_review_run()
            run["lineage"]["build"]["path"] = bad_path
            refresh_identity(run)

            draft_ok, draft_errors = self.validator.validate_review_run(run)
            pass_ok, pass_errors = self.validator.validate_pass_eligibility(run)

            self.assertTrue(draft_ok, (bad_path, draft_errors))
            self.assertFalse(pass_ok, bad_path)
            self.assertTrue(
                any("invalid-evidence" in error and "developer-machine" in error for error in pass_errors),
                (bad_path, pass_errors),
            )

    def test_wrong_version_and_malformed_file_hash_fail_closed(self) -> None:
        wrong_version = clean_review_run()
        wrong_version["schemaVersion"] = 2
        wrong_hash = clean_review_run()
        wrong_hash["lineage"]["build"]["sha256"] = "f" * 63

        version_ok, version_errors = self.validator.validate_review_run(wrong_version)
        hash_ok, hash_errors = self.validator.validate_review_run(wrong_hash)

        self.assertFalse(version_ok)
        self.assertTrue(any("schemaVersion" in error for error in version_errors), version_errors)
        self.assertFalse(hash_ok)
        self.assertTrue(any("lineage.build.sha256" in error for error in hash_errors), hash_errors)

    def test_schema_document_matches_runtime_field_names_and_required_lineage(self) -> None:
        self.assertTrue(SCHEMA_PATH.is_file(), f"schema is missing: {SCHEMA_PATH}")
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        lineage = schema["$defs"]["ArtifactLineage"]

        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 1)
        self.assertEqual(schema["properties"]["schema"]["const"], "forgelens.review-run/v1")
        self.assertEqual(lineage["properties"]["schema"]["const"], "forgelens.artifact-lineage/v1")
        for required in (
            "code",
            "build",
            "replay",
            "truthHash",
            "canonicalPlanPacket",
            "workflowRevision",
            "generation",
            "producedArtifactInventory",
            "geometryIdentitySha256",
        ):
            self.assertIn(required, lineage["required"])
        self.assertIn("decisionChainHeadSha256", schema["required"])
        repository_path = re.compile(schema["$defs"]["RepositoryPath"]["pattern"])
        self.assertIsNotNone(repository_path.fullmatch("qa/evidence/frame.png"))
        for unsafe in ("/absolute", "qa//frame.png", "qa/./frame.png", "qa/../frame.png", "qa/frame.png/", "qa\\frame.png", "qa/\x00frame.png"):
            self.assertIsNone(repository_path.fullmatch(unsafe), unsafe)

    def test_fixture_is_accepted_by_existing_runtime_review_run_validator(self) -> None:
        run = clean_review_run()

        runtime_result = self.runtime.validate_review_run(copy.deepcopy(run))
        standalone_ok, standalone_errors = self.validator.validate_review_run(run)

        self.assertEqual(runtime_result["runId"], run["runId"])
        self.assertTrue(standalone_ok, standalone_errors)

    def test_unknown_fields_and_duplicate_camera_identifiers_are_rejected(self) -> None:
        unknown = clean_review_run()
        unknown["lineage"]["truthHahs"] = unknown["lineage"]["truthHash"]
        duplicate = clean_review_run()
        duplicate["cameraInventory"].append(copy.deepcopy(duplicate["cameraInventory"][0]))

        unknown_ok, unknown_errors = self.validator.validate_review_run(unknown)
        duplicate_ok, duplicate_errors = self.validator.validate_review_run(duplicate)

        self.assertFalse(unknown_ok)
        self.assertTrue(any("unknown field" in error and "truthHahs" in error for error in unknown_errors), unknown_errors)
        self.assertFalse(duplicate_ok)
        self.assertTrue(any("cameraInventory" in error and "unique" in error for error in duplicate_errors), duplicate_errors)

    def test_non_string_unknown_keys_fail_closed_without_raising(self) -> None:
        malformed = clean_review_run()
        malformed["lineage"][7] = "integer-key"
        malformed["lineage"][None] = "null-key"

        ok, errors = self.validator.validate_review_run(malformed)

        self.assertFalse(ok)
        self.assertTrue(errors)

    def test_unhashable_nested_value_fails_closed_without_raising(self) -> None:
        malformed = clean_review_run()
        malformed["lineage"]["build"]["repositoryState"] = {}

        ok, errors = self.validator.validate_review_run(malformed)

        self.assertFalse(ok)
        self.assertTrue(any("lineage.build.repositoryState" in error for error in errors), errors)

    def test_non_finite_contract_extension_is_not_canonical_json(self) -> None:
        malformed = clean_review_run()
        malformed["contract"]["non_finite_extension"] = float("nan")

        ok, errors = self.validator.validate_review_run(malformed)

        self.assertFalse(ok)
        self.assertTrue(any("canonical JSON" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
