#!/usr/bin/env python3
"""Screen authorized BONES-SEED G1 dodge candidates for backward-dodge semantics.

Extracts specific CSV tar members, converts through the *exact same* official
MotionBricks path as ``validate_bones_seed_g1.py``, and renders full-clip
24-frame contact sheets with root trajectory.

The pipeline is intentionally NOT reimplemented — CSV parsing, provenance,
and converter access are delegated to the validated reference so the screener
cannot drift from proven local behaviour.

Outputs go to ``bones-seed/derived/screening/<motion_id>/``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path

import numpy as np
import torch
from matplotlib import pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from motionbricks_service.generate import _pack_413_frames, init_official_service
from tools.qa.validate_bones_seed_g1 import (
    load_csv_as_mujoco_qpos,
    provenance_row,
)
from tools.qa.visual_verify_primitives import G1_PARENTS, parse_g1_frame, render_pose

# ── constants ────────────────────────────────────────────────────────────────
G1_ARCHIVE = PROJECT_ROOT / "bones-seed" / "g1.tar.gz"
INDEX_PATH = PROJECT_ROOT / "bones-seed" / "just_dodge_g1_member_index.json"
SCREENING_ROOT = PROJECT_ROOT / "bones-seed" / "derived" / "screening"

MAX_JOINT_STEP_METERS = 0.2
MAX_SEGMENT_DRIFT_METERS = 1.0e-4

# ── extraction ───────────────────────────────────────────────────────────────


def extract_csv_member(tar_path: Path, member_path: str) -> bytes:
    """Extract exactly one member from the tar archive."""
    with tarfile.open(tar_path, "r:gz") as tf:
        info = tf.getmember(member_path)
        f = tf.extractfile(info)
        if f is None:
            raise FileNotFoundError(f"member {member_path} not found in {tar_path}")
        return f.read()


# ── metrics ──────────────────────────────────────────────────────────────────


def compute_metrics(frames: np.ndarray) -> dict:
    """Compute continuity, displacement, and heading-relative metrics."""
    global_positions = np.stack([parse_g1_frame(frame) for frame in frames])
    if not np.isfinite(frames).all() or not np.isfinite(global_positions).all():
        raise ValueError("non-finite values in converted frames")

    steps = np.linalg.norm(np.diff(global_positions, axis=0), axis=2)
    max_step = float(np.max(steps))

    # segment drift
    lengths = []
    for child, parent in enumerate(G1_PARENTS):
        if parent >= 0:
            lengths.append(
                np.linalg.norm(
                    global_positions[:, child] - global_positions[:, parent], axis=1
                )
            )
    segment_values = np.stack(lengths, axis=1)
    max_drift = float(np.max(np.abs(segment_values - segment_values[0])))

    # root displacement (world)
    root = global_positions[:, 0]
    world_horizontal_net = root[-1, [0, 2]] - root[0, [0, 2]]
    world_displacement = (root[-1] - root[0]).tolist()
    root_path_length = float(np.sum(np.linalg.norm(np.diff(root, axis=0), axis=1)))

    # heading-relative displacement
    # Packing: heading = atan2(rot[:,0,0,2], rot[:,0,2,2]) → heading=0 faces +Z
    init_heading = _initial_heading_radians(frames)
    forward = np.array([np.sin(init_heading), np.cos(init_heading)], dtype=np.float64)
    right = np.array([np.cos(init_heading), -np.sin(init_heading)], dtype=np.float64)
    forward_displacement_m = float(np.dot(world_horizontal_net, forward))
    lateral_displacement_m = float(np.dot(world_horizontal_net, right))
    backward_displacement_m = -forward_displacement_m

    # heading change over clip
    final_heading = _initial_heading_radians(frames[-5:])
    heading_change = float(np.arctan2(np.sin(final_heading - init_heading), np.cos(final_heading - init_heading)))

    return {
        "frame_count": int(len(frames)),
        "max_joint_step_m": max_step,
        "segment_drift_m": max_drift,
        "root_displacement": world_displacement,
        "root_path_length_m": root_path_length,
        "root_trajectory": root.tolist(),
        "initial_heading": float(init_heading),
        "heading_change": heading_change,
        "backward_displacement_m": backward_displacement_m,
        "lateral_displacement_m": lateral_displacement_m,
        "lateral_to_backward_ratio": abs(lateral_displacement_m) / (abs(backward_displacement_m) + 1e-6),
    }


def _initial_heading_radians(frames: np.ndarray) -> float:
    """Return the initial smoothed heading from the first few frames."""
    n = min(5, frames.shape[0])
    cos_mean = float(np.mean(frames[:n, 3]))
    sin_mean = float(np.mean(frames[:n, 4]))
    return float(np.arctan2(sin_mean, cos_mean))


# ── rendering ────────────────────────────────────────────────────────────────


def render_contact_sheet(
    frames: np.ndarray,
    metrics: dict,
    motion_id: str,
    output_path: Path,
) -> None:
    """Render a 12-frame front+side contact sheet with root trajectory."""
    n_frames = len(frames)
    n_cols = 24
    indices = np.linspace(0, n_frames - 1, n_cols, dtype=int)

    fig = plt.figure(figsize=(3 * n_cols, 8))
    gs = fig.add_gridspec(3, n_cols, height_ratios=[1, 1, 0.6])

    # Front views (X-Y)
    for col, idx in enumerate(indices):
        ax = fig.add_subplot(gs[0, col])
        positions = parse_g1_frame(frames[idx])
        render_pose(ax, positions, f"f{idx}", "front")

    # Side views (Z-Y)
    for col, idx in enumerate(indices):
        ax = fig.add_subplot(gs[1, col])
        positions = parse_g1_frame(frames[idx])
        render_pose(ax, positions, f"f{idx}", "side")

    # Root trajectory
    ax_traj = fig.add_subplot(gs[2, :])
    root = np.array(metrics["root_trajectory"])
    ax_traj.plot(root[:, 0], root[:, 2], "k-", linewidth=0.8, alpha=0.6)
    ax_traj.scatter(root[0, 0], root[0, 2], c="green", s=80, label="start", zorder=5)
    ax_traj.scatter(root[-1, 0], root[-1, 2], c="red", s=80, label="end", zorder=5)
    for i, idx in enumerate(indices):
        ax_traj.scatter(
            root[idx, 0], root[idx, 2], c="blue", s=20, zorder=3, alpha=0.6
        )
    ax_traj.set_xlabel("X (m)")
    ax_traj.set_ylabel("Z (m)")
    ax_traj.set_title(
        f"Root trajectory — net Δ=({root[-1, 0] - root[0, 0]:+.2f}, {root[-1, 2] - root[0, 2]:+.2f}) m"
    )
    ax_traj.legend(fontsize=7)
    ax_traj.set_aspect("equal")

    disp = np.array(metrics["root_displacement"])
    fig.suptitle(
        f"BONES-SEED {motion_id} — {n_frames} frames, "
        f"root Δ=({disp[0]:+.2f},{disp[1]:+.2f},{disp[2]:+.2f})m, "
        f"path={metrics['root_path_length_m']:.2f}m",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


# ── screening ────────────────────────────────────────────────────────────────


def screen_candidate(
    motion_id: str,
    archive_member: str,
    converter,
    dataset_root: Path,
    screening_dir: Path,
) -> dict:
    """Screen a single candidate. Returns admission verdict dict."""
    screening_dir.mkdir(parents=True, exist_ok=True)

    # Extract CSV and write to temp path for the reference loader
    csv_bytes = extract_csv_member(G1_ARCHIVE, archive_member)
    csv_path = screening_dir / f"{motion_id}.csv"
    csv_path.write_bytes(csv_bytes)

    # Compute CSV SHA-256
    csv_sha256 = hashlib.sha256(csv_bytes).hexdigest()

    # Provenance: verify against the authorized index; non-fatal for screening
    provenance_ok = False
    provenance_warning = None
    try:
        _, _, _ = provenance_row(dataset_root, motion_id)
        provenance_ok = True
    except Exception as exc:
        provenance_warning = str(exc)

    # Reuse the exact validated CSV→qpos parser
    qpos = load_csv_as_mujoco_qpos(csv_path)

    # Exact same conversion path as validate_bones_seed_g1.py
    with torch.no_grad():
        positions, rotations = converter.convert_mujoco_qpos_to_motion_transforms(
            torch.from_numpy(qpos)[None]
        )
    frames = _pack_413_frames(
        positions[0, :, 0, :].cpu().numpy(),
        positions[0].cpu().numpy(),
        rotations[0].cpu().numpy(),
    )

    # Save raw frames
    raw_path = screening_dir / f"{motion_id}.413.f32"
    raw_path.write_bytes(frames.astype("<f4", copy=False).tobytes())

    # Metrics
    metrics = compute_metrics(frames)
    if metrics["max_joint_step_m"] > MAX_JOINT_STEP_METERS:
        return {
            "motion_id": motion_id,
            "archive_member": archive_member,
            "technical_pass": False,
            "reason": f"max_joint_step {metrics['max_joint_step_m']:.6f}m > {MAX_JOINT_STEP_METERS}m",
            "metrics": metrics,
            "contact_sheet": None,
        }
    if metrics["segment_drift_m"] > MAX_SEGMENT_DRIFT_METERS:
        return {
            "motion_id": motion_id,
            "archive_member": archive_member,
            "technical_pass": False,
            "reason": f"segment_drift {metrics['segment_drift_m']:.6g}m > {MAX_SEGMENT_DRIFT_METERS}m",
            "metrics": metrics,
            "contact_sheet": None,
        }

    # Contact sheet
    sheet_path = screening_dir / f"{motion_id}_contact_sheet.png"
    render_contact_sheet(frames, metrics, motion_id, sheet_path)

    return {
        "motion_id": motion_id,
        "archive_member": archive_member,
        "csv_sha256": csv_sha256,
        "provenance_ok": provenance_ok,
        "provenance_warning": provenance_warning,
        "technical_pass": True,
        "metrics": metrics,
        "contact_sheet": str(sheet_path),
        "raw_frames": str(raw_path),
    }


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "motion_ids", nargs="*", help="Screen specific motion_ids"
    )
    parser.add_argument(
        "--all", action="store_true", help="Screen all dodge-named candidates"
    )
    parser.add_argument(
        "--negative-control",
        action="store_true",
        help="Run on the known-bad ib_dodge_back_L_001__A437",
    )
    parser.add_argument(
        "--manifest-name",
        default=None,
        help="Run-specific manifest basename (default: manifest_TIMESTAMP.json)",
    )
    args = parser.parse_args()

    dataset_root = PROJECT_ROOT / "bones-seed"

    if not G1_ARCHIVE.is_file():
        print(f"ERROR: archive not found: {G1_ARCHIVE}", file=sys.stderr)
        sys.exit(1)

    # Initialize the official service once for all candidates
    service = init_official_service()
    converter = service["agent"]._converter  # exact path from reference validator

    index = json.loads(INDEX_PATH.read_text())
    members = index["members_by_motion_id"]

    if args.negative_control:
        candidates = {
            "ib_dodge_back_L_001__A437": members["ib_dodge_back_L_001__A437"]
        }
    elif args.motion_ids:
        missing = [mid for mid in args.motion_ids if mid not in members]
        if missing:
            print(
                f"ERROR: motion_ids not in index: {', '.join(missing)}",
                file=sys.stderr,
            )
            sys.exit(1)
        candidates = {mid: members[mid] for mid in args.motion_ids}
    elif args.all:
        dodge_ids = [
            mid
            for mid in members
            if "dodge" in mid.lower()
            and mid != "ib_dodge_back_L_001__A437"
        ]
        candidates = {mid: members[mid] for mid in dodge_ids}
    else:
        # Default: negative control
        candidates = {
            "ib_dodge_back_L_001__A437": members["ib_dodge_back_L_001__A437"]
        }

    results = []
    for mid, archive_paths in candidates.items():
        member_path = archive_paths[0]
        print(f"\n=== Screening {mid} ===", file=sys.stderr)
        print(f"  member: {member_path}", file=sys.stderr)
        screening_dir = SCREENING_ROOT / mid
        try:
            result = screen_candidate(
                mid, member_path, converter, dataset_root, screening_dir
            )
            # Write per-candidate receipt immediately
            receipt_path = screening_dir / f"{mid}.screening.json"
            receipt_path.write_text(json.dumps(result, indent=2, default=str))
            results.append(result)
            if result.get("technical_pass"):
                print(f"  technical: PASS", file=sys.stderr)
                m = result["metrics"]
                print(f"  frames: {m['frame_count']}", file=sys.stderr)
                disp = m["root_displacement"]
                print(f"  world Δ: ({disp[0]:+.3f}, {disp[1]:+.3f}, {disp[2]:+.3f})m", file=sys.stderr)
                print(f"  backward: {m.get('backward_displacement_m', float('nan')):+.3f}m", file=sys.stderr)
                print(f"  lateral:  {m.get('lateral_displacement_m', float('nan')):+.3f}m", file=sys.stderr)
                print(f"  lat/back: {m.get('lateral_to_backward_ratio', float('nan')):.1f}", file=sys.stderr)
                print(f"  init heading: {m.get('initial_heading', float('nan')):.3f} rad", file=sys.stderr)
                print(f"  heading Δ:   {m.get('heading_change', float('nan')):.3f} rad", file=sys.stderr)
                print(f"  sheet: {result['contact_sheet']}", file=sys.stderr)
            else:
                print(
                    f"  technical: FAIL — {result.get('reason', 'unknown')}",
                    file=sys.stderr,
                )
        except Exception as exc:
            exc_result = {
                "motion_id": mid,
                "archive_member": member_path,
                "technical_pass": False,
                "reason": str(exc),
                "contact_sheet": None,
            }
            results.append(exc_result)
            print(f"  ERROR: {exc}", file=sys.stderr)

    # Write manifest with timestamp-as-namespace hygiene
    from datetime import datetime, timezone
    manifest_name = args.manifest_name or f"manifest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    manifest_path = SCREENING_ROOT / manifest_name
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nManifest: {manifest_path}", file=sys.stderr)

    tech_pass = sum(1 for r in results if r.get("technical_pass"))
    print(
        f"\nSummary: {len(results)} screened, {tech_pass} technical pass, "
        f"{len(results) - tech_pass} failed",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()