#!/usr/bin/env python3
"""One-batch MotionBricks combat fine-tuning feasibility gate.

The ARDY motion is offline teacher data only. This probe updates MotionBricks'
pose backbone in memory and writes QA-only weights/metrics; it does not create a
runtime motion cache or modify production assets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from motionbricks_service.generate import init_service


FIXED_SAMPLE_SEED = 20260714


def teacher_features(service: dict, teacher_path: Path) -> torch.Tensor:
    teacher = np.load(teacher_path)
    positions = torch.from_numpy(
        np.asarray(teacher["posed_joints"], dtype=np.float32)
    )[None].to(service["device"])
    rotations = torch.from_numpy(
        np.asarray(teacher["global_rot_mats"], dtype=np.float32)
    )[None].to(service["device"])
    contacts = torch.from_numpy(
        np.asarray(teacher["foot_contacts"], dtype=np.float32)
    )[None].to(service["device"])
    lengths = torch.tensor([positions.shape[1]], device=service["device"])
    features = service["motion_rep"](
        {
            "posed_joints": positions,
            "global_joint_rots": rotations,
            "foot_contacts": contacts,
        },
        to_normalize=True,
        lengths=lengths,
    )
    if features.shape != (1, positions.shape[1], 414):
        raise RuntimeError(f"unexpected teacher feature shape {tuple(features.shape)}")
    if not torch.isfinite(features).all():
        raise RuntimeError("teacher features contain non-finite values")
    return features


def fresh_batch(features: torch.Tensor) -> dict:
    frames = features.shape[1]
    return {
        "motion": features.clone(),
        "motion_len": torch.tensor([frames], device=features.device),
        "motion_pad_mask": torch.ones(
            [1, frames], dtype=torch.bool, device=features.device
        ),
        "batch_size": 1,
    }


def train_step(model, optimizer, features: torch.Tensor) -> tuple[float, float]:
    torch.manual_seed(FIXED_SAMPLE_SEED)
    torch.cuda.manual_seed_all(FIXED_SAMPLE_SEED)
    np.random.seed(FIXED_SAMPLE_SEED)
    optimizer.zero_grad(set_to_none=True)
    loss = model.training_step(fresh_batch(features), 0)
    if loss is None or not torch.isfinite(loss):
        raise RuntimeError(f"invalid training loss: {loss}")
    loss.backward()
    squared_norm = torch.zeros([], device=features.device)
    for parameter in model.backbone_net.parameters():
        if parameter.grad is not None:
            if not torch.isfinite(parameter.grad).all():
                raise RuntimeError("non-finite pose-backbone gradient")
            squared_norm += parameter.grad.square().sum()
    grad_norm = squared_norm.sqrt()
    if not torch.isfinite(grad_norm) or grad_norm.item() <= 0.0:
        raise RuntimeError(f"invalid gradient norm {grad_norm.item()}")
    optimizer.step()
    return float(loss.detach().cpu()), float(grad_norm.detach().cpu())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--teacher",
        type=Path,
        default=Path(
            "qa_runs/m3_contact_truth_001/b14k_ardy_constraints/generated/strike/strike_00.npz"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("qa_runs/m3_contact_truth_001/b14p_combat_finetune"),
    )
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--learning-rate", type=float, default=1.0e-5)
    args = parser.parse_args()
    if args.steps < 2:
        raise ValueError("--steps must be at least 2")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    service = init_service()
    model = service["inferencer"]._pose_model
    model.train()
    model._trainer = SimpleNamespace(global_step=0)
    model.log = lambda *args, **kwargs: None
    model._args["min_tokens"] = 8
    model._args["max_tokens"] = 8
    model._args["batchsize_mul_factor"] = 1

    for parameter in model.parameters():
        parameter.requires_grad_(False)
    for parameter in model.backbone_net.parameters():
        parameter.requires_grad_(True)

    features = teacher_features(service, args.teacher)
    trainable = [
        parameter for parameter in model.backbone_net.parameters() if parameter.requires_grad
    ]
    trainable_count = sum(parameter.numel() for parameter in trainable)
    if trainable_count == 0:
        raise RuntimeError("pose backbone has no trainable parameters")
    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate)

    losses: list[float] = []
    grad_norms: list[float] = []
    for step in range(args.steps):
        loss, grad_norm = train_step(model, optimizer, features)
        losses.append(loss)
        grad_norms.append(grad_norm)
        print(f"step={step:03d} loss={loss:.9f} grad_norm={grad_norm:.9f}")

    initial = losses[0]
    final = losses[-1]
    reduction = (initial - final) / initial
    if final >= initial or reduction < 0.02:
        raise RuntimeError(
            f"one-batch overfit failed: initial={initial:.9f} final={final:.9f} "
            f"reduction={reduction:.6f}"
        )

    checkpoint_path = args.output_dir / "pose_backbone_one_batch_overfit.pt"
    torch.save(
        {
            "state_dict": {
                f"backbone_net.{key}": value.detach().cpu()
                for key, value in model.backbone_net.state_dict().items()
            },
            "teacher_sha256": hashlib.sha256(args.teacher.read_bytes()).hexdigest(),
            "steps": args.steps,
            "learning_rate": args.learning_rate,

        },
        checkpoint_path,
    )
    metrics = {
        "teacher": str(args.teacher),
        "teacher_sha256": hashlib.sha256(args.teacher.read_bytes()).hexdigest(),
        "steps": args.steps,
        "learning_rate": args.learning_rate,

        "trainable_parameters": trainable_count,
        "initial_loss": initial,
        "final_loss": final,
        "relative_loss_reduction": reduction,
        "min_gradient_norm": min(grad_norms),
        "max_gradient_norm": max(grad_norms),
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
    }
    (args.output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, sort_keys=True))
    print("B14P_ONE_BATCH_OVERFIT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
