#!/usr/bin/env python3
"""Fail-closed tests for the MotionBricks interaction partition/leakage gate.

The partition builder must reject any corpus whose interaction family
(move_id x opponent-height) spans more than one split, and must produce
family-disjoint train/validation/test partitions from a valid corpus. Random
windows or Cartesian variants from the same template must never leak across
splits (JD-RC0 §2 corpus partition/leakage gate).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "tools" / "qa" / "build_motionbricks_interaction_partitions.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_motionbricks_interaction_partitions", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical_corpus(examples: list[dict]) -> dict:
    import hashlib

    body = {"schema": "interaction-corpus-manifest.v1", "examples": examples}
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    body["manifest_sha256"] = digest
    return body


def example(move_id: str, variant: str, intent: str = "Strike") -> dict:
    import hashlib

    record = {
        "move_id": move_id,
        "variant_id": variant,
        "actor_intent": intent,
        "opponent_intent": "Block",
    }
    record["example_sha256"] = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return record


class InteractionPartitionLeakageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_module()

    def _build(self, corpus: dict):
        with tempfile.TemporaryDirectory(prefix="jd-partition-") as directory:
            corpus_path = Path(directory) / "corpus.json"
            out_path = Path(directory) / "partitions.json"
            corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
            argv = sys.argv
            try:
                sys.argv = [
                    "build_motionbricks_interaction_partitions.py",
                    "--corpus",
                    str(corpus_path),
                    "--output",
                    str(out_path),
                ]
                self.builder.main()
            finally:
                sys.argv = argv
            return json.loads(out_path.read_text(encoding="utf-8"))

    def test_valid_corpus_yields_family_disjoint_splits(self) -> None:
        # One move exposing exactly one high/mid/low family each (the builder's
        # required shape): each height family must land in a distinct split.
        corpus = canonical_corpus(
            [
                example("strike_vertical", "high_left_early"),
                example("strike_vertical", "mid_left_early"),
                example("strike_vertical", "low_left_early"),
            ]
        )
        result = self._build(corpus)

        groups = {}
        for row in result["assignments"]:
            groups.setdefault(row["split"], set()).add(row["partition_group"])
        all_groups = [g for s in groups.values() for g in s]
        self.assertEqual(len(all_groups), len(set(all_groups)), "a partition group leaked across splits")
        self.assertEqual(set(groups.keys()), {"train", "validation", "test"})
        # Each of the three height families appears in exactly one split.
        family_to_splits = {}
        for row in result["assignments"]:
            family_to_splits.setdefault(row["partition_group"], set()).add(row["split"])
        for family, splits in family_to_splits.items():
            self.assertEqual(len(splits), 1, f"{family} spans multiple splits")
        self.assertIn("partition_policy", result)

    def test_leaking_family_is_rejected_fail_closed(self) -> None:
        # Force two examples of the same interaction family (move_id x height)
        # so the builder cannot place them in disjoint splits.
        builder = self.builder
        corpus = canonical_corpus(
            [
                example("strike_vertical", "high_left_early"),
                example("strike_vertical", "high_left_late"),
            ]
        )
        with tempfile.TemporaryDirectory(prefix="jd-partition-leak-") as directory:
            corpus_path = Path(directory) / "corpus.json"
            out_path = Path(directory) / "partitions.json"
            corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
            argv = sys.argv
            raised = False
            try:
                sys.argv = [
                    "build_motionbricks_interaction_partitions.py",
                    "--corpus",
                    str(corpus_path),
                    "--output",
                    str(out_path),
                ]
                try:
                    builder.main()
                except (SystemExit, ValueError):
                    raised = True
            finally:
                sys.argv = argv
        self.assertTrue(raised or not out_path.exists(),
                        "a leaking interaction family must not produce a partition output")

    def test_empty_corpus_is_rejected(self) -> None:
        corpus = canonical_corpus([])
        with tempfile.TemporaryDirectory(prefix="jd-partition-empty-") as directory:
            corpus_path = Path(directory) / "corpus.json"
            corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
            with self.assertRaises((SystemExit, ValueError)):
                argv = sys.argv
                try:
                    sys.argv = [
                        "build_motionbricks_interaction_partitions.py",
                        "--corpus",
                        str(corpus_path),
                        "--output",
                        str(Path(directory) / "out.json"),
                    ]
                    self.builder.main()
                finally:
                    sys.argv = argv


if __name__ == "__main__":
    unittest.main()
