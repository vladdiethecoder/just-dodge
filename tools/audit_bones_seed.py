#!/usr/bin/env python3
"""Create an internal, provenance-locked BONES-SEED selection audit.

The dataset is gated and must remain outside the repository. This tool neither
logs in nor downloads data; it reads an already-authorized local checkout and
writes a minimal audit manifest beside that checkout.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_TERMS = (
    "martial",
    "combat",
    "fight",
    "fencing",
    "sword",
    "weapon",
    "boxing",
    "punch",
    "kick",
    "strike",
    "parry",
    "guard",
    "grapple",
    "wrestling",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_text(row: dict[str, str]) -> str:
    return " ".join(value for value in row.values() if value).lower()


MOTION_PATH_KEYS = (
    "g1_file",
    "soma_file",
    "contact_points_file",
    "temporal_labels_file",
    "source_file",
    "raw_file",
)
G1_ARCHIVE_FALLBACK = "g1.tar.gz"


def source_paths(row: dict[str, str]) -> list[str]:
    metadata_paths = [row[key] for key in MOTION_PATH_KEYS if row.get(key)]
    # v004 omits per-motion file paths. The G1 archive is the immutable source
    # container for MotionBricks-compatible motion; an archive-member index is
    # required before extraction or conversion of an individual motion.
    return metadata_paths or [G1_ARCHIVE_FALLBACK]


def load_rows(metadata_csv: Path) -> list[dict[str, str]]:
    with metadata_csv.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise ValueError(f"metadata has no header: {metadata_csv}")
        return list(reader)


def find_metadata(root: Path) -> Path:
    for name in ("seed_metadata_v004.csv", "seed_metadata_v003.csv"):
        candidate = root / "metadata" / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "missing BONES-SEED metadata CSV; expected metadata/seed_metadata_v004.csv "
        "or metadata/seed_metadata_v003.csv"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit an authorized BONES-SEED checkout without copying raw data."
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        required=True,
        help="Authorized BONES-SEED checkout containing a supported metadata CSV.",
    )
    parser.add_argument(
        "--license-reference",
        required=True,
        help="Opaque internal reference to the approved commercial license; never pass license text.",
    )
    parser.add_argument(
        "--terms",
        nargs="+",
        default=list(DEFAULT_TERMS),
        help="Case-insensitive metadata terms that select combat candidates.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Audit destination; defaults to <dataset-root>/just_dodge_combat_audit.json.",
    )
    parser.add_argument(
        "--g1-member-index",
        type=Path,
        help=(
            "Optional index emitted by the G1 archive scan. When supplied, "
            "only motions with an exact indexed G1 member are admitted."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = args.dataset_root.resolve()
    license_file = root / "LICENSE.md"
    try:
        metadata = find_metadata(root)
    except FileNotFoundError as error:
        parser.error(str(error))
    if not license_file.is_file():
        parser.error(f"missing required dataset license file: {license_file}")
    g1_members_by_motion_id: dict[str, list[str]] | None = None
    g1_member_index_sha256 = None
    if args.g1_member_index:
        index_path = args.g1_member_index.resolve()
        if not index_path.is_file():
            parser.error(f"missing G1 member index: {index_path}")
        member_index = json.loads(index_path.read_text(encoding="utf-8"))
        expected_archive = (root / G1_ARCHIVE_FALLBACK).resolve()
        if Path(member_index.get("g1_archive", "")).resolve() != expected_archive:
            parser.error("G1 member index was generated for a different archive")
        g1_members_by_motion_id = member_index.get("members_by_motion_id", {})
        g1_member_index_sha256 = sha256_file(index_path)

    terms = tuple(term.lower() for term in args.terms)
    rows = load_rows(metadata)
    selected = []
    unavailable = []
    matched_count = 0
    for row in rows:
        text = row_text(row)
        matches = sorted(term for term in terms if term in text)
        if row.get("is_martial_arts", "").lower() in {"1", "true", "yes"}:
            matches.append("is_martial_arts")
        if not matches:
            continue
        matched_count += 1
        motion_id = (
            row.get("uuid")
            or row.get("move_name")
            or row.get("move_uid")
            or row.get("motion_id")
        )
        if not motion_id:
            unavailable.append(
                {
                    "motion_id": None,
                    "reason": "missing_motion_id",
                    "matched_terms": matches,
                }
            )
            continue
        g1_members = (
            g1_members_by_motion_id.get(motion_id, [])
            if g1_members_by_motion_id is not None
            else []
        )
        if g1_members_by_motion_id is not None and not g1_members:
            unavailable.append(
                {
                    "motion_id": motion_id,
                    "reason": "missing_g1_archive_member",
                    "matched_terms": matches,
                }
            )
            continue
        declared_paths = source_paths(row)
        available_paths = [path for path in declared_paths if (root / path).is_file()]
        missing_paths = [path for path in declared_paths if path not in available_paths]
        if not available_paths or missing_paths:
            unavailable.append(
                {
                    "motion_id": motion_id,
                    "declared_source_paths": declared_paths,
                    "missing_source_paths": missing_paths,
                    "matched_terms": matches,
                }
            )
            continue
        selected.append(
            {
                "motion_id": motion_id,
                "declared_source_paths": declared_paths,
                "available_source_paths": available_paths,
                "g1_archive_members": g1_members,
                "matched_terms": matches,
            }
        )

    audit = {
        "schema_version": 5,
        "dataset": "BONES-SEED",
        "dataset_root": str(root),
        "license_reference": args.license_reference,
        "license_file_sha256": sha256_file(license_file),
        "metadata_file_sha256": sha256_file(metadata),
        "g1_member_indexed": g1_members_by_motion_id is not None,
        "g1_member_index_sha256": g1_member_index_sha256,
        "metadata_rows": len(rows),
        "selection_terms": list(terms),
        "matched_count": matched_count,
        "selected_count": len(selected),
        "unavailable_source_count": len(unavailable),
        "selected": selected,
        "unavailable": unavailable,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "raw_data_redistributed": False,
    }

    if args.dry_run:
        print(
            json.dumps(
                {k: audit[k] for k in audit if k not in {"selected", "unavailable"}},
                indent=2,
            )
        )
        return

    out = args.out.resolve() if args.out else root / "just_dodge_combat_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "audit": str(out),
                "metadata_rows": len(rows),
                "selected_count": len(selected),
                "raw_data_redistributed": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
