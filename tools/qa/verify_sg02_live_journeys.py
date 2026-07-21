#!/usr/bin/env python3
"""Verify native SG02 ten-journey lifecycle receipts from stderr/stdout."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

JOURNEY_RE = re.compile(
    r"^SG02_LIVE_JOURNEY index=(?P<index>\d+) seed=(?P<seed>\d+) "
    r"terminal_hash=(?P<terminal>[0-9a-f]{16}) truth_ticks=(?P<ticks>\d+) "
    r"stage_mask=(?P<mask>[0-9a-f]{2}) replay_verified=true$"
)
REMATCH_RE = re.compile(
    r"^SG02_LIVE_REMATCH seed=(?P<seed>\d+) "
    r"canonical_initial_hash=(?P<initial>[0-9a-f]{16}) stage=MatchSetup$"
)
FINAL_RE = re.compile(
    r"^SG02_LIVE_JOURNEYS=PASS count=(?P<count>\d+) no_developer_control=true$"
)
FIRST_STAGE_MASK = 0x7F
REMATCH_STAGE_MASK = 0x7C
MAX_TRUTH_TICKS = 20_000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def verify(text: str, expected_count: int) -> None:
    lines = text.splitlines()
    journeys = [match for line in lines if (match := JOURNEY_RE.fullmatch(line))]
    rematches = [match for line in lines if (match := REMATCH_RE.fullmatch(line))]
    finals = [match for line in lines if (match := FINAL_RE.fullmatch(line))]

    require(len(journeys) == expected_count, f"expected {expected_count} journey receipts, found {len(journeys)}")
    require(len(rematches) == expected_count - 1, "rematch receipt count mismatch")
    require(len(finals) == 1 and int(finals[0]["count"]) == expected_count, "final PASS receipt mismatch")
    require(lines.count("SG02_LIVE_FLOW stage=Boot>Menu>MatchSetup") == 1, "initial Boot/Menu/Setup chain mismatch")
    require(lines.count("SG02_LIVE_FLOW stage=Result>Replay") == expected_count, "Result/Replay chain count mismatch")

    indices = [int(match["index"]) for match in journeys]
    seeds = [int(match["seed"]) for match in journeys]
    require(indices == list(range(1, expected_count + 1)), "journey indices are not contiguous")
    require(seeds == list(range(seeds[0], seeds[0] + expected_count)), "journey seeds are not contiguous")

    for offset, match in enumerate(journeys):
        ticks = int(match["ticks"])
        stage_mask = int(match["mask"], 16)
        require(0 < ticks <= MAX_TRUTH_TICKS, f"journey {offset + 1} exceeded truth-tick budget")
        expected_mask = FIRST_STAGE_MASK if offset == 0 else REMATCH_STAGE_MASK
        require(stage_mask == expected_mask, f"journey {offset + 1} stage mask {stage_mask:02x} != {expected_mask:02x}")

    rematch_seeds = [int(match["seed"]) for match in rematches]
    require(rematch_seeds == seeds[1:], "rematch seeds do not bind the next journeys")
    print(
        "SG02_LIVE_JOURNEY_RECEIPTS=PASS "
        f"count={expected_count} max_truth_ticks={max(int(match['ticks']) for match in journeys)} "
        f"first_seed={seeds[0]} last_seed={seeds[-1]}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()
    require(args.count > 0, "--count must be positive")
    verify(args.log.read_text(encoding="utf-8"), args.count)


if __name__ == "__main__":
    main()
