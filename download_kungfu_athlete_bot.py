#!/usr/bin/env python3
"""Download an exact public Hugging Face dataset revision with source metadata."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

REPO_ID = "LuluCao/KungfuAthleteBot"
REPO_TYPE = "dataset"
REVISION = "ff09f3795dc99bef73b21413b03fa8470917a22c"
DESTINATION = Path("/run/media/vdubrov/Bulk-SSD/combat_mocap_sources/kungfu_athlete_bot")


def main() -> None:
    destination = DESTINATION.resolve()
    provenance_dir = destination / "PROVENANCE"
    provenance_dir.mkdir(parents=True, exist_ok=True)

    api = HfApi(token=False)
    info = api.dataset_info(REPO_ID, revision=REVISION, files_metadata=True, token=False)
    metadata = {
        "source": {
            "repo_url": f"https://huggingface.co/datasets/{REPO_ID}",
            "repo_id": REPO_ID,
            "repo_type": REPO_TYPE,
            "requested_revision": REVISION,
            "resolved_revision": info.sha,
            "license": getattr(info.card_data, "license", None),
            "private": info.private,
            "gated": info.gated,
            "captured_utc": datetime.now(timezone.utc).isoformat(),
        },
        "remote_files": [
            {
                "path": file.rfilename,
                "size_bytes": file.size,
                "blob_id": file.blob_id,
                "lfs": (
                    {
                        "size_bytes": file.lfs.size,
                        "sha256": file.lfs.sha256,
                        "pointer_size_bytes": file.lfs.pointer_size,
                    }
                    if file.lfs
                    else None
                ),
            }
            for file in (info.siblings or [])
        ],
    }
    (provenance_dir / "upstream_hf_file_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    remote_bytes = sum(item["size_bytes"] or 0 for item in metadata["remote_files"])
    print(f"Repo: {REPO_ID}")
    print(f"Revision: {info.sha}")
    print(f"Remote file count: {len(metadata['remote_files'])}")
    print(f"Remote bytes: {remote_bytes}")
    print(f"Destination: {destination}")
    print("Starting snapshot download...")
    result = snapshot_download(
        repo_id=REPO_ID,
        repo_type=REPO_TYPE,
        revision=REVISION,
        local_dir=destination,
        token=False,
        max_workers=8,
    )
    print(f"Snapshot download complete: {result}")


if __name__ == "__main__":
    main()
