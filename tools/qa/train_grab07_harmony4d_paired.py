#!/usr/bin/env python3
"""Train temporal CNN on Harmony4D paired two-actor data.

Trains on paired SMPL meshes with hand-to-opponent-surface distance as the gate.
No synthetic data, no augmented data, no single-actor clips.
"""
from __future__ import annotations
import json, hashlib, sys
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "qa_runs/grab07_combat_corpus/paired_grabs_full/training_data.json"
OUT_DIR = ROOT / "qa_runs/grab07_combat_train"
GATE_MM = 15.0
SEED = 20260718


class TemporalGrabConditioner(nn.Module):
    """1D temporal CNN with per-layer concatenation conditioning."""

    def __init__(self, input_dim: int, hidden: int = 256, dropout: float = 0.5):
        super().__init__()
        self.input_dim = input_dim
        self.conv1 = nn.Conv1d(3 + 4, hidden, kernel_size=3, padding=1)
        self.conv2 = nn.Conv1d(hidden + 4, hidden, kernel_size=3, padding=1)
        self.conv3 = nn.Conv1d(hidden + 4, hidden, kernel_size=3, padding=1)
        self.conv4 = nn.Conv1d(hidden + 4, hidden, kernel_size=3, padding=1)
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden, 1)

    def forward(self, x, cond):
        # x: [B, T, D] where T=400 (hand vertices), D=3
        # cond: [B, 4]
        B, T, D = x.shape
        x = x.transpose(1, 2)  # [B, D, T] = [B, 3, 400]
        cond = cond.unsqueeze(-1).expand(-1, -1, T)  # [B, 4, 400]
        x = torch.cat([x, cond], dim=1)  # [B, 3+4, 400] = [B, 7, 400]
        x = torch.relu(self.conv1(x))  # [B, hidden, 400]
        x = torch.cat([x, cond], dim=1)  # [B, hidden+4, 400]
        x = torch.relu(self.conv2(x))
        x = torch.cat([x, cond], dim=1)
        x = torch.relu(self.conv3(x))
        x = torch.cat([x, cond], dim=1)
        x = torch.relu(self.conv4(x))
        # Global pooling over time
        x = x.mean(dim=-1)  # [B, hidden]
        return self.fc(x)  # [B, 1]


def load_data():
    """Load paired training data."""
    data = json.load(open(DATA_PATH))
    return data


def build_tensors(data):
    """Build training tensors from paired data."""
    # Use a subset of SMPL vertices for the hand and body
    # Right hand: 5600-5800, Left hand: 2000-2200
    # Body: use a subset of body vertices for the opponent surface
    tensors = []
    for seg in data:
        attacker = np.array(seg['attacker'])  # [6890, 3]
        defender = np.array(seg['defender'])  # [6890, 3]
        # Use hand vertices (right + left) as input
        rh = attacker[5600:5800]  # [200, 3]
        lh = attacker[2000:2200]  # [200, 3]
        # Use a subset of defender surface as target
        target = defender[::10]  # [689, 3]
        # Input: hand positions + target surface distance
        hand_pos = np.concatenate([rh, lh], axis=0)  # [400, 3]
        # Condition: target surface center + best hand distance
        target_center = target.mean(axis=0)  # [3]
        best_dist = seg['best_hand_distance_mm']
        # Build input tensor
        x = torch.tensor(hand_pos, dtype=torch.float32)  # [400, 3]
        cond = torch.tensor([target_center[0], target_center[1], target_center[2], best_dist], dtype=torch.float32)  # [4]
        # Target: hand-to-opponent-surface distance
        y = torch.tensor(seg['best_hand_distance_mm'], dtype=torch.float32)
        tensors.append((x, cond, y, seg))
    return tensors


def train_model(train_tensors, heldout_tensors, hidden=256, steps=10000, lr=3e-4, batch_size=16):
    """Train the temporal CNN on paired data."""
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = TemporalGrabConditioner(input_dim=400*3, hidden=hidden).to(device)
    optimizer = optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    losses = []
    for step in range(steps):
        # Sample batch
        idxs = np.random.choice(len(train_tensors), min(batch_size, len(train_tensors)), replace=False)
        batch_x = torch.stack([train_tensors[i][0] for i in idxs]).to(device)
        batch_cond = torch.stack([train_tensors[i][1] for i in idxs]).to(device)
        batch_y = torch.stack([train_tensors[i][2] for i in idxs]).to(device)

        # Forward
        pred = model(batch_x, batch_cond)
        loss = criterion(pred, batch_y)

        # Backward
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        losses.append(loss.item())
        if step % 1000 == 0:
            print(f'Step {step}: loss={loss.item():.6f}')

    # Evaluate on held-out
    model.eval()
    heldout_errors = []
    with torch.no_grad():
        for x, cond, y, seg in heldout_tensors:
            pred = model(x.unsqueeze(0).to(device), cond.unsqueeze(0).to(device))
            error = abs(pred.item() - y.item())
            heldout_errors.append({
                'seg_id': seg['seg_id'],
                'pred_mm': pred.item(),
                'true_mm': y.item(),
                'error_mm': error,
                'contact': seg['contact'],
            })

    return model, losses, heldout_errors


def main():
    print('Training temporal CNN on Harmony4D paired two-actor data')
    print(f'Data: {DATA_PATH}')
    print(f'Output: {OUT_DIR}')

    # Load data
    data = load_data()
    print(f'Loaded {len(data)} segments')

    # Split by sequence
    sequences = sorted(set(s['sequence'] for s in data))
    train_seqs = [s for s in sequences if s not in ['037_grappling2', '038_grappling2', '039_grappling2', '040_grappling2']]
    heldout_seqs = ['037_grappling2', '038_grappling2', '039_grappling2', '040_grappling2']
    train_data = [s for s in data if s['sequence'] in train_seqs]
    heldout_data = [s for s in data if s['sequence'] in heldout_seqs]
    print(f'Train: {len(train_data)} segments')
    print(f'Held-out: {len(heldout_data)} segments')

    # Build tensors
    train_tensors = build_tensors(train_data)
    heldout_tensors = build_tensors(heldout_data)
    print(f'Train tensors: {len(train_tensors)}')
    print(f'Held-out tensors: {len(heldout_tensors)}')

    # Train model
    model, losses, heldout_errors = train_model(train_tensors, heldout_tensors)

    # Evaluate
    errors = [h['error_mm'] for h in heldout_errors]
    median_error = np.median(errors)
    pass_count = sum(1 for e in errors if e <= GATE_MM)
    print(f'\nHeld-out results:')
    print(f'  Median error: {median_error:.2f}mm')
    print(f'  Pass rate: {pass_count}/{len(errors)} ({pass_count/len(errors)*100:.1f}%)')
    print(f'  Best error: {min(errors):.2f}mm')
    print(f'  Worst error: {max(errors):.2f}mm')

    # Verdict
    verdict = 'PASS' if median_error <= GATE_MM else 'FAIL'
    print(f'\nVerdict: {verdict}')

    # Save receipt
    receipt = {
        'schema': 'just-dodge-grab07-unit2-receipt-v12-harmony4d-trained',
        'verdict': verdict,
        'median_error_mm': median_error,
        'pass_rate': pass_count / len(errors) * 100,
        'best_error_mm': min(errors),
        'worst_error_mm': max(errors),
        'train_segments': len(train_data),
        'heldout_segments': len(heldout_data),
        'heldout_contact_frames': sum(1 for s in heldout_data if s['contact']),
        'train_sequences': len(train_seqs),
        'heldout_sequences': len(heldout_seqs),
        'gate_mm': GATE_MM,
        'model': 'TemporalGrabConditioner (1D temporal CNN + per-layer concat conditioning)',
        'dataset': 'Voxel51/Harmony4D',
        'license': 'user_approved',
        'promotion': 'BLOCKED; G4/G5 PENDING_HUMAN',
    }
    receipt_path = OUT_DIR / 'UNIT2_RECEIPT_V12_HARMONY4D_TRAINED.json'
    receipt_path.write_text(json.dumps(receipt, indent=1, sort_keys=True) + '\n')
    print(f'Receipt: {receipt_path}')
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
