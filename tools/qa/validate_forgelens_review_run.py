#!/usr/bin/env python3
"""Fail-closed, dependency-free validation for ForgeLens ReviewRun v1.

Persistence callers must write nothing unless ``validate_review_run`` returns
``(True, [])``. Structural validation intentionally accepts dirty, staged,
untracked, unreachable, and outside-git identities as draft records. Promotion
callers must additionally require ``validate_pass_eligibility`` to return true.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVIEW_RUN_SCHEMA = "forgelens.review-run/v1"
ARTIFACT_LINEAGE_SCHEMA = "forgelens.artifact-lineage/v1"
SCHEMA_VERSION = 1
WORKFLOW_REVISION = "pvp005-w0-review-workflow/v1"
MAX_INVENTORY_ITEMS = 512

ROOT_FIELDS = frozenset(
    {
        "schema",
        "schemaVersion",
        "contract",
        "contractSha256",
        "createdAt",
        "lineage",
        "cameraInventory",
        "aovInventory",
        "requiredEvidence",
        "sourceAuthors",
        "decisionChainHeadSha256",
        "runId",
        "runFingerprintSha256",
    }
)
LINEAGE_FIELDS = frozenset(
    {
        "schema",
        "code",
        "build",
        "replay",
        "verifier",
        "truthHash",
        "truthVerification",
        "canonicalPlanPacket",
        "evidenceManifest",
        "workflowRevision",
        "generation",
        "producedArtifactInventory",
        "geometry",
        "geometryIdentitySha256",
    }
)
CODE_FIELDS = frozenset(
    {
        "schema",
        "revision",
        "reachable",
        "trackedClean",
        "toolProfileSha256",
        "workingTreeDiffSha256",
        "stagedDiffSha256",
        "untrackedInventorySha256",
    }
)
FILE_FIELDS = frozenset(
    {"schema", "path", "sha256", "bytes", "repositoryState", "relevantDiffSha256"}
)
TRUTH_VERIFICATION_FIELDS = frozenset(
    {"schema", "commandProfile", "stdoutSha256", "frames", "winner", "replayHash", "verdict"}
)
PRODUCED_METADATA_FIELDS = frozenset(
    {
        "cameraProfile",
        "aov",
        "kind",
        "frame",
        "tick60Hz",
        "physicsTick120Hz",
        "physicsSubstep",
        "uncropped",
        "fullFrame",
        "width",
        "height",
        "captureRect",
        "geometryIdentitySha256",
    }
)
IDENTITY_FIELDS = (
    "schema",
    "schemaVersion",
    "contract",
    "contractSha256",
    "createdAt",
    "lineage",
    "cameraInventory",
    "aovInventory",
    "requiredEvidence",
    "sourceAuthors",
)
REPOSITORY_STATES = frozenset(
    {"tracked-clean", "tracked-modified", "untracked", "outside-git", "unavailable"}
)
REVIEW_STATES = frozenset(
    {"awaiting_evidence", "awaiting_human", "submitted", "pass", "fail", "superseded", "expired"}
)
REVIEW_TRANSITIONS = {
    "awaiting_evidence": frozenset({"awaiting_human", "superseded", "expired"}),
    "awaiting_human": frozenset({"submitted", "superseded", "expired"}),
    "submitted": frozenset({"pass", "fail", "superseded", "expired"}),
    "pass": frozenset(),
    "fail": frozenset(),
    "superseded": frozenset(),
    "expired": frozenset(),
}
HUMAN_ATTESTATION_TRUE_FIELDS = frozenset(
    {
        "required_for_submitted",
        "browser_actor_server_derived",
        "known_automation_patterns_rejected",
        "self_authorship_rejected",
        "blind_observation_must_precede_label_reveal",
    }
)
BOUND_INPUT_PATHS = (
    ("build",),
    ("replay",),
    ("verifier",),
    ("canonicalPlanPacket",),
    ("evidenceManifest",),
    ("generation", "provider"),
    ("generation", "checkpoint"),
    ("generation", "retarget"),
    ("geometry",),
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TRUTH_HASH_RE = re.compile(r"^(?:[0-9a-f]{16}|[0-9a-f]{64})$")
_COMMIT_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_RUN_ID_RE = re.compile(r"^[0-9a-f]{20}$")
_CLEAN_DIFF_SHA256 = hashlib.sha256(b"").hexdigest()
_EMPTY_UNTRACKED_INVENTORY_SHA256 = hashlib.sha256(b"[]").hexdigest()


def _tool_profile_sha256() -> str:
    root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    for path in (
        root / "tools/asset_review.py",
        root / "tools/asset_review/index.html",
        root / "tools/asset_review/styles.css",
        root / "tools/asset_review/app.js",
        root / "docs/reports/FORGELENS_PHASE_A_READINESS_CONTRACT.json",
    ):
        payload = path.read_bytes()
        label = path.name.encode("utf-8")
        digest.update(struct.pack("<I", len(label)))
        digest.update(label)
        digest.update(struct.pack("<Q", len(payload)))
        digest.update(payload)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _check_exact_fields(value: dict[Any, Any], expected: frozenset[str], path: str, errors: list[str]) -> None:
    for field in sorted(expected - value.keys()):
        errors.append(f"{path}{field}: required field is missing")
    for field in sorted(value.keys() - expected, key=lambda item: (type(item).__name__, repr(item))):
        label = field if isinstance(field, str) else repr(field)
        errors.append(f"{path}{label}: unknown field")


def _check_sha256(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        errors.append(f"{path}: must be a lowercase 64-character SHA-256 digest")


def _check_truth_hash(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or _TRUTH_HASH_RE.fullmatch(value) is None:
        errors.append(f"{path}: must be a lowercase 16- or 64-character deterministic truth hash")


def _check_bounded_string(value: Any, path: str, errors: list[str], maximum: int = 200) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > maximum:
        errors.append(f"{path}: must be a canonical non-empty string of at most {maximum} characters")


def _check_non_negative_integer(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{path}: must be a non-negative integer")


def _check_repository_path(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 1_000:
        errors.append(f"{path}: must be a bounded repository-relative path")
        return
    segments = value.split("/")
    if value.startswith("/") or "\\" in value or "\x00" in value or any(
        segment in {"", ".", ".."} for segment in segments
    ):
        errors.append(f"{path}: must be canonical, repository-relative, and traversal-free")


def _check_timestamp(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.endswith("Z") or len(value) > 80:
        errors.append(f"{path}: must be a bounded UTC ISO 8601 timestamp ending in Z")
        return
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except (ValueError, OverflowError):
        errors.append(f"{path}: must be a valid UTC ISO 8601 timestamp")
        return
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        errors.append(f"{path}: must use UTC")


def _check_contract(value: Any, errors: list[str]) -> None:
    path = "contract"
    if not isinstance(value, dict):
        errors.append(f"{path}: must be an object")
        return
    if value.get("schema") != "just-dodge-forgelens-review-spine-contract-v1":
        errors.append(f"{path}.schema: unsupported review-spine contract")
    if isinstance(value.get("contract_version"), bool) or value.get("contract_version") != 1:
        errors.append(f"{path}.contract_version: unsupported version")
    if value.get("workflow_revision") != WORKFLOW_REVISION:
        errors.append(f"{path}.workflow_revision: must equal {WORKFLOW_REVISION!r}")
    states = value.get("states")
    if not isinstance(states, list) or any(not isinstance(state, str) for state in states) or set(states) != REVIEW_STATES:
        errors.append(f"{path}.states: must declare the fixed v1 state inventory")
    transitions = value.get("transitions")
    normalized: dict[str, frozenset[str]] = {}
    if isinstance(transitions, dict):
        for state, targets in transitions.items():
            if isinstance(state, str) and isinstance(targets, list) and all(isinstance(target, str) for target in targets):
                normalized[state] = frozenset(targets)
    if normalized != REVIEW_TRANSITIONS:
        errors.append(f"{path}.transitions: must declare the fixed acyclic v1 transition graph")
    if value.get("append_only") is not True:
        errors.append(f"{path}.append_only: must be true")
    human = value.get("human_attestation")
    if not isinstance(human, dict) or any(human.get(field) is not True for field in HUMAN_ATTESTATION_TRUE_FIELDS):
        errors.append(f"{path}.human_attestation: required controls must all be true")
    pass_eligibility = value.get("pass_eligibility")
    if not isinstance(pass_eligibility, dict) or not pass_eligibility or any(
        setting is not True for setting in pass_eligibility.values()
    ):
        errors.append(f"{path}.pass_eligibility: declared controls must be non-empty and true")


def _check_code_identity(value: Any, errors: list[str]) -> None:
    path = "lineage.code"
    if not isinstance(value, dict):
        errors.append(f"{path}: must be an object")
        return
    _check_exact_fields(value, CODE_FIELDS, f"{path}.", errors)
    if value.get("schema") != "forgelens.code-identity/v1":
        errors.append(f"{path}.schema: must equal 'forgelens.code-identity/v1'")
    revision = value.get("revision")
    if revision != "outside-git" and (not isinstance(revision, str) or _COMMIT_SHA_RE.fullmatch(revision) is None):
        errors.append(f"{path}.revision: must be 'outside-git' or a full lowercase commit SHA")
    for field in ("reachable", "trackedClean"):
        if not isinstance(value.get(field), bool):
            errors.append(f"{path}.{field}: must be boolean")
    for field in (
        "toolProfileSha256",
        "workingTreeDiffSha256",
        "stagedDiffSha256",
        "untrackedInventorySha256",
    ):
        _check_sha256(value.get(field), f"{path}.{field}", errors)


def _check_file_identity(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path}: must be an object")
        return
    _check_exact_fields(value, FILE_FIELDS, f"{path}.", errors)
    if value.get("schema") != "forgelens.file/v1":
        errors.append(f"{path}.schema: must equal 'forgelens.file/v1'")
    _check_repository_path(value.get("path"), f"{path}.path", errors)
    _check_sha256(value.get("sha256"), f"{path}.sha256", errors)
    _check_non_negative_integer(value.get("bytes"), f"{path}.bytes", errors)
    repository_state = value.get("repositoryState")
    if not isinstance(repository_state, str) or repository_state not in REPOSITORY_STATES:
        errors.append(f"{path}.repositoryState: must be one of {sorted(REPOSITORY_STATES)}")
    relevant = value.get("relevantDiffSha256")
    if relevant is not None:
        _check_sha256(relevant, f"{path}.relevantDiffSha256", errors)


def _check_truth_verification(value: Any, truth_hash: Any, errors: list[str]) -> None:
    path = "lineage.truthVerification"
    if not isinstance(value, dict):
        errors.append(f"{path}: must be an object")
        return
    _check_exact_fields(value, TRUTH_VERIFICATION_FIELDS, f"{path}.", errors)
    if value.get("schema") != "forgelens.truth-verification/v1":
        errors.append(f"{path}.schema: unsupported truth-verification schema")
    if value.get("commandProfile") != "m3-match-verify-v1":
        errors.append(f"{path}.commandProfile: must equal 'm3-match-verify-v1'")
    _check_sha256(value.get("stdoutSha256"), f"{path}.stdoutSha256", errors)
    _check_non_negative_integer(value.get("frames"), f"{path}.frames", errors)
    _check_bounded_string(value.get("winner"), f"{path}.winner", errors, 100)
    _check_truth_hash(value.get("replayHash"), f"{path}.replayHash", errors)
    if value.get("replayHash") != truth_hash:
        errors.append(f"{path}.replayHash: must match lineage.truthHash")
    if value.get("verdict") != "PASS":
        errors.append(f"{path}.verdict: must equal 'PASS'")


def _check_produced_artifacts(value: Any, lineage: dict[str, Any], errors: list[str]) -> None:
    path = "lineage.producedArtifactInventory"
    if not isinstance(value, list):
        errors.append(f"{path}: must be a list")
        return
    if len(value) > MAX_INVENTORY_ITEMS:
        errors.append(f"{path}: must contain at most {MAX_INVENTORY_ITEMS} artifacts")
    observed_paths: set[str] = set()
    for index, artifact in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{item_path}: must be an object")
            continue
        _check_exact_fields(artifact, FILE_FIELDS | PRODUCED_METADATA_FIELDS, f"{item_path}.", errors)
        _check_file_identity({field: artifact.get(field) for field in FILE_FIELDS}, item_path, errors)
        repository_path = artifact.get("path")
        if isinstance(repository_path, str):
            if repository_path in observed_paths:
                errors.append(f"{item_path}.path: produced artifact paths must be unique")
            observed_paths.add(repository_path)
        for field in ("cameraProfile", "aov", "kind"):
            _check_bounded_string(artifact.get(field), f"{item_path}.{field}", errors)
        for field in ("frame", "tick60Hz", "physicsTick120Hz", "physicsSubstep"):
            _check_non_negative_integer(artifact.get(field), f"{item_path}.{field}", errors)
        frame = artifact.get("frame")
        tick60 = artifact.get("tick60Hz")
        tick120 = artifact.get("physicsTick120Hz")
        substep = artifact.get("physicsSubstep")
        if (
            isinstance(frame, int)
            and not isinstance(frame, bool)
            and isinstance(tick60, int)
            and not isinstance(tick60, bool)
            and isinstance(tick120, int)
            and not isinstance(tick120, bool)
            and isinstance(substep, int)
            and not isinstance(substep, bool)
        ):
            if frame != tick60 or substep not in (0, 1) or tick120 != tick60 * 2 + substep:
                errors.append(f"{item_path}: 60 Hz/120 Hz timing identity is inconsistent")
        for field in ("uncropped", "fullFrame"):
            if not isinstance(artifact.get(field), bool):
                errors.append(f"{item_path}.{field}: must be boolean")
        for field in ("width", "height"):
            dimension = artifact.get(field)
            _check_non_negative_integer(dimension, f"{item_path}.{field}", errors)
            if isinstance(dimension, int) and not isinstance(dimension, bool) and not 1 <= dimension <= 16_384:
                errors.append(f"{item_path}.{field}: must be between 1 and 16384")
        capture = artifact.get("captureRect")
        if not isinstance(capture, dict):
            errors.append(f"{item_path}.captureRect: must be an object")
        else:
            _check_exact_fields(capture, frozenset({"x", "y", "width", "height"}), f"{item_path}.captureRect.", errors)
            for field in ("x", "y", "width", "height"):
                _check_non_negative_integer(capture.get(field), f"{item_path}.captureRect.{field}", errors)
        _check_sha256(artifact.get("geometryIdentitySha256"), f"{item_path}.geometryIdentitySha256", errors)
        if artifact.get("geometryIdentitySha256") != lineage.get("geometryIdentitySha256"):
            errors.append(f"{item_path}.geometryIdentitySha256: must match lineage.geometryIdentitySha256")


def _check_camera_inventory(value: Any, errors: list[str]) -> set[str]:
    path = "cameraInventory"
    if not isinstance(value, list):
        errors.append(f"{path}: must be a list")
        return set()
    if not 1 <= len(value) <= 64:
        errors.append(f"{path}: must contain 1 to 64 camera identifiers")
    profiles: list[str] = []
    for index, camera in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(camera, dict):
            errors.append(f"{item_path}: must be an object")
            continue
        _check_exact_fields(camera, frozenset({"profile", "revision", "width", "height"}), f"{item_path}.", errors)
        for field in ("profile", "revision"):
            _check_bounded_string(camera.get(field), f"{item_path}.{field}", errors)
        for field in ("width", "height"):
            dimension = camera.get(field)
            _check_non_negative_integer(dimension, f"{item_path}.{field}", errors)
            if isinstance(dimension, int) and not isinstance(dimension, bool) and not 1 <= dimension <= 16_384:
                errors.append(f"{item_path}.{field}: must be between 1 and 16384")
        if isinstance(camera.get("profile"), str):
            profiles.append(camera["profile"])
    if len(profiles) != len(set(profiles)):
        errors.append(f"{path}: profile identifiers must be unique")
    if profiles != sorted(profiles):
        errors.append(f"{path}: entries must be sorted by profile")
    return set(profiles)


def _check_aov_inventory(value: Any, camera_profiles: set[str], errors: list[str]) -> set[tuple[str, str]]:
    path = "aovInventory"
    if not isinstance(value, list):
        errors.append(f"{path}: must be a list")
        return set()
    if not 1 <= len(value) <= 128:
        errors.append(f"{path}: must contain 1 to 128 AOV identifiers")
    pairs: list[tuple[str, str]] = []
    for index, aov in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(aov, dict):
            errors.append(f"{item_path}: must be an object")
            continue
        _check_exact_fields(
            aov,
            frozenset({"name", "cameraProfile", "geometryCompatibilityGroup"}),
            f"{item_path}.",
            errors,
        )
        for field in ("name", "cameraProfile", "geometryCompatibilityGroup"):
            _check_bounded_string(aov.get(field), f"{item_path}.{field}", errors)
        camera = aov.get("cameraProfile")
        name = aov.get("name")
        if isinstance(camera, str) and camera not in camera_profiles:
            errors.append(f"{item_path}.cameraProfile: names an unknown camera profile")
        if isinstance(camera, str) and isinstance(name, str):
            pairs.append((camera, name))
    if len(pairs) != len(set(pairs)):
        errors.append(f"{path}: camera/AOV identifiers must be unique")
    if pairs != sorted(pairs):
        errors.append(f"{path}: entries must be sorted by cameraProfile and name")
    return set(pairs)


def _check_required_evidence(value: Any, aov_pairs: set[tuple[str, str]], errors: list[str]) -> None:
    path = "requiredEvidence"
    if not isinstance(value, list):
        errors.append(f"{path}: must be a list")
        return
    if not 1 <= len(value) <= 128:
        errors.append(f"{path}: must contain 1 to 128 entries")
    pairs: list[tuple[str, str]] = []
    for index, evidence in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(evidence, dict):
            errors.append(f"{item_path}: must be an object")
            continue
        _check_exact_fields(evidence, frozenset({"cameraProfile", "aov"}), f"{item_path}.", errors)
        for field in ("cameraProfile", "aov"):
            _check_bounded_string(evidence.get(field), f"{item_path}.{field}", errors)
        camera = evidence.get("cameraProfile")
        aov = evidence.get("aov")
        if isinstance(camera, str) and isinstance(aov, str):
            pair = (camera, aov)
            pairs.append(pair)
            if pair not in aov_pairs:
                errors.append(f"{item_path}: names an unknown camera/AOV pair")
    if len(pairs) != len(set(pairs)):
        errors.append(f"{path}: entries must be unique")
    if pairs != sorted(pairs):
        errors.append(f"{path}: entries must be sorted by cameraProfile and aov")


def _validate_structure(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["ReviewRun: must be an object"]
    _check_exact_fields(value, ROOT_FIELDS, "", errors)
    if value.get("schema") != REVIEW_RUN_SCHEMA:
        errors.append(f"schema: must equal {REVIEW_RUN_SCHEMA!r}")
    if isinstance(value.get("schemaVersion"), bool) or value.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"schemaVersion: unsupported version; expected {SCHEMA_VERSION}")
    _check_contract(value.get("contract"), errors)
    _check_sha256(value.get("contractSha256"), "contractSha256", errors)
    if isinstance(value.get("contract"), dict):
        try:
            measured_contract_hash = hashlib.sha256(_canonical_json_bytes(value["contract"])).hexdigest()
        except (TypeError, ValueError):
            errors.append("contract: must contain only canonical JSON values")
        else:
            if value.get("contractSha256") != measured_contract_hash:
                errors.append("contractSha256: must match the canonical embedded contract")
    _check_timestamp(value.get("createdAt"), "createdAt", errors)

    lineage = value.get("lineage")
    if not isinstance(lineage, dict):
        errors.append("lineage: must be an object")
    else:
        _check_exact_fields(lineage, LINEAGE_FIELDS, "lineage.", errors)
        if lineage.get("schema") != ARTIFACT_LINEAGE_SCHEMA:
            errors.append(f"lineage.schema: must equal {ARTIFACT_LINEAGE_SCHEMA!r}")
        _check_code_identity(lineage.get("code"), errors)
        for field in ("build", "replay", "verifier", "canonicalPlanPacket", "evidenceManifest", "geometry"):
            _check_file_identity(lineage.get(field), f"lineage.{field}", errors)
        truth_hash = lineage.get("truthHash")
        _check_truth_hash(truth_hash, "lineage.truthHash", errors)
        _check_truth_verification(lineage.get("truthVerification"), truth_hash, errors)
        if lineage.get("workflowRevision") != WORKFLOW_REVISION:
            errors.append(f"lineage.workflowRevision: must equal {WORKFLOW_REVISION!r}")
        generation = lineage.get("generation")
        if not isinstance(generation, dict):
            errors.append("lineage.generation: must be an object")
        else:
            _check_exact_fields(generation, frozenset({"provider", "checkpoint", "retarget"}), "lineage.generation.", errors)
            for field in ("provider", "checkpoint", "retarget"):
                _check_file_identity(generation.get(field), f"lineage.generation.{field}", errors)
        _check_sha256(lineage.get("geometryIdentitySha256"), "lineage.geometryIdentitySha256", errors)
        _check_produced_artifacts(lineage.get("producedArtifactInventory"), lineage, errors)

    camera_profiles = _check_camera_inventory(value.get("cameraInventory"), errors)
    aov_pairs = _check_aov_inventory(value.get("aovInventory"), camera_profiles, errors)
    _check_required_evidence(value.get("requiredEvidence"), aov_pairs, errors)
    authors = value.get("sourceAuthors")
    if not isinstance(authors, list) or not 1 <= len(authors) <= 64:
        errors.append("sourceAuthors: must be a list of 1 to 64 identifiers")
    else:
        for index, author in enumerate(authors):
            _check_bounded_string(author, f"sourceAuthors[{index}]", errors)
        if any(not isinstance(author, str) for author in authors) or authors != sorted(set(authors)):
            errors.append("sourceAuthors: identifiers must be sorted and unique")
    decision_head = value.get("decisionChainHeadSha256")
    if decision_head is not None:
        _check_sha256(decision_head, "decisionChainHeadSha256", errors)
    run_id = value.get("runId")
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        errors.append("runId: must be 20 lowercase hexadecimal characters")
    _check_sha256(value.get("runFingerprintSha256"), "runFingerprintSha256", errors)
    if all(field in value for field in IDENTITY_FIELDS):
        try:
            identity = {field: value[field] for field in IDENTITY_FIELDS}
            fingerprint = hashlib.sha256(_canonical_json_bytes(identity)).hexdigest()
        except (TypeError, ValueError):
            errors.append("ReviewRun identity: must contain only canonical JSON values")
        else:
            if value.get("runFingerprintSha256") != fingerprint or value.get("runId") != fingerprint[:20]:
                errors.append("runFingerprintSha256/runId: must match the canonical ReviewRun identity")
    return errors


def _pass_eligibility_errors(value: dict[str, Any]) -> list[str]:
    lineage = value["lineage"]
    code = lineage["code"]
    errors: list[str] = []
    revision = code.get("revision")
    if not isinstance(revision, str) or _COMMIT_SHA_RE.fullmatch(revision) is None:
        errors.append("draft-only: lineage.code.revision must bind a full commit SHA for pass eligibility")
    if code.get("reachable") is not True:
        errors.append("draft-only: lineage.code.reachable must be true for pass eligibility")
    if code.get("trackedClean") is not True:
        errors.append("draft-only: lineage.code.trackedClean must be true for pass eligibility")
    try:
        expected_tool_profile = _tool_profile_sha256()
    except OSError:
        errors.append("draft-only: ForgeLens tool profile cannot be measured for pass eligibility")
    else:
        if code.get("toolProfileSha256") != expected_tool_profile:
            errors.append("draft-only: lineage.code.toolProfileSha256 does not match the active ForgeLens tool")
    clean_code_identities = {
        "workingTreeDiffSha256": _CLEAN_DIFF_SHA256,
        "stagedDiffSha256": _CLEAN_DIFF_SHA256,
        "untrackedInventorySha256": _EMPTY_UNTRACKED_INVENTORY_SHA256,
    }
    for field, expected in clean_code_identities.items():
        if code.get(field) != expected:
            errors.append(f"draft-only: lineage.code.{field} must bind the canonical clean identity")
    for components in BOUND_INPUT_PATHS:
        identity: Any = lineage
        for component in components:
            identity = identity[component]
        if identity.get("repositoryState") != "tracked-clean":
            role = ".".join(components)
            errors.append(
                f"draft-only: lineage input {role!r} must declare repositoryState 'tracked-clean' for pass eligibility"
            )
    for index, artifact in enumerate(lineage["producedArtifactInventory"]):
        if artifact.get("repositoryState") != "tracked-clean":
            errors.append(
                f"draft-only: produced artifact {index} must declare repositoryState 'tracked-clean' for pass eligibility"
            )
    return errors


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(
            ("git", *arguments),
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            byte_count += len(chunk)
    return digest.hexdigest(), byte_count


def _bound_file_identities(lineage: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    identities = [
        ("build", lineage["build"]),
        ("replay", lineage["replay"]),
        ("verifier", lineage["verifier"]),
        ("canonicalPlanPacket", lineage["canonicalPlanPacket"]),
        ("evidenceManifest", lineage["evidenceManifest"]),
        ("generation.provider", lineage["generation"]["provider"]),
        ("generation.checkpoint", lineage["generation"]["checkpoint"]),
        ("generation.retarget", lineage["generation"]["retarget"]),
        ("geometry", lineage["geometry"]),
    ]
    identities.extend(
        (f"producedArtifactInventory[{index}]", artifact)
        for index, artifact in enumerate(lineage["producedArtifactInventory"])
    )
    return identities


def _repository_evidence_errors(value: dict[str, Any], repository_root: str | Path) -> list[str]:
    errors: list[str] = []
    try:
        root = Path(repository_root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        return ["draft-only: repository root is unavailable for pass eligibility"]
    if not root.is_dir():
        return ["draft-only: repository root must identify a directory"]

    top_level = _git(root, "rev-parse", "--show-toplevel")
    if top_level is None or top_level.returncode != 0:
        return ["draft-only: repository root is not a readable Git worktree"]
    try:
        observed_top_level = Path(top_level.stdout.decode("utf-8").strip()).resolve(strict=True)
    except (OSError, RuntimeError, UnicodeDecodeError, ValueError):
        return ["draft-only: repository root returned an invalid Git worktree path"]
    if observed_top_level != root:
        return ["draft-only: repository root must equal the Git worktree top level"]

    lineage = value["lineage"]
    code = lineage["code"]
    revision = code["revision"]
    head = _git(root, "rev-parse", "--verify", "HEAD")
    commit = _git(root, "cat-file", "-e", f"{revision}^{{commit}}")
    reachable = _git(root, "merge-base", "--is-ancestor", revision, "HEAD")
    if head is None or head.returncode != 0:
        errors.append("draft-only: repository HEAD cannot be resolved")
    else:
        try:
            observed_head = head.stdout.decode("ascii").strip()
        except UnicodeDecodeError:
            observed_head = ""
        if observed_head != revision:
            errors.append("draft-only: lineage.code.revision does not match repository HEAD")
    if commit is None or commit.returncode != 0 or reachable is None or reachable.returncode != 0:
        errors.append("draft-only: lineage.code.revision is not a reachable repository commit")

    working_diff = _git(root, "diff", "--binary", "--no-ext-diff")
    staged_diff = _git(root, "diff", "--cached", "--binary", "--no-ext-diff")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if working_diff is None or working_diff.returncode != 0:
        errors.append("draft-only: repository working-tree diff identity cannot be measured")
    elif hashlib.sha256(working_diff.stdout).hexdigest() != code["workingTreeDiffSha256"]:
        errors.append("draft-only: lineage.code.workingTreeDiffSha256 does not match repository evidence")
    if staged_diff is None or staged_diff.returncode != 0:
        errors.append("draft-only: repository staged diff identity cannot be measured")
    elif hashlib.sha256(staged_diff.stdout).hexdigest() != code["stagedDiffSha256"]:
        errors.append("draft-only: lineage.code.stagedDiffSha256 does not match repository evidence")

    untracked_inventory: list[dict[str, Any]] = []
    if untracked is None or untracked.returncode != 0:
        errors.append("draft-only: repository untracked inventory cannot be measured")
    else:
        try:
            relative_paths = sorted(
                entry.decode("utf-8")
                for entry in untracked.stdout.split(b"\0")
                if entry and not entry.startswith(b"docs/reports/forgelens_review_runs/")
            )
            for relative in relative_paths:
                path = root / relative
                if path.is_file() and not path.is_symlink():
                    sha256, byte_count = _sha256_file(path)
                    untracked_inventory.append({"path": relative, "sha256": sha256, "bytes": byte_count})
            observed_untracked_hash = hashlib.sha256(_canonical_json_bytes(untracked_inventory)).hexdigest()
        except (OSError, RuntimeError, UnicodeDecodeError, ValueError):
            errors.append("draft-only: repository untracked inventory contains unreadable evidence")
        else:
            if observed_untracked_hash != code["untrackedInventorySha256"]:
                errors.append("draft-only: lineage.code.untrackedInventorySha256 does not match repository evidence")
            if untracked_inventory:
                errors.append("draft-only: repository contains untracked inputs")

    for role, identity in _bound_file_identities(lineage):
        relative = identity["path"]
        candidate = root / relative
        try:
            resolved = candidate.resolve(strict=True)
            inside_root = resolved.is_relative_to(root)
        except (OSError, RuntimeError):
            resolved = candidate
            inside_root = False
        if not inside_root or candidate.is_symlink() or not resolved.is_file():
            errors.append(f"draft-only: lineage input {role!r} is not a regular file inside the repository")
            continue
        try:
            observed_sha256, observed_bytes = _sha256_file(resolved)
        except OSError:
            errors.append(f"draft-only: lineage input {role!r} cannot be read from the repository")
            continue
        if observed_sha256 != identity["sha256"] or observed_bytes != identity["bytes"]:
            errors.append(f"draft-only: lineage input {role!r} bytes do not match repository evidence")
        tracked = _git(root, "ls-files", "--error-unmatch", "--", relative)
        status = _git(root, "status", "--porcelain=v1", "--untracked-files=all", "--", relative)
        if tracked is None or tracked.returncode != 0 or status is None or status.returncode != 0 or status.stdout:
            errors.append(f"draft-only: lineage input {role!r} is not tracked-clean in the repository")
    return errors


def validate_review_run(value: Any) -> tuple[bool, list[str]]:
    """Validate one ReviewRun without mutating it or persisting any bytes."""

    errors = _validate_structure(value)
    return not errors, errors


def validate_pass_eligibility(
    value: Any,
    repository_root: str | Path | None = None,
) -> tuple[bool, list[str]]:
    """Apply structural validation plus live Git/bytes promotion evidence."""

    errors = _validate_structure(value)
    if not errors:
        errors.extend(_pass_eligibility_errors(value))
        if repository_root is None:
            errors.append("draft-only: repository root is required to verify pass eligibility")
        else:
            errors.extend(_repository_evidence_errors(value, repository_root))
    return not errors, errors
