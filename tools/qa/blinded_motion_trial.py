#!/usr/bin/env python3
"""Prepare and score fail-closed blinded C0 action-readability trials."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import random
import shutil
from pathlib import Path


ACTIONS = ("strike", "block", "grab")
CLIP_IDS = ("A", "B", "C")
MIN_PARTICIPANTS = 20
MIN_ACCURACY = 0.80


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def prepare(args: argparse.Namespace) -> None:
    source_dir = args.source_dir.resolve()
    out_dir = args.out_dir.resolve()
    if args.participants < MIN_PARTICIPANTS:
        raise SystemExit(f"participants must be >= {MIN_PARTICIPANTS}")
    if out_dir.exists():
        raise SystemExit(f"refusing to overwrite existing trial packet: {out_dir}")

    sources: dict[str, dict[str, Path]] = {}
    for action, candidate in args.candidate:
        if action not in ACTIONS:
            raise SystemExit(f"unsupported action {action!r}")
        if action in sources:
            raise SystemExit(f"duplicate candidate for {action}")
        paths = {
            view: source_dir / f"{candidate}_{view}_reveal.png"
            for view in ("front", "side")
        }
        for path in paths.values():
            if not path.is_file():
                raise SystemExit(f"missing reveal strip: {path}")
        sources[action] = paths
    if set(sources) != set(ACTIONS):
        raise SystemExit("exactly one strike, block, and grab candidate is required")

    out_dir.mkdir(parents=True)
    rng = random.Random(args.seed)
    permutations = list(itertools.permutations(ACTIONS))
    rng.shuffle(permutations)
    assignments: dict[str, dict[str, str]] = {}
    public_participants = []

    for index in range(args.participants):
        participant_id = f"P{index + 1:02d}"
        participant_dir = out_dir / "participants" / participant_id
        participant_dir.mkdir(parents=True)
        permutation = permutations[index % len(permutations)]
        assignment = dict(zip(CLIP_IDS, permutation, strict=True))
        assignments[participant_id] = assignment
        public_clips = []
        for clip_id, action in assignment.items():
            clip_hashes = {}
            for view in ("front", "side"):
                destination = participant_dir / f"clip_{clip_id}_{view}.png"
                shutil.copyfile(sources[action][view], destination)
                clip_hashes[view] = sha256(destination)
            public_clips.append({"clip_id": clip_id, "sha256": clip_hashes})
        (participant_dir / "instructions.txt").write_text(
            "Without consulting filenames, source material, another participant, or the answer key,\n"
            "label each clip A/B/C exactly once as Strike, Block, or Grab. Use only the first\n"
            "eight ordered frames shown in the front and side strips. Record your labels in\n"
            "responses.csv using lowercase strike, block, or grab.\n"
        )
        public_participants.append(
            {"participant_id": participant_id, "clips": public_clips}
        )

    with (out_dir / "responses.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["participant_id", "clip_id", "label"])

    source_receipts = {
        action: {view: sha256(path) for view, path in paths.items()}
        for action, paths in sources.items()
    }
    write_json(
        out_dir / "trial_manifest.json",
        {
            "schema": "just-dodge-blinded-motion-trial-v1",
            "participants": public_participants,
            "participant_count": args.participants,
            "clips_per_participant": len(CLIP_IDS),
            "labels": list(ACTIONS),
            "minimum_accuracy_per_action": MIN_ACCURACY,
            "source_receipts": source_receipts,
        },
    )
    write_json(
        out_dir / "answer_key.json",
        {
            "schema": "just-dodge-blinded-motion-answer-key-v1",
            "seed": args.seed,
            "assignments": assignments,
            "warning": "Keep this file unavailable to trial participants until all responses are locked.",
        },
    )
    print(f"BLINDED_MOTION_TRIAL_PREPARED={out_dir}")
    print(f"TRIAL_MANIFEST_SHA256={sha256(out_dir / 'trial_manifest.json')}")
    print(f"ANSWER_KEY_SHA256={sha256(out_dir / 'answer_key.json')}")


def score(args: argparse.Namespace) -> None:
    trial_dir = args.trial_dir.resolve()
    manifest_path = trial_dir / "trial_manifest.json"
    answer_path = trial_dir / "answer_key.json"
    responses_path = trial_dir / "responses.csv"
    manifest = json.loads(manifest_path.read_text())
    answers = json.loads(answer_path.read_text())["assignments"]
    expected_participants = {
        entry["participant_id"] for entry in manifest["participants"]
    }
    if len(expected_participants) < MIN_PARTICIPANTS:
        raise SystemExit("trial manifest has fewer than 20 participants")

    seen: set[tuple[str, str]] = set()
    totals = {action: 0 for action in ACTIONS}
    correct = {action: 0 for action in ACTIONS}
    with responses_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["participant_id", "clip_id", "label"]:
            raise SystemExit("responses.csv header is invalid")
        for row in reader:
            participant_id = row["participant_id"].strip()
            clip_id = row["clip_id"].strip().upper()
            label = row["label"].strip().lower()
            key = (participant_id, clip_id)
            if participant_id not in expected_participants:
                raise SystemExit(f"unexpected participant {participant_id!r}")
            if clip_id not in CLIP_IDS or label not in ACTIONS:
                raise SystemExit(f"invalid response {row!r}")
            if key in seen:
                raise SystemExit(f"duplicate response for {participant_id}/{clip_id}")
            seen.add(key)
            action = answers[participant_id][clip_id]
            totals[action] += 1
            correct[action] += int(label == action)

    expected = {
        (participant_id, clip_id)
        for participant_id in expected_participants
        for clip_id in CLIP_IDS
    }
    missing = sorted(expected - seen)
    if missing:
        raise SystemExit(f"incomplete response set: {len(missing)} labels missing")
    results = {
        action: {
            "correct": correct[action],
            "total": totals[action],
            "accuracy": correct[action] / totals[action],
            "pass": correct[action] / totals[action] >= MIN_ACCURACY,
        }
        for action in ACTIONS
    }
    passed = all(result["pass"] for result in results.values())
    report_path = trial_dir / "score_report.json"
    write_json(
        report_path,
        {
            "schema": "just-dodge-blinded-motion-score-v1",
            "responses_sha256": sha256(responses_path),
            "trial_manifest_sha256": sha256(manifest_path),
            "answer_key_sha256": sha256(answer_path),
            "minimum_accuracy_per_action": MIN_ACCURACY,
            "results": results,
            "pass": passed,
        },
    )
    print(json.dumps(results, sort_keys=True))
    print(f"BLINDED_MOTION_GATE={'PASS' if passed else 'FAIL'}")
    print(f"SCORE_REPORT_SHA256={sha256(report_path)}")
    if not passed:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--source-dir", type=Path, required=True)
    prepare_parser.add_argument("--out-dir", type=Path, required=True)
    prepare_parser.add_argument("--participants", type=int, default=20)
    prepare_parser.add_argument("--seed", type=int, default=2026071404)
    prepare_parser.add_argument(
        "--candidate",
        action="append",
        nargs=2,
        metavar=("ACTION", "CANDIDATE"),
        required=True,
    )
    score_parser = subparsers.add_parser("score")
    score_parser.add_argument("--trial-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "prepare":
        prepare(args)
    else:
        score(args)


if __name__ == "__main__":
    main()
