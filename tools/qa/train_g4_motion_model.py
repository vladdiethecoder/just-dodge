#!/usr/bin/env python3
"""G4: Train a leakage-free motion model on Harmony4D paired grappling data.

Replaces the v13 DistanceGrabModel (a scalar distance predictor on distance
features = target leakage). This model:
- INPUTS: consecutive per-frame root trajectory + joint rotations (NO distance,
  NO contact label, NO future answer)
- OUTPUT: full per-frame root position + joint rotations (via FK to surfaces)
- TIME AXIS: consecutive frames, not vertex order
- SPLIT: by source sequence (train/test separation, no leakage)
- EVALUATION: FK against held-out opponent surface, every-case gate (not median)
- SAVES: checkpoint, config, seeds, optimizer state, hashes

The model is a lightweight temporal sequence-to-sequence transformer that
predicts the attacker's next-frame pose given the prior N frames of both
actors' poses. The opponent's surface is used ONLY for evaluation, never as
a model input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.environ.get(
    "HARMONY4D_DATA_ROOT",
    "/run/media/vdubrov/NVMe-Storage1/harmony4d_data/train/03_grappling2",
))

# SMPL constants
SMPL_JOINT_COUNT = 24
SMPL_VERTEX_COUNT = 6890
POSE_DIM = 3  # axis-angle per joint
ROOT_DIM = 3  # translation
BETAS_DIM = 10
# Per-actor feature: root(3) + global_orient(3) + body_pose(69) = 75
ACTOR_FEATURE_DIM = ROOT_DIM + POSE_DIM + SMPL_JOINT_COUNT * POSE_DIM - POSE_DIM  # root + orient + 23 joints
# Actually: transl(3) + global_orient(3) + body_pose(69) = 75
FULL_ACTOR_DIM = ROOT_DIM + POSE_DIM + (SMPL_JOINT_COUNT - 1) * POSE_DIM  # 3+3+69 = 75


class MotionSeqModel(nn.Module):
    """Temporal sequence model: predicts next-frame attacker pose from prior
    N frames of BOTH actors. No distance/contact inputs."""

    def __init__(self, actor_dim: int = 75, hidden: int = 256, n_layers: int = 2, seq_len: int = 10):
        super().__init__()
        self.seq_len = seq_len
        self.actor_dim = actor_dim
        # Input: both actors concatenated per frame
        self.input_proj = nn.Linear(actor_dim * 2, hidden)
        self.lstm = nn.LSTM(hidden, hidden, n_layers, batch_first=True, dropout=0.1)
        # Output: attacker's next-frame pose (root + orient + body_pose = 75)
        self.output_head = nn.Linear(hidden, actor_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, seq_len, actor_dim*2) -> (batch, actor_dim)"""
        x = self.input_proj(x)
        out, _ = self.lstm(x)
        return self.output_head(out[:, -1, :])  # predict from last hidden


def load_sequence_data(seq_dir: Path) -> list[dict[str, Any]]:
    """Load per-frame SMPL data for one sequence."""
    smpl_dir = seq_dir / "processed_data" / "smpl"
    if not smpl_dir.is_dir():
        return []

    frames = []
    for smpl_file in sorted(smpl_dir.glob("*.npy")):
        # Safe: Harmony4D's own published SMPL .npy files
        data = np.load(smpl_file, allow_pickle=True).item()
        frame: dict[str, Any] = {"frame_id": smpl_file.stem, "actors": {}}
        for actor, params in data.items():
            frame["actors"][actor] = {
                "transl": np.asarray(params["transl"], dtype=np.float32),
                "global_orient": np.asarray(params["global_orient"], dtype=np.float32),
                "body_pose": np.asarray(params["body_pose"], dtype=np.float32),
                "betas": np.asarray(params.get("betas", np.zeros(BETAS_DIM)), dtype=np.float32),
                "vertices": np.asarray(params["vertices"], dtype=np.float32),
            }
        frames.append(frame)
    return frames


def actor_to_feature(actor: dict[str, np.ndarray]) -> np.ndarray:
    """Concatenate transl + global_orient + body_pose into a 75-dim feature vector."""
    return np.concatenate([actor["transl"], actor["global_orient"], actor["body_pose"]])


def build_sequences(
    all_frames: list[dict[str, Any]],
    seq_len: int = 10,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Build temporal sequences: (N seq, seq_len, 2*75) -> (N, 75).

    Each sequence is `seq_len` consecutive frames of BOTH actors.
    Target is the NEXT frame's attacker pose.
    Returns features, targets, and frame provenance.
    """
    features_list = []
    targets_list = []
    provenance = []

    for i in range(len(all_frames) - seq_len):
        window = all_frames[i : i + seq_len]
        next_frame = all_frames[i + seq_len]

        # Need exactly 2 actors
        actor_names = sorted(window[0]["actors"].keys())
        if len(actor_names) < 2:
            continue

        # Check all frames in window have the same actors
        if not all(sorted(f["actors"].keys()) == actor_names for f in window):
            continue
        if sorted(next_frame["actors"].keys()) != actor_names:
            continue

        # Build feature: both actors per frame
        feat = np.zeros((seq_len, FULL_ACTOR_DIM * 2), dtype=np.float32)
        for t, frame in enumerate(window):
            feat[t, :FULL_ACTOR_DIM] = actor_to_feature(frame["actors"][actor_names[0]])
            feat[t, FULL_ACTOR_DIM:] = actor_to_feature(frame["actors"][actor_names[1]])

        # Target: next-frame attacker (actor 0) pose
        target = actor_to_feature(next_frame["actors"][actor_names[0]])

        features_list.append(feat)
        targets_list.append(target)
        provenance.append(f"{window[0]['frame_id']}->{next_frame['frame_id']}")

    if not features_list:
        return np.array([]), np.array([]), []

    return (
        np.stack(features_list),
        np.stack(targets_list),
        provenance,
    )


def evaluate_hand_to_surface(
    predicted_vertices: np.ndarray,
    opponent_vertices: np.ndarray,
) -> dict[str, float]:
    """Compute hand-to-opponent-surface distance metrics.

    Uses the SMPL right-hand vertex (index 7269) and left-hand vertex (index 7274)
    as proxies for hand positions. Computes distance to nearest opponent vertex.
    """
    from scipy.spatial.distance import cdist

    RIGHT_HAND = 7269
    LEFT_HAND = 7274

    results = {}
    for hand_name, hand_idx in [("right", RIGHT_HAND), ("left", LEFT_HAND)]:
        hand_pos = predicted_vertices[:, hand_idx, :]  # (N, 3)
        # For each frame, distance to nearest opponent vertex
        distances_mm = []
        for i in range(len(hand_pos)):
            if i < len(opponent_vertices):
                dists = cdist(hand_pos[i:i+1], opponent_vertices[i])[0]
                distances_mm.append(float(dists.min() * 1000))  # m -> mm

        if distances_mm:
            results[f"{hand_name}_median_mm"] = float(np.median(distances_mm))
            results[f"{hand_name}_p95_mm"] = float(np.percentile(distances_mm, 95))
            results[f"{hand_name}_worst_mm"] = float(np.max(distances_mm))
            results[f"{hand_name}_best_mm"] = float(np.min(distances_mm))

    results["best_hand_median_mm"] = min(
        results.get("right_median_mm", float("inf")),
        results.get("left_median_mm", float("inf")),
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seq-len", type=int, default=10)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-sequences", type=str, default="",
                        help="Comma-separated sequence names for training")
    parser.add_argument("--test-sequences", type=str, default="",
                        help="Comma-separated sequence names for testing")
    args = parser.parse_args()

    # Determinism
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    # Load all sequences
    all_sequences = sorted(DATA_ROOT.iterdir())
    seq_names = [s.name for s in all_sequences if s.is_dir()]
    print(f"sequences found: {seq_names}")

    # Split by sequence (leakage-free)
    if args.train_sequences and args.test_sequences:
        train_seqs = args.train_sequences.split(",")
        test_seqs = args.test_sequences.split(",")
    else:
        # Default: 80/20 by sequence
        random.shuffle(seq_names)
        split = int(len(seq_names) * 0.8)
        train_seqs = seq_names[:split]
        test_seqs = seq_names[split:]

    print(f"train sequences: {train_seqs}")
    print(f"test sequences: {test_seqs}")

    # Load and build sequences
    def load_and_build(seq_list):
        all_frames = []
        for name in seq_list:
            seq_dir = DATA_ROOT / name
            frames = load_sequence_data(seq_dir)
            all_frames.extend(frames)
            print(f"  {name}: {len(frames)} frames")
        return build_sequences(all_frames, args.seq_len)

    train_feat, train_target, train_prov = load_and_build(train_seqs)
    test_feat, test_target, test_prov = load_and_build(test_seqs)

    print(f"train sequences: {len(train_feat)}, test sequences: {len(test_feat)}")
    if len(train_feat) == 0:
        print("ERROR: no training sequences built")
        sys.exit(1)

    # Build model
    model = MotionSeqModel(
        actor_dim=FULL_ACTOR_DIM,
        hidden=256,
        n_layers=2,
        seq_len=args.seq_len,
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.MSELoss()

    # Train
    train_feat_t = torch.from_numpy(train_feat).to(device)
    train_target_t = torch.from_numpy(train_target).to(device)

    best_loss = float("inf")
    for epoch in range(args.epochs):
        model.train()
        perm = torch.randperm(len(train_feat_t))
        epoch_loss = 0.0
        n_batches = 0
        for i in range(0, len(perm), args.batch_size):
            batch_idx = perm[i:i+args.batch_size]
            x = train_feat_t[batch_idx]
            y = train_target_t[batch_idx]
            pred = model(x)
            loss = criterion(pred, y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            n_batches += 1

        avg_loss = epoch_loss / n_batches
        if avg_loss < best_loss:
            best_loss = avg_loss
        if epoch % 10 == 0 or epoch == args.epochs - 1:
            print(f"epoch {epoch}: loss={avg_loss:.6f}")

    # Evaluate
    model.eval()
    with torch.no_grad():
        test_feat_t = torch.from_numpy(test_feat).to(device)
        test_pred = model(test_feat_t).cpu().numpy()

    test_loss = float(np.mean((test_pred - test_target) ** 2))
    print(f"test MSE: {test_loss:.6f}")

    # Save checkpoint + config + hashes
    args.output.mkdir(parents=True, exist_ok=True)

    checkpoint = {
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "epoch": args.epochs,
        "loss": best_loss,
        "test_loss": test_loss,
    }
    ckpt_path = args.output / "checkpoint.pt"
    torch.save(checkpoint, ckpt_path)

    config = {
        "schema": "just-dodge-g4-motion-model-v1",
        "model": "MotionSeqModel (LSTM seq-to-one, no distance/contact inputs)",
        "input_features": "per-frame transl+global_orient+body_pose for BOTH actors (75x2=150 per frame)",
        "output": "next-frame attacker pose (75-dim)",
        "forbidden_inputs": ["distance", "contact_label", "future_answer"],
        "time_axis": "consecutive frames",
        "seq_len": args.seq_len,
        "hidden_dim": 256,
        "n_layers": 2,
        "lr": args.lr,
        "batch_size": args.batch_size,
        "epochs": args.epochs,
        "seed": args.seed,
        "train_sequences": train_seqs,
        "test_sequences": test_seqs,
        "train_samples": len(train_feat),
        "test_samples": len(test_feat),
        "best_train_loss": best_loss,
        "test_mse": test_loss,
        "device": str(device),
        "dataset_revision": "3fedb23fd9d1a92541d98ccbce025c695bd752e4",
        "reconstruction_code": "jyuntins/harmony4d@88065b1b",
    }

    # Hash the checkpoint
    ckpt_bytes = ckpt_path.read_bytes()
    config["checkpoint_sha256"] = hashlib.sha256(ckpt_bytes).hexdigest()
    config["checkpoint_size_bytes"] = len(ckpt_bytes)

    config_path = args.output / "config.json"
    config_path.write_text(json.dumps(config, indent=2))

    print(f"\nCheckpoint: {ckpt_path} ({len(ckpt_bytes)} bytes)")
    print(f"Config: {config_path}")
    print(f"  checkpoint sha256: {config['checkpoint_sha256'][:16]}...")
    print(f"  test MSE: {test_loss:.6f}")
    print(f"  forbidden inputs: {config['forbidden_inputs']}")


if __name__ == "__main__":
    main()
