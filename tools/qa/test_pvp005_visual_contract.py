#!/usr/bin/env python3
"""Focused unit tests for the PVP-005 visual acceptance contract."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from pvp005_visual_contract import (
    DEFAULT_CONFIG,
    contrast_ratio,
    oklab_distance,
    select_backgrounds,
    validate_config,
)


class VisualContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(DEFAULT_CONFIG.read_text())

    def test_committed_contract_is_complete_and_hash_bound(self) -> None:
        result = validate_config(DEFAULT_CONFIG)
        self.assertEqual(result["background_selection"]["mode"], "paired")

    def test_declared_materials_require_complementary_pair(self) -> None:
        selected = select_backgrounds(self.config)
        self.assertEqual(selected["dark"], "charcoal")
        self.assertEqual(selected["light"], "offwhite")
        scores = {entry["name"]: entry for entry in selected["scores"]}
        self.assertGreaterEqual(scores["charcoal"]["contrasts"]["actor"], 4.5)
        self.assertGreaterEqual(scores["offwhite"]["contrasts"]["weapon"], 4.5)
        self.assertLess(scores["charcoal"]["contrasts"]["weapon"], 4.5)
        self.assertLess(scores["offwhite"]["contrasts"]["actor"], 4.5)

    def test_single_background_is_preferred_when_one_passes_both(self) -> None:
        config = copy.deepcopy(self.config)
        config["background"]["declared_prepass_samples_srgb8"] = {
            "actor": [250, 250, 250],
            "weapon": [230, 230, 230],
        }
        selected = select_backgrounds(config)
        self.assertEqual(selected["mode"], "single")
        self.assertEqual(selected["single"], "charcoal")

    def test_color_metrics_are_symmetric_and_nonzero(self) -> None:
        bronze = [185, 132, 76]
        charcoal = [11, 13, 18]
        self.assertAlmostEqual(contrast_ratio(bronze, charcoal), contrast_ratio(charcoal, bronze))
        self.assertAlmostEqual(oklab_distance(bronze, charcoal), oklab_distance(charcoal, bronze))
        self.assertGreater(oklab_distance(bronze, charcoal), 0.1)

    def test_angle_contract_rejects_drift(self) -> None:
        config = copy.deepcopy(self.config)
        config["orbit"]["azimuth_degrees"][15] = 338.0
        path = Path(self.id().replace(".", "_"))
        try:
            path.write_text(json.dumps(config))
            with self.assertRaises(SystemExit):
                validate_config(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
