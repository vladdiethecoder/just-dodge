#!/usr/bin/env python3
"""Verify the exact Blender build pinned by the adversarial visual contract."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
THRESHOLDS = ROOT / "docs/quality/ADVERSARIAL_VISUAL_THRESHOLDS.v1.json"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    config = json.loads(THRESHOLDS.read_text())["dcc"]
    executable = shutil.which("blender")
    if executable is None:
        raise SystemExit("pinned Blender is unavailable")
    path = Path(executable).resolve()
    version = subprocess.run([str(path), "--version"], check=True, capture_output=True, text=True).stdout
    if not version.startswith(f"Blender {config['blender_version']}\n"):
        raise SystemExit(f"Blender version drift: {version.splitlines()[0]}")
    expected_build = f"build hash: {config['blender_build_hash']}"
    if expected_build not in version:
        raise SystemExit(f"Blender build drift: expected {expected_build}")
    observed = digest(path)
    if observed != config["linux_x64_executable_sha256"]:
        raise SystemExit(f"Blender executable hash drift: {observed}")
    print(f"BLENDER_PIN={config['blender_version']}+{config['blender_build_hash']}")
    print(f"BLENDER_EXECUTABLE_SHA256={observed}")


if __name__ == "__main__":
    main()
