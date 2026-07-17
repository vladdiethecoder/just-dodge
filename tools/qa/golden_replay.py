#!/usr/bin/env python3
"""Fail-closed verifier for M6 generated golden replay files.

The standard-library-only tool verifies each SHA-256 manifest entry before
trusting/parsing JSON.  `tamper-test` copies the suite, changes one byte, and
asserts that verification rejects it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

FORMAT = "just-dodge-golden-replay-v1"
SCENARIOS = (
    "all_intents",
    "clinch_grab_tech",
    "cancel_combo",
    "juggle",
    "injury_capability_change",
    "incapacitation",
    "out_of_reach_reprompt",
)
REQUIRED_TICK_KEYS = {
    "tick",
    "requested_player",
    "player_locked",
    "opponent_locked",
    "distance_mm",
    "clinched",
    "airborne_ticks",
    "combo_count",
    "events",
    "contact",
    "injury",
    "truth_hash",
}


class VerificationError(RuntimeError):
    """The artifact is invalid or cannot be trusted."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reject(message: str) -> None:
    raise VerificationError(message)


def parse_manifest(root: Path) -> dict[str, str]:
    manifest = root / "MANIFEST.sha256"
    if not manifest.is_file():
        reject(f"missing manifest: {manifest}")
    entries: dict[str, str] = {}
    for line_number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            reject(f"manifest line {line_number}: expected SHA256 and filename")
        digest, filename = fields
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            reject(f"manifest line {line_number}: invalid lowercase SHA-256")
        relative = Path(filename)
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 1:
            reject(f"manifest line {line_number}: unsafe filename {filename!r}")
        if filename in entries:
            reject(f"manifest line {line_number}: duplicate entry {filename!r}")
        entries[filename] = digest
    expected = {f"{scenario}.golden.json" for scenario in SCENARIOS}
    if set(entries) != expected:
        reject(f"manifest entries differ from required suite: {sorted(entries)}")
    return entries


def validate_replay(path: Path, expected_scenario: str) -> str:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        reject(f"{path.name}: invalid JSON: {error}")
    if not isinstance(document, dict):
        reject(f"{path.name}: root must be an object")
    if document.get("format") != FORMAT:
        reject(f"{path.name}: unsupported format")
    if document.get("scenario") != expected_scenario:
        reject(f"{path.name}: scenario does not match filename")
    final_hash = document.get("final_truth_hash")
    if not isinstance(final_hash, str) or len(final_hash) != 16:
        reject(f"{path.name}: invalid final truth hash")
    try:
        int(final_hash, 16)
    except ValueError:
        reject(f"{path.name}: final truth hash is not hexadecimal")
    ticks = document.get("ticks")
    if not isinstance(ticks, list) or not ticks:
        reject(f"{path.name}: ticks must be a nonempty array")
    for tick_number, tick in enumerate(ticks):
        if not isinstance(tick, dict) or not REQUIRED_TICK_KEYS.issubset(tick):
            reject(f"{path.name}: tick {tick_number} lacks required truth fields")
        if tick["tick"] != tick_number:
            reject(f"{path.name}: non-contiguous tick at {tick_number}")
        if not isinstance(tick["events"], list) or not all(
            isinstance(event, str) for event in tick["events"]
        ):
            reject(f"{path.name}: tick {tick_number} events are invalid")
        injury = tick["injury"]
        if not isinstance(injury, dict) or {
            "arm_trauma",
            "torso_trauma",
            "available_intents",
            "incapacitated",
        } - set(injury):
            reject(f"{path.name}: tick {tick_number} injury state is incomplete")
        truth_hash = tick["truth_hash"]
        if not isinstance(truth_hash, str) or len(truth_hash) != 16:
            reject(f"{path.name}: tick {tick_number} truth hash is invalid")
    if ticks[-1]["truth_hash"] != final_hash:
        reject(f"{path.name}: final truth hash does not equal last tick")
    return final_hash


def parse_truth_hashes(root: Path) -> dict[str, str]:
    path = root / "scenario_truth_hashes.txt"
    if not path.is_file():
        reject("missing scenario_truth_hashes.txt")
    result: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 2:
            reject(f"truth hash line {line_number}: expected scenario and hash")
        scenario, truth_hash = fields
        if scenario in result or scenario not in SCENARIOS:
            reject(f"truth hash line {line_number}: duplicate or unknown scenario")
        result[scenario] = truth_hash
    if set(result) != set(SCENARIOS):
        reject("truth hash list is incomplete")
    return result


def verify_dir(root: Path) -> dict[str, str]:
    if not root.is_dir():
        reject(f"not a golden directory: {root}")
    manifest = parse_manifest(root)
    observed: dict[str, str] = {}
    for scenario in SCENARIOS:
        filename = f"{scenario}.golden.json"
        path = root / filename
        if not path.is_file():
            reject(f"manifest file missing: {filename}")
        actual = sha256_file(path)
        if actual != manifest[filename]:
            reject(
                f"SHA-256 mismatch for {filename}: expected {manifest[filename]}, got {actual}"
            )
        observed[scenario] = validate_replay(path, scenario)
    truth_hashes = parse_truth_hashes(root)
    if observed != truth_hashes:
        reject(f"scenario final truth hashes differ: recorded={truth_hashes}, observed={observed}")
    return observed


def verify_command(root: Path) -> int:
    try:
        hashes = verify_dir(root)
    except VerificationError as error:
        print(f"GOLDEN_REPLAY_VERIFY=FAIL_CLOSED reason={error}", file=sys.stderr)
        return 1
    print(
        "GOLDEN_REPLAY_VERIFY=PASS "
        f"scenarios={len(hashes)} final_hashes="
        + ",".join(f"{name}:{hashes[name]}" for name in SCENARIOS)
    )
    return 0


def tamper_test(root: Path) -> int:
    try:
        verify_dir(root)
    except VerificationError as error:
        print(f"TAMPER_TEST=FAIL baseline_untrusted={error}", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="just-dodge-m6-tamper-") as temporary:
        copied = Path(temporary) / "goldens"
        shutil.copytree(root, copied)
        victim = copied / f"{SCENARIOS[0]}.golden.json"
        with victim.open("ab") as handle:
            handle.write(b" ")
        try:
            verify_dir(copied)
        except VerificationError as error:
            print(f"TAMPER_TEST=PASS fail_closed_reason={error}")
            return 0
    print("TAMPER_TEST=FAIL tampered replay was accepted", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "tamper-test"))
    parser.add_argument("golden_dir", type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        return verify_command(args.golden_dir)
    return tamper_test(args.golden_dir)


if __name__ == "__main__":
    raise SystemExit(main())
