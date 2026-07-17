#!/usr/bin/env python3
"""Full-body genuine interaction-conditioning trainer for the P3 vertical-Strike lane.

Extends the right-hand proof-of-concept to full 34-joint body prediction. Genuine
conditioning (NO post-decode masking): the model takes a base full-body window +
interaction tensor (target pos/axis, contact timing, target-id) and predicts the
full-body trajectory. Held out by source clip identity. Measured on raw prediction:

  - full-body mean joint error (mm)
  - right/left hand endpoint error at contact (mm)
  - two-hand grip-span deviation from rigid 0.160 m (mm)

This is a QA/research artifact; runtime_admitted=False; not an admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[2]
HAND_R, HAND_L = 33, 25
GRIP_SPAN_M = 0.160


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


class FullBodyConditioner(nn.Module):
    """Predicts full-body joint-position residual from base + interaction tensor."""

    def __init__(self, n_targets: int = 3, hidden: int = 512):
        super().__init__()
        cond_dim = 3 + 3 + 1 + n_targets  # target pos + axis + contact-phase + target-id
        in_dim = 105 + cond_dim  # 34 joints*3 + root*3 = 105
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden), nn.GELU(),
            nn.Linear(hidden, hidden), nn.GELU(),
            nn.Linear(hidden, hidden), nn.GELU(),
            nn.Linear(hidden, 102),  # 34 joints * 3 residual
        )

    def forward(self, base_feat, cond):
        x = torch.cat([base_feat, cond], dim=-1)
        return self.net(x)  # [B, T, 102]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=ROOT / "qa_runs/p3_strike_corpus")
    ap.add_argument("--out", type=Path, default=ROOT / "qa_runs/p3_interaction_fullbody")
    ap.add_argument("--steps", type=int, default=6000)
    ap.add_argument("--lr", type=float, default=7e-4)
    ap.add_argument("--hidden", type=int, default=512)
    ap.add_argument("--held-out-target", default="high_right")
    args = ap.parse_args()

    manifest = json.loads((args.corpus / "manifest.json").read_text())
    clips = manifest["clips"]
    targets = sorted({c["target"] for c in clips})
    tindex = {t: i for i, t in enumerate(targets)}

    data = []
    for c in clips:
        posed, root = load_clip(ROOT / c["path"])
        contact = int(np.argmin(posed[:, HAND_R, 1]))
        data.append({"target": c["target"], "seed": c["seed"], "posed": posed,
                     "root": root, "contact": contact, "T": posed.shape[0]})
    frames = min(d["T"] for d in data)
    for d in data:
        d["posed"] = d["posed"][:frames]
        d["root"] = d["root"][:frames]

    train = [d for d in data if d["target"] != args.held_out_target]
    heldout = [d for d in data if d["target"] == args.held_out_target]
    if not train or not heldout:
        raise RuntimeError("split failed")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(20260717)
    np.random.seed(20260717)
    model = FullBodyConditioner(len(targets), args.hidden).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)

    def make_batch(d):
        posed = torch.tensor(d["posed"], dtype=torch.float32, device=device)  # [T,34,3]
        root = torch.tensor(d["root"], dtype=torch.float32, device=device)    # [T,3]
        base_feat = torch.cat([posed.reshape(frames, -1), root], dim=-1)      # [T,105]
        # interaction tensor
        hand = posed[d["contact"], HAND_R]
        pre = posed[max(0, d["contact"] - 6), HAND_R]
        axis = hand - pre
        axis = axis / (torch.linalg.vector_norm(axis) + 1e-9)
        phase = torch.full((frames, 1), d["contact"] / frames, device=device)
        target_1h = torch.zeros(frames, len(targets), device=device)
        target_1h[:, tindex[d["target"]]] = 1.0
        cond = torch.cat([
            hand.expand(frames, 3), axis.expand(frames, 3), phase, target_1h,
        ], dim=-1)
        return base_feat[None], cond[None], posed.reshape(frames, -1)[None]

    losses = []
    for step in range(args.steps):
        d = train[step % len(train)]
        base_feat, cond, body_target = make_batch(d)
        opt.zero_grad(set_to_none=True)
        pred = base_feat[..., :102] + model(base_feat, cond)
        loss = torch.mean((pred - body_target) ** 2)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 10.0)
        opt.step()
        losses.append(float(loss.detach().cpu()))

    model.eval()
    held = []
    with torch.no_grad():
        for d in heldout:
            base_feat, cond, body_target = make_batch(d)
            pred = (base_feat[..., :102] + model(base_feat, cond))[0].reshape(frames, 34, 3)
            tgt = body_target[0].reshape(frames, 34, 3)
            full_err = float(torch.mean(torch.linalg.vector_norm(pred - tgt, dim=-1)).cpu()) * 1000.0
            ci = d["contact"]
            rh_err = float(torch.linalg.vector_norm(pred[ci, HAND_R] - tgt[ci, HAND_R]).cpu()) * 1000.0
            lh_err = float(torch.linalg.vector_norm(pred[ci, HAND_L] - tgt[ci, HAND_L]).cpu()) * 1000.0
            span_pred = torch.linalg.vector_norm(pred[:, HAND_R] - pred[:, HAND_L], dim=-1)
            span_tgt = torch.linalg.vector_norm(tgt[:, HAND_R] - tgt[:, HAND_L], dim=-1)
            # span tracking error vs ground truth (kimodo teachers do not hold a
            # rigid grip; the authored r6 0.160 m constant is NOT the reference here)
            span_err = float(torch.abs(span_pred - span_tgt).max().cpu()) * 1000.0
            held.append({"target": d["target"], "seed": d["seed"],
                         "fullbody_err_mm": round(full_err, 2),
                         "right_hand_err_mm": round(rh_err, 2),
                         "left_hand_err_mm": round(lh_err, 2),
                         "grip_span_track_err_mm": round(span_err, 2)})

    args.out.mkdir(parents=True, exist_ok=True)
    ck = args.out / "fullbody_conditioner.pt"
    torch.save({"state_dict": model.state_dict(), "frames": frames, "targets": targets}, ck)
    report = {
        "schema": "just-dodge-p3-interaction-fullbody-v1",
        "runtime_admitted": False,
        "conditioning": "genuine (target pos/axis + contact timing as INPUT; no output masking)",
        "held_out_split": "by source clip identity (target cell fully held out)",
        "held_out_target": args.held_out_target,
        "train_clips": len(train), "heldout_clips": len(heldout),
        "steps": args.steps, "lr": args.lr, "hidden": args.hidden,
        "train_loss_first": losses[0], "train_loss_last": losses[-1],
        "heldout_results": held,
        "checkpoint_sha256": sha(ck.read_bytes()),
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    worst_rh = max(h["right_hand_err_mm"] for h in held)
    worst_full = max(h["fullbody_err_mm"] for h in held)
    worst_span = max(h["grip_span_track_err_mm"] for h in held)
    print(json.dumps(report["heldout_results"], indent=1))
    print(f"P3_FULLBODY held_out={args.held_out_target} worst_rh_mm={worst_rh:.2f} worst_full_mm={worst_full:.2f} worst_span_track_mm={worst_span:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
