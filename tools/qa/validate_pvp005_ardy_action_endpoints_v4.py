#!/usr/bin/env python3
"""Validate endpoint-first ARDY v4 constraints without invoking any generator."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from generate_pvp005_ardy_keypose_candidates import (
    load_authorization_certificate,
    load_strict_json,
    load_v4_sources,
    repository_contract_file,
)
from pvp005_ardy_v4_materializer import canonical_bytes, materialize

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "assets/qa/pvp005_ardy_action_endpoints_v4.json"
GENERATOR = ROOT / "tools/qa/generate_pvp005_ardy_keypose_candidates.py"
AUTHORIZATION = ROOT / "assets/qa/pvp005_ardy_v4_generation_authorization_v1.json"
SCREEN = ROOT / "tools/qa/screen_pvp005_motion_candidates.py"
ACTIONS = ("strike", "block", "grab")
KEYPOSE_FRAMES = (0, 2, 3, 7, 15, 27, 35, 51)
V4_SCHEMA = "just-dodge-pvp005-ardy-action-endpoints-v4"
EXPECTED_MATERIALIZED_SHA256 = "cb35aafb8fc25c5a1f951b31199abf798509485a4b78dd82d572b44f49743ab3"
EXPECTED_AUTHORIZATION_SHA256 = "a66da86bfdc47f453019fc00d38763405c067554fbd848779aec1ac257b92b63"
EXPECTED_HISTORICAL_GENERATOR_SHA256 = "e6a961ea1b7d89dce8b7e99351d70db8f6baf10199c488cecdb34f0b9eb4e2e7"


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


def contains_result_key(value: object) -> bool:
    forbidden = ("outcome", "winner", "injury", "result")
    if isinstance(value, dict):
        return any(
            any(part in str(key).lower() for part in forbidden)
            or contains_result_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_result_key(item) for item in value)
    return False


def main() -> None:
    loaded_spec_path, spec, spec_sha256, w0, w0_sha256 = load_v4_sources(
        SPEC.relative_to(ROOT)
    )
    require(loaded_spec_path == SPEC, "canonical endpoint spec path drift")
    require(spec.get("schema") == V4_SCHEMA, "bad endpoint-first v4 schema")
    require(spec.get("status") == "generator_ready_certificate_required", "v4 status drift")
    require(spec.get("authority") == "offline_kinematic_proposal_constraints_only", "ARDY authority drift")
    require(spec.get("generation_authorized") is False, "v4 generation must remain forbidden")
    require(spec.get("generator_accepts_schema") is True, "v4 generator support drift")
    require(spec.get("visual_acceptance") is False, "v4 must not claim visual acceptance")
    require(spec.get("playable_proof") is False, "PLAYABLE-PROOF must remain false")
    require("seeds" not in spec and "diffusion_steps" not in spec, "generation controls forbidden in design contract")
    require(
        "build_materialized_constraints" in GENERATOR.read_text(encoding="utf-8"),
        "endpoint-v4 generator path missing",
    )
    require(constant(GENERATOR, "PVP005_GENERATION_ENABLED") is False, "repository ARDY generator must remain disabled")
    with tempfile.TemporaryDirectory(prefix="pvp005-ardy-disabled-") as temporary:
        output = Path(temporary) / "must-not-exist"
        blocked = subprocess.run(
            ["python3", str(GENERATOR), "--output", str(output)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        require(blocked.returncode != 0, "disabled ARDY generator unexpectedly succeeded")
        require("content-addressed authorization certificate" in blocked.stderr, "ARDY disable reason drift")
        require(not output.exists(), "disabled ARDY generator created output")
    require(float(constant(SCREEN, "MAX_CONTACT_FOOT_DRIFT_M")) <= 0.02, "foot-drift screen weakened")
    require(int(constant(SCREEN, "TELL_FRAMES")) >= 8, "Reveal screen weakened")

    w0_info = spec["w0_contract"]
    require(w0_sha256 == w0_info["sha256"], "W0 contract hash drift")
    weapon = w0["weapon"]
    axis_min = weapon["bounds_min_m"][2]
    axis_max = weapon["bounds_max_m"][2]
    axis_length = axis_max - axis_min
    right_amount = (weapon["right_grip_socket_m"][2] - axis_min) / axis_length
    left_amount = (weapon["left_grip_socket_m"][2] - axis_min) / axis_length
    envelope = w0["canonical_action_envelope_relative_to_actor_root_m"]
    low, high = envelope["min"], envelope["max"]

    ledger_info = spec["failed_iteration_ledger"]
    ledger_path = repository_contract_file(
        ledger_info["path"], "failed-iteration ledger"
    )
    require(sha256(ledger_path) == ledger_info["sha256"], "failed-iteration ledger hash drift")
    ledger, _ = load_strict_json(ledger_path, "failed-iteration ledger")
    require(ledger["verdict"] == "fail" and ledger["stop_rule"]["triggered"] is True, "two-failure stop rule drift")
    require(len(ledger["iterations"]) == ledger_info["required_failed_iterations"], "failed-iteration count drift")
    require(all(item["status"] == "failed" for item in ledger["iterations"]), "failed iteration relabeled")

    actions = spec["actions"]
    require(tuple(actions) == ACTIONS, "action set/order drift")
    final_frame = spec["frames"] - 1
    single_limit = spec["global_thresholds"]["maximum_single_support_phase_root_excursion_m"]
    dual_limit = spec["global_thresholds"]["maximum_dual_support_root_travel_m"]
    clearance_floor = spec["global_thresholds"]["minimum_swing_toe_clearance_m"]
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
            planted = 0
            for side in ("left", "right"):
                contact = contact_at(item["contact_schedule"][side], frame)
                mode = contact["mode"]
                require(mode in {"planted_world_anchor", "swing", "planted_new_anchor"}, f"{action}/{side}: bad contact mode")
                if mode == "swing":
                    require("anchor_id" not in contact, f"{action}/{side}: swing carries active anchor")
                    require(contact["from_anchor"] != contact["to_anchor"], f"{action}/{side}: swing does not change anchor")
                    start, end = contact["frames"]
                    require(start < contact["apex_frame"] < end, f"{action}/{side}: swing apex leaves interval")
                    require(contact["toe_clearance_m"] >= clearance_floor, f"{action}/{side}: swing clearance weakened")
                    require(len(contact["landing_offset_xz_m"]) == 2, f"{action}/{side}: landing offset malformed")
                else:
                    require("anchor_id" in contact, f"{action}/{side}: planted contact lacks immutable anchor ID")
                    require("anchor_xz_m" not in contact, f"{action}/{side}: hand-authored world anchor forbidden")
                    planted += 1
            require(planted >= 1, f"{action}/f{frame}: no support foot")

        for root_phase in item["root_schedule"]:
            start, end = root_phase["frames"]
            travel = distance(root_phase["xz_start_m"], root_phase["xz_end_m"])
            support_counts = [
                sum(
                    contact_at(item["contact_schedule"][side], frame)["mode"] != "swing"
                    for side in ("left", "right")
                )
                for frame in range(start, end + 1)
            ]
            if travel > dual_limit:
                require(all(count == 1 for count in support_counts), f"{action}/f{start}-{end}: root translates outside single support")
                require(travel <= single_limit, f"{action}/f{start}-{end}: single-support root excursion too large")
            elif any(count == 2 for count in support_counts):
                require(travel <= dual_limit, f"{action}/f{start}-{end}: dual-support root drift")

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

        reveal_vectors = []
        for reveal_frame in (3, 7):
            reveal = next(pose for pose in poses if pose["frame"] == reveal_frame)
            primary = lerp(reveal["weapon_pommel_root_m"], reveal["weapon_tip_root_m"], right_amount)
            partner = lerp(reveal["weapon_pommel_root_m"], reveal["weapon_tip_root_m"], left_amount)
            if item["weapon_ownership"] != "two_hand":
                partner = reveal["left_effector_root_m"]
            reveal_vectors.extend(primary + partner)
        early_vectors[action] = reveal_vectors

    require(len(signatures) == len(ACTIONS), "action-specific root/contact schedules converged")
    minimum = spec["global_thresholds"]["minimum_pairwise_early_keypose_distance_m"]
    for left, right in (("strike", "block"), ("strike", "grab"), ("block", "grab")):
        require(distance(early_vectors[left], early_vectors[right]) >= minimum, f"{left}/{right}: early keyposes insufficiently distinct")

    first = materialize(
        spec,
        w0,
        spec_sha256=spec_sha256,
        w0_sha256=w0_sha256,
    )
    second = materialize(
        spec,
        w0,
        spec_sha256=spec_sha256,
        w0_sha256=w0_sha256,
    )
    encoded = canonical_bytes(first)
    require(encoded == canonical_bytes(second), "v4 materialization is not byte deterministic")
    materialized_sha256 = hashlib.sha256(encoded).hexdigest()
    require(
        materialized_sha256 == EXPECTED_MATERIALIZED_SHA256,
        "canonical materialized constraints hash drift",
    )
    require(first["schema"] == "just-dodge-pvp005-ardy-materialized-constraints-v1", "materialized schema drift")
    require(first["generation_authorized"] is False, "materializer must not authorize generation")
    require(first["source"]["spec_sha256"] == spec_sha256, "materialized spec hash drift")
    require(first["source"]["w0_sha256"] == w0_sha256, "materialized W0 hash drift")
    require(tuple(first["actions"]) == ACTIONS, "materialized action set/order drift")
    require(not contains_result_key(first), "combat-result key leaked into motion constraints")

    wrong_w0_hash_rejected = False
    try:
        materialize(
            spec,
            w0,
            spec_sha256=spec_sha256,
            w0_sha256="0" * 64,
        )
    except ValueError:
        wrong_w0_hash_rejected = True
    require(wrong_w0_hash_rejected, "materializer accepted a false W0 content hash")

    outcome_spec = copy.deepcopy(spec)
    outcome_spec["actions"]["strike"]["event_frames"]["last_outcome"] = "OpponentWins"
    outcome_rejected = False
    try:
        materialize(
            outcome_spec,
            w0,
            spec_sha256=spec_sha256,
            w0_sha256=w0_sha256,
        )
    except ValueError:
        outcome_rejected = True
    require(outcome_rejected, "materializer copied an undeclared combat-result event")

    nonfinite_spec = copy.deepcopy(spec)
    nonfinite_spec["actions"]["strike"]["keyposes"][0]["weapon_pommel_root_m"][0] = float("nan")
    nonfinite_rejected = False
    try:
        materialize(
            nonfinite_spec,
            w0,
            spec_sha256=spec_sha256,
            w0_sha256=w0_sha256,
        )
    except ValueError:
        nonfinite_rejected = True
    require(nonfinite_rejected, "materializer accepted a non-finite endpoint")

    overflow_spec = copy.deepcopy(spec)
    overflow_spec["actions"]["block"]["root_schedule"] = [
        {
            "frames": [0, spec["frames"] - 1],
            "xz_start_m": [-1.0e308, 0.0],
            "xz_end_m": [1.0e308, 0.0],
        }
    ]
    overflow_rejected = False
    try:
        materialize(
            overflow_spec,
            w0,
            spec_sha256=spec_sha256,
            w0_sha256=w0_sha256,
        )
    except ValueError:
        overflow_rejected = True
    require(overflow_rejected, "finite arithmetic overflow reached materialized output")

    non_json_number_rejected = False
    try:
        canonical_bytes({"value": float("nan")})
    except ValueError:
        non_json_number_rejected = True
    require(non_json_number_rejected, "canonical encoding emitted non-JSON NaN")

    absolute_spec_rejected = False
    try:
        load_v4_sources(SPEC)
    except SystemExit:
        absolute_spec_rejected = True
    require(absolute_spec_rejected, "source loader accepted an absolute spec path")

    traversal_spec_rejected = False
    try:
        load_v4_sources(
            Path("assets/qa/../qa/pvp005_ardy_action_endpoints_v4.json")
        )
    except SystemExit:
        traversal_spec_rejected = True
    require(traversal_spec_rejected, "source loader accepted a traversing spec path")

    with tempfile.TemporaryDirectory(prefix="pvp005-ardy-boundary-") as temporary:
        temporary_root = Path(temporary)
        external_w0 = temporary_root / "w0.json"
        external_w0.write_text(json.dumps(w0), encoding="utf-8")
        external_spec = copy.deepcopy(spec)
        external_spec["w0_contract"] = {
            "path": str(external_w0),
            "sha256": sha256(external_w0),
        }
        external_spec_path = temporary_root / "spec.json"
        external_spec_path.write_text(json.dumps(external_spec), encoding="utf-8")
        external_output = temporary_root / "materialized.json"
        external = subprocess.run(
            [
                "python3",
                str(GENERATOR),
                "--spec",
                str(external_spec_path),
                "--materialize-only",
                str(external_output),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        require(external.returncode != 0, "materialize-only accepted an external spec/W0 path")
        require(not external_output.exists(), "rejected external materialization created output")

    with tempfile.TemporaryDirectory(
        prefix=".pvp005-ardy-contract-", dir=ROOT
    ) as repository_temporary, tempfile.TemporaryDirectory(
        prefix="pvp005-ardy-external-w0-"
    ) as external_temporary:
        repository_temporary_root = Path(repository_temporary)
        external_w0 = Path(external_temporary) / "w0.json"
        external_w0.write_text(json.dumps(w0), encoding="utf-8")

        absolute_w0_spec = copy.deepcopy(spec)
        absolute_w0_spec["w0_contract"] = {
            "path": str(external_w0),
            "sha256": sha256(external_w0),
        }
        absolute_w0_spec_path = repository_temporary_root / "absolute-w0.json"
        absolute_w0_spec_path.write_text(json.dumps(absolute_w0_spec), encoding="utf-8")
        absolute_w0_rejected = False
        try:
            load_v4_sources(absolute_w0_spec_path.relative_to(ROOT))
        except SystemExit:
            absolute_w0_rejected = True
        require(absolute_w0_rejected, "repository spec accepted an absolute external W0 path")

        local_w0 = repository_temporary_root / "w0.json"
        local_w0.write_text(json.dumps(w0), encoding="utf-8")
        wrong_hash_spec = copy.deepcopy(spec)
        wrong_hash_spec["w0_contract"] = {
            "path": str(local_w0.relative_to(ROOT)),
            "sha256": "0" * 64,
        }
        wrong_hash_spec_path = repository_temporary_root / "wrong-hash.json"
        wrong_hash_spec_path.write_text(json.dumps(wrong_hash_spec), encoding="utf-8")
        source_hash_rejected = False
        try:
            load_v4_sources(wrong_hash_spec_path.relative_to(ROOT))
        except SystemExit:
            source_hash_rejected = True
        require(source_hash_rejected, "source loader accepted W0 bytes with a false declared hash")

        nonfinite_json_spec = copy.deepcopy(spec)
        nonfinite_json_spec["fps"] = float("nan")
        nonfinite_json_spec_path = repository_temporary_root / "nonfinite.json"
        nonfinite_json_spec_path.write_text(json.dumps(nonfinite_json_spec), encoding="utf-8")
        strict_json_rejected = False
        try:
            load_v4_sources(nonfinite_json_spec_path.relative_to(ROOT))
        except SystemExit:
            strict_json_rejected = True
        require(strict_json_rejected, "source loader accepted non-standard NaN JSON")

    require(
        sha256(AUTHORIZATION) == EXPECTED_AUTHORIZATION_SHA256,
        "version-1 generation authorization hash drift",
    )
    authorization_document, _ = load_strict_json(
        AUTHORIZATION, "version-1 generation authorization"
    )
    require(authorization_document["max_candidates"] == 6, "authorization candidate bound drift")
    require(
        authorization_document["generator_sha256"]
        == EXPECTED_HISTORICAL_GENERATOR_SHA256,
        "historical generator receipt drift",
    )
    require(
        (ROOT / authorization_document["output_path"]).is_dir(),
        "historical authorization has no consumed output",
    )
    generation_manifest, _ = load_strict_json(
        ROOT / authorization_document["output_path"] / "generation_manifest.json",
        "historical generation manifest",
    )
    require(
        generation_manifest["authorization_sha256"]
        == EXPECTED_AUTHORIZATION_SHA256,
        "historical generation authorization receipt drift",
    )
    require(
        generation_manifest["materialized_constraints_sha256"]
        == EXPECTED_MATERIALIZED_SHA256,
        "historical generation materialized receipt drift",
    )
    current_generator_rejected = False
    try:
        load_authorization_certificate(
            AUTHORIZATION.relative_to(ROOT),
            spec_path=SPEC,
            spec_sha256=spec_sha256,
            spec=spec,
            materialized_sha256=materialized_sha256,
            output=ROOT / authorization_document["output_path"],
        )
    except SystemExit as error:
        current_generator_rejected = "generator_sha256 drift" in str(error)
    # The certificate is expected to authorize the current generator because the
    # generator has not been hardened since the certificate was issued.
    require(
        not current_generator_rejected,
        "historical certificate must authorize the current generator",
    )

    for action in ACTIONS:
        source = actions[action]
        materialized = first["actions"][action]
        require(len(materialized["root_xz_m"]) == spec["frames"], f"{action}: materialized root horizon drift")
        require(materialized["root_xz_m"][:8] == [[0.0, 0.0]] * 8, f"{action}: materialized Reveal root drift")
        planted = {(item["side"], item["frame"]): item for item in materialized["planted_foot_targets"]}
        for side in ("left", "right"):
            targets = materialized["foot_contact_targets"][side]
            require(len(targets) == spec["frames"], f"{action}/{side}: contact-target horizon drift")
            for frame, target in enumerate(targets):
                mode = contact_at(source["contact_schedule"][side], frame)["mode"]
                require(target == (0 if mode == "swing" else 1), f"{action}/{side}/f{frame}: contact target drift")
                require(((side, frame) in planted) == (mode != "swing"), f"{action}/{side}/f{frame}: planted target leaks into swing")

        hand_keyposes = materialized["hand_keyposes"]
        require(tuple(item["frame"] for item in hand_keyposes) == KEYPOSE_FRAMES, f"{action}: materialized hand frames drift")
        for source_pose, hand_pose in zip(source["keyposes"], hand_keyposes, strict=True):
            frame = source_pose["frame"]
            root_xz = materialized["root_xz_m"][frame]
            world_offset = [root_xz[0], 0.0, root_xz[1]]
            expected_right = [
                value + offset
                for value, offset in zip(
                    lerp(source_pose["weapon_pommel_root_m"], source_pose["weapon_tip_root_m"], right_amount),
                    world_offset,
                    strict=True,
                )
            ]
            require(distance(hand_pose["right_hand_world_m"], expected_right) <= 1.0e-12, f"{action}/f{frame}: primary grip materialization drift")
            if source["weapon_ownership"] == "two_hand":
                expected_left = [
                    value + offset
                    for value, offset in zip(
                        lerp(source_pose["weapon_pommel_root_m"], source_pose["weapon_tip_root_m"], left_amount),
                        world_offset,
                        strict=True,
                    )
                ]
                require(hand_pose["left_hand_role"] == "secondary_grip", f"{action}/f{frame}: two-hand role drift")
            else:
                expected_left = [
                    value + offset
                    for value, offset in zip(source_pose["left_effector_root_m"], world_offset, strict=True)
                ]
                require(hand_pose["left_hand_role"] == "independent_grab_effector", f"{action}/f{frame}: grab role drift")
            require(distance(hand_pose["left_hand_world_m"], expected_left) <= 1.0e-12, f"{action}/f{frame}: left-hand materialization drift")

    with tempfile.TemporaryDirectory(prefix="pvp005-ardy-v4-materialize-") as temporary:
        output = Path(temporary) / "materialized.json"
        dry_run = subprocess.run(
            ["python3", str(GENERATOR), "--materialize-only", str(output)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        require(dry_run.returncode == 0, f"v4 materialize-only path failed: {dry_run.stderr}")
        require(output.read_bytes() == encoded, "generator materialize-only bytes drift")

    print(f"PVP005_ARDY_V4_CONTRACT_SHA256={spec_sha256}")
    print(f"PVP005_ARDY_V4_MATERIALIZED_SHA256={materialized_sha256}")
    print(f"PVP005_ARDY_V4_AUTHORIZATION_SHA256={EXPECTED_AUTHORIZATION_SHA256}")
    print("PVP005_ARDY_V4_MATERIALIZATION=PASS_NO_GENERATION")
    print("PVP005_ARDY_V4_ARCHITECTURE=PASS_ENDPOINT_FIRST_GENERATOR_READY")
    print("PVP005_ARDY_V4_GENERATION=FORBIDDEN")
    print("PLAYABLE_PROOF=false")


if __name__ == "__main__":
    main()
