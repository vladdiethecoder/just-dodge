#!/usr/bin/env python3
"""Build the P3 real target-directed vertical-Strike corpus (kimodo teachers).

Generates REAL kimodo clips for the vertical-Strike lane: 3 targets
(high_left/center/right) x N distinct seeds. Each clip is a genuine kimodo
generation with a distinct seed (source identity), NOT a Cartesian/pose variant
of one template. These are training teachers for the interaction-conditioned
MotionBricks checkpoint (train-path), separated by source clip identity for
held-out evaluation.

Distinctness is verified: clips sharing a target but different seeds must differ
in motion (min pairwise trajectory distance above a floor), else the corpus is
rejected as label-swapped. Timing variants come from retiming to early/nominal/
late contact frames downstream; this stage produces the diverse target-directed
source motion.

Output: qa_runs/p3_strike_corpus/<target>/seed<k>.npz + manifest.json (gitignored).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "high_left": "raise longsword high overhead with both hands then slash down to the upper left, planted feet",
    "high_center": "raise longsword high overhead with both hands then slash straight down to the head, planted feet",
    "high_right": "raise longsword high overhead with both hands then slash down to the upper right, planted feet",
}
BASE_SEED = 20260717
DURATION = 2.0
MODEL = "Kimodo-G1-SEED-v1"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def hand_traj(npz_path: Path) -> np.ndarray:
    d = np.load(npz_path)
    posed = d["posed_joints"]
    if posed.ndim == 4:
        posed = posed[0]
    return posed[:, 33, :]  # right hand (G1 joint 33)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "qa_runs/p3_strike_corpus")
    ap.add_argument("--seeds", type=int, default=6, help="distinct seeds per target")
    ap.add_argument("--targets", nargs="*", default=list(TARGETS))
    args = ap.parse_args()
    args.out = args.out.resolve()

    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "just-dodge-p3-strike-corpus-v1", "model": MODEL,
                "duration_s": DURATION, "clips": []}

    for target in args.targets:
        prompt = TARGETS[target]
        tdir = args.out / target
        tdir.mkdir(parents=True, exist_ok=True)
        for k in range(args.seeds):
            # Retry weak generations with a seed offset; a real vertical strike
            # must raise the hand overhead (ymax) then drop it (travel, y_range).
            clip_ok = False
            for attempt in range(8):
                seed = BASE_SEED + k + attempt * 1000
                stem = tdir / f"seed{seed}"
                npz = Path(f"{stem}.npz")
                if not npz.is_file():
                    proc = subprocess.run(
                        ["kimodo_gen", prompt, "--model", MODEL, "--duration", str(DURATION),
                         "--num_samples", "1", "--seed", str(seed), "--output", str(stem)],
                        cwd=ROOT, capture_output=True, text=True, timeout=300)
                    if proc.returncode != 0 or not npz.is_file():
                        continue
                traj = hand_traj(npz)
                travel = float(np.abs(np.diff(traj, axis=0)).sum())
                y_max = float(traj[:, 1].max())
                y_range = float(traj[:, 1].max() - traj[:, 1].min())
                # Real overhead vertical strike: hand rises overhead then cuts down.
                if travel > 1.5 and y_max > 1.0 and y_range > 0.35:
                    clip_ok = True
                    break
                npz.unlink(missing_ok=True)  # reject weak clip, retry
            if not clip_ok:
                print(f"FAIL {target}/clip{k}: no strong strike after retries", file=sys.stderr)
                return 1
            manifest["clips"].append({
                "target": target, "seed": seed, "path": str(npz.relative_to(ROOT)),
                "sha256": sha(npz.read_bytes()), "frames": int(traj.shape[0]),
                "hand_travel_m": round(travel, 4), "hand_y_range_m": round(y_range, 4),
                "prompt": prompt,
            })
            print(f"  {target}/seed{seed}: frames={traj.shape[0]} travel={travel:.3f}m y_range={y_range:.3f}m")

    # Distinctness: within each target, distinct seeds must produce distinct motion.
    failures = []
    for target in args.targets:
        clips = [c for c in manifest["clips"] if c["target"] == target]
        trajs = [hand_traj(ROOT / c["path"]) for c in clips]
        # pad/trim to common length
        L = min(t.shape[0] for t in trajs)
        trajs = [t[:L] for t in trajs]
        min_pair = min(
            float(np.abs(trajs[i] - trajs[j]).mean())
            for i in range(len(trajs)) for j in range(i + 1, len(trajs))
        ) if len(trajs) > 1 else 1.0
        print(f"  {target}: min pairwise hand-traj diff = {min_pair*1000:.1f}mm")
        if min_pair < 0.005:  # <5mm mean diff => effectively identical (label swap)
            failures.append(f"{target}: seeds not distinct (min diff {min_pair*1000:.1f}mm)")

    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    n = len(manifest["clips"])
    print(f"P3_STRIKE_CORPUS clips={n} targets={len(args.targets)} seeds_per_target={args.seeds}")
    if failures:
        for f in failures:
            print(f"DISTINCTNESS_FAIL {f}", file=sys.stderr)
        return 1
    print("P3_STRIKE_CORPUS_DISTINCT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
