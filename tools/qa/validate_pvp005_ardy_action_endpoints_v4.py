#!/usr/bin/env python3
"""Validate endpoint-first ARDY v4 constraints without invoking any generator."""

from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "assets/qa/pvp005_ardy_action_endpoints_v4.json"
GENERATOR = ROOT / "tools/qa/generate_pvp005_ardy_keypose_candidates.py"
SCREEN = ROOT / "tools/qa/screen_pvp005_motion_candidates.py"
ACTIONS = ("strike", "block", "grab")
KEYPOSE_FRAMES = (0, 4, 7, 16, 30, 40, 51)
V4_SCHEMA = "just-dodge-pvp005-ardy-action-endpoints-v4"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def lerp(left: list[float], right: list[float], amount: float) -> list[float]:
    return [a + amount * (b - a) for a, b in zip(left, right, strict=True)]


def constant(path: Path, name: str) -> Any:
    module = ast.parse(path.read_text(encoding="utf-8"))
    for statement in module.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in statement.targets
        ):
            return ast.literal_eval(statement.value)
    raise SystemExit(f"missing constant {name} in {path.relative_to(ROOT)}")


def contiguous(segments: list[dict], final_frame: int) -> None:
    expected = 0
    previous_end = None
    for segment in segments:
        start, end = segment["frames"]
        require(start == expected and end >= start, "non-contiguous schedule")
        if previous_end is not None and "xz_start_m" in segment:
            require(segment["xz_start_m"] == previous_end, "root endpoint discontinuity")
        previous_end = segment.get("xz_end_m")
        expected = end + 1
    require(expected == final_frame + 1, "schedule does not cover horizon")


def sample_root(segments: list[dict], frame: int) -> list[float]:
    for segment in segments:
        start, end = segment["frames"]
        if start <= frame <= end:
            if start == end:
                return list(segment["xz_end_m"])
            amount = (frame - start) / (end - start)
            return lerp(segment["xz_start_m"], segment["xz_end_m"], amount)
    raise AssertionError(frame)


def contact_at(segments: list[dict], frame: int) -> dict:
    return next(segment for segment in segments if segment["frames"][0] <= frame <= segment["frames"][1])


def inside(point: list[float], low: list[float], high: list[float]) -> bool:
    return all(low[axis] <= point[axis] <= high[axis] for axis in range(3))


def main() -> None:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    require(spec.get("schema") == V4_SCHEMA, "bad endpoint-first v4 schema")
    require(spec.get("status") == "design_validated_generation_forbidden", "v4 status drift")
    require(spec.get("authority") == "offline_kinematic_proposal_constraints_only", "ARDY authority drift")
    require(spec.get("generation_authorized") is False, "v4 generation must remain forbidden")
    require(spec.get("generator_accepts_schema") is False, "v4 must not claim generator support")
    require(spec.get("visual_acceptance") is False, "v4 must not claim visual acceptance")
    require(spec.get("playable_proof") is False, "PLAYABLE-PROOF must remain false")
    require("seeds" not in spec and "diffusion_steps" not in spec, "generation controls forbidden in design contract")
    require(V4_SCHEMA not in GENERATOR.read_text(encoding="utf-8"), "current generator unexpectedly accepts endpoint v4")
    require(float(constant(SCREEN, "MAX_CONTACT_FOOT_DRIFT_M")) <= 0.02, "foot-drift screen weakened")
    require(int(constant(SCREEN, "TELL_FRAMES")) >= 8, "Reveal screen weakened")

    w0_info = spec["w0_contract"]
    w0_path = ROOT / w0_info["path"]
    require(sha256(w0_path) == w0_info["sha256"], "W0 contract hash drift")
    w0 = json.loads(w0_path.read_text(encoding="utf-8"))
    weapon = w0["weapon"]
    axis_min = weapon["bounds_min_m"][2]
    axis_max = weapon["bounds_max_m"][2]
    axis_length = axis_max - axis_min
    right_amount = (weapon["right_grip_socket_m"][2] - axis_min) / axis_length
    left_amount = (weapon["left_grip_socket_m"][2] - axis_min) / axis_length
    envelope = w0["canonical_action_envelope_relative_to_actor_root_m"]
    low, high = envelope["min"], envelope["max"]

    ledger_info = spec["failed_iteration_ledger"]
    ledger_path = ROOT / ledger_info["path"]
    require(sha256(ledger_path) == ledger_info["sha256"], "failed-iteration ledger hash drift")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    require(ledger["verdict"] == "fail" and ledger["stop_rule"]["triggered"] is True, "two-failure stop rule drift")
    require(len(ledger["iterations"]) == ledger_info["required_failed_iterations"], "failed-iteration count drift")
    require(all(item["status"] == "failed" for item in ledger["iterations"]), "failed iteration relabeled")

    actions = spec["actions"]
    require(tuple(actions) == ACTIONS, "action set/order drift")
    final_frame = spec["frames"] - 1
    margin = spec["global_thresholds"]["support_polygon_margin_m"]
    single_limit = spec["global_thresholds"]["maximum_single_support_root_distance_m"]
    length_tolerance = spec["global_thresholds"]["maximum_weapon_axis_length_error_m"]
    early_vectors: dict[str, list[float]] = {}
    signatures = set()

    for action in ACTIONS:
        item = actions[action]
        contiguous(item["root_schedule"], final_frame)
        for side in ("left", "right"):
            contiguous(item["contact_schedule"][side], final_frame)
        signatures.add(json.dumps({"root": item["root_schedule"], "contact": item["contact_schedule"]}, sort_keys=True))
        require(all(sample_root(item["root_schedule"], frame) == [0.0, 0.0] for frame in range(8)), f"{action}: first Reveal root drift")

        for frame in range(spec["frames"]):
            root = sample_root(item["root_schedule"], frame)
            anchors = []
            for side in ("left", "right"):
                contact = contact_at(item["contact_schedule"][side], frame)
                mode = contact["mode"]
                require(mode in {"planted_world_anchor", "swing_free", "planted_new_anchor"}, f"{action}/{side}: bad contact mode")
                if mode == "swing_free":
                    require("anchor_xz_m" not in contact, f"{action}/{side}: swing carries anchor")
                else:
                    require("anchor_xz_m" in contact, f"{action}/{side}: planted contact lacks anchor")
                    anchors.append(contact["anchor_xz_m"])
            require(bool(anchors), f"{action}/f{frame}: no support foot")
            if len(anchors) == 1:
                require(distance(root, anchors[0]) <= single_limit, f"{action}/f{frame}: root leaves single support")
            else:
                for axis in range(2):
                    lower = min(anchor[axis] for anchor in anchors) - margin
                    upper = max(anchor[axis] for anchor in anchors) + margin
                    require(lower <= root[axis] <= upper, f"{action}/f{frame}: root leaves support polygon")

        poses = item["keyposes"]
        require(tuple(pose["frame"] for pose in poses) == KEYPOSE_FRAMES, f"{action}: keypose frames drift")
        for pose in poses:
            pommel = pose["weapon_pommel_root_m"]
            tip = pose["weapon_tip_root_m"]
            require(abs(distance(pommel, tip) - axis_length) <= length_tolerance, f"{action}/f{pose['frame']}: weapon length drift")
            require(inside(pommel, low, high) and inside(tip, low, high), f"{action}/f{pose['frame']}: complete weapon leaves W0 envelope")
            primary = lerp(pommel, tip, right_amount)
            secondary = lerp(pommel, tip, left_amount)
            require(abs(distance(primary, secondary) - weapon["grip_socket_separation_m"]) <= 1.0e-8, f"{action}/f{pose['frame']}: derived grip spacing drift")
            if item["weapon_ownership"] == "two_hand":
                require("left_effector_root_m" not in pose, f"{action}: two-hand pose has independent left effector")
                require(inside(primary, low, high) and inside(secondary, low, high), f"{action}: derived grip leaves envelope")
            else:
                effector = pose["left_effector_root_m"]
                require(inside(effector, low, high), f"grab/f{pose['frame']}: left effector leaves envelope")
                require(distance(effector, secondary) >= w0["thresholds"]["minimum_inactive_hand_to_grip_distance_m"], f"grab/f{pose['frame']}: left effector aliases grip")

        reveal = next(pose for pose in poses if pose["frame"] == 7)
        primary = lerp(reveal["weapon_pommel_root_m"], reveal["weapon_tip_root_m"], right_amount)
        partner = lerp(reveal["weapon_pommel_root_m"], reveal["weapon_tip_root_m"], left_amount)
        if item["weapon_ownership"] != "two_hand":
            partner = reveal["left_effector_root_m"]
        early_vectors[action] = primary + partner

    require(len(signatures) == len(ACTIONS), "action-specific root/contact schedules converged")
    minimum = spec["global_thresholds"]["minimum_pairwise_early_keypose_distance_m"]
    for left, right in (("strike", "block"), ("strike", "grab"), ("block", "grab")):
        require(distance(early_vectors[left], early_vectors[right]) >= minimum, f"{left}/{right}: early keyposes insufficiently distinct")

    print(f"PVP005_ARDY_V4_CONTRACT_SHA256={sha256(SPEC)}")
    print("PVP005_ARDY_V4_ARCHITECTURE=PASS_ENDPOINT_FIRST_DESIGN_ONLY")
    print("PVP005_ARDY_V4_GENERATION=FORBIDDEN")
    print("PLAYABLE_PROOF=false")


if __name__ == "__main__":
    main()
