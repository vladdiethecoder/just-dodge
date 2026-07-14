#!/usr/bin/env python3
"""Static fail-closed preflight for the post-two-failure ARDY architecture."""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "assets/qa/pvp005_ardy_constraint_architecture_v3.json"
SCREEN = ROOT / "tools/qa/screen_pvp005_motion_candidates.py"
ACTIONS = ("strike", "block", "grab")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def constant(path: Path, name: str) -> object:
    module = ast.parse(path.read_text())
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in statement.targets):
                return ast.literal_eval(statement.value)
    raise SystemExit(f"missing screening constant: {name}")


def contiguous(segments: list[dict[str, object]], final_frame: int) -> bool:
    expected = 0
    for segment in segments:
        start, end = segment["frames"]
        if start != expected or end < start:
            return False
        expected = end + 1
    return expected == final_frame + 1


def distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def main() -> None:
    spec = json.loads(SPEC.read_text())
    require(spec.get("schema") == "just-dodge-pvp005-ardy-constraint-architecture-v3", "bad v3 architecture schema")
    require(spec.get("status") == "superseded_archive_not_runtime_authority", "v3 archive status drift")
    require(spec.get("superseded_by") == "live_ardy_motionbricks_physics_neural_plan_packet_architecture", "v3 supersession drift")
    require(spec.get("generation_authorized") is False, "iteration 3 must remain generation-forbidden")
    require(tuple(spec["actions"]) == ACTIONS, "action set or ordering drift")
    require(constant(SCREEN, "MAX_CONTACT_FOOT_DRIFT_M") <= 0.02, "candidate screen foot-drift threshold weakened")
    require(constant(SCREEN, "TELL_FRAMES") >= 8, "candidate screen Reveal window weakened")

    rules = spec["global_rules"]
    grip = float(rules["two_hand_grip_separation_m"])
    tolerance = float(rules["two_hand_grip_tolerance_m"])
    final_frame = int(spec["frames"]) - 1
    frame7_vectors: dict[str, list[float]] = {}
    for action in ACTIONS:
        item = spec["actions"][action]
        require(contiguous(item["root_schedule"], final_frame), f"{action}: non-contiguous root schedule")
        for side in ("left", "right"):
            require(contiguous(item["contact_schedule"][side], final_frame), f"{action}/{side}: non-contiguous contact schedule")
        first_root = item["root_schedule"][0]
        require(first_root["frames"][0] == 0 and first_root["frames"][1] >= 7, f"{action}: Reveal root segment incomplete")
        require(first_root["xz_start_m"] == first_root["xz_end_m"], f"{action}: Reveal root is not stationary")
        poses = item["early_hand_keyposes_m"]
        require([pose["frame"] for pose in poses] == [0, 4, 7], f"{action}: early keypose frames drift")
        if action in ("strike", "block"):
            for pose in poses:
                separation = distance(pose["right"], pose["left"])
                require(abs(separation - grip) <= tolerance, f"{action}/f{pose['frame']}: grip separation {separation:.6f} m")
        else:
            require(distance(poses[-1]["right"], poses[-1]["left"]) >= 0.5, "grab: early reach is not visually separated")
        frame7_vectors[action] = poses[-1]["right"] + poses[-1]["left"]

    for left, right in (("strike", "block"), ("strike", "grab"), ("block", "grab")):
        require(distance(frame7_vectors[left], frame7_vectors[right]) >= 0.12, f"{left}/{right}: analytic early-pose separation too small")
    print("PVP005_ARDY_V3_ARCHITECTURE=PASS_SUPERSEDED_ARCHIVE_ONLY")
    print("PVP005_ARDY_ITERATION_3_GENERATION=FORBIDDEN")


if __name__ == "__main__":
    main()
