"""Deterministic MotionBrains inference service for Just Dodge."""
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
    # TODO: load pose_model, root_model, vqvae, motion_rep, clip_holder
    _SERVICE = {"ready": True, "mb_dir": mb_dir}
    return _SERVICE


def generate_clip(
    action: str,
    weapon: str,
    stance: str,
    context_frames: list,  # list of [34, 4x4] world matrices
    seed: int = 0,
) -> bytes:
    """
    Returns raw float32 bytes of [N, 413] frames (same layout as parse_g1_frame).
    """
    svc = init_service()
    assert svc["ready"]
    # TODO: run full_agent.generate_new_frames with the combat primitive.
    # Stub: return deterministic zero frames to prove the bridge.
    frames = np.zeros((30, 413), dtype=np.float32)
    frames[:, 1] = 0.9  # pelvis height
    return frames.tobytes()
