#!/usr/bin/env python3
"""Fail-closed repository quarantine gate for Just Dodge (JD-RC0 §1/§2).

The 162-example dynamic combat demo and every mocked/synthetic/developer-machine
artifact are quarantined exploratory-only evidence. They must not be referenced
from any tracked production, promotion, CI, or evidence path as if they were
valid. This gate scans tracked files and fails if a forbidden reference appears
outside the explicitly allowed quarantine notice/tooling set.

Exit 0 = quarantine holds. Exit 1 = a forbidden reference was found.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Files that legitimately mention the quarantined demo: the quarantine notice,
# the quarantined generator/renderer themselves, the promotion gate that rejects
# them, its tests, and the recorded truth baseline. Everything else is forbidden.
ALLOWED = {
    "docs/evidence_quarantine/DYNAMIC_COMBAT_DEMO_162_INVALID.md",
    "tools/qa/dynamic_combat_demo.py",
    "tools/qa/render_dynamic_combat_frames.py",
    "tools/qa/validate_forgelens_review_run.py",
    "tools/qa/test_forgelens_review_run_schema.py",
    "tools/qa/enforce_evidence_quarantine.py",
    "docs/reports/JD_RC0_TRUTH_BASELINE_2026-07-17.md",
}

FORBIDDEN_MARKERS = (
    "dynamic_combat_demo",
    "dynamic-combat-demo-162",
    "render_dynamic_combat_frames",
    "r6k-dynamic-combat-demo",
)

SCAN_SUFFIXES = {".py", ".rs", ".json", ".md", ".yml", ".yaml", ".ron", ".toml", ".js", ".sh"}


def tracked_files() -> list[str]:
    out = subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def main() -> int:
    violations: list[str] = []
    for rel in tracked_files():
        if rel in ALLOWED:
            continue
        path = ROOT / rel
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lowered = text.lower()
        for marker in FORBIDDEN_MARKERS:
            if marker.lower() in lowered:
                violations.append(f"{rel}: references quarantined marker {marker!r}")
                break
    if violations:
        print("EVIDENCE_QUARANTINE=FAIL")
        for violation in violations:
            print(f"  {violation}")
        return 1
    print("EVIDENCE_QUARANTINE=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
