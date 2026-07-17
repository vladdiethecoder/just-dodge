#!/usr/bin/env python3
"""Focused regression tests for held-out MotionBricks acceptance gates."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "qa"))
import heldout_motion_acceptance as gate
from build_interaction_corpus import build_interaction_tensor, build_variants, heldout_training_condition


CONDITION = {
    "opponent_intent": "Strike",
    "response_intent": "Parry",
    "attack_height": "high",
    "attack_side": "left",
    "contact_timing": "early",
    "target_role": "Weapon",
    "reach_band": "close",
}
TRAINING_CONDITION = {
    "opponent_intent": "Strike",
    "response_intent": "Block",
    "attack_height": "high",
    "attack_side": "center",
    "contact_timing": "nominal",
    "target_role": "Body",
    "reach_band": "medium",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HeldoutMotionAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.candidates = self.root / "candidates"
        self.candidates.mkdir()
        self.training = self.root / "training.json"
        self.cases_path = self.root / "cases.json"
        self.output = self.root / "report.json"
        self.training.write_text(
            json.dumps({"schema": gate.TRAINING_SCHEMA, "conditions": [TRAINING_CONDITION]}),
            encoding="utf-8",
        )
        self.case = {
            "id": "parry_high_left_early",
            "condition": copy.deepcopy(CONDITION),
            "expected_contact_frame": 18,
            "candidate_path": "parry_high_left_early.npz",
            "observer_path": "parry_high_left_early.observer.json",
            "visual_review_path": "parry_high_left_early.visual.json",
        }
        self.thresholds = {
            "max_foot_drift_m": 0.02,
            "max_grip_error_m": 0.01,
            "max_contact_timing_error_frames": 2,
            "max_contact_distance_m": 0.01,
            "minimum_visual_quality_score": 1.0,
            "minimum_visual_confidence": 0.8,
        }
        self.write_bundle()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_bundle(
        self,
        *,
        foot_drift: float = 0.0,
        grip_error: float = 0.0,
        observed_contact_frame: int = 18,
        visual_failure: bool = False,
    ) -> None:
        frames = 64
        positions = np.zeros((frames, 34, 3), dtype=np.float32)
        positions[:, 7] = [-0.2, 0.0, 0.0]
        positions[:, 14] = [0.2, 0.0, 0.0]
        positions[:, 25] = [-0.08, 1.0, 0.0]
        positions[:, 33] = [0.08, 1.0, 0.0]
        positions[8:16, 7, 0] += np.linspace(0.0, foot_drift, 8)
        targets = np.stack((positions[:, 25], positions[:, 33]), axis=1)
        targets[:, 0, 0] += grip_error
        contacts = np.ones((frames, 4), dtype=np.float32)
        candidate = self.candidates / self.case["candidate_path"]
        np.savez(candidate, posed_joints=positions)
        observer = {
            "schema": gate.OBSERVER_SCHEMA,
            "authority": "deterministic_physics_contact_observer",
            "case_id": self.case["id"],
            "candidate_sha256": digest(candidate),
            "physics_run_id": "physics-run-fixture-0001",
            "physics_trace_sha256": "a" * 64,
            "foot_contacts": contacts.tolist(),
            "grip_targets_m": targets.tolist(),
            "contact_events": [{"primary": True, "frame": observed_contact_frame, "distance_m": 0.0}],
        }
        (self.candidates / self.case["observer_path"]).write_text(json.dumps(observer), encoding="utf-8")
        captures = []
        fixture_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAFAAH/e+m+7wAAAABJRU5ErkJggg=="
        )
        for view in ("front", "side"):
            path = self.candidates / f"{view}.png"
            path.write_bytes(fixture_png)
            captures.append(
                {
                    "view": view,
                    "path": path.name,
                    "sha256": digest(path),
                    "resolution_px": [1, 1],
                    "frame_indices": [0, self.case["expected_contact_frame"]],
                }
            )
        answers = [
            {"id": question, "verdict": "yes", "confidence": 0.95}
            for question in gate.REQUIRED_VISUAL_QUESTIONS
        ]
        if visual_failure:
            answers[0]["verdict"] = "no"
        review = {
            "schema": gate.VISUAL_SCHEMA,
            "case_id": self.case["id"],
            "candidate_sha256": digest(candidate),
            "reviewer": {
                "kind": "vlm",
                "independent": True,
                "blinded": True,
                "review_run_id": "review-run-fixture-0001",
                "decision_receipt_sha256": "b" * 64,
            },
            "captures": captures,
            "answers": answers,
        }
        (self.candidates / self.case["visual_review_path"]).write_text(
            json.dumps(review), encoding="utf-8"
        )
        self.cases_path.write_text(
            json.dumps(
                {
                    "schema": gate.CASES_SCHEMA,
                    "thresholds": self.thresholds,
                    "cases": [self.case],
                }
            ),
            encoding="utf-8",
        )

    def evaluate(self) -> dict:
        return gate.evaluate(self.training, self.cases_path, self.candidates)

    def test_accepts_disjoint_condition_with_bound_evidence(self) -> None:
        report = self.evaluate()
        self.assertEqual(report["status"], "pass")
        observed = report["cases"][0]
        self.assertEqual(observed["observed_contact_timing_error_frames"], 0)
        self.assertEqual(observed["visual_quality_score"], 1.0)
        self.assertLessEqual(observed["observed_foot_drift_m"], self.thresholds["max_foot_drift_m"])
        self.assertLessEqual(observed["observed_grip_error_m"], self.thresholds["max_grip_error_m"])

    def test_rejects_condition_present_in_training_manifest(self) -> None:
        self.training.write_text(
            json.dumps({"schema": gate.TRAINING_SCHEMA, "conditions": [CONDITION]}), encoding="utf-8"
        )
        with self.assertRaisesRegex(gate.GateError, "appears in the training manifest"):
            self.evaluate()

    def test_rejects_foot_drift_over_threshold(self) -> None:
        self.write_bundle(foot_drift=0.021)
        with self.assertRaisesRegex(gate.GateError, "foot drift"):
            self.evaluate()

    def test_rejects_grip_error_over_threshold(self) -> None:
        self.write_bundle(grip_error=0.011)
        with self.assertRaisesRegex(gate.GateError, "grip error"):
            self.evaluate()

    def test_rejects_contact_timing_outside_window(self) -> None:
        self.write_bundle(observed_contact_frame=21)
        with self.assertRaisesRegex(gate.GateError, "contact timing error"):
            self.evaluate()

    def test_rejects_missing_contact_or_mutable_thresholds(self) -> None:
        observer_path = self.candidates / self.case["observer_path"]
        observer = json.loads(observer_path.read_text(encoding="utf-8"))
        observer["contact_events"] = []
        observer_path.write_text(json.dumps(observer), encoding="utf-8")
        with self.assertRaisesRegex(gate.GateError, "exactly one primary contact event"):
            self.evaluate()
        self.write_bundle()
        cases = json.loads(self.cases_path.read_text(encoding="utf-8"))
        cases["thresholds"]["max_grip_error_m"] = 0.5
        self.cases_path.write_text(json.dumps(cases), encoding="utf-8")
        with self.assertRaisesRegex(gate.GateError, "immutable admission policy"):
            self.evaluate()

    def test_rejects_visual_quality_or_unbound_review(self) -> None:
        self.write_bundle(visual_failure=True)
        with self.assertRaisesRegex(gate.GateError, "visual quality score"):
            self.evaluate()
        self.write_bundle()
        review_path = self.candidates / self.case["visual_review_path"]
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["candidate_sha256"] = "0" * 64
        review_path.write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaisesRegex(gate.GateError, "does not bind candidate bytes"):
            self.evaluate()
        self.write_bundle()
        review_path = self.candidates / self.case["visual_review_path"]
        review = json.loads(review_path.read_text(encoding="utf-8"))
        capture = self.candidates / "front.png"
        capture.write_bytes(b"not-a-png")
        review["captures"][0]["sha256"] = digest(capture)
        review_path.write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaisesRegex(gate.GateError, "decodable PNG"):
            self.evaluate()

    def test_cli_writes_a_hashable_pass_report(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "qa" / "heldout_motion_acceptance.py"),
                "--training-manifest", str(self.training),
                "--heldout-cases", str(self.cases_path),
                "--candidate-dir", str(self.candidates),
                "--output", str(self.output),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("HELDOUT_MOTION_ACCEPTANCE=PASS", completed.stdout)
        report = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "pass")
        self.assertEqual(len(report["cases"]), 1)

    def test_cli_failure_replaces_stale_pass_report(self) -> None:
        self.output.write_text(json.dumps({"schema": gate.SCHEMA, "status": "pass"}), encoding="utf-8")
        observer_path = self.candidates / self.case["observer_path"]
        observer = json.loads(observer_path.read_text(encoding="utf-8"))
        observer["contact_events"][0]["distance_m"] = 0.5
        observer_path.write_text(json.dumps(observer), encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "qa" / "heldout_motion_acceptance.py"),
                "--training-manifest", str(self.training),
                "--heldout-cases", str(self.cases_path),
                "--candidate-dir", str(self.candidates),
                "--output", str(self.output),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(json.loads(self.output.read_text(encoding="utf-8"))["status"], "fail")

    def test_corpus_projection_records_the_exact_training_condition_axes(self) -> None:
        batch = json.loads((ROOT / "assets" / "data" / "r6k_move_batch.json").read_text())
        move = next(item for item in batch["moves"] if item["id"] == "block_high")
        variant = next(item for item in build_variants(move) if item["id"] == "low_right_late")
        condition = heldout_training_condition(build_interaction_tensor(move, variant))
        self.assertEqual(
            condition,
            {
                "opponent_intent": "Strike",
                "response_intent": "Block",
                "attack_height": "low",
                "attack_side": "right",
                "contact_timing": "late",
                "target_role": "Legs",
                "reach_band": "medium",
            },
        )
        contract = json.loads((ROOT / "assets" / "qa" / "heldout_motion_acceptance_v1.json").read_text())
        training_signatures = {gate.condition_signature(condition, "training")}
        heldout_signatures = {gate.condition_signature(case["condition"], case["id"]) for case in contract["cases"]}
        self.assertFalse(training_signatures & heldout_signatures)

    def test_committed_contract_has_three_distinct_heldout_conditions(self) -> None:
        contract = json.loads((ROOT / "assets" / "qa" / "heldout_motion_acceptance_v1.json").read_text())
        self.assertEqual(contract["schema"], gate.CASES_SCHEMA)
        self.assertEqual(len(contract["cases"]), 3)
        signatures = [gate.condition_signature(case["condition"], case["id"]) for case in contract["cases"]]
        self.assertEqual(len(signatures), len(set(signatures)))
        self.assertEqual(contract["thresholds"]["max_foot_drift_m"], 0.02)
        self.assertEqual(contract["thresholds"]["max_grip_error_m"], 0.01)
        self.assertEqual(contract["thresholds"]["max_contact_timing_error_frames"], 2)
        self.assertEqual(contract["thresholds"]["max_contact_distance_m"], 0.01)
        self.assertEqual(contract["thresholds"]["minimum_visual_quality_score"], 1.0)


if __name__ == "__main__":
    unittest.main()
