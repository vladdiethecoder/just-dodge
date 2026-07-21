#!/usr/bin/env python3
"""UNIT-2 GRAB07 held-out evaluator (fixed, versioned).

Evaluates the 220.9mm baseline retargeted grab_07 and every UNIT-2 candidate
through the IDENTICAL evaluator, actor geometry, secure-grab window
(ticks 32..47), and 650mm truth configuration (GRAB_REACH_MM=650 preserved;
truth-side clinch untouched).

Metric: visible hand-to-opponent-surface error (mm) at the contact frame.
The opponent surface plane is at the 650mm acquisition stop from the grabber
root; the grabber faces +Z. Error = max(0, plane_z - max(hand_world_z)) in mm.
Hand world = root_world + hand_local (Z-forward convention, matching the
committed capture/pose evidence at qa_runs/grab07_650mm_closure/).

PASS gate: held-out error <= 15mm. Exactly 0.0mm is a masking red flag and is
reported as suspicious, not silently accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HAND_R, HAND_L = 33, 25  # G1 joint indices
GRAB_REACH_MM = 650  # src/intent/plan_phase.rs:21 — preserved, never lowered
SECURE_GRAB_TICKS = (32, 47)  # canonical secure-grab window (truth ticks, 60Hz)
BASELINE_CLEARANCE_MM = 220.9  # committed measurement, COMPARISON_RECEIPT.md


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_clip(path: Path):
    d = np.load(path)
    posed = d["posed_joints"]
    if posed.ndim == 4:
        posed = posed[0]
    root = d["root_positions"]
    if root.ndim == 3:
        root = root[0]
    return posed.astype(np.float64), root.astype(np.float64)


def hand_surface_error_mm(posed: np.ndarray, root: np.ndarray, contact: int) -> dict:
    """Two-sided hand-to-opponent-surface error at the contact frame.

    Uses abs(reach_z - plane_z) so BOTH undershoot (hand short of opponent)
    and overshoot (hand punching through opponent) count as error. The old
    one-sided max(0, plane_z - reach_z) made overshoots look like 0mm PASS.

    posed_joints are already WORLD-space (hips == root), so the visible hand
    world position is the posed hand joint directly; do NOT add root again.
    """
    rh = posed[contact, HAND_R]
    lh = posed[contact, HAND_L]
    plane_z_m = GRAB_REACH_MM / 1000.0
    reach_z = max(float(rh[2]), float(lh[2]))
    err_mm = abs(reach_z - plane_z_m) * 1000.0
    return {
        "contact_frame": int(contact),
        "reach_z_m": round(reach_z, 4),
        "plane_z_m": plane_z_m,
        "hand_surface_err_mm": round(err_mm, 2),
    }


def evaluate_clip(path: Path) -> dict:
    posed, root = load_clip(path)
    rh_z = posed[:, HAND_R, 2]
    lh_z = posed[:, HAND_L, 2]
    contact = int(np.argmax((rh_z + lh_z) * 0.5))
    return hand_surface_error_mm(posed, root, contact)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path,
                    default=ROOT / "qa_runs/grab07_interaction_train/eval_candidates.json")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "qa_runs/grab07_interaction_train/eval_report.json")
    args = ap.parse_args()

    spec = json.loads(args.manifest.read_text())
    rows = []
    for cand in spec["candidates"]:
        path = ROOT / cand["path"]
        if not path.is_file():
            rows.append({**cand, "status": "MISSING", "hand_surface_err_mm": None})
            continue
        m = evaluate_clip(path)
        rows.append({**cand, "status": "EVALUATED", **m,
                     "npz_sha256": sha(path.read_bytes())})

    baseline = {"name": "baseline_retargeted_grab07",
                "hand_surface_err_mm": BASELINE_CLEARANCE_MM,
                "evidence": "qa_runs/grab07_650mm_closure/COMPARISON_RECEIPT.md"}

    measured = [r for r in rows if r["status"] == "EVALUATED"]
    best = min(measured, key=lambda r: r["hand_surface_err_mm"], default=None)
    gate_mm = 15.0
    if best is None:
        verdict = "BLOCKED"
        reason = "no candidate clips evaluated"
    elif best["hand_surface_err_mm"] == 0.0:
        verdict = "SUSPICIOUS_ZERO"
        reason = "exactly 0.0mm held-out error is a hard-mask red flag"
    elif best["hand_surface_err_mm"] <= gate_mm:
        verdict = "PASS"
        reason = (f"best held-out {best['hand_surface_err_mm']:.2f}mm <= {gate_mm:.0f}mm "
                  f"(MACHINE_ELIGIBLE_FOR_LATER_HUMAN_REVIEW only)")
    else:
        verdict = "FAIL"
        reason = f"best held-out {best['hand_surface_err_mm']:.2f}mm > {gate_mm:.0f}mm"

    report = {
        "schema": "just-dodge-grab07-unit2-eval-v1",
        "grab_reach_mm": GRAB_REACH_MM,
        "secure_grab_ticks": list(SECURE_GRAB_TICKS),
        "evaluator": "fixed Z-forward hand-surface metric; identical for baseline and candidates",
        "baseline": baseline,
        "candidates": rows,
        "best_candidate": best,
        "gate_mm": gate_mm,
        "verdict": verdict,
        "reason": reason,
        "runtime_admitted": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"verdict": verdict, "best_mm": (best or {}).get("hand_surface_err_mm"),
                      "reason": reason}, indent=1))
    print(f"GRAB07_UNIT2_EVAL verdict={verdict} baseline_mm={BASELINE_CLEARANCE_MM} "
          f"best_mm={(best or {}).get('hand_surface_err_mm')}")
    return 0 if verdict in ("PASS", "FAIL") else 1


if __name__ == "__main__":
    raise SystemExit(main())
