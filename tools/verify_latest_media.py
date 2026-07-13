#!/usr/bin/env python3
"""Fail closed when canonical Milestone 3 review media is stale, incomplete, or tampered."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs" / "media" / "latest"
REQUIRED = ("rendering-overview.png", "gameplay-demo.mp4", "manifest.json", "README.md")
PRESENTATION_PATHS = ("src/main.rs", "src/ui.rs", "src/renderer.rs", "src/milestone3.rs", "assets")


def fail(message: str) -> NoReturn:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(
        ("git", *args), cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if result.returncode:
        fail(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def main() -> None:
    missing = [name for name in REQUIRED if not (MEDIA / name).is_file()]
    if missing:
        fail(f"missing canonical media: {', '.join(missing)}")

    try:
        manifest = json.loads((MEDIA / "manifest.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"invalid manifest JSON: {error}")

    required_manifest = {
        "capture_utc",
        "source_commit",
        "build_sha256",
        "media_sha256",
        "resolution",
        "frame_rate",
        "capture_command",
        "packaged_build",
        "truth_hash",
        "demonstrated_features",
        "known_defects",
        "owner_accepted",
    }
    missing_keys = sorted(required_manifest - manifest.keys())
    if missing_keys:
        fail(f"manifest missing keys: {', '.join(missing_keys)}")
    if not isinstance(manifest["media_sha256"], dict):
        fail("manifest media_sha256 must be an object")
    if not isinstance(manifest["owner_accepted"], bool):
        fail("manifest owner_accepted must be boolean")
    try:
        capture_time = datetime.fromisoformat(manifest["capture_utc"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        fail(f"capture_utc must be ISO-8601 UTC: {error}")
    if capture_time.tzinfo is None:
        fail("capture_utc must include a timezone")

    git("cat-file", "-e", f"{manifest['source_commit']}^{{commit}}")
    changed = git("diff", "--name-only", f"{manifest['source_commit']}..HEAD", "--", *PRESENTATION_PATHS)
    if changed:
        fail("capture predates presentation-relevant commits: " + ", ".join(changed.splitlines()))

    for name in ("rendering-overview.png", "gameplay-demo.mp4"):
        expected = manifest["media_sha256"].get(name)
        if not isinstance(expected, str):
            fail(f"manifest lacks SHA-256 for {name}")
        actual = sha256(MEDIA / name)
        if actual != expected:
            fail(f"SHA-256 mismatch for {name}: expected {expected}, got {actual}")

    print("PASS: canonical review media is complete, source-current, and hash-verified")


if __name__ == "__main__":
    main()
