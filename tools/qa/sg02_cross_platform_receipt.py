#!/usr/bin/env python3
"""Emit a fail-closed SG02 golden-replay platform receipt.

The executable itself performs each scenario 100 times. This wrapper binds its
seven reported final truth hashes to a source revision, platform identity, and
binary hash. It deliberately rejects Wine/non-native platform labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "just-dodge-sg02-platform-receipt-v1"
EXPECTED_SCHEMA = "just-dodge-sg02-golden-hashes-v1"
LINE = re.compile(
    r"^golden_match scenario=([a-z0-9_]+) final_truth_hash=([0-9a-f]{16}) "
    r"runs=100 identical=true$"
)
PLATFORM_SYSTEM = {"Linux": "Linux", "Windows": "Windows", "SteamDeck": "Linux"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def read_expected(path: Path) -> tuple[dict[str, str], str]:
    document = json.loads(path.read_bytes())
    if document.get("schema") != EXPECTED_SCHEMA:
        raise ValueError(f"unsupported expected-hash schema: {path}")
    scenarios = document.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios:
        raise ValueError("expected scenarios must be a nonempty object")
    normalized: dict[str, str] = {}
    for scenario, truth_hash in scenarios.items():
        if not isinstance(scenario, str) or not isinstance(truth_hash, str):
            raise ValueError("scenario hashes must be strings")
        if not re.fullmatch(r"[0-9a-f]{16}", truth_hash):
            raise ValueError(f"invalid expected truth hash for {scenario!r}")
        normalized[scenario] = truth_hash
    return normalized, sha256_bytes(canonical_bytes(document))


def parse_hashes(output: str, expected_scenarios: set[str]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for raw in output.splitlines():
        match = LINE.fullmatch(raw.strip())
        if not match:
            continue
        scenario, truth_hash = match.groups()
        if scenario in observed:
            raise ValueError(f"duplicate scenario from golden_match: {scenario}")
        observed[scenario] = truth_hash
    if set(observed) != expected_scenarios:
        raise ValueError(
            "golden_match scenario set mismatch: "
            f"expected={sorted(expected_scenarios)} observed={sorted(observed)}"
        )
    return observed


def steamdeck_attestation(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    for raw in text.splitlines():
        if "=" not in raw or raw.startswith("#"):
            continue
        key, value = raw.split("=", 1)
        fields[key] = value.strip().strip('"')
    haystack = " ".join(fields.values()).lower()
    if "steamos" not in haystack and "steamdeck" not in haystack:
        raise ValueError(f"Steam Deck attestation lacks SteamOS marker: {path}")
    return {
        "os_release_sha256": sha256_file(path),
        "os_id": fields.get("ID", ""),
        "os_variant_id": fields.get("VARIANT_ID", ""),
    }


def run_binary(binary: Path) -> str:
    completed = subprocess.run(
        [str(binary), "--print-hashes"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"golden_match failed rc={completed.returncode}: {completed.stderr.strip()}"
        )
    return completed.stdout


def rustc_version() -> str:
    return subprocess.check_output(("rustc", "--version"), text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden-match", required=True, type=Path)
    parser.add_argument("--expected", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--platform-label", required=True, choices=sorted(PLATFORM_SYSTEM))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--steamdeck-os-release",
        type=Path,
        help="required with --platform-label SteamDeck; must attest SteamOS",
    )
    args = parser.parse_args()

    if not re.fullmatch(r"[0-9a-f]{40}", args.source_revision):
        parser.error("--source-revision must be a 40-character lowercase Git commit")
    if not args.golden_match.is_file():
        parser.error(f"golden_match is not a file: {args.golden_match}")
    if platform.system() != PLATFORM_SYSTEM[args.platform_label]:
        parser.error(
            f"platform label {args.platform_label} requires {PLATFORM_SYSTEM[args.platform_label]}, "
            f"observed {platform.system()} (Wine is not Windows evidence)"
        )
    if args.platform_label == "SteamDeck":
        if args.steamdeck_os_release is None:
            parser.error("SteamDeck receipts require --steamdeck-os-release")
        attestation = steamdeck_attestation(args.steamdeck_os_release)
    elif args.steamdeck_os_release is not None:
        parser.error("--steamdeck-os-release is valid only for SteamDeck receipts")
    else:
        attestation = None

    expected, expected_sha256 = read_expected(args.expected)
    observed = parse_hashes(run_binary(args.golden_match), set(expected))
    if observed != expected:
        parser.error(f"golden truth hashes differ: expected={expected} observed={observed}")

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "source_revision": args.source_revision,
        "platform_label": args.platform_label,
        "observed_system": platform.system(),
        "observed_machine": platform.machine(),
        "python_version": platform.python_version(),
        "rustc_version": rustc_version(),
        "golden_match_sha256": sha256_file(args.golden_match),
        "golden_match_args": ["--print-hashes"],
        "expected_hashes_sha256": expected_sha256,
        "scenario_hashes": observed,
    }
    if attestation is not None:
        receipt["steamdeck_attestation"] = attestation
    receipt["receipt_sha256"] = sha256_bytes(canonical_bytes(receipt))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(
        "SG02_PLATFORM_RECEIPT=PASS "
        f"platform={args.platform_label} scenarios={len(observed)} "
        f"receipt_sha256={receipt['receipt_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
