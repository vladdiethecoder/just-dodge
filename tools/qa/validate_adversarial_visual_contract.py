#!/usr/bin/env python3
"""Fail closed when the permanent adversarial visual contract drifts or weakens."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
THRESHOLDS = ROOT / "docs/quality/ADVERSARIAL_VISUAL_THRESHOLDS.v1.json"
CONTRACT = ROOT / "docs/quality/ADVERSARIAL_VISUAL_CONTRACT.md"
VISUAL = ROOT / "assets/qa/pvp005_visual_harness_v1.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    thresholds = json.loads(THRESHOLDS.read_text())
    visual = json.loads(VISUAL.read_text())
    require(CONTRACT.is_file(), "missing permanent adversarial visual contract")
    require(thresholds.get("schema") == "just-dodge-adversarial-visual-thresholds-v1", "bad threshold schema")
    render = thresholds["renderer"]
    require(render["orbit_view_count"] >= 16, "orbit view count weakened")
    require(render["orbit_step_degrees"] <= 22.5, "orbit angular coverage weakened")
    require(render["individual_view_size_px"] >= 2048, "individual view resolution weakened")
    require(render["sheet_size_px"] >= 4096, "structure-sheet resolution weakened")
    require(render["first_person_strip_frames"] >= 8, "first-person strip weakened")
    require(render["human_readability_frames"] >= 6, "human readability window weakened")

    permanent_physical = thresholds["physical"]
    current_physical = visual["thresholds"]
    comparisons = {
        "maximum_planted_foot_drift_m": "max_planted_foot_drift_m",
        "maximum_ground_penetration_m": "max_ground_penetration_m",
        "maximum_socket_position_error_m": "max_sword_socket_position_error_m",
        "maximum_socket_angle_error_degrees": "max_sword_socket_angle_error_degrees",
        "maximum_frozen_packet_evaluation_ms": "max_frozen_packet_decode_ms",
    }
    for permanent, current in comparisons.items():
        require(
            float(current_physical[current]) <= float(permanent_physical[permanent]),
            f"PVP-005 visual threshold weaker than permanent contract: {current}",
        )

    permanent_human = thresholds["human"]
    require(current_physical["minimum_human_judgments_per_action"] >= permanent_human["minimum_judgments_per_action"], "judgment count weakened")
    require(current_physical["minimum_human_accuracy_per_action"] >= permanent_human["minimum_accuracy_per_action"], "human accuracy weakened")
    require(current_physical["maximum_pairwise_confusion"] <= permanent_human["maximum_pairwise_confusion"], "confusion threshold weakened")

    workflow_text = "\n".join(path.read_text() for path in (ROOT / ".github/workflows").glob("*.yml"))
    for check in thresholds["required_checks"]:
        require(f"name: {check}" in workflow_text, f"missing required GitHub check: {check}")
    print("ADVERSARIAL_VISUAL_CONTRACT=PASS_CONFIG_ONLY")


if __name__ == "__main__":
    main()
