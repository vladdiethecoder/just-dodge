#!/usr/bin/env python3
"""Measure a fresh PVP-005 C0 reveal render without granting semantic admission."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image


VIEWS = ("front", "side", "top", "first_person_duel")
MIN_CARRIER_HEIGHT = 0.55
MAX_CARRIER_HEIGHT = 0.90
MIN_CARRIER_PIXEL_FRACTION = 0.05
MIN_TEMPORAL_RGB_DELTA = 0.001
EXPECTED_IMAGE_SIZE = (2048, 2048)
POSE_RECEIPT = re.compile(r"selected=(\d+) pose_receipt=([0-9a-f]{16})")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def carrier_metrics(path: Path) -> tuple[float, float]:
    rgb = np.asarray(Image.open(path).convert("RGB"))
    mask = (
        (rgb[:, :, 0] > 80)
        & (rgb[:, :, 0] > rgb[:, :, 2] * 1.25)
        & (rgb[:, :, 1] > rgb[:, :, 2] * 1.10)
    )
    y, _ = np.where(mask)
    if len(y) == 0:
        return 0.0, 0.0
    height = float((y.max() - y.min() + 1) / rgb.shape[0])
    return height, float(mask.mean())


def temporal_delta(left: Path, right: Path) -> float:
    a = np.asarray(Image.open(left).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(right).convert("RGB"), dtype=np.int16)
    return float(np.abs(a - b).mean() / 255.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render_root = args.render_root.resolve()
    manifest = json.loads(args.manifest.read_text())
    failures: list[str] = []
    action_reports = {}

    for action in ("strike", "block", "grab"):
        entry = manifest["actions"][action]
        candidate = entry["candidate"]
        frames = entry["tell_frames"]
        action_dir = render_root / candidate
        expected = {
            action_dir / f"{candidate}_f{frame:02d}_{view}.png"
            for frame in frames
            for view in VIEWS
        }
        actual = set(action_dir.glob("*.png"))
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing:
            failures.append(f"{action}: missing {len(missing)} images")
        if extra:
            failures.append(f"{action}: unexpected {len(extra)} images")

        image_receipts = {}
        for path in sorted(expected & actual):
            with Image.open(path) as image:
                size = image.size
            if size != EXPECTED_IMAGE_SIZE:
                failures.append(f"{action}: {path.name} size {size}")
            image_receipts[path.name] = {"bytes": path.stat().st_size, "sha256": digest(path)}

        front_paths = [action_dir / f"{candidate}_f{frame:02d}_front.png" for frame in frames]
        occupancy = [carrier_metrics(path) for path in front_paths if path.is_file()]
        deltas = [
            temporal_delta(left, right)
            for left, right in zip(front_paths, front_paths[1:])
            if left.is_file() and right.is_file()
        ]
        if len(occupancy) != len(frames):
            failures.append(f"{action}: incomplete front occupancy evidence")
        else:
            for frame, (height, pixel_fraction) in zip(frames, occupancy, strict=True):
                if not MIN_CARRIER_HEIGHT <= height <= MAX_CARRIER_HEIGHT:
                    failures.append(f"{action}: frame {frame} carrier height {height:.6f}")
                if pixel_fraction < MIN_CARRIER_PIXEL_FRACTION:
                    failures.append(
                        f"{action}: frame {frame} carrier pixels {pixel_fraction:.6f}"
                    )
        if len(deltas) != len(frames) - 1 or any(
            delta < MIN_TEMPORAL_RGB_DELTA for delta in deltas
        ):
            failures.append(f"{action}: reveal contains a static/duplicate adjacent frame")

        log_path = action_dir / "render.log"
        receipt_pairs = POSE_RECEIPT.findall(log_path.read_text() if log_path.is_file() else "")
        receipt_frames = [int(frame) for frame, _ in receipt_pairs]
        receipt_values = [value for _, value in receipt_pairs]
        if receipt_frames != frames:
            failures.append(f"{action}: pose receipt frames {receipt_frames} != {frames}")
        if len(set(receipt_values)) != len(frames):
            failures.append(f"{action}: pose receipts are not unique per reveal frame")

        action_reports[action] = {
            "candidate": candidate,
            "tell_frames": frames,
            "pose_receipts": receipt_values,
            "front_carrier_height_fraction": [value[0] for value in occupancy],
            "front_carrier_pixel_fraction": [value[1] for value in occupancy],
            "adjacent_front_rgb_delta": deltas,
            "images": image_receipts,
            "front_strip": {
                "path": f"{candidate}_front_reveal.png",
                "sha256": digest(render_root / f"{candidate}_front_reveal.png"),
            },
            "side_strip": {
                "path": f"{candidate}_side_reveal.png",
                "sha256": digest(render_root / f"{candidate}_side_reveal.png"),
            },
        }

    report = {
        "schema": "just-dodge-pvp005-c0-visual-harness-v1",
        "thresholds": {
            "expected_image_size_px": list(EXPECTED_IMAGE_SIZE),
            "front_carrier_height_fraction": [MIN_CARRIER_HEIGHT, MAX_CARRIER_HEIGHT],
            "min_front_carrier_pixel_fraction": MIN_CARRIER_PIXEL_FRACTION,
            "min_adjacent_front_rgb_delta": MIN_TEMPORAL_RGB_DELTA,
        },
        "actions": action_reports,
        "automated_mechanical_visual_pass": not failures,
        "semantic_blinded_human_gate": "pending",
        "socket_contact_parity_gate": "not_measured",
        "known_visual_finding": (
            "QA sword crosses the Block carrier in early frames; this harness does not waive or "
            "score the separate pose-derived socket/contact gate."
        ),
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    cards = []
    for action, action_report in action_reports.items():
        candidate = html.escape(action_report["candidate"])
        cards.append(
            f"<section><h2>{html.escape(action.title())}: {candidate}</h2>"
            f"<img src='{candidate}_front_reveal.png' alt='{action} front reveal'>"
            f"<img src='{candidate}_side_reveal.png' alt='{action} side reveal'></section>"
        )
    (render_root / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>PVP-005 C0 visual harness</title>"
        "<style>body{background:#111;color:#eee;font:16px sans-serif}img{display:block;"
        "max-width:100%;margin:8px 0;border:1px solid #555}</style>"
        "<h1>PVP-005 C0 reveal evidence — mechanical visual checks only</h1>"
        "<p>Semantic blinded-human and socket/contact parity gates remain pending.</p>"
        + "".join(cards)
    )
    print(f"PVP005_C0_VISUAL_REPORT_SHA256={digest(args.output)}")
    print(
        "PVP005_C0_VISUAL_HARNESS="
        + ("PASS_MECHANICAL_ONLY" if not failures else "FAIL")
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
