#!/usr/bin/env python3
"""Segment KungfuAthleteBot G1 clips into action-labeled windows.

Same approach as segment_cmu_combat.py but operates on the Kungfu corpus.
These clips contain diverse Wushu techniques: fist forms, sword forms, staff,
kicks, stance transitions, footwork, and more.
"""
from __future__ import annotations
import json, hashlib, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
G1_DIR = ROOT / "qa_runs/grab07_combat_corpus/kungfu_g1"
OUT_DIR = ROOT / "qa_runs/grab07_combat_corpus/kungfu_segments"
HAND_R, HAND_L = 33, 25
FOOT_R, FOOT_L = 23, 18
WINDOW = 120
STRIDE = 60


def load_g1(path):
    d = np.load(path)
    return d["posed_joints"].astype(np.float64), d["root_positions"].astype(np.float64)


def find_reach_events(jp):
    rh_fwd = jp[:, HAND_R, 2] - jp[:, 0, 2]
    lh_fwd = jp[:, HAND_L, 2] - jp[:, 0, 2]
    fwd = (rh_fwd + lh_fwd) * 0.5
    kernel = np.ones(5) / 5
    fwd_smooth = np.convolve(fwd, kernel, mode='same')
    threshold = np.percentile(fwd_smooth, 50) + 0.03
    peaks = []
    for i in range(5, len(fwd_smooth) - 5):
        if (fwd_smooth[i] > threshold and
            fwd_smooth[i] >= fwd_smooth[i-1] and
            fwd_smooth[i] >= fwd_smooth[i+1]):
            if not peaks or i - peaks[-1] >= STRIDE:
                peaks.append(i)
    return peaks


def classify_window(jp, center):
    lo = max(0, center - WINDOW // 2)
    hi = min(jp.shape[0], center + WINDOW // 2)
    w = jp[lo:hi]
    rh_fwd = w[:, HAND_R, 2] - w[:, 0, 2]
    lh_fwd = w[:, HAND_L, 2] - w[:, 0, 2]
    rf_fwd = w[:, FOOT_R, 2] - w[:, 0, 2]
    lf_fwd = w[:, FOOT_L, 2] - w[:, 0, 2]
    peak_hand = max(rh_fwd.max(), lh_fwd.max())
    peak_foot = max(rf_fwd.max(), lf_fwd.max())
    hand_travel = abs(np.diff(rh_fwd)).sum() + abs(np.diff(lh_fwd)).sum()
    root_dz = abs(w[-1, 0, 2] - w[0, 0, 2])
    root_dy = abs(w[-1, 0, 1] - w[0, 0, 1])
    motion = hand_travel + root_dz * 10 + root_dy * 10

    if peak_hand > 0.15 and peak_foot < 0.25 and hand_travel > 0.2:
        return "grab" if root_dz > 0.05 else "strike"
    if peak_foot > 0.15:
        return "kick"
    if motion > 0.3:
        return "footwork"
    return "idle"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((G1_DIR / "manifest.json").read_text())
    segments = []

    for c in manifest["clips"]:
        clip_id = c["clip_id"]
        jp, root = load_g1(c["path"])
        T = jp.shape[0]
        if T < 30:
            continue

        peaks = find_reach_events(jp)
        if not peaks:
            # Sample evenly for idle/footwork/stance windows
            peaks = list(range(WINDOW // 2, T - WINDOW // 2, max(STRIDE, 1)))

        for idx, center in enumerate(peaks[:6]):
            label = classify_window(jp, center)
            lo = max(0, center - WINDOW // 2)
            hi = min(T, center + WINDOW // 2)
            if hi - lo < 30:
                continue
            seg = jp[lo:hi].copy()
            seg[:, :, 0] -= seg[0, 0, 0]
            seg[:, :, 2] -= seg[0, 0, 2]
            root_seg = seg[:, 0, :].copy()
            seg_id = f"kf_{clip_id}_{idx:02d}_{label}"
            npz_path = OUT_DIR / f"{seg_id}.npz"
            np.savez_compressed(npz_path, posed_joints=seg, root_positions=root_seg)
            sha = hashlib.sha256(npz_path.read_bytes()).hexdigest()
            rh_z = seg[:, HAND_R, 2]; lh_z = seg[:, HAND_L, 2]
            contact = int(np.argmax((rh_z + lh_z) * 0.5))
            peak_reach = float(max(rh_z[contact], lh_z[contact]))
            segments.append({
                "seg_id": seg_id, "clip_id": clip_id, "label": label,
                "path": str(npz_path.relative_to(ROOT)), "sha256": sha,
                "frames": int(seg.shape[0]), "contact_frame": contact,
                "peak_reach_m": round(peak_reach, 4),
            })

    from collections import Counter
    labels = Counter(s["label"] for s in segments)
    out = {
        "schema": "just-dodge-kungfu-segments-v1",
        "source": "KungfuAthleteBot (Apache-2.0)",
        "runtime_allowed": False,
        "training_allowed": True,
        "total_segments": len(segments),
        "label_counts": dict(labels),
        "segments": segments,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(f"KUNGFU_SEGMENTS total={len(segments)} labels={dict(labels)}")


if __name__ == "__main__":
    raise SystemExit(main())
