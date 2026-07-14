#!/usr/bin/env python3
"""Render and index the deterministic PVP-005 candidate MRT orbit sheets."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import struct
import subprocess
from pathlib import Path

from pvp005_visual_contract import DEFAULT_CONFIG, sha256, validate_config


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "assets/motion/pvp005_candidates/manifest.json"


def png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise SystemExit(f"invalid PNG output: {path}")
    return struct.unpack(">II", header[16:24])


def render_action(binary: Path, action: str, entry: dict[str, object], output: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "PVP005_ACTION": action,
            "PVP005_F413": str(ROOT / entry["f413"]["path"]),
            "PVP005_TELL_START": str(entry["tell_frames"][0]),
            "PVP005_OUTPUT_DIR": str(output),
        }
    )
    subprocess.run([str(binary)], cwd=ROOT, env=env, check=True)


def build_index(output: Path, actions: list[str], config_hash: str) -> dict[str, object]:
    reports: dict[str, object] = {}
    receipts: dict[str, object] = {}
    sections = []
    for action in actions:
        action_root = output / action
        report_path = action_root / "capture.json"
        report = json.loads(report_path.read_text())
        reports[action] = report
        images = sorted(action_root.glob("*.png"))
        if len(images) != 180:
            raise SystemExit(f"{action}: expected 160 orbit sheets and 20 first-person strips, found {len(images)}")
        for image in images:
            expected_dimensions = (4096, 512) if "first_person_8f" in image.name else (2048, 2048)
            if png_dimensions(image) != expected_dimensions:
                raise SystemExit(f"{image}: expected {expected_dimensions}, got {png_dimensions(image)}")
            relative = image.relative_to(output).as_posix()
            receipts[relative] = {"bytes": image.stat().st_size, "sha256": sha256(image)}
        preview = action_root / f"{action}_candidate_f00_charcoal_beauty.png"
        sections.append(
            f"<section><h2>{html.escape(action.title())} — {'PASS' if report['pass'] else 'FAIL'}</h2>"
            f"<p>crop failures: {report['crop_failures']}; visibility failures: {report['visibility_failures']}</p>"
            f"<a href='{html.escape(preview.relative_to(output).as_posix())}'>"
            f"<img loading='lazy' src='{html.escape(preview.relative_to(output).as_posix())}'></a></section>"
        )
    result = {
        "schema": "just-dodge-pvp005-candidate-visual-index-v1",
        "config_sha256": config_hash,
        "candidate_manifest_sha256": sha256(MANIFEST),
        "scope": "candidate",
        "required_scopes_complete": False,
        "reports": reports,
        "image_receipts": receipts,
        "pass": all(report["pass"] for report in reports.values()),
        "remaining_scopes": ["admitted", "live_runtime"],
        "remaining_layers": [
            "wireframe",
        ],
        "first_person_output": "8_frame_4096x512_strip_from_live_camera_matrices",
    }
    (output / "index.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (output / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>PVP-005 candidate MRT harness</title>"
        "<style>body{font:16px sans-serif;background:#111;color:#eee;max-width:1200px;margin:auto}"
        "img{width:100%;height:auto}section{margin:2rem 0;padding:1rem;background:#222}</style>"
        "<h1>PVP-005 deterministic candidate MRT harness</h1>"
        "<p>Candidate scope only. This index is not an admission packet or readability pass.</p>"
        + "".join(sections)
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--actions", nargs="+", choices=["strike", "block", "grab"], default=["strike", "block", "grab"])
    parser.add_argument("--binary", type=Path, default=ROOT / "target/release/pvp005_capture")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--allow-failed-candidates", action="store_true", help="emit diagnostic index but return zero when current candidates fail crop/visibility")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite visual harness output: {output}")
    contract = validate_config(DEFAULT_CONFIG)
    manifest = json.loads(MANIFEST.read_text())
    if not args.skip_build:
        subprocess.run(["cargo", "build", "--locked", "--release", "--bin", "pvp005_capture"], cwd=ROOT, check=True)
    binary = args.binary.resolve()
    if not binary.is_file():
        raise SystemExit(f"missing PVP-005 capture binary: {binary}")
    output.mkdir(parents=True)
    for action in args.actions:
        render_action(binary, action, manifest["actions"][action], output / action)
    result = build_index(output, args.actions, hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest())
    print(f"PVP005_VISUAL_INDEX_SHA256={sha256(output / 'index.json')}")
    print(f"PVP005_CANDIDATE_VISUAL_HARNESS={'PASS' if result['pass'] else 'FAIL'}")
    if not result["pass"] and not args.allow_failed_candidates:
        raise SystemExit("candidate visual harness failed closed; inspect index.json")


if __name__ == "__main__":
    main()
