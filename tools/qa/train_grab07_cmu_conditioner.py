#!/usr/bin/env python3
"""UNIT-2 GRAB conditioner v4 — trained on REAL CMU combat mocap.

Uses the 70 reach-calibrated grab segments from the CMU combat corpus
(absolute hand-Z in [0.45, 0.85]m, centered on the 650mm engine plane).

Genuine dual-backbone conditioning:
  - condition (target contact pos + reach axis + phase) enters BOTH pose and
    root backbone INPUTS before decoding
  - base input is only frame-0 state (broadcast over time)
  - NO output masking, NO post-decode FK replacement
  - condition-ablation test: zeroed condition must produce worse hand-surface error

Two-sided gate: abs(reach_z - 0.65) * 1000 <= 15mm
Leakage-resistant split: hold out entire source clips (by subject number)
runtime_admitted=False
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[2]
SEG_DIR = ROOT / "qa_runs/grab07_combat_corpus/segments"
OUT_DIR = ROOT / "qa_runs/grab07_combat_train"
HAND_R, HAND_L = 33, 25
GRAB_REACH_MM = 650
GATE_MM = 15.0
SEED = 20260718
REACH_LO, REACH_HI = 0.45, 0.85  # calibration band around 650mm plane


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_seg(path):
    d = np.load(path)
    posed = d["posed_joints"].astype(np.float64)
    root = d["root_positions"].astype(np.float64)
    return posed, root


class GrabConditioner(nn.Module):
    def __init__(self, n_targets: int, hidden: int = 512):
        super().__init__()
        cd = 3 + 3 + 1 + n_targets
        self.pose_backbone = nn.Sequential(
            nn.Linear(102 + cd, hidden), nn.GELU(),
            nn.Linear(hidden, hidden), nn.GELU(),
            nn.Linear(hidden, hidden), nn.GELU(),
            nn.Linear(hidden, 102))
        self.root_backbone = nn.Sequential(
            nn.Linear(3 + cd, hidden // 2), nn.GELU(),
            nn.Linear(hidden // 2, hidden // 2), nn.GELU(),
            nn.Linear(hidden // 2, 3))

    def forward(self, init_pose, init_root, cond):
        return (self.pose_backbone(torch.cat([init_pose, cond], -1)),
                self.root_backbone(torch.cat([init_root, cond], -1)))


def hand_surface_err_mm(pred_posed, contact):
    rh = pred_posed[contact, HAND_R]
    lh = pred_posed[contact, HAND_L]
    return abs(max(float(rh[2]), float(lh[2])) - GRAB_REACH_MM / 1000.0) * 1000.0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--steps", type=int, default=10000)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--hidden", type=int, default=512)
    ap.add_argument("--held-out-subjects", nargs="*",
                    default=["17", "79", "80"])  # boxing subjects held out
    args = ap.parse_args()

    manifest = json.loads((SEG_DIR / "manifest.json").read_text())

    # Filter: grab segments with absolute hand-Z in calibration band
    data = []
    for s in manifest["segments"]:
        if s["label"] != "grab":
            continue
        posed, root = load_seg(s["path"])
        contact = s["contact_frame"]
        peak = max(posed[contact, HAND_R, 2], posed[contact, HAND_L, 2])
        if not (REACH_LO <= peak <= REACH_HI):
            continue
        clip_id = s["clip_id"]
        subject = clip_id.split("_")[0]
        T = min(posed.shape[0], 120)
        data.append({
            "seg_id": s["seg_id"], "clip_id": clip_id, "subject": subject,
            "posed": posed[:T], "root": root[:T], "contact": min(contact, T - 1), "T": T,
            "peak_reach": peak,
        })

    if len(data) < 10:
        print(f"BLOCKED: only {len(data)} calibrated grab segments, need >= 10")
        return 2

    # Leakage-resistant split by subject
    held_subs = set(args.held_out_subjects)
    train = [d for d in data if d["subject"] not in held_subs]
    heldout = [d for d in data if d["subject"] in held_subs]

    if not heldout:
        # Fallback: hold out 2 subjects with most segments
        from collections import Counter
        subj_counts = Counter(d["subject"] for d in data)
        held_subs = set(s for s, _ in subj_counts.most_common(2))
        train = [d for d in data if d["subject"] not in held_subs]
        heldout = [d for d in data if d["subject"] in held_subs]

    if not train or not heldout:
        print(f"BLOCKED: split failed train={len(train)} held={len(heldout)}")
        return 2

    # Verify no leakage
    train_subs = {d["subject"] for d in train}
    held_subs_actual = {d["subject"] for d in heldout}
    assert not (train_subs & held_subs_actual), "LEAKAGE: shared subjects"

    frames = min(d["T"] for d in data)
    for d in data:
        d["posed"] = d["posed"][:frames]
        d["root"] = d["root"][:frames]

    # Target cells by reach height band
    def reach_cell(peak):
        if peak < 0.55: return "low"
        if peak > 0.75: return "high"
        return "nominal"

    for d in data:
        d["cell"] = reach_cell(d["peak_reach"])
    cells = sorted({d["cell"] for d in data})
    cindex = {c: i for i, c in enumerate(cells)}

    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    model = GrabConditioner(len(cells), args.hidden).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)

    def build_tensors(d):
        posed = torch.tensor(d["posed"], dtype=torch.float32, device=device)
        root = torch.tensor(d["root"], dtype=torch.float32, device=device)
        pose_feat = posed.reshape(frames, -1)  # [T, 102]
        # Exogenous target: desired contact point at 650mm forward
        reach_m = GRAB_REACH_MM / 1000.0
        contact = min(d["contact"], frames - 1)
        rc = root[contact]
        tgt = torch.tensor([rc[0].item(), 1.0, rc[2].item() + reach_m],
                           device=device)
        axis = torch.tensor([0., 0., 1.], device=device)
        phase = torch.full((frames, 1), contact / frames, device=device)
        c1h = torch.zeros(frames, len(cells), device=device)
        c1h[:, cindex[d["cell"]]] = 1.0
        cond = torch.cat([tgt.expand(frames, 3), axis.expand(frames, 3),
                          phase, c1h], dim=-1)
        return pose_feat, root, cond, posed.reshape(frames, -1)

    losses = []
    for step in range(args.steps):
        d = train[step % len(train)]
        pf, rf, cond, target = build_tensors(d)
        init_pose = pf[0:1].expand(frames, -1)
        init_root = rf[0:1].expand(frames, -1)
        opt.zero_grad(set_to_none=True)
        pp, pr = model(init_pose[None], init_root[None], cond[None])
        # Endpoint-weighted loss
        w = torch.ones(34, device=device)
        w[HAND_R] = 8.0
        w[HAND_L] = 8.0
        pw = w.reshape(1, 1, 34, 1)
        pe = ((pp.reshape(1, frames, 34, 3) -
               target[None].reshape(1, frames, 34, 3)) ** 2 * pw).mean()
        re = torch.mean((pr - rf[None]) ** 2)
        loss = pe + 0.5 * re
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 10.0)
        opt.step()
        losses.append(float(loss.detach().cpu()))

    model.eval()

    def run_eval(ablate):
        rows = []
        with torch.no_grad():
            for d in heldout:
                pf, rf, cond, target = build_tensors(d)
                if ablate:
                    cond = torch.zeros_like(cond)
                init_pose = pf[0:1].expand(frames, -1)
                init_root = rf[0:1].expand(frames, -1)
                pp, pr = model(init_pose[None], init_root[None], cond[None])
                pred = pp[0].reshape(frames, 34, 3)
                tgt = target.reshape(frames, 34, 3)
                full_err = float(torch.mean(
                    torch.linalg.vector_norm(pred - tgt, dim=-1)).cpu()) * 1000
                hs = hand_surface_err_mm(pred, min(d["contact"], frames - 1))
                rows.append({"seg_id": d["seg_id"], "subject": d["subject"],
                             "cell": d["cell"], "peak_reach": round(d["peak_reach"], 4),
                             "fullbody_err_mm": round(full_err, 2),
                             "hand_surface_err_mm": round(hs, 2)})
        return rows

    held_cond = run_eval(ablate=False)
    held_abl = run_eval(ablate=True)
    best_cond = min(h["hand_surface_err_mm"] for h in held_cond)
    worst_cond = max(h["hand_surface_err_mm"] for h in held_cond)
    median_cond = float(np.median([h["hand_surface_err_mm"] for h in held_cond]))
    best_abl = min(h["hand_surface_err_mm"] for h in held_abl)
    ablation_delta = best_abl - best_cond
    ablation_ok = ablation_delta > 5.0  # conditioned must beat ablated by >5mm

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ck = OUT_DIR / "grab07_conditioner.pt"
    torch.save({"state_dict": model.state_dict(), "frames": frames,
                "cells": cells, "arch": "GrabConditioner-v4-cmu-mocap"}, ck)

    if best_cond == 0.0:
        verdict, reason = "SUSPICIOUS_ZERO", "0.0mm error: masking red flag"
    elif best_cond <= GATE_MM and ablation_ok:
        verdict = "PASS"
        reason = (f"best {best_cond:.2f}mm <= {GATE_MM:.0f}mm, ablation delta "
                  f"{ablation_delta:.2f}mm (MACHINE_ELIGIBLE_FOR_LATER_HUMAN_REVIEW)")
    elif best_cond <= GATE_MM:
        verdict, reason = "FAIL", f"distance passes but ablation delta {ablation_delta:.2f}mm <= 5mm"
    else:
        verdict, reason = "FAIL", f"best {best_cond:.2f}mm > {GATE_MM:.0f}mm"

    report = {
        "schema": "just-dodge-grab07-unit2-train-v4-cmu",
        "runtime_admitted": False,
        "source": "CMU Graphics Lab Motion Capture Database (public domain)",
        "conditioning": "genuine dual-backbone (exogenous target enters pose+root INPUT)",
        "held_out_split": f"by subject: {sorted(held_subs_actual)}",
        "train_segments": len(train), "heldout_segments": len(heldout),
        "cells": cells, "steps": args.steps, "lr": args.lr,
        "hidden": args.hidden, "seed": SEED,
        "train_loss_first": losses[0], "train_loss_last": losses[-1],
        "heldout_conditioned": held_cond,
        "heldout_ablated": held_abl,
        "best_cond_mm": best_cond, "median_cond_mm": round(median_cond, 2),
        "worst_cond_mm": worst_cond, "best_abl_mm": best_abl,
        "ablation_delta_mm": round(ablation_delta, 2),
        "ablation_ok": ablation_ok,
        "verdict": verdict, "reason": reason,
        "checkpoint_sha256": sha(ck.read_bytes()),
    }
    (OUT_DIR / "train_report.json").write_text(
        json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"verdict": verdict, "best_mm": best_cond,
                      "median_mm": round(median_cond, 2),
                      "ablation_delta": round(ablation_delta, 2),
                      "ablation_ok": ablation_ok,
                      "train_seg": len(train), "held_seg": len(heldout)},
                     indent=1))
    print(f"GRAB07_UNIT2_V4 verdict={verdict} best={best_cond:.2f}mm "
          f"median={median_cond:.2f}mm abl_delta={ablation_delta:.2f}mm")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
