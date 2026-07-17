#!/usr/bin/env python3
"""MEDIA-TO-CONSTRAINT-COMPILER-V1 (offline only).

Converts an admitted media-corpus intake record plus derived semantic anchors
into a canonical constraint packet. The output schema deliberately has no
room for raw frame arrays, contact outcomes, injuries, or hit results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "motion-constraint-packet.v1"
FORBIDDEN_KEYS = {
    "frames",
    "frame_arrays",
    "f413",
    "npz",
    "bvh",
    "fbx",
    "hit",
    "hits",
    "injury",
    "injuries",
    "damage",
    "outcome",
    "results",
    "kill",
}
REQUIRED_CORPUS_FIELDS = {"schema_version", "record_id", "source", "labels", "admission"}


def fail(message: str) -> None:
    print(f"MEDIA_TO_CONSTRAINT_ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def reject_forbidden(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in FORBIDDEN_KEYS:
                fail(f"forbidden key {path}.{key}")
            reject_forbidden(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_forbidden(child, f"{path}[{index}]")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read {path}: {error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--anchors", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    corpus = load_json(args.corpus)
    anchors = load_json(args.anchors)
    if not isinstance(corpus, dict) or not REQUIRED_CORPUS_FIELDS.issubset(corpus):
        fail("corpus record missing required media-corpus-abi.v1 fields")
    if corpus.get("schema_version") != "media-corpus-abi.v1":
        fail("corpus schema_version must be media-corpus-abi.v1")
    admission = corpus.get("admission", {})
    if admission.get("runtime_allowed") is not False:
        fail("corpus runtime_allowed must be false")
    if not admission.get("training_allowed", False):
        fail("corpus training_allowed must be true for constraint compilation")
    reject_forbidden(corpus)
    reject_forbidden(anchors)

    corpus_bytes = canonical_json(corpus)
    anchor_bytes = canonical_json(anchors)
    compiler_identity = f"{Path(__file__).name}@media-to-constraint-compiler.v1"
    packet = {
        "schema_version": SCHEMA_VERSION,
        "record_id": corpus["record_id"],
        "source_sha256": sha256_bytes(corpus_bytes),
        "anchor_sha256": sha256_bytes(anchor_bytes),
        "compiler_sha256": sha256_file(Path(__file__).resolve()),
        "compiler": compiler_identity,
        "intent_classes": corpus.get("labels", {}).get("intent_classes", []),
        "constraints": anchors,
        "outcome_authority": "deterministic_physics_only",
        "runtime_playback_allowed": False,
    }
    packet_bytes = canonical_json(packet)
    packet["packet_sha256"] = sha256_bytes(packet_bytes)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(packet) + b"\n")
    print(f"MEDIA_TO_CONSTRAINT_PACKET=PASS output={args.output} packet_sha256={packet['packet_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
