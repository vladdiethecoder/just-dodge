#!/usr/bin/env python3
"""Fail closed when any source or code bound to the PVP-005 packet drifts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "assets/motion/pvp005_candidates/manifest.json"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify_receipt(receipt: dict[str, object]) -> None:
    path = ROOT / str(receipt["path"])
    if not path.is_file():
        raise SystemExit(f"missing bound file: {path.relative_to(ROOT)}")
    if path.stat().st_size != receipt["bytes"]:
        raise SystemExit(f"size drift: {path.relative_to(ROOT)}")
    actual = digest(path)
    if actual != receipt["sha256"]:
        raise SystemExit(f"SHA-256 drift: {path.relative_to(ROOT)}")


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("schema") != "just-dodge-pvp005-motion-candidate-packet-v1":
        raise SystemExit("unsupported PVP-005 candidate packet schema")
    if manifest.get("status") != "pending_blinded_human_trials":
        raise SystemExit("candidate verifier cannot approve an unexpected status")
    if manifest.get("runtime_promoted") is not False:
        raise SystemExit("unadmitted candidate packet must not be runtime-promoted")

    for action in ("strike", "block", "grab"):
        entry = manifest["actions"].get(action)
        if not entry or len(entry.get("tell_frames", [])) not in (6, 7, 8):
            raise SystemExit(f"invalid {action} reveal window")
        verify_receipt(entry["source"])
        verify_receipt(entry["f413"])
        verify_receipt(entry["c0_reveal"]["front"])
        verify_receipt(entry["c0_reveal"]["side"])

    for entry in manifest["bound_files"].values():
        verify_receipt(entry)
    for component in manifest["provenance"].values():
        for key in ("license", "normalized_model_card"):
            if key in component:
                verify_receipt(component[key])

    print(f"PVP005_CANDIDATE_PACKET_SHA256={digest(MANIFEST)}")
    print("PVP005_CANDIDATE_PACKET=PASS_PENDING_HUMAN_TRIALS")


if __name__ == "__main__":
    main()
