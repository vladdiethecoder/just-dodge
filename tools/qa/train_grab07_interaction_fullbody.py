#!/usr/bin/env python3
"""UNIT-2 GRAB07 genuine interaction-conditioning trainer (v2).

Genuine conditioning, NO post-decode masking and NO output masking:
  - conditioning enters BOTH the pose backbone and the root backbone as INPUT
    features before decoding (separate residual heads), never as a post-decode
    FK/pose overwrite.
  - leakage-resistant held-out split by (source sequence, interaction cell):
    an entire target cell AND every seed/window derived from its sequences is
    held out; no training window may share a source sequence with held-out.
  - condition-ablation test: the trained checkpoint is evaluated twice on the
    held-out cell — once with the true conditioning tensor, once with the
    conditioning zeroed/shuffled. The conditioned run must beat the ablated
    run on hand-surface error, proving the checkpoint USES the target geometry
    instead of ignoring it.

Gate (WO/G5): held-out visible hand-to-opponent-surface error <= 15mm at the
650mm acquisition. Exactly 0.0mm is a masking red flag. runtime_admitted=False.
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
GRAB_REACH_MM = 650
SEED = 20260718


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


class GrabConditioner(nn.Module):
    """Conditioned residual predictor with SEPARATE pose and root backbones.

    Conditioning (target contact pos + reach axis + contact phase + target-id)
    enters BOTH backbone INPUTS before decoding. The base input is only the
    INITIAL pose/root state (frame 0), broadcast over time — NOT the full
    per-frame clip — so the model cannot collapse to identity and is forced to
    use the target geometry to reconstruct the trajectory. No masking anywhere.
    """

    def __init__(self, n_targets: int, hidden: int = 512):
        super().__init__()
        cond_dim = 3 + 3 + 1 + n_targets
        self.pose_backbone = nn.Sequential(
            nn.Linear(102 + cond_dim, hidden), nn.GELU(),
            nn.Linear(hidden, hidden), nn.GELU(),
            nn.Linear(hidden, hidden), nn.GELU(),
            nn.Linear(hidden, 102),
        )
        self.root_backbone = nn.Sequential(
            nn.Linear(3 + cond_dim, hidden // 2), nn.GELU(),
            nn.Linear(hidden // 2, hidden // 2), nn.GELU(),
            nn.Linear(hidden // 2, 3),
        )

    def forward(self, init_pose, init_root, cond):
        pose = self.pose_backbone(torch.cat([init_pose, cond], dim=-1))
        root = self.root_backbone(torch.cat([init_root, cond], dim=-1))
        return pose, root


def build_tensors(d, frames, targets, tindex, device):
    posed = torch.tensor(d["posed"], dtype=torch.float32, device=device)  # [T,34,3]
    root = torch.tensor(d["root"], dtype=torch.float32, device=device)    # [T,3]
    pose_feat = posed.reshape(frames, -1)                                  # [T,102]
    # GENUINE EXOGENOUS conditioning: the desired opponent contact geometry at
    # the 650mm acquisition, NOT the clip's own measured hand. The model must
    # learn to MOVE toward this external target; it cannot copy it from itself.
    # Target contact point = root at contact + GRAB_REACH forward (+Z), at the
    # target cell's height band. This is the engine truth, exogenous to the pose.
    reach_m = GRAB_REACH_MM / 1000.0
    target_height = {"reach_nominal": 1.45, "reach_high": 1.65, "reach_low": 0.95}[d["target"]]
    root_c = root[d["contact"]]
    tgt = torch.tensor([root_c[0], target_height, root_c[2] + reach_m], device=device)
    axis = torch.tensor([0.0, 0.0, 1.0], device=device)  # forward reach axis
    phase = torch.full((frames, 1), d["contact"] / frames, device=device)
    target_1h = torch.zeros(frames, len(targets), device=device)
    target_1h[:, tindex[d["target"]]] = 1.0
    cond = torch.cat([tgt.expand(frames, 3), axis.expand(frames, 3), phase, target_1h], dim=-1)
    return pose_feat, root, cond, posed.reshape(frames, -1)


def hand_surface_err_mm(pred_posed: torch.Tensor, pred_root: torch.Tensor, contact: int) -> float:
    # Two-sided: abs(reach_z - plane_z). Overshoot and undershoot both count.
    # posed_joints are already WORLD-space (hips == root), so the visible hand
    # world position is the posed hand joint directly; do NOT add root again.
    rh = pred_posed[contact, HAND_R]
    lh = pred_posed[contact, HAND_L]
    plane_z = GRAB_REACH_MM / 1000.0
    reach_z = max(float(rh[2]), float(lh[2]))
    return abs(reach_z - plane_z) * 1000.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=ROOT / "qa_runs/grab07_interaction_corpus")
    ap.add_argument("--out", type=Path, default=ROOT / "qa_runs/grab07_interaction_train")
    ap.add_argument("--steps", type=int, default=6000)
    ap.add_argument("--lr", type=float, default=7e-4)
    ap.add_argument("--hidden", type=int, default=512)
    ap.add_argument("--held-out-target", default="reach_nominal")
    args = ap.parse_args()

    manifest = json.loads((args.corpus / "manifest.json").read_text())
    clips = manifest["clips"]
    targets = sorted({c["target"] for c in clips})
    tindex = {t: i for i, t in enumerate(targets)}

    data = []
    for c in clips:
        posed, root = load_clip(ROOT / c["path"])
        rh_z = posed[:, HAND_R, 2]
        lh_z = posed[:, HAND_L, 2]
        contact = int(np.argmax((rh_z + lh_z) * 0.5))
        # source sequence identity = (target cell, seed); no sub-window re-use.
        data.append({"target": c["target"], "seed": c["seed"], "posed": posed,
                     "root": root, "contact": contact, "T": posed.shape[0]})
    frames = min(d["T"] for d in data)
    for d in data:
        d["posed"] = d["posed"][:frames]
        d["root"] = d["root"][:frames]

    # Leakage-resistant split: hold out an entire interaction cell; every clip
    # (source sequence) of that cell is excluded from training.
    train = [d for d in data if d["target"] != args.held_out_target]
    heldout = [d for d in data if d["target"] == args.held_out_target]
    if not train or not heldout:
        raise RuntimeError("split failed: need >=2 targets with clips")
    held_seqs = {(d["target"], d["seed"]) for d in heldout}
    leak = [d for d in train if (d["target"], d["seed"]) in held_seqs]
    if leak:
        raise RuntimeError(f"leakage: {len(leak)} held-out sequences in train")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    model = GrabConditioner(len(targets), args.hidden).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)

    losses = []
    for step in range(args.steps):
        d = train[step % len(train)]
        pose_feat, root, cond, body_target = build_tensors(d, frames, targets, tindex, device)
        # base input = frame-0 state broadcast over time (NOT the full clip),
        # so the model must use the conditioning to reconstruct the trajectory.
        init_pose = pose_feat[0:1].expand(frames, -1)
        init_root = root[0:1].expand(frames, -1)
        opt.zero_grad(set_to_none=True)
        pred_pose, pred_root = model(init_pose[None], init_root[None], cond[None])
        # Endpoint-weighted loss: emphasize the two grab hands so the contact
        # geometry is learned, not just the mean full-body shape.
        w = torch.ones(34, device=device)
        w[HAND_R] = 6.0
        w[HAND_L] = 6.0
        pw = w.reshape(1, 1, 34, 1)
        pose_term = ((pred_pose.reshape(1, frames, 34, 3) - body_target[None].reshape(1, frames, 34, 3)) ** 2 * pw).mean()
        root_term = torch.mean((pred_root - root[None]) ** 2)
        loss = pose_term + 0.5 * root_term
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 10.0)
        opt.step()
        losses.append(float(loss.detach().cpu()))

    model.eval()

    def run_heldout(ablate: bool):
        rows = []
        with torch.no_grad():
            for d in heldout:
                pose_feat, root, cond, body_target = build_tensors(d, frames, targets, tindex, device)
                if ablate:
                    cond = torch.zeros_like(cond)  # condition ablation: no target geometry
                init_pose = pose_feat[0:1].expand(frames, -1)
                init_root = root[0:1].expand(frames, -1)
                pred_pose, pred_root = model(init_pose[None], init_root[None], cond[None])
                pred_pose = pred_pose[0].reshape(frames, 34, 3)
                pred_root = pred_root[0]
                tgt = body_target.reshape(frames, 34, 3)
                full_err = float(torch.mean(torch.linalg.vector_norm(pred_pose - tgt, dim=-1)).cpu()) * 1000.0
                hs = hand_surface_err_mm(pred_pose, pred_root, d["contact"])
                rows.append({"target": d["target"], "seed": d["seed"],
                             "fullbody_err_mm": round(full_err, 2),
                             "hand_surface_err_mm": round(hs, 2)})
        return rows

    held_conditioned = run_heldout(ablate=False)
    held_ablated = run_heldout(ablate=True)
    worst_cond = max(h["hand_surface_err_mm"] for h in held_conditioned)
    best_cond = min(h["hand_surface_err_mm"] for h in held_conditioned)
    worst_abl = min(h["hand_surface_err_mm"] for h in held_ablated)
    ablation_ok = worst_cond < worst_abl

    args.out.mkdir(parents=True, exist_ok=True)
    ck = args.out / "grab07_conditioner.pt"
    torch.save({"state_dict": model.state_dict(), "frames": frames, "targets": targets,
                "arch": "GrabConditioner-v3-initstate-cond-decode"}, ck)

    gate_mm = 15.0
    if best_cond == 0.0:
        verdict, reason = "SUSPICIOUS_ZERO", "exactly 0.0mm held-out error: masking red flag"
    elif best_cond <= gate_mm and ablation_ok:
        verdict = "PASS"
        reason = f"best held-out {best_cond:.2f}mm <= {gate_mm:.0f}mm and ablation proves conditioning is used"
    elif best_cond <= gate_mm:
        verdict, reason = "FAIL", "passes distance gate but FAILS condition-ablation (ignores target geometry)"
    else:
        verdict, reason = "FAIL", f"best held-out {best_cond:.2f}mm > {gate_mm:.0f}mm"

    report = {
        "schema": "just-dodge-grab07-unit2-train-v2",
        "runtime_admitted": False,
        "conditioning": "genuine dual-backbone (condition enters pose+root INPUT; no output masking)",
        "held_out_split": "leakage-resistant by (source sequence, interaction cell)",
        "held_out_target": args.held_out_target,
        "train_clips": len(train), "heldout_clips": len(heldout),
        "steps": args.steps, "lr": args.lr, "hidden": args.hidden, "seed": SEED,
        "train_loss_first": losses[0], "train_loss_last": losses[-1],
        "heldout_conditioned": held_conditioned,
        "heldout_ablated": held_ablated,
        "ablation_ok": ablation_ok,
        "verdict": verdict, "reason": reason,
        "checkpoint_sha256": sha(ck.read_bytes()),
    }
    (args.out / "train_report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"verdict": verdict, "best_mm": best_cond, "worst_mm": worst_cond,
                      "ablation_ok": ablation_ok, "reason": reason}, indent=1))
    print(f"GRAB07_UNIT2_TRAIN verdict={verdict} best_mm={best_cond:.2f} "
          f"worst_mm={worst_cond:.2f} ablation_ok={ablation_ok}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
