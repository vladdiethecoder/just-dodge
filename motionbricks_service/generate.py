"""Real MotionBrains root + pose + VQVAE inference service for Just Dodge.

The service loads the GR00T MotionBricks pose/root/VQVAE checkpoints once in
`init_service()` and exposes `generate_clip(action, weapon, stance,
context_frames, seed)` which returns deterministic float32 bytes of shape
`[N, 413]` (the same layout as `motion::parse_g1_frame`).
"""
import math
import os
from types import SimpleNamespace
from typing import Any, Optional

import numpy as np
import pyron
import torch

from .interaction_forward import apply_fk_targets, parse_authorized_request

_SERVICE: dict | None = None
_OFFICIAL_SERVICE: dict | None = None

# Paths to the GR00T MotionBricks checkout and its trained checkpoints.
# All paths can be overridden via environment variables (see README.md).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MB_DIR_DEFAULT = os.path.abspath(
    os.path.join(_PROJECT_ROOT, "..", "gr00t", "motionbricks")
)
_CHECKPOINT_DIR_DEFAULT = os.path.abspath(
    os.path.join(_PROJECT_ROOT, "..", "gr00t", "motionbricks", "out")
)

MB_DIR = os.getenv("MB_DIR", _MB_DIR_DEFAULT)
CHECKPOINT_DIR = os.getenv("CHECKPOINT_DIR", _CHECKPOINT_DIR_DEFAULT)
PRIMITIVES_RON = os.path.join(_PROJECT_ROOT, "assets", "data", "primitives.ron")
SKELETON_XML = os.getenv(
    "SKELETON_XML", os.path.join(MB_DIR, "assets", "skeletons", "g1", "g1.xml")
)
CLIP_CKPT = os.getenv("CLIP_CKPT", os.path.join(CHECKPOINT_DIR, "G1-clip.ckpt"))


class DictNamespace(dict):
    """Dict that also supports attribute access, needed for MotionModel args."""

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def _dict_to_namespace(d: dict) -> DictNamespace:
    ns = DictNamespace()
    for k, v in d.items():
        ns[k] = _dict_to_namespace(v) if isinstance(v, dict) else v
    return ns


def _build_motion_rep(cfg: dict) -> Any:
    """Instantiate the MotionBricks dual-root global-joints representation."""
    from motionbricks.motionlib.core.motion_reps.dual_root_global_joints import (
        GlobalRootGlobalJoints,
    )
    from motionbricks.motionlib.core.skeletons.g1 import G1Skeleton34
    from motionbricks.motionlib.core.utils.stats import Stats

    skel_cfg = cfg.get("skeleton", {})
    folder = skel_cfg.get("folder", "")
    if folder and not os.path.isabs(folder):
        folder = os.path.join(MB_DIR, folder)
    skeleton = G1Skeleton34(
        folder=folder, name=skel_cfg.get("name"), t_pose=skel_cfg.get("t_pose", "capture")
    )

    motion_rep_cfg = cfg.get("motion_rep", {})
    stats_folder = motion_rep_cfg.get("stats", {}).get("folder", "")
    if stats_folder and not os.path.isabs(stats_folder):
        stats_folder = os.path.join(MB_DIR, stats_folder)
    stats = Stats(folder=stats_folder)

    return GlobalRootGlobalJoints(
        name="g1skel34_dual_root_global_joints",
        stats=stats,
        skeleton=skeleton,
        fps=cfg.get("fps", 30),
    )


def _load_vqvae(pose_hparams: dict, local_motion_rep: Any) -> Any:
    """Build and load the VQVAE from the separate VQVAE checkpoint."""
    from tools.export_motionbricks_onnx import build_pose_vqvae

    vqvae = build_pose_vqvae(pose_hparams, local_motion_rep)
    vqvae_ckpt = torch.load(
        os.path.join(
            CHECKPOINT_DIR,
            "motionbricks_vqvae",
            "version_1",
            "checkpoints",
            "model-step=2000000.ckpt",
        ),
        map_location="cpu",
        weights_only=True,
    )
    vqvae_sd = {}
    for k, v in vqvae_ckpt["state_dict"].items():
        if k.startswith("pose_net."):
            vqvae_sd[k.replace("pose_net.", "")] = v

    # Patch the decoder output layer if the checkpoint has a different channel count.
    if "decoder.model.6.weight" in vqvae_sd:
        ckpt_out = vqvae_sd["decoder.model.6.weight"].shape[0]
        if vqvae.decoder.model[6].weight.shape[0] != ckpt_out:
            import torch.nn as nn

            old_conv = vqvae.decoder.model[6]
            new_conv = nn.Conv1d(
                old_conv.in_channels,
                ckpt_out,
                old_conv.kernel_size,
                stride=old_conv.stride,
                padding=old_conv.padding,
                dilation=old_conv.dilation,
                groups=old_conv.groups,
                bias=old_conv.bias is not None,
            )
            vqvae.decoder.model[6] = new_conv
    missing, unexpected = vqvae.load_state_dict(vqvae_sd, strict=False)
    if missing or unexpected:
        print(
            f"[motionbricks_service] VQVAE loaded: {len(vqvae_sd)} keys, "
            f"{len(missing)} missing, {len(unexpected)} unexpected"
        )
    return vqvae


def _load_backbone(checkpoint_path: str, build_fn: Any, motion_rep: Any) -> Any:
    """Build a backbone network and load its checkpoint."""
    # hparams.yaml lives in the version directory, not the checkpoints directory.
    version_dir = os.path.dirname(os.path.dirname(checkpoint_path))
    hparams = _load_yaml_cfg(os.path.join(version_dir, "hparams.yaml"))
    backbone, _ = build_fn(hparams, motion_rep)
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    back_sd = {}
    for k, v in ckpt["state_dict"].items():
        if k.startswith("backbone_net."):
            back_sd[k.replace("backbone_net.", "")] = v
    missing, unexpected = backbone.load_state_dict(back_sd, strict=False)
    if missing or unexpected:
        print(
            f"[motionbricks_service] backbone loaded: {len(back_sd)} keys, "
            f"{len(missing)} missing, {len(unexpected)} unexpected"
        )
    return hparams, backbone


def _load_yaml_cfg(path: str) -> dict:
    """Read a Hydra YAML config and resolve ${...} interpolations."""
    from tools.export_motionbricks_onnx import load_yaml_cfg

    return load_yaml_cfg(path)


def _ensure_canonical_motionbricks_import() -> Any:
    """Import MotionBricks only from the configured checkout."""
    import importlib
    import sys

    canonical_dir = os.path.abspath(MB_DIR)
    if not os.path.isdir(canonical_dir):
        raise RuntimeError(f"MotionBricks checkout is missing: {canonical_dir}")

    cached = sys.modules.get("motionbricks")
    cached_file = getattr(cached, "__file__", None)
    if cached_file is not None and not os.path.abspath(cached_file).startswith(
        canonical_dir + os.sep
    ):
        for name in list(sys.modules):
            if name == "motionbricks" or name.startswith("motionbricks."):
                del sys.modules[name]

    if canonical_dir in sys.path:
        sys.path.remove(canonical_dir)
    sys.path.insert(0, canonical_dir)
    motionbricks = importlib.import_module("motionbricks")
    module_file = motionbricks.__file__
    if module_file is None or not os.path.abspath(module_file).startswith(
        canonical_dir + os.sep
    ):
        raise RuntimeError(
            "Refusing non-canonical MotionBricks import: "
            f"{module_file}; expected under {canonical_dir}"
        )
    return motionbricks


def init_service(
    mb_dir: str = MB_DIR,
    checkpoint_dir: str = CHECKPOINT_DIR,
) -> dict:
    """Load the MotionBrains pose/root models, VQVAE, and clip holder once."""
    global _SERVICE
    if _SERVICE is not None:
        return _SERVICE

    _ensure_canonical_motionbricks_import()
    from motionbricks.helper.mujoco_helper import get_mujoco_converter
    from motionbricks.motion_backbone.demo.clips import clip_holder_G1
    from motionbricks.motion_backbone.inference.motion_inference import motion_inference
    from motionbricks.motion_backbone.models.pose_model import MotionModel as PoseModel
    from motionbricks.motion_backbone.models.root_model import MotionModel as RootModel
    from tools.export_motionbricks_onnx import build_pose_backbone, build_root_backbone

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[motionbricks_service] initializing on {device}")

    pose_hparams = _load_yaml_cfg(
        os.path.join(checkpoint_dir, "motionbricks_pose", "version_1", "hparams.yaml")
    )
    motion_rep = _build_motion_rep(pose_hparams)
    local_motion_rep = motion_rep.dual_rep.local_motion_rep

    vqvae = _load_vqvae(pose_hparams, local_motion_rep)
    pose_backbone = _load_backbone(
        os.path.join(
            checkpoint_dir,
            "motionbricks_pose",
            "version_1",
            "checkpoints",
            "model-step=2000000.ckpt",
        ),
        build_pose_backbone,
        motion_rep,
    )[1]

    pose_args = _dict_to_namespace(pose_hparams["model"]["args"])
    pose_args.vqvae_model_ckpt_path = os.path.join(
        checkpoint_dir,
        "motionbricks_vqvae",
        "version_1",
        "checkpoints",
        "model-step=2000000.ckpt",
    )
    pose_model = PoseModel(
        pose_vqvae_network=vqvae,
        root_vqvae_network=None,
        backbone_network=pose_backbone,
        motion_rep=motion_rep,
        args=pose_args,
    )

    root_hparams, root_backbone = _load_backbone(
        os.path.join(
            checkpoint_dir,
            "motionbricks_root",
            "version_1",
            "checkpoints",
            "model-step=2000000.ckpt",
        ),
        build_root_backbone,
        motion_rep,
    )
    root_args = _dict_to_namespace(root_hparams["model"]["args"])
    root_args.vqvae_model_ckpt_path = pose_args.vqvae_model_ckpt_path
    root_model = RootModel(
        pose_vqvae_network=None,
        root_vqvae_network=None,
        backbone_network=root_backbone,
        motion_rep=motion_rep,
        args=root_args,
    )

    inferencer = motion_inference(
        {"pose": pose_model, "root": root_model}, pose_args, device=device
    )
    converter = get_mujoco_converter(motion_rep, SKELETON_XML).to(device)
    clip_holder = clip_holder_G1(
        train_dataloader=None,
        ckpt_path=CLIP_CKPT,
        converter=converter,
        reprocess_clips=False,
    ).to(device)

    _SERVICE = {
        "ready": True,
        "mb_dir": mb_dir,
        "checkpoint_dir": checkpoint_dir,
        "device": device,
        "inferencer": inferencer,
        "motion_rep": motion_rep,
        "converter": converter,
        "clip_holder": clip_holder,
        "num_frames_per_token": 4,
        "num_tokens": 8,
    }
    print("[motionbricks_service] ready")
    return _SERVICE


def init_official_service() -> dict:
    """Initialize NVIDIA's unmodified navigation wrapper around MotionBricks.

    The wrapper owns canonicalization, spring-target construction, qpos
    filtering, and MuJoCo conversion; this service must not duplicate them.
    """
    global _OFFICIAL_SERVICE
    if _OFFICIAL_SERVICE is not None:
        return _OFFICIAL_SERVICE

    _ensure_canonical_motionbricks_import()
    from motionbricks.motion_backbone.demo.utils import navigation_demo

    scene_xml = os.path.join(MB_DIR, "assets", "skeletons", "g1", "scene_29dof.xml")
    args = SimpleNamespace(
        humanoid_xml=scene_xml,
        humanoid_scene_xml=scene_xml,
        skeleton_xml=SKELETON_XML,
        result_dir=CHECKPOINT_DIR,
        data_root=os.path.join(MB_DIR, "datasets"),
        explicit_dataset_folder=None,
        clips_ckpt=CLIP_CKPT,
        reprocess_clips=False,
        controller="random",
        lookat_movement_direction=False,
        pre_filter_qpos=True,
        source_root_realignment=True,
        target_root_realignment=True,
        force_canonicalization=True,
        skip_ending_target_cond=False,
        random_speed_scale=False,
        speed_scale=[1.0, 1.0],
        generate_dt=2.0,
        clips="G1",
        random_seed=1234,
        return_model_configs=True,
        return_dataloader=True,
        recording_dir=None,
        EXP="default",
        planner="default",
        use_qpos=True,
        allowed_mode=None,
    )
    prior_cwd = os.getcwd()
    try:
        # NVIDIA's checked-in Hydra configs intentionally contain paths relative
        # to the MotionBricks checkout (for example `out/.../skeleton`).
        os.chdir(MB_DIR)
        demo = navigation_demo(args)
    finally:
        os.chdir(prior_cwd)
    _OFFICIAL_SERVICE = {"args": args, "demo": demo, "agent": demo.full_agent}
    return _OFFICIAL_SERVICE


def _load_primitives() -> list[dict]:
    """Parse the RON primitive library into a list of primitive dicts.

    Each dict contains the keys: action, weapon, stance, source_id,
    feature_window, root_target.
    """
    if not os.path.exists(PRIMITIVES_RON):
        raise FileNotFoundError(f"Primitive library not found: {PRIMITIVES_RON}")
    with open(PRIMITIVES_RON, "r", encoding="utf-8") as f:
        text = f.read()

    data = pyron.loads(text, preserve_class_names=True)
    primitives = data.get("primitives", [])

    def _normalize(value: Any) -> Any:
        """Convert pyron unit-enum markers to plain strings recursively."""
        if isinstance(value, dict):
            if len(value) == 1 and "!__name__" in value:
                return value["!__name__"]
            return {k: _normalize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_normalize(v) for v in value]
        return value

    return [_normalize(p) for p in primitives]


def _load_primitive(action: str, weapon: str, stance: str) -> np.ndarray:
    """Read the RON primitive library and return the matching feature window.

    Returns the primitive's `feature_window` as a float32 NumPy array.
    Raises ValueError if no matching primitive exists.
    """
    action = action.lower()
    weapon = weapon.lower()
    stance = stance.lower()

    for primitive in _load_primitives():
        if (
            str(primitive.get("action")).lower() == action
            and str(primitive.get("weapon")).lower() == weapon
            and str(primitive.get("stance")).lower() == stance
        ):
            return np.array(primitive["feature_window"], dtype=np.float32)

    raise ValueError(
        f"No primitive found for {action}/{weapon}/{stance} in {PRIMITIVES_RON}"
    )


def _context_to_transforms(
    context_frames: Any, svc: dict
) -> tuple[torch.Tensor, torch.Tensor]:
    """Convert incoming [N, 34, 4, 4] world matrices to global positions/rotations.

    If the context is None, empty, or degenerate (all identity), fall back to
    the neutral idle pose from the clip holder.
    """
    converter = svc["converter"]
    clip_holder = svc["clip_holder"]
    device = svc["device"]
    NUM_F = svc["num_frames_per_token"]

    ctx = None if context_frames is None else np.asarray(context_frames, dtype=np.float32)
    use_neutral = ctx is None or ctx.size == 0
    if not use_neutral and ctx.ndim == 4 and ctx.shape[1:] == (34, 4, 4):
        # Degenerate pose detection: all matrices are identity.
        eye = np.eye(4, dtype=np.float32)
        if np.allclose(ctx, eye, atol=1e-6):
            use_neutral = True

    if use_neutral:
        idle_qpos = clip_holder.mujoco_qpos[0, 0:1].to(device)
        ctx_qpos = idle_qpos[None, :1].repeat(1, NUM_F, 1)
        return converter.convert_mujoco_qpos_to_motion_transforms(ctx_qpos)

    # Convert world matrices to global positions and rotation matrices.
    if ctx.ndim != 4 or ctx.shape[1:] != (34, 4, 4):
        raise ValueError(
            f"context_frames must be [N, 34, 4, 4], got shape {ctx.shape}"
        )

    positions = torch.from_numpy(ctx[:, :, :3, 3]).to(device)
    rotations = torch.from_numpy(ctx[:, :, :3, :3]).to(device)

    # Pad or trim to exactly NUM_F frames.
    n = positions.shape[0]
    if n < NUM_F:
        positions = torch.cat([positions] + [positions[-1:]] * (NUM_F - n), dim=0)
        rotations = torch.cat([rotations] + [rotations[-1:]] * (NUM_F - n), dim=0)
    elif n > NUM_F:
        positions = positions[-NUM_F:]
        rotations = rotations[-NUM_F:]

    return positions[None], rotations[None]


def _build_root_values(
    positions: torch.Tensor, rotations: torch.Tensor
) -> torch.Tensor:
    """Global root values: [pos_x, pos_y, pos_z, cos(heading), sin(heading)]."""
    root_pos = positions[:, :, 0, :]
    heading = torch.atan2(rotations[:, :, 0, 0, 2], rotations[:, :, 0, 2, 2])
    return torch.cat(
        [root_pos, torch.cos(heading)[..., None], torch.sin(heading)[..., None]], dim=-1
    )


def _build_local_root_values(root_values: torch.Tensor, fps: float) -> torch.Tensor:
    """Finite-difference local root velocities from global root values."""
    B, F, _ = root_values.shape
    local = torch.zeros([B, F, 4], device=root_values.device, dtype=root_values.dtype)
    angle = torch.atan2(root_values[:, :, 4], root_values[:, :, 3])
    if F > 1:
        local[:, : F - 1, 0] = (
            ((angle[:, 1:] - angle[:, :-1] + math.pi) % (2 * math.pi)) - math.pi
        ) * fps
        local[:, : F - 1, 1:3] = (
            root_values[:, 1:, [0, 2]] - root_values[:, :-1, [0, 2]]
        ) * fps
        local[:, : F - 1, 3] = root_values[:, : F - 1, 1]
    return local


def _build_local_poses(
    positions: torch.Tensor,
    rotations: torch.Tensor,
    is_context: bool,
) -> torch.Tensor:
    """Local pose feature used by the root/pose backbones."""
    from motionbricks.motionlib.core.utils.rotations import matrix_to_cont6d

    B, F = rotations.shape[0], rotations.shape[1]
    if is_context:
        joint_positions = positions[:, :, 1:, :].clone()
        joint_positions[..., 0] = positions[:, :, 1:, 0] - positions[:, :, :1, 0]
        joint_positions[..., 2] = positions[:, :, 1:, 2] - positions[:, :, :1, 2]
    else:
        joint_positions = positions[:, :, 1:, :]
    rot6d = matrix_to_cont6d(rotations)
    return torch.cat(
        [
            joint_positions.reshape(B, F, -1),
            rot6d.reshape(B, F, -1),
        ],
        dim=-1,
    )


def _run_inference(
    ctx_pos: torch.Tensor,
    ctx_rot: torch.Tensor,
    tgt_pos: torch.Tensor,
    tgt_rot: torch.Tensor,
    svc: dict,
) -> torch.Tensor:
    """Run MotionBrains inference and return unnormalized global motion features."""
    inferencer = svc["inferencer"]
    fps = svc["motion_rep"].fps
    device = svc["device"]
    NUM_F = svc["num_frames_per_token"]
    num_tokens = svc["num_tokens"]
    B = 1

    ctx_root = _build_root_values(ctx_pos, ctx_rot)
    ctx_local_root = _build_local_root_values(ctx_root, fps)
    ctx_local_poses = _build_local_poses(ctx_pos, ctx_rot, is_context=True)

    tgt_root = _build_root_values(tgt_pos, tgt_rot)
    tgt_local_root = _build_local_root_values(tgt_root, fps)
    tgt_local_poses = _build_local_poses(tgt_pos, tgt_rot, is_context=False)

    global_root_values = torch.cat([ctx_root, tgt_root], dim=1)
    local_root_values = torch.cat([ctx_local_root, tgt_local_root], dim=1)
    local_poses = torch.cat([ctx_local_poses, tgt_local_poses], dim=1)

    has_global = torch.ones(B, 2 * NUM_F, dtype=torch.bool, device=device)
    has_local = torch.ones(B, 2 * NUM_F, dtype=torch.bool, device=device)
    has_poses = torch.ones(B, 2 * NUM_F, dtype=torch.bool, device=device)
    # The last velocity in the context window is ill-defined.
    has_local[:, NUM_F - 1] = False

    nt = torch.full([B], num_tokens, dtype=torch.int, device=device)
    config = {
        "num_inference_step": 1,
        "smooth_root_traj": False,
        "allow_pred_out_of_reach_num_tokens": False,
        "pose_token_sampling_use_argmax": True,
        "skip_ending_target_cond": True,
    }

    pred_global_motions, pred_num_tokens = inferencer.predict(
        global_root_values,
        has_global,
        local_root_values,
        has_local,
        local_poses,
        has_poses,
        nt,
        config=config,
    )
    num_pred_frames = int((pred_num_tokens * NUM_F).item())
    return pred_global_motions[:, :num_pred_frames, :]


def _pack_413_frames(
    root_pos: np.ndarray, posed_joints: np.ndarray, rot_mats: np.ndarray
) -> np.ndarray:
    """Pack authoritative global transforms into the Rust [N, 413] layout."""
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

    # local_vel [308:410] and foot_contacts [410:413] remain zero.
    return frames


def _to_413_frames(pred_global_motions: torch.Tensor, motion_rep: Any) -> np.ndarray:
    """Convert unnormalized global motion features to the Rust [N, 413] layout."""
    out = motion_rep.inverse(
        pred_global_motions, is_normalized=False, return_quat=False, return_all=False
    )
    return _pack_413_frames(
        out["root_pos"][0].detach().cpu().numpy(),
        out["posed_joints"][0].detach().cpu().numpy(),
        out["global_joint_rots"][0].detach().cpu().numpy(),
    )


def _reset_official_episode(agent: Any, demo: Any) -> None:
    """Reset every stateful upstream navigation-controller field we exercise.

    The upstream base reset clears only `_prev_qpos`; `random_controller` also
    caches `_control` and `_time_since_prev_control`, which otherwise leaks one
    request's control target into the next same-seed request.
    """
    agent.reset()
    controller = demo.controller
    controller.reset()
    if hasattr(controller, "_control"):
        controller._control = None
    if hasattr(controller, "_time_since_prev_control"):
        controller._time_since_prev_control = 0.0


def generate_official_navigation_clip(seed: int = 0) -> bytes:
    """Run one exact NVIDIA MotionBricks controller/replan cycle.

    It returns a healthy 34-joint G1 locomotion trajectory. It intentionally
    accepts no combat-action label: the released navigation checkpoint has no
    Strike/Block/Thrust conditioning, so combat semantics remain fail-closed.
    """
    svc = init_official_service()
    args = svc["args"]
    demo = svc["demo"]
    agent = svc["agent"]

    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    _reset_official_episode(agent, demo)

    qpos = agent.get_next_frame()
    demo.mj_data.qpos[:] = qpos[0]
    controls = demo.controller.generate_control_signals(
        None,
        demo.mj_model,
        demo.mj_data,
        visualize=False,
        control_info={"force_idle": False, "allowed_mode": None},
    )
    controls["context_mujoco_qpos"] = agent.get_context_mujoco_qpos()
    with torch.no_grad():
        agent.generate_new_frames(
            controls,
            demo.controller.get_controller_dt() * args.generate_dt,
            force_generation=True,
        )

    positions, rotations = agent._converter.convert_mujoco_qpos_to_motion_transforms(
        agent.frames["mujoco_qpos"]
    )
    frames = _pack_413_frames(
        positions[0, :, 0, :].detach().cpu().numpy(),
        positions[0].detach().cpu().numpy(),
        rotations[0].detach().cpu().numpy(),
    )
    if not np.isfinite(frames).all():
        raise RuntimeError("Official MotionBricks trajectory contains non-finite values")
    return frames.tobytes()


def load_primitive_clip(
    action: str, weapon: str, stance: str, root_lock: bool = True
) -> bytes:
    """Return the measured primitive clip without neural generation.

    This is the source-validity/calibration path: it proves serialization and
    retargeting against the real mocap window before generated output is trusted.
    """
    svc = init_service()
    feature_window = _load_primitive(action, weapon, stance)
    features = torch.from_numpy(feature_window[None]).to(svc["device"])
    out = svc["motion_rep"].inverse(
        features, is_normalized=True, return_quat=False, return_all=False
    )
    frames = _pack_413_frames(
        out["root_pos"][0].detach().cpu().numpy(),
        out["posed_joints"][0].detach().cpu().numpy(),
        out["global_joint_rots"][0].detach().cpu().numpy(),
    )
    if not np.isfinite(frames).all():
        raise RuntimeError("Primitive clip contains non-finite values")
    if root_lock and frames.shape[0] > 0:
        frames[:, 0:3] = frames[0, 0:3]
    return frames.tobytes()


def generate_clip(
    action: str,
    weapon: str,
    stance: str,
    context_frames: Optional[list] = None,  # list of [34, 4, 4] world matrices
    seed: int = 0,
    root_lock: bool = True,
) -> bytes:
    """Generate a deterministic combat clip and return raw float32 bytes of [N, 413].

    Args:
        root_lock: If True, subtract the first-frame root translation from all
            generated frames. This prevents the VQVAE from extrapolating small
            capture-space root drift into runaway global motion during gameplay.
    """
    svc = init_service()
    assert svc["ready"]

    # Determinism: fix all seeds and disable non-deterministic CuDNN heuristics.
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    device = svc["device"]
    motion_rep = svc["motion_rep"]

    feature_window = _load_primitive(action, weapon, stance)
    fw_t = torch.from_numpy(feature_window[None]).to(device)
    # The primitive library stores normalized MotionBricks features.
    tgt_out = motion_rep.inverse(
        fw_t, is_normalized=True, return_quat=False, return_all=False
    )
    tgt_pos = tgt_out["posed_joints"]
    tgt_rot = tgt_out["global_joint_rots"]

    ctx_pos, ctx_rot = _context_to_transforms(context_frames, svc)

    pred_global_motions = _run_inference(ctx_pos, ctx_rot, tgt_pos, tgt_rot, svc)
    frames = _to_413_frames(pred_global_motions, motion_rep)

    if not np.isfinite(frames).all():
        raise RuntimeError("Generated clip contains non-finite values")

    if root_lock and frames.shape[0] > 0:
        # Root-lock the clip: keep the pose (root-relative joint positions and
        # global rotations) but pin the global root translation to the first frame.
        # This prevents the VQVAE from drifting across the arena during generation.
        frames[:, 0:3] = frames[0, 0:3]

    return frames.tobytes()


def generate_interaction_clip(
    proposal_document: dict,
    certificate_document: dict,
) -> bytes:
    """Generate one certificate-authorized offline interaction-conditioned clip.

    The accepted document carries sparse global SO(3) FK targets. This adapter
    is intentionally unavailable to normal runtime action dispatch: callers
    must present a content-addressed ARDY proposal and exact offline-only
    certificate before the GPU service is initialized.
    """
    proposal, _certificate = parse_authorized_request(proposal_document, certificate_document)
    svc = init_service()
    assert svc["ready"]

    torch.manual_seed(proposal.seed)
    torch.cuda.manual_seed_all(proposal.seed)
    np.random.seed(proposal.seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    feature_window = _load_primitive(proposal.action, proposal.weapon, proposal.stance)
    device = svc["device"]
    motion_rep = svc["motion_rep"]
    target_out = motion_rep.inverse(
        torch.from_numpy(feature_window[None]).to(device),
        is_normalized=True,
        return_quat=False,
        return_all=False,
    )
    target_positions, target_rotations = apply_fk_targets(
        target_out["posed_joints"],
        target_out["global_joint_rots"],
        proposal,
    )

    context = None
    if proposal.context_frame is not None:
        context = np.asarray([proposal.context_frame], dtype=np.float32)
    context_positions, context_rotations = _context_to_transforms(context, svc)
    prediction = _run_inference(
        context_positions,
        context_rotations,
        target_positions,
        target_rotations,
        svc,
    )
    frames = _to_413_frames(prediction, motion_rep)
    if not np.isfinite(frames).all():
        raise RuntimeError("Authorized interaction clip contains non-finite values")
    return frames.tobytes()
