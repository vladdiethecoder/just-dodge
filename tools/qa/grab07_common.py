#!/usr/bin/env python3
"""Shared strict parsing, metrics, schema checks, and gate logic for Grab-07 QA.

Only Python's standard library is used so these tools can run in the pinned
Python environment without a package installation.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

CAPTURE_SCHEMA = "grab07-capture-v1"
RECEIPT_SCHEMA = "grab07-promotion-receipt-v1"
PHASES = (
    "tell", "approach", "first_contact", "secure_grab", "consequence", "release", "recovery",
)
CAMERA_NAMES = ("first_person", "front", "side", "top", "three_quarter")
EPS = 1e-12


class ContractError(ValueError):
    """An artifact violates the shared Grab-07 contract."""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def number(value: Any, label: str) -> float:
    require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{label}: expected finite number")
    value = float(value)
    require(math.isfinite(value), f"{label}: expected finite number")
    return value


def integer(value: Any, label: str) -> int:
    require(isinstance(value, int) and not isinstance(value, bool), f"{label}: expected integer")
    return value


def vector(value: Any, length: int, label: str) -> list[float]:
    require(isinstance(value, list) and len(value) == length, f"{label}: expected array[{length}]")
    return [number(item, f"{label}[{index}]") for index, item in enumerate(value)]


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"required input missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON {path}: {exc}") from exc


def load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ContractError(f"required input missing: {path}") from exc
    require(lines, f"{label}: must contain at least one record")
    records = []
    for line_no, line in enumerate(lines, 1):
        require(line.strip(), f"{label}:{line_no}: blank JSONL lines are forbidden")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError(f"{label}:{line_no}: invalid JSON: {exc}") from exc
        require(isinstance(record, dict), f"{label}:{line_no}: record must be object")
        records.append(record)
    return records


def parse_capture(path: Path) -> list[dict[str, Any]]:
    records = load_jsonl(path, "capture.jsonl")
    previous_tick = -1
    for line_no, record in enumerate(records, 1):
        prefix = f"capture.jsonl:{line_no}"
        required = {
            "schema", "physics_tick", "render_frame", "substep_within_frame", "phase", "contacts",
            "max_penetration_depth_m", "rms_penetration_depth_m", "grabber_root", "opponent_root",
        }
        require(required <= record.keys(), f"{prefix}: missing {sorted(required - record.keys())}")
        require(record["schema"] == CAPTURE_SCHEMA, f"{prefix}: unexpected schema")
        tick = integer(record["physics_tick"], f"{prefix}.physics_tick")
        require(tick == previous_tick + 1, f"{prefix}: physics_tick must be contiguous from zero")
        previous_tick = tick
        require(integer(record["render_frame"], f"{prefix}.render_frame") == tick // 2, f"{prefix}: render_frame != physics_tick // 2")
        require(integer(record["substep_within_frame"], f"{prefix}.substep_within_frame") == tick % 2, f"{prefix}: substep_within_frame != physics_tick % 2")
        require(record["phase"] in PHASES, f"{prefix}: invalid phase")
        require(isinstance(record["contacts"], list), f"{prefix}.contacts must be array")
        require(isinstance(record["grabber_root"], str) and record["grabber_root"], f"{prefix}.grabber_root missing")
        require(isinstance(record["opponent_root"], str) and record["opponent_root"], f"{prefix}.opponent_root missing")
        max_depth = number(record["max_penetration_depth_m"], f"{prefix}.max_penetration_depth_m")
        rms_depth = number(record["rms_penetration_depth_m"], f"{prefix}.rms_penetration_depth_m")
        require(max_depth >= 0 and rms_depth >= 0, f"{prefix}: penetration depth must be non-negative")
        for contact_index, contact in enumerate(record["contacts"]):
            contact_prefix = f"{prefix}.contacts[{contact_index}]"
            require(isinstance(contact, dict), f"{contact_prefix}: contact must be object")
            contact_required = {"attacker", "defender", "attacker_proxy", "defender_proxy", "point_m", "normal", "depth_m", "time_of_impact", "mesh_pair"}
            require(contact_required <= contact.keys(), f"{contact_prefix}: missing {sorted(contact_required - contact.keys())}")
            for key in ("attacker", "defender", "mesh_pair"):
                require(isinstance(contact[key], str) and contact[key], f"{contact_prefix}.{key}: expected non-empty string")
            integer(contact["attacker_proxy"], f"{contact_prefix}.attacker_proxy")
            integer(contact["defender_proxy"], f"{contact_prefix}.defender_proxy")
            vector(contact["point_m"], 3, f"{contact_prefix}.point_m")
            vector(contact["normal"], 3, f"{contact_prefix}.normal")
            require(number(contact["depth_m"], f"{contact_prefix}.depth_m") >= 0, f"{contact_prefix}.depth_m must be non-negative")
            number(contact["time_of_impact"], f"{contact_prefix}.time_of_impact")
    return records


def parse_findings(path: Path, capture: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = load_jsonl(path, "findings.jsonl")
    capture_ticks = {record["physics_tick"] for record in capture}
    required = {
        "artifact_sha256", "revision", "clip", "physics_tick", "subframe", "lod", "object_pair", "mesh_pair",
        "triangle_ids", "barycentric", "world_point", "local_point", "normal", "signed_depth_m", "area_m2", "duration_ticks",
    }
    for line_no, record in enumerate(records, 1):
        prefix = f"findings.jsonl:{line_no}"
        require(required <= record.keys(), f"{prefix}: missing {sorted(required - record.keys())}")
        for key in ("artifact_sha256", "revision", "lod", "object_pair", "mesh_pair"):
            require(isinstance(record[key], str) and record[key], f"{prefix}.{key}: expected non-empty string")
        require(record["clip"] == "grab07", f"{prefix}.clip must be grab07")
        tick = integer(record["physics_tick"], f"{prefix}.physics_tick")
        require(tick in capture_ticks, f"{prefix}.physics_tick is absent from capture")
        number(record["subframe"], f"{prefix}.subframe")
        triangle_ids = record["triangle_ids"]
        require(isinstance(triangle_ids, list) and len(triangle_ids) == 2, f"{prefix}.triangle_ids: expected array[2]")
        for index, tri_id in enumerate(triangle_ids):
            require(integer(tri_id, f"{prefix}.triangle_ids[{index}]") >= 0, f"{prefix}.triangle_ids[{index}] must be non-negative")
        vector(record["barycentric"], 3, f"{prefix}.barycentric")
        vector(record["world_point"], 3, f"{prefix}.world_point")
        vector(record["local_point"], 3, f"{prefix}.local_point")
        vector(record["normal"], 3, f"{prefix}.normal")
        number(record["signed_depth_m"], f"{prefix}.signed_depth_m")
        require(number(record["area_m2"], f"{prefix}.area_m2") >= 0, f"{prefix}.area_m2 must be non-negative")
        require(integer(record["duration_ticks"], f"{prefix}.duration_ticks") >= 0, f"{prefix}.duration_ticks must be non-negative")
    return records


def parse_phases(path: Path, capture: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = load_json(path)
    spans = raw.get("phases") if isinstance(raw, dict) else raw
    require(isinstance(spans, list), "phases.json: expected a list or an object with phases")
    require(len(spans) == len(PHASES), "phases.json: exactly seven phase spans required")
    end_tick = capture[-1]["physics_tick"]
    cursor = 0
    seen = []
    for index, span in enumerate(spans):
        prefix = f"phases.json[{index}]"
        require(isinstance(span, dict), f"{prefix}: span must be object")
        require({"phase", "start_physics_tick", "end_physics_tick"} <= span.keys(), f"{prefix}: missing phase fields")
        phase = span["phase"]
        require(phase in PHASES, f"{prefix}.phase invalid")
        start = integer(span["start_physics_tick"], f"{prefix}.start_physics_tick")
        end = integer(span["end_physics_tick"], f"{prefix}.end_physics_tick")
        require(start == cursor and end >= start, f"{prefix}: spans must be contiguous and non-empty")
        cursor = end + 1
        seen.append(phase)
    require(tuple(seen) == PHASES, "phases.json: phase order must match shared contract")
    require(cursor == end_tick + 1, "phases.json: spans must cover the full capture")
    for record in capture:
        matched = next(span for span in spans if span["start_physics_tick"] <= record["physics_tick"] <= span["end_physics_tick"])
        require(record["phase"] == matched["phase"], f"capture tick {record['physics_tick']}: phase disagrees with phases.json")
    metadata = raw if isinstance(raw, dict) else {}
    return spans, metadata


def parse_cameras(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = load_json(path)
    cameras = raw.get("cameras") if isinstance(raw, dict) else raw
    require(isinstance(cameras, list) and len(cameras) == len(CAMERA_NAMES), "cameras.json: exactly five cameras required")
    names = []
    for index, camera in enumerate(cameras):
        prefix = f"cameras.json[{index}]"
        require(isinstance(camera, dict), f"{prefix}: camera must be object")
        require({"name", "eye_m", "target_m", "up"} <= camera.keys(), f"{prefix}: missing camera fields")
        require(isinstance(camera["name"], str), f"{prefix}.name must be string")
        names.append(camera["name"])
        vector(camera["eye_m"], 3, f"{prefix}.eye_m")
        vector(camera["target_m"], 3, f"{prefix}.target_m")
        vector(camera["up"], 3, f"{prefix}.up")
        require(("fov_deg" in camera) ^ ("ortho_scale" in camera), f"{prefix}: exactly one of fov_deg or ortho_scale required")
        number(camera.get("fov_deg", camera.get("ortho_scale")), f"{prefix}.projection")
    require(tuple(names) == CAMERA_NAMES, "cameras.json: camera order/names drifted")
    return cameras, raw if isinstance(raw, dict) else {}


def validate_schema(value: Any, schema: dict[str, Any], location: str = "$") -> None:
    """Small deterministic validator for the vocabulary used by our checked-in schema."""
    if "$ref" in schema:
        reference = schema["$ref"]
        require(reference.startswith("#/$defs/"), f"{location}: unsupported schema ref {reference}")
        return validate_schema(value, schema_root(schema)[reference.split("/")[-1]], location)
    if "const" in schema:
        require(value == schema["const"], f"{location}: expected {schema['const']!r}")
    if "enum" in schema:
        require(value in schema["enum"], f"{location}: expected one of {schema['enum']}")
    schema_type = schema.get("type")
    if schema_type == "object":
        require(isinstance(value, dict), f"{location}: expected object")
        for key in schema.get("required", []):
            require(key in value, f"{location}: missing required property {key}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            require(not extra, f"{location}: unexpected properties {sorted(extra)}")
        for key, item_schema in properties.items():
            if key in value:
                validate_schema(value[key], with_root(item_schema, schema), f"{location}.{key}")
    elif schema_type == "array":
        require(isinstance(value, list), f"{location}: expected array")
        if "minItems" in schema:
            require(len(value) >= schema["minItems"], f"{location}: too few items")
        if "maxItems" in schema:
            require(len(value) <= schema["maxItems"], f"{location}: too many items")
        if "items" in schema:
            for index, item in enumerate(value):
                validate_schema(item, with_root(schema["items"], schema), f"{location}[{index}]")
    elif schema_type == "string":
        import re
        require(isinstance(value, str), f"{location}: expected string")
        if "minLength" in schema:
            require(len(value) >= schema["minLength"], f"{location}: string is empty")
        if "pattern" in schema:
            require(re.fullmatch(schema["pattern"], value) is not None, f"{location}: pattern mismatch")
    elif schema_type == "integer":
        require(isinstance(value, int) and not isinstance(value, bool), f"{location}: expected integer")
        if "minimum" in schema:
            require(value >= schema["minimum"], f"{location}: below minimum")
    elif schema_type == "number":
        number(value, location)
        if "minimum" in schema:
            require(value >= schema["minimum"], f"{location}: below minimum")
    elif schema_type is not None:
        raise ContractError(f"{location}: unsupported schema type {schema_type}")


def schema_root(schema: dict[str, Any]) -> dict[str, Any]:
    return schema.get("__root__", schema).get("$defs", {})


def with_root(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    copied = dict(schema)
    copied["__root__"] = root.get("__root__", root)
    return copied


def metrics_from_capture_and_findings(capture: list[dict[str, Any]], findings: list[dict[str, Any]]) -> dict[str, Any]:
    max_penetration = max(float(record["max_penetration_depth_m"]) for record in capture)
    rms_values = [float(record["rms_penetration_depth_m"]) for record in capture]
    rms_penetration = math.sqrt(sum(value * value for value in rms_values) / len(rms_values))
    affected = [finding for finding in findings if float(finding["signed_depth_m"]) < 0]
    affected_area = sum(float(finding["area_m2"]) for finding in affected)
    duration = max((int(finding["duration_ticks"]) for finding in affected), default=0)
    min_clearance = min((float(finding["signed_depth_m"]) for finding in findings), default=0.0)
    return {
        "max_penetration_m": max_penetration,
        "rms_penetration_m": rms_penetration,
        "affected_area_m2": affected_area,
        "duration_ticks": duration,
        "min_clearance_m": min_clearance,
    }


def has_secure_grab_contact(capture: list[dict[str, Any]]) -> int:
    count = 0
    for record in capture:
        if record["phase"] != "secure_grab":
            continue
        for contact in record["contacts"]:
            pair = contact["mesh_pair"].lower()
            if contact["attacker"] == "grabber" and contact["defender"] == "opponent" and "hand" in pair:
                count += 1
    return count


def repair_is_available(receipt: dict[str, Any]) -> bool:
    return receipt.get("output_sha256") != "pending"


def evaluate_gates(receipt: dict[str, Any], capture: list[dict[str, Any]], findings: list[dict[str, Any]], determinism: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    after = receipt["after"]
    available = repair_is_available(receipt)
    if not available:
        g1 = {"status": "FAIL", "measured_value": "after-repair evidence unavailable"}
        g2 = {"status": "FAIL", "measured_value": "after-repair evidence unavailable"}
    else:
        g1_pass = after["max_penetration_m"] <= EPS
        g1 = {"status": "PASS" if g1_pass else "FAIL", "measured_value": f"after max penetration={after['max_penetration_m']:.9g} m (required 0)"}
        g2_pass = after["max_penetration_m"] <= 0.0005
        g2 = {"status": "PASS" if g2_pass else "FAIL", "measured_value": f"after max penetration={after['max_penetration_m']:.9g} m (limit 0.0005 m)"}
    secure_contacts = has_secure_grab_contact(capture)
    g3 = {
        "status": "PASS" if secure_contacts else "FAIL",
        "measured_value": f"secure_grab hand-to-opponent contact events={secure_contacts}",
    }
    g4 = {"status": "PENDING_HUMAN", "measured_value": "beauty material review requires human decision"}
    g5 = {"status": "PENDING_HUMAN", "measured_value": "first_person + silhouette semantic review requires human decision"}
    # A G6 result is valid only for these exact receipt bytes, not merely an older
    # run that happened to have the same input fingerprint.
    rerun_matches = bool(
        determinism
        and determinism.get("status") == "PASS"
        and determinism.get("baseline_deterministic_rerun_sha256") == receipt["deterministic_rerun_sha256"]
        and determinism.get("baseline_receipt_sha256") == sha256_bytes(canonical_bytes(receipt))
    )
    g6 = {
        "status": "PASS" if rerun_matches else "FAIL",
        "measured_value": "deterministic rerun receipt/input hash matches" if rerun_matches else "no matching deterministic rerun evidence",
    }
    return {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "G6": g6}
