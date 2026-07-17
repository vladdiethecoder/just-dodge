#!/usr/bin/env python3
"""Build the JD-RC0 vertical-Strike target/timing corpus (9 cells).

For each of 3 targets (high_left/center/right) x 3 timings (early/nominal/late)
this generates a distinct endpoint-spec variant of the vertical Strike and runs
the genuine optimization author (build_pvp005_r6_rotation_strike) to produce an
authored trajectory + proof. Conditioning is genuine: the target/timing is an
INPUT to the optimization author (via the spec keypose schedule), NOT a
post-decode replacement. Each cell carries full provenance and measured thresholds.

Held-out separation is by cell (target x timing), never by frames within a clip.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_SPEC = ROOT / "assets/qa/pvp005_ardy_action_endpoints_v4.json"
BUILDER = ROOT / "tools/qa/build_pvp005_r6_rotation_strike.py"
CONTACT_KEYPOSE_FRAME = 27  # strike apex (downward cut crosses center)
# Target X-offset (meters, character-root frame) applied to the contact keypose
# terminal pommel/tip. Vertical strike stays high (Y) and cuts down (tip drops).
TARGETS = {
    "high_left": -0.28,
    "high_center": 0.0,
    "high_right": 0.28,
}
# Timing shift (frames) applied to the contact keypose + contact event frame.
TIMINGS = {
    "early": -4,
    "nominal": 0,
    "late": +4,
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_variant_spec(target: str, timing: str) -> dict:
    spec = json.loads(BASE_SPEC.read_text(encoding="utf-8"))
    strike = spec["actions"]["strike"]
    dx = TARGETS[target]
    df = TIMINGS[timing]
    keyposes = copy.deepcopy(strike["keyposes"])
    for kp in keyposes:
        # Shift the contact (apex) keypose in X by target; shift all frames >=
        # contact in time by timing. Only the contact keypose carries the target
        # direction; recovery keyposes keep their relative shape.
        if kp["frame"] == CONTACT_KEYPOSE_FRAME:
            for axis_key in ("weapon_pommel_root_m", "weapon_tip_root_m"):
                kp[axis_key][0] = round(kp[axis_key][0] + dx, 7)
    # Re-time: shift ONLY the contact keypose frame and the contact event by
    # timing. The terminal (recovery) keypose must stay at the final frame so
    # keypose interpolation covers the whole horizon [0, frames).
    frames = spec["frames"]
    last_frame = keyposes[-1]["frame"]
    new_kps = []
    for kp in keyposes:
        nf = kp["frame"]
        if kp["frame"] == CONTACT_KEYPOSE_FRAME:
            nf = kp["frame"] + df
        nf = max(0, min(frames - 1, nf))
        nk = dict(kp)
        nk["frame"] = nf
        new_kps.append(nk)
    # Restore terminal keypose to the horizon end to preserve coverage.
    new_kps[-1]["frame"] = last_frame
    # Enforce strictly increasing ordering.
    for i in range(1, len(new_kps)):
        if new_kps[i]["frame"] <= new_kps[i - 1]["frame"]:
            new_kps[i]["frame"] = min(last_frame, new_kps[i - 1]["frame"] + 1)
    # If ordering forced the terminal frame down, restore it.
    if new_kps[-1]["frame"] != last_frame:
        new_kps[-1]["frame"] = last_frame
    strike["keyposes"] = new_kps
    strike["event_frames"]["weapon_contact_proposal"] = max(
        0, min(frames - 1, strike["event_frames"]["weapon_contact_proposal"] + df)
    )
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cells", nargs="*", default=None,
                        help="subset like high_left:early; default all 9")
    parser.add_argument("--dry-run", action="store_true", help="write specs only, no solve")
    args = parser.parse_args()

    base = json.loads(BASE_SPEC.read_text(encoding="utf-8"))
    ardy_commit = base["source_commit"]
    out_specs = args.out / "specs"
    out_specs.mkdir(parents=True, exist_ok=True)

    def rel(p: Path) -> str:
        try:
            return str(p.resolve().relative_to(ROOT))
        except ValueError:
            return str(p)

    manifest = {"schema": "just-dodge-p3-vertical-strike-corpus-v1",
                "base_spec_sha256": sha256_bytes(BASE_SPEC.read_bytes()),
                "ardy_source_commit": ardy_commit, "cells": []}

    wanted = set(args.cells) if args.cells else None
    for target in TARGETS:
        for timing in TIMINGS:
            cell = f"{target}:{timing}"
            if wanted and cell not in wanted:
                continue
            spec = build_variant_spec(target, timing)
            spec_path = out_specs / f"{target}_{timing}.json"
            # Preserve key order (no sort_keys): the materializer requires the
            # exact action set/order strike/block/grab and rejects extra keys.
            spec_path.write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8")
            entry = {"cell": cell, "target": target, "timing": timing,
                     "spec": rel(spec_path),
                     "spec_sha256": sha256_bytes(spec_path.read_bytes())}
            if not args.dry_run:
                traj = args.out / "trajectories" / f"{target}_{timing}.npz"
                proof = args.out / "proofs" / f"{target}_{timing}.json"
                traj.parent.mkdir(parents=True, exist_ok=True)
                proof.parent.mkdir(parents=True, exist_ok=True)
                proc = subprocess.run(
                    [sys.executable, str(BUILDER), "--spec", str(spec_path),
                     "--trajectory-output", str(traj), "--proof-output", str(proof)],
                    cwd=ROOT, capture_output=True, text=True)
                entry["builder_returncode"] = proc.returncode
                if proc.returncode == 0 and proof.is_file():
                    pdata = json.loads(proof.read_text(encoding="utf-8"))
                    entry["proof"] = rel(proof)
                    entry["trajectory"] = rel(traj)
                    entry["metrics"] = pdata["metrics"]
                    entry["status"] = "authored"
                else:
                    entry["status"] = "builder_failed"
                    entry["builder_stderr_tail"] = proc.stderr[-2000:]
            else:
                entry["status"] = "spec_only"
            manifest["cells"].append(entry)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    authored = sum(1 for c in manifest["cells"] if c["status"] == "authored")
    failed = sum(1 for c in manifest["cells"] if c["status"] == "builder_failed")
    print(f"P3_VERTICAL_STRIKE_CORPUS cells={len(manifest['cells'])} authored={authored} failed={failed}")
    print(f"MANIFEST={args.out / 'manifest.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
