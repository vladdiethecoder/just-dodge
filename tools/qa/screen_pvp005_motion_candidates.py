#!/usr/bin/env python3
"""Fail-closed structural and early-tell screen for PVP-005 ARDY candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from motionbricks_service.generate import _pack_413_frames


PARENTS = (-1, 0, 1, 2, 3, 4, 5, 6, 0, 8, 9, 10, 11, 12, 13, 0, 15,
           16, 17, 18, 19, 20, 21, 22, 23, 24, 17, 26, 27, 28, 29, 30, 31, 32)
ACTIONS = ("strike", "block", "grab")
HANDS = (25, 33)
SHOULDERS = (20, 28)
FEET = ((7, (0, 1)), (14, (2, 3)))
FPS = 25
TELL_FRAMES = 8

MAX_SEGMENT_DRIFT_M = 1.0e-4
MAX_JOINT_STEP_M = 0.20
MAX_ANGULAR_STEP_RAD = 0.70
MAX_CONTACT_FOOT_DRIFT_M = 0.05
MAX_ROTATION_ERROR = 1.0e-3
MIN_ROOT_HEIGHT_M = 0.45
MAX_ROOT_HEIGHT_M = 1.20
MAX_ABS_POSITION_M = 3.0


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def segment_drift(positions: np.ndarray) -> float:
    lengths = np.stack(
        [
            np.linalg.norm(positions[:, child] - positions[:, parent], axis=1)
            for child, parent in enumerate(PARENTS)
            if parent >= 0
        ],
        axis=1,
    )
    return float(np.max(np.abs(lengths - lengths[0])))


def max_angular_step(rotations: np.ndarray) -> float:
    relative = np.matmul(np.swapaxes(rotations[:-1], -1, -2), rotations[1:])
    trace = np.trace(relative, axis1=-2, axis2=-1)
    cosine = np.clip((trace - 1.0) * 0.5, -1.0, 1.0)
    return float(np.max(np.arccos(cosine)))


def contacted_foot_drift(positions: np.ndarray, contacts: np.ndarray) -> float:
    maximum = 0.0
    for joint, channels in FEET:
        planted = np.max(contacts[:, channels], axis=1) > 0.5
        start: int | None = None
        for frame, active in enumerate(np.append(planted, False)):
            if active and start is None:
                start = frame
            elif not active and start is not None:
                if frame - start >= 2:
                    anchor = positions[start, joint]
                    drift = np.linalg.norm(positions[start:frame, joint] - anchor, axis=1)
                    maximum = max(maximum, float(np.max(drift)))
                start = None
    return maximum


def event_and_tell(action: str, positions: np.ndarray) -> tuple[int, list[int]]:
    hands = positions[:, HANDS]
    hand_midpoint = hands.mean(axis=1)
    if action == "strike":
        vertical_velocity = np.diff(hand_midpoint[:, 1], prepend=hand_midpoint[0, 1])
        event = 10 + int(np.argmin(vertical_velocity[10:]))
    elif action == "block":
        event = 10 + int(np.argmax(hand_midpoint[10:, 1]))
    else:
        start = len(positions) // 5
        end = len(positions) * 4 // 5
        separation = np.linalg.norm(hands[:, 0] - hands[:, 1], axis=1)
        event = start + int(np.argmin(separation[start:end]))
    tell_end = max(TELL_FRAMES, event - 4)
    tell_start = max(0, tell_end - TELL_FRAMES)
    return event, list(range(tell_start, tell_start + TELL_FRAMES))


def semantic_metrics(action: str, positions: np.ndarray, event: int) -> dict[str, float]:
    hands = positions[:, HANDS]
    midpoint = hands.mean(axis=1)
    separation = np.linalg.norm(hands[:, 0] - hands[:, 1], axis=1)
    root_horizontal = positions[:, 0, (0, 2)]
    horizontal_hand_delta = np.linalg.norm(midpoint[:, (0, 2)] - midpoint[0, (0, 2)], axis=1)
    result = {
        "hand_separation_at_event_m": float(separation[event]),
        "hand_horizontal_range_m": float(np.max(horizontal_hand_delta)),
        "root_horizontal_path_m": float(
            np.linalg.norm(np.diff(root_horizontal, axis=0), axis=1).sum()
        ),
        "hand_height_at_event_m": float(midpoint[event, 1]),
    }
    if action == "strike":
        apex = int(np.argmax(midpoint[: event + 1, 1]))
        result["hand_apex_frame"] = float(apex)
        result["downward_hand_travel_m"] = float(
            midpoint[apex, 1] - np.min(midpoint[apex:, 1])
        )
    elif action == "block":
        shoulder_height = positions[event, SHOULDERS, 1].mean()
        result["guard_height_over_shoulders_m"] = float(midpoint[event, 1] - shoulder_height)
    else:
        result["root_forward_extent_m"] = float(
            np.max(np.linalg.norm(root_horizontal - root_horizontal[0], axis=1))
        )
    return result


def inspect(path: Path, action: str, output: Path) -> tuple[dict, np.ndarray]:
    archive = np.load(path)
    required = ("posed_joints", "global_rot_mats", "root_positions", "foot_contacts")
    missing = [name for name in required if name not in archive]
    if missing:
        raise RuntimeError(f"{path}: missing {missing}")
    positions = np.asarray(archive["posed_joints"], dtype=np.float32)
    rotations = np.asarray(archive["global_rot_mats"], dtype=np.float32)
    roots = np.asarray(archive["root_positions"], dtype=np.float32)
    contacts = np.asarray(archive["foot_contacts"], dtype=np.float32)
    frames = len(positions)
    if positions.shape != (frames, 34, 3):
        raise RuntimeError(f"{path}: posed_joints shape {positions.shape}")
    if rotations.shape != (frames, 34, 3, 3):
        raise RuntimeError(f"{path}: global_rot_mats shape {rotations.shape}")
    if roots.shape != (frames, 3) or contacts.shape != (frames, 4):
        raise RuntimeError(f"{path}: malformed root/contact arrays")
    if frames < 2 * TELL_FRAMES or not all(
        np.isfinite(value).all() for value in (positions, rotations, roots, contacts)
    ):
        raise RuntimeError(f"{path}: too short or non-finite")

    orthogonal = np.matmul(np.swapaxes(rotations, -1, -2), rotations)
    rotation_error = float(np.max(np.abs(orthogonal - np.eye(3, dtype=np.float32))))
    determinant_error = float(np.max(np.abs(np.linalg.det(rotations) - 1.0)))
    drift = segment_drift(positions)
    joint_step = float(np.max(np.linalg.norm(np.diff(positions, axis=0), axis=2)))
    angular_step = max_angular_step(rotations)
    foot_drift = contacted_foot_drift(positions, contacts)
    root_min = float(np.min(roots[:, 1]))
    root_max = float(np.max(roots[:, 1]))
    max_abs = float(np.max(np.abs(positions)))
    event, tell = event_and_tell(action, positions)

    failures = []
    checks = (
        (rotation_error <= MAX_ROTATION_ERROR, f"rotation_error={rotation_error:.6g}"),
        (determinant_error <= MAX_ROTATION_ERROR, f"determinant_error={determinant_error:.6g}"),
        (drift <= MAX_SEGMENT_DRIFT_M, f"segment_drift_m={drift:.6g}"),
        (joint_step <= MAX_JOINT_STEP_M, f"joint_step_m={joint_step:.6g}"),
        (angular_step <= MAX_ANGULAR_STEP_RAD, f"angular_step_rad={angular_step:.6g}"),
        (foot_drift <= MAX_CONTACT_FOOT_DRIFT_M, f"contact_foot_drift_m={foot_drift:.6g}"),
        (root_min >= MIN_ROOT_HEIGHT_M, f"root_height_min_m={root_min:.6g}"),
        (root_max <= MAX_ROOT_HEIGHT_M, f"root_height_max_m={root_max:.6g}"),
        (max_abs <= MAX_ABS_POSITION_M, f"max_abs_position_m={max_abs:.6g}"),
    )
    failures.extend(message for passed, message in checks if not passed)

    packed = _pack_413_frames(roots, positions, rotations)
    packed_path = output / "f413" / f"{path.stem}.413.f32"
    packed_path.parent.mkdir(parents=True, exist_ok=True)
    packed_path.write_bytes(packed.astype("<f4", copy=False).tobytes())

    metric = {
        "action": action,
        "candidate": path.stem,
        "source_path": str(path.relative_to(ROOT)),
        "source_sha256": digest(path),
        "frames": frames,
        "fps": FPS,
        "event_frame": event,
        "tell_frames": tell,
        "rotation_orthogonality_max_error": rotation_error,
        "rotation_determinant_max_error": determinant_error,
        "max_segment_drift_m": drift,
        "max_joint_step_m": joint_step,
        "max_angular_step_rad": angular_step,
        "max_contact_foot_drift_m": foot_drift,
        "root_height_min_m": root_min,
        "root_height_max_m": root_max,
        "max_abs_position_m": max_abs,
        "f413_path": str(packed_path.relative_to(ROOT)),
        "f413_sha256": digest(packed_path),
        "structural_pass": not failures,
        "failures": failures,
        "semantic": semantic_metrics(action, positions, event),
    }
    return metric, positions


def draw_sheet(action: str, rows: list[tuple[dict, np.ndarray]], output: Path, side: bool) -> None:
    figure, axes = plt.subplots(len(rows), TELL_FRAMES, figsize=(20, 2.5 * len(rows)))
    for row, (metric, positions) in enumerate(rows):
        for column, frame in enumerate(metric["tell_frames"]):
            pose = positions[frame]
            axis = axes[row, column]
            horizontal = 2 if side else 0
            for joint, parent in enumerate(PARENTS):
                if parent >= 0:
                    axis.plot(
                        [pose[parent, horizontal], pose[joint, horizontal]],
                        [pose[parent, 1], pose[joint, 1]],
                        color="black" if metric["structural_pass"] else "red",
                        linewidth=1.4,
                    )
            axis.set_aspect("equal")
            axis.set_xlim(-1.25, 1.25)
            axis.set_ylim(0.0, 2.0)
            axis.axis("off")
            axis.set_title(f"{metric['candidate']} f{frame}", fontsize=7)
    view = "side" if side else "front"
    figure.suptitle(f"PVP-005 {action} first-eight tell candidates — {view}")
    figure.tight_layout()
    figure.savefig(output, dpi=150)
    plt.close(figure)


def draw_overview(action: str, rows: list[tuple[dict, np.ndarray]], output: Path, side: bool) -> None:
    columns = 10
    figure, axes = plt.subplots(len(rows), columns, figsize=(25, 2.5 * len(rows)))
    for row, (metric, positions) in enumerate(rows):
        frames = np.rint(np.linspace(0, len(positions) - 1, columns)).astype(int)
        for column, frame in enumerate(frames):
            pose = positions[frame]
            axis = axes[row, column]
            horizontal = 2 if side else 0
            for joint, parent in enumerate(PARENTS):
                if parent >= 0:
                    axis.plot(
                        [pose[parent, horizontal], pose[joint, horizontal]],
                        [pose[parent, 1], pose[joint, 1]],
                        color="black" if metric["structural_pass"] else "red",
                        linewidth=1.4,
                    )
            axis.set_aspect("equal")
            axis.set_xlim(-1.25, 1.25)
            axis.set_ylim(0.0, 2.0)
            axis.axis("off")
            axis.set_title(f"{metric['candidate']} f{frame}", fontsize=7)
    view = "side" if side else "front"
    figure.suptitle(f"PVP-005 {action} full candidate overview — {view}")
    figure.tight_layout()
    figure.savefig(output, dpi=150)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT / "qa_runs/pvp005_motion_admission/candidates",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "qa_runs/pvp005_motion_admission/screen",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    report = {
        "schema": "just-dodge-pvp005-candidate-screen-v1",
        "thresholds": {
            "max_segment_drift_m": MAX_SEGMENT_DRIFT_M,
            "max_joint_step_m": MAX_JOINT_STEP_M,
            "max_angular_step_rad": MAX_ANGULAR_STEP_RAD,
            "max_contact_foot_drift_m": MAX_CONTACT_FOOT_DRIFT_M,
            "max_rotation_error": MAX_ROTATION_ERROR,
            "root_height_m": [MIN_ROOT_HEIGHT_M, MAX_ROOT_HEIGHT_M],
            "max_abs_position_m": MAX_ABS_POSITION_M,
        },
        "actions": {},
    }
    for action in ACTIONS:
        paths = sorted((args.root / action).glob(f"{action}_*.npz"))
        if len(paths) != 8:
            raise RuntimeError(f"expected exactly 8 {action} candidates, got {len(paths)}")
        rows = [inspect(path, action, args.output) for path in paths]
        report["actions"][action] = [metric for metric, _ in rows]
        draw_sheet(action, rows, args.output / f"{action}_tell_front.png", side=False)
        draw_sheet(action, rows, args.output / f"{action}_tell_side.png", side=True)
        draw_overview(action, rows, args.output / f"{action}_overview_front.png", side=False)
        draw_overview(action, rows, args.output / f"{action}_overview_side.png", side=True)

    report_path = args.output / "candidate_screen.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    counts = {
        action: sum(item["structural_pass"] for item in values)
        for action, values in report["actions"].items()
    }
    print(json.dumps({"structural_pass": counts, "report_sha256": digest(report_path)}, sort_keys=True))
    passed = all(count == 8 for count in counts.values())
    print(f"PVP005_CANDIDATE_SCREEN={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
