#!/usr/bin/env python3
"""Falsify the released MotionBricks checkpoint as an online interaction solver."""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from motionbricks_service.generate import _run_inference, init_service

OUTPUT = ROOT / "qa_runs/m3_contact_truth_001/b14w_online_solver_contract"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    service = init_service()
    inferencer = service["inferencer"]
    pose = inferencer._pose_model.backbone_net
    root = inferencer._root_model.backbone_net

    predict_parameters = tuple(inspect.signature(inferencer.predict).parameters)
    pose_source = inspect.getsource(inferencer._predict_pose_tokens)
    adapter_source = inspect.getsource(_run_inference)
    facts = {
        "pose_accepts_text_embedding": bool(pose.ACCEPT_TEXT_EMB_INPUT),
        "root_accepts_text_embedding": bool(root.ACCEPT_TEXT_EMB_INPUT),
        "predict_parameters": predict_parameters,
        "has_interaction_parameter": any(
            "interaction" in parameter for parameter in predict_parameters
        ),
        "frames_per_token": int(pose.get_num_frames_per_token()),
        "min_tokens": int(pose._args["min_tokens"]),
        "max_tokens": int(pose._args["max_tokens"]),
        "root_start_end_embedding_frames": int(
            root._input_position_emb.num_embeddings
        ),
        "pose_uses_first_context_block": (
            "batch['local_poses'][:, :num_frames_per_token]" in pose_source
        ),
        "pose_uses_final_target_block": (
            "batch['local_poses'][:, -num_frames_per_token + i]" in pose_source
        ),
        "adapter_concatenates_context_and_target": (
            "torch.cat([ctx_local_poses, tgt_local_poses], dim=1)"
            in adapter_source
        ),
        "adapter_constraint_count_expression": "2 * NUM_F" in adapter_source,
    }
    if facts["pose_accepts_text_embedding"] or facts["root_accepts_text_embedding"]:
        raise RuntimeError("checkpoint unexpectedly enables a text condition channel")
    if facts["has_interaction_parameter"]:
        raise RuntimeError("released inferencer unexpectedly exposes interaction input")
    if facts["frames_per_token"] != 4:
        raise RuntimeError(f"unexpected frames/token: {facts['frames_per_token']}")
    if (facts["min_tokens"], facts["max_tokens"]) != (6, 16):
        raise RuntimeError(
            f"unexpected token horizon: {facts['min_tokens']}..{facts['max_tokens']}"
        )
    if facts["root_start_end_embedding_frames"] != 8:
        raise RuntimeError(
            "released root model no longer has the verified four-start/four-end boundary"
        )
    required = (
        "pose_uses_first_context_block",
        "pose_uses_final_target_block",
        "adapter_concatenates_context_and_target",
        "adapter_constraint_count_expression",
    )
    missing = [name for name in required if not facts[name]]
    if missing:
        raise RuntimeError(f"source contract changed; missing probes: {missing}")

    official_root = Path(inspect.getfile(type(inferencer))).resolve().parents[2]
    files = {
        "motion_inference": Path(inspect.getfile(type(inferencer))).resolve(),
        "pose_backbone": Path(inspect.getfile(type(pose))).resolve(),
        "root_backbone": Path(inspect.getfile(type(root))).resolve(),
        "adapter": Path(inspect.getfile(_run_inference)).resolve(),
    }
    metrics = {
        "verdict": "released_checkpoint_requires_interaction_conditioning_extension",
        "facts": facts,
        "source_files": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in files.items()
        },
        "official_checkout_root": str(official_root),
    }
    metrics_path = OUTPUT / "metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, sort_keys=True))
    print("B14W_RELEASED_CHECKPOINT_REJECTED_FOR_ONLINE_CONDITIONING=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
