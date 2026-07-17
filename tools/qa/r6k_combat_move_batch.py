#!/usr/bin/env python3
"""R6K combat-move batch pipeline: Kimodo teacher -> ARDY proposal -> MotionBricks interaction target.

Offline only. No provider authors contact, injury, reaction, or outcome. MotionBricks
remains the sole runtime motion engine; this script produces training/QA evidence only.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import torch

REPO = Path("/run/media/vdubrov/NVMe-Storage1/Just Dodge")
KIMODO_DIR = Path("/home/vdubrov/Projects/kimodo-r6k-1aece8c")
ARDY_DIR = Path("/home/vdubrov/Projects/ardy-r6k-693f74d")
MB_DIR = Path("/run/media/vdubrov/NVMe-Storage1/gr00t/motionbricks")
KIMODO_MODEL_ROOT = Path("/home/vdubrov/Models/kimodo-r6k-6c9233af")
ARDY_MODEL_ROOT = Path("/home/vdubrov/Models/ardy-r6k-abe6c43b")
KIMODO_MODEL_DIR = KIMODO_MODEL_ROOT / "Kimodo-SOMA-RP-v1.1"
ARDY_MODEL_DIR = ARDY_MODEL_ROOT / "ARDY-Core-RP-20FPS-Horizon40"
TEXT_ROOT = Path("/run/media/vdubrov/NVMe-Storage1/r6k-models/text-encoder")
TEXT_BUNDLE = Path("/home/vdubrov/Projects/r6k-combat-batch/text-encoder-bundle")
BATCH_SPEC = REPO / "assets/data/r6k_move_batch.json"
OUT_ROOT = Path("/home/vdubrov/Projects/r6k-combat-batch/artifacts")

KIMODO_MODEL_SHA256 = "ef0a0ca45a6089ab4532dde609785771ae3f38755b4ae6cf314b0213e07cd4a3"
ARDY_DENOISER_SHA256 = "1019d0bf269cf8d1b3e3e9b4a384a58c112672959b071279ddb65814d77660cd"
ARDY_TOKENIZER_SHA256 = "58a887e299a3a6779b5b4ff361b452c4349d45b513b5957f2a961d393623abcd"
KIMODO_COMMIT = "1aece8c124d73d255ceff5086d983b844c9f4e94"
ARDY_COMMIT = "693f74d13b3d04a0a22ce127ee79c929dd89756b"

KIMODO_FPS = 30
KIMODO_FRAMES = 90
ARDY_FPS = 20
ARDY_FRAMES = 40
MB_FPS = 30
MB_FRAMES = 64
SEED_BASE = 2026071700

CORE_JOINTS = [
    "Hips", "Spine", "Spine1", "Spine2", "Spine3", "Neck", "Head",
    "RightShoulder", "RightArm", "RightForeArm", "RightHand", "RightHandEnd", "RightHandThumb1",
    "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand", "LeftHandEnd", "LeftHandThumb1",
    "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase",
    "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
]

G1_DIRECT = {
    "pelvis_skel": "Hips",
    "left_hip_pitch_skel": "LeftUpLeg", "left_knee_skel": "LeftLeg",
    "left_ankle_pitch_skel": "LeftFoot", "left_toe_base": "LeftToeBase",
    "right_hip_pitch_skel": "RightUpLeg", "right_knee_skel": "RightLeg",
    "right_ankle_pitch_skel": "RightFoot", "right_toe_base": "RightToeBase",
    "left_shoulder_pitch_skel": "LeftShoulder", "left_elbow_skel": "LeftForeArm",
    "left_wrist_roll_skel": "LeftHand", "left_hand_roll_skel": "LeftHandEnd",
    "right_shoulder_pitch_skel": "RightShoulder", "right_elbow_skel": "RightForeArm",
    "right_wrist_roll_skel": "RightHand", "right_hand_roll_skel": "RightHandEnd",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def deterministic_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(arrays):
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, np.asarray(arrays[name]), allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, buffer.getvalue(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def rotation_basis_from_axis(axis: torch.Tensor, flip_x: bool) -> torch.Tensor:
    z = axis / torch.linalg.vector_norm(axis)
    x_seed = torch.tensor([-1.0 if flip_x else 1.0, 0.0, 0.0], dtype=torch.float64)
    x = x_seed - torch.dot(x_seed, z) * z
    x = x / torch.linalg.vector_norm(x)
    y = torch.linalg.cross(z, x)
    return torch.stack((x, y, z), dim=-1)


def resample(a: np.ndarray, n: int) -> np.ndarray:
    x = np.linspace(0, len(a) - 1, n)
    lo = np.floor(x).astype(int)
    hi = np.minimum(lo + 1, len(a) - 1)
    t = (x - lo)[:, None]
    return a[lo] * (1 - t) + a[hi] * t


def verify_environment() -> None:
    if sha256(KIMODO_MODEL_DIR / "model.safetensors") != KIMODO_MODEL_SHA256:
        raise RuntimeError("Kimodo checkpoint SHA mismatch")
    if sha256(ARDY_MODEL_DIR / "denoiser.safetensors") != ARDY_DENOISER_SHA256:
        raise RuntimeError("ARDY denoiser SHA mismatch")
    for label, root, commit in (("kimodo", KIMODO_DIR, KIMODO_COMMIT), ("ardy", ARDY_DIR, ARDY_COMMIT)):
        head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        if head != commit:
            raise RuntimeError(f"{label} checkout drift: {head}")


def prepare_text_bundle() -> None:
    sources = {
        "mntp": TEXT_ROOT / "llm2vec-mntp-31474e39",
        "supervised": TEXT_ROOT / "llm2vec-supervised-baa8ebf0",
        "meta": TEXT_ROOT / "meta-llama-3-8b-instruct-8afb486c",
    }
    if TEXT_BUNDLE.exists():
        return
    TEXT_BUNDLE.mkdir(parents=True, exist_ok=True)
    shutil.copytree(sources["mntp"], TEXT_BUNDLE / "mntp", ignore=shutil.ignore_patterns(".cache"))
    shutil.copytree(sources["supervised"], TEXT_BUNDLE / "supervised", ignore=shutil.ignore_patterns(".cache"))
    mnt_cfg_path = TEXT_BUNDLE / "mntp" / "adapter_config.json"
    mnt_cfg = json.loads(mnt_cfg_path.read_text())
    mnt_cfg["base_model_name_or_path"] = str(sources["meta"])
    write_json(mnt_cfg_path, mnt_cfg)
    sup_cfg_path = TEXT_BUNDLE / "supervised" / "adapter_config.json"
    sup_cfg = json.loads(sup_cfg_path.read_text())
    sup_cfg["base_model_name_or_path"] = str(TEXT_BUNDLE / "mntp")
    write_json(sup_cfg_path, sup_cfg)


def embed_prompt(prompt: str, seed: int) -> np.ndarray:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    from kimodo.model.llm2vec.llm2vec_wrapper import LLM2VecEncoder
    encoder = LLM2VecEncoder(
        base_model_name_or_path=str(TEXT_BUNDLE / "mntp"),
        peft_model_name_or_path=str(TEXT_BUNDLE / "supervised"),
        dtype="bfloat16",
        llm_dim=4096,
        device="cuda",
    )
    with torch.no_grad():
        feature, _ = encoder([prompt])
    arr = feature.detach().cpu().to(torch.float32).contiguous().numpy()
    if arr.ndim == 2:
        arr = arr[None, ...]
    torch.set_default_dtype(torch.float32)
    return arr


def build_kimodo_constraints(move: dict, out_dir: Path) -> tuple[Path, np.ndarray]:
    from kimodo.constraints import (
        FullBodyConstraintSet,
        LeftFootConstraintSet,
        LeftHandConstraintSet,
        RightFootConstraintSet,
        RightHandConstraintSet,
        Root2DConstraintSet,
        save_constraints_lst,
    )
    from kimodo.geometry import axis_angle_to_matrix
    from kimodo.skeleton import SOMASkeleton30

    skeleton = SOMASkeleton30()
    torch.set_default_dtype(torch.float64)
    root_height = float(-skeleton.neutral_joints[:, 1].min().item() + 0.007)
    root = torch.tensor([0.0, root_height, 0.0], dtype=torch.float64)
    key_frames = move["key_frames"]
    centers = move["grip_centers"]
    axes = move["grip_axes"]
    grip_half_span = 0.08
    selected_names = [
        "Spine1", "Spine2", "Chest",
        "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
        "RightShoulder", "RightArm", "RightForeArm", "RightHand",
    ]
    selected = [skeleton.bone_index[n] for n in selected_names]
    left_hand = skeleton.bone_index["LeftHand"]
    right_hand = skeleton.bone_index["RightHand"]
    previous = torch.full((len(selected), 3), 1.0e-4, dtype=torch.float64)
    solved_local = []
    residuals = []

    for frame, center_raw, axis_raw in zip(key_frames, centers, axes):
        center = torch.tensor(center_raw, dtype=torch.float64)
        axis = torch.tensor(axis_raw, dtype=torch.float64)
        axis = axis / torch.linalg.vector_norm(axis)
        left_target = center - grip_half_span * axis
        right_target = center + grip_half_span * axis
        left_rot_target = rotation_basis_from_axis(axis, flip_x=True)
        right_rot_target = rotation_basis_from_axis(axis, flip_x=False)
        parameter = torch.nn.Parameter(previous.clone())
        optimizer = torch.optim.Adam([parameter], lr=0.025)
        for _ in range(1800):
            optimizer.zero_grad(set_to_none=True)
            local = torch.eye(3, dtype=torch.float64).repeat(skeleton.nbjoints, 1, 1)
            local[selected] = axis_angle_to_matrix(parameter)
            global_rots, joints, _ = skeleton.fk(local.unsqueeze(0), root.unsqueeze(0))
            joints = joints[0]
            global_rots = global_rots[0]
            pos_loss = (
                torch.sum((joints[left_hand] - left_target) ** 2)
                + torch.sum((joints[right_hand] - right_target) ** 2)
            )
            rot_loss = (
                torch.mean((global_rots[left_hand] - left_rot_target) ** 2)
                + torch.mean((global_rots[right_hand] - right_rot_target) ** 2)
            )
            regularization = 0.0005 * torch.mean(parameter**2) + 0.001 * torch.mean((parameter - previous) ** 2)
            loss = 1200.0 * pos_loss + 45.0 * rot_loss + regularization
            loss.backward()
            optimizer.step()
            with torch.no_grad():
                norms = torch.linalg.vector_norm(parameter, dim=-1, keepdim=True).clamp_min(1e-12)
                parameter.copy_(parameter * torch.clamp(2.8 / norms, max=1.0))
        with torch.no_grad():
            local = torch.eye(3, dtype=torch.float64).repeat(skeleton.nbjoints, 1, 1)
            local[selected] = axis_angle_to_matrix(parameter)
            global_rots, joints, _ = skeleton.fk(local.unsqueeze(0), root.unsqueeze(0))
            joints = joints[0]
            lp = float(torch.linalg.vector_norm(joints[left_hand] - left_target))
            rp = float(torch.linalg.vector_norm(joints[right_hand] - right_target))
            residuals.append({"frame": frame, "left_hand_m": lp, "right_hand_m": rp})
            if max(lp, rp) >= 0.010:
                raise RuntimeError(f"{move['id']}: authored keyframe failed hand gate at frame {frame}: {residuals[-1]}")
            solved_local.append(local.clone())
            previous = parameter.detach().clone()

    local_stack = torch.stack(solved_local).to(torch.float32)
    skeleton = skeleton.to(dtype=torch.float32)
    root = root.to(torch.float32)
    global_rots, posed_joints, _ = skeleton.fk(local_stack, root.repeat(len(key_frames), 1))
    kf = torch.tensor(key_frames)
    num_frames = KIMODO_FRAMES
    dense_frames = torch.arange(num_frames)
    foot_pose = posed_joints[0].unsqueeze(0).repeat(num_frames, 1, 1)
    foot_rots = global_rots[0].unsqueeze(0).repeat(num_frames, 1, 1, 1)

    root_dodge = move.get("root_dodge")
    if root_dodge is not None:
        direction = torch.tensor(root_dodge["direction"], dtype=torch.float64)
        peak = int(root_dodge["peak_frame"])
        root_path = torch.zeros((num_frames, 2), dtype=torch.float64)
        for f in range(num_frames):
            if f <= peak:
                t = f / max(peak, 1)
            else:
                t = max(0.0, 1.0 - (f - peak) / max(num_frames - 1 - peak, 1))
            offset = direction * t
            root_path[f] = torch.tensor([offset[0], offset[2]], dtype=torch.float64)
    else:
        root_path = torch.zeros((num_frames, 2), dtype=torch.float64)
    heading = torch.tensor([1.0, 0.0], dtype=torch.float64).repeat(num_frames, 1)

    fullbody_positions = [key_frames.index(f) for f in (key_frames[0], key_frames[2], key_frames[4], key_frames[-1])]
    fullbody = FullBodyConstraintSet(
        skeleton,
        torch.tensor([key_frames[0], key_frames[2], key_frames[4], key_frames[-1]]),
        posed_joints[fullbody_positions],
        global_rots[fullbody_positions],
        root_path[[key_frames[0], key_frames[2], key_frames[4], key_frames[-1]]].to(torch.float64),
    )
    left_hand_c = LeftHandConstraintSet(skeleton, kf, posed_joints, global_rots, root_path[kf].to(torch.float64))
    right_hand_c = RightHandConstraintSet(skeleton, kf, posed_joints, global_rots, root_path[kf].to(torch.float64))
    left_foot_c = LeftFootConstraintSet(skeleton, dense_frames, foot_pose, foot_rots, root_path)
    right_foot_c = RightFootConstraintSet(skeleton, dense_frames, foot_pose, foot_rots, root_path)
    root_c = Root2DConstraintSet(skeleton, dense_frames, root_path, global_root_heading=heading)
    constraints = [root_c, fullbody, left_foot_c, right_foot_c, left_hand_c, right_hand_c]
    constraints_path = out_dir / "kimodo_constraints.json"
    save_constraints_lst(str(constraints_path), constraints)

    kf_positions = torch.tensor(key_frames)
    reference = {
        "local_rot_mats": local_stack.unsqueeze(0).numpy(),
        "global_rot_mats": global_rots.unsqueeze(0).numpy(),
        "posed_joints": posed_joints.unsqueeze(0).numpy(),
        "key_frames": np.asarray(key_frames, dtype=np.int64),
        "root_path": root_path.numpy(),
    }
    ref_path = out_dir / "kimodo_reference.soma30.npz"
    deterministic_npz(ref_path, reference)
    return constraints_path, np.asarray(residuals and [max(r["left_hand_m"], r["right_hand_m"]) for r in residuals])


def generate_kimodo_teacher(move: dict, out_dir: Path, constraints_path: Path, embedding: np.ndarray, seed: int) -> Path:
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["CHECKPOINT_DIR"] = str(KIMODO_MODEL_ROOT)
    torch.set_default_dtype(torch.float32)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)

    cached_feature = torch.from_numpy(embedding)

    class CachedEncoder:
        def __call__(self, text):
            lengths = [cached_feature.shape[1] if cached_feature.dim() >= 2 else 1]
            return cached_feature.to("cuda"), lengths

    from kimodo import load_model
    from kimodo.constraints import load_constraints_lst
    model = load_model("Kimodo-SOMA-RP-v1.1", device="cuda", text_encoder=CachedEncoder())
    constraints = load_constraints_lst(str(constraints_path), model.skeleton, device="cuda")
    with torch.no_grad():
        output = model(
            move["prompt"],
            KIMODO_FRAMES,
            num_denoising_steps=100,
            constraint_lst=constraints,
            cfg_weight=[2.0, 2.0],
            num_samples=1,
            cfg_type="separated",
            return_numpy=True,
            first_heading_angle=torch.tensor(0.0, device="cuda"),
            post_processing=True,
            root_margin=0.01,
        )
    required = ["local_rot_mats", "global_rot_mats", "posed_joints", "root_positions",
                "smooth_root_pos", "foot_contacts", "global_root_heading"]
    arrays = {key: np.asarray(output[key]) for key in required}
    for key, arr in arrays.items():
        if not np.isfinite(arr).all():
            raise RuntimeError(f"{move['id']}: non-finite Kimodo output {key}")
    out_path = out_dir / "kimodo_teacher.soma77.npz"
    deterministic_npz(out_path, arrays)
    return out_path


def map_teacher_to_core27(teacher_path: Path, move: dict, out_dir: Path) -> Path:
    sys.path.insert(0, str(MB_DIR))
    from motionbricks.motionlib.core.skeletons.g1 import G1Skeleton
    from motionbricks.motionlib.core.utils.torch_utils import batch_rigid_transform

    sk = G1Skeleton(device="cuda")
    q = sk.bone_index
    with np.load(teacher_path, allow_pickle=False) as data:
        cl = torch.from_numpy(np.asarray(data["local_rot_mats"][0]).astype("float32")).cuda()
        cr = torch.from_numpy(np.asarray(data["root_positions"][0]).astype("float32")).cuda()
    T = cl.shape[0]
    g = torch.eye(3, device="cuda").repeat(T, 34, 1, 1)
    c = {n: i for i, n in enumerate(CORE_JOINTS)}
    for gn, cn in G1_DIRECT.items():
        g[:, q[gn]] = cl[:, c[cn]]
    s = cl[:, c["Spine"]]
    for n in ("Spine1", "Spine2", "Spine3"):
        s = s @ cl[:, c[n]]
    g[:, q["waist_yaw_skel"]] = s
    p, r = batch_rigid_transform(g, sk.neutral_joints.float()[None].repeat(T, 1, 1), sk.joint_parents, sk.root_idx)
    root = torch.zeros(T, 3, device="cuda")
    root[:, 1] = 0.82 + (cr[:, 1] - cr[0, 1])
    root[:, 0] = cr[:, 0]
    root[:, 2] = cr[:, 2]
    p = p + root[:, None]

    core27 = {
        "core27_local": g.cpu().numpy(),
        "core27_global": g.cpu().numpy(),
        "core27_joints_m": p.cpu().numpy(),
        "root_positions_m": root.cpu().numpy(),
    }
    ref_path = out_dir / "teacher.core27.npz"
    deterministic_npz(ref_path, core27)
    return ref_path


def generate_ardy_proposal(move: dict, out_dir: Path, core27_path: Path, embedding: np.ndarray, seed: int) -> Path:
    from ardy.constraints import EndEffectorConstraintSet, FullBodyConstraintSet, Root2DConstraintSet, save_constraints_lst
    from ardy.skeleton import CoreSkeleton27

    with np.load(core27_path, allow_pickle=False) as data:
        core_local = np.asarray(data["core27_local"], dtype=np.float32)
        core_global = np.asarray(data["core27_global"], dtype=np.float32)
        core_joints = np.asarray(data["core27_joints_m"], dtype=np.float32)
        root = np.asarray(data["root_positions_m"], dtype=np.float32)
    source_frames = np.rint(np.linspace(15, 74, ARDY_FRAMES)).astype(np.int64)
    local = torch.from_numpy(core_local[source_frames])
    global_rots = torch.from_numpy(core_global[source_frames])
    joints = torch.from_numpy(core_joints[source_frames]).clone()
    roots = torch.from_numpy(root[source_frames])
    skeleton = CoreSkeleton27()
    idx = skeleton.bone_index
    for name in ("LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"):
        joints[:, idx[name]] = joints[0, idx[name]]
    left = idx["LeftHand"]
    right = idx["RightHand"]
    midpoint = (joints[:, left] + joints[:, right]) * 0.5
    axis = joints[:, right] - joints[:, left]
    axis = axis / torch.linalg.vector_norm(axis, dim=-1, keepdim=True).clamp_min(1.0e-8)
    joints[:, left] = midpoint - axis * 0.080
    joints[:, right] = midpoint + axis * 0.080
    root_2d = roots[:, [0, 2]]
    full_frames = torch.tensor([0, 20, 39], dtype=torch.long)
    hand_frames = torch.tensor([0, 8, 16, 24, 32, 39], dtype=torch.long)
    dense_frames = torch.arange(ARDY_FRAMES, dtype=torch.long)
    constraints = [
        Root2DConstraintSet(skeleton, dense_frames, root_2d, torch.zeros(ARDY_FRAMES)),
        FullBodyConstraintSet(skeleton, full_frames, joints[full_frames], global_rots[full_frames], root_2d[full_frames]),
        EndEffectorConstraintSet(skeleton, hand_frames, joints[hand_frames], global_rots[hand_frames], root_2d[hand_frames], joint_names=["LeftHand", "RightHand"]),
        EndEffectorConstraintSet(skeleton, dense_frames, joints, global_rots, root_2d, joint_names=["LeftFoot", "RightFoot", "Hips"]),
    ]
    constraints_path = out_dir / "ardy_constraints.json"
    save_constraints_lst(str(constraints_path), constraints)

    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    torch.set_default_dtype(torch.float32)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=False)

    cached_feature = torch.from_numpy(embedding)

    class CachedEncoder:
        def __call__(self, text):
            lengths = [cached_feature.shape[1] if cached_feature.dim() >= 2 else 1]
            return cached_feature.to("cuda"), lengths

    from ardy.model import load_model
    from ardy.constraints import load_constraints_lst
    from ardy.motion_rep.tools import length_to_mask
    model = load_model("ARDY-Core-RP-20FPS-Horizon40", device="cuda", text_encoder=CachedEncoder(), checkpoints_dir=str(ARDY_MODEL_ROOT))
    loaded = load_constraints_lst(str(constraints_path), model.skeleton)
    index_attributes = {"frame_indices", "pos_indices", "rot_indices"}
    for constraint in loaded:
        for name, value in vars(constraint).items():
            if isinstance(value, torch.Tensor) and name not in index_attributes:
                setattr(constraint, name, value.to("cuda"))
    lengths = torch.tensor([ARDY_FRAMES], device="cuda")
    pad_mask = length_to_mask(lengths)
    observed, mask = model.motion_rep.create_conditions_from_constraints_batched(loaded, lengths, to_normalize=True, device="cuda")
    text_feat = torch.from_numpy(embedding).to("cuda")
    text_pad_mask = torch.ones(text_feat.shape[:2], dtype=torch.bool, device="cuda")
    with torch.no_grad():
        motion = model(
            [move["prompt"]],
            ARDY_FRAMES,
            num_denoising_steps=10,
            pad_mask=pad_mask,
            first_heading_angle=torch.zeros(1, device="cuda"),
            motion_mask=mask,
            observed_motion=observed,
            cfg_weight=2.0,
            text_feat=text_feat,
            text_pad_mask=text_pad_mask,
            crop_history_length=None,
        )
        output = model.motion_rep.inverse(motion, is_normalized=True)
    arrays = {key: np.asarray(output[key]) for key in output}
    for key, arr in arrays.items():
        if not np.isfinite(arr).all():
            raise RuntimeError(f"{move['id']}: non-finite ARDY output {key}")
    out_path = out_dir / "ardy_proposal.core27.npz"
    deterministic_npz(out_path, arrays)
    return out_path


def _pack_413(root_pos: np.ndarray, posed_joints: np.ndarray, rot_mats: np.ndarray) -> np.ndarray:
    N = root_pos.shape[0]
    frames = np.zeros((N, 413), dtype=np.float32)
    frames[:, 0:3] = root_pos
    heading = np.arctan2(rot_mats[:, 0, 0, 2], rot_mats[:, 0, 2, 2])
    frames[:, 3] = np.cos(heading)
    frames[:, 4] = np.sin(heading)
    frames[:, 5:104] = (posed_joints[:, 1:] - root_pos[:, None, :]).reshape(N, -1)
    for j in range(34):
        v0 = rot_mats[:, j, :, 0]
        v1 = rot_mats[:, j, :, 1]
        norm0 = np.linalg.norm(v0, axis=1, keepdims=True) + 1e-8
        v0n = v0 / norm0
        v1p = v1 - v0n * np.sum(v0n * v1, axis=1, keepdims=True)
        norm1 = np.linalg.norm(v1p, axis=1, keepdims=True) + 1e-8
        v1n = v1p / norm1
        frames[:, 104 + j * 6 : 104 + j * 6 + 3] = v0n
        frames[:, 104 + j * 6 + 3 : 104 + j * 6 + 6] = v1n
    return frames


def train_interaction(move: dict, out_dir: Path, ardy_path: Path, seed: int) -> dict:
    sys.path.insert(0, str(MB_DIR))
    from motionbricks.motionlib.core.skeletons.g1 import G1Skeleton
    from motionbricks.motionlib.core.utils.torch_utils import batch_rigid_transform
    from torch import nn

    sk = G1Skeleton(device="cuda")
    q = sk.bone_index
    with np.load(ardy_path, allow_pickle=False) as data:
        cl = torch.from_numpy(np.asarray(data["local_rot_mats"][0]).astype("float32")).cuda()
        cr = torch.from_numpy(np.asarray(data["root_positions"][0]).astype("float32")).cuda()
    T = cl.shape[0]
    g = torch.eye(3, device="cuda").repeat(T, 34, 1, 1)
    c = {n: i for i, n in enumerate(CORE_JOINTS)}
    for gn, cn in G1_DIRECT.items():
        g[:, q[gn]] = cl[:, c[cn]]
    s = cl[:, c["Spine"]]
    for n in ("Spine1", "Spine2", "Spine3"):
        s = s @ cl[:, c[n]]
    g[:, q["waist_yaw_skel"]] = s
    from motionbricks.motionlib.core.utils.torch_utils import batch_rigid_transform
    p40, r40 = batch_rigid_transform(g, sk.neutral_joints.float()[None].repeat(T, 1, 1), sk.joint_parents, sk.root_idx)
    root40 = torch.zeros(T, 3, device="cuda")
    root40[:, 1] = 0.82 + (cr[:, 1] - cr[0, 1])
    root40[:, 0] = cr[:, 0]
    root40[:, 2] = cr[:, 2]
    p40 = p40 + root40[:, None]
    ids = torch.round(torch.linspace(0, ARDY_FRAMES - 1, MB_FRAMES, device="cuda")).long()
    p = p40[ids].clone()
    r = r40[ids].clone()
    root = root40[ids].clone()

    feet = [q[n] for n in ("left_ankle_roll_skel", "left_toe_base", "right_ankle_roll_skel", "right_toe_base")]
    for j in feet:
        p[:, j] = p[0, j]
    lh, rh = q["left_hand_roll_skel"], q["right_hand_roll_skel"]
    mid = (p[:, lh] + p[:, rh]) / 2
    axis = p[:, rh] - p[:, lh]
    axis /= torch.linalg.vector_norm(axis, dim=-1, keepdim=True).clamp_min(1e-8)
    p[:, lh] = mid - axis * 0.08
    p[:, rh] = mid + axis * 0.08
    if "root_dodge" not in move:
        root[:, [0, 2]] = root[0, [0, 2]]

    target = torch.from_numpy(_pack_413(root.cpu().numpy(), p.cpu().numpy(), r.cpu().numpy())).cuda()
    target[:, 410:413] = 1

    base_seed_path = REPO / "assets/motion/pvp005_r6/hero_strike.motionbricks.413.f32"
    b = np.fromfile(base_seed_path, dtype=np.float32).reshape(-1, 413)
    base = torch.from_numpy(resample(b, MB_FRAMES).astype(np.float32)).cuda()

    constraint = torch.zeros_like(target)
    mask = torch.zeros_like(target)
    keys = [0, 16, 32, 48, 63]
    for k in keys:
        constraint[k] = target[k]
        mask[k] = 1
    dense = [*range(0, 5), *range(410, 413)]
    for j in [*feet, lh, rh]:
        if j > 0:
            dense += list(range(5 + (j - 1) * 3, 5 + j * 3))
        dense += list(range(104 + j * 6, 104 + (j + 1) * 6))
    constraint[:, dense] = target[:, dense]
    mask[:, dense] = 1
    phase = torch.stack(
        [torch.sin(torch.linspace(0, torch.pi * 2, MB_FRAMES, device="cuda")),
         torch.cos(torch.linspace(0, torch.pi * 2, MB_FRAMES, device="cuda"))], -1)

    class Interaction(nn.Module):
        def __init__(self):
            super().__init__()
            self.inp = nn.Conv1d(1241, 256, 5, padding=2)
            self.blocks = nn.ModuleList([nn.Conv1d(256, 256, 5, padding=2 * d, dilation=d) for d in (1, 2, 4, 8)])
            self.out = nn.Conv1d(256, 413, 1)

        def forward(self, base, constraint, mask, phase):
            x = torch.cat([base, constraint, mask, phase], -1).transpose(1, 2)
            x = torch.nn.functional.gelu(self.inp(x))
            for b in self.blocks:
                x = x + torch.nn.functional.gelu(b(x))
            raw = base + self.out(x).transpose(1, 2)
            return raw * (1 - mask) + constraint * mask

    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.set_default_dtype(torch.float32)
    m = Interaction().cuda()
    opt = torch.optim.AdamW(m.parameters(), lr=2e-4)
    weights = torch.ones(413, device="cuda")
    weights[dense] = 50
    steps = 1200
    for step in range(steps):
        opt.zero_grad(set_to_none=True)
        pred = m(base[None], constraint[None], mask[None], phase[None])[0]
        loss = torch.mean((pred - target).square() * weights)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(m.parameters(), 10)
        opt.step()
    m.eval()
    with torch.no_grad():
        x = m(base[None], constraint[None], mask[None], phase[None])[0]
        y = m(base[None], constraint[None], mask[None], phase[None])[0]
    if not torch.equal(x, y):
        raise RuntimeError(f"{move['id']}: non deterministic interaction output")
    arr = x.cpu().numpy().astype(np.float32)
    pos = np.empty((MB_FRAMES, 34, 3), np.float32)
    pos[:, 0] = arr[:, :3]
    for j in range(1, 34):
        pos[:, j] = arr[:, :3] + arr[:, 5 + (j - 1) * 3 : 5 + j * 3]
    foot = {sk.bone_order_names[j]: float(np.linalg.norm(pos[:, j] - pos[0, j], axis=-1).max()) for j in feet}
    span = np.linalg.norm(pos[:, rh] - pos[:, lh], axis=-1)
    grip = float(np.abs(span - 0.16).max())
    hand = max(
        float(np.linalg.norm(pos[:, j] - p[:, j].cpu().numpy(), axis=-1).max())
        for j in (lh, rh)
    )
    raw = out_dir / "motionbricks_interaction.413.f32"
    raw.write_bytes(arr.tobytes())
    ck = out_dir / "motionbricks_interaction.pt"
    torch.save({"state_dict": {k: v.detach().cpu() for k, v in m.state_dict().items()}}, ck)
    onnx = out_dir / "motionbricks_interaction.onnx"
    torch.onnx.export(
        m,
        (base[None], constraint[None], mask[None], phase[None]),
        onnx,
        input_names=["base", "constraint", "mask", "phase"],
        output_names=["target"],
        opset_version=18,
        dynamo=False,
    )
    metrics = {
        "schema": "just-dodge-r6k-motionbricks-interaction-v1",
        "move_id": move["id"],
        "action": move["action"],
        "status": "pass" if max(foot.values()) < 0.01 and grip < 0.01 and hand < 0.01 else "fail",
        "frames": MB_FRAMES,
        "fps": MB_FPS,
        "seed": seed,
        "steps": steps,
        "foot_drift_m": foot,
        "grip_error_max_m": grip,
        "hand_target_error_max_m": hand,
        "target_mse": float(np.mean((arr - target.cpu().numpy()) ** 2)),
        "pack413_sha256": sha256(raw),
        "checkpoint_sha256": sha256(ck),
        "onnx_sha256": sha256(onnx),
        "runtime_admitted": False,
        "promoted": False,
        "authority": "motion/stance/retarget/in-between only; no opponent/contact/injury/reaction/outcome inputs or outputs",
    }
    write_json(out_dir / "metrics.json", metrics)
    if metrics["status"] != "pass":
        raise RuntimeError(f"{move['id']}: interaction gate failed: {json.dumps(metrics)}")
    return metrics


def run_move(move: dict) -> dict:
    move_id = move["id"]
    seed = SEED_BASE + hash(move_id) % 1000
    out_dir = OUT_ROOT / move_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    embedding = embed_prompt(move["prompt"], seed)
    constraints_path, hand_residuals = build_kimodo_constraints(move, out_dir)
    teacher_path = generate_kimodo_teacher(move, out_dir, constraints_path, embedding, seed)
    core27_path = map_teacher_to_core27(teacher_path, move, out_dir)
    ardy_path = generate_ardy_proposal(move, out_dir, core27_path, embedding, seed)
    metrics = train_interaction(move, out_dir, ardy_path, seed)
    metrics["kimodo_teacher_sha256"] = sha256(teacher_path)
    metrics["ardy_proposal_sha256"] = sha256(ardy_path)
    metrics["authored_hand_residual_max_m"] = float(np.max(hand_residuals))
    write_json(out_dir / "receipt.json", metrics)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moves", nargs="*", default=None, help="move ids to run (default: all)")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    batch = json.loads(BATCH_SPEC.read_text())
    moves = batch["moves"]
    if args.list:
        for m in moves:
            print(m["id"], m["action"])
        return
    verify_environment()
    prepare_text_bundle()
    selected = moves if not args.moves else [m for m in moves if m["id"] in args.moves]
    results = []
    for move in selected:
        print(f"=== {move['id']} ({move['action']}) ===", flush=True)
        try:
            metrics = run_move(move)
            results.append({"id": move["id"], "status": "pass", "metrics": metrics})
            print(f"PASS {move['id']}: foot={max(metrics['foot_drift_m'].values()):.4f} grip={metrics['grip_error_max_m']:.6f} hand={metrics['hand_target_error_max_m']:.4f}", flush=True)
        except Exception as error:
            import traceback
            traceback.print_exc()
            results.append({"id": move["id"], "status": "fail", "error": str(error)})
            print(f"FAIL {move['id']}: {error}", flush=True)
    summary_path = OUT_ROOT / "batch_summary.json"
    write_json(summary_path, {"schema": "just-dodge-r6k-move-batch-summary-v1", "results": results})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
