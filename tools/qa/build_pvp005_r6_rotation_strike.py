#!/usr/bin/env python3
"""Build and falsify one dense rotation-conditioned PVP005-R6 Strike.

This stage does not run diffusion. It solves the rejected endpoint-v4 Strike
onto the pinned ARDY G1Skeleton34, compiles every global rotation plus the
root trajectory through the shipped ARDY motion representation, reconstructs
FK from those exact conditioned channels, and writes output only when every
mechanical gate passes.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARDY = Path("/run/media/vdubrov/NVMe-Storage1/ardy")
DEFAULT_SPEC = ROOT / "assets/qa/pvp005_ardy_action_endpoints_v4.json"
DEFAULT_SOURCE = ROOT / "assets/motion/pvp005_candidates/strike/strike_02.ardy.npz"
DEFAULT_SOURCE_MANIFEST = ROOT / "assets/motion/pvp005_candidates/manifest.json"
G1_MODEL = "ARDY-G1-RP-25FPS-Horizon52"
G1_ROOT_HEIGHT_M = 0.78
FRAMES = 52
FPS = 25
SOURCE_RETIME_ANCHORS = ((0, 38), (15, 54), (27, 66), (51, 89))
MAX_ENDPOINT_ERROR_M = 0.01
MAX_GRIP_ANGLE_ERROR_DEG = 3.0
MAX_ANGULAR_STEP_RAD = 0.7
MAX_FLOOR_PENETRATION_M = 1.0e-4
MIN_PREPARATION_COM_DISPLACEMENT_M = 0.03
OPTIMIZATION_STEPS = 1_500
FLOOR_CLEARANCE_MARGIN_M = 0.002
TEMPORAL_GUARD_RAD = 0.62


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def refuse_existing(*paths: Path) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise SystemExit(f"refusing to overwrite PVP005-R6 output: {existing}")


def retime_source_indices() -> list[int]:
    result = []
    for frame in range(FRAMES):
        for (left_frame, left_source), (right_frame, right_source) in zip(
            SOURCE_RETIME_ANCHORS,
            SOURCE_RETIME_ANCHORS[1:],
            strict=True,
        ):
            if left_frame <= frame <= right_frame:
                amount = (frame - left_frame) / (right_frame - left_frame)
                result.append(round(left_source + amount * (right_source - left_source)))
                break
    if len(result) != FRAMES:
        raise AssertionError("source retime does not cover the ARDY horizon")
    return result


def interpolate_keyposes(keyposes: list[dict], key: str) -> np.ndarray:
    output = []
    for frame in range(FRAMES):
        for left, right in zip(keyposes, keyposes[1:], strict=True):
            if left["frame"] <= frame <= right["frame"]:
                amount = (frame - left["frame"]) / (right["frame"] - left["frame"])
                output.append(
                    [
                        (1.0 - amount) * a + amount * b
                        for a, b in zip(left[key], right[key], strict=True)
                    ]
                )
                break
    if len(output) != FRAMES:
        raise AssertionError(f"keypose interpolation for {key} does not cover the horizon")
    return np.asarray(output, dtype=np.float64)


def _slerp_direction(left: np.ndarray, right: np.ndarray, amount: float) -> np.ndarray:
    left = left / np.linalg.norm(left)
    right = right / np.linalg.norm(right)
    dot = float(np.clip(np.dot(left, right), -1.0, 1.0))
    if dot > 0.9995:
        blended = (1.0 - amount) * left + amount * right
        return blended / np.linalg.norm(blended)
    if dot < -0.9995:
        axis = np.cross(left, np.asarray([0.0, 1.0, 0.0]))
        if np.linalg.norm(axis) < 1.0e-6:
            axis = np.cross(left, np.asarray([1.0, 0.0, 0.0]))
        axis /= np.linalg.norm(axis)
        angle = math.pi * amount
        return (
            left * math.cos(angle)
            + np.cross(axis, left) * math.sin(angle)
            + axis * np.dot(axis, left) * (1.0 - math.cos(angle))
        )
    angle = math.acos(dot)
    scale = math.sin(angle)
    return (
        math.sin((1.0 - amount) * angle) / scale * left
        + math.sin(amount * angle) / scale * right
    )


def rigid_weapon_hand_targets(keyposes: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    first = keyposes[0]
    first_pommel = np.asarray(first["weapon_pommel_world_m"], dtype=np.float64)
    first_axis = np.asarray(first["weapon_tip_world_m"], dtype=np.float64) - first_pommel
    first_axis /= np.linalg.norm(first_axis)
    right_offset = float(
        np.dot(np.asarray(first["right_hand_world_m"]) - first_pommel, first_axis)
    )
    left_offset = float(
        np.dot(np.asarray(first["left_hand_world_m"]) - first_pommel, first_axis)
    )
    if abs((right_offset - left_offset) - 0.160) > 1.0e-6:
        raise SystemExit("W0 keypose grip separation drift")

    left_targets = []
    right_targets = []
    for frame in range(FRAMES):
        for left, right in zip(keyposes, keyposes[1:], strict=True):
            if left["frame"] <= frame <= right["frame"]:
                amount = (frame - left["frame"]) / (right["frame"] - left["frame"])
                pommel = (1.0 - amount) * np.asarray(
                    left["weapon_pommel_world_m"], dtype=np.float64
                ) + amount * np.asarray(right["weapon_pommel_world_m"], dtype=np.float64)
                left_axis = np.asarray(left["weapon_tip_world_m"], dtype=np.float64) - np.asarray(
                    left["weapon_pommel_world_m"], dtype=np.float64
                )
                right_axis = np.asarray(
                    right["weapon_tip_world_m"], dtype=np.float64
                ) - np.asarray(right["weapon_pommel_world_m"], dtype=np.float64)
                axis = _slerp_direction(left_axis, right_axis, amount)
                left_targets.append(pommel + axis * left_offset)
                right_targets.append(pommel + axis * right_offset)
                break
    if len(left_targets) != FRAMES:
        raise AssertionError("rigid W0 interpolation does not cover the ARDY horizon")
    return np.asarray(left_targets), np.asarray(right_targets)


def parse_g1_hinges(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8").split("pub const G1_NODES", 1)[1]
    blocks = re.findall(r"G1NodeV1 \{(.*?)\n    \},", text, re.DOTALL)
    nodes = []
    for block in blocks:
        name = re.search(r'name: "([^"]+)"', block)
        if name is None:
            continue
        kind = re.search(r"kind: G1NodeKind::(\w+)", block)
        axis = re.search(r"hinge_axis_q30: \[([^]]+)\]", block)
        limits = re.search(r"limits_microradians: \[([^]]+)\]", block)
        if kind is None or axis is None or limits is None:
            raise SystemExit(f"incomplete canonical G1 node {name.group(1)}")
        nodes.append(
            {
                "name": name.group(1),
                "kind": kind.group(1),
                "axis": tuple(int(value.strip()) for value in axis.group(1).split(",")),
                "limits": tuple(
                    int(value.strip()) / 1_000_000.0 for value in limits.group(1).split(",")
                ),
            }
        )
    if len(nodes) != 34 or sum(node["kind"] == "ActuatedHinge" for node in nodes) != 29:
        raise SystemExit("canonical G1 articulation is not the expected 34-node/29-hinge model")
    return nodes


def target_foot_positions(action: dict, neutral: np.ndarray) -> np.ndarray:
    indices = (6, 7, 13, 14)
    targets = np.empty((FRAMES, len(indices), 3), dtype=np.float64)
    swings = {item["side"]: item for item in action["swing_intervals"]}

    def side_offset(side: str, frame: int) -> tuple[float, float, float]:
        swing = swings[side]
        start, end = swing["frames"]
        if frame < start:
            xz = swing["from_anchor_offset_xz_m"]
            clearance = 0.0
        elif frame <= end:
            amount = (frame - start) / (end - start)
            xz = [
                (1.0 - amount) * a + amount * b
                for a, b in zip(
                    swing["from_anchor_offset_xz_m"],
                    swing["to_anchor_offset_xz_m"],
                    strict=True,
                )
            ]
            clearance = swing["toe_clearance_m"] * math.sin(math.pi * amount)
        else:
            xz = swing["to_anchor_offset_xz_m"]
            clearance = 0.0
        return float(xz[0]), float(xz[1]), float(clearance)

    for frame in range(FRAMES):
        left_x, left_z, left_clearance = side_offset("left", frame)
        right_x, right_z, right_clearance = side_offset("right", frame)
        for slot, (joint, x, z, clearance) in enumerate(
            (
                (6, left_x, left_z, left_clearance),
                (7, left_x, left_z, left_clearance),
                (13, right_x, right_z, right_clearance),
                (14, right_x, right_z, right_clearance),
            )
        ):
            targets[frame, slot] = neutral[joint] + np.asarray(
                [x, G1_ROOT_HEIGHT_M, z], dtype=np.float64
            )
            targets[frame, slot, 1] = (
                max(0.0, targets[frame, slot, 1])
                + FLOOR_CLEARANCE_MARGIN_M
                + clearance
            )
    return targets


def skew(value):
    import torch

    zero = torch.zeros_like(value[..., 0])
    x_value, y_value, z_value = value.unbind(-1)
    return torch.stack(
        (
            zero,
            -z_value,
            y_value,
            z_value,
            zero,
            -x_value,
            -y_value,
            x_value,
            zero,
        ),
        dim=-1,
    ).reshape(*value.shape[:-1], 3, 3)


def projected_hinge_angles(local_rotations, nodes):
    import torch

    angles = []
    limits = []
    joint_indices = []
    for index, node in enumerate(nodes):
        if node["kind"] != "ActuatedHinge":
            continue
        axis = node["axis"]
        rotation = local_rotations[:, index]
        if axis[0]:
            angle = torch.atan2(rotation[:, 2, 1] * math.copysign(1.0, axis[0]), rotation[:, 1, 1])
        elif axis[1]:
            angle = torch.atan2(-rotation[:, 2, 0] * math.copysign(1.0, axis[1]), rotation[:, 0, 0])
        else:
            angle = torch.atan2(rotation[:, 1, 0] * math.copysign(1.0, axis[2]), rotation[:, 0, 0])
        angles.append(angle)
        limits.append(node["limits"])
        joint_indices.append(index)
    return torch.stack(angles, dim=1), limits, joint_indices


def maximum_angular_step(global_rotations) -> float:
    import torch

    relative = global_rotations[:-1].transpose(-1, -2) @ global_rotations[1:]
    trace = relative.diagonal(dim1=-2, dim2=-1).sum(-1)
    return float(torch.acos(((trace - 1.0) * 0.5).clamp(-1.0, 1.0)).max())


def solve_rotation_trajectory(
    skeleton,
    action: dict,
    source_local: np.ndarray,
    nodes,
    steps: int = OPTIMIZATION_STEPS,
    lr: float = 0.025,
    hand_weight: float = 300.0,
):
    import torch

    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    dtype = torch.float64
    skeleton = skeleton.to(device="cpu", dtype=dtype)
    base = torch.as_tensor(source_local[retime_source_indices()], dtype=dtype)
    root = torch.as_tensor(
        [[x_value, G1_ROOT_HEIGHT_M, z_value] for x_value, z_value in action["root_xz_m"]],
        dtype=dtype,
    )
    left_targets, right_targets = rigid_weapon_hand_targets(action["hand_keyposes"])
    left_hand = torch.as_tensor(left_targets, dtype=dtype)
    right_hand = torch.as_tensor(right_targets, dtype=dtype)
    feet = torch.as_tensor(
        target_foot_positions(action, skeleton.neutral_joints.detach().cpu().numpy()), dtype=dtype
    )
    foot_indices = [6, 7, 13, 14]
    delta = torch.zeros((FRAMES, 34, 3), dtype=dtype, requires_grad=True)
    optimizer = torch.optim.Adam([delta], lr=lr)
    # Scale LR-decay milestones to the requested step count (same 8/15 and 4/5
    # fractions as the 1500-step baseline).
    milestones = [max(1, int(steps * 8 / 15)), max(1, int(steps * 4 / 5))]
    scheduler = torch.optim.lr_scheduler.MultiStepLR(
        optimizer, milestones=milestones, gamma=0.2
    )
    best = None
    best_score = float("inf")

    for iteration in range(steps + 1):
        optimizer.zero_grad()
        local = torch.matrix_exp(skew(delta)) @ base
        global_rotations, positions, _ = skeleton.fk(local, root)
        hand_loss = (
            (positions[:, 25] - left_hand).square().sum(-1).mean()
            + (positions[:, 33] - right_hand).square().sum(-1).mean()
        )
        foot_loss = (positions[:, foot_indices] - feet).square().sum(-1).mean()
        smoothness = (delta[1:] - delta[:-1]).square().mean()
        regularization = delta.square().mean()
        floor_loss = torch.relu(FLOOR_CLEARANCE_MARGIN_M - positions[..., 1]).square().mean()
        relative_rotations = global_rotations[:-1].transpose(-1, -2) @ global_rotations[1:]
        relative_cosine = (
            relative_rotations.diagonal(dim1=-2, dim2=-1).sum(-1) - 1.0
        ) * 0.5
        temporal_guard_loss = torch.relu(
            math.cos(TEMPORAL_GUARD_RAD) - relative_cosine
        ).square().mean()
        angles, limits, _ = projected_hinge_angles(local, nodes)
        limit_loss = torch.zeros((), dtype=dtype)
        for column, (low, high) in enumerate(limits):
            limit_loss = limit_loss + torch.relu(low - angles[:, column]).square().mean()
            limit_loss = limit_loss + torch.relu(angles[:, column] - high).square().mean()
        loss = (
            hand_weight * hand_loss
            + 180.0 * foot_loss
            + 30.0 * smoothness
            + 0.4 * regularization
            + 2_000.0 * floor_loss
            + 2_000.0 * temporal_guard_loss
            + 80.0 * limit_loss
        )
        loss.backward()
        optimizer.step()
        scheduler.step()

        if iteration >= 200 and iteration % 10 == 0:
            with torch.no_grad():
                hand_error = torch.linalg.vector_norm(
                    torch.stack(
                        (positions[:, 25] - left_hand, positions[:, 33] - right_hand), dim=1
                    ),
                    dim=-1,
                ).max()
                foot_error = torch.linalg.vector_norm(
                    positions[:, foot_indices] - feet, dim=-1
                ).max()
                angular_step = maximum_angular_step(global_rotations)
                floor_penetration = max(0.0, -float(positions[..., 1].min()))
                score = (
                    float(hand_error + foot_error)
                    + 10.0 * max(0.0, angular_step - MAX_ANGULAR_STEP_RAD)
                    + 10.0 * floor_penetration
                )
                if score < best_score:
                    best_score = score
                    best = delta.detach().clone()

    if best is None:
        raise SystemExit("rotation solve produced no candidate state")
    with torch.no_grad():
        local = torch.matrix_exp(skew(best)) @ base
        global_rotations, positions, _ = skeleton.fk(local, root)
    return {
        "local_rotations": local,
        "global_rotations": global_rotations,
        "positions": positions,
        "root": root,
        "left_hand_targets": left_hand,
        "right_hand_targets": right_hand,
        "foot_targets": feet,
    }


class DenseRotationConstraint:
    def __init__(self, root, global_rotations):
        import torch

        self.root = root
        self.global_rotations = global_rotations
        self.frames = torch.arange(len(root), device=root.device, dtype=torch.long)

    def update_constraints(self, data_dict, index_dict):
        import torch

        joints = torch.arange(self.global_rotations.shape[1], device=self.root.device)
        indices = torch.stack(
            (
                self.frames[:, None].expand(-1, len(joints)),
                joints[None].expand(len(self.frames), -1),
            ),
            dim=-1,
        ).reshape(-1, 2)
        data_dict["root_2d"].append(self.root[:, [0, 2]])
        index_dict["root_2d"].append(self.frames)
        data_dict["root_y_pos"].append(self.root[:, 1])
        index_dict["root_y_pos"].append(self.frames)
        data_dict["global_root_heading"].append(
            torch.stack((torch.ones_like(self.root[:, 0]), torch.zeros_like(self.root[:, 0])), dim=-1)
        )
        index_dict["global_root_heading"].append(self.frames)
        data_dict["global_joints_rots"].append(self.global_rotations.reshape(-1, 3, 3))
        index_dict["global_joints_rots"].append(indices)


def load_pinned_model(ardy_root: Path, device: str):
    sys.path.insert(0, str(ardy_root))
    import torch
    from ardy.model import load_model
    from huggingface_hub import snapshot_download

    if device.startswith("cuda") and not torch.cuda.is_available():
        raise SystemExit("pinned ARDY rotation proof requires CUDA")
    snapshot_download(repo_id=f"nvidia/{G1_MODEL}", local_files_only=True)
    with contextlib.redirect_stdout(sys.stderr):
        model = load_model(G1_MODEL, device=device, text_encoder=False)
    if type(model.skeleton).__name__ != "G1Skeleton34":
        raise SystemExit(f"unexpected ARDY skeleton: {type(model.skeleton).__name__}")
    if int(model.gen_horizon_len) != FRAMES or int(model.motion_rep.fps) != FPS:
        raise SystemExit("ARDY model horizon/FPS drift")
    return model


def constrained_reconstruction(model, solved, device: str):
    import torch

    constraint = DenseRotationConstraint(
        solved["root"].to(device=device, dtype=torch.float32),
        solved["global_rotations"].to(device=device, dtype=torch.float32),
    )
    lengths = torch.tensor([FRAMES], device=device)
    observed, mask = model.motion_rep.create_conditions_from_constraints_batched(
        [constraint], lengths, to_normalize=False, device=device
    )
    rotation_mask = mask[0, :, model.motion_rep.slice_dict["global_rot_data"]]
    root_mask = mask[0, :, model.motion_rep.slice_dict["root_pos"]]
    if not bool(rotation_mask.all()) or int(rotation_mask.sum()) != FRAMES * 34 * 6:
        raise SystemExit("rotation conditioning does not cover all FK-consumed global rotation channels")
    if not bool(root_mask.all()) or int(root_mask.sum()) != FRAMES * 3:
        raise SystemExit("rotation conditioning does not cover the complete root trajectory")
    decoded = model.motion_rep.inverse(observed, is_normalized=False)
    return decoded, {
        "rotation_mask_true": int(rotation_mask.sum()),
        "rotation_mask_expected": FRAMES * 34 * 6,
        "root_mask_true": int(root_mask.sum()),
        "root_mask_expected": FRAMES * 3,
    }


def metrics(decoded: dict, solved: dict, action: dict, nodes) -> dict[str, object]:
    import torch

    positions = decoded["posed_joints"][0].detach().cpu().to(torch.float64)
    local = decoded["local_rot_mats"][0].detach().cpu().to(torch.float64)
    global_rotations = decoded["global_rot_mats"][0].detach().cpu().to(torch.float64)
    left_target = solved["left_hand_targets"]
    right_target = solved["right_hand_targets"]
    hand_errors = torch.linalg.vector_norm(
        torch.stack((positions[:, 25] - left_target, positions[:, 33] - right_target), dim=1),
        dim=-1,
    )
    foot_errors = torch.linalg.vector_norm(
        positions[:, [6, 7, 13, 14]] - solved["foot_targets"], dim=-1
    )
    contacts = np.asarray(
        [action["foot_contact_targets"]["left"], action["foot_contact_targets"]["right"]],
        dtype=bool,
    ).T
    planted = []
    for frame in range(FRAMES):
        if contacts[frame, 0]:
            planted.extend((float(foot_errors[frame, 0]), float(foot_errors[frame, 1])))
        if contacts[frame, 1]:
            planted.extend((float(foot_errors[frame, 2]), float(foot_errors[frame, 3])))

    desired_axes = solved["right_hand_targets"] - solved["left_hand_targets"]
    actual_axes = positions[:, 33] - positions[:, 25]
    actual_span = torch.linalg.vector_norm(actual_axes, dim=-1)
    desired_axes /= torch.linalg.vector_norm(desired_axes, dim=-1, keepdim=True)
    actual_axes /= actual_span[:, None]
    grip_angle = torch.rad2deg(
        torch.acos((desired_axes * actual_axes).sum(-1).clamp(-1.0, 1.0))
    )

    angles, limits, joint_indices = projected_hinge_angles(local, nodes)
    violations = []
    for column, ((low, high), joint) in enumerate(zip(limits, joint_indices, strict=True)):
        below = float(torch.relu(low - angles[:, column]).max())
        above = float(torch.relu(angles[:, column] - high).max())
        if max(below, above) > 1.0e-6:
            violations.append(
                {"joint": nodes[joint]["name"], "maximum_violation_rad": max(below, above)}
            )

    return {
        "maximum_hand_endpoint_error_m": float(hand_errors.max()),
        "maximum_planted_foot_endpoint_error_m": max(planted),
        "maximum_weapon_grip_position_error_m": float(hand_errors.max()),
        "maximum_weapon_grip_angle_error_degrees": float(grip_angle.max()),
        "minimum_weapon_grip_span_m": float(actual_span.min()),
        "maximum_weapon_grip_span_m": float(actual_span.max()),
        "maximum_absolute_angular_step_rad": maximum_angular_step(global_rotations),
        "minimum_joint_height_m": float(positions[..., 1].min()),
        "first_eight_frame_com_displacement_m": float(
            torch.linalg.vector_norm(positions[7].mean(0) - positions[0].mean(0))
        ),
        "joint_limit_violations": violations,
    }


def gate_failures(values: dict[str, Any]) -> list[str]:
    checks = (
        (values["maximum_hand_endpoint_error_m"] < MAX_ENDPOINT_ERROR_M, "hand_endpoint_error"),
        (
            values["maximum_planted_foot_endpoint_error_m"] < MAX_ENDPOINT_ERROR_M,
            "planted_foot_endpoint_error",
        ),
        (
            values["maximum_weapon_grip_position_error_m"] < MAX_ENDPOINT_ERROR_M,
            "weapon_grip_position_error",
        ),
        (
            values["maximum_weapon_grip_angle_error_degrees"] < MAX_GRIP_ANGLE_ERROR_DEG,
            "weapon_grip_angle_error",
        ),
        (float(values["minimum_weapon_grip_span_m"]) >= 0.158, "weapon_grip_span_minimum"),
        (float(values["maximum_weapon_grip_span_m"]) <= 0.162, "weapon_grip_span_maximum"),
        (
            values["maximum_absolute_angular_step_rad"] <= MAX_ANGULAR_STEP_RAD,
            "absolute_angular_step",
        ),
        (
            values["minimum_joint_height_m"] >= -MAX_FLOOR_PENETRATION_M,
            "floor_penetration",
        ),
        (
            values["first_eight_frame_com_displacement_m"]
            >= MIN_PREPARATION_COM_DISPLACEMENT_M,
            "first_eight_frame_preparation",
        ),
        (not values["joint_limit_violations"], "joint_limits"),
    )
    return [name for passed, name in checks if not passed]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ardy-root", type=Path, default=DEFAULT_ARDY)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--trajectory-output", type=Path, required=True)
    parser.add_argument("--proof-output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=OPTIMIZATION_STEPS,
                        help="optimization steps (default %(default)s; raise for tighter solve)")
    parser.add_argument("--lr", type=float, default=0.025,
                        help="Adam learning rate (default %(default)s)")
    parser.add_argument("--hand-weight", type=float, default=300.0,
                        help="hand/grip endpoint loss weight (default %(default)s)")
    args = parser.parse_args()

    trajectory_output = args.trajectory_output.resolve()
    proof_output = args.proof_output.resolve()
    refuse_existing(trajectory_output, proof_output)
    if args.ardy_root.resolve().joinpath(".git").is_dir() is False:
        raise SystemExit("ARDY source tree is missing")
    ardy_revision = __import__("subprocess").check_output(
        ["git", "-C", str(args.ardy_root.resolve()), "rev-parse", "HEAD"], text=True
    ).strip()

    from generate_pvp005_ardy_keypose_candidates import load_v4_sources
    from pvp005_ardy_v4_materializer import materialize

    spec_path, spec, spec_hash, w0, w0_hash = load_v4_sources(
        args.spec.resolve().relative_to(ROOT)
    )
    if spec["source_commit"] != ardy_revision:
        raise SystemExit(f"ARDY revision drift: {ardy_revision} != {spec['source_commit']}")
    materialized = materialize(
        spec, w0, spec_sha256=spec_hash, w0_sha256=w0_hash
    )
    action = materialized["actions"]["strike"]

    source_manifest = json.loads(DEFAULT_SOURCE_MANIFEST.read_text(encoding="utf-8"))
    source_receipt = source_manifest["actions"]["strike"]["source"]
    source = args.source.resolve()
    if source != ROOT / source_receipt["path"] or sha256(source) != source_receipt["sha256"]:
        raise SystemExit("pinned structural-pass Strike source hash/path drift")
    source_archive = np.load(source)
    if source_archive["local_rot_mats"].shape != (90, 34, 3, 3):
        raise SystemExit("pinned Strike source rotation shape drift")

    sys.path.insert(0, str(args.ardy_root.resolve()))
    from ardy.skeleton.definitions import G1Skeleton34

    skeleton = G1Skeleton34()
    nodes = parse_g1_hinges(ROOT / "src/g1_articulation.rs")
    solved = solve_rotation_trajectory(
        skeleton, action, source_archive["local_rot_mats"], nodes,
        steps=args.steps, lr=args.lr, hand_weight=args.hand_weight,
    )
    device = "cuda:0"
    model = load_pinned_model(args.ardy_root.resolve(), device)
    decoded, mask_metrics = constrained_reconstruction(model, solved, device)
    measured = metrics(decoded, solved, action, nodes)
    failures = gate_failures(measured)
    if failures:
        raise SystemExit(
            "PVP005_R6_ROTATION_PROOF=FAIL "
            + ",".join(failures)
            + " metrics="
            + json.dumps(measured, sort_keys=True)
        )

    trajectory_output.parent.mkdir(parents=True, exist_ok=True)
    decoded_cpu = {
        key: decoded[key][0].detach().cpu().numpy()
        for key in (
            "local_rot_mats",
            "global_rot_mats",
            "posed_joints",
            "root_positions",
            "global_root_heading",
        )
    }
    contacts = np.asarray(
        [action["foot_contact_targets"]["left"], action["foot_contact_targets"]["right"]],
        dtype=bool,
    ).T
    foot_contacts = contacts[:, [0, 0, 1, 1]]
    np.savez_compressed(
        trajectory_output,
        **decoded_cpu,
        foot_contacts=foot_contacts,
        desired_left_hand=solved["left_hand_targets"].numpy(),
        desired_right_hand=solved["right_hand_targets"].numpy(),
        desired_foot_positions=solved["foot_targets"].numpy(),
    )
    proof = {
        "schema": "just-dodge-pvp005-r6-rotation-conditioning-proof-v1",
        "status": "pass_representation_proof_no_diffusion_run",
        "authority": "offline_rotation_conditioned_strike_target_only",
        "repository_revision": __import__("subprocess").check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "ardy_revision": ardy_revision,
        "model": G1_MODEL,
        "source": {
            "path": str(source.relative_to(ROOT)),
            "sha256": sha256(source),
            "retime_anchors": SOURCE_RETIME_ANCHORS,
        },
        "spec": {"path": str(spec_path.relative_to(ROOT)), "sha256": spec_hash},
        "materialized_constraints_sha256": hashlib.sha256(canonical_bytes(materialized)).hexdigest(),
        "conditioning_mask": mask_metrics,
        "metrics": measured,
        "thresholds": {
            "maximum_endpoint_error_m": MAX_ENDPOINT_ERROR_M,
            "maximum_grip_angle_error_degrees": MAX_GRIP_ANGLE_ERROR_DEG,
            "maximum_absolute_angular_step_rad": MAX_ANGULAR_STEP_RAD,
            "maximum_floor_penetration_m": MAX_FLOOR_PENETRATION_M,
            "minimum_first_eight_frame_com_displacement_m": MIN_PREPARATION_COM_DISPLACEMENT_M,
        },
        "diffusion_candidates_generated": 0,
    }
    proof_output.parent.mkdir(parents=True, exist_ok=True)
    proof_output.write_bytes(canonical_bytes(proof))
    print(f"PVP005_R6_ROTATION_PROOF=PASS")
    print(f"PVP005_R6_ROTATION_TRAJECTORY={trajectory_output}")
    print(f"PVP005_R6_ROTATION_TRAJECTORY_SHA256={sha256(trajectory_output)}")
    print(f"PVP005_R6_ROTATION_PROOF_SHA256={sha256(proof_output)}")
    print(json.dumps(measured, sort_keys=True))


if __name__ == "__main__":
    main()
