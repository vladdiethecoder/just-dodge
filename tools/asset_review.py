#!/usr/bin/env python3
"""Serve the dependency-free Just Dodge Asset Review Studio on loopback.

Usage:
    python3 tools/asset_review.py
    python3 tools/asset_review.py --asset assets/source/meshy/w0_sword/assembled_001/model.glb
    python3 tools/asset_review.py --port 4177 --no-open

The server indexes repository GLB evidence and stores review state under
qa_runs/asset_reviews/. It never mutates source assets.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import json
import math
import mimetypes
import os
import re
import secrets
import subprocess
import struct
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
MAX_REQUEST_BYTES = 1_000_000
MAX_COMMENTS = 500
MAX_COMMENT_CHARS = 8_000
MAX_EVIDENCE_BYTES = 12 * 1024 * 1024
SESSION_TTL_SECONDS = 4 * 60 * 60
STATIC_DIR = Path(__file__).with_name("asset_review")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
DECISIONS = {"pending", "approved", "changes-requested", "rejected"}
CATEGORIES = {
    "silhouette",
    "topology",
    "materials",
    "rigging",
    "scale",
    "performance",
    "gameplay",
    "pipeline",
    "other",
}
SEVERITIES = {"note", "minor", "major", "blocker"}
STATUSES = {"open", "resolved", "wont-fix"}
CHECK_STATES = {"unchecked", "pass", "needs-work", "not-applicable"}
NEURAL_STATUSES = {"not-evaluated", "awaiting-neural-review", "pass", "fail"}
NEURAL_CRITERIA = {
    "semanticIntent",
    "temporalCoherence",
    "footContacts",
    "balance",
    "deformation",
    "weaponGrip",
    "transitionContinuity",
    "physicalPlausibility",
}
COMPONENT_COUNTS = {
    5120: ("b", 1),
    5121: ("B", 1),
    5122: ("h", 2),
    5123: ("H", 2),
    5125: ("I", 4),
    5126: ("f", 4),
}
TYPE_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "Cargo.toml").is_file() and (candidate / "assets").is_dir():
            return candidate
    raise RuntimeError("could not locate Just Dodge repository root")


def safe_repo_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise ValueError("path must be a non-empty repository-relative string")
    candidate_input = Path(relative)
    if candidate_input.is_absolute():
        raise ValueError("absolute paths are not allowed")
    root = root.resolve()
    candidate = (root / candidate_input).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("path escapes repository root") from exc
    return candidate


def stable_asset_id(relative: str) -> str:
    return hashlib.sha256(relative.encode("utf-8")).hexdigest()[:20]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_command(root: Path, arguments: list[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-C", os.fspath(root), *arguments],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(arguments, 127, b"", b"")


def _tool_profile_sha256() -> str:
    digest = hashlib.sha256()
    files = (Path(__file__), STATIC_DIR / "index.html", STATIC_DIR / "styles.css", STATIC_DIR / "app.js")
    for path in files:
        payload = path.read_bytes()
        label = path.name.encode("utf-8")
        digest.update(struct.pack("<I", len(label)))
        digest.update(label)
        digest.update(struct.pack("<Q", len(payload)))
        digest.update(payload)
    return digest.hexdigest()


def artifact_identity(
    root: Path,
    asset_path: str,
    *,
    tool_profile: str = "forgelens.repository-glb/v1",
    capture_profile: str = "repository-glb/catalog-v2",
    parent_evidence_sha256: list[str] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    path = safe_repo_path(root, asset_path)
    if not path.is_file():
        raise ValueError("artifact must name an existing repository file")
    canonical_path = path.relative_to(root).as_posix()
    if asset_path != canonical_path:
        raise ValueError("artifact path must use its canonical repository-relative spelling")
    parent_hashes = sorted(
        {
            _hex_digest(value, f"parent_evidence_sha256[{index}]")
            for index, value in enumerate(parent_evidence_sha256 or [])
        }
    )
    stat_before = path.stat()
    content_sha256 = _sha256_file(path)
    stat_after = path.stat()
    if (stat_before.st_dev, stat_before.st_ino, stat_before.st_size, stat_before.st_mtime_ns) != (
        stat_after.st_dev,
        stat_after.st_ino,
        stat_after.st_size,
        stat_after.st_mtime_ns,
    ):
        raise ValueError("artifact changed while its identity was being measured")
    head_result = _git_command(root, ["rev-parse", "HEAD"])
    head = head_result.stdout.decode("ascii", "replace").strip() if head_result.returncode == 0 else None
    tracked_result = _git_command(root, ["ls-files", "--error-unmatch", "--", asset_path])
    if head is None:
        repository_state = "outside-git"
        relevant_diff_sha256 = content_sha256
    elif tracked_result.returncode != 0:
        repository_state = "untracked"
        relevant_diff_sha256 = content_sha256
    else:
        diff_result = _git_command(root, ["diff", "--binary", "--no-ext-diff", "HEAD", "--", asset_path])
        if diff_result.returncode != 0:
            repository_state = "unavailable"
            relevant_diff_sha256 = None
        elif diff_result.stdout:
            repository_state = "tracked-modified"
            relevant_diff_sha256 = hashlib.sha256(diff_result.stdout).hexdigest()
        else:
            repository_state = "tracked-clean"
            relevant_diff_sha256 = None
    if head is not None:
        confirmed = _git_command(root, ["rev-parse", "HEAD"])
        confirmed_head = confirmed.stdout.decode("ascii", "replace").strip() if confirmed.returncode == 0 else None
        if confirmed_head != head:
            raise ValueError("repository revision changed while artifact identity was being measured")
    content_identity = {
        "logicalPath": asset_path,
        "contentSha256": content_sha256,
        "bytes": stat_after.st_size,
    }
    content_encoded = json.dumps(
        content_identity, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    ).encode("utf-8")
    identity = {
        "schema": "forgelens.artifact/v1",
        "logicalPath": asset_path,
        "logicalId": stable_asset_id(asset_path),
        "contentSha256": content_sha256,
        "bytes": stat_after.st_size,
        "repository": {
            "head": head,
            "state": repository_state,
            "relevantDiffSha256": relevant_diff_sha256,
        },
        "toolProfile": tool_profile,
        "toolProfileSha256": _tool_profile_sha256(),
        "captureProfile": capture_profile,
        "parentEvidenceSha256": parent_hashes,
    }
    encoded = json.dumps(identity, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
    identity["fingerprintSha256"] = hashlib.sha256(encoded).hexdigest()
    identity["versionId"] = hashlib.sha256(content_encoded).hexdigest()[:20]
    return identity


def _read_glb_json(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12:
            raise ValueError("truncated GLB header")
        magic, version, total_length = struct.unpack("<4sII", header)
        if magic != b"glTF" or version != 2:
            raise ValueError("only GLB 2.0 is supported")
        if total_length != path.stat().st_size:
            raise ValueError("GLB declared length does not match file size")
        chunk_header = handle.read(8)
        if len(chunk_header) != 8:
            raise ValueError("missing GLB JSON chunk")
        chunk_length, chunk_type = struct.unpack("<II", chunk_header)
        if chunk_type != 0x4E4F534A or chunk_length > 64 * 1024 * 1024:
            raise ValueError("invalid GLB JSON chunk")
        payload = handle.read(chunk_length)
        if len(payload) != chunk_length:
            raise ValueError("truncated GLB JSON chunk")
    document = json.loads(payload.decode("utf-8").rstrip("\x00 \t\r\n"))
    if not isinstance(document, dict):
        raise ValueError("GLB JSON root must be an object")
    return document


def _accessor_count(document: dict[str, Any], index: Any) -> int:
    if not isinstance(index, int):
        return 0
    accessors = document.get("accessors", [])
    if not isinstance(accessors, list) or not 0 <= index < len(accessors):
        return 0
    accessor = accessors[index]
    if not isinstance(accessor, dict):
        return 0
    count = accessor.get("count", 0)
    return count if isinstance(count, int) and count >= 0 else 0


def measure_glb(path: Path) -> dict[str, Any]:
    document = _read_glb_json(path)
    meshes = document.get("meshes", []) if isinstance(document.get("meshes", []), list) else []
    vertices = 0
    triangles = 0
    primitives = 0
    for mesh in meshes:
        if not isinstance(mesh, dict):
            continue
        for primitive in mesh.get("primitives", []):
            if not isinstance(primitive, dict):
                continue
            primitives += 1
            attributes = primitive.get("attributes", {})
            position_count = _accessor_count(document, attributes.get("POSITION") if isinstance(attributes, dict) else None)
            vertices += position_count
            mode = primitive.get("mode", 4)
            element_count = _accessor_count(document, primitive.get("indices")) or position_count
            if mode == 4:
                triangles += element_count // 3
            elif mode in (5, 6) and element_count >= 3:
                triangles += element_count - 2
    asset = document.get("asset", {}) if isinstance(document.get("asset"), dict) else {}
    return {
        "bytes": path.stat().st_size,
        "meshes": len(meshes),
        "nodes": len(document.get("nodes", [])) if isinstance(document.get("nodes"), list) else 0,
        "primitives": primitives,
        "vertices": vertices,
        "triangles": triangles,
        "materials": len(document.get("materials", [])) if isinstance(document.get("materials"), list) else 0,
        "textures": len(document.get("textures", [])) if isinstance(document.get("textures"), list) else 0,
        "animations": len(document.get("animations", [])) if isinstance(document.get("animations"), list) else 0,
        "skins": len(document.get("skins", [])) if isinstance(document.get("skins"), list) else 0,
        "generator": str(asset.get("generator", "unknown")),
        "extensions": [str(value) for value in document.get("extensionsUsed", [])]
        if isinstance(document.get("extensionsUsed"), list)
        else [],
    }


def asset_family(relative: Path) -> str:
    parts = relative.parts
    if "meshy" in parts:
        index = parts.index("meshy")
        if index + 1 < len(parts):
            return parts[index + 1]
    return relative.parent.name or relative.stem


def asset_stage(relative: Path) -> str:
    lowered = [part.lower() for part in relative.parts]
    stage_labels = (
        ("reference", "Reference"),
        ("candidate", "Generated candidate"),
        ("basetopo", "DCC / base topology"),
        ("retopo", "DCC / retopology"),
        ("assembled", "DCC / assembled"),
        ("rigged", "DCC / rigged"),
        ("pose_carrier", "DCC / pose carrier"),
        ("cooked", "Runtime cooked"),
    )
    for marker, label in stage_labels:
        if any(marker in part for part in lowered):
            return label
    return "Source model"


def _evidence_images(root: Path, model: Path, family: str) -> list[str]:
    candidates: list[Path] = []
    for parent in (model.parent, model.parent / "qa"):
        if parent.is_dir():
            candidates.extend(path for path in parent.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)
    if len(candidates) < 4:
        family_root = root / "assets" / "source" / "meshy" / family
        if family_root.is_dir():
            candidates.extend(path for path in family_root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)
    unique = sorted({path.resolve() for path in candidates}, key=lambda path: (len(path.parts), path.as_posix()))
    return [path.relative_to(root).as_posix() for path in unique[:12]]


def build_catalog(root: Path) -> dict[str, Any]:
    root = root.resolve()
    assets_root = root / "assets"
    records: list[dict[str, Any]] = []
    if not assets_root.is_dir():
        return {"schemaVersion": SCHEMA_VERSION, "generatedAt": utc_now(), "assets": [], "families": []}
    for model in sorted(assets_root.rglob("*.glb")):
        relative = model.relative_to(root)
        relative_text = relative.as_posix()
        family = asset_family(relative)
        artifact = artifact_identity(root, relative_text)
        try:
            metrics = measure_glb(model)
            error = None
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            metrics = {"bytes": model.stat().st_size}
            error = str(exc)
        stat = model.stat()
        records.append(
            {
                "id": artifact["versionId"],
                "logicalId": artifact["logicalId"],
                "name": family.replace("_", " "),
                "family": family,
                "stage": asset_stage(relative),
                "path": relative_text,
                "artifact": artifact,
                "modifiedAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
                "metrics": metrics,
                "evidenceImages": _evidence_images(root, model, family),
                "error": error,
            }
        )
    stage_order = {
        "Reference": 0,
        "Generated candidate": 1,
        "Source model": 2,
        "DCC / base topology": 3,
        "DCC / retopology": 4,
        "DCC / assembled": 5,
        "DCC / rigged": 6,
        "DCC / pose carrier": 7,
        "Runtime cooked": 8,
    }
    records.sort(key=lambda item: (item["family"], stage_order.get(item["stage"], 99), item["path"]))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "assets": records,
        "families": sorted({record["family"] for record in records}),
    }


def _bounded_string(value: Any, field: str, allowed: set[str] | None = None, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    value = value.strip()
    if len(value) > maximum:
        raise ValueError(f"{field} exceeds {maximum} characters")
    if allowed is not None and value not in allowed:
        raise ValueError(f"unsupported {field}: {value}")
    return value


def _hex_digest(value: Any, field: str) -> str:
    value = _bounded_string(value, field, maximum=64)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be 64 lowercase hexadecimal characters")
    return value


def validate_artifact(value: Any, asset_path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("artifact must be an object")
    if value.get("schema") != "forgelens.artifact/v1":
        raise ValueError("artifact.schema must be forgelens.artifact/v1")
    logical_path = _bounded_string(value.get("logicalPath"), "artifact.logicalPath", maximum=1_000)
    if logical_path != asset_path:
        raise ValueError("artifact logical path does not match assetPath")
    logical_id = _bounded_string(value.get("logicalId"), "artifact.logicalId", maximum=20)
    if logical_id != stable_asset_id(asset_path):
        raise ValueError("artifact logical id does not match assetPath")
    byte_count = value.get("bytes")
    if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 0:
        raise ValueError("artifact.bytes must be a non-negative integer")
    repository_input = value.get("repository")
    if not isinstance(repository_input, dict):
        raise ValueError("artifact.repository must be an object")
    head = repository_input.get("head")
    if head is not None:
        head = _bounded_string(head, "artifact.repository.head", maximum=64)
    repository_state = _bounded_string(
        repository_input.get("state"),
        "artifact.repository.state",
        {"tracked-clean", "tracked-modified", "untracked", "outside-git", "unavailable"},
    )
    relevant_diff = repository_input.get("relevantDiffSha256")
    if relevant_diff is not None:
        relevant_diff = _hex_digest(relevant_diff, "artifact.repository.relevantDiffSha256")
    capture_profile = _bounded_string(value.get("captureProfile"), "artifact.captureProfile", maximum=200)
    parents_input = value.get("parentEvidenceSha256", [])
    if not isinstance(parents_input, list) or len(parents_input) > 64:
        raise ValueError("artifact.parentEvidenceSha256 must be a list of at most 64 hashes")
    parent_hashes = [
        _hex_digest(parent, f"artifact.parentEvidenceSha256[{index}]")
        for index, parent in enumerate(parents_input)
    ]
    if parent_hashes != sorted(set(parent_hashes)):
        raise ValueError("artifact.parentEvidenceSha256 must be sorted and unique")
    identity = {
        "schema": "forgelens.artifact/v1",
        "logicalPath": logical_path,
        "logicalId": logical_id,
        "contentSha256": _hex_digest(value.get("contentSha256"), "artifact.contentSha256"),
        "bytes": byte_count,
        "repository": {
            "head": head,
            "state": repository_state,
            "relevantDiffSha256": relevant_diff,
        },
        "toolProfile": _bounded_string(value.get("toolProfile"), "artifact.toolProfile", maximum=200),
        "toolProfileSha256": _hex_digest(value.get("toolProfileSha256"), "artifact.toolProfileSha256"),
        "captureProfile": capture_profile,
        "parentEvidenceSha256": parent_hashes,
    }
    encoded = json.dumps(identity, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
    fingerprint = hashlib.sha256(encoded).hexdigest()
    content_identity = {
        "logicalPath": logical_path,
        "contentSha256": identity["contentSha256"],
        "bytes": byte_count,
    }
    content_encoded = json.dumps(
        content_identity, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    ).encode("utf-8")
    version_id = hashlib.sha256(content_encoded).hexdigest()[:20]
    if value.get("fingerprintSha256") != fingerprint or value.get("versionId") != version_id:
        raise ValueError("artifact fingerprint does not match its canonical identity")
    identity["fingerprintSha256"] = fingerprint
    identity["versionId"] = version_id
    return identity


def _finite_vector(value: Any, field: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{field} must contain exactly three numbers")
    result = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)) or not math.isfinite(float(component)):
            raise ValueError(f"{field} contains a non-finite component")
        if abs(float(component)) > 1_000_000.0:
            raise ValueError(f"{field} component exceeds safety bound")
        result.append(float(component))
    return result


def validate_review(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("review payload must be an object")
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"schemaVersion must be {SCHEMA_VERSION}")
    asset_path = _bounded_string(payload.get("assetPath"), "assetPath", maximum=1_000)
    if Path(asset_path).is_absolute() or ".." in Path(asset_path).parts:
        raise ValueError("assetPath must remain repository-relative")
    artifact = validate_artifact(payload.get("artifact"), asset_path)
    decision = _bounded_string(payload.get("decision", "pending"), "decision", DECISIONS)
    checklist_input = payload.get("checklist", {})
    if not isinstance(checklist_input, dict) or len(checklist_input) > 64:
        raise ValueError("checklist must be an object with at most 64 entries")
    checklist: dict[str, str] = {}
    for key, value in checklist_input.items():
        clean_key = _bounded_string(key, "checklist key", maximum=80)
        checklist[clean_key] = _bounded_string(value, f"checklist.{clean_key}", CHECK_STATES)
    comments_input = payload.get("comments", [])
    if not isinstance(comments_input, list) or len(comments_input) > MAX_COMMENTS:
        raise ValueError(f"comments must be a list with at most {MAX_COMMENTS} entries")
    comments: list[dict[str, Any]] = []
    for index, raw in enumerate(comments_input):
        if not isinstance(raw, dict):
            raise ValueError(f"comments[{index}] must be an object")
        point = raw.get("point")
        normalized_point = None
        if point is not None:
            if not isinstance(point, dict):
                raise ValueError(f"comments[{index}].point must be an object")
            normalized_point = {
                "world": _finite_vector(point.get("world"), f"comments[{index}].point.world"),
                "normal": _finite_vector(point.get("normal", [0.0, 1.0, 0.0]), f"comments[{index}].point.normal"),
            }
        comments.append(
            {
                "id": _bounded_string(raw.get("id"), f"comments[{index}].id", maximum=100),
                "text": _bounded_string(raw.get("text"), f"comments[{index}].text", maximum=MAX_COMMENT_CHARS),
                "category": _bounded_string(raw.get("category", "other"), f"comments[{index}].category", CATEGORIES),
                "severity": _bounded_string(raw.get("severity", "note"), f"comments[{index}].severity", SEVERITIES),
                "status": _bounded_string(raw.get("status", "open"), f"comments[{index}].status", STATUSES),
                "author": _bounded_string(raw.get("author", "human"), f"comments[{index}].author", maximum=100),
                "createdAt": _bounded_string(raw.get("createdAt", utc_now()), f"comments[{index}].createdAt", maximum=80),
                "point": normalized_point,
                "camera": raw.get("camera") if isinstance(raw.get("camera"), dict) else None,
            }
        )
    neural_input = payload.get("neuralMotion")
    neural_motion = None
    if neural_input is not None:
        if not isinstance(neural_input, dict):
            raise ValueError("neuralMotion must be an object")
        neural_status = _bounded_string(
            neural_input.get("status", "not-evaluated"), "neuralMotion.status", NEURAL_STATUSES
        )
        criteria_input = neural_input.get("criteria", {})
        if not isinstance(criteria_input, dict) or not set(criteria_input).issubset(NEURAL_CRITERIA):
            raise ValueError("neuralMotion.criteria contains unsupported keys")
        criteria: dict[str, dict[str, Any]] = {}
        for key, raw in criteria_input.items():
            if not isinstance(raw, dict):
                raise ValueError(f"neuralMotion.criteria.{key} must be an object")
            verdict = _bounded_string(
                raw.get("verdict", "not-evaluated"),
                f"neuralMotion.criteria.{key}.verdict",
                {"not-evaluated", "pass", "fail"},
            )
            score = raw.get("score")
            if score is not None and (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(float(score))
                or not 0.0 <= float(score) <= 1.0
            ):
                raise ValueError(f"neuralMotion.criteria.{key}.score must be within [0, 1]")
            criteria[key] = {
                "verdict": verdict,
                "score": None if score is None else float(score),
                "finding": str(raw.get("finding", ""))[:2_000],
            }
        neural_motion = {
            "status": neural_status,
            "clip": str(neural_input.get("clip", ""))[:200],
            "model": str(neural_input.get("model", ""))[:200],
            "evaluatedAt": str(neural_input.get("evaluatedAt", ""))[:80] or None,
            "evidencePath": str(neural_input.get("evidencePath", ""))[:1_000] or None,
            "evidenceSha256": str(neural_input.get("evidenceSha256", ""))[:64] or None,
            "summary": str(neural_input.get("summary", ""))[:8_000],
            "criteria": criteria,
        }
    report_summary = str(payload.get("reportSummary", ""))[:MAX_COMMENT_CHARS]
    submission_input = payload.get("submission")
    submission = None
    if submission_input is not None:
        if not isinstance(submission_input, dict):
            raise ValueError("submission must be an object")
        receipt_id = _bounded_string(submission_input.get("receiptId"), "submission.receiptId", maximum=20)
        content_sha256 = _bounded_string(
            submission_input.get("contentSha256"), "submission.contentSha256", maximum=64
        )
        if len(receipt_id) != 20 or any(character not in "0123456789abcdef" for character in receipt_id):
            raise ValueError("submission.receiptId must be 20 lowercase hexadecimal characters")
        if len(content_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in content_sha256
        ):
            raise ValueError("submission.contentSha256 must be 64 lowercase hexadecimal characters")
        if receipt_id != content_sha256[:20]:
            raise ValueError("submission.receiptId must match the content digest prefix")
        submission = {
            "receiptId": receipt_id,
            "contentSha256": content_sha256,
            "submittedAt": _bounded_string(
                submission_input.get("submittedAt"), "submission.submittedAt", maximum=80
            ),
            "submittedBy": _bounded_string(
                submission_input.get("submittedBy", "human"), "submission.submittedBy", maximum=100
            ),
        }
    task_plan_input = payload.get("taskPlan")
    task_plan = None
    if task_plan_input is not None:
        if not isinstance(task_plan_input, dict):
            raise ValueError("taskPlan must be an object")
        tasks_input = task_plan_input.get("tasks", [])
        if not isinstance(tasks_input, list) or not 1 <= len(tasks_input) <= 64:
            raise ValueError("taskPlan.tasks must contain 1 to 64 tasks")
        tasks = []
        for index, raw in enumerate(tasks_input):
            if not isinstance(raw, dict):
                raise ValueError(f"taskPlan.tasks[{index}] must be an object")
            criteria = raw.get("acceptanceCriteria", [])
            sources = raw.get("sourceCommentIds", [])
            dependencies = raw.get("dependencies", [])
            if not all(isinstance(items, list) and len(items) <= 32 for items in (criteria, sources, dependencies)):
                raise ValueError(f"taskPlan.tasks[{index}] lists must contain at most 32 entries")
            tasks.append(
                {
                    "id": _bounded_string(raw.get("id"), f"taskPlan.tasks[{index}].id", maximum=80),
                    "title": _bounded_string(raw.get("title"), f"taskPlan.tasks[{index}].title", maximum=200),
                    "description": _bounded_string(
                        raw.get("description"), f"taskPlan.tasks[{index}].description", maximum=2_000
                    ),
                    "priority": _bounded_string(
                        raw.get("priority", "medium"),
                        f"taskPlan.tasks[{index}].priority",
                        {"critical", "high", "medium", "low"},
                    ),
                    "acceptanceCriteria": [str(item)[:500] for item in criteria],
                    "sourceCommentIds": [str(item)[:100] for item in sources],
                    "dependencies": [str(item)[:80] for item in dependencies],
                }
            )
        adversarial = task_plan_input.get("adversarialReview")
        if not isinstance(adversarial, dict):
            raise ValueError("taskPlan.adversarialReview must be an object")
        findings = adversarial.get("findings", [])
        if not isinstance(findings, list) or len(findings) > 64:
            raise ValueError("taskPlan.adversarialReview.findings must be a list of at most 64 entries")
        task_plan = {
            "reportReceiptId": _bounded_string(
                task_plan_input.get("reportReceiptId"), "taskPlan.reportReceiptId", maximum=20
            ),
            "planner": _bounded_string(task_plan_input.get("planner"), "taskPlan.planner", maximum=200),
            "plannedAt": _bounded_string(task_plan_input.get("plannedAt"), "taskPlan.plannedAt", maximum=80),
            "tasks": tasks,
            "adversarialReview": {
                "verdict": _bounded_string(
                    adversarial.get("verdict"), "taskPlan.adversarialReview.verdict", {"pass", "fail"}
                ),
                "reviewer": _bounded_string(
                    adversarial.get("reviewer"), "taskPlan.adversarialReview.reviewer", maximum=200
                ),
                "reviewedAt": _bounded_string(
                    adversarial.get("reviewedAt"), "taskPlan.adversarialReview.reviewedAt", maximum=80
                ),
                "findings": [str(item)[:1_000] for item in findings],
            },
        }
    updated_at = payload.get("updatedAt")
    if updated_at is None:
        updated_at = utc_now()
    else:
        updated_at = _bounded_string(updated_at, "updatedAt", maximum=80)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "assetPath": asset_path,
        "artifact": artifact,
        "decision": decision,
        "checklist": checklist,
        "comments": comments,
        "neuralMotion": neural_motion,
        "reportSummary": report_summary,
        "submission": submission,
        "taskPlan": task_plan,
        "updatedAt": updated_at,
    }


def report_content_sha256(review: dict[str, Any]) -> str:
    content = {
        key: review.get(key)
        for key in ("assetPath", "artifact", "decision", "checklist", "comments", "neuralMotion", "reportSummary")
    }
    encoded = json.dumps(content, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def save_neural_evidence(root: Path, payload: Any, *, captured_by: str = "internal-call") -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("neural evidence payload must be an object")
    asset_path = _bounded_string(payload.get("assetPath"), "assetPath", maximum=1_000)
    safe_repo_path(root, asset_path)
    artifact = validate_artifact(payload.get("artifact"), asset_path)
    current_artifact = artifact_identity(root, asset_path)
    if artifact["fingerprintSha256"] != current_artifact["fingerprintSha256"]:
        raise StaleArtifactError("artifact changed before neural evidence was submitted; reload the exact current version")
    clip = _bounded_string(payload.get("clip", "animation"), "clip", maximum=200)
    data_url = payload.get("pngDataUrl")
    if not isinstance(data_url, str) or not data_url.startswith("data:image/png;base64,"):
        raise ValueError("pngDataUrl must be a base64 PNG data URL")
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("pngDataUrl contains invalid base64") from exc
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("neural evidence is not a PNG")
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise ValueError(f"neural evidence exceeds {MAX_EVIDENCE_BYTES} byte limit")
    digest = hashlib.sha256(raw).hexdigest()
    directory = root.resolve() / "qa_runs" / "asset_reviews" / "evidence" / artifact["versionId"]
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{digest[:20]}.png"
    if not target.exists():
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        except BaseException:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise
    relative = target.relative_to(root.resolve()).as_posix()
    receipt = target.with_suffix(".json")
    receipt.write_text(
        json.dumps(
            {
                "schemaVersion": SCHEMA_VERSION,
                "assetPath": asset_path,
                "artifact": artifact,
                "clip": clip,
                "evidencePath": relative,
                "sha256": digest,
                "bytes": len(raw),
                "createdAt": utc_now(),
                "capturedBy": captured_by,
                "requiredReview": "neural-visual-animation-quality",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"evidencePath": relative, "evidenceSha256": digest}


@dataclass(frozen=True)
class ReplayRunConfig:
    replay_path: str
    verifier_path: str
    capture_paths: tuple[str, ...] = ()


def build_replay_review_run(root: Path, config: ReplayRunConfig) -> dict[str, Any]:
    replay = artifact_identity(root, config.replay_path, capture_profile="m3-replay-v2")
    verifier = artifact_identity(root, config.verifier_path, capture_profile="m3-replay-verifier-v1")
    verifier_path = safe_repo_path(root, config.verifier_path)
    try:
        completed = subprocess.run(
            [str(verifier_path), "--verify", str(safe_repo_path(root, config.replay_path))],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("replay verifier exceeded 30 second limit") from exc
    output = completed.stdout.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        raise ValueError(f"replay verifier failed with exit {completed.returncode}: {output[-2_000:]}")
    match = re.search(r"frames=(\d+) winner=([^ ]+) hash=([0-9a-f]{16})", output)
    if match is None:
        raise ValueError("replay verifier output is missing frames/winner/hash evidence")
    captures = [
        artifact_identity(root, path, capture_profile="replay-visual-capture-v1")
        for path in config.capture_paths
    ]
    verification = {
        "commandProfile": "m3-match-verify-v1",
        "stdoutSha256": hashlib.sha256(completed.stdout).hexdigest(),
        "frames": int(match.group(1)),
        "winner": match.group(2),
        "truthHash": match.group(3),
        "verdict": "PASS",
    }
    identity_payload = {
        "schema": "forgelens.replay-review-run/v1",
        "replayFingerprintSha256": replay["fingerprintSha256"],
        "verifierFingerprintSha256": verifier["fingerprintSha256"],
        "captureFingerprintSha256": [capture["fingerprintSha256"] for capture in captures],
        "verification": verification,
        "toolProfileSha256": _tool_profile_sha256(),
    }
    fingerprint = hashlib.sha256(_canonical_json_bytes(identity_payload)).hexdigest()
    return {
        "schemaVersion": 1,
        "kind": "replay",
        "runId": fingerprint[:20],
        "fingerprintSha256": fingerprint,
        "replay": replay,
        "verifier": verifier,
        "captures": captures,
        "captureSetSha256": hashlib.sha256(
            _canonical_json_bytes([capture["fingerprintSha256"] for capture in captures])
        ).hexdigest(),
        "verification": verification,
        "reviewScope": "presentation-and-evidence-only; deterministic replay remains authoritative",
        "visualStatus": "capture-backed" if captures else "truth-only-no-visual-capture",
        "captureAssociation": (
            "operator-declared; capture bytes are bound but derivation from replay is not machine-proven"
            if captures
            else "none"
        ),
    }


def submit_replay_review(
    root: Path,
    config: ReplayRunConfig,
    payload: Any,
    *,
    submitted_by: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("replay review payload must be an object")
    current = build_replay_review_run(root, config)
    claimed = _bounded_string(
        payload.get("reviewRunFingerprint"), "reviewRunFingerprint", maximum=64
    )
    if claimed != current["fingerprintSha256"]:
        raise StaleArtifactError("replay ReviewRun changed; reload before submitting")
    decision = _bounded_string(
        payload.get("decision"), "decision", {"approved", "changes-requested", "rejected"}
    )
    if decision == "approved" and not current["captures"]:
        raise ValueError("replay approval requires at least one bound visual capture")
    summary = _bounded_string(payload.get("summary", ""), "summary", maximum=MAX_COMMENT_CHARS)
    content = {
        "reviewRunFingerprint": current["fingerprintSha256"],
        "decision": decision,
        "summary": summary,
        "submittedBy": submitted_by,
    }
    digest = hashlib.sha256(_canonical_json_bytes(content)).hexdigest()
    result = {
        "schemaVersion": 1,
        **content,
        "receiptId": digest[:20],
        "contentSha256": digest,
        "submittedAt": utc_now(),
    }
    directory = root / "qa_runs" / "asset_reviews" / "replay_runs" / current["runId"]
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{result['receiptId']}.json"
    encoded = json.dumps(result, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    with tempfile.NamedTemporaryFile(dir=directory, prefix=".tmp-", delete=False) as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.link(temporary, destination)
    except FileExistsError:
        return json.loads(destination.read_text(encoding="utf-8"))
    finally:
        temporary.unlink(missing_ok=True)
    return result


class AuthorityError(RuntimeError):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status


class BrowserAuthority:
    cookie_name = "ForgeLensSession"

    def __init__(
        self,
        bootstrap_token: str,
        *,
        ttl_seconds: int = SESSION_TTL_SECONDS,
        monotonic: Any = time.monotonic,
    ):
        if not bootstrap_token:
            raise ValueError("bootstrap token must not be empty")
        self._bootstrap_digest = hashlib.sha256(bootstrap_token.encode("utf-8")).digest()
        self._ttl_seconds = ttl_seconds
        self._monotonic = monotonic
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def exchange(self, bootstrap_token: str) -> tuple[str, dict[str, str]]:
        supplied = hashlib.sha256(bootstrap_token.encode("utf-8")).digest()
        with self._lock:
            expected = self._bootstrap_digest
            if expected is None or not hmac.compare_digest(expected, supplied):
                raise AuthorityError(HTTPStatus.FORBIDDEN, "bootstrap token is invalid or already used")
            self._bootstrap_digest = None
            session_token = secrets.token_urlsafe(32)
            csrf_token = secrets.token_urlsafe(32)
            actor_id = f"human-browser-{hashlib.sha256(session_token.encode('utf-8')).hexdigest()[:16]}"
            expires_monotonic = self._monotonic() + self._ttl_seconds
            expires_at = datetime.fromtimestamp(time.time() + self._ttl_seconds, timezone.utc).isoformat().replace(
                "+00:00", "Z"
            )
            self._sessions[hashlib.sha256(session_token.encode("utf-8")).hexdigest()] = {
                "actorId": actor_id,
                "csrfToken": csrf_token,
                "expiresMonotonic": expires_monotonic,
                "expiresAt": expires_at,
            }
        return session_token, {"actorId": actor_id, "csrfToken": csrf_token, "expiresAt": expires_at}

    def authorize(self, cookie_header: str | None, csrf_token: str | None = None) -> dict[str, str]:
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header or "")
        except Exception as exc:
            raise AuthorityError(HTTPStatus.UNAUTHORIZED, "browser session cookie is invalid") from exc
        morsel = cookie.get(self.cookie_name)
        if morsel is None:
            raise AuthorityError(HTTPStatus.UNAUTHORIZED, "browser session is required")
        session_key = hashlib.sha256(morsel.value.encode("utf-8")).hexdigest()
        with self._lock:
            record = self._sessions.get(session_key)
            if record is None:
                raise AuthorityError(HTTPStatus.UNAUTHORIZED, "browser session is invalid")
            if self._monotonic() >= record["expiresMonotonic"]:
                del self._sessions[session_key]
                raise AuthorityError(HTTPStatus.UNAUTHORIZED, "browser session expired")
            result = {
                "actorId": record["actorId"],
                "csrfToken": record["csrfToken"],
                "expiresAt": record["expiresAt"],
            }
        if csrf_token is not None and not hmac.compare_digest(result["csrfToken"], csrf_token):
            raise AuthorityError(HTTPStatus.FORBIDDEN, "CSRF token is missing or invalid")
        return result


class StaleArtifactError(ValueError):
    pass


class ReviewStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.directory = self.root / "qa_runs" / "asset_reviews"
        self._lock = threading.RLock()

    def _path(self, asset_path: str) -> Path:
        return self.directory / f"{stable_asset_id(asset_path)}.json"

    def _stored_submission(self, asset_path: str) -> Any:
        path = self._path(asset_path)
        if not path.is_file():
            return None
        with self._lock:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        return payload.get("submission") if isinstance(payload, dict) else None

    def _empty(
        self,
        asset_path: str,
        artifact: dict[str, Any],
        superseded: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "assetPath": asset_path,
            "artifact": artifact,
            "decision": "pending",
            "checklist": {},
            "comments": [],
            "neuralMotion": None,
            "reportSummary": "",
            "submission": None,
            "taskPlan": None,
            "updatedAt": None,
            "supersededSnapshot": superseded,
        }

    def _archive_stale(self, path: Path, raw: bytes, data: Any, reason: str) -> dict[str, Any]:
        snapshot_sha256 = hashlib.sha256(raw).hexdigest()
        artifact = data.get("artifact") if isinstance(data, dict) else None
        version_id = artifact.get("versionId") if isinstance(artifact, dict) else None
        archive_id = version_id if isinstance(version_id, str) and len(version_id) == 20 else f"legacy-{snapshot_sha256[:20]}"
        archive_dir = self.directory / "superseded" / path.stem
        archive_path = archive_dir / f"{archive_id}.json"
        with self._lock:
            if not path.is_file() or path.read_bytes() != raw:
                raise StaleArtifactError("review changed concurrently while superseded evidence was archived; reload")
            archive_dir.mkdir(parents=True, exist_ok=True)
            if archive_path.exists():
                if archive_path.read_bytes() != raw:
                    archive_path = archive_dir / f"{archive_id}-{snapshot_sha256[:12]}.json"
                else:
                    path.unlink(missing_ok=True)
            if archive_path.exists():
                if archive_path.read_bytes() != raw:
                    raise RuntimeError("superseded review archive hash collision")
                path.unlink(missing_ok=True)
            else:
                os.replace(path, archive_path)
        return {
            "reason": reason,
            "snapshotSha256": snapshot_sha256,
            "archivedPath": archive_path.relative_to(self.root).as_posix(),
        }

    def load(self, asset_path: str) -> dict[str, Any]:
        current_artifact = artifact_identity(self.root, asset_path)
        path = self._path(asset_path)
        with self._lock:
            if not path.is_file():
                return self._empty(asset_path, current_artifact)
            raw = path.read_bytes()
            data = json.loads(raw.decode("utf-8"))
            stored_artifact = data.get("artifact") if isinstance(data, dict) else None
            stored_schema = data.get("schemaVersion") if isinstance(data, dict) else None
            if stored_schema != SCHEMA_VERSION or not isinstance(stored_artifact, dict):
                superseded = self._archive_stale(path, raw, data, "schema-v1-unbound-artifact")
                return self._empty(asset_path, current_artifact, superseded)
            normalized = validate_review(data)
            if normalized["artifact"]["fingerprintSha256"] != current_artifact["fingerprintSha256"]:
                superseded = self._archive_stale(path, raw, data, "artifact-bytes-or-revision-changed")
                return self._empty(asset_path, current_artifact, superseded)
            if (normalized.get("submission") or {}).get("submittedBy") == "human":
                superseded = self._archive_stale(path, raw, data, "nominal-human-authority-replaced")
                normalized["submission"] = None
                normalized["taskPlan"] = None
                normalized["supersededSnapshot"] = superseded
            return normalized

    def _write(self, normalized: dict[str, Any]) -> dict[str, Any]:
        safe_repo_path(self.root, normalized["assetPath"])
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self._path(normalized["assetPath"])
        encoded = (json.dumps(normalized, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with self._lock:
            existing_raw = None
            existing_data = None
            if target.is_file():
                existing_raw = target.read_bytes()
                try:
                    existing_data = json.loads(existing_raw.decode("utf-8"))
                    existing = validate_review(existing_data)
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    self._archive_stale(target, existing_raw, None, "invalid-or-unbound-review-schema")
                    raise StaleArtifactError("existing review was superseded; reload the current pending version")
                if (
                    existing["artifact"]["fingerprintSha256"]
                    != normalized["artifact"]["fingerprintSha256"]
                ):
                    self._archive_stale(
                        target,
                        existing_raw,
                        existing_data,
                        "artifact-bytes-or-revision-changed",
                    )
                    raise StaleArtifactError("existing review belongs to a superseded artifact; reload")
            descriptor, temp_name = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".tmp", dir=self.directory)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                self._require_current_artifact(normalized)
                self._require_neural_evidence(normalized)
                os.replace(temp_name, target)
                try:
                    self._require_current_artifact(normalized)
                    self._require_neural_evidence(normalized)
                except (StaleArtifactError, ValueError):
                    if target.is_file() and target.read_bytes() == encoded:
                        if existing_raw is None:
                            target.unlink()
                        else:
                            restore_descriptor, restore_name = tempfile.mkstemp(
                                prefix=f".{target.stem}.restore.", suffix=".tmp", dir=self.directory
                            )
                            try:
                                with os.fdopen(restore_descriptor, "wb") as restore:
                                    restore.write(existing_raw)
                                    restore.flush()
                                    os.fsync(restore.fileno())
                                os.replace(restore_name, target)
                            except BaseException:
                                try:
                                    os.unlink(restore_name)
                                except FileNotFoundError:
                                    pass
                                raise
                            self._archive_stale(
                                target,
                                existing_raw,
                                existing_data,
                                "artifact-or-evidence-changed-during-review-write",
                            )
                    raise
            except BaseException:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass
                raise
        return normalized

    @staticmethod
    def _bind_actor(payload: dict[str, Any], actor_id: str | None) -> dict[str, Any]:
        candidate = dict(payload)
        if actor_id is None:
            return candidate
        comments = []
        for value in payload.get("comments", []):
            comment = dict(value) if isinstance(value, dict) else value
            if isinstance(comment, dict):
                comment["author"] = actor_id
            comments.append(comment)
        candidate["comments"] = comments
        return candidate

    def save(self, payload: Any, *, actor_id: str | None = None) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("review payload must be an object")
        candidate = self._bind_actor(payload, actor_id)
        if actor_id is not None:
            asset_path = _bounded_string(payload.get("assetPath"), "assetPath", maximum=1_000)
            if candidate.get("submission") != self._stored_submission(asset_path):
                candidate["submission"] = None
                candidate["taskPlan"] = None
        candidate["updatedAt"] = utc_now()
        normalized = validate_review(candidate)
        self._require_current_artifact(normalized)
        self._require_neural_evidence(normalized)
        submission = normalized.get("submission")
        if not submission:
            normalized["taskPlan"] = None
        elif submission["contentSha256"] != report_content_sha256(normalized):
            normalized["submission"] = None
            normalized["taskPlan"] = None
        return self._write(normalized)

    def submit(
        self,
        payload: Any,
        *,
        submitted_by: str = "internal-call",
        animated: bool | None = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("review payload must be an object")
        candidate = self._bind_actor(payload, submitted_by)
        candidate["submission"] = None
        candidate["taskPlan"] = None
        candidate["updatedAt"] = utc_now()
        normalized = validate_review(candidate)
        self._require_current_artifact(normalized)
        self._require_neural_evidence(normalized)
        if animated is None:
            path = safe_repo_path(self.root, normalized["assetPath"])
            animated = bool(measure_glb(path).get("animations"))
        if normalized["decision"] == "pending":
            raise ValueError("choose Approve, Request changes, or Reject before submitting")
        if animated and normalized["decision"] == "approved" and (normalized.get("neuralMotion") or {}).get("status") != "pass":
            raise ValueError("animated approval requires a passing neural visual audit")
        digest = report_content_sha256(normalized)
        normalized["submission"] = {
            "receiptId": digest[:20],
            "contentSha256": digest,
            "submittedAt": utc_now(),
            "submittedBy": submitted_by,
        }
        return self._write(normalized)

    def _require_current_artifact(self, review: dict[str, Any]) -> None:
        current = artifact_identity(self.root, review["assetPath"])
        if review["artifact"]["fingerprintSha256"] != current["fingerprintSha256"]:
            raise StaleArtifactError("artifact changed after this review was loaded; reload the exact current version")

    def _require_neural_evidence(self, review: dict[str, Any]) -> None:
        neural = review.get("neuralMotion")
        if not isinstance(neural, dict) or neural.get("status") != "pass":
            return
        evidence_path = neural.get("evidencePath")
        evidence_sha256 = neural.get("evidenceSha256")
        if not isinstance(evidence_path, str) or not evidence_path:
            raise ValueError("passing neural evidence requires a persisted evidencePath")
        try:
            evidence_sha256 = _hex_digest(evidence_sha256, "neuralMotion.evidenceSha256")
        except ValueError as exc:
            raise ValueError("passing neural evidence requires a valid evidenceSha256") from exc
        expected_path = (
            f"qa_runs/asset_reviews/evidence/{review['artifact']['versionId']}/"
            f"{evidence_sha256[:20]}.png"
        )
        if evidence_path != expected_path:
            raise ValueError("passing neural evidence path is not content-addressed for this artifact version")
        target = safe_repo_path(self.root, evidence_path)
        if not target.is_file():
            raise ValueError("passing neural evidence file does not exist")
        stat_before = target.stat()
        measured_sha256 = _sha256_file(target)
        stat_after = target.stat()
        if (stat_before.st_dev, stat_before.st_ino, stat_before.st_size, stat_before.st_mtime_ns) != (
            stat_after.st_dev,
            stat_after.st_ino,
            stat_after.st_size,
            stat_after.st_mtime_ns,
        ):
            raise StaleArtifactError("neural evidence changed while it was being verified")
        if measured_sha256 != evidence_sha256:
            raise ValueError("passing neural evidence bytes do not match evidenceSha256")
        receipt_path = target.with_suffix(".json")
        if not receipt_path.is_file():
            raise ValueError("passing neural evidence receipt does not exist")
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("passing neural evidence receipt is invalid") from exc
        if not isinstance(receipt, dict) or (
            receipt.get("schemaVersion") != SCHEMA_VERSION
            or receipt.get("assetPath") != review["assetPath"]
            or not isinstance(receipt.get("artifact"), dict)
            or receipt["artifact"].get("fingerprintSha256")
            != review["artifact"]["fingerprintSha256"]
            or receipt.get("clip") != neural.get("clip")
            or receipt.get("evidencePath") != evidence_path
            or receipt.get("sha256") != evidence_sha256
            or receipt.get("bytes") != stat_after.st_size
            or receipt.get("requiredReview") != "neural-visual-animation-quality"
        ):
            raise ValueError("passing neural evidence receipt is not bound to this artifact and audit")

    def _is_superseded_receipt(self, asset_path: str, receipt_id: str) -> bool:
        archive_dir = self.directory / "superseded" / stable_asset_id(asset_path)
        with self._lock:
            for path in sorted(archive_dir.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                submission = data.get("submission") if isinstance(data, dict) else None
                if isinstance(submission, dict) and submission.get("receiptId") == receipt_id:
                    return True
        return False

    def submit_task_plan(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("task plan payload must be an object")
        asset_path = _bounded_string(payload.get("assetPath"), "assetPath", maximum=1_000)
        receipt_id = _bounded_string(payload.get("reportReceiptId"), "reportReceiptId", maximum=20)
        current = self.load(asset_path)
        submission = current.get("submission")
        if not submission:
            superseded = current.get("supersededSnapshot")
            if (
                isinstance(superseded, dict)
                and superseded.get("reason") == "artifact-bytes-or-revision-changed"
            ) or self._is_superseded_receipt(asset_path, receipt_id):
                raise StaleArtifactError("submitted report receipt is stale for the current artifact version")
            raise ValueError("task planning requires a submitted human report")
        if receipt_id != submission["receiptId"]:
            raise ValueError("task plan receipt does not match the submitted human report")
        candidate = dict(current)
        candidate["taskPlan"] = {
            "reportReceiptId": receipt_id,
            "planner": payload.get("planner"),
            "plannedAt": utc_now(),
            "tasks": payload.get("tasks"),
            "adversarialReview": payload.get("adversarialReview"),
        }
        candidate["updatedAt"] = utc_now()
        normalized = validate_review(candidate)
        if normalized["taskPlan"]["adversarialReview"]["verdict"] != "pass":
            raise ValueError("task plan cannot be accepted until adversarial verification passes")
        return self._write(normalized)


@dataclass(frozen=True)
class ServerContext:
    root: Path
    initial_asset: str | None
    catalog: dict[str, Any]
    reviews: ReviewStore
    authority: BrowserAuthority
    replay_config: ReplayRunConfig | None = None


class AssetReviewHandler(BaseHTTPRequestHandler):
    server_version = "JustDodgeAssetReview/2"
    context: ServerContext

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        message = re.sub(r"(/auth/bootstrap\?token=)[^ ]+", r"\1[REDACTED]", format % args)
        print(f"[asset-review] {self.address_string()} {message}")

    def _headers(
        self,
        status: HTTPStatus,
        content_type: str,
        length: int,
        extra_headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self' blob: data:; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; worker-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'")
        for name, value in extra_headers:
            self.send_header(name, value)
        self.end_headers()

    def _send_bytes(
        self,
        payload: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        extra_headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self._headers(status, content_type, len(payload), extra_headers)
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send_bytes(json.dumps(payload, separators=(",", ":")).encode("utf-8"), "application/json; charset=utf-8", status)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message, "status": status.value}, status)

    def _expected_origin(self) -> str:
        return f"http://127.0.0.1:{getattr(self.server, 'server_port')}"

    def _require_authority(self, *, mutation: bool) -> dict[str, str]:
        if self.headers.get("Host") != self._expected_origin().removeprefix("http://"):
            raise AuthorityError(HTTPStatus.FORBIDDEN, "request Host is not the bound loopback origin")
        csrf_token = None
        if mutation:
            if self.headers.get("Origin") != self._expected_origin():
                raise AuthorityError(HTTPStatus.FORBIDDEN, "mutation Origin is not the bound loopback origin")
            csrf_token = self.headers.get("X-ForgeLens-CSRF")
            if not csrf_token:
                raise AuthorityError(HTTPStatus.FORBIDDEN, "CSRF token is missing or invalid")
        return self.context.authority.authorize(self.headers.get("Cookie"), csrf_token)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if route == "/auth/bootstrap":
                if self.command == "HEAD":
                    raise AuthorityError(HTTPStatus.METHOD_NOT_ALLOWED, "bootstrap requires GET")
                if self.headers.get("Host") != self._expected_origin().removeprefix("http://"):
                    raise AuthorityError(HTTPStatus.FORBIDDEN, "request Host is not the bound loopback origin")
                session_token, _ = self.context.authority.exchange(query.get("token", [""])[0])
                location = "/"
                if self.context.initial_asset:
                    location += "?asset=" + urllib.parse.quote(self.context.initial_asset, safe="")
                cookie = (
                    f"{BrowserAuthority.cookie_name}={session_token}; Path=/; HttpOnly; "
                    f"SameSite=Strict; Max-Age={SESSION_TTL_SECONDS}"
                )
                self._send_bytes(
                    b"",
                    "text/plain; charset=utf-8",
                    HTTPStatus.SEE_OTHER,
                    (("Location", location), ("Set-Cookie", cookie), ("Referrer-Policy", "no-referrer")),
                )
                return
            if route == "/api/session":
                self._send_json(self._require_authority(mutation=False))
                return
            if route == "/api/replay-run":
                self._require_authority(mutation=False)
                if self.context.replay_config is None:
                    self._send_json(None)
                else:
                    self._send_json(
                        build_replay_review_run(self.context.root, self.context.replay_config)
                    )
                return
            if route == "/api/catalog":
                self._require_authority(mutation=False)
                payload = build_catalog(self.context.root)
                payload["initialAsset"] = self.context.initial_asset
                self._send_json(payload)
                return
            if route == "/api/review":
                self._require_authority(mutation=False)
                asset = query.get("asset", [""])[0]
                asset = urllib.parse.unquote(asset)
                safe_repo_path(self.context.root, asset)
                self._send_json(self.context.reviews.load(asset))
                return
            if route.startswith("/file/"):
                self._require_authority(mutation=False)
                relative = urllib.parse.unquote(route[len("/file/") :])
                path = safe_repo_path(self.context.root, relative)
                if not path.is_file():
                    self._error(HTTPStatus.NOT_FOUND, "file not found")
                    return
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self._send_bytes(path.read_bytes(), content_type)
                return
            static_name = "index.html" if route in ("", "/") else route.lstrip("/")
            if "/" in static_name or static_name not in {"index.html", "styles.css", "app.js"}:
                self._error(HTTPStatus.NOT_FOUND, "route not found")
                return
            static_path = STATIC_DIR / static_name
            if not static_path.is_file():
                self._error(HTTPStatus.NOT_FOUND, "static asset not found")
                return
            content_type = mimetypes.guess_type(static_path.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type == "application/javascript":
                content_type += "; charset=utf-8"
            self._send_bytes(static_path.read_bytes(), content_type)
        except AuthorityError as exc:
            self._error(exc.status, str(exc))
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        route = urllib.parse.urlparse(self.path).path
        if route not in {
            "/api/review",
            "/api/report",
            "/api/report-plan",
            "/api/neural-evidence",
            "/api/replay-report",
        }:
            self._error(HTTPStatus.NOT_FOUND, "route not found")
            return
        try:
            authority = self._require_authority(mutation=True)
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise ValueError("Content-Length is required")
            length = int(raw_length)
            request_limit = (
                MAX_REQUEST_BYTES
                if route in {"/api/review", "/api/report", "/api/report-plan", "/api/replay-report"}
                else MAX_EVIDENCE_BYTES * 2
            )
            if length < 0 or length > request_limit:
                raise ValueError(f"request exceeds {request_limit} byte limit")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("truncated request body")
            payload = json.loads(raw.decode("utf-8"))
            if route == "/api/review":
                result = self.context.reviews.save(payload, actor_id=authority["actorId"])
            elif route == "/api/report":
                asset_path = payload.get("assetPath") if isinstance(payload, dict) else None
                record = next(
                    (asset for asset in build_catalog(self.context.root)["assets"] if asset["path"] == asset_path), None
                )
                if record is None:
                    raise ValueError("report asset is not in the repository catalog")
                result = self.context.reviews.submit(payload, submitted_by=authority["actorId"])
                print(
                    f"FORGELENS_REPORT_SUBMITTED={asset_path} RECEIPT={result['submission']['receiptId']}",
                    flush=True,
                )
            elif route == "/api/report-plan":
                result = self.context.reviews.submit_task_plan(payload)
                print(
                    f"FORGELENS_TASK_PLAN_VERIFIED={result['assetPath']} RECEIPT={result['submission']['receiptId']} TASKS={len(result['taskPlan']['tasks'])}",
                    flush=True,
                )
            elif route == "/api/neural-evidence":
                result = save_neural_evidence(
                    self.context.root, payload, captured_by=authority["actorId"]
                )
            else:
                if self.context.replay_config is None:
                    raise ValueError("no replay ReviewRun is configured")
                result = submit_replay_review(
                    self.context.root,
                    self.context.replay_config,
                    payload,
                    submitted_by=authority["actorId"],
                )
            self._send_json(result, HTTPStatus.OK)
        except AuthorityError as exc:
            self._error(exc.status, str(exc))
        except StaleArtifactError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the Just Dodge Asset Review Studio")
    parser.add_argument("--root", type=Path, default=None, help="repository root (auto-detected by default)")
    parser.add_argument("--asset", help="repository-relative GLB to select initially")
    parser.add_argument("--port", type=int, default=4177, help="loopback TCP port; use 0 for any free port")
    parser.add_argument("--no-open", action="store_true", help="do not open the browser automatically")
    parser.add_argument("--replay", help="repository-relative M3 replay (.ron) to review")
    parser.add_argument(
        "--replay-verifier",
        default="target/debug/m3_match",
        help="repository-relative m3_match verifier executable",
    )
    parser.add_argument(
        "--capture",
        action="append",
        default=[],
        help="repository-relative visual capture bound to the replay ReviewRun (repeatable)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = find_repo_root(args.root or Path(__file__).parent)
    initial_asset = None
    if args.asset:
        path = safe_repo_path(root, args.asset)
        if not path.is_file() or path.suffix.lower() != ".glb":
            raise SystemExit(f"--asset must name an existing repository GLB: {args.asset}")
        initial_asset = path.relative_to(root).as_posix()
    if not STATIC_DIR.is_dir():
        raise SystemExit(f"missing static UI directory: {STATIC_DIR}")
    replay_config = None
    if args.replay:
        replay_config = ReplayRunConfig(
            replay_path=safe_repo_path(root, args.replay).relative_to(root).as_posix(),
            verifier_path=safe_repo_path(root, args.replay_verifier).relative_to(root).as_posix(),
            capture_paths=tuple(
                safe_repo_path(root, capture).relative_to(root).as_posix() for capture in args.capture
            ),
        )
        build_replay_review_run(root, replay_config)
    bootstrap_token = secrets.token_urlsafe(32)
    context = ServerContext(
        root=root,
        initial_asset=initial_asset,
        catalog=build_catalog(root),
        reviews=ReviewStore(root),
        authority=BrowserAuthority(bootstrap_token),
        replay_config=replay_config,
    )
    handler_type = type("BoundAssetReviewHandler", (AssetReviewHandler,), {"context": context})
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_type)
    host = "127.0.0.1"
    port = server.server_port
    url = f"http://{host}:{port}/"
    if initial_asset:
        url += "?asset=" + urllib.parse.quote(initial_asset, safe="")
    print(f"ASSET_REVIEW_URL={url}", flush=True)
    print(f"ASSET_REVIEW_ROOT={root}", flush=True)
    print(f"ASSET_REVIEW_COUNT={len(context.catalog['assets'])}", flush=True)
    if not args.no_open:
        bootstrap_url = (
            f"http://{host}:{port}/auth/bootstrap?token="
            + urllib.parse.quote(bootstrap_token, safe="")
        )
        threading.Timer(0.3, lambda: webbrowser.open(bootstrap_url)).start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
