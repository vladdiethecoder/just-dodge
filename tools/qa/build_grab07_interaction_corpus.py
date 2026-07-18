#!/usr/bin/env python3
"""Build the GRAB07 real target-directed grab corpus (kimodo teachers).

Generates REAL kimodo clips for the grab lane: a paired two-hand reach/lunge
that physically closes toward a target at the engine's 650 mm acquisition
distance. Each clip is a genuine kimodo generation with a distinct seed (source
identity), NOT a hand-authored or Cartesian/pose variant of one template. These
are training teachers for the interaction-conditioned grab conditioner
(Approach A, train-path), separated by source clip identity for held-out eval.

The grab is a FORWARD reach, not an overhead strike, so the quality floor
measures: forward hand travel (z), peak forward reach, two-hand grip span in a
plausible grab band, and a deliberate forward step/lunge (root z displacement).

Distinctness is verified: clips sharing a target but different seeds must
differ in motion (min pairwise trajectory distance above a floor), else the
corpus is rejected as label-swapped.

Output: qa_runs/grab07_interaction_corpus/<target>/seed<k>.npz + manifest.json
(gitignored; teacher corpus, runtime_admitted=False).
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
# Grab reach targets: condition on the desired forward contact distance. The
# engine acquisition is 650 mm; the conditioner learns to land the hands at a
# target forward distance so the retargeted mesh closes the gap.
TARGETS = {
    "reach_nominal": "step forward and reach out with both hands to grab a person in front at arm's length, two-hand grab to the torso, deliberate lunge",
    "reach_high": "lunge forward and grab high at the opponent's shoulders with both hands, aggressive two-hand grab, planted back foot",
    "reach_low": "drop level and lunge forward to grab the opponent's waist with both hands, low two-hand grab",
}
BASE_SEED = 20260718
DURATION = 2.0
MODEL = "Kimodo-G1-SEED-v1"
HAND_R, HAND_L = 33, 25  # G1 joints


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load(npz_path: Path):
    d = np.load(npz_path)
    posed = d["posed_joints"]
    if posed.ndim == 4:
        posed = posed[0]
    root = d["root_positions"]
    if root.ndim == 3:
        root = root[0]
    return posed, root


def hand_traj(npz_path: Path, joint: int) -> np.ndarray:
    posed, _ = load(npz_path)
    return posed[:, joint, :]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "qa_runs/grab07_interaction_corpus")
    ap.add_argument("--seeds", type=int, default=6, help="distinct seeds per target")
    ap.add_argument("--targets", nargs="*", default=list(TARGETS))
    args = ap.parse_args()
    args.out = args.out.resolve()

    args.out.mkdir(parents=True, exist_ok=True)
    existing = []
    old_manifest_path = args.out / "manifest.json"
    if old_manifest_path.is_file():
        try:
            existing = json.loads(old_manifest_path.read_text()).get("clips", [])
        except Exception:
            existing = []
    manifest = {"schema": "just-dodge-grab07-interaction-corpus-v1", "model": MODEL,
                "duration_s": DURATION, "runtime_admitted": False,
                "conditioning": "genuine target-directed grab (no output masking)",
                "clips": list(existing)}

    for target in args.targets:
        prompt = TARGETS[target]
        tdir = args.out / target
        tdir.mkdir(parents=True, exist_ok=True)
        for k in range(args.seeds):
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
                posed, root = load(npz)
                rh = posed[:, HAND_R, :]
                lh = posed[:, HAND_L, :]
                # Forward reach (kimodo G1 forward = +Z of the posed joints).
                zmax = float(max(rh[:, 2].max(), lh[:, 2].max()))
                z_travel = float(np.abs(np.diff(rh[:, 2]) ).sum())
                # Forward lunge: root z displacement over the clip.
                root_dz = float(root[-1, 2] - root[0, 2])
                # Two-hand grip span at the peak-reach frame.
                peak = int(np.argmax((rh[:, 2] + lh[:, 2]) * 0.5))
                span = float(np.linalg.norm(rh[peak] - lh[peak]))
                # Real grab: hands reach forward (>0.3 m), there is forward hand
                # travel, a deliberate step/lunge, and a plausible grab span
                # (0.08–0.55 m — two hands closing on a torso, not T-pose apart).
                # Reach calibration: the contact-frame peak hand world-Z must be
                # within [0.52, 0.78]m of the 650mm engine plane. Clips that
                # massively overshoot (>0.78m) or undershoot (<0.52m) are
                # inconsistent teachers for the <=15mm-at-650mm gate.
                peak_reach = float(max(rh[peak, 2], lh[peak, 2]))
                if zmax > 0.30 and z_travel > 0.30 and root_dz > 0.05 \
                        and 0.08 < span < 0.55 and 0.52 <= peak_reach <= 0.78:
                    clip_ok = True
                    break
                npz.unlink(missing_ok=True)  # reject weak clip, retry
            if not clip_ok:
                print(f"WARN {target}/clip{k}: no strong grab after retries; skipping slot", file=sys.stderr)
                continue
            manifest["clips"].append({
                "target": target, "seed": seed, "path": str(npz.relative_to(ROOT)),
                "sha256": sha(npz.read_bytes()), "frames": int(posed.shape[0]),
                "reach_zmax_m": round(zmax, 4), "hand_z_travel_m": round(z_travel, 4),
                "root_lunge_dz_m": round(root_dz, 4), "grip_span_m": round(span, 4),
                "contact_frame": peak, "prompt": prompt,
            })
            print(f"  {target}/seed{seed}: frames={posed.shape[0]} zmax={zmax:.3f}m "
                  f"lunge_dz={root_dz:.3f}m span={span:.3f}m")

    # Distinctness: within each target, distinct seeds must produce distinct motion.
    failures = []
    seen = {}
    for c in manifest["clips"]:
        seen.setdefault(c["target"], []).append(c)
    for target in args.targets:
        clips = seen.get(target, [])
        if not clips:
            failures.append(f"{target}: no admitted clips after retries")
            print(f"  {target}: NO_CLIPS")
            continue
        if len(clips) < 2:
            print(f"  {target}: only {len(clips)} clip(s); distinctness vacuous")
            continue
        trajs = [hand_traj(ROOT / c["path"], HAND_R) for c in clips]
        L = min(t.shape[0] for t in trajs)
        trajs = [t[:L] for t in trajs]
        min_pair = min(
            float(np.abs(trajs[i] - trajs[j]).mean())
            for i in range(len(trajs)) for j in range(i + 1, len(trajs))
        )
        print(f"  {target}: min pairwise hand-traj diff = {min_pair*1000:.1f}mm ({len(clips)} clips)")
        if min_pair < 0.005:
            failures.append(f"{target}: seeds not distinct (min diff {min_pair*1000:.1f}mm)")

    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    n = len(manifest["clips"])
    print(f"GRAB07_INTERACTION_CORPUS clips={n} targets={len(args.targets)} seeds_per_target={args.seeds}")
    if failures:
        for f in failures:
            print(f"DISTINCTNESS_FAIL {f}", file=sys.stderr)
        return 1
    print("GRAB07_INTERACTION_CORPUS_DISTINCT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
