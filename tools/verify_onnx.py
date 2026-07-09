#!/usr/bin/env python3
"""Smoke-test exported MotionBrains ONNX artifacts."""
import os
import numpy as np
import onnxruntime as ort

ASSETS = "assets"


def run_pose_backbone():
    sess = ort.InferenceSession(os.path.join(ASSETS, "motionbricks_pose_backbone.onnx"))
    n_tokens = 8
    pose_tokens = np.random.randint(0, 11, (1, n_tokens, 8), dtype=np.int64)
    local_root = np.random.randn(1, n_tokens * 4, 4).astype(np.float32)
    pose_cond = np.zeros((1, n_tokens * 4, 304), dtype=np.float32)
    has_pose = np.zeros((1, n_tokens * 4), dtype=np.bool_)
    num_tokens = np.array([[n_tokens]], dtype=np.int64)
    out = sess.run(None, {
        "pose_tokens": pose_tokens,
        "local_root_values": local_root,
        "pose_cond": pose_cond,
        "has_pose_cond": has_pose,
        "num_tokens": num_tokens,
    })
    logits = out[0]
    assert logits.shape[:3] == (1, n_tokens, 8), logits.shape
    assert logits.shape[-1] in (10, 11), logits.shape
    assert np.isfinite(logits).all()
    print("pose_backbone OK", logits.shape)


def run_root_backbone():
    sess = ort.InferenceSession(os.path.join(ASSETS, "motionbricks_root_backbone.onnx"))
    n = 8
    g = np.random.randn(1, n, 5).astype(np.float32)
    hg = np.ones((1, n), dtype=np.bool_)
    l = np.random.randn(1, n, 4).astype(np.float32)
    hl = np.ones((1, n), dtype=np.bool_)
    p = np.random.randn(1, n, 304).astype(np.float32)
    hp = np.ones((1, n), dtype=np.bool_)
    nt = np.array([[8]], dtype=np.int64)
    out = sess.run(None, {
        "global_root_values": g, "has_global_root": hg,
        "local_root_values": l, "has_local_root": hl,
        "poses": p, "has_poses": hp, "num_tokens": nt,
    })
    pred_global, num_logits = out
    assert pred_global.shape[0] == 1 and pred_global.shape[2] == 5, pred_global.shape
    assert num_logits.shape[0] == 1, num_logits.shape
    assert np.isfinite(pred_global).all() and np.isfinite(num_logits).all()
    print("root_backbone OK", pred_global.shape, num_logits.shape)


if __name__ == "__main__":
    run_pose_backbone()
    run_root_backbone()
