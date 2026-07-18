#!/usr/bin/env python3
"""Segment the 59 CMU G1-retargeted combat clips into action-labeled windows.

Each CMU clip contains hundreds-to-thousands of frames at 60fps. We segment
them into short windows (~120 frames = 2s) centered on peak forward reach
events, then classify each window as grab/strike/kick/other based on the
hand and foot motion patterns.

Output: qa_runs/grab07_combat_corpus/segments/<clip_id>_<idx>_<label>.npz
  posed_joints: [T, 34, 3] world-space (hips == root)
  root_positions: [T, 3]
"""
from __future__ import annotations
import json, hashlib, os, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
G1_DIR = ROOT / "qa_runs/grab07_combat_corpus/g1"
OUT_DIR = ROOT / "qa_runs/grab07_combat_corpus/segments"
HAND_R, HAND_L = 33, 25
FOOT_R, FOOT_L = 23, 18
WINDOW = 120  # 2 seconds at 60fps
STRIDE = 60   # 1 second stride for overlap

CMU_INDEX = {
    "02_05":"punch/strike","13_10":"jump grab reach","13_12":"jump grab reach",
    "13_17":"boxing","13_18":"boxing","14_07":"jump grab reach",
    "14_08":"jump grab reach","14_09":"jump grab reach",
    "15_13":"boxing","17_10":"boxing","56_02":"fists up grab smash",
    "56_03":"grab smash throw punches","56_04":"fists up grab punches",
    "56_06":"throw punches grab skip","74_03":"kick","74_04":"kick",
    "74_05":"kick","74_06":"kick","75_16":"jump kick","76_01":"retreat punch",
    "79_08":"boxing","80_10":"boxing","85_05":"HandStandKicks",
    "85_06":"KickFlip","86_01":"jumps kicks punches",
    "86_02":"squats run punches","86_03":"running kicking",
    "86_04":"stretching punching chopping","86_05":"punching chopping",
    "86_06":"running kicking punching knee","86_08":"kicking punching",
    "87_01":"jump kick spin","88_04":"spin kicks flips",
    "88_06":"jump spin kick","90_05":"jump kick","90_06":"jump kick",
    "90_07":"jump kick","111_19":"punch kick","113_13":"punch and kick",
    "135_04":"front kick (martial arts)","141_14":"punch and kick",
    "143_23":"punching","143_24":"kicking",
    "144_05":"front kick","144_06":"front kick",
    "144_07":"left blocks","144_08":"left blocks",
    "144_09":"left front kick","144_10":"left front kick",
    "144_13":"left punch seq","144_14":"left punch seq",
    "144_20":"punch sequence","144_21":"punch sequence",
    "144_26":"right blocks","144_27":"right blocks",
    "22_17":"arm wrestle","22_20":"violence threaten strike",
    "23_17":"arm wrestle","23_20":"violence threaten strike",
}


def load_g1(path):
    d = np.load(path, allow_pickle=True).item()
    return d['joint_positions'].astype(np.float64)


def find_reach_events(jp):
    """Find frames where both hands reach forward (high hand Z relative to root)."""
    rh_fwd = jp[:, HAND_R, 2] - jp[:, 0, 2]  # hand Z relative to root Z
    lh_fwd = jp[:, HAND_L, 2] - jp[:, 0, 2]
    fwd = (rh_fwd + lh_fwd) * 0.5

    # Smooth
    kernel = np.ones(5) / 5
    fwd_smooth = np.convolve(fwd, kernel, mode='same')

    # Find local maxima above a threshold
    threshold = np.percentile(fwd_smooth, 60) + 0.05
    peaks = []
    for i in range(5, len(fwd_smooth) - 5):
        if (fwd_smooth[i] > threshold and
            fwd_smooth[i] >= fwd_smooth[i-1] and
            fwd_smooth[i] >= fwd_smooth[i+1]):
            # Check separation from last peak
            if not peaks or i - peaks[-1] >= STRIDE:
                peaks.append(i)
    return peaks, fwd_smooth


def classify_window(jp, center):
    """Classify a window centered at `center` based on motion patterns."""
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
    root_dz = w[-1, 0, 2] - w[0, 0, 2]

    # Grab: hands reach forward together, feet planted (low foot forward)
    if peak_hand > 0.2 and peak_foot < 0.3 and hand_travel > 0.3:
        return "grab"
    # Kick: feet extend forward significantly
    if peak_foot > 0.2:
        return "kick"
    # Strike: hands reach with less two-hand convergence
    if peak_hand > 0.15 or hand_travel > 0.2:
        return "strike"
    return "other"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    segments = []

    for npy in sorted(G1_DIR.glob("*.npy")):
        clip_id = npy.stem
        jp = load_g1(npy)
        T = jp.shape[0]
        desc = CMU_INDEX.get(clip_id, "?")

        peaks, _ = find_reach_events(jp)
        if not peaks:
            # Fallback: sample evenly
            peaks = list(range(WINDOW//2, T - WINDOW//2, max(STRIDE, 1)))

        for idx, center in enumerate(peaks[:8]):  # max 8 windows per clip
            label = classify_window(jp, center)
            if label == "other":
                continue

            lo = max(0, center - WINDOW // 2)
            hi = min(T, center + WINDOW // 2)
            if hi - lo < 30:
                continue

            seg = jp[lo:hi].copy()
            # Normalize: center root XZ at origin
            seg[:, :, 0] -= seg[0, 0, 0]
            seg[:, :, 2] -= seg[0, 0, 2]

            root = seg[:, 0, :].copy()
            seg_id = f"{clip_id}_{idx:02d}_{label}"
            npz_path = OUT_DIR / f"{seg_id}.npz"
            np.savez_compressed(npz_path, posed_joints=seg, root_positions=root)

            sha = hashlib.sha256(npz_path.read_bytes()).hexdigest()
            # Compute contact-frame metrics
            rh_z = seg[:, HAND_R, 2]
            lh_z = seg[:, HAND_L, 2]
            contact = int(np.argmax((rh_z + lh_z) * 0.5))
            peak_reach = float(max(rh_z[contact], lh_z[contact]))

            segments.append({
                "seg_id": seg_id, "clip_id": clip_id, "label": label,
                "source_desc": desc, "path": str(npz_path.relative_to(ROOT)),
                "sha256": sha, "frames": int(seg.shape[0]),
                "contact_frame": contact, "peak_reach_m": round(peak_reach, 4),
            })

    # Deduplicate by seg_id
    seen = set()
    unique = []
    for s in segments:
        if s["seg_id"] not in seen:
            seen.add(s["seg_id"])
            unique.append(s)

    from collections import Counter
    labels = Counter(s["label"] for s in unique)
    clips = Counter(s["clip_id"] for s in unique)

    manifest = {
        "schema": "just-dodge-grab07-combat-segments-v1",
        "source": "CMU Graphics Lab Motion Capture Database (public domain)",
        "url": "http://mocap.cs.cmu.edu/",
        "runtime_allowed": False,
        "training_allowed": True,
        "pipeline": "ASF/AMC -> BVH (convert_cmu_amc_to_bvh.py) -> G1 retarget (retarget_to_g1.py) -> segment",
        "window_frames": WINDOW,
        "stride_frames": STRIDE,
        "total_segments": len(unique),
        "label_counts": dict(labels),
        "source_clip_count": len(clips),
        "segments": unique,
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(f"COMBAT_SEGMENTS total={len(unique)} labels={dict(labels)} clips={len(clips)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
