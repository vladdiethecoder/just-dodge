#!/usr/bin/env python3
"""Index exact selected BONES-SEED motion ids inside the compressed G1 archive.

The index does not extract or redistribute raw motion. It is an internal,
ignored provenance artifact consumed by ``audit_bones_seed.py --g1-member-index``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index selected motion ids in BONES-SEED g1.tar.gz without extraction."
    )
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument(
        "--audit",
        type=Path,
        help="Selection audit; defaults to <dataset-root>/just_dodge_combat_audit.json.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Index destination; defaults to <dataset-root>/just_dodge_g1_member_index.json.",
    )
    args = parser.parse_args()

    root = args.dataset_root.resolve()
    audit_path = (
        args.audit.resolve()
        if args.audit
        else root / "just_dodge_combat_audit.json"
    )
    archive_path = root / "g1.tar.gz"
    if not audit_path.is_file():
        parser.error(f"missing selection audit: {audit_path}")
    if not archive_path.is_file():
        parser.error(f"missing G1 archive: {archive_path}")

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    motion_ids = {row["motion_id"] for row in audit["selected"] if row.get("motion_id")}
    members_by_motion_id: dict[str, list[str]] = {}
    with tarfile.open(archive_path, "r|gz") as archive:
        for member in archive:
            if not member.isfile():
                continue
            motion_id = Path(member.name).stem
            if motion_id in motion_ids:
                members_by_motion_id.setdefault(motion_id, []).append(member.name)

    missing_motion_ids = sorted(motion_ids - members_by_motion_id.keys())
    index = {
        "schema_version": 1,
        "source_audit": str(audit_path),
        "source_audit_sha256": sha256_file(audit_path),
        "g1_archive": str(archive_path),
        "g1_archive_sha256": sha256_file(archive_path),
        "selected_count": len(motion_ids),
        "indexed_motion_count": len(members_by_motion_id),
        "missing_motion_count": len(missing_motion_ids),
        "members_by_motion_id": {
            motion_id: members_by_motion_id[motion_id]
            for motion_id in sorted(members_by_motion_id)
        },
        "missing_motion_ids": missing_motion_ids,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "raw_data_extracted": False,
    }
    out_path = args.out.resolve() if args.out else root / "just_dodge_g1_member_index.json"
    out_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "index": str(out_path),
                "selected_count": len(motion_ids),
                "indexed_motion_count": len(members_by_motion_id),
                "missing_motion_count": len(missing_motion_ids),
                "raw_data_extracted": False,
            },
            indent=2,
        )
    )
    if missing_motion_ids:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
