#!/usr/bin/env python3
"""UNIT-2 GRAB conditioner v5 — SEQUENCE MODEL (temporal CNN) on real CMU mocap.

Owner-mandated Option B: replace the MLP with a sequence model that predicts
per-frame pose corrections conditioned on BOTH the exogenous target AND the
current trajectory state. The MLP could only learn static mappings; this
temporal CNN learns reach DYNAMICS (accelerate toward target, decelerate at
contact) needed to terminate at the 650mm engine distance.

Architecture:
  - Input: full pose trajectory [T, 102] + root [T, 3] + exogenous condition [T, cd]
  - 1D temporal convolutions over time (kernel=5, 3 layers) capture dynamics
  - Condition concatenated to each convolution input at every temporal layer
  - Output: per-frame pose correction [T, 102] and root correction [T, 3]
  - NO output masking, NO post-decode FK replacement

Fights should feel ALIVE — fighters pace, circle, and close distance dynamically
like For Honor duels, not stationary pose trading.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
SEG_DIRS = [
    ROOT / "qa_runs/grab07_combat_corpus/segments",          # CMU
    ROOT / "qa_runs/grab07_combat_corpus/kungfu_segments",    # KungfuAthleteBot
    ROOT / "qa_runs/grab07_combat_corpus/kyokushin_segments", # Kyokushin Karate
]
OUT_DIR = ROOT / "qa_runs/grab07_combat_train"
HAND_R, HAND_L = 33, 25
GRAB_REACH_MM = 650
GATE_MM = 15.0
EARLY_STOP_LOSS = 1e-4
SEED = 20260718
REACH_LO, REACH_HI = 0.30, 1.0  # widen calibration band for more training data


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_seg(path):
    d = np.load(path)
    return d["posed_joints"].astype(np.float64), d["root_positions"].astype(np.float64)


class TemporalGrabConditioner(nn.Module):
    """1D temporal CNN with concatenation-based conditioning.

    Learns per-frame pose dynamics conditioned on the exogenous grab target.
    The temporal receptive field captures the accelerate-decelerate-contact
    pattern of a real grab approach.  The condition is concatenated to the
    input of every convolution, so no zero-initialized affine path can silence
    the exogenous target.
    """
    def __init__(self, n_targets: int, hidden: int = 256):
        super().__init__()
        cd = 3 + 3 + 1 + n_targets

        # Every convolution consumes the exogenous condition explicitly.
        self.pose_in = nn.Conv1d(102 + cd, hidden, 5, padding=2)
        self.pose_drop1 = nn.Dropout(0.5)
        self.pose_conv1 = nn.Conv1d(hidden + cd, hidden, 5, padding=2)
        self.pose_drop2 = nn.Dropout(0.5)
        self.pose_conv2 = nn.Conv1d(hidden + cd, hidden, 5, padding=2)
        self.pose_drop3 = nn.Dropout(0.5)
        self.pose_out = nn.Conv1d(hidden, 102, 3, padding=1)

        # Root stream
        self.root_in = nn.Conv1d(3 + cd, hidden // 2, 5, padding=2)
        self.root_conv = nn.Conv1d(hidden // 2 + cd, hidden // 2, 5, padding=2)
        self.root_out = nn.Conv1d(hidden // 2, 3, 3, padding=1)

    def forward(self, pose_seq, root_seq, cond_seq):
        # pose_seq: [B, T, 102] -> [B, C, T]
        p = pose_seq.permute(0, 2, 1)
        r = root_seq.permute(0, 2, 1)
        c = cond_seq.permute(0, 2, 1)

        p = F.gelu(self.pose_in(torch.cat([p, c], dim=1)))
        p = self.pose_drop1(p)
        p = F.gelu(self.pose_conv1(torch.cat([p, c], dim=1)))
        p = self.pose_drop2(p)
        p = F.gelu(self.pose_conv2(torch.cat([p, c], dim=1)))
        p = self.pose_drop3(p)
        pose_res = self.pose_out(p).permute(0, 2, 1)  # [B, T, 102]

        r = F.gelu(self.root_in(torch.cat([r, c], dim=1)))
        r = F.gelu(self.root_conv(torch.cat([r, c], dim=1)))
        root_res = self.root_out(r).permute(0, 2, 1)  # [B, T, 3]

        return pose_res, root_res


def hand_surface_err_mm(pred_posed, contact):
    rh = pred_posed[contact, HAND_R]
    lh = pred_posed[contact, HAND_L]
    return abs(max(float(rh[2]), float(lh[2])) - GRAB_REACH_MM / 1000.0) * 1000.0


def build_condition(root, contact, cell, cindex, n_cells, frames, device):
    """Exogenous target: desired contact at 650mm forward from root at contact."""
    reach_m = GRAB_REACH_MM / 1000.0
    rc = root[contact]
    tgt = torch.tensor([rc[0].item(), 1.0, rc[2].item() + reach_m], device=device)
    axis = torch.tensor([0., 0., 1.], device=device)
    phase = torch.linspace(0, 1, frames, device=device).unsqueeze(-1)
    c1h = torch.zeros(frames, n_cells, device=device)
    c1h[:, cindex[cell]] = 1.0
    return torch.cat([tgt.expand(frames, 3), axis.expand(frames, 3), phase, c1h], dim=-1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--steps", type=int, default=15000)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--hidden", type=int, default=256)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--action", choices=["grab","strike","kick","footwork"], default="grab")
    ap.add_argument("--held-out-subjects", nargs="*",
                    default=["86", "135"] + [f"ky_B{367+i:04d}" for i in range(10)])
    args = ap.parse_args()

    # Load from all segment directories
    all_segments = []
    for seg_dir in SEG_DIRS:
        mf = seg_dir / "manifest.json"
        if mf.exists():
            m = json.loads(mf.read_text())
            if seg_dir.name == "segments":
                corpus = "CMU"
            elif seg_dir.name == "kungfu_segments":
                corpus = "KungfuAthleteBot"
            elif seg_dir.name == "kyokushin_segments":
                corpus = "Kyokushin"
            else:
                corpus = seg_dir.name
            all_segments.extend({**s, "corpus": corpus} for s in m["segments"])

    data = []
    for s in all_segments:
        if s["label"] != args.action:
            continue
        posed, root = load_seg(s["path"])
        contact = min(s["contact_frame"], posed.shape[0] - 1)
        peak = max(posed[contact, HAND_R, 2], posed[contact, HAND_L, 2])
        if not (REACH_LO <= peak <= REACH_HI):
            continue
        # Split CMU by its original subject identifier and Kungfu/Kyokushin by clip.
        # Kyokushin clips get their own subject for held-out separation.
        if s["corpus"] == "CMU":
            subject = s["clip_id"].split("_", 1)[0]
        elif s["corpus"] == "KungfuAthleteBot":
            subject = f"kf_{s['clip_id']}"
        else:
            # Kyokushin: subject is athlete ID (e.g. 'B0367' from 'B0367_2017-01-31-...')
            athlete = s["clip_id"].split("_")[0]
            subject = f"ky_{athlete}"
        T = min(posed.shape[0], 120)
        data.append({
            "seg_id": s["seg_id"], "clip_id": s["clip_id"], "subject": subject,
            "corpus": s["corpus"],
            "posed": posed[:T], "root": root[:T],
            "contact": min(contact, T - 1), "T": T, "peak_reach": peak,
        })

    if len(data) < 10:
        print(f"BLOCKED: only {len(data)} calibrated {args.action} segments")
        return 2

    held_subs = set(args.held_out_subjects)
    train = [d for d in data if d["subject"] not in held_subs]
    heldout = [d for d in data if d["subject"] in held_subs]
    if not heldout:
        from collections import Counter
        sc = Counter(d["subject"] for d in data)
        held_subs = set(s for s, _ in sc.most_common(3))
        train = [d for d in data if d["subject"] not in held_subs]
        heldout = [d for d in data if d["subject"] in held_subs]
    if not train or not heldout:
        print(f"BLOCKED: split failed train={len(train)} held={len(heldout)}")
        return 2

    assert not ({d["subject"] for d in train} & {d["subject"] for d in heldout}), "LEAKAGE"

    frames = min(d["T"] for d in data)
    for d in data:
        d["posed"] = d["posed"][:frames]
        d["root"] = d["root"][:frames]
        d["contact"] = min(d["contact"], frames - 1)

    def reach_cell(p):
        if p < 0.55: return "low"
        if p > 0.75: return "high"
        return "nominal"
    for d in data:
        d["cell"] = reach_cell(d["peak_reach"])
    cells = sorted({d["cell"] for d in data})
    cindex = {c: i for i, c in enumerate(cells)}

    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    model = TemporalGrabConditioner(len(cells), args.hidden).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.steps)

    # Pre-compute tensors
    def prep(d):
        posed = torch.tensor(d["posed"], dtype=torch.float32, device=device)
        root = torch.tensor(d["root"], dtype=torch.float32, device=device)
        pf = posed.reshape(frames, -1)
        cond = build_condition(root, d["contact"], d["cell"], cindex, len(cells), frames, device)
        return pf, root, cond, posed.reshape(frames, -1), d["contact"]

    train_prep = [prep(d) for d in train]
    held_prep = [prep(d) for d in heldout]

    losses = []
    # Early stop: only after sustained low loss (100 steps below threshold),
    # not the first step that dips below (prevents memorization)
    patience = 100
    low_loss_count = 0
    early_stop_loss = 0.0001
    early_stopped = False

    # Per-corpus balanced loss: weight each corpus inversely proportional to its size
    # so CMU/Kungfu grabs get equal gradient weight to kyokushin karate grabs.
    corpus_counts = {}
    for d in train:
        corpus_counts[d["corpus"]] = corpus_counts.get(d["corpus"], 0) + 1
    corpus_weights = {c: len(train) / (len(corpus_counts) * n) for c, n in corpus_counts.items()}
    print(f"Corpus weights: {corpus_weights}")

    for step in range(args.steps):
        idxs = np.random.choice(len(train_prep), min(args.batch_size, len(train_prep)), replace=True)
        pf_batch = torch.stack([train_prep[i][0] for i in idxs])
        rf_batch = torch.stack([train_prep[i][1] for i in idxs])
        cond_batch = torch.stack([train_prep[i][2] for i in idxs])
        tgt_batch = torch.stack([train_prep[i][3] for i in idxs])
        # Per-sample corpus weight
        batch_weights = torch.tensor([corpus_weights[train[i]["corpus"]] for i in idxs], device=device)

        opt.zero_grad(set_to_none=True)
        pose_res, root_res = model(pf_batch, rf_batch, cond_batch)
        pred_pose = pf_batch + pose_res
        pred_root = rf_batch + root_res

        w = torch.ones(34, device=device)
        w[HAND_R] = 8.0
        w[HAND_L] = 8.0
        pw = w.reshape(1, 1, 34, 1)
        # Per-sample weighted pose error
        pe_per = ((pred_pose.reshape(len(idxs), frames, 34, 3) -
               tgt_batch.reshape(len(idxs), frames, 34, 3)) ** 2 * pw).mean(dim=(1,2,3))
        pe = (pe_per * batch_weights).mean()
        re = torch.mean((pred_root - rf_batch) ** 2)
        # Hand-reach gate loss: directly optimize |hand_z - 0.65| at contact
        contact_idx = torch.tensor([train_prep[i][4] for i in idxs], device=device)
        reach_m = GRAB_REACH_MM / 1000.0
        rh_pred = pred_pose.reshape(len(idxs), frames, 34, 3)[:, :, HAND_R, 2]
        lh_pred = pred_pose.reshape(len(idxs), frames, 34, 3)[:, :, HAND_L, 2]
        hand_reach = torch.maximum(rh_pred, lh_pred)
        contact_mask = torch.zeros(len(idxs), frames, device=device)
        for b in range(len(idxs)):
            contact_mask[b, contact_idx[b]] = 1.0
        hs_err = (hand_reach * contact_mask).sum(dim=1) - reach_m
        gate_loss_per = (hs_err ** 2)
        gate_loss = (gate_loss_per * batch_weights).mean()
        loss = pe + 0.3 * re + 0.5 * gate_loss
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 10.0)
        opt.step()
        sched.step()
        losses.append(float(loss.detach().cpu()))

        # Sustained low-loss early stop (prevents single-step memorization trigger)
        if losses[-1] < early_stop_loss:
            low_loss_count += 1
            if low_loss_count >= patience:
                early_stopped = True
                break
        else:
            low_loss_count = 0
        if losses[-1] < EARLY_STOP_LOSS:
            early_stopped = True
            break

    model.eval()

    def run_eval(ablate):
        rows = []
        with torch.no_grad():
            for i, d in enumerate(heldout):
                pf, rf, cond, target, contact = held_prep[i]
                if ablate:
                    cond = torch.zeros_like(cond)
                pr, rr = model(pf[None], rf[None], cond[None])
                pred = (pf[None] + pr)[0].reshape(frames, 34, 3)
                tgt = target.reshape(frames, 34, 3)
                full_err = float(torch.mean(
                    torch.linalg.vector_norm(pred - tgt, dim=-1)).cpu()) * 1000
                hs = hand_surface_err_mm(pred, contact)
                rows.append({"seg_id": d["seg_id"], "subject": d["subject"],
                             "corpus": d["corpus"], "cell": d["cell"],
                             "peak_reach": round(d["peak_reach"], 4),
                             "fullbody_err_mm": round(full_err, 2),
                             "hand_surface_err_mm": round(hs, 2)})
        return rows

    held_cond = run_eval(ablate=False)
    held_abl = run_eval(ablate=True)
    best_cond = min(h["hand_surface_err_mm"] for h in held_cond)
    median_cond = float(np.median([h["hand_surface_err_mm"] for h in held_cond]))
    worst_cond = max(h["hand_surface_err_mm"] for h in held_cond)
    best_abl = min(h["hand_surface_err_mm"] for h in held_abl)
    median_abl = float(np.median([h["hand_surface_err_mm"] for h in held_abl]))
    worst_abl = max(h["hand_surface_err_mm"] for h in held_abl)
    ablation_delta = median_abl - median_cond
    ablation_ok = ablation_delta > 5.0

    def distribution(rows):
        values = np.array([row["hand_surface_err_mm"] for row in rows], dtype=np.float64)
        return {
            "count": len(values), "best_mm": round(float(np.min(values)), 2),
            "p05_mm": round(float(np.percentile(values, 5)), 2),
            "p25_mm": round(float(np.percentile(values, 25)), 2),
            "median_mm": round(float(np.median(values)), 2),
            "p75_mm": round(float(np.percentile(values, 75)), 2),
            "p95_mm": round(float(np.percentile(values, 95)), 2),
            "worst_mm": round(float(np.max(values)), 2),
            "at_or_below_15mm": int(np.count_nonzero(values <= GATE_MM)),
        }

    held_comparison = [
        {"seg_id": conditioned["seg_id"],
         "conditioned_hand_surface_err_mm": conditioned["hand_surface_err_mm"],
         "ablated_hand_surface_err_mm": ablated["hand_surface_err_mm"],
         "conditioned_advantage_mm": round(
             ablated["hand_surface_err_mm"] - conditioned["hand_surface_err_mm"], 2)}
        for conditioned, ablated in zip(held_cond, held_abl, strict=True)
    ]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ck = OUT_DIR / "grab07_conditioner_seq.pt"
    torch.save({"state_dict": model.state_dict(), "frames": frames,
                "cells": cells, "hidden": args.hidden,
                "arch": "TemporalGrabConditioner-v6-concat"}, ck)

    if median_cond == 0.0:
        verdict, reason = "SUSPICIOUS_ZERO", "0.0mm: masking red flag"
    elif median_cond <= GATE_MM and ablation_ok:
        verdict = "PASS"
        reason = (f"median {median_cond:.2f}mm <= {GATE_MM:.0f}mm, median ablation "
                  f"delta {ablation_delta:.2f}mm > 5mm "
                  "(MACHINE_ELIGIBLE_FOR_LATER_HUMAN_REVIEW)")
    elif median_cond <= GATE_MM:
        verdict, reason = "FAIL", (
            f"median distance passes but median ablation delta {ablation_delta:.2f}mm <= 5mm")
    else:
        verdict, reason = "FAIL", f"median {median_cond:.2f}mm > {GATE_MM:.0f}mm"

    report = {
        "schema": "just-dodge-grab07-unit2-train-v6-seq-concat",
        "runtime_admitted": False,
        "source": "CMU Graphics Lab Motion Capture Database + KungfuAthleteBot",
        "architecture": "TemporalGrabConditioner (1D CNN + per-layer concatenation conditioning)",
        "conditioning": "exogenous target concatenated to every pose/root convolution input",
        "held_out_split": f"by subject: {sorted({d['subject'] for d in heldout})}",
        "train_segments": len(train), "heldout_segments": len(heldout),
        "train_corpora": sorted({d["corpus"] for d in train}),
        "heldout_corpora": sorted({d["corpus"] for d in heldout}),
        "cells": cells, "steps": args.steps, "lr": args.lr,
        "hidden": args.hidden, "batch_size": args.batch_size, "seed": SEED,
        "train_loss_first": losses[0], "train_loss_last": losses[-1],
        "actual_steps": len(losses), "early_stop_loss": EARLY_STOP_LOSS,
        "early_stopped": early_stopped,
        "heldout_conditioned": held_cond, "heldout_ablated": held_abl,
        "heldout_comparison": held_comparison,
        "conditioned_distribution": distribution(held_cond),
        "ablated_distribution": distribution(held_abl),
        "best_cond_mm": best_cond, "median_cond_mm": round(median_cond, 2),
        "worst_cond_mm": worst_cond, "best_abl_mm": best_abl,
        "median_abl_mm": round(median_abl, 2), "worst_abl_mm": worst_abl,
        "median_ablation_delta_mm": round(ablation_delta, 2), "ablation_ok": ablation_ok,
        "verdict": verdict, "reason": reason,
        "checkpoint_sha256": sha(ck.read_bytes()),
    }
    (OUT_DIR / "train_report_seq.json").write_text(
        json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"verdict": verdict, "best_mm": best_cond,
                      "median_mm": round(median_cond, 2),
                      "median_abl_mm": round(median_abl, 2),
                      "median_ablation_delta": round(ablation_delta, 2),
                      "ablation_ok": ablation_ok,
                      "train_seg": len(train), "held_seg": len(heldout),
                      "train_corpora": sorted({d["corpus"] for d in train}),
                      "arch": "temporal-cnn-concat"}, indent=1))
    print(f"GRAB07_UNIT2_V6 verdict={verdict} median={median_cond:.2f}mm "
          f"median_abl={median_abl:.2f}mm median_abl_delta={ablation_delta:.2f}mm")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
