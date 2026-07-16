#!/usr/bin/env python3
"""Materialize endpoint-first ARDY v4 design data without running a model.

The output is a deterministic, content-addressed proposal-constraint document.
It contains no combat outcomes and does not authorize neural generation.
"""

from __future__ import annotations

import json
import math
from typing import Any, cast

SPEC_SCHEMA = "just-dodge-pvp005-ardy-action-endpoints-v4"
W0_SCHEMA = "just-dodge-pvp005-w0-grip-camera-v1"
OUTPUT_SCHEMA = "just-dodge-pvp005-ardy-materialized-constraints-v1"
ACTIONS = ("strike", "block", "grab")
SIDES = ("left", "right")
FORBIDDEN_RESULT_KEY_PARTS = ("outcome", "winner", "injury", "result")
EVENT_FRAME_SCHEMA = {
    "strike": {"weapon_contact_proposal": "frame"},
    "block": {"guard_window": "interval"},
    "grab": {"left_hand_contact_proposal": "frame"},
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_finite_numbers(value: object, path: str = "$") -> None:
    if isinstance(value, float):
        _require(math.isfinite(value), f"non-finite number at {path}")
    elif isinstance(value, dict):
        for key, item in value.items():
            _require_finite_numbers(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _require_finite_numbers(item, f"{path}[{index}]")


def _reject_result_keys(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            _require(
                not any(part in lowered for part in FORBIDDEN_RESULT_KEY_PARTS),
                f"combat-result key forbidden at {path}.{key}",
            )
            _reject_result_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_result_keys(item, f"{path}[{index}]")


def _materialize_event_frames(
    action: str, raw: object, frames: int
) -> dict[str, int | list[int]]:
    _require(isinstance(raw, dict), f"{action} event frames must be an object")
    event_frames = cast(dict[str, Any], raw)
    expected = EVENT_FRAME_SCHEMA[action]
    _require(set(event_frames) == set(expected), f"{action} event-frame schema drift")
    result: dict[str, int | list[int]] = {}
    for key, kind in expected.items():
        value = event_frames[key]
        if kind == "frame":
            _require(type(value) is int and 0 <= value < frames, f"{action}/{key} frame leaves horizon")
            result[key] = value
        else:
            _require(
                isinstance(value, list)
                and len(value) == 2
                and all(type(item) is int for item in value),
                f"{action}/{key} interval malformed",
            )
            start, end = value
            _require(0 <= start <= end < frames, f"{action}/{key} interval leaves horizon")
            result[key] = [start, end]
    return result


def _lerp(left: list[float], right: list[float], amount: float) -> list[float]:
    _require(len(left) == len(right), "vector shape mismatch")
    return [a + amount * (b - a) for a, b in zip(left, right, strict=True)]


def _add(left: list[float], right: list[float]) -> list[float]:
    _require(len(left) == len(right), "vector shape mismatch")
    return [a + b for a, b in zip(left, right, strict=True)]


def _materialize_root(schedule: list[dict[str, Any]], frames: int) -> list[list[float]]:
    root: list[list[float] | None] = [None] * frames
    previous_end: list[float] | None = None
    expected_start = 0
    for segment in schedule:
        start, end = segment["frames"]
        _require(start == expected_start and start <= end < frames, "root schedule is not contiguous")
        start_xz = list(segment["xz_start_m"])
        end_xz = list(segment["xz_end_m"])
        _require(len(start_xz) == 2 and len(end_xz) == 2, "root xz shape drift")
        if previous_end is not None:
            _require(start_xz == previous_end, "root endpoint discontinuity")
        span = end - start
        for frame in range(start, end + 1):
            amount = 1.0 if span == 0 else (frame - start) / span
            _require(root[frame] is None, "overlapping root schedule")
            root[frame] = _lerp(start_xz, end_xz, amount)
        previous_end = end_xz
        expected_start = end + 1
    _require(expected_start == frames and all(item is not None for item in root), "root schedule misses frames")
    return [item for item in root if item is not None]


def _materialize_feet(
    schedule: dict[str, list[dict[str, Any]]], frames: int
) -> tuple[dict[str, list[int]], list[dict[str, Any]], list[dict[str, Any]]]:
    contact_targets: dict[str, list[int | None]] = {side: [None] * frames for side in SIDES}
    planted: list[dict[str, Any]] = []
    swings: list[dict[str, Any]] = []

    for side in SIDES:
        initial_anchor = "L0" if side == "left" else "R0"
        anchors: dict[str, list[float]] = {initial_anchor: [0.0, 0.0]}
        expected_start = 0
        for segment in schedule[side]:
            start, end = segment["frames"]
            _require(start == expected_start and start <= end < frames, f"{side} contact schedule is not contiguous")
            mode = segment["mode"]
            if mode == "swing":
                from_anchor = segment["from_anchor"]
                to_anchor = segment["to_anchor"]
                _require(from_anchor in anchors and to_anchor not in anchors, f"{side} swing anchor transition drift")
                landing_offset = list(segment["landing_offset_xz_m"])
                _require(len(landing_offset) == 2, f"{side} landing offset shape drift")
                anchors[to_anchor] = _add(anchors[from_anchor], landing_offset)
                for frame in range(start, end + 1):
                    _require(contact_targets[side][frame] is None, f"{side} overlapping contact schedule")
                    contact_targets[side][frame] = 0
                swings.append(
                    {
                        "side": side,
                        "frames": [start, end],
                        "from_anchor": from_anchor,
                        "to_anchor": to_anchor,
                        "from_anchor_offset_xz_m": list(anchors[from_anchor]),
                        "to_anchor_offset_xz_m": list(anchors[to_anchor]),
                        "apex_frame": segment["apex_frame"],
                        "toe_clearance_m": segment["toe_clearance_m"],
                    }
                )
            else:
                _require(mode in {"planted_world_anchor", "planted_new_anchor"}, f"{side} contact mode drift")
                anchor_id = segment["anchor_id"]
                _require(anchor_id in anchors, f"{side} planted anchor was not materialized")
                for frame in range(start, end + 1):
                    _require(contact_targets[side][frame] is None, f"{side} overlapping contact schedule")
                    contact_targets[side][frame] = 1
                    planted.append(
                        {
                            "side": side,
                            "frame": frame,
                            "anchor_id": anchor_id,
                            "anchor_offset_xz_m": list(anchors[anchor_id]),
                        }
                    )
            expected_start = end + 1
        _require(expected_start == frames, f"{side} contact schedule misses frames")
        _require(all(item is not None for item in contact_targets[side]), f"{side} contact target misses frames")

    planted.sort(key=lambda item: (item["frame"], SIDES.index(item["side"])))
    swings.sort(key=lambda item: (item["frames"][0], SIDES.index(item["side"])))
    return (
        {side: [cast(int, item) for item in contact_targets[side]] for side in SIDES},
        planted,
        swings,
    )


def _materialize_hands(
    action: dict[str, Any], root_xz: list[list[float]], weapon: dict[str, Any]
) -> list[dict[str, Any]]:
    axis_min = weapon["bounds_min_m"][2]
    axis_max = weapon["bounds_max_m"][2]
    axis_length = axis_max - axis_min
    _require(axis_length > 0.0, "W0 axis length must be positive")
    right_amount = (weapon["right_grip_socket_m"][2] - axis_min) / axis_length
    left_amount = (weapon["left_grip_socket_m"][2] - axis_min) / axis_length
    _require(0.0 <= right_amount <= 1.0 and 0.0 <= left_amount <= 1.0, "W0 grip leaves weapon axis")

    result = []
    for pose in action["keyposes"]:
        frame = pose["frame"]
        _require(0 <= frame < len(root_xz), "keypose frame leaves horizon")
        world_offset = [root_xz[frame][0], 0.0, root_xz[frame][1]]
        pommel_world = _add(list(pose["weapon_pommel_root_m"]), world_offset)
        tip_world = _add(list(pose["weapon_tip_root_m"]), world_offset)
        right_hand = _lerp(pommel_world, tip_world, right_amount)
        if action["weapon_ownership"] == "two_hand":
            left_hand = _lerp(pommel_world, tip_world, left_amount)
            left_role = "secondary_grip"
        else:
            left_hand = _add(list(pose["left_effector_root_m"]), world_offset)
            left_role = "independent_grab_effector"
        result.append(
            {
                "frame": frame,
                "weapon_pommel_world_m": pommel_world,
                "weapon_tip_world_m": tip_world,
                "right_hand_world_m": right_hand,
                "right_hand_role": "primary_grip",
                "left_hand_world_m": left_hand,
                "left_hand_role": left_role,
            }
        )
    return result


def materialize(
    spec: dict[str, Any],
    w0: dict[str, Any],
    *,
    spec_sha256: str,
    w0_sha256: str,
) -> dict[str, Any]:
    """Return deterministic ARDY proposal constraints derived from v4 and W0."""

    _require_finite_numbers(spec)
    _require_finite_numbers(w0)
    _require(spec.get("schema") == SPEC_SCHEMA, "unsupported ARDY endpoint schema")
    _require(w0.get("schema") == W0_SCHEMA, "unsupported W0 schema")
    _require(spec.get("generation_authorized") is False, "materializer requires generation to remain unauthorized")
    _require(tuple(spec["actions"]) == ACTIONS, "action set/order drift")
    _require(_is_sha256(spec_sha256) and _is_sha256(w0_sha256), "source hashes must be lowercase SHA-256 hex")
    _require(
        isinstance(spec.get("w0_contract"), dict)
        and spec["w0_contract"].get("sha256") == w0_sha256,
        "loaded W0 bytes do not match the declared contract hash",
    )
    frames = int(spec["frames"])
    _require(frames > 0, "frame horizon must be positive")

    actions: dict[str, Any] = {}
    for name in ACTIONS:
        source = spec["actions"][name]
        root_xz = _materialize_root(source["root_schedule"], frames)
        contact_targets, planted, swings = _materialize_feet(source["contact_schedule"], frames)
        actions[name] = {
            "intent": source["intent"],
            "weapon_ownership": source["weapon_ownership"],
            "root_xz_m": root_xz,
            "foot_contact_targets": contact_targets,
            "planted_foot_targets": planted,
            "swing_intervals": swings,
            "hand_keyposes": _materialize_hands(source, root_xz, w0["weapon"]),
            "proposal_event_frames": _materialize_event_frames(
                name, source["event_frames"], frames
            ),
        }

    document = {
        "schema": OUTPUT_SCHEMA,
        "authority": "offline_kinematic_proposal_constraints_only",
        "generation_authorized": False,
        "playable_proof": False,
        "fps": spec["fps"],
        "frames": frames,
        "shipping_fps": spec["shipping_fps"],
        "source": {
            "spec_schema": SPEC_SCHEMA,
            "spec_sha256": spec_sha256,
            "w0_schema": W0_SCHEMA,
            "w0_sha256": w0_sha256,
            "ardy_source_commit": spec["source_commit"],
            "model": spec["model"],
        },
        "actions": actions,
    }
    _require_finite_numbers(document)
    _reject_result_keys(document)
    return document


def canonical_bytes(value: dict[str, Any]) -> bytes:
    """Encode a materialized document with stable ordering and no whitespace."""

    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
