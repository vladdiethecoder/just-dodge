#!/usr/bin/env python3
"""Build deterministic, interaction-family-disjoint train/validation/test splits.

The input is the offline interaction corpus, not a runtime clip library. A split
unit is one ``move_id × opponent-height`` family (nine side/timing variants), so
all views of a held-out attack-height geometry remain in exactly one partition.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Load the offline interaction contract by file path so CI (which has no
# torch) can run the partition leakage test without triggering the package
# __init__ import chain (motionbricks_service/__init__ -> generate -> torch).
import importlib.util  # noqa: E402

_IF_PATH = ROOT / "motionbricks_service" / "interaction_forward.py"
_IF_SPEC = importlib.util.spec_from_file_location("interaction_forward_offline", _IF_PATH)
assert _IF_SPEC is not None and _IF_SPEC.loader is not None
interaction_forward = importlib.util.module_from_spec(_IF_SPEC)
sys.modules["interaction_forward_offline"] = interaction_forward
_IF_SPEC.loader.exec_module(interaction_forward)
canonical_json = interaction_forward.canonical_json
sha256_json = interaction_forward.sha256_json
strict_json_load = interaction_forward.strict_json_load

SPLITS = ("train", "validation", "test")
SCHEMA = "just-dodge.motionbricks.interaction-partitions/v1"


def _corpus_digest(corpus: dict[str, Any]) -> str:
    unsealed = dict(corpus)
    supplied = unsealed.pop("manifest_sha256", None)
    if not isinstance(supplied, str) or supplied != sha256_json(unsealed):
        raise ValueError("input corpus manifest_sha256 does not bind canonical corpus bytes")
    return supplied


def _height_family(example: dict[str, Any]) -> str:
    variant = example.get("variant_id")
    move_id = example.get("move_id")
    if not isinstance(variant, str) or not isinstance(move_id, str):
        raise ValueError("examples require string move_id and variant_id")
    height = variant.split("_", 1)[0]
    if height not in {"high", "mid", "low"}:
        raise ValueError(f"unsupported interaction height family: {variant}")
    return f"{move_id}:{height}"


def build_partitions(corpus: dict[str, Any]) -> dict[str, Any]:
    corpus_sha256 = _corpus_digest(corpus)
    examples = corpus.get("examples")
    if not isinstance(examples, list) or not examples:
        raise ValueError("input corpus must contain non-empty examples")

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for example in examples:
        if not isinstance(example, dict):
            raise ValueError("corpus example must be an object")
        claimed = example.get("example_sha256")
        unsealed = dict(example)
        unsealed.pop("example_sha256", None)
        if not isinstance(claimed, str) or claimed != sha256_json(unsealed):
            raise ValueError("example_sha256 does not bind canonical example")
        groups[_height_family(example)].append(example)

    by_move: dict[str, list[str]] = defaultdict(list)
    for group in groups:
        move_id, _height = group.rsplit(":", 1)
        by_move[move_id].append(group)
    assignments: dict[str, str] = {}
    for move_id, move_groups in sorted(by_move.items()):
        if len(move_groups) != len(SPLITS):
            raise ValueError(f"{move_id} must expose exactly one high/mid/low interaction family")
        # Stable ranking avoids source-order dependence while guaranteeing every
        # action/move has examples in every partition.
        ranked = sorted(
            move_groups,
            key=lambda group: hashlib.sha256(group.encode("utf-8")).hexdigest(),
        )
        assignments.update(dict(zip(ranked, SPLITS, strict=True)))

    rows: list[dict[str, str]] = []
    seen_examples: set[str] = set()
    for group in sorted(groups):
        split = assignments[group]
        for example in sorted(groups[group], key=lambda item: item["example_sha256"]):
            example_sha256 = example["example_sha256"]
            if example_sha256 in seen_examples:
                raise ValueError("duplicate interaction example hash")
            seen_examples.add(example_sha256)
            rows.append(
                {
                    "example_sha256": example_sha256,
                    "move_id": example["move_id"],
                    "actor_intent": example["actor_intent"],
                    "partition_group": group,
                    "split": split,
                }
            )
    rows.sort(key=lambda row: (row["split"], row["partition_group"], row["example_sha256"]))

    by_split = {split: [row for row in rows if row["split"] == split] for split in SPLITS}
    if any(not by_split[split] for split in SPLITS):
        raise ValueError("all train/validation/test partitions must be non-empty")
    for move_id, move_groups in by_move.items():
        observed = {assignments[group] for group in move_groups}
        if observed != set(SPLITS):
            raise ValueError(f"{move_id} does not cover every partition")
    for split_a in SPLITS:
        groups_a = {row["partition_group"] for row in by_split[split_a]}
        for split_b in SPLITS:
            if split_a < split_b and groups_a & {row["partition_group"] for row in by_split[split_b]}:
                raise ValueError("interaction family leakage across partitions")

    manifest = {
        "schema": SCHEMA,
        "input_corpus_sha256": corpus_sha256,
        "partition_policy": "move_id × opponent-height family; no family may appear in more than one split",
        "splits": {
            split: {
                "count": len(by_split[split]),
                "example_sha256": [row["example_sha256"] for row in by_split[split]],
                "partition_groups": sorted({row["partition_group"] for row in by_split[split]}),
            }
            for split in SPLITS
        },
        "assignments": rows,
    }
    manifest["manifest_sha256"] = sha256_json(manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = build_partitions(strict_json_load(args.corpus.read_text("utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(manifest) + b"\n")
    counts = ",".join(f"{split}={manifest['splits'][split]['count']}" for split in SPLITS)
    print(f"MOTIONBRICKS_INTERACTION_PARTITIONS=PASS {counts} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
