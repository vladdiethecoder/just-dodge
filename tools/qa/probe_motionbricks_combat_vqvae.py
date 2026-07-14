#!/usr/bin/env python3
"""One-batch combat adaptation gate for MotionBricks' pose VQVAE."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from motionbricks.helper.data_training_util import extract_feature_from_motion_rep
from motionbricks_service.generate import init_service


CROP_START = 14
CROP_FRAMES = 32
FIXED_SEED = 20260714


def teacher_global_features(service: dict, teacher_path: Path) -> torch.Tensor:
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
    return features


def crop_local_features(service: dict, global_features: torch.Tensor) -> torch.Tensor:
    crop = global_features[:, CROP_START : CROP_START + CROP_FRAMES + 1]
    local = service["motion_rep"].dual_rep.global_to_local(
        crop,
        is_normalized=True,
        to_normalize=True,
        lengths=torch.tensor([crop.shape[1]], device=service["device"]),
    )
    local = local[:, :CROP_FRAMES]
    expected_width = len(
        service["motion_rep"].dual_rep.local_motion_rep.indices["all"]
    )
    if local.shape != (1, CROP_FRAMES, expected_width) or not torch.isfinite(local).all():
        raise RuntimeError(f"invalid local teacher features {tuple(local.shape)}")
    return local


def decode(pose_net, local: torch.Tensor, tokens: torch.Tensor) -> dict:
    external = extract_feature_from_motion_rep(
        local, pose_net.motion_rep, pose_net.decoder_external_cond_feature_mode
    )
    no_targets = torch.zeros(
        local.shape[:2], dtype=torch.bool, device=local.device
    )
    return pose_net.forward_decoder(
        tokens,
        target_cond=local,
        has_target_cond=no_targets,
        external_cond=external,
        use_overall_indices=False,
    )


def decode_positions(service: dict, recon_local: torch.Tensor) -> np.ndarray:
    global_features = service["motion_rep"].dual_rep.local_to_global(
        recon_local,
        is_normalized=True,
        to_normalize=False,
        lengths=torch.tensor([recon_local.shape[1]], device=service["device"]),
    )
    output = service["motion_rep"].inverse(
        global_features,
        is_normalized=False,
        return_quat=False,
        return_all=False,
    )
    return output["posed_joints"][0].detach().cpu().numpy()


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
        default=Path("qa_runs/m3_contact_truth_001/b14r_combat_vqvae"),
    )
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--learning-rate", type=float, default=1.0e-5)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(FIXED_SEED)
    torch.cuda.manual_seed_all(FIXED_SEED)
    np.random.seed(FIXED_SEED)
    service = init_service()
    pose_net = service["inferencer"]._vqvae_pose_model
    pose_net.eval()
    for parameter in pose_net.parameters():
        parameter.requires_grad_(False)
    for parameter in pose_net.decoder.parameters():
        parameter.requires_grad_(True)
    pose_net.decoder.train()
    optimizer = torch.optim.AdamW(pose_net.decoder.parameters(), lr=args.learning_rate)

    global_features = teacher_global_features(service, args.teacher)
    local = crop_local_features(service, global_features)
    with torch.no_grad():
        tokens = pose_net.encode_into_idx(local, fetch_overall_indices=False)
    losses: list[float] = []
    recon_losses: list[float] = []
    grad_norms: list[float] = []
    for step in range(args.steps):
        torch.manual_seed(FIXED_SEED)
        torch.cuda.manual_seed_all(FIXED_SEED)
        optimizer.zero_grad(set_to_none=True)
        output = decode(pose_net, local, tokens)
        recon_loss = torch.nn.functional.smooth_l1_loss(output["recon_state"], local)
        loss = recon_loss
        if not torch.isfinite(loss):
            raise RuntimeError(f"non-finite loss at step {step}")
        loss.backward()
        squared = torch.zeros([], device=service["device"])
        for parameter in pose_net.decoder.parameters():
            if parameter.grad is not None:
                if not torch.isfinite(parameter.grad).all():
                    raise RuntimeError(f"non-finite gradient at step {step}")
                squared += parameter.grad.square().sum()
        grad_norm = squared.sqrt()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
        recon_losses.append(float(recon_loss.detach().cpu()))
        grad_norms.append(float(grad_norm.detach().cpu()))
        print(
            f"step={step:03d} loss={losses[-1]:.9f} "
            f"recon={recon_losses[-1]:.9f} grad_norm={grad_norms[-1]:.9f}"
        )

    reduction = (losses[0] - losses[-1]) / losses[0]
    if reduction < 0.02:
        raise RuntimeError(
            f"VQVAE overfit failed: initial={losses[0]:.9f} "
            f"final={losses[-1]:.9f} reduction={reduction:.6f}"
        )
    pose_net.eval()
    with torch.no_grad():
        reconstructed = decode(pose_net, local, tokens)["recon_state"]
    positions = decode_positions(service, reconstructed)
    max_abs = float(np.abs(positions).max())
    root_min = float(positions[:, 0, 1].min())
    root_max = float(positions[:, 0, 1].max())
    if max_abs > 5.0 or root_min < 0.2 or root_max > 2.0:
        raise RuntimeError(
            f"decoded pose out of bounds: max_abs={max_abs:.6f} "
            f"root_y=[{root_min:.6f}, {root_max:.6f}]"
        )

    checkpoint = args.output_dir / "motionbricks_pose_vqvae_combat_overfit.pt"
    torch.save(
        {
            "state_dict": {
                key: value.detach().cpu() for key, value in pose_net.state_dict().items()
            },
            "teacher_sha256": hashlib.sha256(args.teacher.read_bytes()).hexdigest(),
            "steps": args.steps,
            "learning_rate": args.learning_rate,
        },
        checkpoint,
    )
    metrics = {
        "teacher": str(args.teacher),
        "teacher_sha256": hashlib.sha256(args.teacher.read_bytes()).hexdigest(),
        "steps": args.steps,
        "learning_rate": args.learning_rate,
        "trainable_parameters": sum(p.numel() for p in pose_net.decoder.parameters()),
        "initial_loss": losses[0],
        "final_loss": losses[-1],
        "relative_loss_reduction": reduction,
        "initial_reconstruction_loss": recon_losses[0],
        "final_reconstruction_loss": recon_losses[-1],
        "min_gradient_norm": min(grad_norms),
        "max_gradient_norm": max(grad_norms),
        "decoded_max_abs_m": max_abs,
        "decoded_root_height_min_m": root_min,
        "decoded_root_height_max_m": root_max,
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
    }
    (args.output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, sort_keys=True))
    print("B14R_COMBAT_VQVAE_OVERFIT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
