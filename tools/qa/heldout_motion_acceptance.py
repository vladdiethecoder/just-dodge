#!/usr/bin/env python3
"""Fail-closed held-out interaction acceptance gate for MotionBricks candidates.

This evaluator is deliberately offline and presentation/kinematics-only. It never
creates a contact, force, injury, or outcome: planted-foot observations,
grip targets, and the primary contact event must arrive in a candidate-hash-bound
export from the deterministic truth/contact observer. A candidate passes only
when its condition is explicitly absent from the supplied training manifest, its
motion metrics pass, and independent blinded visual evidence is bound to the
exact candidate bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA = "just-dodge-heldout-motion-acceptance-v1"
TRAINING_SCHEMA = "just-dodge-interaction-training-manifest-v1"
CASES_SCHEMA = "just-dodge-heldout-interaction-cases-v1"
VISUAL_SCHEMA = "just-dodge-heldout-motion-visual-review-v1"
OBSERVER_SCHEMA = "just-dodge-deterministic-contact-observer-v1"

# These are immutable admission policy limits, not producer-configurable hints.
POLICY_THRESHOLDS = {
    "max_foot_drift_m": 0.02,
    "max_grip_error_m": 0.01,
    "max_contact_timing_error_frames": 2,
    "max_contact_distance_m": 0.01,
    "minimum_visual_quality_score": 1.0,
    "minimum_visual_confidence": 0.8,
}

# G1 joint indices, fixed for this evidence format.
LEFT_FOOT = (7, (0, 1))
RIGHT_FOOT = (14, (2, 3))
GRIP_JOINTS = (25, 33)
REQUIRED_VISUAL_QUESTIONS = (
    "full_body_visible",
    "feet_visually_grounded",
    "grip_visually_coherent",
    "no_obvious_mesh_or_silhouette_collapse",
)
REQUIRED_VIEWS = ("front", "side")
REQUIRED_CONDITION_FIELDS = (
    "opponent_intent",
    "response_intent",
    "attack_height",
    "attack_side",
    "contact_timing",
    "target_role",
    "reach_band",
)


class GateError(ValueError):
    """A malformed or unacceptable candidate/evidence bundle."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def strict_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GateError(f"cannot load JSON {path}: {error}") from error
    if not isinstance(data, dict):
        raise GateError(f"{path}: root must be an object")
    return data


def relative_file(root: Path, raw: str, label: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise GateError(f"{label} must be a repository-relative path")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise GateError(f"{label} escapes candidate root") from error
    if not resolved.is_file():
        raise GateError(f"{label} does not exist: {candidate}")
    return resolved


def require_finite_array(name: str, value: np.ndarray, shape: tuple[int | None, ...]) -> None:
    if value.ndim != len(shape) or any(expected is not None and got != expected for got, expected in zip(value.shape, shape, strict=True)):
        raise GateError(f"{name} has shape {value.shape}, expected {shape}")
    if not np.isfinite(value).all():
        raise GateError(f"{name} contains non-finite values")


def condition_signature(condition: Any, label: str) -> str:
    if not isinstance(condition, dict):
        raise GateError(f"{label} must be an object")
    missing = [field for field in REQUIRED_CONDITION_FIELDS if field not in condition]
    extra = sorted(set(condition) - set(REQUIRED_CONDITION_FIELDS))
    if missing or extra:
        raise GateError(f"{label} must contain exactly held-out axes; missing={missing}, extra={extra}")
    if not all(isinstance(condition[field], str) and condition[field] for field in REQUIRED_CONDITION_FIELDS):
        raise GateError(f"{label} axes must be non-empty strings")
    return hashlib.sha256(canonical_bytes(condition)).hexdigest()


def load_training_signatures(training_manifest: Path) -> set[str]:
    manifest = strict_json(training_manifest)
    if manifest.get("schema") != TRAINING_SCHEMA:
        raise GateError(f"training manifest must use {TRAINING_SCHEMA}")
    conditions = manifest.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise GateError("training manifest requires a non-empty conditions list")
    return {condition_signature(item, "training condition") for item in conditions}


def planted_foot_drift(positions: np.ndarray, contacts: np.ndarray) -> float:
    maximum = 0.0
    for joint, channels in (LEFT_FOOT, RIGHT_FOOT):
        planted = np.max(contacts[:, channels], axis=1) >= 0.5
        start: int | None = None
        for frame, active in enumerate(np.append(planted, False)):
            if active and start is None:
                start = frame
            elif not active and start is not None:
                if frame - start >= 2:
                    drift = np.linalg.norm(positions[start:frame, joint] - positions[start, joint], axis=1)
                    maximum = max(maximum, float(np.max(drift)))
                start = None
    return maximum


def load_candidate(path: Path) -> np.ndarray:
    try:
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != {"posed_joints"}:
                raise GateError(f"{path.name}: candidate must contain only posed_joints")
            positions = np.asarray(archive["posed_joints"], dtype=np.float64)
    except (OSError, ValueError) as error:
        if isinstance(error, GateError):
            raise
        raise GateError(f"cannot load candidate {path}: {error}") from error
    if positions.shape[0] < 2:
        raise GateError(f"{path.name}: candidate needs at least two frames")
    require_finite_array("posed_joints", positions, (positions.shape[0], 34, 3))
    return positions


def load_observer(case: dict[str, Any], candidate_root: Path, candidate_sha256: str, frames: int) -> dict[str, Any]:
    path = relative_file(candidate_root, case.get("observer_path", ""), f"{case['id']} observer_path")
    observer = strict_json(path)
    if observer.get("schema") != OBSERVER_SCHEMA:
        raise GateError(f"{path.name}: unsupported deterministic observer schema")
    if observer.get("authority") != "deterministic_physics_contact_observer":
        raise GateError(f"{path.name}: observer authority drift")
    if observer.get("case_id") != case["id"] or observer.get("candidate_sha256") != candidate_sha256:
        raise GateError(f"{path.name}: observer does not bind the exact candidate")
    physics_run_id = observer.get("physics_run_id")
    trace_sha256 = observer.get("physics_trace_sha256")
    if not isinstance(physics_run_id, str) or not physics_run_id or not isinstance(trace_sha256, str) or len(trace_sha256) != 64:
        raise GateError(f"{path.name}: observer requires a physics run ID and trace SHA-256")
    contacts = np.asarray(observer.get("foot_contacts"), dtype=np.float64)
    targets = np.asarray(observer.get("grip_targets_m"), dtype=np.float64)
    require_finite_array("observer foot_contacts", contacts, (frames, 4))
    require_finite_array("observer grip_targets_m", targets, (frames, 2, 3))
    if np.any((contacts < 0.0) | (contacts > 1.0)):
        raise GateError(f"{path.name}: observer foot contacts must be probabilities in [0, 1]")
    if not np.any(contacts >= 0.5):
        raise GateError(f"{path.name}: observer has no planted-foot evidence")
    events = observer.get("contact_events")
    if not isinstance(events, list):
        raise GateError(f"{path.name}: contact_events must be a list")
    primary = [event for event in events if isinstance(event, dict) and event.get("primary") is True]
    if len(primary) != 1:
        raise GateError(f"{path.name}: observer requires exactly one primary contact event")
    event = primary[0]
    frame = event.get("frame")
    distance = event.get("distance_m")
    if not isinstance(frame, int) or not 0 <= frame < frames or not isinstance(distance, (int, float)) or not math.isfinite(float(distance)) or distance < 0:
        raise GateError(f"{path.name}: primary contact event is malformed")
    return {
        "path": str(path.relative_to(candidate_root)),
        "sha256": sha256(path),
        "foot_contacts": contacts,
        "grip_targets": targets,
        "contact_frame": frame,
        "contact_distance_m": float(distance),
        "physics_run_id": physics_run_id,
        "physics_trace_sha256": trace_sha256,
    }


def png_dimensions(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise GateError(f"{path.name}: capture must be a decodable PNG")
    width = int.from_bytes(raw[16:20], "big")
    height = int.from_bytes(raw[20:24], "big")
    if width <= 0 or height <= 0:
        raise GateError(f"{path.name}: PNG dimensions must be positive")
    return width, height


def validate_visual_review(case: dict[str, Any], candidate_root: Path, candidate_sha256: str, thresholds: dict[str, Any]) -> dict[str, Any]:
    review_path = relative_file(candidate_root, case["visual_review_path"], "visual_review_path")
    review = strict_json(review_path)
    if review.get("schema") != VISUAL_SCHEMA:
        raise GateError(f"{review_path.name}: unsupported visual review schema")
    if review.get("case_id") != case["id"]:
        raise GateError(f"{review_path.name}: review case_id does not bind the case")
    if review.get("candidate_sha256") != candidate_sha256:
        raise GateError(f"{review_path.name}: review candidate_sha256 does not bind candidate bytes")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, dict) or reviewer.get("independent") is not True or reviewer.get("blinded") is not True:
        raise GateError(f"{review_path.name}: visual review must be independent and blinded")
    if reviewer.get("kind") not in {"human", "vlm"} or not isinstance(reviewer.get("review_run_id"), str) or not reviewer["review_run_id"]:
        raise GateError(f"{review_path.name}: reviewer kind and immutable review_run_id are required")
    receipt_sha256 = reviewer.get("decision_receipt_sha256")
    if not isinstance(receipt_sha256, str) or len(receipt_sha256) != 64:
        raise GateError(f"{review_path.name}: reviewer requires decision_receipt_sha256")

    captures = review.get("captures")
    if not isinstance(captures, list):
        raise GateError(f"{review_path.name}: captures must be a list")
    seen_views: set[str] = set()
    for capture in captures:
        if not isinstance(capture, dict):
            raise GateError(f"{review_path.name}: capture must be an object")
        view = capture.get("view")
        if view not in REQUIRED_VIEWS or view in seen_views:
            raise GateError(f"{review_path.name}: require exactly one front and one side capture")
        seen_views.add(view)
        path = relative_file(candidate_root, capture.get("path", ""), f"capture {view} path")
        if capture.get("sha256") != sha256(path):
            raise GateError(f"{review_path.name}: {view} capture hash mismatch")
        resolution = capture.get("resolution_px")
        if not isinstance(resolution, list) or len(resolution) != 2 or not all(isinstance(value, int) and value > 0 for value in resolution):
            raise GateError(f"{review_path.name}: {view} capture requires positive resolution_px")
        if tuple(resolution) != png_dimensions(path):
            raise GateError(f"{review_path.name}: {view} capture resolution does not match PNG bytes")
        frame_indices = capture.get("frame_indices")
        expected_frame = case["expected_contact_frame"]
        if not isinstance(frame_indices, list) or expected_frame not in frame_indices or not all(isinstance(frame, int) and frame >= 0 for frame in frame_indices):
            raise GateError(f"{review_path.name}: {view} capture must include the contact frame")
    if seen_views != set(REQUIRED_VIEWS):
        raise GateError(f"{review_path.name}: required front and side captures are missing")

    answers = review.get("answers")
    if not isinstance(answers, list):
        raise GateError(f"{review_path.name}: answers must be a list")
    parsed: dict[str, dict[str, Any]] = {}
    for answer in answers:
        if not isinstance(answer, dict) or answer.get("id") in parsed:
            raise GateError(f"{review_path.name}: answers must have unique IDs")
        parsed[answer["id"]] = answer
    if set(parsed) != set(REQUIRED_VISUAL_QUESTIONS):
        raise GateError(f"{review_path.name}: answers must cover the complete visual rubric")
    minimum_confidence = float(thresholds["minimum_visual_confidence"])
    passed = [
        answer.get("verdict") == "yes" and isinstance(answer.get("confidence"), (int, float)) and math.isfinite(answer["confidence"]) and answer["confidence"] >= minimum_confidence
        for answer in parsed.values()
    ]
    score = sum(passed) / len(REQUIRED_VISUAL_QUESTIONS)
    if score < float(thresholds["minimum_visual_quality_score"]):
        raise GateError(f"{review_path.name}: visual quality score {score:.3f} is below threshold")
    return {
        "review_path": str(review_path.relative_to(candidate_root)),
        "review_sha256": sha256(review_path),
        "visual_quality_score": score,
        "reviewer_kind": reviewer["kind"],
    }


def evaluate(training_manifest: Path, heldout_cases_path: Path, candidate_root: Path) -> dict[str, Any]:
    training_signatures = load_training_signatures(training_manifest)
    bundle = strict_json(heldout_cases_path)
    if bundle.get("schema") != CASES_SCHEMA:
        raise GateError(f"held-out cases must use {CASES_SCHEMA}")
    thresholds = bundle.get("thresholds")
    if not isinstance(thresholds, dict):
        raise GateError("held-out cases require thresholds")
    required_thresholds = tuple(POLICY_THRESHOLDS)
    if set(thresholds) != set(required_thresholds):
        raise GateError("held-out threshold keys drift")
    if thresholds != POLICY_THRESHOLDS:
        raise GateError("held-out thresholds must match immutable admission policy")

    cases = bundle.get("cases")
    if not isinstance(cases, list) or not cases:
        raise GateError("held-out cases require a non-empty cases list")
    results = []
    case_ids: set[str] = set()
    signatures: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise GateError("held-out case must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            raise GateError("held-out cases require unique non-empty IDs")
        case_ids.add(case_id)
        signature = condition_signature(case.get("condition"), f"held-out case {case_id} condition")
        if signature in training_signatures:
            raise GateError(f"{case_id}: condition appears in the training manifest")
        if signature in signatures:
            raise GateError(f"{case_id}: duplicate held-out condition")
        signatures.add(signature)
        expected_frame = case.get("expected_contact_frame")
        if not isinstance(expected_frame, int) or expected_frame < 0:
            raise GateError(f"{case_id}: expected_contact_frame must be a non-negative integer")
        candidate_path = relative_file(candidate_root, case.get("candidate_path", ""), f"{case_id} candidate_path")
        candidate_sha256 = sha256(candidate_path)
        positions = load_candidate(candidate_path)
        frames = positions.shape[0]
        if expected_frame >= frames:
            raise GateError(f"{case_id}: expected_contact_frame is outside candidate horizon")
        observer = load_observer(case, candidate_root, candidate_sha256, frames)
        foot_drift = planted_foot_drift(positions, observer["foot_contacts"])
        grip_error = float(
            max(
                np.max(np.linalg.norm(positions[:, joint] - observer["grip_targets"][:, slot], axis=1))
                for slot, joint in enumerate(GRIP_JOINTS)
            )
        )
        observed_frame = int(observer["contact_frame"])
        contact_distance = float(observer["contact_distance_m"])
        contact_error = abs(observed_frame - expected_frame)
        if foot_drift > POLICY_THRESHOLDS["max_foot_drift_m"]:
            raise GateError(f"{case_id}: foot drift {foot_drift:.6f} m exceeds threshold")
        if grip_error > POLICY_THRESHOLDS["max_grip_error_m"]:
            raise GateError(f"{case_id}: grip error {grip_error:.6f} m exceeds threshold")
        if contact_distance > POLICY_THRESHOLDS["max_contact_distance_m"]:
            raise GateError(f"{case_id}: primary contact distance {contact_distance:.6f} m exceeds threshold")
        if contact_error > POLICY_THRESHOLDS["max_contact_timing_error_frames"]:
            raise GateError(f"{case_id}: contact timing error {contact_error} frames exceeds threshold")
        visual = validate_visual_review(case, candidate_root, candidate_sha256, POLICY_THRESHOLDS)
        results.append(
            {
                "case_id": case_id,
                "condition_sha256": signature,
                "candidate_path": str(candidate_path.relative_to(candidate_root)),
                "candidate_sha256": candidate_sha256,
                "frames": frames,
                "observed_foot_drift_m": foot_drift,
                "observed_grip_error_m": grip_error,
                "expected_contact_frame": expected_frame,
                "observed_contact_frame": observed_frame,
                "observed_contact_distance_m": contact_distance,
                "observed_contact_timing_error_frames": contact_error,
                "observer_path": observer["path"],
                "observer_sha256": observer["sha256"],
                "physics_run_id": observer["physics_run_id"],
                "physics_trace_sha256": observer["physics_trace_sha256"],
                **visual,
            }
        )
    return {
        "schema": SCHEMA,
        "status": "pass",
        "authority": "offline kinematic/visual acceptance only; deterministic physics owns contact, force, injury, and outcome",
        "training_manifest_sha256": sha256(training_manifest),
        "heldout_cases_sha256": sha256(heldout_cases_path),
        "thresholds": thresholds,
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-manifest", required=True, type=Path)
    parser.add_argument("--heldout-cases", required=True, type=Path)
    parser.add_argument("--candidate-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = evaluate(args.training_manifest.resolve(), args.heldout_cases.resolve(), args.candidate_dir.resolve())
    except GateError as error:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        failure = {"schema": SCHEMA, "status": "fail", "error": str(error)}
        args.output.write_bytes(canonical_bytes(failure) + b"\n")
        print(f"HELDOUT_MOTION_ACCEPTANCE=FAIL: {error}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(report) + b"\n")
    print(json.dumps({"status": "PASS", "cases": len(report["cases"]), "report_sha256": sha256(args.output)}, sort_keys=True))
    print("HELDOUT_MOTION_ACCEPTANCE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
