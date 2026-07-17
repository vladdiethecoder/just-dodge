#!/usr/bin/env python3
"""Rigid weapon-socket/orientation genuine-conditioning proof on the authored r6 lane.

The authored r6 vertical-Strike lane is WEAPON-LOCKED (rigid 0.160 m grip, grip
angle <=0.14 deg), unlike the non-rigid kimodo teachers. This trains a genuine
conditioner on the 9 target/timing cells (target pos/axis + contact timing + cell-id
as INPUT, residual prediction, NO output masking), holding out one full cell by
identity, and measures on the unseen cell:

  - full-body joint error (mm)
  - right/left hand endpoint error at contact (mm)
  - weapon-socket error: two-hand span deviation from rigid 0.160 m (mm) -- valid here
    because the lane IS rigid
  - weapon orientation error at contact (degrees), from the predicted hand rotations

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
FRAMES = 52


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def rot6(rot: np.ndarray) -> np.ndarray:
    """[T,34,3,3] -> [T,34,6] first two columns (6D rotation repr)."""
    return np.concatenate([rot[..., 0], rot[..., 1]], axis=-1)


def mat_from_6d(v: np.ndarray) -> np.ndarray:
    a1, a2 = v[:3], v[3:6]
    b1 = a1 / (np.linalg.norm(a1) + 1e-9)
    b2 = a2 - np.dot(b1, a2) * b1
    b2 = b2 / (np.linalg.norm(b2) + 1e-9)
    b3 = np.cross(b1, b2)
    return np.stack([b1, b2, b3], axis=1)


class RigidConditioner(nn.Module):
    """Predicts full-body position residual + hand-rotation residual."""

    def __init__(self, n_cells: int = 9, hidden: int = 512):
        super().__init__()
        cond_dim = 3 + 3 + 1 + n_cells  # target pos + axis + contact-phase + cell-id
        in_dim = 105 + cond_dim
        self.body = nn.Sequential(
            nn.Linear(in_dim, hidden), nn.GELU(),
            nn.Linear(hidden, hidden), nn.GELU(),
            nn.Linear(hidden, 102),  # 34 joints * 3
        )
        self.rot = nn.Sequential(
            nn.Linear(in_dim, hidden), nn.GELU(),
            nn.Linear(hidden, hidden // 2), nn.GELU(),
            nn.Linear(hidden // 2, 12),  # 2 hands * 6D rotation
        )

    def forward(self, base_feat, cond):
        x = torch.cat([base_feat, cond], dim=-1)
        return self.body(x), self.rot(x)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lane", type=Path, default=ROOT / "qa_runs/p3_vertical_strike_corpus")
    ap.add_argument("--out", type=Path, default=ROOT / "qa_runs/p3_rigid_train")
    ap.add_argument("--steps", type=int, default=6000)
    ap.add_argument("--lr", type=float, default=7e-4)
    ap.add_argument("--held-out-cell", default="high_right_nominal")
    args = ap.parse_args()

    traj_dir = args.lane / "trajectories"
    cells = sorted(p.stem for p in traj_dir.glob("*.npz"))
    assert len(cells) == 9, cells
    cindex = {c: i for i, c in enumerate(cells)}

    data = {}
    for cell in cells:
        d = np.load(traj_dir / f"{cell}.npz")
        posed = d["posed_joints"].astype(np.float64)
        rot = d["global_rot_mats"].astype(np.float64)
        root = d["root_positions"].astype(np.float64)
        contact = int(np.argmin(posed[:, HAND_R, 1]))
        data[cell] = {"posed": posed, "rot": rot, "root": root, "contact": contact}

    heldout = [args.held_out_cell]
    train = [c for c in cells if c not in heldout]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(20260717)
    np.random.seed(20260717)
    model = RigidConditioner(len(cells)).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)

    def make_batch(cell):
        d = data[cell]
        posed = torch.tensor(d["posed"], dtype=torch.float32, device=device)
        root = torch.tensor(d["root"], dtype=torch.float32, device=device)
        rot = torch.tensor(rot6(d["rot"]), dtype=torch.float32, device=device)  # [T,34,6]
        base_feat = torch.cat([posed.reshape(FRAMES, -1), root], dim=-1)        # [T,105]
        hand = posed[d["contact"], HAND_R]
        pre = posed[max(0, d["contact"] - 6), HAND_R]
        axis = hand - pre
        axis = axis / (torch.linalg.vector_norm(axis) + 1e-9)
        phase = torch.full((FRAMES, 1), d["contact"] / FRAMES, device=device)
        cell_1h = torch.zeros(FRAMES, len(cells), device=device)
        cell_1h[:, cindex[cell]] = 1.0
        cond = torch.cat([hand.expand(FRAMES, 3), axis.expand(FRAMES, 3), phase, cell_1h], dim=-1)
        # hand rotation targets (both hands, 6D)
        hand_rot = torch.cat([rot[:, HAND_L], rot[:, HAND_R]], dim=-1)  # [T,12]
        return base_feat[None], cond[None], posed.reshape(FRAMES, -1)[None], hand_rot[None]

    losses = []
    for step in range(args.steps):
        cell = train[step % len(train)]
        base_feat, cond, body_t, rot_t = make_batch(cell)
        opt.zero_grad(set_to_none=True)
        pb, pr = model(base_feat, cond)
        pred_body = base_feat[..., :102] + pb
        pred_rot = rot_t + pr
        loss = torch.mean((pred_body - body_t) ** 2) + 0.1 * torch.mean((pred_rot - rot_t) ** 2)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 10.0)
        opt.step()
        losses.append(float(loss.detach().cpu()))

    model.eval()
    held = []
    with torch.no_grad():
        for cell in heldout:
            base_feat, cond, body_t, rot_t = make_batch(cell)
            pb, pr = model(base_feat, cond)
            pred = (base_feat[..., :102] + pb)[0].reshape(FRAMES, 34, 3)
            tgt = body_t[0].reshape(FRAMES, 34, 3)
            pred_rot = (rot_t + pr)[0].cpu().numpy()  # [T,12]
            tgt_rot = rot_t[0].cpu().numpy()
            d = data[cell]
            ci = d["contact"]
            full_err = float(torch.mean(torch.linalg.vector_norm(pred - tgt, dim=-1)).cpu()) * 1000.0
            rh_err = float(torch.linalg.vector_norm(pred[ci, HAND_R] - tgt[ci, HAND_R]).cpu()) * 1000.0
            lh_err = float(torch.linalg.vector_norm(pred[ci, HAND_L] - tgt[ci, HAND_L]).cpu()) * 1000.0
            span = torch.linalg.vector_norm(pred[:, HAND_R] - pred[:, HAND_L], dim=-1)
            socket_err = float(torch.abs(span - GRIP_SPAN_M).max().cpu()) * 1000.0
            # weapon orientation: right-hand rotation at contact
            prh = mat_from_6d(pred_rot[ci, 6:12])
            trh = mat_from_6d(tgt_rot[ci, 6:12])
            cos = float(np.clip((np.trace(prh.T @ trh) - 1.0) / 2.0, -1.0, 1.0))
            orient_deg = float(np.degrees(np.arccos(cos)))
            held.append({"cell": cell, "fullbody_err_mm": round(full_err, 2),
                         "right_hand_err_mm": round(rh_err, 2),
                         "left_hand_err_mm": round(lh_err, 2),
                         "socket_span_err_mm": round(socket_err, 2),
                         "weapon_orient_err_deg": round(orient_deg, 3)})

    args.out.mkdir(parents=True, exist_ok=True)
    ck = args.out / "rigid_conditioner.pt"
    torch.save({"state_dict": model.state_dict(), "cells": cells}, ck)
    report = {
        "schema": "just-dodge-p3-rigid-interaction-v1",
        "runtime_admitted": False,
        "lane": "authored r6 rigid-grip (weapon-locked)",
        "conditioning": "genuine (target pos/axis + contact timing + cell-id INPUT; no output masking)",
        "held_out_split": "by cell identity (one full target/timing cell held out)",
        "held_out_cell": args.held_out_cell,
        "train_cells": len(train), "heldout_cells": len(heldout),
        "steps": args.steps, "lr": args.lr,
        "train_loss_first": losses[0], "train_loss_last": losses[-1],
        "heldout_results": held,
        "checkpoint_sha256": sha(ck.read_bytes()),
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps(held, indent=1))
    h = held[0]
    print(f"P3_RIGID held_out={args.held_out_cell} full={h['fullbody_err_mm']:.2f}mm rh={h['right_hand_err_mm']:.2f}mm socket={h['socket_span_err_mm']:.2f}mm orient={h['weapon_orient_err_deg']:.3f}deg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
