#!/usr/bin/env python3
"""Focused structural tests for SG02 platform receipt/reduction tooling."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RECEIPT = load_module("sg02_receipt", "tools/qa/sg02_cross_platform_receipt.py")
REDUCE = load_module("sg02_reduce", "tools/qa/sg02_cross_platform_reduce.py")
EXPECTED_PATH = ROOT / "tools/qa/sg02_golden_hashes.json"


class CrossPlatformReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected, self.expected_sha256 = RECEIPT.read_expected(EXPECTED_PATH)

    def receipt(self, label: str = "Linux") -> dict[str, object]:
        unsigned: dict[str, object] = {
            "schema": RECEIPT.SCHEMA,
            "source_revision": "0" * 40,
            "platform_label": label,
            "observed_system": "Linux" if label != "Windows" else "Windows",
            "observed_machine": "x86_64",
            "python_version": "3.test",
            "rustc_version": "rustc test",
            "golden_match_sha256": "a" * 64,
            "golden_match_args": ["--print-hashes"],
            "expected_hashes_sha256": self.expected_sha256,
            "scenario_hashes": self.expected,
        }
        if label == "SteamDeck":
            unsigned["steamdeck_attestation"] = {
                "os_release_sha256": "b" * 64,
                "os_id": "steamos",
                "os_variant_id": "steamdeck",
            }
        unsigned["receipt_sha256"] = REDUCE.sha256_bytes(REDUCE.canonical_bytes(unsigned))
        return unsigned

    def test_parser_requires_exact_seven_scenarios(self) -> None:
        output = "\n".join(
            f"golden_match scenario={name} final_truth_hash={truth_hash} runs=100 identical=true"
            for name, truth_hash in self.expected.items()
        )
        self.assertEqual(RECEIPT.parse_hashes(output, set(self.expected)), self.expected)
        with self.assertRaises(ValueError):
            RECEIPT.parse_hashes(output.rsplit("\n", 1)[0], set(self.expected))

    def test_reducer_accepts_valid_receipt_and_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory(prefix="just-dodge-sg02-test-") as temporary:
            path = Path(temporary) / "receipt.json"
            path.write_text(json.dumps(self.receipt()), encoding="utf-8")
            self.assertEqual(
                REDUCE.read_receipt(path, self.expected, self.expected_sha256)["platform_label"],
                "Linux",
            )
            tampered = self.receipt()
            tampered["scenario_hashes"] = dict(self.expected, all_intents="0" * 16)
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaises(ValueError):
                REDUCE.read_receipt(path, self.expected, self.expected_sha256)

    def test_steamdeck_attestation_requires_steamos_marker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="just-dodge-sg02-test-") as temporary:
            path = Path(temporary) / "os-release"
            path.write_text('ID="steamos"\nVARIANT_ID="steamdeck"\n', encoding="utf-8")
            attestation = RECEIPT.steamdeck_attestation(path)
            self.assertEqual(attestation["os_id"], "steamos")
            path.write_text('ID="fedora"\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                RECEIPT.steamdeck_attestation(path)


if __name__ == "__main__":
    unittest.main()
