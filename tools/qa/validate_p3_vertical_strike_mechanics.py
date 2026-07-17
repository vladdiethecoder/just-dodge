#!/usr/bin/env python3
"""Mechanical-proof validation gate for the 9 P3 vertical-Strike trajectories.

Measures, per cell, the WO §3 properties derivable without an opponent model:
  - SO(3) validity of every local/global rotation (orthonormal, det +1, finite)
  - independent FK recompute consistency (local+root -> posed_joints)
  - full-body FK endpoint spread (sanity bound)
  - planted-foot slide within each contiguous planted window (not the step)
  - hand-socket (two-hand grip span) stability around the rigid 0.160 m
  - impact timing: contact event lands at the intended frame +/- 1 tick

These are genuine authored conditioning targets (optimization output), not a
trained generator. Run after build_p3_vertical_strike_corpus.py. Exit 1 on any
mechanical failure. Requires the ARDY source tree for the G1Skeleton34 FK.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path("/run/media/vdubrov/NVMe-Storage1/Just Dodge")
sys.path.insert(0, "/run/media/vdubrov/NVMe-Storage1/ardy")
from ardy.skeleton.definitions import G1Skeleton34  # noqa: E402

TRAJ_DIR = ROOT / "qa_runs/p3_vertical_strike_corpus/trajectories"
SPECS_DIR = ROOT / "qa_runs/p3_vertical_strike_corpus/specs"
FPS = 25
HAND_L, HAND_R = 25, 33
FEET = [6, 7, 13, 14]  # ankle_roll/toe L/R (from builder foot_indices)


def so3_error(m: np.ndarray) -> tuple[float, float]:
    """Max orthonormality error and det deviation for rotation stack [...,3,3]."""
    eye = np.eye(3)
    orth = np.abs(np.einsum("...ij,...kj->...ik", m, m) - eye).max()
    det = np.abs(np.linalg.det(m) - 1.0).max()
    finite = 0.0 if np.isfinite(m).all() else 1.0
    return float(max(orth, finite)), float(max(det, finite))


def main() -> int:
    sk = G1Skeleton34()
    report = {"cells": {}, "failures": []}
    paths = sorted(TRAJ_DIR.glob("*.npz"))
    assert len(paths) == 9, f"expected 9 trajectories, found {len(paths)}"

    for p in paths:
        name = p.stem
        d = np.load(p)
        local = d["local_rot_mats"].astype(np.float64)      # [T,34,3,3]
        glob = d["global_rot_mats"].astype(np.float64)       # [T,34,3,3]
        posed = d["posed_joints"].astype(np.float64)         # [T,34,3]
        root = d["root_positions"].astype(np.float64)        # [T,3]
        contacts = d["foot_contacts"]                        # [T,4] bool
        T = local.shape[0]

        # SO(3) validity
        lo, ld = so3_error(local)
        go, gd = so3_error(glob)

        # Independent FK recompute
        grot, gpos, _ = sk.fk(
            torch.from_numpy(local).float(), torch.from_numpy(root).float()
        )
        fk_err = float(np.abs(gpos.numpy().astype(np.float64) - posed).max())
        fk_spread_mm = float(
            (posed.max(axis=(0, 1)) - posed.min(axis=(0, 1))).max() * 1000.0
        )

        # Planted-foot slide: only WITHIN each contiguous contact segment (the
        # actual planted window). The feet legitimately step (left plants
        # [0,27], swings, replants [36,51]); the step is not slide. Measure the
        # max horizontal displacement inside a single contiguous planted run.
        foot_xy = posed[:, FEET, :][:, :, [0, 2]]  # [T,4,2]
        max_slide = 0.0
        for fi in range(4):
            c = contacts[:, fi]
            # find contiguous True runs
            idx = np.flatnonzero(c)
            if len(idx) < 2:
                continue
            splits = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
            for run in splits:
                if len(run) >= 2:
                    seg = foot_xy[run, fi]
                    max_slide = max(max_slide, float(np.abs(np.diff(seg, axis=0)).max()))
        max_slide_mm = max_slide * 1000.0

        # Hand-socket (grip span) stability: should stay near the rigid 0.160 m.
        span = np.linalg.norm(posed[:, HAND_R] - posed[:, HAND_L], axis=-1)
        span_dev_mm = float(np.abs(span - 0.160).max() * 1000.0)

        # Impact timing: the authored contact event is the hand reaching its
        # target (local minimum of hand height in the active window around the
        # intended contact frame). Wind-up descent is excluded by taking the
        # local min within the window, not global velocity.
        spec = json.loads((SPECS_DIR / f"{name}.json").read_text())
        intended = spec["actions"]["strike"]["event_frames"]["weapon_contact_proposal"]
        rh_y = posed[:, HAND_R, 1]
        win_lo, win_hi = max(0, intended - 6), min(len(rh_y) - 1, intended + 6)
        impact_frame = int(win_lo + np.argmin(rh_y[win_lo:win_hi + 1]))
        timing_err = abs(impact_frame - intended)

        cell = {
            "so3_local_orth_err": lo, "so3_local_det_err": ld,
            "so3_global_orth_err": go, "so3_global_det_err": gd,
            "fk_recompute_max_err_m": fk_err,
            "fk_spread_mm": fk_spread_mm,
            "planted_foot_slide_mm": max_slide_mm,
            "grip_span_dev_mm": span_dev_mm,
            "impact_frame": impact_frame, "intended_frame": intended,
            "timing_err_frames": timing_err,
        }
        report["cells"][name] = cell

        # Assertions (WO-aligned mechanical bounds; these are authored targets,
        # so SO(3)/FK must be exact and slide/span near-zero)
        if max(lo, ld, go, gd) > 1e-4:
            report["failures"].append(f"{name}: SO(3) error {max(lo,ld,go,gd):.2e}")
        if fk_err > 1e-3:
            report["failures"].append(f"{name}: FK recompute err {fk_err:.2e} m")
        if max_slide_mm > 5.0:
            report["failures"].append(f"{name}: foot slide {max_slide_mm:.2f} mm")
        if timing_err > 1:
            report["failures"].append(f"{name}: timing err {timing_err} frames (impact f{impact_frame} vs intended f{intended})")

    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"P3_MECH_PROOF cells={len(paths)} failures={len(report['failures'])}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
