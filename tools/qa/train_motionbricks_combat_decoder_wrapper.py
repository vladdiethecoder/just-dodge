#!/usr/bin/env python3
"""Held-out multi-action decoder validation through MotionBricks' wrapper API."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as functional

ROOT = Path(__file__).resolve().parents[2]
QA_TOOLS = ROOT / "tools/qa"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(QA_TOOLS))

from motionbricks_service.generate import init_service
from probe_motionbricks_combat_vqvae import decode, decode_positions

ACTIONS = ("strike", "block", "grab")
WINDOW = 32
STRIDE = 16


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def starts(length: int) -> list[int]:
    values = list(range(0, length - WINDOW + 1, STRIDE))
    if not values:
        raise RuntimeError(f"clip shorter than {WINDOW}: {length}")
    if values[-1] != length - WINDOW:
        values.append(length - WINDOW)
    return values


def prepare(service: dict, manifest: dict) -> dict:
    pose_net = service["inferencer"]._vqvae_pose_model
    grouped = defaultdict(lambda: defaultdict(list))
    for entry in manifest["entries"]:
        features = np.load(ROOT / entry["features_path"], allow_pickle=False)
        global_motion = torch.from_numpy(features)[None].to(service["device"])
        with torch.no_grad():
            local = service["motion_rep"].dual_rep.global_to_local(
                global_motion,
                is_normalized=True,
                to_normalize=True,
                lengths=torch.tensor([len(features)], device=service["device"]),
            )
            for start in starts(local.shape[1]):
                crop = local[:, start : start + WINDOW].contiguous()
                token = pose_net.encode_into_idx(crop, fetch_overall_indices=False)
                grouped[entry["split"]][entry["action"]].append(
                    (entry["source_id"], crop, token.detach())
                )
    return grouped


def evaluate(service: dict, grouped: dict) -> tuple[dict, dict]:
    pose_net = service["inferencer"]._vqvae_pose_model
    pose_net.eval()
    losses: dict[str, float] = {}
    bounds = {"max_abs_m": 0.0, "root_min_m": 1.0e9, "root_max_m": -1.0e9}
    with torch.no_grad():
        for action in ACTIONS:
            action_losses = []
            for _, local, token in grouped[action]:
                recon = decode(pose_net, local, token)["recon_state"]
                action_losses.append(float(functional.smooth_l1_loss(recon, local)))
                positions = decode_positions(service, recon)
                bounds["max_abs_m"] = max(
                    bounds["max_abs_m"], float(np.abs(positions).max())
                )
                bounds["root_min_m"] = min(
                    bounds["root_min_m"], float(positions[:, 0, 1].min())
                )
                bounds["root_max_m"] = max(
                    bounds["root_max_m"], float(positions[:, 0, 1].max())
                )
            losses[action] = float(np.mean(action_losses))
    return losses, bounds


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("qa_runs/m3_contact_truth_001/b14t_combat_dataset/corpus/manifest.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("qa_runs/m3_contact_truth_001/b14v_wrapper_generalization"),
    )
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--learning-rate", type=float, default=1.0e-6)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    service = init_service()
    pose_net = service["inferencer"]._vqvae_pose_model
    grouped = prepare(service, manifest)
    for split in ("train", "validation"):
        for action in ACTIONS:
            if not grouped[split][action]:
                raise RuntimeError(f"missing {split}/{action}")
    train_sources = {
        source for action in ACTIONS for source, _, _ in grouped["train"][action]
    }
    validation_sources = {
        source for action in ACTIONS for source, _, _ in grouped["validation"][action]
    }
    if train_sources & validation_sources:
        raise RuntimeError("train/validation source overlap")
    baseline, baseline_bounds = evaluate(service, grouped["validation"])

    pose_net.eval()
    for parameter in pose_net.parameters():
        parameter.requires_grad_(False)
    pose_net.decoder.train()
    for parameter in pose_net.decoder.parameters():
        parameter.requires_grad_(True)
    optimizer = torch.optim.AdamW(pose_net.decoder.parameters(), lr=args.learning_rate)
    rng = random.Random(20260715)
    losses: list[float] = []
    gradients: list[float] = []
    for step in range(args.steps):
        action = ACTIONS[step % 3]
        _, local, token = rng.choice(grouped["train"][action])
        optimizer.zero_grad(set_to_none=True)
        recon = decode(pose_net, local, token)["recon_state"]
        loss = functional.smooth_l1_loss(recon, local)
        if action != "block":
            _, block_local, block_token = rng.choice(grouped["train"]["block"])
            block_recon = decode(pose_net, block_local, block_token)["recon_state"]
            loss = loss + 2.0 * functional.smooth_l1_loss(
                block_recon, block_local
            )
        if not torch.isfinite(loss):
            raise RuntimeError(f"non-finite loss at {step}")
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_(pose_net.decoder.parameters(), 100.0)
        optimizer.step()
        losses.append(float(loss.detach()))
        gradients.append(float(norm))
        if step % 25 == 0 or step == args.steps - 1:
            print(f"step={step:03d} action={action} loss={losses[-1]:.9f} grad={gradients[-1]:.9f}")
    final, final_bounds = evaluate(service, grouped["validation"])
    improvement = {
        action: (baseline[action] - final[action]) / baseline[action]
        for action in ACTIONS
    }
    if not all(value > 0.0 for value in improvement.values()):
        raise RuntimeError(f"held-out action regression: {improvement}")
    if final_bounds["max_abs_m"] >= 5.0:
        raise RuntimeError(f"decoded coordinates out of bounds: {final_bounds}")
    if final_bounds["root_min_m"] <= 0.1 or final_bounds["root_max_m"] >= 2.0:
        raise RuntimeError(f"decoded root out of bounds: {final_bounds}")
    checkpoint = args.output_dir / "motionbricks_pose_vqvae_combat_corpus.pt"
    torch.save(
        {
            "state_dict": {key: value.detach().cpu() for key, value in pose_net.state_dict().items()},
            "manifest_sha256": sha(args.manifest),
            "steps": args.steps,
            "learning_rate": args.learning_rate,
        },
        checkpoint,
    )
    metrics = {
        "manifest_sha256": sha(args.manifest),
        "train_sources": sorted(train_sources),
        "validation_sources": sorted(validation_sources),
        "baseline_validation_loss": baseline,
        "final_validation_loss": final,
        "relative_validation_improvement": improvement,
        "baseline_bounds": baseline_bounds,
        "final_bounds": final_bounds,
        "steps": args.steps,
        "learning_rate": args.learning_rate,
        "train_loss_first": losses[0],
        "train_loss_last": losses[-1],
        "gradient_norm_min": min(gradients),
        "gradient_norm_max": max(gradients),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha(checkpoint),
    }
    (args.output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, sort_keys=True))
    print("B14V_WRAPPER_GENERALIZATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
