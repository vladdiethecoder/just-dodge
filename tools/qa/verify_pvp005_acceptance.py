#!/usr/bin/env python3
"""Validate an immutable PVP-005 acceptance packet; absence fails closed."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / "docs/reports/PVP005_ACCEPTANCE_PACKET.json"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("motion", "provenance"), required=True)
    args = parser.parse_args()
    if not PACKET.is_file():
        raise SystemExit(f"PVP-005 is not admitted: missing {PACKET.relative_to(ROOT)}")
    packet = json.loads(PACKET.read_text())
    if packet.get("schema") != "just-dodge-pvp005-acceptance-v1":
        raise SystemExit("unsupported PVP-005 acceptance packet schema")
    if packet.get("verdict") != "pass" or packet.get("playable_proof") is not False:
        raise SystemExit("PVP-005 acceptance verdict is not a fail-closed pass boundary")
    revision = packet["git_commit"]
    subprocess.run(["git", "cat-file", "-e", f"{revision}^{{commit}}"], cwd=ROOT, check=True)
    for receipt in packet["bound_artifacts"]:
        path = ROOT / receipt["path"]
        if not path.is_file() or digest(path) != receipt["sha256"]:
            raise SystemExit(f"PVP-005 bound artifact missing or drifted: {receipt['path']}")
    if args.scope == "motion":
        human = packet["human_readability"]
        if any(value < 20 for value in human["judgments_per_action"].values()):
            raise SystemExit("insufficient blind judgments")
        if any(value < 0.8 for value in human["accuracy_per_action"].values()):
            raise SystemExit("per-action blind accuracy failed")
        if any(value > 0.2 for value in human["pairwise_confusion"].values()):
            raise SystemExit("pairwise blind confusion failed")
    print(f"PVP005_{args.scope.upper()}_GATE=PASS")


if __name__ == "__main__":
    main()
