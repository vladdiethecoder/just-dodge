"""Deterministic MotionBrains inference service for Just Dodge.

NOTE: This module currently returns a deterministic stub clip because the full
PyTorch inference pipeline (pose_model + root_model + vqvae + motion_rep +
clip_holder) depends on:

1. Agent B completing Tasks 6-8 and producing the full ONNX backbones.
2. Agent A completing Task 9 and producing the first production primitive in
   assets/data/primitives.ron.

Once those artifacts are present, replace the stub return path in
`generate_clip` with a real `full_navigation_agent.generate_new_frames` call.
"""
import os
import numpy as np

_SERVICE = None


def init_service(
    mb_dir: str = "/run/media/vdubrov/Bulk-SSD/gr00t/motionbricks",
    checkpoint_dir: str = "/run/media/vdubrov/Bulk-SSD/gr00t/motionbricks/out",
):
    global _SERVICE
    if _SERVICE is not None:
        return _SERVICE

    # Real initialization would load:
    #   - pose_model / root_model from checkpoint_dir
    #   - vqvae, motion_rep
    #   - clip_holder_G1 and full_navigation_agent
    # These are blocked on Tasks 6-9, so we leave the service in stub mode.
    _SERVICE = {
        "ready": True,
        "mb_dir": mb_dir,
        "checkpoint_dir": checkpoint_dir,
        "real_inference": False,
    }
    return _SERVICE


def _context_to_features(context_frames: list) -> np.ndarray:
    """Convert incoming [34, 4x4] world matrices to a [frames, 34, 4, 4] float array."""
    if not context_frames:
        ctx = np.zeros((1, 34, 4, 4), dtype=np.float32)
        for j in range(34):
            ctx[0, j] = np.eye(4, dtype=np.float32)
        return ctx
    return np.stack(context_frames, axis=0).astype(np.float32)


def _generate_stub(seed: int) -> np.ndarray:
    """Deterministic [30, 413] float32 clip used while real inference is blocked."""
    rng = np.random.default_rng(seed)
    frames = np.zeros((30, 413), dtype=np.float32)
    # Pelvis height so the character stands on the ground.
    frames[:, 1] = 0.9
    # Slight sinusoidal variation to prove determinism and avoid all-zero frames.
    t = np.arange(30, dtype=np.float32)
    frames[:, 0] = np.sin(t * 0.2) * 0.05
    frames[:, 2] = np.cos(t * 0.2) * 0.05
    # Perturb arm joints in the 6D rotation channels (indices 104..307) slightly.
    rot_start = 104
    rot_end = 308
    noise = rng.uniform(-0.05, 0.05, size=(30, rot_end - rot_start)).astype(np.float32)
    frames[:, rot_start:rot_end] = noise
    return frames


def generate_clip(
    action: str,
    weapon: str,
    stance: str,
    context_frames: list,  # list of [34, 4x4] world matrices
    seed: int = 0,
) -> bytes:
    """
    Returns raw float32 bytes of [N, 413] frames (same layout as parse_g1_frame).

    Currently this is a deterministic stub because the full MotionBricks
    inference pipeline is waiting on Agent B (ONNX backbone export) and Agent A
    (first production primitive). The stub is NOT a motion fallback — it is a
    bridge-only placeholder that will be removed once real inference is wired.
    """
    svc = init_service()
    assert svc["ready"]

    # Real path (blocked):
    #   ctx = _context_to_features(context_frames)
    #   primitive = select_primitive(action, weapon, stance)
    #   agent = build_full_navigation_agent(...)
    #   qpos = matrices_to_mujoco_qpos(ctx)
    #   output = agent.generate_new_frames({...})
    #   frames = motion_rep.inverse(output) -> [N, 413]
    #   return frames.tobytes()

    if not svc.get("real_inference", False):
        # TODO(Agent B): remove this branch once ONNX backbones + primitives exist.
        frames = _generate_stub(seed)
        return frames.tobytes()

    raise NotImplementedError("Real MotionBricks inference not yet enabled")
