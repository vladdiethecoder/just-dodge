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
import fcntl
import hashlib
import hmac
import json
import math
import mimetypes
import os
import re
import selectors
import secrets
import signal
import stat
import subprocess
import struct
import tempfile
import threading
import time
import urllib.parse
import webbrowser
import zlib
from contextlib import contextmanager
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
REVIEW_SPINE_CONTRACT = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "reports"
    / "FORGELENS_PHASE_A_READINESS_CONTRACT.json"
)
REVIEW_WORKFLOW_REVISION = "pvp005-w0-review-workflow/v1"
FULL_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
REVIEW_RUN_STATES = {
    "awaiting_evidence",
    "awaiting_human",
    "submitted",
    "pass",
    "fail",
    "superseded",
    "expired",
}
REVIEW_RUN_TRANSITIONS = {
    "awaiting_evidence": {"awaiting_human", "superseded", "expired"},
    "awaiting_human": {"submitted", "superseded", "expired"},
    "submitted": {"pass", "fail", "superseded", "expired"},
    "pass": set(),
    "fail": set(),
    "superseded": set(),
    "expired": set(),
}
TERMINAL_REVIEW_STATES = {"pass", "fail", "superseded", "expired"}
HUMAN_ATTESTATION_TEXT = (
    "I attest that I am a human reviewer and made this decision from direct blinded observation."
)
MAX_REVIEW_INVENTORY = 512
MAX_VERIFIER_OUTPUT_BYTES = 256 * 1024
REPLAY_VERIFIER_TIMEOUT_SECONDS = 30
REQUEST_IO_TIMEOUT_SECONDS = 10
FILE_IDENTITY_FIELDS = frozenset(
    {"schema", "path", "sha256", "bytes", "repositoryState", "relevantDiffSha256"}
)
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
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


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
    files = (
        Path(__file__),
        STATIC_DIR / "index.html",
        STATIC_DIR / "styles.css",
        STATIC_DIR / "app.js",
        REVIEW_SPINE_CONTRACT,
    )
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
    document = _strict_json_loads(payload.decode("utf-8").rstrip("\x00 \t\r\n"))
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


def _validated_glb_png_images(path: Path, document: dict[str, Any]) -> set[int]:
    with path.open("rb") as handle:
        handle.seek(12)
        json_length, json_type = struct.unpack("<II", handle.read(8))
        if json_type != 0x4E4F534A:
            raise ValueError("GLB JSON chunk is missing")
        handle.seek(json_length, os.SEEK_CUR)
        chunk_header = handle.read(8)
        if len(chunk_header) != 8:
            binary = b""
        else:
            binary_length, binary_type = struct.unpack("<II", chunk_header)
            if binary_type != 0x004E4942:
                raise ValueError("GLB binary chunk is invalid")
            binary = handle.read(binary_length)
            if len(binary) != binary_length:
                raise ValueError("GLB binary chunk is truncated")
    validated: set[int] = set()
    images = document.get("images", [])
    views = document.get("bufferViews", [])
    if not isinstance(images, list) or not isinstance(views, list):
        return validated
    for index, image in enumerate(images):
        if not isinstance(image, dict) or image.get("mimeType") != "image/png":
            continue
        payload: bytes | None = None
        view_index = image.get("bufferView")
        if isinstance(view_index, int) and not isinstance(view_index, bool) and 0 <= view_index < len(views):
            view = views[view_index]
            if isinstance(view, dict) and view.get("buffer", 0) == 0:
                offset = view.get("byteOffset", 0)
                length = view.get("byteLength")
                if (
                    isinstance(offset, int)
                    and not isinstance(offset, bool)
                    and isinstance(length, int)
                    and not isinstance(length, bool)
                    and offset >= 0
                    and length >= 0
                    and offset + length <= len(binary)
                ):
                    payload = binary[offset : offset + length]
        uri = image.get("uri")
        if payload is None and isinstance(uri, str) and uri.startswith("data:image/png;base64,"):
            try:
                payload = base64.b64decode(uri.partition(",")[2], validate=True)
            except (binascii.Error, ValueError):
                payload = None
        if payload is None:
            continue
        descriptor, temporary_name = tempfile.mkstemp(prefix="forgelens-image-", suffix=".png")
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
            _png_dimensions(temporary_path, f"image[{index}]")
        except (OSError, ValueError):
            continue
        finally:
            temporary_path.unlink(missing_ok=True)
        validated.add(index)
    return validated


def viewer_eligibility(
    document: Any,
    *,
    validated_image_indexes: set[int] | None = None,
) -> dict[str, Any]:
    if not isinstance(document, dict):
        return {"status": "viewer_unsupported", "reasons": ["invalid_gltf_document"]}
    reasons: list[str] = []
    accessors = document.get("accessors", [])
    if isinstance(accessors, list) and any(
        isinstance(accessor, dict) and accessor.get("sparse") is not None for accessor in accessors
    ):
        reasons.append("sparse_accessor")
    meshes = document.get("meshes", [])
    if isinstance(meshes, list):
        for mesh in meshes:
            primitives = mesh.get("primitives", []) if isinstance(mesh, dict) else []
            if not isinstance(primitives, list):
                continue
            for primitive in primitives:
                if not isinstance(primitive, dict):
                    continue
                if primitive.get("targets"):
                    reasons.append("morph_target")
                mode = primitive.get("mode", 4)
                if mode != 4:
                    reasons.append(f"unsupported_primitive_mode:{mode}")
    animations = document.get("animations", [])
    if isinstance(animations, list):
        for animation in animations:
            if not isinstance(animation, dict):
                continue
            samplers = animation.get("samplers", [])
            if isinstance(samplers, list) and any(
                isinstance(sampler, dict) and sampler.get("interpolation", "LINEAR") == "CUBICSPLINE"
                for sampler in samplers
            ):
                reasons.append("cubic_spline_animation")
            channels = animation.get("channels", [])
            if isinstance(channels, list) and any(
                isinstance(channel, dict)
                and isinstance(channel.get("target"), dict)
                and channel["target"].get("path") == "weights"
                for channel in channels
            ):
                reasons.append("morph_weight_animation")
    required_extensions = document.get("extensionsRequired", [])
    if isinstance(required_extensions, list):
        for extension in required_extensions:
            if isinstance(extension, str) and extension:
                reasons.append(f"unsupported_required_extension:{extension}")
    images = document.get("images", [])
    if isinstance(images, list) and any(
        isinstance(image, dict)
        and isinstance(image.get("uri"), str)
        and not image["uri"].startswith("data:")
        for image in images
    ):
        reasons.append("external_image_uri")
    if isinstance(images, list):
        validated = validated_image_indexes or set()
        if any(
            isinstance(image, dict)
            and not (
                isinstance(image.get("uri"), str)
                and not image["uri"].startswith("data:")
            )
            and index not in validated
            for index, image in enumerate(images)
        ):
            reasons.append("texture_decode_failure")
    reasons = sorted(set(reasons))
    return {
        "status": "viewer_unsupported" if reasons else "viewer_supported",
        "reasons": reasons,
    }


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
        "viewerEligibility": viewer_eligibility(
            document,
            validated_image_indexes=_validated_glb_png_images(path, document),
        ),
    }


_MESH_DOCTOR_DIR = "qa_runs/p4_mesh_doctor"


def _mesh_doctor_report(root: Path, asset: str) -> dict[str, Any]:
    """Load Mesh Doctor detection findings for an asset, if present.

    Maps an asset path to its detection report(s) under qa_runs/p4_mesh_doctor/.
    Returns the report JSON (schema just-dodge-forgelens-mesh-doctor-*) or a
    not-available payload. This is a READ surface for the ForgeLens Mesh Doctor UI;
    detection itself runs in the Blender worker (tools/blender/mesh_doctor_*).
    """
    stem = Path(asset).stem
    # candidate report filenames written by the Blender workers (prefer pair
    # reports for multi-part assets; fall back to self-intersection)
    candidates = [
        root / _MESH_DOCTOR_DIR / f"{stem}_self_intersect.json",
        root / _MESH_DOCTOR_DIR / "w0_pair_Guard_BladeAndTang.json" if "w0" in asset or "sword" in asset else None,
        root / _MESH_DOCTOR_DIR / "c0_self_intersect.json" if "c0" in asset or "duelist" in asset else None,
    ]
    found = None
    for cand in candidates:
        if cand is not None and cand.is_file():
            found = cand
            break
    if found is None:
        return {
            "available": False,
            "asset": asset,
            "note": "no Mesh Doctor detection report for this asset; run tools/blender/mesh_doctor_detect.py",
        }
    try:
        report = json.loads(found.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Mesh Doctor report unreadable: {found}: {exc}") from exc
    clusters = report.get("clusters") or report.get("findings") or []
    return {
        "available": True,
        "asset": asset,
        "report_path": str(found.relative_to(root)),
        "schema": report.get("schema"),
        "runtime_admitted": report.get("runtime_admitted", False),
        "count": report.get("clusters_count", report.get("findings_count", len(clusters))),
        "clusters": clusters[:200],
        "scope_note": report.get("scope_note", ""),
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


def _required_field(value: dict[str, Any], field: str) -> Any:
    if field not in value:
        raise ValueError(f"{field} is required")
    return value[field]


def _exact_object_fields(
    value: Any,
    field: str,
    required: set[str],
    optional: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - (optional or set()))
    if missing:
        raise ValueError(f"{field} is missing required fields: {missing}")
    if unknown:
        raise ValueError(f"{field} contains unknown fields: {unknown}")
    return value


def _non_negative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _validate_review_contract_shape(contract: Any) -> dict[str, Any]:
    states = contract.get("states") if isinstance(contract, dict) else None
    if (
        not isinstance(contract, dict)
        or contract.get("schema") != "just-dodge-forgelens-review-spine-contract-v1"
        or contract.get("contract_version") != 1
        or contract.get("workflow_revision") != REVIEW_WORKFLOW_REVISION
        or not isinstance(states, list)
        or any(not isinstance(state, str) for state in states)
        or set(states) != REVIEW_RUN_STATES
        or not contract.get("append_only")
    ):
        raise ValueError("ForgeLens review-spine contract schema/core invariants are invalid")
    transitions = contract.get("transitions")
    normalized_transitions = {}
    if isinstance(transitions, dict):
        for state, targets in transitions.items():
            if not isinstance(state, str) or not isinstance(targets, list) or any(
                not isinstance(target, str) for target in targets
            ):
                raise ValueError("ForgeLens review-spine transition graph is invalid")
            normalized_transitions[state] = set(targets)
    if normalized_transitions != REVIEW_RUN_TRANSITIONS:
        raise ValueError("ForgeLens review-spine transition graph is invalid")
    human = contract.get("human_attestation")
    if not isinstance(human, dict) or any(
        human.get(field) is not True
        for field in (
            "required_for_submitted",
            "browser_actor_server_derived",
            "known_automation_patterns_rejected",
            "self_authorship_rejected",
            "blind_observation_must_precede_label_reveal",
        )
    ):
        raise ValueError("ForgeLens human-attestation contract is weakened")
    pass_eligibility = contract.get("pass_eligibility")
    if not isinstance(pass_eligibility, dict) or not pass_eligibility or any(
        value is not True for value in pass_eligibility.values()
    ):
        raise ValueError("ForgeLens pass-eligibility contract is weakened")
    return json.loads(json.dumps(contract))


def _review_contract_snapshot() -> dict[str, Any]:
    if not REVIEW_SPINE_CONTRACT.is_file():
        raise RuntimeError(f"missing ForgeLens review-spine contract: {REVIEW_SPINE_CONTRACT}")
    try:
        document = json.loads(
            REVIEW_SPINE_CONTRACT.read_text(encoding="utf-8"),
            object_pairs_hook=_json_object_without_duplicates,
            parse_constant=_reject_non_finite_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("ForgeLens review-spine contract is unreadable") from exc
    contract = document.get("review_spine_contract") if isinstance(document, dict) else None
    try:
        return _validate_review_contract_shape(contract)
    except ValueError as exc:
        raise RuntimeError("ForgeLens review-spine contract schema/version is invalid") from exc


def _review_contract_sha256(contract: dict[str, Any] | None = None) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(contract if contract is not None else _review_contract_snapshot())
    ).hexdigest()


def _canonical_repository_path(root: Path, relative: Any, field: str) -> tuple[str, Path]:
    relative = _bounded_string(relative, field, maximum=1_000)
    path = safe_repo_path(root, relative)
    if not path.is_file():
        raise ValueError(f"{field} must name an existing repository file")
    canonical = path.relative_to(root.resolve()).as_posix()
    if relative != canonical:
        raise ValueError(f"{field} must use its canonical repository-relative spelling")
    return relative, path


def _repository_identity(root: Path) -> dict[str, Any]:
    root = root.resolve()
    empty_sha256 = hashlib.sha256(b"").hexdigest()
    head_result = _git_command(root, ["rev-parse", "--verify", "HEAD"])
    if head_result.returncode != 0:
        return {
            "schema": "forgelens.code-identity/v1",
            "revision": "outside-git",
            "reachable": False,
            "trackedClean": False,
            "toolProfileSha256": _tool_profile_sha256(),
            "workingTreeDiffSha256": empty_sha256,
            "stagedDiffSha256": empty_sha256,
            "untrackedInventorySha256": empty_sha256,
        }
    revision = head_result.stdout.decode("ascii", "replace").strip().lower()
    if len(revision) not in (40, 64) or any(character not in "0123456789abcdef" for character in revision):
        raise ValueError("git HEAD did not resolve to a full hexadecimal commit identity")
    working = _git_command(root, ["diff", "--binary", "--no-ext-diff"])
    staged = _git_command(root, ["diff", "--cached", "--binary", "--no-ext-diff"])
    untracked = _git_command(root, ["ls-files", "--others", "--exclude-standard", "-z"])
    if working.returncode != 0 or staged.returncode != 0 or untracked.returncode != 0:
        raise ValueError("git repository identity could not be measured")
    untracked_entries = []
    for encoded in sorted(path for path in untracked.stdout.split(b"\x00") if path):
        relative = encoded.decode("utf-8", "surrogateescape")
        if relative == "docs/reports/forgelens_review_runs" or relative.startswith(
            "docs/reports/forgelens_review_runs/"
        ):
            continue
        path = safe_repo_path(root, relative)
        if not path.is_file():
            continue
        untracked_entries.append(
            {"path": relative, "bytes": path.stat().st_size, "sha256": _sha256_file(path)}
        )
    reachable = _git_command(root, ["cat-file", "-e", f"{revision}^{{commit}}"]).returncode == 0
    return {
        "schema": "forgelens.code-identity/v1",
        "revision": revision,
        "reachable": reachable,
        "trackedClean": not working.stdout and not staged.stdout and not untracked_entries,
        "toolProfileSha256": _tool_profile_sha256(),
        "workingTreeDiffSha256": hashlib.sha256(working.stdout).hexdigest(),
        "stagedDiffSha256": hashlib.sha256(staged.stdout).hexdigest(),
        "untrackedInventorySha256": hashlib.sha256(_canonical_json_bytes(untracked_entries)).hexdigest(),
    }


def _file_identity(root: Path, relative: Any, field: str) -> dict[str, Any]:
    relative, path = _canonical_repository_path(root, relative, field)
    root = root.resolve()
    stat_before = path.stat()
    digest = _sha256_file(path)
    stat_after = path.stat()
    before = (stat_before.st_dev, stat_before.st_ino, stat_before.st_size, stat_before.st_mtime_ns)
    after = (stat_after.st_dev, stat_after.st_ino, stat_after.st_size, stat_after.st_mtime_ns)
    if before != after:
        raise ValueError(f"{field} changed while its identity was being measured")
    head_result = _git_command(root, ["rev-parse", "--verify", "HEAD"])
    tracked_result = _git_command(root, ["ls-files", "--error-unmatch", "--", relative])
    relevant_diff_sha256 = None
    if head_result.returncode != 0:
        repository_state = "outside-git"
    elif tracked_result.returncode != 0:
        repository_state = "untracked"
    else:
        diff_result = _git_command(root, ["diff", "--binary", "--no-ext-diff", "HEAD", "--", relative])
        if diff_result.returncode != 0:
            repository_state = "unavailable"
        elif diff_result.stdout:
            repository_state = "tracked-modified"
            relevant_diff_sha256 = hashlib.sha256(diff_result.stdout).hexdigest()
        else:
            repository_state = "tracked-clean"
    return {
        "schema": "forgelens.file/v1",
        "path": relative,
        "sha256": digest,
        "bytes": stat_after.st_size,
        "repositoryState": repository_state,
        "relevantDiffSha256": relevant_diff_sha256,
    }


def _validate_file_identity_shape(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    if set(value) != FILE_IDENTITY_FIELDS:
        raise ValueError(f"{field} fields must exactly match {sorted(FILE_IDENTITY_FIELDS)}")
    if value.get("schema") != "forgelens.file/v1":
        raise ValueError(f"{field}.schema must be forgelens.file/v1")
    relative = _bounded_string(value.get("path"), f"{field}.path", maximum=1_000)
    byte_count = _non_negative_integer(value.get("bytes"), f"{field}.bytes")
    repository_state = _bounded_string(
        value.get("repositoryState"),
        f"{field}.repositoryState",
        {"tracked-clean", "tracked-modified", "untracked", "outside-git", "unavailable"},
    )
    relevant = value.get("relevantDiffSha256")
    if relevant is not None:
        relevant = _hex_digest(relevant, f"{field}.relevantDiffSha256")
    return {
        "schema": "forgelens.file/v1",
        "path": relative,
        "sha256": _hex_digest(value.get("sha256"), f"{field}.sha256"),
        "bytes": byte_count,
        "repositoryState": repository_state,
        "relevantDiffSha256": relevant,
    }


def _camera_inventory(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 64:
        raise ValueError("cameraInventory must contain 1 to 64 entries")
    result = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"cameraInventory[{index}] must be an object")
        if set(raw) != {"profile", "revision", "width", "height"}:
            raise ValueError(f"cameraInventory[{index}] fields do not exactly match the v1 schema")
        width = _non_negative_integer(raw.get("width"), f"cameraInventory[{index}].width")
        height = _non_negative_integer(raw.get("height"), f"cameraInventory[{index}].height")
        if not 1 <= width <= 16_384 or not 1 <= height <= 16_384:
            raise ValueError(f"cameraInventory[{index}] dimensions must be between 1 and 16384")
        result.append(
            {
                "profile": _bounded_string(raw.get("profile"), f"cameraInventory[{index}].profile", maximum=200),
                "revision": _bounded_string(raw.get("revision"), f"cameraInventory[{index}].revision", maximum=200),
                "width": width,
                "height": height,
            }
        )
    result.sort(key=lambda item: item["profile"])
    if len({item["profile"] for item in result}) != len(result):
        raise ValueError("cameraInventory profiles must be unique")
    return result


def _aov_inventory(value: Any, cameras: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 128:
        raise ValueError("aovInventory must contain 1 to 128 entries")
    camera_names = {camera["profile"] for camera in cameras}
    result = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"aovInventory[{index}] must be an object")
        camera = _bounded_string(raw.get("cameraProfile"), f"aovInventory[{index}].cameraProfile", maximum=200)
        if camera not in camera_names:
            raise ValueError(f"aovInventory[{index}] names an unknown camera profile")
        result.append(
            {
                "name": _bounded_string(raw.get("name"), f"aovInventory[{index}].name", maximum=100),
                "cameraProfile": camera,
                "geometryCompatibilityGroup": _bounded_string(
                    raw.get("geometryCompatibilityGroup"),
                    f"aovInventory[{index}].geometryCompatibilityGroup",
                    maximum=200,
                ),
            }
        )
    result.sort(key=lambda item: (item["cameraProfile"], item["name"]))
    keys = {(item["cameraProfile"], item["name"]) for item in result}
    if len(keys) != len(result):
        raise ValueError("aovInventory camera/AOV pairs must be unique")
    return result


def _required_evidence(value: Any, aovs: list[dict[str, str]]) -> list[dict[str, str]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 128:
        raise ValueError("requiredEvidence must contain 1 to 128 entries")
    known = {(entry["cameraProfile"], entry["name"]) for entry in aovs}
    result = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"requiredEvidence[{index}] must be an object")
        entry = {
            "cameraProfile": _bounded_string(
                raw.get("cameraProfile"), f"requiredEvidence[{index}].cameraProfile", maximum=200
            ),
            "aov": _bounded_string(raw.get("aov"), f"requiredEvidence[{index}].aov", maximum=100),
        }
        if (entry["cameraProfile"], entry["aov"]) not in known:
            raise ValueError(f"requiredEvidence[{index}] names an unknown camera/AOV pair")
        result.append(entry)
    result.sort(key=lambda item: (item["cameraProfile"], item["aov"]))
    if len({(item["cameraProfile"], item["aov"]) for item in result}) != len(result):
        raise ValueError("requiredEvidence entries must be unique")
    return result


def _produced_artifacts(
    root: Path,
    value: Any,
    aovs: list[dict[str, str]],
    geometry_identity_sha256: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_REVIEW_INVENTORY:
        raise ValueError(f"producedArtifacts must be a list of at most {MAX_REVIEW_INVENTORY} entries")
    known = {(entry["cameraProfile"], entry["name"]) for entry in aovs}
    result = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"producedArtifacts[{index}] must be an object")
        expected_fields = {
            "path",
            "kind",
            "cameraProfile",
            "aov",
            "frame",
            "tick60Hz",
            "physicsTick120Hz",
            "physicsSubstep",
        }
        if set(raw) != expected_fields:
            unknown = sorted(set(raw) - expected_fields)
            raise ValueError(
                f"producedArtifacts[{index}] fields do not exactly match the v1 schema; unknown={unknown}"
            )
        identity = _file_identity(root, raw.get("path"), f"producedArtifacts[{index}].path")
        camera = _bounded_string(
            raw.get("cameraProfile"), f"producedArtifacts[{index}].cameraProfile", maximum=200
        )
        aov = _bounded_string(raw.get("aov"), f"producedArtifacts[{index}].aov", maximum=100)
        if (camera, aov) not in known:
            raise ValueError(f"producedArtifacts[{index}] names an unknown camera/AOV pair")
        substep = _non_negative_integer(raw.get("physicsSubstep"), f"producedArtifacts[{index}].physicsSubstep")
        if substep not in (0, 1):
            raise ValueError(f"producedArtifacts[{index}].physicsSubstep must be 0 or 1")
        frame = _non_negative_integer(raw.get("frame"), f"producedArtifacts[{index}].frame")
        tick60 = _non_negative_integer(raw.get("tick60Hz"), f"producedArtifacts[{index}].tick60Hz")
        physics_tick = _non_negative_integer(
            raw.get("physicsTick120Hz"), f"producedArtifacts[{index}].physicsTick120Hz"
        )
        if frame != tick60 or physics_tick != tick60 * 2 + substep:
            raise ValueError(f"producedArtifacts[{index}] 60 Hz/120 Hz timing identity is inconsistent")
        result.append(
            {
                **identity,
                "kind": _bounded_string(raw.get("kind"), f"producedArtifacts[{index}].kind", maximum=100),
                "cameraProfile": camera,
                "aov": aov,
                "frame": frame,
                "tick60Hz": tick60,
                "physicsTick120Hz": physics_tick,
                "physicsSubstep": substep,
                "geometryIdentitySha256": geometry_identity_sha256,
            }
        )
    result.sort(key=lambda item: (item["path"], item["cameraProfile"], item["aov"], item["frame"]))
    if len({item["path"] for item in result}) != len(result):
        raise ValueError("producedArtifacts paths must be unique")
    return result


def _bind_canonical_plan(
    root: Path,
    plan_path: Any,
    cameras: list[dict[str, Any]],
    aovs: list[dict[str, str]],
    required_evidence: list[dict[str, str]],
) -> dict[str, Any]:
    identity = _file_identity(root, plan_path, "canonicalPlanPath")
    if identity["bytes"] > MAX_REQUEST_BYTES:
        raise ValueError("canonical plan exceeds the bounded JSON size")
    try:
        document = json.loads(
            safe_repo_path(root, identity["path"]).read_text(encoding="utf-8"),
            object_pairs_hook=_json_object_without_duplicates,
            parse_constant=_reject_non_finite_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"canonical plan is invalid: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "workflowRevision",
        "cameraInventory",
        "aovInventory",
        "requiredEvidence",
    }:
        raise ValueError("canonical plan fields do not exactly match forgelens.canonical-plan/v1")
    if document.get("schema") != "forgelens.canonical-plan/v1":
        raise ValueError("canonical plan schema mismatch")
    if document.get("workflowRevision") != REVIEW_WORKFLOW_REVISION:
        raise ValueError("canonical plan workflowRevision mismatch")
    plan_cameras = _camera_inventory(document.get("cameraInventory"))
    plan_aovs = _aov_inventory(document.get("aovInventory"), plan_cameras)
    plan_required = _required_evidence(document.get("requiredEvidence"), plan_aovs)
    if plan_cameras != cameras or plan_aovs != aovs or plan_required != required_evidence:
        raise ValueError("declaration camera/AOV/evidence inventory does not match the canonical plan")
    return identity


def _png_dimensions(path: Path, field: str) -> tuple[int, int]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{field} cannot be read") from exc
    if len(payload) > MAX_EVIDENCE_BYTES or payload[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{field} must be a bounded PNG")
    offset = 8
    ihdr: bytes | None = None
    compressed = bytearray()
    saw_iend = False
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise ValueError(f"{field} PNG chunk is truncated")
        chunk_length = int.from_bytes(payload[offset : offset + 4], "big")
        chunk_type = payload[offset + 4 : offset + 8]
        chunk_end = offset + 12 + chunk_length
        if chunk_end > len(payload):
            raise ValueError(f"{field} PNG chunk exceeds file bounds")
        chunk_data = payload[offset + 8 : offset + 8 + chunk_length]
        stored_crc = int.from_bytes(payload[offset + 8 + chunk_length : chunk_end], "big")
        measured_crc = binascii.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if stored_crc != measured_crc:
            raise ValueError(f"{field} PNG chunk CRC mismatch")
        if chunk_type == b"IHDR":
            if ihdr is not None or offset != 8 or chunk_length != 13:
                raise ValueError(f"{field} PNG IHDR is invalid")
            ihdr = chunk_data
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
            if len(compressed) > MAX_EVIDENCE_BYTES:
                raise ValueError(f"{field} PNG compressed image data is too large")
        elif chunk_type == b"IEND":
            if chunk_length != 0 or chunk_end != len(payload):
                raise ValueError(f"{field} PNG IEND/trailing bytes are invalid")
            saw_iend = True
        offset = chunk_end
    if ihdr is None or not compressed or not saw_iend:
        raise ValueError(f"{field} PNG is missing required chunks")
    width, height = struct.unpack(">II", ihdr[0:8])
    bit_depth = ihdr[8]
    color_type = ihdr[9]
    compression, filter_method, interlace = ihdr[10:13]
    if not width or not height or width > 16_384 or height > 16_384:
        raise ValueError(f"{field} PNG dimensions are outside the bounded range")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    valid_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        4: {8, 16},
        6: {8, 16},
    }
    if (
        channels is None
        or bit_depth not in valid_depths[color_type]
        or compression != 0
        or filter_method != 0
        or interlace != 0
    ):
        raise ValueError(f"{field} PNG encoding is unsupported for exact evidence validation")
    row_bytes = (width * channels * bit_depth + 7) // 8
    expected_bytes = (row_bytes + 1) * height
    if expected_bytes > MAX_EVIDENCE_BYTES:
        raise ValueError(f"{field} PNG decoded image exceeds the evidence bound")
    try:
        decompressor = zlib.decompressobj()
        decoded = decompressor.decompress(bytes(compressed), expected_bytes + 1)
        if decompressor.unconsumed_tail or len(decoded) > expected_bytes:
            raise ValueError(f"{field} PNG decoded image exceeds declared dimensions")
        decoded += decompressor.flush()
    except zlib.error as exc:
        raise ValueError(f"{field} PNG image data is not decodable") from exc
    if not decompressor.eof or decompressor.unused_data or len(decoded) != expected_bytes:
        raise ValueError(f"{field} PNG decoded byte count does not match IHDR dimensions")
    if any(decoded[row * (row_bytes + 1)] > 4 for row in range(height)):
        raise ValueError(f"{field} PNG uses an invalid row filter")
    return width, height


def _bind_evidence_manifest(
    root: Path,
    manifest_path: Any,
    cameras: list[dict[str, Any]],
    produced: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_identity = _file_identity(root, manifest_path, "evidenceManifestPath")
    if manifest_identity["bytes"] > MAX_REQUEST_BYTES:
        raise ValueError("evidence manifest exceeds the bounded JSON size")
    path = safe_repo_path(root, manifest_identity["path"])
    try:
        manifest = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_json_object_without_duplicates,
            parse_constant=_reject_non_finite_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"evidence manifest is invalid: {exc}") from exc
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema",
        "workflowRevision",
        "cameraInventorySha256",
        "artifacts",
    }:
        raise ValueError("evidence manifest fields do not exactly match forgelens.evidence-manifest/v1")
    if manifest.get("schema") != "forgelens.evidence-manifest/v1":
        raise ValueError("evidence manifest schema is not forgelens.evidence-manifest/v1")
    if manifest.get("workflowRevision") != REVIEW_WORKFLOW_REVISION:
        raise ValueError("evidence manifest workflowRevision mismatch")
    camera_sha256 = hashlib.sha256(_canonical_json_bytes(cameras)).hexdigest()
    if manifest.get("cameraInventorySha256") != camera_sha256:
        raise ValueError("evidence manifest cameraInventorySha256 mismatch")
    manifest_artifacts = manifest.get("artifacts")
    if not isinstance(manifest_artifacts, list) or len(manifest_artifacts) != len(produced):
        raise ValueError("evidence manifest artifact inventory does not match producedArtifacts")
    by_path: dict[str, dict[str, Any]] = {}
    manifest_fields = {
        "path",
        "kind",
        "cameraProfile",
        "aov",
        "frame",
        "tick60Hz",
        "physicsTick120Hz",
        "physicsSubstep",
        "sha256",
        "bytes",
        "width",
        "height",
        "captureRect",
    }
    for index, entry in enumerate(manifest_artifacts):
        if not isinstance(entry, dict) or set(entry) != manifest_fields:
            raise ValueError(f"evidence manifest artifacts[{index}] fields do not exactly match the v1 schema")
        relative = _bounded_string(entry.get("path"), f"evidence manifest artifacts[{index}].path", maximum=1_000)
        for field in ("kind", "cameraProfile", "aov"):
            _bounded_string(entry.get(field), f"evidence manifest artifacts[{index}].{field}", maximum=200)
        for field in (
            "frame",
            "tick60Hz",
            "physicsTick120Hz",
            "physicsSubstep",
            "bytes",
            "width",
            "height",
        ):
            _non_negative_integer(entry.get(field), f"evidence manifest artifacts[{index}].{field}")
        _hex_digest(entry.get("sha256"), f"evidence manifest artifacts[{index}].sha256")
        if relative in by_path:
            raise ValueError("evidence manifest artifact paths must be unique")
        by_path[relative] = entry
    cameras_by_name = {camera["profile"]: camera for camera in cameras}
    bound: list[dict[str, Any]] = []
    metadata_fields = (
        "path",
        "kind",
        "cameraProfile",
        "aov",
        "frame",
        "tick60Hz",
        "physicsTick120Hz",
        "physicsSubstep",
    )
    for produced_entry in produced:
        manifest_entry = by_path.get(produced_entry["path"])
        if manifest_entry is None:
            raise ValueError(f"evidence manifest is missing {produced_entry['path']}")
        if any(manifest_entry[field] != produced_entry[field] for field in metadata_fields):
            raise ValueError(f"evidence manifest metadata mismatch for {produced_entry['path']}")
        if manifest_entry["sha256"] != produced_entry["sha256"] or manifest_entry["bytes"] != produced_entry["bytes"]:
            raise ValueError(f"evidence manifest sha256/bytes mismatch for {produced_entry['path']}")
        width, height = _png_dimensions(safe_repo_path(root, produced_entry["path"]), produced_entry["path"])
        if manifest_entry["width"] != width or manifest_entry["height"] != height:
            raise ValueError(f"evidence manifest measured dimensions mismatch for {produced_entry['path']}")
        capture = manifest_entry.get("captureRect")
        if not isinstance(capture, dict) or set(capture) != {"x", "y", "width", "height"}:
            raise ValueError(f"evidence manifest captureRect is invalid for {produced_entry['path']}")
        normalized_capture = {
            key: _non_negative_integer(capture.get(key), f"evidence manifest captureRect.{key}")
            for key in ("x", "y", "width", "height")
        }
        if normalized_capture["width"] != width or normalized_capture["height"] != height:
            raise ValueError(f"evidence manifest captureRect dimensions mismatch for {produced_entry['path']}")
        camera = cameras_by_name[produced_entry["cameraProfile"]]
        if (
            normalized_capture["x"] + width > camera["width"]
            or normalized_capture["y"] + height > camera["height"]
        ):
            raise ValueError(f"evidence manifest captureRect exceeds canonical camera bounds for {produced_entry['path']}")
        full_frame = (
            normalized_capture["x"] == 0
            and normalized_capture["y"] == 0
            and width == camera["width"]
            and height == camera["height"]
        )
        bound.append(
            {
                **produced_entry,
                "width": width,
                "height": height,
                "captureRect": normalized_capture,
                "uncropped": full_frame,
                "fullFrame": full_frame,
            }
        )
    return manifest_identity, bound


def _review_run_identity_payload(run: dict[str, Any]) -> dict[str, Any]:
    return {
        key: run[key]
        for key in (
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
    }


def build_review_run(root: Path, declaration: Any) -> dict[str, Any]:
    if not isinstance(declaration, dict):
        raise ValueError("review-run declaration must be an object")
    required = (
        "schema",
        "workflowRevision",
        "buildPath",
        "replayPath",
        "verifierPath",
        "truthHash",
        "canonicalPlanPath",
        "evidenceManifestPath",
        "providerPath",
        "checkpointPath",
        "retargetPath",
        "geometryPath",
        "sourceAuthors",
        "cameraInventory",
        "aovInventory",
        "requiredEvidence",
        "producedArtifacts",
    )
    for field in required:
        _required_field(declaration, field)
    allowed_declaration_fields = {*required, "sourceRevision", "createdAt"}
    unknown = sorted(set(declaration) - allowed_declaration_fields)
    if unknown:
        raise ValueError(f"review-run declaration contains unknown fields: {unknown}")
    if declaration["schema"] != "forgelens.review-run-declaration/v1":
        raise ValueError("schema must be forgelens.review-run-declaration/v1")
    workflow_revision = _bounded_string(declaration["workflowRevision"], "workflowRevision", maximum=200)
    if workflow_revision != REVIEW_WORKFLOW_REVISION:
        raise ValueError(f"workflowRevision must be {REVIEW_WORKFLOW_REVISION}")
    code = _repository_identity(root)
    if "sourceRevision" in declaration and declaration["sourceRevision"] != code["revision"]:
        raise ValueError("sourceRevision does not match the exact measured code revision")
    source_authors_input = declaration["sourceAuthors"]
    if not isinstance(source_authors_input, list) or not 1 <= len(source_authors_input) <= 64:
        raise ValueError("sourceAuthors must contain 1 to 64 pseudonymous identifiers")
    source_authors = sorted(
        {
            _bounded_string(value, f"sourceAuthors[{index}]", maximum=200)
            for index, value in enumerate(source_authors_input)
        }
    )
    if len(source_authors) != len(source_authors_input):
        raise ValueError("sourceAuthors entries must be unique")
    cameras = _camera_inventory(declaration["cameraInventory"])
    aovs = _aov_inventory(declaration["aovInventory"], cameras)
    required_evidence = _required_evidence(declaration["requiredEvidence"], aovs)
    canonical_plan = _bind_canonical_plan(
        root,
        declaration["canonicalPlanPath"],
        cameras,
        aovs,
        required_evidence,
    )
    geometry = _file_identity(root, declaration["geometryPath"], "geometryPath")
    geometry_identity_sha256 = hashlib.sha256(
        _canonical_json_bytes({"path": geometry["path"], "sha256": geometry["sha256"], "bytes": geometry["bytes"]})
    ).hexdigest()
    produced = _produced_artifacts(root, declaration["producedArtifacts"], aovs, geometry_identity_sha256)
    evidence_manifest, produced = _bind_evidence_manifest(
        root,
        declaration["evidenceManifestPath"],
        cameras,
        produced,
    )
    verifier_artifact, completed, truth_match = _execute_allowlisted_replay_verifier(
        root,
        declaration["verifierPath"],
        declaration["replayPath"],
        _contract_replay_verifier_allowlist(),
        capture_profile="review-run-truth-verifier-v1",
    )
    declared_truth = _bounded_string(declaration["truthHash"], "truthHash", maximum=64)
    if re.fullmatch(r"[0-9a-f]{16}|[0-9a-f]{64}", declared_truth) is None:
        raise ValueError("truthHash must be a lowercase 16- or 64-character hexadecimal digest")
    measured_truth = truth_match.group(3)
    if measured_truth != declared_truth:
        raise ValueError("truthHash does not match the bounded replay truth verifier result")
    verifier = _file_identity(root, declaration["verifierPath"], "verifierPath")
    if verifier["sha256"] != verifier_artifact["contentSha256"]:
        raise ValueError("verifierPath identity does not match the executed allowlisted verifier")
    lineage = {
        "schema": "forgelens.artifact-lineage/v1",
        "code": code,
        "build": _file_identity(root, declaration["buildPath"], "buildPath"),
        "replay": _file_identity(root, declaration["replayPath"], "replayPath"),
        "verifier": verifier,
        "truthHash": declared_truth,
        "truthVerification": {
            "schema": "forgelens.truth-verification/v1",
            "commandProfile": "m3-match-verify-v1",
            "stdoutSha256": hashlib.sha256(completed.stdout).hexdigest(),
            "frames": int(truth_match.group(1)),
            "winner": _bounded_string(truth_match.group(2), "truthVerification.winner", maximum=100),
            "replayHash": measured_truth,
            "verdict": "PASS",
        },
        "canonicalPlanPacket": canonical_plan,
        "evidenceManifest": evidence_manifest,
        "workflowRevision": workflow_revision,
        "generation": {
            "provider": _file_identity(root, declaration["providerPath"], "providerPath"),
            "checkpoint": _file_identity(root, declaration["checkpointPath"], "checkpointPath"),
            "retarget": _file_identity(root, declaration["retargetPath"], "retargetPath"),
        },
        "producedArtifactInventory": produced,
        "geometry": geometry,
        "geometryIdentitySha256": geometry_identity_sha256,
    }
    contract = _review_contract_snapshot()
    created_at = _bounded_string(declaration.get("createdAt", utc_now()), "createdAt", maximum=80)
    _parse_attestation_time(created_at, "createdAt")
    run = {
        "schema": "forgelens.review-run/v1",
        "schemaVersion": 1,
        "contract": contract,
        "contractSha256": _review_contract_sha256(contract),
        "createdAt": created_at,
        "lineage": lineage,
        "cameraInventory": cameras,
        "aovInventory": aovs,
        "requiredEvidence": required_evidence,
        "sourceAuthors": source_authors,
        "decisionChainHeadSha256": None,
    }
    fingerprint = hashlib.sha256(_canonical_json_bytes(_review_run_identity_payload(run))).hexdigest()
    run["runId"] = fingerprint[:20]
    run["runFingerprintSha256"] = fingerprint
    return validate_review_run(run)


def validate_review_run(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("ReviewRun must be an object")
    expected_run_fields = {
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
    if set(value) != expected_run_fields:
        raise ValueError("ReviewRun fields do not exactly match the v1 schema")
    if value.get("schema") != "forgelens.review-run/v1" or value.get("schemaVersion") != 1:
        raise ValueError("ReviewRun schema must be forgelens.review-run/v1")
    contract = _validate_review_contract_shape(value.get("contract"))
    if value.get("contractSha256") != _review_contract_sha256(contract):
        raise ValueError("ReviewRun contractSha256 does not match its embedded versioned contract")
    lineage = value.get("lineage")
    if not isinstance(lineage, dict) or lineage.get("schema") != "forgelens.artifact-lineage/v1":
        raise ValueError("ReviewRun lineage schema must be forgelens.artifact-lineage/v1")
    if set(lineage) != {
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
    }:
        raise ValueError("ReviewRun lineage fields do not exactly match the v1 schema")
    code = lineage.get("code")
    if not isinstance(code, dict) or code.get("schema") != "forgelens.code-identity/v1":
        raise ValueError("ReviewRun lineage.code is invalid")
    if set(code) != {
        "schema",
        "revision",
        "reachable",
        "trackedClean",
        "toolProfileSha256",
        "workingTreeDiffSha256",
        "stagedDiffSha256",
        "untrackedInventorySha256",
    }:
        raise ValueError("ReviewRun lineage.code fields do not exactly match the v1 schema")
    revision = _bounded_string(code.get("revision"), "lineage.code.revision", maximum=64)
    if revision != "outside-git" and (
        len(revision) not in (40, 64) or any(character not in "0123456789abcdef" for character in revision)
    ):
        raise ValueError("lineage.code.revision must be a full commit identity or outside-git")
    for field in (
        "toolProfileSha256",
        "workingTreeDiffSha256",
        "stagedDiffSha256",
        "untrackedInventorySha256",
    ):
        _hex_digest(code.get(field), f"lineage.code.{field}")
    if not isinstance(code.get("reachable"), bool) or not isinstance(code.get("trackedClean"), bool):
        raise ValueError("lineage.code reachability/cleanliness flags must be boolean")
    for field in ("build", "replay", "verifier", "canonicalPlanPacket", "evidenceManifest", "geometry"):
        _validate_file_identity_shape(lineage.get(field), f"lineage.{field}")
    truth_hash = _bounded_string(lineage.get("truthHash"), "lineage.truthHash", maximum=64)
    if re.fullmatch(r"[0-9a-f]{16}|[0-9a-f]{64}", truth_hash) is None:
        raise ValueError("lineage.truthHash must be a lowercase 16- or 64-character hexadecimal digest")
    truth_verification = lineage.get("truthVerification")
    if not isinstance(truth_verification, dict) or set(truth_verification) != {
        "schema",
        "commandProfile",
        "stdoutSha256",
        "frames",
        "winner",
        "replayHash",
        "verdict",
    }:
        raise ValueError("lineage.truthVerification fields do not exactly match the v1 schema")
    if (
        truth_verification.get("schema") != "forgelens.truth-verification/v1"
        or truth_verification.get("commandProfile") != "m3-match-verify-v1"
        or truth_verification.get("verdict") != "PASS"
        or truth_verification.get("replayHash") != truth_hash
    ):
        raise ValueError("lineage.truthVerification does not bind a passing exact replay truth")
    _hex_digest(truth_verification.get("stdoutSha256"), "lineage.truthVerification.stdoutSha256")
    _non_negative_integer(truth_verification.get("frames"), "lineage.truthVerification.frames")
    _bounded_string(truth_verification.get("winner"), "lineage.truthVerification.winner", maximum=100)
    if lineage.get("workflowRevision") != REVIEW_WORKFLOW_REVISION:
        raise ValueError("lineage.workflowRevision drift")
    generation = lineage.get("generation")
    if not isinstance(generation, dict) or set(generation) != {"provider", "checkpoint", "retarget"}:
        raise ValueError("lineage.generation must be an object")
    for field in ("provider", "checkpoint", "retarget"):
        _validate_file_identity_shape(generation.get(field), f"lineage.generation.{field}")
    _hex_digest(lineage.get("geometryIdentitySha256"), "lineage.geometryIdentitySha256")
    produced = lineage.get("producedArtifactInventory")
    if not isinstance(produced, list) or len(produced) > MAX_REVIEW_INVENTORY:
        raise ValueError("lineage.producedArtifactInventory is invalid")
    for index, artifact in enumerate(produced):
        artifact_metadata_fields = {
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
        if set(artifact) != FILE_IDENTITY_FIELDS | artifact_metadata_fields:
            raise ValueError(f"lineage.producedArtifactInventory[{index}] fields are not canonical")
        _validate_file_identity_shape(
            {field: artifact[field] for field in FILE_IDENTITY_FIELDS},
            f"lineage.producedArtifactInventory[{index}]",
        )
        for field in ("cameraProfile", "aov", "kind"):
            _bounded_string(artifact.get(field), f"lineage.producedArtifactInventory[{index}].{field}")
        for field in ("frame", "tick60Hz", "physicsTick120Hz", "physicsSubstep"):
            _non_negative_integer(artifact.get(field), f"lineage.producedArtifactInventory[{index}].{field}")
        if (
            artifact["frame"] != artifact["tick60Hz"]
            or artifact["physicsSubstep"] not in (0, 1)
            or artifact["physicsTick120Hz"] != artifact["tick60Hz"] * 2 + artifact["physicsSubstep"]
        ):
            raise ValueError(f"lineage.producedArtifactInventory[{index}] timing identity is inconsistent")
        for field in ("uncropped", "fullFrame"):
            if not isinstance(artifact.get(field), bool):
                raise ValueError(f"lineage.producedArtifactInventory[{index}].{field} must be boolean")
        for field in ("width", "height"):
            dimension = _non_negative_integer(
                artifact.get(field), f"lineage.producedArtifactInventory[{index}].{field}"
            )
            if not 1 <= dimension <= 16_384:
                raise ValueError(f"lineage.producedArtifactInventory[{index}].{field} is outside bounds")
        capture = artifact.get("captureRect")
        if not isinstance(capture, dict) or set(capture) != {"x", "y", "width", "height"}:
            raise ValueError(f"lineage.producedArtifactInventory[{index}].captureRect is invalid")
        for field in ("x", "y", "width", "height"):
            _non_negative_integer(capture.get(field), f"lineage.producedArtifactInventory[{index}].captureRect.{field}")
        _hex_digest(
            artifact.get("geometryIdentitySha256"),
            f"lineage.producedArtifactInventory[{index}].geometryIdentitySha256",
        )
    cameras = _camera_inventory(value.get("cameraInventory"))
    if cameras != value["cameraInventory"]:
        raise ValueError("cameraInventory must be canonical and sorted")
    aovs = _aov_inventory(value.get("aovInventory"), cameras)
    if aovs != value["aovInventory"]:
        raise ValueError("aovInventory must be canonical and sorted")
    required = _required_evidence(value.get("requiredEvidence"), aovs)
    if required != value["requiredEvidence"]:
        raise ValueError("requiredEvidence must be canonical and sorted")
    authors = value.get("sourceAuthors")
    if not isinstance(authors, list) or not authors:
        raise ValueError("sourceAuthors must be a non-empty list")
    for index, author in enumerate(authors):
        _bounded_string(author, f"sourceAuthors[{index}]", maximum=200)
    if authors != sorted(set(authors)):
        raise ValueError("sourceAuthors must be canonical and unique")
    head = value.get("decisionChainHeadSha256")
    if head is not None:
        _hex_digest(head, "decisionChainHeadSha256")
    created_at = _bounded_string(value.get("createdAt"), "createdAt", maximum=80)
    _parse_attestation_time(created_at, "createdAt")
    fingerprint = hashlib.sha256(_canonical_json_bytes(_review_run_identity_payload(value))).hexdigest()
    if value.get("runFingerprintSha256") != fingerprint or value.get("runId") != fingerprint[:20]:
        raise ValueError("ReviewRun fingerprint does not match its canonical identity")
    return json.loads(json.dumps(value))


def _file_identity_matches(root: Path, identity: dict[str, Any]) -> bool:
    try:
        current = _file_identity(root, identity["path"], identity["path"])
    except (OSError, ValueError):
        return False
    return current["sha256"] == identity["sha256"] and current["bytes"] == identity["bytes"]


def review_run_eligibility(
    root: Path,
    run: Any,
    *,
    pin_statuses: list[dict[str, Any]] | None = None,
    viewer_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run = validate_review_run(run)
    lineage = run["lineage"]
    blockers: list[str] = []
    bound_inputs = {
        "build": lineage["build"],
        "replay": lineage["replay"],
        "verifier": lineage["verifier"],
        "canonical_plan": lineage["canonicalPlanPacket"],
        "evidence_manifest": lineage["evidenceManifest"],
        "provider": lineage["generation"]["provider"],
        "checkpoint": lineage["generation"]["checkpoint"],
        "retarget": lineage["generation"]["retarget"],
        "geometry": lineage["geometry"],
    }
    for role, identity in bound_inputs.items():
        if not _file_identity_matches(root, identity):
            blockers.append(f"lineage_input_changed:{role}")
    if not _file_identity_matches(root, lineage["canonicalPlanPacket"]):
        blockers.append("canonical_plan_changed")
    produced = lineage["producedArtifactInventory"]
    if any(not _file_identity_matches(root, artifact) for artifact in produced):
        blockers.append("produced_artifact_changed")
    try:
        _, truth_completed, truth_match = _execute_allowlisted_replay_verifier(
            root,
            lineage["verifier"]["path"],
            lineage["replay"]["path"],
            ((lineage["verifier"]["path"], lineage["verifier"]["sha256"]),),
            capture_profile="review-run-truth-revalidation-v1",
        )
        truth_verification = lineage["truthVerification"]
        if (
            truth_match.group(3) != lineage["truthHash"]
            or hashlib.sha256(truth_completed.stdout).hexdigest() != truth_verification["stdoutSha256"]
            or int(truth_match.group(1)) != truth_verification["frames"]
            or truth_match.group(2) != truth_verification["winner"]
        ):
            blockers.append("truth_verification_changed")
    except (OSError, ValueError):
        blockers.append("truth_verification_failed")
    viewer_inputs = [lineage["geometry"], *produced]
    for identity in viewer_inputs:
        if Path(identity["path"]).suffix.lower() != ".glb":
            continue
        try:
            path = safe_repo_path(root, identity["path"])
            document = _read_glb_json(path)
            viewer = viewer_eligibility(
                document,
                validated_image_indexes=_validated_glb_png_images(path, document),
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            blockers.append("viewer_unsupported:invalid_gltf_document")
            continue
        blockers.extend(
            f"viewer_unsupported:{reason}" for reason in viewer["reasons"]
        )
    required = {(item["cameraProfile"], item["aov"]) for item in run["requiredEvidence"]}
    complete = {
        (artifact["cameraProfile"], artifact["aov"])
        for artifact in produced
        if artifact["uncropped"] and artifact["fullFrame"]
    }
    if not required.issubset(complete):
        blockers.append("missing_required_evidence")
    if produced and not any(artifact["uncropped"] and artifact["fullFrame"] for artifact in produced):
        blockers.append("cropped_only_review_input")
    if any(status.get("status") == "stale" for status in pin_statuses or []):
        blockers.append("stale_pin")
    if viewer_context is not None:
        viewer_status = viewer_context.get("status")
        if viewer_status == "context_lost":
            blockers.append("visual_context_lost")
        elif viewer_status == "recapture_required":
            blockers.append("visual_context_recapture_required")
        elif viewer_status != "stable":
            blockers.append("visual_context_invalid")
    pass_blockers = list(blockers)
    code = lineage["code"]
    revision = code["revision"]
    if revision == "outside-git" or not code["reachable"]:
        pass_blockers.append("revision_unreachable")
    else:
        root = root.resolve()
        commit = _git_command(root, ["cat-file", "-e", f"{revision}^{{commit}}"])
        reachable = _git_command(root, ["merge-base", "--is-ancestor", revision, "HEAD"])
        if commit.returncode != 0 or reachable.returncode != 0:
            pass_blockers.append("revision_unreachable")
    if not code["trackedClean"]:
        pass_blockers.append("code_revision_not_tracked_clean")
    if code["toolProfileSha256"] != _tool_profile_sha256():
        pass_blockers.append("tool_profile_changed")
    core_inputs = list(bound_inputs.values())
    if any(identity["repositoryState"] != "tracked-clean" for identity in core_inputs):
        pass_blockers.append("lineage_input_not_tracked_clean")
    if any(identity["repositoryState"] != "tracked-clean" for identity in produced):
        pass_blockers.append("evidence_input_not_tracked_clean")
    blockers = list(dict.fromkeys(blockers))
    pass_blockers = list(dict.fromkeys(pass_blockers))
    return {
        "schema": "forgelens.review-eligibility/v1",
        "eligibleForHumanReview": not blockers,
        "eligibleForPass": not pass_blockers,
        "blockers": blockers,
        "passBlockers": pass_blockers,
    }


def validate_review_pin(value: Any, run: Any) -> dict[str, Any]:
    run = validate_review_run(run)
    if not isinstance(value, dict) or value.get("schema") != "forgelens.review-pin/v1":
        raise ValueError("review pin schema must be forgelens.review-pin/v1")
    required = (
        "pinId",
        "revision",
        "artifactSha256",
        "workflowRevision",
        "canonicalPlanSha256",
        "geometryIdentitySha256",
        "frame",
        "tick60Hz",
        "physicsTick120Hz",
        "physicsSubstep",
        "cameraProfile",
        "aov",
        "screenPoint",
        "severity",
        "category",
        "text",
        "author",
        "createdAt",
        "updatedAt",
        "status",
        "resolutionRevision",
    )
    for field in required:
        _required_field(value, field)
    allowed_pin_fields = {
        *required,
        "schema",
        "worldPoint",
        "worldNormal",
        "worldRay",
        "triangleId",
        "objectId",
        "boneId",
        "socketId",
        "contactId",
    }
    unknown_pin_fields = sorted(set(value) - allowed_pin_fields)
    if unknown_pin_fields:
        raise ValueError(f"review pin contains unknown fields: {unknown_pin_fields}")
    revision = _bounded_string(value["revision"], "pin.revision", maximum=64)
    artifact_sha256 = _hex_digest(value["artifactSha256"], "pin.artifactSha256")
    workflow_revision = _bounded_string(value["workflowRevision"], "pin.workflowRevision", maximum=200)
    plan_sha256 = _hex_digest(value["canonicalPlanSha256"], "pin.canonicalPlanSha256")
    geometry_sha256 = _hex_digest(value["geometryIdentitySha256"], "pin.geometryIdentitySha256")
    expected = {
        "revision": run["lineage"]["code"]["revision"],
        "artifactSha256": run["lineage"]["geometry"]["sha256"],
        "workflowRevision": run["lineage"]["workflowRevision"],
        "canonicalPlanSha256": run["lineage"]["canonicalPlanPacket"]["sha256"],
        "geometryIdentitySha256": run["lineage"]["geometryIdentitySha256"],
    }
    observed = {
        "revision": revision,
        "artifactSha256": artifact_sha256,
        "workflowRevision": workflow_revision,
        "canonicalPlanSha256": plan_sha256,
        "geometryIdentitySha256": geometry_sha256,
    }
    for field, expected_value in expected.items():
        if observed[field] != expected_value:
            raise ValueError(f"pin {field} does not match the ReviewRun")
    camera = _bounded_string(value["cameraProfile"], "pin.cameraProfile", maximum=200)
    aov = _bounded_string(value["aov"], "pin.aov", maximum=100)
    if (camera, aov) not in {
        (entry["cameraProfile"], entry["name"]) for entry in run["aovInventory"]
    }:
        raise ValueError("pin cameraProfile/AOV is not declared by the ReviewRun")
    screen = value["screenPoint"]
    if not isinstance(screen, dict):
        raise ValueError("pin.screenPoint must be an object")
    normalized_screen = {}
    for axis in ("x", "y"):
        component = screen.get(axis)
        if (
            isinstance(component, bool)
            or not isinstance(component, (int, float))
            or not math.isfinite(float(component))
        ):
            raise ValueError(f"pin.screenPoint.{axis} must be finite")
        if not 0.0 <= float(component) <= 1.0:
            raise ValueError(f"pin.screenPoint.{axis} must be normalized to [0, 1]")
        normalized_screen[axis] = float(component)
    world_ray = value.get("worldRay")
    normalized_ray = None
    if world_ray is not None:
        if not isinstance(world_ray, dict):
            raise ValueError("pin.worldRay must be an object")
        normalized_ray = {
            "origin": _finite_vector(world_ray.get("origin"), "pin.worldRay.origin"),
            "direction": _finite_vector(world_ray.get("direction"), "pin.worldRay.direction"),
        }
        direction_length = math.sqrt(
            sum(component * component for component in normalized_ray["direction"])
        )
        if not direction_length:
            raise ValueError("pin.worldRay.direction must not be zero")
        if abs(direction_length - 1.0) > 1e-12:
            normalized_ray["direction"] = [
                component / direction_length for component in normalized_ray["direction"]
            ]
    status = _bounded_string(value["status"], "pin.status", {"open", "resolved", "wont-fix"})
    resolution_revision = value["resolutionRevision"]
    if resolution_revision is not None:
        resolution_revision = _bounded_string(resolution_revision, "pin.resolutionRevision", maximum=64)
    if status == "resolved" and resolution_revision is None:
        raise ValueError("resolved pin requires resolutionRevision")
    created_at = _bounded_string(value["createdAt"], "pin.createdAt", maximum=80)
    updated_at = _bounded_string(value["updatedAt"], "pin.updatedAt", maximum=80)
    if _parse_attestation_time(created_at, "pin.createdAt") > _parse_attestation_time(
        updated_at, "pin.updatedAt"
    ):
        raise ValueError("pin.updatedAt must not precede pin.createdAt")
    pin_id = _bounded_string(value["pinId"], "pin.pinId", maximum=200)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", pin_id):
        raise ValueError("pinId must contain only safe identifier characters")
    optional_ids = {}
    for field in ("triangleId", "objectId", "boneId", "socketId", "contactId"):
        raw = value.get(field)
        optional_ids[field] = None if raw is None else _bounded_string(raw, f"pin.{field}", maximum=200)
    substep = _non_negative_integer(value["physicsSubstep"], "pin.physicsSubstep")
    if substep not in (0, 1):
        raise ValueError("pin.physicsSubstep must be 0 or 1")
    frame = _non_negative_integer(value["frame"], "pin.frame")
    tick60 = _non_negative_integer(value["tick60Hz"], "pin.tick60Hz")
    physics_tick = _non_negative_integer(value["physicsTick120Hz"], "pin.physicsTick120Hz")
    if frame != tick60 or physics_tick != tick60 * 2 + substep:
        raise ValueError("pin 60 Hz frame/tick and 120 Hz physics identity are inconsistent")
    return {
        "schema": "forgelens.review-pin/v1",
        "pinId": pin_id,
        **observed,
        "frame": frame,
        "tick60Hz": tick60,
        "physicsTick120Hz": physics_tick,
        "physicsSubstep": substep,
        "cameraProfile": camera,
        "aov": aov,
        "screenPoint": normalized_screen,
        "worldRay": normalized_ray,
        **optional_ids,
        "severity": _bounded_string(value["severity"], "pin.severity", SEVERITIES),
        "category": _bounded_string(value["category"], "pin.category", CATEGORIES),
        "text": _bounded_string(value["text"], "pin.text", maximum=MAX_COMMENT_CHARS),
        "author": _bounded_string(value["author"], "pin.author", maximum=200),
        "createdAt": created_at,
        "updatedAt": updated_at,
        "status": status,
        "resolutionRevision": resolution_revision,
    }


def derive_review_pin_context(
    root: Path,
    run: Any,
    pin: Any,
    *,
    target_aov: str | None = None,
) -> dict[str, Any]:
    run = validate_review_run(run)
    pin = validate_review_pin(pin, run)
    aov = pin["aov"] if target_aov is None else _bounded_string(target_aov, "targetAov", maximum=100)
    if (pin["cameraProfile"], aov) not in {
        (entry["cameraProfile"], entry["name"]) for entry in run["aovInventory"]
    }:
        raise ValueError("targetAov is not declared for the ReviewPin camera profile")
    geometry = _file_identity(root, run["lineage"]["geometry"]["path"], "currentGeometry")
    geometry_identity_sha256 = hashlib.sha256(
        _canonical_json_bytes(
            {"path": geometry["path"], "sha256": geometry["sha256"], "bytes": geometry["bytes"]}
        )
    ).hexdigest()
    plan = _file_identity(root, run["lineage"]["canonicalPlanPacket"]["path"], "currentCanonicalPlan")
    return {
        "revision": run["lineage"]["code"]["revision"],
        "artifactSha256": geometry["sha256"],
        "workflowRevision": run["lineage"]["workflowRevision"],
        "canonicalPlanSha256": plan["sha256"],
        "geometryIdentitySha256": geometry_identity_sha256,
        "frame": pin["frame"],
        "tick60Hz": pin["tick60Hz"],
        "physicsTick120Hz": pin["physicsTick120Hz"],
        "physicsSubstep": pin["physicsSubstep"],
        "cameraProfile": pin["cameraProfile"],
        "aov": aov,
    }


def review_pin_status(pin: Any, run: Any, context: Any) -> dict[str, Any]:
    run = validate_review_run(run)
    pin = validate_review_pin(pin, run)
    if not isinstance(context, dict):
        raise ValueError("pin context must be an object")
    fields = (
        "revision",
        "artifactSha256",
        "workflowRevision",
        "canonicalPlanSha256",
        "geometryIdentitySha256",
        "frame",
        "tick60Hz",
        "physicsTick120Hz",
        "physicsSubstep",
        "cameraProfile",
        "aov",
    )
    if set(context) != set(fields):
        raise ValueError("pin context fields do not exactly match the v1 schema")
    normalized = {field: _required_field(context, field) for field in fields}
    for field in ("artifactSha256", "canonicalPlanSha256", "geometryIdentitySha256"):
        normalized[field] = _hex_digest(normalized[field], f"pinContext.{field}")
    for field in ("revision", "workflowRevision", "cameraProfile", "aov"):
        normalized[field] = _bounded_string(normalized[field], f"pinContext.{field}", maximum=200)
    for field in ("frame", "tick60Hz", "physicsTick120Hz", "physicsSubstep"):
        normalized[field] = _non_negative_integer(normalized[field], f"pinContext.{field}")
    if (
        normalized["frame"] != normalized["tick60Hz"]
        or normalized["physicsSubstep"] not in (0, 1)
        or normalized["physicsTick120Hz"]
        != normalized["tick60Hz"] * 2 + normalized["physicsSubstep"]
    ):
        raise ValueError("pin context 60 Hz/120 Hz timing identity is inconsistent")
    mismatches = [
        field
        for field in (
            "revision",
            "artifactSha256",
            "workflowRevision",
            "canonicalPlanSha256",
            "geometryIdentitySha256",
            "frame",
            "tick60Hz",
            "physicsTick120Hz",
            "physicsSubstep",
            "cameraProfile",
        )
        if normalized[field] != pin[field]
    ]
    source = next(
        (
            entry
            for entry in run["aovInventory"]
            if entry["cameraProfile"] == pin["cameraProfile"] and entry["name"] == pin["aov"]
        ),
        None,
    )
    target = next(
        (
            entry
            for entry in run["aovInventory"]
            if entry["cameraProfile"] == normalized["cameraProfile"] and entry["name"] == normalized["aov"]
        ),
        None,
    )
    aov_compatible = bool(
        source
        and target
        and source["geometryCompatibilityGroup"] == target["geometryCompatibilityGroup"]
    )
    if normalized["aov"] != pin["aov"] and not aov_compatible:
        mismatches.append("aov")
    return {
        "pinId": pin["pinId"],
        "status": "stale" if mismatches else "active",
        "mismatches": mismatches,
        "aovGeometryCompatible": aov_compatible,
        "context": normalized,
    }


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
    verifier_allowlist: tuple[tuple[str, str], ...] = ()


def _run_bounded_process(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    max_output_bytes: int,
    pass_fds: tuple[int, ...] = (),
) -> subprocess.CompletedProcess[bytes]:
    if not command or timeout_seconds <= 0 or max_output_bytes < 1:
        raise ValueError("bounded process limits are invalid")
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        pass_fds=pass_fds,
    )
    if process.stdout is None:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        raise RuntimeError("bounded process stdout pipe was not created")
    descriptor = process.stdout.fileno()
    os.set_blocking(descriptor, False)
    selector = selectors.DefaultSelector()
    selector.register(descriptor, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + timeout_seconds
    stream_open = True
    try:
        while stream_open or process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
                raise ValueError(f"verifier timeout exceeded {timeout_seconds:g} seconds")
            events = selector.select(min(remaining, 0.05)) if stream_open else []
            for key, _ in events:
                try:
                    chunk = os.read(key.fd, 65_536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fd)
                    stream_open = False
                    continue
                if len(output) + len(chunk) > max_output_bytes:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=5)
                    raise ValueError(f"verifier output exceeds {max_output_bytes} byte limit")
                output.extend(chunk)
            if process.poll() is not None and stream_open and not events:
                try:
                    chunk = os.read(descriptor, 65_536)
                except BlockingIOError:
                    chunk = None
                if chunk == b"":
                    selector.unregister(descriptor)
                    stream_open = False
                elif chunk:
                    if len(output) + len(chunk) > max_output_bytes:
                        raise ValueError(f"verifier output exceeds {max_output_bytes} byte limit")
                    output.extend(chunk)
        return subprocess.CompletedProcess(command, process.returncode, bytes(output), b"")
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if process.poll() is None:
            process.wait(timeout=5)
        raise
    finally:
        selector.close()
        process.stdout.close()


def _execute_allowlisted_replay_verifier(
    root: Path,
    verifier_relative: str,
    replay_relative: str,
    allowlist: tuple[tuple[str, str], ...],
    *,
    capture_profile: str,
) -> tuple[dict[str, Any], subprocess.CompletedProcess[bytes], re.Match[str]]:
    _, verifier_path = _canonical_repository_path(root, verifier_relative, "verifierPath")
    _, replay_path = _canonical_repository_path(root, replay_relative, "replayPath")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(verifier_path, flags)
    replay_descriptor: int | None = None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("replay verifier must be a regular file")
        digest = hashlib.sha256()
        offset = 0
        while offset < before.st_size:
            chunk = os.pread(descriptor, min(1_048_576, before.st_size - offset), offset)
            if not chunk:
                raise ValueError("replay verifier changed while it was being measured")
            digest.update(chunk)
            offset += len(chunk)
        verifier_sha256 = digest.hexdigest()
        if (verifier_relative, verifier_sha256) not in allowlist:
            raise ValueError("replay verifier is not present in the fixed path/SHA-256 allowlist")
        verifier = artifact_identity(root, verifier_relative, capture_profile=capture_profile)
        if verifier["contentSha256"] != verifier_sha256 or verifier["bytes"] != before.st_size:
            raise ValueError("replay verifier path changed during identity measurement")
        replay_descriptor = os.open(replay_path, flags)
        replay_before = os.fstat(replay_descriptor)
        if not stat.S_ISREG(replay_before.st_mode):
            raise ValueError("replay input must be a regular file")
        replay_digest = hashlib.sha256()
        replay_offset = 0
        while replay_offset < replay_before.st_size:
            chunk = os.pread(
                replay_descriptor,
                min(1_048_576, replay_before.st_size - replay_offset),
                replay_offset,
            )
            if not chunk:
                raise ValueError("replay input changed while it was being measured")
            replay_digest.update(chunk)
            replay_offset += len(chunk)
        replay_identity = _file_identity(root, replay_relative, "replayPath")
        if (
            replay_identity["sha256"] != replay_digest.hexdigest()
            or replay_identity["bytes"] != replay_before.st_size
        ):
            raise ValueError("replay input path changed during identity measurement")
        completed = _run_bounded_process(
            [f"/proc/self/fd/{descriptor}", "--verify", f"/proc/self/fd/{replay_descriptor}"],
            cwd=root,
            timeout_seconds=REPLAY_VERIFIER_TIMEOUT_SECONDS,
            max_output_bytes=MAX_VERIFIER_OUTPUT_BYTES,
            pass_fds=(descriptor, replay_descriptor),
        )
        after = os.fstat(descriptor)
        path_stat = os.stat(verifier_path, follow_symlinks=False)
        replay_after = os.fstat(replay_descriptor)
        replay_path_stat = os.stat(replay_path, follow_symlinks=False)
        immutable_stat = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        if immutable_stat != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or (path_stat.st_dev, path_stat.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("replay verifier path changed during hash-to-exec validation")
        replay_immutable_stat = (
            replay_before.st_dev,
            replay_before.st_ino,
            replay_before.st_size,
            replay_before.st_mtime_ns,
            replay_before.st_ctime_ns,
        )
        if replay_immutable_stat != (
            replay_after.st_dev,
            replay_after.st_ino,
            replay_after.st_size,
            replay_after.st_mtime_ns,
            replay_after.st_ctime_ns,
        ) or (replay_path_stat.st_dev, replay_path_stat.st_ino) != (
            replay_before.st_dev,
            replay_before.st_ino,
        ):
            raise ValueError("replay input path changed during hash-to-exec validation")
    finally:
        if replay_descriptor is not None:
            os.close(replay_descriptor)
        os.close(descriptor)
    output = completed.stdout.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        raise ValueError(f"replay verifier failed with exit {completed.returncode}: {output[-2_000:]}")
    match = re.search(r"frames=(\d+) winner=([^ ]+) hash=([0-9a-f]{16,64})", output)
    if match is None:
        raise ValueError("replay verifier output is missing frames/winner/hash evidence")
    return verifier, completed, match


def build_replay_review_run(root: Path, config: ReplayRunConfig) -> dict[str, Any]:
    replay = artifact_identity(root, config.replay_path, capture_profile="m3-replay-v2")
    verifier, completed, match = _execute_allowlisted_replay_verifier(
        root,
        config.verifier_path,
        config.replay_path,
        config.verifier_allowlist,
        capture_profile="m3-replay-verifier-v1",
    )
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


class TransitionError(ValueError):
    pass


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _write_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_name, path)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise RuntimeError(f"immutable content collision at {path}")
        _fsync_directory(path.parent)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _parse_attestation_time(value: Any, field: str) -> datetime:
    text = _bounded_string(value, field, maximum=80)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_human_attestation(
    details: Any,
    run: dict[str, Any],
    browser_actor_id: str,
) -> dict[str, Any]:
    if not isinstance(details, dict):
        raise ValueError("submitted transition details must be an object")
    expected_fields = {
        "proposedDecision",
        "reviewerId",
        "humanAttestation",
        "authorshipExcluded",
        "blindObservationAt",
        "labelRevealedAt",
        "decisionAt",
        "sourceRevision",
    }
    if set(details) != expected_fields:
        raise ValueError("submitted transition details do not exactly match the human-attestation schema")
    reviewer = _bounded_string(details.get("reviewerId"), "reviewerId", maximum=200)
    lowered = reviewer.casefold()
    automation_markers = ("agent", "automation", "bot", "hermes", "codex", "browser-session", "test-reviewer")
    if any(marker in lowered for marker in automation_markers):
        raise ValueError("human attestation rejects known automation or browser-session reviewer identities")
    if reviewer.casefold() in {author.casefold() for author in run["sourceAuthors"]}:
        raise ValueError("reviewer must be excluded from source authorship")
    if details.get("authorshipExcluded") is not True:
        raise ValueError("human attestation requires explicit authorship exclusion")
    attestation = _bounded_string(details.get("humanAttestation"), "humanAttestation", maximum=500)
    if attestation != HUMAN_ATTESTATION_TEXT:
        raise ValueError("human attestation text does not match the required explicit statement")
    proposed = _bounded_string(details.get("proposedDecision"), "proposedDecision", {"pass", "fail"})
    source_revision = _bounded_string(details.get("sourceRevision"), "sourceRevision", maximum=64)
    if source_revision != run["lineage"]["code"]["revision"]:
        raise ValueError("human attestation sourceRevision does not match the ReviewRun")
    blind = _parse_attestation_time(details.get("blindObservationAt"), "blindObservationAt")
    revealed = _parse_attestation_time(details.get("labelRevealedAt"), "labelRevealedAt")
    decided = _parse_attestation_time(details.get("decisionAt"), "decisionAt")
    if not blind < revealed <= decided:
        raise ValueError("blind observation must occur before label reveal and decision")
    return {
        "proposedDecision": proposed,
        "reviewerId": reviewer,
        "humanAttestation": attestation,
        "humanAttestationAuthority": "operational-attestation-not-cryptographic-proof",
        "browserActorId": _bounded_string(browser_actor_id, "browserActorId", maximum=200),
        "authorshipExcluded": True,
        "sourceAuthors": list(run["sourceAuthors"]),
        "blindObservationAt": details["blindObservationAt"],
        "labelRevealedAt": details["labelRevealedAt"],
        "decisionAt": details["decisionAt"],
        "sourceRevision": source_revision,
    }


class StoreInstanceLock:
    """Process-lifetime exclusive lock preventing concurrent ForgeLens servers on one store."""

    def __init__(self, root: Path, directory: Path | None = None):
        root = root.resolve()
        self.directory = (
            directory.resolve()
            if directory is not None
            else root / "docs" / "reports" / "forgelens_review_runs"
        )
        self._descriptor: int | None = None

    def acquire(self) -> None:
        if self._descriptor is not None:
            raise RuntimeError("ForgeLens store instance lock is already held by this object")
        self.directory.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.directory / ".server.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(descriptor)
            raise RuntimeError("ForgeLens store is already owned by another server process") from exc
        os.ftruncate(descriptor, 0)
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        self._descriptor = descriptor

    def close(self) -> None:
        if self._descriptor is None:
            return
        descriptor = self._descriptor
        self._descriptor = None
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.close()


class ReviewRunStore:
    """Crash-recoverable append-only ReviewRun receipts in a non-ignored admission path."""

    def __init__(self, root: Path, directory: Path | None = None):
        self.root = root.resolve()
        self.directory = (
            directory.resolve()
            if directory is not None
            else self.root / "docs" / "reports" / "forgelens_review_runs"
        )
        self._thread_lock = threading.RLock()

    def _run_directory(self, run_id: str) -> Path:
        run_id = _bounded_string(run_id, "runId", maximum=20)
        if len(run_id) != 20 or any(character not in "0123456789abcdef" for character in run_id):
            raise ValueError("runId must be 20 lowercase hexadecimal characters")
        return self.directory / run_id

    @contextmanager
    def _exclusive(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        lock_path = self.directory / ".store.lock"
        with self._thread_lock:
            descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

    @staticmethod
    def _receipt_bytes(receipt: dict[str, Any]) -> bytes:
        return _canonical_json_bytes(receipt) + b"\n"

    def _validate_receipt(
        self,
        value: Any,
        run: dict[str, Any],
        expected_sequence: int,
        expected_previous: str | None,
    ) -> dict[str, Any]:
        if not isinstance(value, dict) or value.get("schema") != "forgelens.decision-receipt/v1":
            raise RuntimeError("invalid immutable ReviewRun receipt schema")
        if value.get("runId") != run["runId"] or value.get("runFingerprintSha256") != run["runFingerprintSha256"]:
            raise RuntimeError("ReviewRun receipt identity mismatch")
        if value.get("sequence") != expected_sequence or value.get("previousReceiptSha256") != expected_previous:
            raise RuntimeError("ReviewRun receipt chain fork or sequence gap")
        state = value.get("state")
        if state not in REVIEW_RUN_STATES:
            raise RuntimeError("ReviewRun receipt contains an unknown state")
        content = dict(value)
        claimed = content.pop("receiptSha256", None)
        digest = hashlib.sha256(_canonical_json_bytes(content)).hexdigest()
        if claimed != digest:
            raise RuntimeError("ReviewRun receipt hash mismatch")
        return value

    def _scan_receipts(self, run: dict[str, Any]) -> list[dict[str, Any]]:
        receipt_directory = self._run_directory(run["runId"]) / "receipts"
        if not receipt_directory.is_dir():
            return []
        parsed = []
        for path in sorted(receipt_directory.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"invalid immutable receipt file: {path}") from exc
            sequence = value.get("sequence") if isinstance(value, dict) else None
            if isinstance(sequence, bool) or not isinstance(sequence, int):
                raise RuntimeError("ReviewRun receipt sequence is invalid")
            parsed.append((sequence, path, value))
        parsed.sort(key=lambda item: (item[0], item[1].name))
        if len({sequence for sequence, _, _ in parsed}) != len(parsed):
            raise RuntimeError("ReviewRun receipt chain fork detected")
        result = []
        previous = None
        for expected, (sequence, _, value) in enumerate(parsed):
            if sequence != expected:
                raise RuntimeError("ReviewRun receipt chain has a sequence gap")
            normalized = self._validate_receipt(value, run, expected, previous)
            if expected > 0 and normalized["state"] not in REVIEW_RUN_TRANSITIONS[result[-1]["state"]]:
                raise RuntimeError("ReviewRun receipt chain contains an invalid transition")
            result.append(normalized)
            previous = normalized["receiptSha256"]
        return result

    def _write_head(self, run_directory: Path, receipt: dict[str, Any]) -> None:
        payload = {
            "schema": "forgelens.review-head/v1",
            "runId": receipt["runId"],
            "sequence": receipt["sequence"],
            "state": receipt["state"],
            "receiptSha256": receipt["receiptSha256"],
        }
        encoded = _canonical_json_bytes(payload) + b"\n"
        _atomic_replace(run_directory / "head.json", encoded)
        _atomic_replace(run_directory / "head.witness.json", encoded)

    def _write_receipt(
        self,
        run: dict[str, Any],
        state: str,
        previous: dict[str, Any] | None,
        actor_id: str,
        details: dict[str, Any],
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        sequence = 0 if previous is None else previous["sequence"] + 1
        content = {
            "schema": "forgelens.decision-receipt/v1",
            "schemaVersion": 1,
            "runId": run["runId"],
            "runFingerprintSha256": run["runFingerprintSha256"],
            "sequence": sequence,
            "state": state,
            "previousReceiptSha256": None if previous is None else previous["receiptSha256"],
            "actorId": _bounded_string(actor_id, "actorId", maximum=200),
            "occurredAt": _bounded_string(occurred_at or utc_now(), "occurredAt", maximum=80),
            "details": details,
        }
        digest = hashlib.sha256(_canonical_json_bytes(content)).hexdigest()
        receipt = {**content, "receiptSha256": digest}
        run_directory = self._run_directory(run["runId"])
        destination = run_directory / "receipts" / f"{sequence:06d}-{digest}.json"
        _write_immutable(destination, self._receipt_bytes(receipt))
        self._write_head(run_directory, receipt)
        return receipt

    def _scan_pin_receipts(
        self,
        run: dict[str, Any],
        pin_id: str,
    ) -> list[dict[str, Any]]:
        pin_directory = self._run_directory(run["runId"]) / "pins" / pin_id
        if not pin_directory.is_dir():
            return []
        parsed = []
        for path in sorted(pin_directory.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"invalid immutable pin receipt: {path}") from exc
            sequence = value.get("sequence") if isinstance(value, dict) else None
            if isinstance(sequence, bool) or not isinstance(sequence, int):
                raise RuntimeError("pin receipt sequence is invalid")
            parsed.append((sequence, path, value))
            if len(parsed) > MAX_REVIEW_INVENTORY:
                raise RuntimeError("pin receipt history exceeds the bounded inventory")
        parsed.sort(key=lambda item: (item[0], item[1].name))
        if len({sequence for sequence, _, _ in parsed}) != len(parsed):
            raise RuntimeError("pin receipt chain fork detected")
        result = []
        previous = None
        for expected, (sequence, _, value) in enumerate(parsed):
            if sequence != expected:
                raise RuntimeError("pin receipt chain has a sequence gap")
            if (
                not isinstance(value, dict)
                or value.get("schema") != "forgelens.review-pin-receipt/v1"
                or value.get("runId") != run["runId"]
                or value.get("pinId") != pin_id
                or value.get("previousPinReceiptSha256") != previous
            ):
                raise RuntimeError("pin receipt identity or chain mismatch")
            content = dict(value)
            claimed = content.pop("pinReceiptSha256", None)
            digest = hashlib.sha256(_canonical_json_bytes(content)).hexdigest()
            if claimed != digest:
                raise RuntimeError("pin receipt hash mismatch")
            normalized_pin = validate_review_pin(value.get("pin"), run)
            if normalized_pin != value["pin"]:
                raise RuntimeError("pin receipt payload is not canonical")
            result.append(value)
            previous = claimed
        return result

    def _scan_pins(self, run: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        pins_directory = self._run_directory(run["runId"]) / "pins"
        if not pins_directory.is_dir():
            return [], []
        current = []
        history = []
        directories = sorted(path for path in pins_directory.iterdir() if path.is_dir())
        if len(directories) > MAX_REVIEW_INVENTORY:
            raise RuntimeError("ReviewPin inventory exceeds the bounded limit")
        for directory in directories:
            pin_id = directory.name
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", pin_id):
                raise RuntimeError("unsafe pin directory name in immutable store")
            receipts = self._scan_pin_receipts(run, pin_id)
            if not receipts:
                raise RuntimeError("pin directory has no immutable receipts")
            history.extend(receipts)
            current.append(receipts[-1]["pin"])
        current.sort(key=lambda pin: pin["pinId"])
        history.sort(key=lambda receipt: (receipt["pinId"], receipt["sequence"]))
        return current, history

    @staticmethod
    def _pin_head_binding(pin_receipts: list[dict[str, Any]]) -> tuple[list[dict[str, str]], str]:
        latest: dict[str, dict[str, Any]] = {}
        for receipt in pin_receipts:
            current = latest.get(receipt["pinId"])
            if current is None or receipt["sequence"] > current["sequence"]:
                latest[receipt["pinId"]] = receipt
        heads = [
            {"pinId": pin_id, "pinReceiptSha256": receipt["pinReceiptSha256"]}
            for pin_id, receipt in sorted(latest.items())
        ]
        return heads, hashlib.sha256(_canonical_json_bytes(heads)).hexdigest()

    def _scan_viewer_receipts(self, run: dict[str, Any]) -> list[dict[str, Any]]:
        directory = self._run_directory(run["runId"]) / "viewer-receipts"
        if not directory.is_dir():
            return []
        parsed = []
        for path in sorted(directory.glob("*.json")):
            try:
                receipt = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"invalid immutable viewer-context receipt: {path}") from exc
            sequence = receipt.get("sequence") if isinstance(receipt, dict) else None
            if isinstance(sequence, bool) or not isinstance(sequence, int):
                raise RuntimeError("viewer-context receipt sequence is invalid")
            parsed.append((sequence, path, receipt))
            if len(parsed) > MAX_REVIEW_INVENTORY:
                raise RuntimeError("viewer-context history exceeds the bounded inventory")
        parsed.sort(key=lambda item: (item[0], item[1].name))
        if len({sequence for sequence, _, _ in parsed}) != len(parsed):
            raise RuntimeError("viewer-context receipt chain fork detected")
        result = []
        previous = None
        expected_status = None
        generation = 0
        for expected, (sequence, _, receipt) in enumerate(parsed):
            if sequence != expected:
                raise RuntimeError("viewer-context receipt chain has a sequence gap")
            if not isinstance(receipt, dict) or set(receipt) != {
                "schema",
                "schemaVersion",
                "runId",
                "runFingerprintSha256",
                "sequence",
                "event",
                "generation",
                "status",
                "previousViewerReceiptSha256",
                "actorId",
                "occurredAt",
                "capture",
                "viewerReceiptSha256",
            }:
                raise RuntimeError("viewer-context receipt fields are invalid")
            if (
                receipt.get("schema") != "forgelens.viewer-context-receipt/v1"
                or receipt.get("schemaVersion") != 1
                or receipt.get("runId") != run["runId"]
                or receipt.get("runFingerprintSha256") != run["runFingerprintSha256"]
                or receipt.get("previousViewerReceiptSha256") != previous
            ):
                raise RuntimeError("viewer-context receipt identity or chain mismatch")
            event = receipt.get("event")
            status = receipt.get("status")
            if not isinstance(event, str) or not isinstance(status, str):
                raise RuntimeError("viewer-context event/status is invalid")
            if expected == 0:
                if event != "initialized" or status != "stable" or receipt.get("generation") != 0:
                    raise RuntimeError("viewer-context chain initial receipt is invalid")
            else:
                prior_status = result[-1]["status"]
                allowed = {
                    "stable": {"context_lost": "context_lost"},
                    "context_lost": {"context_restored": "recapture_required"},
                    "recapture_required": {
                        "recaptured": "stable",
                        "context_lost": "context_lost",
                    },
                }
                expected_status = allowed.get(prior_status, {}).get(event)
                if status != expected_status:
                    raise RuntimeError("viewer-context receipt chain contains an invalid transition")
                if event == "context_lost":
                    generation += 1
                if receipt.get("generation") != generation:
                    raise RuntimeError("viewer-context generation mismatch")
            capture = receipt.get("capture")
            if event == "recaptured":
                if not isinstance(capture, dict) or set(capture) != {
                    "path",
                    "sha256",
                    "bytes",
                    "width",
                    "height",
                    "evidencePath",
                    "cameraProfile",
                    "aov",
                    "geometryIdentitySha256",
                }:
                    raise RuntimeError("viewer recapture receipt has no exact capture identity")
                expected_prefix = (
                    self._run_directory(run["runId"]) / "viewer-captures"
                ).relative_to(self.root).as_posix() + "/"
                relative = capture.get("path")
                if not isinstance(relative, str) or not relative.startswith(expected_prefix):
                    raise RuntimeError("viewer recapture path escapes its immutable run directory")
                capture_path = safe_repo_path(self.root, relative)
                try:
                    payload = capture_path.read_bytes()
                except OSError as exc:
                    raise RuntimeError("viewer recapture PNG is missing") from exc
                if (
                    hashlib.sha256(payload).hexdigest() != capture.get("sha256")
                    or len(payload) != capture.get("bytes")
                ):
                    raise RuntimeError("viewer recapture PNG identity mismatch")
                try:
                    dimensions = _png_dimensions(capture_path, "viewer recapture")
                except ValueError as exc:
                    raise RuntimeError("viewer recapture PNG validation failed") from exc
                if list(dimensions) != [capture.get("width"), capture.get("height")]:
                    raise RuntimeError("viewer recapture PNG dimensions mismatch")
                if not any(
                    artifact["path"] == capture["evidencePath"]
                    and artifact["sha256"] == capture["sha256"]
                    and artifact["bytes"] == capture["bytes"]
                    and artifact["width"] == dimensions[0]
                    and artifact["height"] == dimensions[1]
                    and artifact["cameraProfile"] == capture["cameraProfile"]
                    and artifact["aov"] == capture["aov"]
                    and artifact["geometryIdentitySha256"] == capture["geometryIdentitySha256"]
                    for artifact in run["lineage"]["producedArtifactInventory"]
                ):
                    raise RuntimeError("viewer recapture is not bound to an immutable produced artifact")
            elif capture is not None:
                raise RuntimeError("non-recapture viewer event contains a capture identity")
            content = dict(receipt)
            claimed = content.pop("viewerReceiptSha256", None)
            digest = hashlib.sha256(_canonical_json_bytes(content)).hexdigest()
            if claimed != digest:
                raise RuntimeError("viewer-context receipt hash mismatch")
            result.append(receipt)
            previous = claimed
        return result

    def _write_viewer_receipt(
        self,
        run: dict[str, Any],
        event: str,
        status: str,
        generation: int,
        previous: dict[str, Any] | None,
        actor_id: str,
        capture: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sequence = 0 if previous is None else previous["sequence"] + 1
        content = {
            "schema": "forgelens.viewer-context-receipt/v1",
            "schemaVersion": 1,
            "runId": run["runId"],
            "runFingerprintSha256": run["runFingerprintSha256"],
            "sequence": sequence,
            "event": event,
            "generation": generation,
            "status": status,
            "previousViewerReceiptSha256": (
                None if previous is None else previous["viewerReceiptSha256"]
            ),
            "actorId": _bounded_string(actor_id, "viewerContext.actorId", maximum=200),
            "occurredAt": utc_now(),
            "capture": capture,
        }
        digest = hashlib.sha256(_canonical_json_bytes(content)).hexdigest()
        receipt = {**content, "viewerReceiptSha256": digest}
        destination = (
            self._run_directory(run["runId"])
            / "viewer-receipts"
            / f"{sequence:06d}-{digest}.json"
        )
        _write_immutable(destination, _canonical_json_bytes(receipt) + b"\n")
        return receipt

    @staticmethod
    def _viewer_context(receipts: list[dict[str, Any]]) -> dict[str, Any]:
        if not receipts:
            raise RuntimeError("ReviewRun has no initial viewer-context receipt")
        head = receipts[-1]
        return {
            "schema": "forgelens.viewer-context/v1",
            "status": head["status"],
            "generation": head["generation"],
            "headReceiptSha256": head["viewerReceiptSha256"],
            "receipts": receipts,
        }

    def record_viewer_event(
        self,
        run_id: str,
        event: str,
        *,
        expected_previous_sha256: str,
        actor_id: str,
        capture_png_base64: Any = None,
    ) -> dict[str, Any]:
        event = _bounded_string(event, "viewerContext.event", maximum=40)
        with self._exclusive():
            snapshot = self._load_unlocked(run_id)
            if snapshot["state"] not in {"awaiting_evidence", "awaiting_human"}:
                raise TransitionError("viewer context is immutable after ReviewRun submission")
            run = {**snapshot["reviewRun"], "decisionChainHeadSha256": None}
            run = validate_review_run(run)
            previous = snapshot["viewerContext"]["receipts"][-1]
            if expected_previous_sha256 != previous["viewerReceiptSha256"]:
                raise TransitionError("viewer-context expected previous receipt does not match current head")
            allowed = {
                "stable": {"context_lost": "context_lost"},
                "context_lost": {"context_restored": "recapture_required"},
                "recapture_required": {
                    "recaptured": "stable",
                    "context_lost": "context_lost",
                },
            }
            status = allowed.get(previous["status"], {}).get(event)
            if status is None:
                raise TransitionError(
                    f"invalid viewer-context transition {previous['status']} -> {event}"
                )
            generation = previous["generation"] + (1 if event == "context_lost" else 0)
            capture = None
            if event == "recaptured":
                encoded = _bounded_string(
                    capture_png_base64,
                    "viewerContext.capturePngBase64",
                    maximum=MAX_EVIDENCE_BYTES * 2,
                )
                try:
                    capture_bytes = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise ValueError("viewer recapture is not strict base64") from exc
                if not capture_bytes or len(capture_bytes) > MAX_EVIDENCE_BYTES:
                    raise ValueError("viewer recapture PNG is empty or exceeds the evidence bound")
                capture_sha256 = hashlib.sha256(capture_bytes).hexdigest()
                run_directory = self._run_directory(run["runId"])
                temporary_fd, temporary_name = tempfile.mkstemp(
                    prefix=".viewer-capture-",
                    suffix=".png",
                    dir=run_directory,
                )
                temporary_path = Path(temporary_name)
                try:
                    with os.fdopen(temporary_fd, "wb") as handle:
                        handle.write(capture_bytes)
                        handle.flush()
                        os.fsync(handle.fileno())
                    width, height = _png_dimensions(temporary_path, "viewer recapture")
                    if not any(
                        camera["width"] == width and camera["height"] == height
                        for camera in run["cameraInventory"]
                    ):
                        raise ValueError(
                            "viewer recapture dimensions do not match any canonical-plan camera"
                        )
                    bound_artifact = next(
                        (
                            artifact
                            for artifact in run["lineage"]["producedArtifactInventory"]
                            if artifact["sha256"] == capture_sha256
                            and artifact["bytes"] == len(capture_bytes)
                            and artifact["width"] == width
                            and artifact["height"] == height
                        ),
                        None,
                    )
                    if bound_artifact is None:
                        raise ValueError(
                            "viewer recapture must exactly match a bound produced artifact"
                        )
                finally:
                    temporary_path.unlink(missing_ok=True)
                capture_path = (
                    run_directory
                    / "viewer-captures"
                    / f"generation-{generation:06d}-{capture_sha256}.png"
                )
                _write_immutable(capture_path, capture_bytes)
                capture = {
                    "path": capture_path.relative_to(self.root).as_posix(),
                    "sha256": capture_sha256,
                    "bytes": len(capture_bytes),
                    "width": width,
                    "height": height,
                    "evidencePath": bound_artifact["path"],
                    "cameraProfile": bound_artifact["cameraProfile"],
                    "aov": bound_artifact["aov"],
                    "geometryIdentitySha256": bound_artifact["geometryIdentitySha256"],
                }
            elif capture_png_base64 is not None:
                raise ValueError("capturePngBase64 is accepted only for recaptured events")
            return self._write_viewer_receipt(
                run,
                event,
                status,
                generation,
                previous,
                actor_id,
                capture,
            )

    def save_pin(self, run_id: str, pin: Any) -> dict[str, Any]:
        with self._exclusive():
            snapshot = self._load_unlocked(run_id)
            if snapshot["state"] not in {"awaiting_evidence", "awaiting_human"}:
                raise TransitionError("pins are immutable after ReviewRun submission")
            run = validate_review_run(
                {**snapshot["reviewRun"], "decisionChainHeadSha256": None}
            )
            normalized = validate_review_pin(pin, run)
            receipts = self._scan_pin_receipts(run, normalized["pinId"])
            previous = receipts[-1] if receipts else None
            sequence = 0 if previous is None else previous["sequence"] + 1
            content = {
                "schema": "forgelens.review-pin-receipt/v1",
                "schemaVersion": 1,
                "runId": run["runId"],
                "runFingerprintSha256": run["runFingerprintSha256"],
                "pinId": normalized["pinId"],
                "sequence": sequence,
                "previousPinReceiptSha256": (
                    None if previous is None else previous["pinReceiptSha256"]
                ),
                "recordedAt": utc_now(),
                "pin": normalized,
            }
            digest = hashlib.sha256(_canonical_json_bytes(content)).hexdigest()
            receipt = {**content, "pinReceiptSha256": digest}
            destination = (
                self._run_directory(run["runId"])
                / "pins"
                / normalized["pinId"]
                / f"{sequence:06d}-{digest}.json"
            )
            _write_immutable(destination, _canonical_json_bytes(receipt) + b"\n")
            return receipt

    @staticmethod
    def _run_file_identities(run: dict[str, Any]) -> list[dict[str, Any]]:
        lineage = run["lineage"]
        return [
            lineage["build"],
            lineage["replay"],
            lineage["verifier"],
            lineage["canonicalPlanPacket"],
            lineage["evidenceManifest"],
            lineage["generation"]["provider"],
            lineage["generation"]["checkpoint"],
            lineage["generation"]["retarget"],
            lineage["geometry"],
            *lineage["producedArtifactInventory"],
        ]

    @classmethod
    def _run_file_paths(cls, run: dict[str, Any]) -> set[str]:
        return {identity["path"] for identity in cls._run_file_identities(run)}

    def allowed_file_identities(self, relative: str) -> tuple[dict[str, Any], ...]:
        identities: list[dict[str, Any]] = []
        with self._exclusive():
            if not self.directory.is_dir():
                return ()
            for manifest_path in sorted(self.directory.glob("*/run.json")):
                try:
                    run = validate_review_run(json.loads(manifest_path.read_text(encoding="utf-8")))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    raise RuntimeError("invalid immutable ReviewRun manifest while building file identities") from exc
                if manifest_path.parent.name != run["runId"]:
                    raise RuntimeError("ReviewRun manifest directory identity mismatch")
                identities.extend(
                    identity for identity in self._run_file_identities(run) if identity["path"] == relative
                )
        return tuple(identities)

    def is_allowed_file(self, relative: str) -> bool:
        return bool(self.allowed_file_identities(relative))

    def _load_unlocked(self, run_id: str) -> dict[str, Any]:
        run_directory = self._run_directory(run_id)
        manifest_path = run_directory / "run.json"
        if not manifest_path.is_file():
            raise ValueError("ReviewRun does not exist")
        try:
            run = validate_review_run(json.loads(manifest_path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("immutable ReviewRun manifest is invalid") from exc
        if run["runId"] != run_id:
            raise RuntimeError("ReviewRun manifest runId does not match its immutable directory")
        receipts = self._scan_receipts(run)
        if not receipts:
            raise RuntimeError("ReviewRun has no initial decision receipt")
        for index, receipt in enumerate(receipts):
            if receipt["state"] != "pass":
                continue
            details = receipt.get("details")
            if not isinstance(details, dict) or set(details) != {
                "externalHumanDecisionAuthority",
                "externalDecisionFile",
                "externalDecisionRepositoryRevision",
                "externalDecisionSha256",
                "reviewerPseudonym",
                "sourceRevision",
                "submittedReceiptSha256",
            }:
                raise RuntimeError("terminal pass has no exact external human decision binding")
            if index == 0 or receipts[index - 1]["state"] != "submitted":
                raise RuntimeError("terminal pass does not follow a submitted decision")
            submitted = receipts[index - 1]
            decision_file = details["externalDecisionFile"]
            revision = details["externalDecisionRepositoryRevision"]
            if (
                details["externalHumanDecisionAuthority"]
                != "tracked-clean-external-human-decision-file"
                or details["submittedReceiptSha256"] != submitted["receiptSha256"]
                or details["reviewerPseudonym"] != submitted["details"]["reviewerId"]
                or details["sourceRevision"] != run["lineage"]["code"]["revision"]
                or not isinstance(decision_file, dict)
                or decision_file.get("repositoryState") != "tracked-clean"
                or details["externalDecisionSha256"] != decision_file.get("sha256")
                or not isinstance(revision, str)
                or not FULL_REVISION_PATTERN.fullmatch(revision)
            ):
                raise RuntimeError("terminal pass external human decision metadata mismatch")
            if _git_command(self.root, ["cat-file", "-e", f"{revision}^{{commit}}"]).returncode != 0:
                raise RuntimeError("terminal pass external human decision commit is unreachable")
            if _git_command(self.root, ["merge-base", "--is-ancestor", revision, "HEAD"]).returncode != 0:
                raise RuntimeError("terminal pass external human decision commit is not in current history")
            committed = _git_command(
                self.root,
                ["show", f"{revision}:{decision_file.get('path', '')}"],
            )
            if (
                committed.returncode != 0
                or hashlib.sha256(committed.stdout).hexdigest() != decision_file.get("sha256")
                or len(committed.stdout) != decision_file.get("bytes")
            ):
                raise RuntimeError("terminal pass external human decision bytes are not recoverable")
        head = receipts[-1]
        expected_head = {
            "schema": "forgelens.review-head/v1",
            "runId": run["runId"],
            "sequence": head["sequence"],
            "state": head["state"],
            "receiptSha256": head["receiptSha256"],
        }
        stored_heads = []
        for head_path in (run_directory / "head.json", run_directory / "head.witness.json"):
            try:
                candidate = json.loads(head_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if (
                isinstance(candidate, dict)
                and candidate.get("schema") == "forgelens.review-head/v1"
                and candidate.get("runId") == run["runId"]
                and not isinstance(candidate.get("sequence"), bool)
                and isinstance(candidate.get("sequence"), int)
                and candidate.get("state") in REVIEW_RUN_STATES
                and isinstance(candidate.get("receiptSha256"), str)
            ):
                stored_heads.append(candidate)
        if not stored_heads:
            self._write_head(run_directory, head)
        else:
            highest_sequence = max(candidate["sequence"] for candidate in stored_heads)
            highest = [candidate for candidate in stored_heads if candidate["sequence"] == highest_sequence]
            if any(candidate != highest[0] for candidate in highest[1:]):
                raise RuntimeError("ReviewRun durable decision-head witnesses conflict")
            stored_head = highest[0]
            if stored_head == expected_head:
                if len(stored_heads) != 2 or any(candidate != expected_head for candidate in stored_heads):
                    self._write_head(run_directory, head)
            elif stored_head["sequence"] < head["sequence"]:
                self._write_head(run_directory, head)
            elif stored_head["sequence"] > head["sequence"]:
                raise RuntimeError("ReviewRun receipt tail is missing behind the durable decision head")
            else:
                raise RuntimeError("ReviewRun durable decision head conflicts with its receipt chain")
        pins, pin_receipts = self._scan_pins(run)
        pin_heads, pin_set_sha256 = self._pin_head_binding(pin_receipts)
        viewer_receipts = self._scan_viewer_receipts(run)
        viewer_context = self._viewer_context(viewer_receipts)
        for receipt in receipts:
            if receipt["state"] != "submitted":
                continue
            details = receipt.get("details")
            if (
                not isinstance(details, dict)
                or details.get("reviewPinHeads") != pin_heads
                or details.get("reviewPinSetSha256") != pin_set_sha256
                or details.get("viewerContextReceiptSha256")
                != viewer_context["headReceiptSha256"]
                or details.get("viewerContextGeneration") != viewer_context["generation"]
            ):
                raise RuntimeError(
                    "submitted decision receipt does not match the immutable ReviewPin set or viewer-context binding"
                )
        exported_run = {**run, "decisionChainHeadSha256": head["receiptSha256"]}
        pin_statuses: list[dict[str, Any]] = []
        for pin in pins:
            try:
                context = derive_review_pin_context(self.root, run, pin)
                pin_statuses.append(review_pin_status(pin, run, context))
            except (OSError, ValueError):
                pin_statuses.append(
                    {
                        "schema": "forgelens.review-pin-status/v1",
                        "pinId": pin["pinId"],
                        "status": "stale",
                        "mismatches": ["lineage_unavailable"],
                        "aovGeometryCompatible": False,
                        "context": None,
                    }
                )
        return {
            "schema": "forgelens.review-run-snapshot/v1",
            "reviewRun": exported_run,
            "runId": run["runId"],
            "state": head["state"],
            "headReceiptSha256": head["receiptSha256"],
            "receipts": receipts,
            "pins": pins,
            "pinStatuses": pin_statuses,
            "pinReceipts": pin_receipts,
            "viewerContext": viewer_context,
            "eligibility": review_run_eligibility(
                self.root,
                run,
                pin_statuses=pin_statuses,
                viewer_context=viewer_context,
            ),
        }

    def create(self, run: Any) -> dict[str, Any]:
        run = validate_review_run(run)
        if run["decisionChainHeadSha256"] is not None:
            raise ValueError("new ReviewRun manifest decisionChainHeadSha256 must be null")
        with self._exclusive():
            run_directory = self._run_directory(run["runId"])
            manifest = _canonical_json_bytes(run) + b"\n"
            _write_immutable(run_directory / "run.json", manifest)
            receipts = self._scan_receipts(run)
            if not receipts:
                self._write_receipt(
                    run,
                    "awaiting_evidence",
                    None,
                    "forgelens-server",
                    {"reason": "ReviewRun created; evidence is not yet admitted"},
                    occurred_at=run["createdAt"],
                )
            viewer_receipts = self._scan_viewer_receipts(run)
            if not viewer_receipts:
                self._write_viewer_receipt(
                    run,
                    "initialized",
                    "stable",
                    0,
                    None,
                    "forgelens-server",
                )
            return self._load_unlocked(run["runId"])

    def load(self, run_id: str) -> dict[str, Any]:
        with self._exclusive():
            return self._load_unlocked(run_id)

    def export_admission_packet(self, run_id: str) -> dict[str, Any]:
        with self._exclusive():
            snapshot = self._load_unlocked(run_id)
            packet = {
                "schema": "forgelens.admission-packet/v1",
                "exportedAt": utc_now(),
                "reviewRun": snapshot["reviewRun"],
                "state": snapshot["state"],
                "receipts": snapshot["receipts"],
                "pins": snapshot["pins"],
                "pinReceipts": snapshot["pinReceipts"],
                "eligibility": snapshot["eligibility"],
            }
            payload = _canonical_json_bytes(packet) + b"\n"
            digest = hashlib.sha256(payload).hexdigest()
            destination = self._run_directory(run_id) / "exports" / f"{digest}.json"
            _write_immutable(destination, payload)
            return {
                "schema": "forgelens.admission-export/v1",
                "runId": run_id,
                "exportPath": destination.relative_to(self.root).as_posix(),
                "exportFileSha256": digest,
                "bytes": len(payload),
            }

    def transition(
        self,
        run_id: str,
        target_state: str,
        *,
        expected_previous_sha256: str,
        actor_id: str,
        details: Any,
        pin_statuses: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        target_state = _bounded_string(target_state, "targetState", REVIEW_RUN_STATES)
        expected_previous_sha256 = _hex_digest(expected_previous_sha256, "expectedPreviousSha256")
        with self._exclusive():
            snapshot = self._load_unlocked(run_id)
            current_state = snapshot["state"]
            if current_state in TERMINAL_REVIEW_STATES:
                raise TransitionError(f"ReviewRun is terminal in state {current_state}; immutable decisions cannot be edited")
            if snapshot["headReceiptSha256"] != expected_previous_sha256:
                raise TransitionError("ReviewRun decision head changed concurrently; reload before transition")
            if target_state not in REVIEW_RUN_TRANSITIONS[current_state]:
                raise TransitionError(f"transition {current_state} -> {target_state} is not allowed")
            run = validate_review_run(
                {
                    **snapshot["reviewRun"],
                    "decisionChainHeadSha256": None,
                }
            )
            eligibility = review_run_eligibility(
                self.root,
                run,
                pin_statuses=pin_statuses,
                viewer_context=snapshot["viewerContext"],
            )
            normalized_details: dict[str, Any]
            if target_state == "awaiting_human":
                if eligibility["blockers"]:
                    raise TransitionError(
                        "ReviewRun evidence is not eligible for human review: " + ", ".join(eligibility["blockers"])
                    )
                normalized_details = {}
            elif target_state == "submitted":
                if eligibility["blockers"]:
                    raise TransitionError(
                        "ReviewRun submission is blocked: " + ", ".join(eligibility["blockers"])
                    )
                normalized_details = _validate_human_attestation(details, run, actor_id)
                pin_heads, pin_set_sha256 = self._pin_head_binding(snapshot["pinReceipts"])
                normalized_details["reviewPinHeads"] = pin_heads
                normalized_details["reviewPinSetSha256"] = pin_set_sha256
                normalized_details["viewerContextReceiptSha256"] = snapshot["viewerContext"][
                    "headReceiptSha256"
                ]
                normalized_details["viewerContextGeneration"] = snapshot["viewerContext"][
                    "generation"
                ]
            else:
                if not isinstance(details, dict):
                    raise ValueError("transition details must be an object")
                encoded_details = _canonical_json_bytes(details)
                if len(encoded_details) > MAX_REQUEST_BYTES:
                    raise ValueError("transition details exceed the request byte limit")
                normalized_details = json.loads(encoded_details.decode("utf-8"))
            previous = snapshot["receipts"][-1]
            if target_state == "pass":
                raise TransitionError(
                    "pass requires an external human decision import; browser/API possession is insufficient"
                )
            return self._write_receipt(
                run,
                target_state,
                previous,
                actor_id,
                normalized_details,
            )

    def import_external_human_decision(self, run_id: str, decision_path: str) -> dict[str, Any]:
        with self._exclusive():
            snapshot = self._load_unlocked(run_id)
            if snapshot["state"] != "submitted":
                raise TransitionError("external human decision import requires a submitted ReviewRun")
            run = snapshot["reviewRun"]
            run["decisionChainHeadSha256"] = None
            run = validate_review_run(run)
            identity = _file_identity(self.root, decision_path, "externalHumanDecisionPath")
            if identity["repositoryState"] != "tracked-clean":
                raise TransitionError("external human decision import must be a tracked-clean repository file")
            path = safe_repo_path(self.root, identity["path"])
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != identity["sha256"] or len(raw) != identity["bytes"]:
                raise TransitionError("external human decision changed while being read")
            if len(raw) > MAX_REQUEST_BYTES:
                raise TransitionError("external human decision import exceeds the bounded JSON size")
            try:
                decision = json.loads(
                    raw.decode("utf-8"),
                    object_pairs_hook=_json_object_without_duplicates,
                    parse_constant=_reject_non_finite_json_constant,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                raise TransitionError(f"external human decision import is invalid JSON: {exc}") from exc
            expected_fields = {
                "schema",
                "runId",
                "submittedReceiptSha256",
                "reviewerPseudonym",
                "finalDecision",
                "attestation",
                "decisionAt",
                "sourceRevision",
            }
            if not isinstance(decision, dict) or set(decision) != expected_fields:
                raise TransitionError("external human decision fields do not exactly match the v1 schema")
            if decision.get("schema") != "forgelens.external-human-decision/v1":
                raise TransitionError("external human decision schema mismatch")
            current = snapshot["receipts"][-1]
            submitted_details = current["details"]
            if (
                decision.get("runId") != run_id
                or decision.get("submittedReceiptSha256") != current["receiptSha256"]
                or decision.get("reviewerPseudonym") != submitted_details.get("reviewerId")
                or decision.get("sourceRevision") != run["lineage"]["code"]["revision"]
                or decision.get("finalDecision") != "pass"
                or submitted_details.get("proposedDecision") != "pass"
            ):
                raise TransitionError("external human decision does not match the submitted immutable lineage")
            if decision.get("attestation") != (
                "I independently approve this exact immutable ReviewRun for admission."
            ):
                raise TransitionError("external human decision requires the exact independent approval attestation")
            decision_at = _parse_attestation_time(decision.get("decisionAt"), "externalHumanDecision.decisionAt")
            submitted_at = _parse_attestation_time(
                submitted_details.get("decisionAt"), "submittedAttestation.decisionAt"
            )
            if decision_at < submitted_at:
                raise TransitionError("external human decision precedes the submitted blind decision")
            decision_repository = _repository_identity(self.root)
            if (
                decision_repository["revision"] == "outside-git"
                or not decision_repository["reachable"]
                or not decision_repository["trackedClean"]
            ):
                raise TransitionError(
                    "external human decision import requires a reachable tracked-clean repository revision"
                )
            committed_decision = _git_command(
                self.root,
                ["show", f"{decision_repository['revision']}:{identity['path']}"],
            )
            if committed_decision.returncode != 0 or committed_decision.stdout != raw:
                raise TransitionError(
                    "external human decision committed bytes are not recoverable at the measured revision"
                )
            eligibility = review_run_eligibility(
                self.root,
                run,
                pin_statuses=snapshot["pinStatuses"],
                viewer_context=snapshot["viewerContext"],
            )
            if eligibility["passBlockers"]:
                raise TransitionError(
                    "external human pass is blocked: " + ", ".join(eligibility["passBlockers"])
                )
            return self._write_receipt(
                run,
                "pass",
                current,
                f"external-human-decision-import:{decision['reviewerPseudonym']}",
                {
                    "externalHumanDecisionAuthority": "tracked-clean-external-human-decision-file",
                    "externalDecisionFile": identity,
                    "externalDecisionRepositoryRevision": decision_repository["revision"],
                    "externalDecisionSha256": hashlib.sha256(raw).hexdigest(),
                    "reviewerPseudonym": decision["reviewerPseudonym"],
                    "sourceRevision": decision["sourceRevision"],
                    "submittedReceiptSha256": current["receiptSha256"],
                },
            )


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


def _catalog_file_allowlist(catalog: dict[str, Any]) -> frozenset[str]:
    allowed: set[str] = set()
    assets = catalog.get("assets", []) if isinstance(catalog, dict) else []
    if not isinstance(assets, list):
        return frozenset()
    for record in assets:
        if not isinstance(record, dict):
            continue
        path = record.get("path")
        if isinstance(path, str):
            allowed.add(path)
        evidence = record.get("evidenceImages", [])
        if isinstance(evidence, list):
            allowed.update(value for value in evidence if isinstance(value, str))
    return frozenset(allowed)


def _catalog_file_identities(
    root: Path,
    catalog: dict[str, Any],
) -> dict[str, tuple[dict[str, Any], ...]]:
    result: dict[str, tuple[dict[str, Any], ...]] = {}
    for relative in sorted(_catalog_file_allowlist(catalog)):
        try:
            identity = _file_identity(root, relative, f"catalogFile[{relative}]")
        except (OSError, ValueError):
            continue
        result[relative] = (identity,)
    return result


def _startup_file_identities(
    root: Path,
    catalog: dict[str, Any],
    replay_config: ReplayRunConfig | None,
) -> dict[str, tuple[dict[str, Any], ...]]:
    result = _catalog_file_identities(root, catalog)
    if replay_config is None:
        return result
    for index, relative in enumerate(replay_config.capture_paths):
        identity = _file_identity(root, relative, f"replayCapture[{index}]")
        result[relative] = (*result.get(relative, ()), identity)
    return result


def _allowlisted_repo_file(root: Path, relative: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or not relative_path.parts or ".." in relative_path.parts:
        raise ValueError("file path is not a canonical repository-relative path")
    cursor = root.resolve()
    for part in relative_path.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("symlinked files are not eligible review inputs")
    resolved = safe_repo_path(root, relative)
    if resolved.relative_to(root.resolve()).as_posix() != relative:
        raise ValueError("file path is not canonically spelled")
    return resolved


def _json_object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_non_finite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _strict_json_loads(value: str | bytes) -> Any:
    return json.loads(
        value,
        object_pairs_hook=_json_object_without_duplicates,
        parse_constant=_reject_non_finite_json_constant,
    )


MOTION_LAB_VIEW_IDS = (
    "kimodo-teacher",
    "ardy-proposal",
    "motionbricks-target",
    "physics-execution",
)
MOTION_LAB_TRACKS = ("text", "fullBody", "root", "endEffectors", "contacts")
MOTION_LAB_METRICS = ("fkResidual", "footDrift", "com", "grip", "weaponPath")
MOTION_LAB_ACTIONS = {"approved", "rejected", "changes-requested"}


def _motion_lab_id(value: Any, field: str) -> str:
    value = _bounded_string(value, field, maximum=200)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise ValueError(f"{field} must contain only safe identifier characters")
    return value


def _motion_lab_frame(value: Any, field: str, frame_count: int) -> int:
    frame = _non_negative_integer(value, field)
    if frame >= frame_count:
        raise ValueError(f"{field} is outside the declared Motion Lab frame range")
    return frame


def _motion_lab_vector(value: Any, field: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{field} must be a three-component vector")
    result = []
    for index, component in enumerate(value):
        if isinstance(component, bool) or not isinstance(component, (int, float)) or not math.isfinite(component):
            raise ValueError(f"{field}[{index}] must be finite")
        result.append(float(component))
    return result


def validate_motion_lab(value: Any) -> dict[str, Any]:
    """Validate the standalone, non-admission Motion Lab payload fail closed."""
    value = _exact_object_fields(
        value,
        "motion lab",
        {"schema", "motionLabId", "revision", "fps", "frameCount", "tracks", "views", "candidates", "metrics"},
        {"lineage"},
    )
    if value["schema"] != "forgelens.motion-lab/v1":
        raise ValueError("motion lab schema must be forgelens.motion-lab/v1")
    motion_lab_id = _motion_lab_id(value["motionLabId"], "motionLabId")
    revision = _bounded_string(value["revision"], "revision", maximum=64)
    if not re.fullmatch(r"[0-9a-f]{7,64}", revision):
        raise ValueError("motion lab revision must be a lowercase hexadecimal revision")
    fps = _non_negative_integer(value["fps"], "fps")
    if not 1 <= fps <= 240:
        raise ValueError("motion lab fps must be within [1, 240]")
    frame_count = _non_negative_integer(value["frameCount"], "frameCount")
    if not 1 <= frame_count <= 100_000:
        raise ValueError("motion lab frameCount must be within [1, 100000]")
    tracks = _exact_object_fields(value["tracks"], "motion lab tracks", set(MOTION_LAB_TRACKS))
    normalized_tracks: dict[str, list[dict[str, Any]]] = {}
    for name in MOTION_LAB_TRACKS:
        raw_entries = tracks[name]
        if not isinstance(raw_entries, list) or len(raw_entries) > frame_count:
            raise ValueError(f"motion lab track {name} must be a bounded list")
        entries: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_entries):
            field = f"tracks.{name}[{index}]"
            if name in {"text", "fullBody"}:
                raw = _exact_object_fields(raw, field, {"frame", "label"})
                entries.append({"frame": _motion_lab_frame(raw["frame"], f"{field}.frame", frame_count), "label": _bounded_string(raw["label"], f"{field}.label", maximum=400)})
            elif name == "root":
                raw = _exact_object_fields(raw, field, {"frame", "position"})
                entries.append({"frame": _motion_lab_frame(raw["frame"], f"{field}.frame", frame_count), "position": _motion_lab_vector(raw["position"], f"{field}.position")})
            elif name == "endEffectors":
                raw = _exact_object_fields(raw, field, {"frame", "jointId", "position"})
                entries.append({"frame": _motion_lab_frame(raw["frame"], f"{field}.frame", frame_count), "jointId": _motion_lab_id(raw["jointId"], f"{field}.jointId"), "position": _motion_lab_vector(raw["position"], f"{field}.position")})
            else:
                raw = _exact_object_fields(raw, field, {"frame", "objectId", "state"})
                state = _bounded_string(raw["state"], f"{field}.state", {"planted", "touching", "airborne", "released"})
                entries.append({"frame": _motion_lab_frame(raw["frame"], f"{field}.frame", frame_count), "objectId": _motion_lab_id(raw["objectId"], f"{field}.objectId"), "state": state})
        normalized_tracks[name] = entries
    raw_views = value["views"]
    if not isinstance(raw_views, list) or len(raw_views) != len(MOTION_LAB_VIEW_IDS):
        raise ValueError("motion lab must contain exactly the four synchronized views")
    views: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_views):
        raw = _exact_object_fields(
            raw,
            f"views[{index}]",
            {"id", "label", "frames"},
            {"jointNames", "parents"},
        )
        view_id = _motion_lab_id(raw["id"], f"views[{index}].id")
        joint_names = raw.get("jointNames")
        parents = raw.get("parents")
        if (joint_names is None) != (parents is None):
            raise ValueError(f"views[{index}] jointNames and parents must appear together")
        if joint_names is not None:
            if not isinstance(joint_names, list) or not 1 <= len(joint_names) <= 256:
                raise ValueError(f"views[{index}].jointNames must contain 1..256 joints")
            joint_names = [
                _motion_lab_id(name, f"views[{index}].jointNames[{joint_index}]")
                for joint_index, name in enumerate(joint_names)
            ]
            if not isinstance(parents, list) or len(parents) != len(joint_names):
                raise ValueError(f"views[{index}].parents must match jointNames")
            normalized_parents = []
            for joint_index, parent in enumerate(parents):
                if isinstance(parent, bool) or not isinstance(parent, int) or not -1 <= parent < len(joint_names):
                    raise ValueError(f"views[{index}].parents[{joint_index}] is invalid")
                if joint_index == 0 and parent != -1:
                    raise ValueError(f"views[{index}] root parent must be -1")
                if joint_index and parent >= joint_index:
                    raise ValueError(f"views[{index}] parents must precede children")
                normalized_parents.append(parent)
            parents = normalized_parents
        frames = raw["frames"]
        if not isinstance(frames, list) or not frames or len(frames) > frame_count:
            raise ValueError(f"views[{index}].frames must be a non-empty bounded list")
        normalized_frames = []
        for frame_index, frame in enumerate(frames):
            frame = _exact_object_fields(
                frame,
                f"views[{index}].frames[{frame_index}]",
                {"frame", "root"},
                {"joints"},
            )
            normalized_frame = {
                "frame": _motion_lab_frame(frame["frame"], f"views[{index}].frames[{frame_index}].frame", frame_count),
                "root": _motion_lab_vector(frame["root"], f"views[{index}].frames[{frame_index}].root"),
            }
            if "joints" in frame:
                if joint_names is None or not isinstance(frame["joints"], list) or len(frame["joints"]) != len(joint_names):
                    raise ValueError(f"views[{index}].frames[{frame_index}].joints must match jointNames")
                normalized_frame["joints"] = [
                    _motion_lab_vector(joint, f"views[{index}].frames[{frame_index}].joints[{joint_index}]")
                    for joint_index, joint in enumerate(frame["joints"])
                ]
            elif joint_names is not None:
                raise ValueError(f"views[{index}].frames[{frame_index}] is missing joints")
            normalized_frames.append(normalized_frame)
        normalized_view = {
            "id": view_id,
            "label": _bounded_string(raw["label"], f"views[{index}].label", maximum=200),
            "frames": normalized_frames,
        }
        if joint_names is not None:
            normalized_view.update({"jointNames": joint_names, "parents": parents})
        views.append(normalized_view)
    if tuple(view["id"] for view in views) != MOTION_LAB_VIEW_IDS:
        raise ValueError("motion lab views must be ordered Kimodo, ARDY, MotionBricks, then physics")
    raw_candidates = value["candidates"]
    if not isinstance(raw_candidates, list) or not 2 <= len(raw_candidates) <= 32:
        raise ValueError("motion lab candidates must contain 2..32 bounded candidates")
    candidates = []
    candidate_ids = set()
    for index, raw in enumerate(raw_candidates):
        raw = _exact_object_fields(raw, f"candidates[{index}]", {"id", "label", "viewId"})
        candidate_id = _motion_lab_id(raw["id"], f"candidates[{index}].id")
        if candidate_id in candidate_ids:
            raise ValueError("motion lab candidate ids must be unique")
        candidate_ids.add(candidate_id)
        view_id = _motion_lab_id(raw["viewId"], f"candidates[{index}].viewId")
        if view_id not in MOTION_LAB_VIEW_IDS:
            raise ValueError("motion lab candidate references an unknown synchronized view")
        candidates.append({"id": candidate_id, "label": _bounded_string(raw["label"], f"candidates[{index}].label", maximum=200), "viewId": view_id})
    metrics = _exact_object_fields(value["metrics"], "motion lab metrics", set(MOTION_LAB_METRICS))
    normalized_metrics: dict[str, dict[str, Any]] = {}
    for name in MOTION_LAB_METRICS:
        metric = _exact_object_fields(metrics[name], f"metrics.{name}", {"unit", "series"})
        series = metric["series"]
        if not isinstance(series, list) or len(series) != frame_count:
            raise ValueError(f"metrics.{name}.series must have exactly frameCount values")
        normalized = []
        for index, number in enumerate(series):
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
                raise ValueError(f"metrics.{name}.series[{index}] must be finite")
            normalized.append(float(number))
        normalized_metrics[name] = {"unit": _bounded_string(metric["unit"], f"metrics.{name}.unit", maximum=30), "series": normalized}
    normalized = {"schema": "forgelens.motion-lab/v1", "motionLabId": motion_lab_id, "revision": revision, "fps": fps, "frameCount": frame_count, "tracks": normalized_tracks, "views": views, "candidates": candidates, "metrics": normalized_metrics}
    if "lineage" in value:
        lineage = _exact_object_fields(
            value["lineage"],
            "motion lab lineage",
            {"kimodoSha256", "ardySha256", "motionBricksSha256", "physicsSha256"},
        )
        normalized["lineage"] = {
            field: _hex_digest(lineage[field], f"lineage.{field}")
            for field in ("kimodoSha256", "ardySha256", "motionBricksSha256", "physicsSha256")
        }
    return normalized


def _motion_lab_source(root: Path, relative: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _allowlisted_repo_file(root, relative)
    if not path.is_file():
        raise ValueError("Motion Lab payload is not a regular file")
    before = path.stat()
    if before.st_size > MAX_REQUEST_BYTES:
        raise ValueError(f"Motion Lab payload exceeds {MAX_REQUEST_BYTES} byte limit")
    payload = path.read_bytes()
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise StaleArtifactError("Motion Lab payload changed while it was being read")
    try:
        document = validate_motion_lab(_strict_json_loads(payload))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Motion Lab payload is invalid: {exc}") from exc
    return document, {"path": relative, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}


def load_motion_lab(root: Path, relative: str) -> dict[str, Any]:
    """Load only a regular, canonical repository payload; no provider fallback exists."""
    return _motion_lab_source(root, relative)[0]


class MotionLabStore:
    """Append-only Motion Lab annotations; deliberately separate from ReviewRun admission."""

    def __init__(self, root: Path, relative: str):
        self.root = root.resolve()
        self.relative = relative
        document, _ = _motion_lab_source(self.root, relative)
        self.directory = self.root / "qa_runs" / "asset_reviews" / "motion_lab" / document["motionLabId"]
        self._lock = threading.RLock()

    def _source(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return _motion_lab_source(self.root, self.relative)

    def _event_paths(self) -> list[Path]:
        if not self.directory.is_dir():
            return []
        return sorted(self.directory.glob("events/*.json"))

    def _events(self, source: dict[str, Any], document: dict[str, Any]) -> list[dict[str, Any]]:
        events = []
        previous = None
        for expected_sequence, path in enumerate(self._event_paths(), start=1):
            try:
                event = _strict_json_loads(path.read_bytes())
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                raise RuntimeError("Motion Lab event receipt is unreadable") from exc
            content = dict(event) if isinstance(event, dict) else None
            claimed = content.pop("eventSha256", None) if content is not None else None
            if (
                not isinstance(event, dict)
                or event.get("schema") != "forgelens.motion-lab-event/v1"
                or event.get("sequence") != expected_sequence
                or event.get("previousEventSha256") != previous
                or event.get("motionLabId") != document["motionLabId"]
                or event.get("revision") != document["revision"]
                or event.get("sourceSha256") != source["sha256"]
                or not isinstance(claimed, str)
                or hashlib.sha256(_canonical_json_bytes(content)).hexdigest() != claimed
            ):
                raise RuntimeError("Motion Lab event chain is invalid or stale")
            previous = claimed
            events.append(event)
        return events

    def load(self) -> dict[str, Any]:
        with self._lock:
            document, source = self._source()
            events = self._events(source, document)
            return {"schema": "forgelens.motion-lab-snapshot/v1", "motionLab": document, "source": source, "events": events, "admissionAuthority": "none-motion-lab-events-never-transition-reviewrun"}

    def append_annotation(self, request: Any, *, actor_id: str) -> dict[str, Any]:
        request = _exact_object_fields(request, "motion lab annotation", {"motionLabId", "sourceSha256", "reviewerKind", "text", "revision", "frame", "jointId", "objectId", "worldPoint"})
        with self._lock:
            document, source = self._source()
            if request["motionLabId"] != document["motionLabId"] or request["revision"] != document["revision"]:
                raise StaleArtifactError("Motion Lab identity changed; reload before annotating")
            if request["sourceSha256"] != source["sha256"]:
                raise StaleArtifactError("Motion Lab payload bytes changed; reload before annotating")
            reviewer_kind = _bounded_string(request["reviewerKind"], "reviewerKind", {"human", "api", "inkling"})
            events = self._events(source, document)
            content = {
                "schema": "forgelens.motion-lab-event/v1",
                "eventType": "annotation",
                "sequence": len(events) + 1,
                "previousEventSha256": None if not events else events[-1]["eventSha256"],
                "motionLabId": document["motionLabId"],
                "revision": document["revision"],
                "sourceSha256": source["sha256"],
                "reviewerKind": reviewer_kind,
                "actorId": _bounded_string(actor_id, "actorId", maximum=200),
                "recordedAt": utc_now(),
                "text": _bounded_string(request["text"], "text", maximum=MAX_COMMENT_CHARS),
                "frame": _motion_lab_frame(request["frame"], "frame", document["frameCount"]),
                "jointId": _motion_lab_id(request["jointId"], "jointId"),
                "objectId": _motion_lab_id(request["objectId"], "objectId"),
                "worldPoint": _motion_lab_vector(request["worldPoint"], "worldPoint"),
            }
            digest = hashlib.sha256(_canonical_json_bytes(content)).hexdigest()
            event = {**content, "eventSha256": digest}
            _write_immutable(self.directory / "events" / f"{content['sequence']:06d}-{digest}.json", _canonical_json_bytes(event) + b"\n")
            return event

    def import_human_event(self, relative: str) -> dict[str, Any]:
        """Import an external human outcome; it is never a ReviewRun/pass transition."""
        path = _allowlisted_repo_file(self.root, relative)
        if not path.is_file() or path.stat().st_size > MAX_REQUEST_BYTES:
            raise ValueError("Motion Lab human event is not a bounded regular file")
        raw = path.read_bytes()
        try:
            request = _strict_json_loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("Motion Lab human event is invalid JSON") from exc
        request = _exact_object_fields(
            request,
            "motion lab human event",
            {"schema", "motionLabId", "revision", "sourceSha256", "reviewerPseudonym", "action", "comment", "decidedAt", "attestation"},
        )
        if request["schema"] != "forgelens.motion-lab-human-event/v1":
            raise ValueError("motion lab human event schema is invalid")
        reviewer = _bounded_string(request["reviewerPseudonym"], "reviewerPseudonym", maximum=200)
        if re.search(r"(?:api|inkling|agent|automation|hermes)", reviewer, re.IGNORECASE):
            raise ValueError("API, Inkling, and automation identities cannot import human outcomes")
        action = _bounded_string(request["action"], "action", MOTION_LAB_ACTIONS)
        attestation = _bounded_string(request["attestation"], "attestation", maximum=500)
        if attestation != "I independently reviewed this exact Motion Lab payload; this outcome does not approve a ReviewRun.":
            raise ValueError("motion lab human event attestation is invalid")
        decided_at = _bounded_string(request["decidedAt"], "decidedAt", maximum=80)
        _parse_attestation_time(decided_at, "decidedAt")
        with self._lock:
            document, source = self._source()
            if request["motionLabId"] != document["motionLabId"] or request["revision"] != document["revision"]:
                raise StaleArtifactError("Motion Lab identity changed; do not import this outcome")
            if request["sourceSha256"] != source["sha256"]:
                raise StaleArtifactError("Motion Lab payload bytes changed; do not import this outcome")
            events = self._events(source, document)
            content = {
                "schema": "forgelens.motion-lab-event/v1",
                "eventType": "human-outcome",
                "sequence": len(events) + 1,
                "previousEventSha256": None if not events else events[-1]["eventSha256"],
                "motionLabId": document["motionLabId"],
                "revision": document["revision"],
                "sourceSha256": source["sha256"],
                "reviewerKind": "external-human",
                "reviewerPseudonym": reviewer,
                "action": action,
                "comment": _bounded_string(request["comment"], "comment", maximum=MAX_COMMENT_CHARS),
                "decidedAt": decided_at,
                "recordedAt": utc_now(),
                "externalEventPath": relative,
                "externalEventSha256": hashlib.sha256(raw).hexdigest(),
                "admissionAuthority": "none-motion-lab-outcome-never-transitions-reviewrun",
            }
            digest = hashlib.sha256(_canonical_json_bytes(content)).hexdigest()
            event = {**content, "eventSha256": digest}
            _write_immutable(self.directory / "events" / f"{content['sequence']:06d}-{digest}.json", _canonical_json_bytes(event) + b"\n")
            return event

@dataclass(frozen=True)
class ServerContext:
    root: Path
    initial_asset: str | None
    catalog: dict[str, Any]
    reviews: ReviewStore
    authority: BrowserAuthority
    replay_config: ReplayRunConfig | None = None
    review_runs: ReviewRunStore | None = None
    file_identities: dict[str, tuple[dict[str, Any], ...]] | None = None
    active_review_run_id: str | None = None
    motion_lab: MotionLabStore | None = None


class AssetReviewHandler(BaseHTTPRequestHandler):
    server_version = "JustDodgeAssetReview/2"
    context: ServerContext

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(REQUEST_IO_TIMEOUT_SECONDS)

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
            if route == "/api/motion-lab":
                self._require_authority(mutation=False)
                if parsed.query:
                    raise ValueError("motion lab endpoint does not accept query parameters")
                if self.context.motion_lab is None:
                    self._error(HTTPStatus.NOT_FOUND, "Motion Lab is disabled; launch with --motion-lab <repository-relative-json>")
                else:
                    self._send_json(self.context.motion_lab.load())
                return
            if route == "/api/active-review-run":
                self._require_authority(mutation=False)
                if parsed.query:
                    raise ValueError("active ReviewRun endpoint does not accept query parameters")
                if self.context.active_review_run_id is None:
                    self._send_json(None)
                elif self.context.review_runs is None:
                    raise ValueError("active ReviewRun has no configured store")
                else:
                    self._send_json(
                        self.context.review_runs.load(self.context.active_review_run_id)
                    )
                return
            if route == "/api/review-run":
                self._require_authority(mutation=False)
                if self.context.review_runs is None:
                    raise ValueError("ReviewRun store is not configured")
                if set(query) != {"runId"} or len(query["runId"]) != 1:
                    raise ValueError("review-run lookup requires exactly one runId query parameter")
                self._send_json(self.context.review_runs.load(query["runId"][0]))
                return
            if route == "/api/review":
                self._require_authority(mutation=False)
                asset = query.get("asset", [""])[0]
                asset = urllib.parse.unquote(asset)
                safe_repo_path(self.context.root, asset)
                self._send_json(self.context.reviews.load(asset))
                return
            if route == "/api/mesh-doctor":
                self._require_authority(mutation=False)
                asset = query.get("asset", [""])[0]
                asset = urllib.parse.unquote(asset)
                safe_repo_path(self.context.root, asset)
                self._send_json(_mesh_doctor_report(self.context.root, asset))
                return
            if route.startswith("/file/"):
                self._require_authority(mutation=False)
                relative = urllib.parse.unquote(route[len("/file/") :])
                identities = list((self.context.file_identities or {}).get(relative, ()))
                if self.context.review_runs is not None:
                    identities.extend(self.context.review_runs.allowed_file_identities(relative))
                if not identities:
                    self._error(HTTPStatus.FORBIDDEN, "file is not bound by the immutable catalog or a ReviewRun")
                    return
                expected = {(identity["sha256"], identity["bytes"]) for identity in identities}
                if len(expected) != 1:
                    self._error(
                        HTTPStatus.CONFLICT,
                        "file path is bound to conflicting immutable identities; use a content-addressed artifact",
                    )
                    return
                path = _allowlisted_repo_file(self.context.root, relative)
                if not path.is_file():
                    self._error(HTTPStatus.NOT_FOUND, "file not found")
                    return
                payload = path.read_bytes()
                digest = hashlib.sha256(payload).hexdigest()
                expected_sha256, expected_bytes = next(iter(expected))
                if digest != expected_sha256 or len(payload) != expected_bytes:
                    self._error(
                        HTTPStatus.CONFLICT,
                        "file bytes no longer match the immutable catalog/ReviewRun identity",
                    )
                    return
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self._send_bytes(
                    payload,
                    content_type,
                    extra_headers=(("X-ForgeLens-SHA256", digest),),
                )
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
        except RuntimeError as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"integrity validation failed: {exc}")
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
            "/api/review-run",
            "/api/review-run-transition",
            "/api/review-pin",
            "/api/viewer-context",
            "/api/review-run-export",
            "/api/motion-lab-annotation",
        }:
            self._error(HTTPStatus.NOT_FOUND, "route not found")
            return
        try:
            authority = self._require_authority(mutation=True)
            if self.headers.get("Transfer-Encoding") is not None:
                raise ValueError("Transfer-Encoding is not accepted; bounded Content-Length is required")
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Content-Type must be application/json")
                return
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise ValueError("Content-Length is required")
            if not re.fullmatch(r"[0-9]+", raw_length):
                raise ValueError("Content-Length must be an unsigned decimal integer")
            length = int(raw_length, 10)
            request_limit = (
                MAX_EVIDENCE_BYTES * 2
                if route in {"/api/neural-evidence", "/api/viewer-context"}
                else MAX_REQUEST_BYTES
            )
            if length > request_limit:
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"request exceeds {request_limit} byte limit")
                return
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("truncated request body")
            payload = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_json_object_without_duplicates,
                parse_constant=_reject_non_finite_json_constant,
            )
            response_status = HTTPStatus.OK
            if route == "/api/review-run":
                if self.context.review_runs is None:
                    raise ValueError("ReviewRun store is not configured")
                result = self.context.review_runs.create(build_review_run(self.context.root, payload))
                response_status = HTTPStatus.CREATED
            elif route == "/api/motion-lab-annotation":
                if self.context.motion_lab is None:
                    raise ValueError("Motion Lab is disabled; annotations require --motion-lab")
                result = self.context.motion_lab.append_annotation(payload, actor_id=authority["actorId"])
                response_status = HTTPStatus.CREATED
            elif route == "/api/review-pin":
                if self.context.review_runs is None:
                    raise ValueError("review-pin API requires a configured store and object payload")
                payload = _exact_object_fields(payload, "review-pin request", {"runId", "pin"})
                result = self.context.review_runs.save_pin(
                    _required_field(payload, "runId"),
                    _required_field(payload, "pin"),
                )
            elif route == "/api/viewer-context":
                if self.context.review_runs is None:
                    raise ValueError("viewer-context API requires a configured ReviewRun store")
                payload = _exact_object_fields(
                    payload,
                    "viewer-context request",
                    {"runId", "event", "expectedPreviousSha256"},
                    {"capturePngBase64"},
                )
                result = self.context.review_runs.record_viewer_event(
                    _required_field(payload, "runId"),
                    _required_field(payload, "event"),
                    expected_previous_sha256=_required_field(
                        payload, "expectedPreviousSha256"
                    ),
                    actor_id=authority["actorId"],
                    capture_png_base64=payload.get("capturePngBase64"),
                )
            elif route == "/api/review-run-export":
                if self.context.review_runs is None:
                    raise ValueError("review-run export requires a configured store and object payload")
                payload = _exact_object_fields(payload, "review-run export request", {"runId"})
                result = self.context.review_runs.export_admission_packet(
                    _required_field(payload, "runId")
                )
            elif route == "/api/review-run-transition":
                if self.context.review_runs is None:
                    raise ValueError("review-run transition requires a configured store and object payload")
                payload = _exact_object_fields(
                    payload,
                    "review-run transition request",
                    {"runId", "targetState", "expectedPreviousSha256", "details"},
                    {"targetAov"},
                )
                run_id = _required_field(payload, "runId")
                snapshot = self.context.review_runs.load(run_id)
                run = validate_review_run(
                    {**snapshot["reviewRun"], "decisionChainHeadSha256": None}
                )
                pin_statuses = None
                if snapshot["pins"] and payload.get("targetState") == "submitted":
                    pin_statuses = [
                        review_pin_status(
                            pin,
                            run,
                            derive_review_pin_context(
                                self.context.root,
                                run,
                                pin,
                                target_aov=payload.get("targetAov"),
                            ),
                        )
                        for pin in snapshot["pins"]
                    ]
                result = self.context.review_runs.transition(
                    run_id,
                    _required_field(payload, "targetState"),
                    expected_previous_sha256=_required_field(payload, "expectedPreviousSha256"),
                    actor_id=authority["actorId"],
                    details=_required_field(payload, "details"),
                    pin_statuses=pin_statuses,
                )
            elif route == "/api/review":
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
            self._send_json(result, response_status)
        except AuthorityError as exc:
            self._error(exc.status, str(exc))
        except StaleArtifactError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except TransitionError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except RuntimeError as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"integrity validation failed: {exc}")
        except (ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
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
        default="target/release/m3_match",
        help="repository-relative m3_match verifier executable",
    )
    parser.add_argument(
        "--capture",
        action="append",
        default=[],
        help="repository-relative visual capture bound to the replay ReviewRun (repeatable)",
    )
    parser.add_argument(
        "--review-run-declaration",
        help="repository-relative forgelens.review-run-declaration/v1 JSON to create and display",
    )
    parser.add_argument(
        "--import-human-decision",
        nargs=2,
        metavar=("RUN_ID", "REPOSITORY_RELATIVE_JSON"),
        help="import a tracked-clean external human decision; this path is intentionally unavailable over HTTP",
    )
    parser.add_argument(
        "--motion-lab",
        help="repository-relative forgelens.motion-lab/v1 JSON; omitted means /api/motion-lab fails closed",
    )
    parser.add_argument(
        "--import-motion-lab-human-event",
        metavar="REPOSITORY_RELATIVE_JSON",
        help="import an external human Motion Lab outcome; unavailable over HTTP and never a ReviewRun transition",
    )
    return parser.parse_args()


def _contract_replay_verifier_allowlist() -> tuple[tuple[str, str], ...]:
    try:
        contract = json.loads(
            REVIEW_SPINE_CONTRACT.read_text(encoding="utf-8"),
            object_pairs_hook=_json_object_without_duplicates,
            parse_constant=_reject_non_finite_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("ForgeLens review-spine contract is unreadable") from exc
    spine = contract.get("review_spine_contract") if isinstance(contract, dict) else None
    entries = spine.get("replay_verifier_allowlist") if isinstance(spine, dict) else None
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("ForgeLens review-spine contract has no verifier allowlist")
    result = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise RuntimeError(f"verifier allowlist entry {index} is invalid")
        path = _bounded_string(entry.get("path"), f"verifierAllowlist[{index}].path", maximum=1_000)
        digest = _hex_digest(entry.get("sha256"), f"verifierAllowlist[{index}].sha256")
        result.append((path, digest))
    if len(set(result)) != len(result):
        raise RuntimeError("ForgeLens verifier allowlist contains duplicate entries")
    return tuple(result)


def _load_review_run_declaration(root: Path, relative: str) -> Any:
    path = _allowlisted_repo_file(root, relative)
    if not path.is_file():
        raise ValueError("ReviewRun declaration is not a regular file")
    if path.stat().st_size > MAX_REQUEST_BYTES:
        raise ValueError(f"ReviewRun declaration exceeds {MAX_REQUEST_BYTES} byte limit")
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_json_object_without_duplicates,
        parse_constant=_reject_non_finite_json_constant,
    )


def main() -> int:
    args = parse_args()
    if args.review_run_declaration and args.import_human_decision:
        raise SystemExit(
            "--review-run-declaration and --import-human-decision are mutually exclusive"
        )
    if args.import_motion_lab_human_event and not args.motion_lab:
        raise SystemExit("--import-motion-lab-human-event requires --motion-lab")
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
            verifier_allowlist=_contract_replay_verifier_allowlist(),
        )
        build_replay_review_run(root, replay_config)
    bootstrap_token = secrets.token_urlsafe(32)
    catalog = build_catalog(root)
    review_runs = ReviewRunStore(root)
    motion_lab = MotionLabStore(root, args.motion_lab) if args.motion_lab else None
    instance_lock = StoreInstanceLock(root)
    instance_lock.acquire()
    server = None
    try:
        active_review_run_id = None
        if args.import_human_decision:
            import_run_id, import_path = args.import_human_decision
            receipt = review_runs.import_external_human_decision(import_run_id, import_path)
            active_review_run_id = import_run_id
            print(
                f"FORGELENS_EXTERNAL_HUMAN_DECISION_IMPORTED={import_run_id} RECEIPT={receipt['receiptSha256']}",
                flush=True,
            )
        if args.review_run_declaration:
            declaration = _load_review_run_declaration(root, args.review_run_declaration)
            active_review_run_id = review_runs.create(
                build_review_run(root, declaration)
            )["runId"]
        if args.import_motion_lab_human_event:
            assert motion_lab is not None
            motion_event = motion_lab.import_human_event(args.import_motion_lab_human_event)
            print(
                f"FORGELENS_MOTION_LAB_HUMAN_EVENT_IMPORTED={motion_event['motionLabId']} RECEIPT={motion_event['eventSha256']}",
                flush=True,
            )
        context = ServerContext(
            root=root,
            initial_asset=initial_asset,
            catalog=catalog,
            reviews=ReviewStore(root),
            authority=BrowserAuthority(bootstrap_token),
            replay_config=replay_config,
            review_runs=review_runs,
            file_identities=_startup_file_identities(root, catalog, replay_config),
            active_review_run_id=active_review_run_id,
            motion_lab=motion_lab,
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
        if active_review_run_id:
            print(f"FORGELENS_ACTIVE_REVIEW_RUN={active_review_run_id}", flush=True)
        if motion_lab is not None:
            snapshot = motion_lab.load()
            print(
                f"FORGELENS_MOTION_LAB={snapshot['motionLab']['motionLabId']} SOURCE_SHA256={snapshot['source']['sha256']}",
                flush=True,
            )
        if not args.no_open:
            bootstrap_url = (
                f"http://{host}:{port}/auth/bootstrap?token="
                + urllib.parse.quote(bootstrap_token, safe="")
            )
            threading.Timer(0.3, lambda: webbrowser.open(bootstrap_url)).start()
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.server_close()
        instance_lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
