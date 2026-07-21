#!/usr/bin/env python3
"""Validate the W0 grip ownership and fixed-camera framing contract without generating motion."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "assets/qa/pvp005_w0_grip_camera_v1.json"
RETIREMENT = ROOT / "docs/provenance/RETIRED_ASSET_CORPUS_20260720.json"
ACTIONS = ("strike", "block", "grab")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sub(a: list[float], b: list[float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum(left * right for left, right in zip(a, b))


def cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def normalized(value: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(dot(value, value))
    require(length > 1.0e-9, "degenerate camera vector")
    return tuple(component / length for component in value)  # type: ignore[return-value]


def corners(low: list[float], high: list[float], offset: list[float]) -> list[list[float]]:
    return [
        [values[axis] + offset[axis] for axis in range(3)]
        for values in itertools.product(*zip(low, high))
    ]


def assert_camera_contains(camera: dict, points: list[list[float]], label: str) -> None:
    eye = camera["eye_m"]
    aim = camera["aim_point_m"]
    forward = normalized(sub(aim, eye))
    right = normalized(cross((0.0, 1.0, 0.0), forward))
    up = cross(forward, right)
    tangent = math.tan(math.radians(camera["vertical_fov_degrees"]) * 0.5)
    width, height = camera["output_px"]
    aspect = width / height
    margin = camera["crop_margin_px"]
    limit_x = 1.0 - 2.0 * margin / width
    limit_y = 1.0 - 2.0 * margin / height
    for index, point in enumerate(points):
        relative = sub(point, eye)
        depth = dot(relative, forward)
        require(camera["near_m"] < depth < camera["far_m"], f"{label} corner {index} depth crop")
        ndc_x = dot(relative, right) / (depth * tangent * aspect)
        ndc_y = dot(relative, up) / (depth * tangent)
        require(abs(ndc_x) <= limit_x and abs(ndc_y) <= limit_y, f"{label} corner {index} projected crop: {(ndc_x, ndc_y)}")


def measured_rigid_bounds(path: Path) -> tuple[list[float], list[float]]:
    payload = path.read_bytes()
    require(len(payload) >= 8, "W0 rigid mesh is truncated")
    vertex_count, index_count = struct.unpack_from("<II", payload)
    require(vertex_count > 0 and index_count > 0 and index_count % 3 == 0, "W0 rigid mesh header malformed")
    positions_bytes = vertex_count * 3 * 4
    require(len(payload) >= 8 + positions_bytes, "W0 rigid positions are truncated")
    values = struct.unpack_from(f"<{vertex_count * 3}f", payload, 8)
    low = [min(values[axis::3]) for axis in range(3)]
    high = [max(values[axis::3]) for axis in range(3)]
    return low, high


def main() -> None:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    require(spec.get("schema") == "just-dodge-pvp005-w0-grip-camera-v1", "unsupported W0 contract")
    require(spec.get("authority") == "presentation_constraint_only_no_motion_generation", "W0 authority drift")
    require(spec.get("generation_enabled") is False, "W0 contract must not enable generation")
    require(spec.get("visual_acceptance") is False, "W0 contract must not claim acceptance")
    require(spec.get("playable_proof") is False, "PLAYABLE-PROOF must remain false")

    weapon = spec["weapon"]
    weapon_path = ROOT / weapon["path"]
    retired = not weapon_path.is_file()
    if retired:
        retirement = json.loads(RETIREMENT.read_text(encoding="utf-8"))
        require(retirement.get("runtime_admissible") is False, "W0 retirement became runtime-admissible")
        retired_hashes = {entry["path"]: entry["sha256"] for entry in retirement["files"]}
        require(retired_hashes.get(weapon["path"]) == weapon["sha256"], "missing W0 retirement hash")
    else:
        require(sha256(weapon_path) == weapon["sha256"], "W0 payload hash drift")
        measured_min, measured_max = measured_rigid_bounds(weapon_path)
        for observed, expected in zip(measured_min, weapon["bounds_min_m"]):
            require(abs(observed - expected) <= 2.0e-4, "W0 minimum bounds drift")
        for observed, expected in zip(measured_max, weapon["bounds_max_m"]):
            require(abs(observed - expected) <= 2.0e-4, "W0 maximum bounds drift")
    right = weapon["right_grip_socket_m"]
    left = weapon["left_grip_socket_m"]
    separation = math.sqrt(sum((a - b) ** 2 for a, b in zip(right, left)))
    require(abs(separation - weapon["grip_socket_separation_m"]) <= 1.0e-9, "W0 grip spacing drift")
    clearance = weapon["minimum_anchor_clearance_m"]
    for name, limits in (("core", weapon["grip_core_z_m"]), ("wrap", weapon["grip_wrap_z_m"])):
        for side, socket in (("left", left), ("right", right)):
            require(
                limits[0] + clearance <= socket[2] <= limits[1] - clearance,
                f"W0 {side} socket leaves {name} with required clearance",
            )

    actions = spec["actions"]
    require(tuple(actions) == ACTIONS, "W0 action set/order drift")
    for action in ("strike", "block"):
        policy = actions[action]
        require(policy["weapon_ownership"] == "two_hand", f"{action} must use two-hand ownership")
        require(policy["required_active_sockets"] == ["right_grip_socket_m", "left_grip_socket_m"], f"{action} active sockets drift")
    grab = actions["grab"]
    require(grab["weapon_ownership"] == "one_hand_right_visible_stow", "Grab ownership drift")
    require(grab["required_active_sockets"] == ["right_grip_socket_m"], "Grab must have one active grip")
    require(grab["left_hand_role"] == "grab_contact_effector_not_a_grip", "Grab left-hand role drift")

    thresholds = spec["thresholds"]
    require(thresholds["maximum_active_grip_position_error_m"] <= 0.01, "grip position threshold weakened")
    require(thresholds["maximum_active_grip_angle_error_degrees"] <= 3.0, "grip angle threshold weakened")
    require(thresholds["maximum_crop_edge_pixels"] == 0, "crop threshold weakened")

    envelope = spec["canonical_action_envelope_relative_to_actor_root_m"]
    margin = thresholds["crop_margin_px"]
    orbit = spec["orbit_camera"] | {"crop_margin_px": margin}
    for azimuth in orbit["azimuth_degrees"]:
        radians = math.radians(azimuth)
        aim = orbit["aim_point_m"]
        orbit["eye_m"] = [
            aim[0] + math.sin(radians) * orbit["radius_m"],
            orbit["eye_height_m"],
            aim[2] + math.cos(radians) * orbit["radius_m"],
        ]
        assert_camera_contains(orbit, corners(envelope["min"], envelope["max"], [0.0, 0.0, 0.0]), f"orbit {azimuth}")

    first_person = spec["first_person_camera"] | {"crop_margin_px": margin}
    require(first_person["preflight_vertical_fov_degrees"] == [60.0, 70.0, 85.0], "first-person FOV preflight drift")
    for vertical_fov in first_person["preflight_vertical_fov_degrees"]:
        camera = first_person | {"vertical_fov_degrees": vertical_fov}
        assert_camera_contains(
            camera,
            corners(envelope["min"], envelope["max"], camera["opponent_root_m"]),
            f"first-person/{vertical_fov}",
        )

    receipt_info = spec["source_failure_receipt"]
    receipt_path = ROOT / receipt_info["path"]
    require(sha256(receipt_path) == receipt_info["sha256"], "source failure receipt hash drift")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    require(receipt["revision"] == receipt_info["revision"] and receipt["pass"] is False, "source receipt no longer describes the bound failure")
    require(all(receipt["actions"][action]["orbit_crop_failures"] > 0 for action in ACTIONS), "source crop falsifier missing")
    require(all(receipt["actions"][action]["left_grip_error_max_m"] > 0.01 for action in ACTIONS), "source grip falsifier missing")

    print(f"PVP005_W0_CONTRACT_SHA256={sha256(SPEC)}")
    print(
        "PVP005_W0_GRIP_CAMERA="
        + ("PASS_RETIRED_BLOCKED" if retired else "PASS_CONTRACT_ONLY")
    )
    print(f"RUNTIME_ADMISSIBLE={'false' if retired else 'unreviewed'}")
    print("PVP005_CANDIDATE_GENERATION=false")
    print("PLAYABLE_PROOF=false")


if __name__ == "__main__":
    main()
