#!/usr/bin/env python3
"""Fail-closed PVP005-R6K SOMA77→SOMA30→ARDY Core27→C0 bridge.

Offline only. This script maps rotations, scale/coordinates, and end-effectors; it
never authors combat contact, injury, reaction, or outcome truth.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import struct
import sys
import zipfile
from pathlib import Path

import numpy as np
import torch

TEACHER_SHA256 = "c3412394684264381c8c3b5828f607c69878100d52cba0648cbb84aa75202ece"
KIMODO_COMMIT = "1aece8c124d73d255ceff5086d983b844c9f4e94"
ARDY_COMMIT = "693f74d13b3d04a0a22ce127ee79c929dd89756b"
ARDY_TREE = "c430040bbac13d673781f3bce000d82307018727"
C0_SHA256 = "36a9c4e41f7e33ff58d68c10aa59a6b6cdbfb7e0384e0402e520801c205a1c7e"
FRAME_COUNT = 90

CORE_FROM_SOMA: dict[str, str | None] = {
    "Hips": "Hips",
    "Spine": None,
    "Spine1": "Spine1",
    "Spine2": "Spine2",
    "Spine3": "Chest",
    "Neck": None,
    "Head": "Head",
    "RightShoulder": "RightShoulder",
    "RightArm": "RightArm",
    "RightForeArm": "RightForeArm",
    "RightHand": "RightHand",
    "RightHandEnd": "RightHandMiddleEnd",
    "RightHandThumb1": "RightHandThumbEnd",
    "LeftShoulder": "LeftShoulder",
    "LeftArm": "LeftArm",
    "LeftForeArm": "LeftForeArm",
    "LeftHand": "LeftHand",
    "LeftHandEnd": "LeftHandMiddleEnd",
    "LeftHandThumb1": "LeftHandThumbEnd",
    "RightUpLeg": "RightLeg",
    "RightLeg": "RightShin",
    "RightFoot": "RightFoot",
    "RightToeBase": "RightToeBase",
    "LeftUpLeg": "LeftLeg",
    "LeftLeg": "LeftShin",
    "LeftFoot": "LeftFoot",
    "LeftToeBase": "LeftToeBase",
}

C0_FROM_CORE = {
    "Hips": "Hips",
    "LeftUpLeg": "LeftUpLeg",
    "LeftLeg": "LeftLeg",
    "LeftFoot": "LeftFoot",
    "LeftToeBase": "LeftToeBase",
    "RightUpLeg": "RightUpLeg",
    "RightLeg": "RightLeg",
    "RightFoot": "RightFoot",
    "RightToeBase": "RightToeBase",
    "Spine02": "Spine1",
    "Spine01": "Spine2",
    "Spine": "Spine3",
    "LeftShoulder": "LeftShoulder",
    "LeftArm": "LeftArm",
    "LeftForeArm": "LeftForeArm",
    "LeftHand": "LeftHand",
    "RightShoulder": "RightShoulder",
    "RightArm": "RightArm",
    "RightForeArm": "RightForeArm",
    "RightHand": "RightHand",
    "neck": "Neck",
    "Head": "Head",
}

CORE_LIMIT_DEG = {
    "Hips": 180.0,
    "Spine": 90.0,
    "Spine1": 90.0,
    "Spine2": 90.0,
    "Spine3": 90.0,
    "Neck": 110.0,
    "Head": 130.0,
    "RightShoulder": 150.0,
    "LeftShoulder": 150.0,
    "RightArm": 180.0,
    "LeftArm": 180.0,
    "RightForeArm": 180.0,
    "LeftForeArm": 180.0,
    "RightHand": 180.0,
    "LeftHand": 180.0,
    "RightHandEnd": 180.0,
    "LeftHandEnd": 180.0,
    "RightHandThumb1": 180.0,
    "LeftHandThumb1": 180.0,
    "RightUpLeg": 165.0,
    "LeftUpLeg": 165.0,
    "RightLeg": 175.0,
    "LeftLeg": 175.0,
    "RightFoot": 130.0,
    "LeftFoot": 130.0,
    "RightToeBase": 100.0,
    "LeftToeBase": 100.0,
}

C0_LIMIT_DEG = {
    "Hips": 180.0,
    "LeftUpLeg": 165.0, "RightUpLeg": 165.0,
    "LeftLeg": 175.0, "RightLeg": 175.0,
    "LeftFoot": 130.0, "RightFoot": 130.0,
    "LeftToeBase": 100.0, "RightToeBase": 100.0,
    "Spine02": 90.0, "Spine01": 90.0, "Spine": 90.0,
    "LeftShoulder": 150.0, "RightShoulder": 150.0,
    "LeftArm": 180.0, "RightArm": 180.0,
    "LeftForeArm": 180.0, "RightForeArm": 180.0,
    "LeftHand": 180.0, "RightHand": 180.0,
    "neck": 110.0, "Head": 130.0,
    "head_end": 180.0, "headfront": 180.0,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def deterministic_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(arrays):
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, np.asarray(arrays[name]), allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, buffer.getvalue(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def decompose_local(matrices: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    linear = matrices[..., :3, :3]
    scale = np.linalg.norm(linear, axis=-2)
    if np.any(scale <= 1.0e-8):
        raise ValueError("C0 rest matrix contains zero scale")
    rotations = linear / scale[..., None, :]
    if np.min(np.linalg.det(rotations)) <= 0.0:
        raise ValueError("C0 rest matrix contains reflection")
    return scale, rotations, matrices[..., :3, 3]


def make_local(scale: torch.Tensor, rotation: torch.Tensor, translation: torch.Tensor) -> torch.Tensor:
    shape = rotation.shape[:-2]
    result = torch.zeros(*shape, 4, 4, dtype=rotation.dtype, device=rotation.device)
    result[..., :3, :3] = rotation * scale.unsqueeze(-2)
    result[..., :3, 3] = translation
    result[..., 3, 3] = 1.0
    return result


def fk_c0(local: torch.Tensor, parents: list[int]) -> torch.Tensor:
    world: list[torch.Tensor] = []
    for joint, parent in enumerate(parents):
        world.append(local[:, joint] if parent < 0 else world[parent] @ local[:, joint])
    return torch.stack(world, dim=1)


def world_rotations(world: torch.Tensor) -> torch.Tensor:
    linear = world[..., :3, :3]
    scale = torch.linalg.vector_norm(linear, dim=-2).clamp_min(1.0e-12)
    rotations = linear / scale.unsqueeze(-2)
    u, _, vh = torch.linalg.svd(rotations)
    rotations = u @ vh
    if torch.any(torch.linalg.det(rotations) <= 0.0):
        raise ValueError("world rotation reflection")
    return rotations


def rotation_angles_deg(rotations: torch.Tensor) -> torch.Tensor:
    trace = rotations.diagonal(dim1=-2, dim2=-1).sum(-1)
    cosine = ((trace - 1.0) * 0.5).clamp(-1.0, 1.0)
    return torch.rad2deg(torch.acos(cosine))


def quaternions_from_matrices(matrices: np.ndarray) -> tuple[np.ndarray, int, float]:
    # Stable scalar-last [x,y,z,w], then temporal hemisphere canonicalization.
    output = np.empty((*matrices.shape[:-2], 4), dtype=np.float32)
    flat_in = matrices.reshape(-1, 3, 3)
    flat_out = output.reshape(-1, 4)
    for index, matrix in enumerate(flat_in):
        trace = float(np.trace(matrix))
        if trace > 0.0:
            s = math.sqrt(trace + 1.0) * 2.0
            q = np.array([(matrix[2, 1] - matrix[1, 2]) / s, (matrix[0, 2] - matrix[2, 0]) / s, (matrix[1, 0] - matrix[0, 1]) / s, 0.25 * s])
        else:
            diagonal = np.diag(matrix)
            axis = int(np.argmax(diagonal))
            if axis == 0:
                s = math.sqrt(max(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2], 0.0)) * 2.0
                q = np.array([0.25 * s, (matrix[0, 1] + matrix[1, 0]) / s, (matrix[0, 2] + matrix[2, 0]) / s, (matrix[2, 1] - matrix[1, 2]) / s])
            elif axis == 1:
                s = math.sqrt(max(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2], 0.0)) * 2.0
                q = np.array([(matrix[0, 1] + matrix[1, 0]) / s, 0.25 * s, (matrix[1, 2] + matrix[2, 1]) / s, (matrix[0, 2] - matrix[2, 0]) / s])
            else:
                s = math.sqrt(max(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1], 0.0)) * 2.0
                q = np.array([(matrix[0, 2] + matrix[2, 0]) / s, (matrix[1, 2] + matrix[2, 1]) / s, 0.25 * s, (matrix[1, 0] - matrix[0, 1]) / s])
        q /= np.linalg.norm(q)
        flat_out[index] = q
    corrections = 0
    min_dot = 1.0
    # matrices are [T,J,3,3]
    for joint in range(output.shape[1]):
        for frame in range(1, output.shape[0]):
            dot = float(np.dot(output[frame - 1, joint], output[frame, joint]))
            if dot < 0.0:
                output[frame, joint] *= -1.0
                dot = -dot
                corrections += 1
            min_dot = min(min_dot, dot)
    return output, corrections, min_dot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--teacher", type=Path, required=True)
    parser.add_argument("--c0", type=Path, required=True)
    parser.add_argument("--ardy-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if sha256(args.teacher) != TEACHER_SHA256:
        raise ValueError("golden teacher SHA-256 mismatch")
    if not args.c0.is_file():
        raise FileNotFoundError(args.c0)
    c0_data = json.loads(args.c0.read_text())
    if c0_data["source_sha256"] != C0_SHA256:
        raise ValueError("C0 source SHA-256 mismatch")
    sys.path.insert(0, str(args.ardy_root))
    from ardy.geometry import axis_angle_to_matrix
    from ardy.skeleton import CoreSkeleton27, SOMASkeleton30

    soma30 = SOMASkeleton30()
    core27 = CoreSkeleton27()
    with np.load(args.teacher, allow_pickle=False) as source:
        teacher = {key: np.asarray(source[key]) for key in source.files}
    local77 = torch.from_numpy(teacher["local_rot_mats"][0]).to(torch.float64)
    root = torch.from_numpy(teacher["root_positions"][0]).to(torch.float64)
    soma_slice = [
        [name for name, _ in soma30.bone_order_names_with_parents].index(name)
        for name in soma30.bone_order_names
    ]
    # ARDY and Kimodo use the exact same SOMA77 ordering at their pinned commits.
    soma77_names = [name for name, _ in __import__("ardy.skeleton.definitions", fromlist=["SOMASkeleton77"]).SOMASkeleton77.bone_order_names_with_parents]
    soma_slice = [soma77_names.index(name) for name in soma30.bone_order_names]
    local30 = local77[:, soma_slice]
    soma30_global, soma30_joints, _ = soma30.fk(local30, root)

    core_local = torch.eye(3, dtype=torch.float64).repeat(FRAME_COUNT, core27.nbjoints, 1, 1)
    sindex = soma30.bone_index
    cindex = core27.bone_index
    for core_name, soma_name in CORE_FROM_SOMA.items():
        if soma_name is not None:
            core_local[:, cindex[core_name]] = local30[:, sindex[soma_name]]
    # Preserve the exact composite neck rotation while collapsing SOMA's two neck joints.
    core_local[:, cindex["Neck"]] = local30[:, sindex["Neck1"]] @ local30[:, sindex["Neck2"]]
    core_global, core_joints, _ = core27.fk(core_local, root)

    roundtrip_local = torch.eye(3, dtype=torch.float64).repeat(FRAME_COUNT, soma30.nbjoints, 1, 1)
    for core_name, soma_name in CORE_FROM_SOMA.items():
        if soma_name is not None:
            roundtrip_local[:, sindex[soma_name]] = core_local[:, cindex[core_name]]
    roundtrip_local[:, sindex["Spine1"]] = core_local[:, cindex["Spine"]] @ core_local[:, cindex["Spine1"]]
    roundtrip_local[:, sindex["Neck1"]] = torch.eye(3, dtype=torch.float64)
    roundtrip_local[:, sindex["Neck2"]] = core_local[:, cindex["Neck"]]
    roundtrip_global, roundtrip_joints, _ = soma30.fk(roundtrip_local, root)
    endpoint_names = ["LeftHand", "LeftHandMiddleEnd", "RightHand", "RightHandMiddleEnd", "LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"]
    roundtrip_errors = {
        name: float(torch.max(torch.linalg.vector_norm(roundtrip_joints[:, sindex[name]] - soma30_joints[:, sindex[name]], dim=-1)))
        for name in endpoint_names
    }

    c0_bones = c0_data["bones"]
    c0_names = [bone["name"] for bone in c0_bones]
    c0_index = {name: index for index, name in enumerate(c0_names)}
    parents = [int(bone["parent"]) for bone in c0_bones]
    rest_local_np = np.stack([np.array(bone["rest_local_col_major"], dtype=np.float64).reshape(4, 4, order="F") for bone in c0_bones])
    rest_scale_np, rest_local_rot_np, rest_translation_np = decompose_local(rest_local_np)
    rest_scale = torch.from_numpy(rest_scale_np)
    rest_local_rot = torch.from_numpy(rest_local_rot_np)
    rest_translation = torch.from_numpy(rest_translation_np)
    rest_local = make_local(rest_scale, rest_local_rot, rest_translation)
    rest_world = fk_c0(rest_local.unsqueeze(0), parents)[0]
    rest_world_rot = world_rotations(rest_world.unsqueeze(0))[0]

    desired_global = torch.empty(FRAME_COUNT, len(c0_bones), 3, 3, dtype=torch.float64)
    mapped_local_rot = torch.empty_like(desired_global)
    for joint, name in enumerate(c0_names):
        core_name = C0_FROM_CORE.get(name)
        if core_name is not None:
            desired_global[:, joint] = core_global[:, cindex[core_name]] @ rest_world_rot[joint]
        elif parents[joint] >= 0:
            desired_global[:, joint] = desired_global[:, parents[joint]] @ rest_local_rot[joint]
        else:
            desired_global[:, joint] = rest_world_rot[joint]
        mapped_local_rot[:, joint] = desired_global[:, joint] if parents[joint] < 0 else desired_global[:, parents[joint]].transpose(-1, -2) @ desired_global[:, joint]
    scale_batch = rest_scale.unsqueeze(0).repeat(FRAME_COUNT, 1, 1)
    translation_batch = rest_translation.unsqueeze(0).repeat(FRAME_COUNT, 1, 1)
    translation_batch[:, 0] = root
    mapped_local = make_local(scale_batch, mapped_local_rot, translation_batch)
    mapped_world = fk_c0(mapped_local, parents)

    target_soma_names = ["LeftHand", "RightHand", "LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"]
    target_c0_names = ["LeftHand", "RightHand", "LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"]
    target_c0 = [c0_index[name] for name in target_c0_names]
    target_positions = torch.empty(FRAME_COUNT, len(target_c0_names), 3, dtype=torch.float64)

    def neutral_chain_length(positions: torch.Tensor, names: list[str], index: dict[str, int]) -> float:
        return sum(
            float(torch.linalg.vector_norm(positions[index[child]] - positions[index[parent]]))
            for parent, child in zip(names[:-1], names[1:], strict=True)
        )

    soma_neutral = soma30.neutral_joints.to(torch.float64)
    c0_rest_positions = rest_world[:, :3, 3]
    semantic_scale: dict[str, float] = {}
    for side in ("Left", "Right"):
        source_arm_chain = [f"{side}Shoulder", f"{side}Arm", f"{side}ForeArm", f"{side}Hand"]
        c0_arm_chain = source_arm_chain
        arm_ratio = neutral_chain_length(c0_rest_positions, c0_arm_chain, c0_index) / neutral_chain_length(
            soma_neutral, source_arm_chain, sindex
        )
        semantic_scale[f"{side}Hand"] = arm_ratio
        hand_slot = target_soma_names.index(f"{side}Hand")
        source_vector = soma30_joints[:, sindex[f"{side}Hand"]] - soma30_joints[:, sindex[f"{side}Shoulder"]]
        target_positions[:, hand_slot] = mapped_world[:, c0_index[f"{side}Shoulder"], :3, 3] + arm_ratio * source_vector

        for end_name, chain in (
            (f"{side}Foot", [f"{side}Leg", f"{side}Shin", f"{side}Foot"]),
            (f"{side}ToeBase", [f"{side}Leg", f"{side}Shin", f"{side}Foot", f"{side}ToeBase"]),
        ):
            c0_chain = [f"{side}UpLeg", f"{side}Leg", f"{side}Foot"]
            if end_name.endswith("ToeBase"):
                c0_chain.append(f"{side}ToeBase")
            ratio = neutral_chain_length(c0_rest_positions, c0_chain, c0_index) / neutral_chain_length(
                soma_neutral, chain, sindex
            )
            semantic_scale[end_name] = ratio
            slot = target_soma_names.index(end_name)
            source_vector = soma30_joints[:, sindex[end_name]] - soma30_joints[:, sindex[f"{side}Leg"]]
            target_positions[:, slot] = mapped_world[:, c0_index[f"{side}UpLeg"], :3, 3] + ratio * source_vector

    # W0 has a fixed 0.160 m two-hand socket span. Preserve the scale-mapped
    # midpoint while projecting the pair onto that explicit corridor axis.
    left_slot = target_soma_names.index("LeftHand")
    right_slot = target_soma_names.index("RightHand")
    midpoint = (target_positions[:, left_slot] + target_positions[:, right_slot]) * 0.5
    source_axis = soma30_joints[:, sindex["RightHand"]] - soma30_joints[:, sindex["LeftHand"]]
    source_axis = source_axis / torch.linalg.vector_norm(source_axis, dim=-1, keepdim=True).clamp_min(1.0e-12)
    target_positions[:, left_slot] = midpoint - source_axis * 0.080
    target_positions[:, right_slot] = midpoint + source_axis * 0.080
    # The teacher specification declares both feet planted at fixed world
    # anchors. Do not propagate residual generator skate into the bridge.
    for planted_name in ("LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"):
        slot = target_soma_names.index(planted_name)
        target_positions[:, slot] = target_positions[0, slot]
    def damped_rotation_arc(source: torch.Tensor, target: torch.Tensor, damping: float) -> torch.Tensor:
        source = source / torch.linalg.vector_norm(source, dim=-1, keepdim=True).clamp_min(1.0e-12)
        target = target / torch.linalg.vector_norm(target, dim=-1, keepdim=True).clamp_min(1.0e-12)
        cross = torch.linalg.cross(source, target)
        sine = torch.linalg.vector_norm(cross, dim=-1)
        cosine = torch.sum(source * target, dim=-1).clamp(-1.0, 1.0)
        axis = cross / sine.unsqueeze(-1).clamp_min(1.0e-12)
        fallback_x = torch.linalg.cross(source, torch.tensor([1.0, 0.0, 0.0], dtype=torch.float64).expand_as(source))
        fallback_y = torch.linalg.cross(source, torch.tensor([0.0, 1.0, 0.0], dtype=torch.float64).expand_as(source))
        fallback = torch.where(
            (torch.linalg.vector_norm(fallback_x, dim=-1) > 0.1).unsqueeze(-1), fallback_x, fallback_y
        )
        fallback = fallback / torch.linalg.vector_norm(fallback, dim=-1, keepdim=True).clamp_min(1.0e-12)
        axis = torch.where((sine > 1.0e-8).unsqueeze(-1), axis, fallback)
        angle = torch.atan2(sine, cosine) * damping
        return axis_angle_to_matrix(axis * angle.unsqueeze(-1))

    final_rot = mapped_local_rot.clone()
    hand_specs = [
        ("LeftHand", "LeftHand", ["LeftForeArm", "LeftArm", "LeftShoulder"]),
        ("RightHand", "RightHand", ["RightForeArm", "RightArm", "RightShoulder"]),
    ]
    foot_specs = [
        ("LeftFoot", "LeftToeBase", "LeftFoot", "LeftToeBase", ["LeftFoot", "LeftLeg", "LeftUpLeg"], ["LeftLeg", "LeftUpLeg"]),
        ("RightFoot", "RightToeBase", "RightFoot", "RightToeBase", ["RightFoot", "RightLeg", "RightUpLeg"], ["RightLeg", "RightUpLeg"]),
    ]

    def aim(chain_name: str, effector_name: str, target: torch.Tensor, damping: float) -> None:
        joint = c0_index[chain_name]
        effector = c0_index[effector_name]
        local = make_local(scale_batch, final_rot, translation_batch)
        world = fk_c0(local, parents)
        rotations = world_rotations(world)
        joint_position = world[:, joint, :3, 3]
        current = world[:, effector, :3, 3] - joint_position
        desired = target - joint_position
        correction = damped_rotation_arc(current, desired, damping)
        desired_world = correction @ rotations[:, joint]
        parent = parents[joint]
        final_rot[:, joint] = desired_world if parent < 0 else rotations[:, parent].transpose(-1, -2) @ desired_world

    for _ in range(96):
        for hand_name, source_name, chain in hand_specs:
            target = target_positions[:, target_soma_names.index(source_name)]
            for joint_name in chain:
                aim(joint_name, hand_name, target, 0.90)
        for foot_name, toe_name, source_foot, source_toe, toe_chain, foot_chain in foot_specs:
            toe_target = target_positions[:, target_soma_names.index(source_toe)]
            foot_target = target_positions[:, target_soma_names.index(source_foot)]
            for joint_name in toe_chain:
                aim(joint_name, toe_name, toe_target, 0.86)
            for joint_name in foot_chain:
                aim(joint_name, foot_name, foot_target, 0.90)

    final_local = make_local(scale_batch, final_rot, translation_batch)
    final_world = fk_c0(final_local, parents)
    final_world_rot = world_rotations(final_world)
    # Restore exact mapped hand orientation after positional CCD; hand rotation does not alter hand-joint position.
    for hand_name in ("LeftHand", "RightHand"):
        joint = c0_index[hand_name]
        parent = parents[joint]
        final_rot[:, joint] = final_world_rot[:, parent].transpose(-1, -2) @ desired_global[:, joint]
    final_local = make_local(scale_batch, final_rot, translation_batch)
    final_world = fk_c0(final_local, parents)
    final_world_rot = world_rotations(final_world)
    final_positions = final_world[:, target_c0, :3, 3]
    local_correction = mapped_local_rot.transpose(-1, -2) @ final_rot
    max_local_correction_deg = float(torch.max(rotation_angles_deg(local_correction)))

    position_errors = torch.linalg.vector_norm(final_positions - target_positions, dim=-1)
    hand_error = float(torch.max(position_errors[:, :2]))
    grip_error = float(torch.max(torch.abs(torch.linalg.vector_norm(final_positions[:, 1] - final_positions[:, 0], dim=-1) - torch.linalg.vector_norm(target_positions[:, 1] - target_positions[:, 0], dim=-1))))
    foot_target_error = float(torch.max(position_errors[:, 2:]))
    c0_foot_drift = {
        name: float(torch.max(torch.linalg.vector_norm(final_world[:, c0_index[name], :3, 3] - final_world[0, c0_index[name], :3, 3], dim=-1)))
        for name in ("LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase")
    }
    hand_rotation_errors = {}
    for hand_name in ("LeftHand", "RightHand"):
        joint = c0_index[hand_name]
        delta_rotation = final_world_rot[:, joint] @ rest_world_rot[joint].transpose(-1, -2)
        source_rotation = soma30_global[:, sindex[hand_name]]
        residual = delta_rotation.transpose(-1, -2) @ source_rotation
        hand_rotation_errors[hand_name] = float(torch.max(rotation_angles_deg(residual)))

    core_angles = rotation_angles_deg(core_local)
    joint_limit_violations = []
    for joint, name in enumerate(core27.bone_order_names):
        observed = float(torch.max(core_angles[:, joint]))
        limit = CORE_LIMIT_DEG[name]
        if observed > limit + 1.0e-4:
            joint_limit_violations.append({"skeleton": "ARDY Core27", "joint": name, "observed_deg": observed, "limit_deg": limit})
    c0_delta_from_rest = rest_local_rot.unsqueeze(0).transpose(-1, -2) @ final_rot
    c0_angles = rotation_angles_deg(c0_delta_from_rest)
    for joint, name in enumerate(c0_names):
        observed = float(torch.max(c0_angles[:, joint]))
        limit = C0_LIMIT_DEG[name]
        if observed > limit + 1.0e-4:
            joint_limit_violations.append({"skeleton": "C0", "joint": name, "observed_deg": observed, "limit_deg": limit})

    matrices = {
        "soma30_local": local30.numpy(),
        "soma30_global": soma30_global.numpy(),
        "soma30_joints_m": soma30_joints.numpy(),
        "core27_local": core_local.numpy(),
        "core27_global": core_global.numpy(),
        "core27_joints_m": core_joints.numpy(),
        "c0_local_col_major": final_local.numpy(),
        "c0_world_col_major": final_world.numpy(),
        "root_positions_m": root.numpy(),
        "foot_contacts": teacher["foot_contacts"][0],
        "global_root_heading_xz": teacher["global_root_heading"][0],
        "scaled_constraint_targets_m": target_positions.numpy(),
    }
    quat_metrics = {}
    for name in ("soma30_local", "core27_local"):
        quats, corrections, min_dot = quaternions_from_matrices(matrices[name])
        matrices[name.replace("local", "local_quat_xyzw")] = quats
        quat_metrics[name] = {"hemisphere_corrections": corrections, "postcanonical_min_consecutive_dot": min_dot}
    c0_rot_np = final_rot.numpy()
    c0_quats, c0_corrections, c0_min_dot = quaternions_from_matrices(c0_rot_np)
    matrices["c0_local_quat_xyzw"] = c0_quats
    quat_metrics["c0_local"] = {"hemisphere_corrections": c0_corrections, "postcanonical_min_consecutive_dot": c0_min_dot}

    all_rotation_arrays = [local30.numpy(), core_local.numpy(), final_rot.numpy()]
    det_min = min(float(np.linalg.det(value.reshape(-1, 3, 3)).min()) for value in all_rotation_arrays)
    det_max = max(float(np.linalg.det(value.reshape(-1, 3, 3)).max()) for value in all_rotation_arrays)
    finite = all(np.isfinite(value).all() for value in matrices.values())
    scale_ratios = {}
    pairs = [("LeftLeg", "LeftLeg"), ("RightLeg", "RightLeg"), ("LeftFoot", "LeftFoot"), ("RightFoot", "RightFoot"), ("LeftArm", "LeftArm"), ("RightArm", "RightArm"), ("LeftForeArm", "LeftForeArm"), ("RightForeArm", "RightForeArm")]
    core_neutral = core27.neutral_joints.numpy()
    for c0_name, core_name in pairs:
        cj = c0_index[c0_name]
        cp = parents[cj]
        sj = cindex[core_name]
        sp = int(core27.joint_parents[sj])
        c0_len = float(np.linalg.norm(rest_world[cj, :3, 3].numpy() - rest_world[cp, :3, 3].numpy()))
        core_len = float(np.linalg.norm(core_neutral[sj] - core_neutral[sp]))
        scale_ratios[c0_name] = c0_len / core_len

    report = {
        "schema": "just-dodge-pvp005-r6k-rotation-bridge-v1",
        "status": "pass" if (
            max(roundtrip_errors.values()) < 0.010
            and hand_error < 0.010
            and grip_error < 0.010
            and max(hand_rotation_errors.values()) <= 3.0
            and max(c0_foot_drift.values()) < 0.010
            and finite
            and det_min > 0.999
            and det_max < 1.001
            and not joint_limit_violations
            and all(item["postcanonical_min_consecutive_dot"] >= 0.0 for item in quat_metrics.values())
        ) else "fail",
        "authority": "offline_constraints_and_reference_only",
        "teacher_sha256": TEACHER_SHA256,
        "kimodo_commit": KIMODO_COMMIT,
        "ardy_commit": ARDY_COMMIT,
        "ardy_tree": ARDY_TREE,
        "c0_source_sha256": C0_SHA256,
        "coordinate_contract": {
            "source_and_core": "right-handed Y-up metres, +Z heading at angle zero",
            "c0_asset": "right-handed +Z-up centimetre children under 0.01 root scale",
            "c0_asset_to_runtime_xyz": ["x", "z", "-y"],
            "runtime": "right-handed Y-up metres, +Z forward",
            "heading_input": [1.0, 0.0],
        },
        "mapping": {"soma77_to_soma30": "exact official named subset", "soma30_to_core27": CORE_FROM_SOMA, "core27_to_c0": C0_FROM_CORE},
        "scale_mapping": {"method": "shoulder/hip-relative semantic-chain scaling with fixed 0.160 m W0 grip and stationary declared foot anchors", "semantic_target_ratios": semantic_scale, "c0_to_core_segment_ratios": scale_ratios, "c0_root_scale": rest_scale_np[0].tolist()},
        "roundtrip_fk_endpoint_error_m": roundtrip_errors,
        "roundtrip_fk_endpoint_error_max_m": max(roundtrip_errors.values()),
        "c0_hand_position_error_max_m": hand_error,
        "c0_grip_span_error_max_m": grip_error,
        "c0_hand_rotation_error_deg": hand_rotation_errors,
        "c0_foot_target_error_max_m": foot_target_error,
        "c0_planted_foot_drift_m": c0_foot_drift,
        "rotation_determinants": {"min": det_min, "max": det_max},
        "quaternion_continuity": quat_metrics,
        "joint_limit_definition_deg": {"ARDY Core27": CORE_LIMIT_DEG, "C0": C0_LIMIT_DEG},
        "joint_limit_violations": joint_limit_violations,
        "ik": {"method": "deterministic batched CCD", "iterations": 96, "maximum_local_correction_deg": max_local_correction_deg},
        "finite": finite,
        "forbidden_authority": ["hit", "block_result", "opponent_reaction", "injury", "outcome"],
        "ardy_generation_authorized": False,
        "runtime_admitted": False,
        "promoted": False,
    }
    bridge_path = args.output / "kimodo_to_ardy_core27_to_c0.bridge.npz"
    deterministic_npz(bridge_path, matrices)
    report["bridge_path"] = bridge_path.name
    report["bridge_sha256"] = sha256(bridge_path)
    report["report_sha256"] = hashlib.sha256(canonical_bytes(report)).hexdigest()
    report_path = args.output / "rotation_bridge_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    if report["status"] != "pass":
        raise RuntimeError(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps({"status": report["status"], "bridge_sha256": report["bridge_sha256"], "report_sha256": report["report_sha256"], "roundtrip_m": report["roundtrip_fk_endpoint_error_max_m"], "hand_m": hand_error, "hand_deg": max(hand_rotation_errors.values()), "foot_drift_m": max(c0_foot_drift.values())}, sort_keys=True))


if __name__ == "__main__":
    main()
