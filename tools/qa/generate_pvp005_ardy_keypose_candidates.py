#!/usr/bin/env python3
"""Generate fixed-seed PVP-005 proposals from pinned ARDY keypose constraints."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from pvp005_ardy_v4_materializer import SPEC_SCHEMA, canonical_bytes, materialize


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPEC = Path("assets/qa/pvp005_ardy_keyposes_v1.json")
DEFAULT_V4_SPEC = Path("assets/qa/pvp005_ardy_action_endpoints_v4.json")
DEFAULT_ARDY = Path(os.environ.get("JUST_DODGE_ARDY_ROOT", "/run/media/vdubrov/NVMe-Storage1/ardy"))
G1_ROOT_HEIGHT_M = 0.78
PVP005_GENERATION_ENABLED = False
GENERATION_DISABLED_MESSAGE = "PVP-005 ARDY generation is disabled pending a content-addressed authorization certificate"
AUTHORIZATION_SCHEMA = "just-dodge-pvp005-ardy-v4-generation-authorization-v1"
ACTIONS = ("strike", "block", "grab")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def repository_file(path: Path, label: str) -> Path:
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"{label} path must be repository-relative without traversal")
    resolved = (ROOT / path).resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as error:
        raise SystemExit(f"{label} must remain inside the repository") from error
    if not resolved.is_file():
        raise SystemExit(f"{label} is not a file: {resolved}")
    return resolved


def repository_contract_file(value: object, label: str) -> Path:
    if not isinstance(value, str):
        raise SystemExit(f"{label} path must be a string")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise SystemExit(f"{label} path must be repository-relative without traversal")
    return repository_file(relative, label)


def load_strict_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()

    def reject_constant(token: str) -> None:
        raise ValueError(f"non-finite JSON constant {token}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key}")
            result[key] = value
        return result

    def require_finite(value: object, location: str = "$") -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"non-finite JSON number at {location}")
        if isinstance(value, dict):
            for key, item in value.items():
                require_finite(item, f"{location}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                require_finite(item, f"{location}[{index}]")

    try:
        document = json.loads(
            raw.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
        require_finite(document)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"invalid strict JSON in {label}: {error}") from error
    if not isinstance(document, dict):
        raise SystemExit(f"{label} must contain a JSON object")
    return document, raw


def load_v4_sources(
    spec_candidate: Path,
) -> tuple[Path, dict[str, Any], str, dict[str, Any], str]:
    spec_path = repository_file(spec_candidate, "ARDY endpoint spec")
    spec, spec_bytes = load_strict_json(spec_path, "ARDY endpoint spec")
    contract = spec.get("w0_contract")
    if not isinstance(contract, dict):
        raise SystemExit("ARDY endpoint spec has no W0 contract")
    w0_path = repository_contract_file(contract.get("path"), "W0 contract")
    w0, w0_bytes = load_strict_json(w0_path, "W0 contract")
    w0_hash = sha256_bytes(w0_bytes)
    if contract.get("sha256") != w0_hash:
        raise SystemExit("loaded W0 bytes do not match the declared contract hash")
    return spec_path, spec, sha256_bytes(spec_bytes), w0, w0_hash


def git_revision(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def load_authorization_certificate(
    path: Path,
    *,
    spec_path: Path,
    spec_sha256: str,
    spec: dict[str, object],
    materialized_sha256: str,
    output: Path,
) -> dict[str, object]:
    certificate_path = repository_file(path, "ARDY generation authorization")
    certificate, _ = load_strict_json(
        certificate_path, "ARDY generation authorization"
    )
    if certificate.get("schema") != AUTHORIZATION_SCHEMA:
        raise SystemExit("unsupported ARDY generation authorization schema")
    if certificate.get("status") != "authorized_one_bounded_offline_probe_batch":
        raise SystemExit("ARDY generation authorization status drift")
    try:
        output_relative = str(output.relative_to(ROOT))
        spec_relative = str(spec_path.relative_to(ROOT))
    except ValueError as error:
        raise SystemExit("authorized ARDY paths must remain inside the repository") from error
    checks = {
        "output_path": output_relative,
        "spec_path": spec_relative,
        "spec_sha256": spec_sha256,
        "generator_path": str(Path(__file__).resolve().relative_to(ROOT)),
        "generator_sha256": sha256(Path(__file__).resolve()),
        "materialized_sha256": materialized_sha256,
        "ardy_source_commit": spec["source_commit"],
        "model": spec["model"],
        "actions": list(ACTIONS),
        "text_conditioning": False,
        "runtime_admission": False,
        "truth_authority": False,
        "one_shot": True,
    }
    for key, expected in checks.items():
        if certificate.get(key) != expected:
            raise SystemExit(f"ARDY authorization {key} drift")
    seeds = certificate.get("seeds")
    if not isinstance(seeds, list) or not seeds or len(seeds) > 2:
        raise SystemExit("ARDY authorization must bind one or two seeds")
    if any(not isinstance(seed, int) for seed in seeds):
        raise SystemExit("ARDY authorization seed type drift")
    if certificate.get("max_candidates") != len(ACTIONS) * len(seeds):
        raise SystemExit("ARDY authorization candidate bound drift")
    if certificate.get("diffusion_steps") != 10 or certificate.get("constraint_weight") != 3.0:
        raise SystemExit("ARDY authorization generation controls drift")
    condition_hashes = certificate.get("condition_sha256")
    if not isinstance(condition_hashes, dict) or tuple(condition_hashes) != ACTIONS:
        raise SystemExit("ARDY authorization condition receipt set drift")
    if any(not isinstance(value, str) or len(value) != 64 for value in condition_hashes.values()):
        raise SystemExit("ARDY authorization condition receipt malformed")
    return certificate


def build_constraints(model, keyframes: list[dict[str, object]], device: str):
    import torch
    from ardy.constraints import Root2DConstraintSet, create_pairs

    class PositionOnlyConstraintSet:
        def __init__(self, frame_indices, positions, joint_indices, root_y=None):
            self.frame_indices = frame_indices
            self.positions = positions
            self.joint_indices = torch.tensor(joint_indices)
            self.root_y = root_y

        def update_constraints(self, data_dict, index_dict):
            indices = create_pairs(self.frame_indices, self.joint_indices)
            data_dict["global_joints_positions"].append(
                self.positions[:, self.joint_indices].reshape(-1, 3)
            )
            index_dict["global_joints_positions"].append(indices)
            if self.root_y is not None:
                data_dict["root_y_pos"].append(self.root_y)
                index_dict["root_y_pos"].append(self.frame_indices)

    skeleton = model.skeleton
    frame_indices = torch.tensor([item["frame"] for item in keyframes])
    sparse_root_xz = torch.tensor(
        [item["root_xz_m"] for item in keyframes], dtype=torch.float32, device=device
    )
    frames = int(model.gen_horizon_len)
    dense_frames = torch.arange(frames)
    root_xz = torch.empty((frames, 2), dtype=torch.float32, device=device)
    for left, right in zip(range(len(keyframes) - 1), range(1, len(keyframes))):
        start = int(keyframes[left]["frame"])
        end = int(keyframes[right]["frame"])
        alpha = torch.linspace(0.0, 1.0, end - start + 1, device=device)[:, None]
        root_xz[start : end + 1] = sparse_root_xz[left].lerp(sparse_root_xz[right], alpha)
    roots = torch.cat(
        [
            sparse_root_xz[:, :1],
            torch.full((len(keyframes), 1), 0.78, device=device),
            sparse_root_xz[:, 1:],
        ],
        dim=1,
    )
    neutral = skeleton.neutral_joints.to(device=device, dtype=torch.float32)
    positions = neutral[None].repeat(len(keyframes), 1, 1)
    positions = positions + roots[:, None]

    names = skeleton.bone_index
    for index, item in enumerate(keyframes):
        for side in ("left", "right"):
            endpoint = torch.tensor(item[f"{side}_hand_m"], dtype=torch.float32, device=device)
            wrist = endpoint - torch.tensor([0.0, 0.0, 0.10], device=device)
            positions[index, names[f"{side}_wrist_yaw_skel"]] = wrist
            positions[index, names[f"{side}_hand_roll_skel"]] = endpoint

    heading = torch.zeros(frames, device=device)
    root_constraint = Root2DConstraintSet(
        skeleton,
        dense_frames,
        root_xz,
        global_root_heading=heading,
    )
    hand_indices = [
        names["pelvis_skel"],
        names["left_wrist_yaw_skel"],
        names["left_hand_roll_skel"],
        names["right_wrist_yaw_skel"],
        names["right_hand_roll_skel"],
    ]
    hands = PositionOnlyConstraintSet(frame_indices, positions, hand_indices)
    foot_indices = [
        names["pelvis_skel"],
        names["left_ankle_roll_skel"],
        names["left_toe_base"],
        names["right_ankle_roll_skel"],
        names["right_toe_base"],
    ]
    initial_root = torch.tensor([0.0, 0.78, 0.0], device=device)
    dense_positions = neutral[None].repeat(frames, 1, 1) + initial_root
    dense_positions[:, names["pelvis_skel"], 0] = root_xz[:, 0]
    dense_positions[:, names["pelvis_skel"], 1] = 0.78
    dense_positions[:, names["pelvis_skel"], 2] = root_xz[:, 1]
    feet = PositionOnlyConstraintSet(
        dense_frames,
        dense_positions,
        foot_indices,
        root_y=torch.full((frames,), 0.78, device=device),
    )
    return [root_constraint, hands, feet]


def build_materialized_constraints(skeleton, action: dict[str, object], device: str):
    """Compile materialized v4 rows into sparse ARDY constraint objects."""

    import torch
    from ardy.constraints import Root2DConstraintSet

    class IndexedPositionConstraintSet:
        def __init__(self, indices, positions):
            self.indices = indices
            self.positions = positions

        def update_constraints(self, data_dict, index_dict):
            data_dict["global_joints_positions"].append(self.positions)
            index_dict["global_joints_positions"].append(self.indices)

    class RootHeightConstraintSet:
        def __init__(self, frame_indices, root_y):
            self.frame_indices = frame_indices
            self.root_y = root_y

        def update_constraints(self, data_dict, index_dict):
            data_dict["root_y_pos"].append(self.root_y)
            index_dict["root_y_pos"].append(self.frame_indices)

    root_xz = torch.tensor(action["root_xz_m"], dtype=torch.float32, device=device)
    frames = len(root_xz)
    if frames == 0:
        raise ValueError("materialized v4 action has no frames")
    frame_indices = torch.arange(frames)
    root_constraint = Root2DConstraintSet(
        skeleton,
        frame_indices,
        root_xz,
        global_root_heading=torch.zeros(frames, dtype=torch.float32, device=device),
    )
    root_height = RootHeightConstraintSet(
        frame_indices,
        torch.full((frames,), G1_ROOT_HEIGHT_M, dtype=torch.float32, device=device),
    )

    names = skeleton.bone_index
    hand_indices = {
        "left": names["left_hand_roll_skel"],
        "right": names["right_hand_roll_skel"],
    }
    foot_indices = {
        "left": (names["left_ankle_roll_skel"], names["left_toe_base"]),
        "right": (names["right_ankle_roll_skel"], names["right_toe_base"]),
    }
    position_indices = []
    position_values = []
    for frame, (root_x, root_z) in enumerate(action["root_xz_m"]):
        position_indices.append([frame, skeleton.root_idx])
        position_values.append([root_x, G1_ROOT_HEIGHT_M, root_z])
    for pose in action["hand_keyposes"]:
        frame = int(pose["frame"])
        for side in ("left", "right"):
            position_indices.append([frame, hand_indices[side]])
            position_values.append(pose[f"{side}_hand_world_m"])

    neutral = skeleton.neutral_joints.to(dtype=torch.float32, device=device)
    for target in action["planted_foot_targets"]:
        side = target["side"]
        frame = int(target["frame"])
        offset_x, offset_z = target["anchor_offset_xz_m"]
        world_offset = torch.tensor(
            [offset_x, G1_ROOT_HEIGHT_M, offset_z],
            dtype=torch.float32,
            device=device,
        )
        for joint_index in foot_indices[side]:
            position_indices.append([frame, joint_index])
            position_values.append((neutral[joint_index] + world_offset).tolist())

    positions = IndexedPositionConstraintSet(
        torch.tensor(position_indices, dtype=torch.long),
        torch.tensor(position_values, dtype=torch.float32, device=device),
    )
    return [root_constraint, root_height, positions]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--ardy-root", type=Path, default=DEFAULT_ARDY)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument(
        "--materialize-only",
        type=Path,
        metavar="OUTPUT_JSON",
        help="materialize endpoint-v4 constraints without importing ARDY or running a model",
    )
    args = parser.parse_args()
    if args.materialize_only is not None:
        if args.output is not None:
            parser.error("--materialize-only cannot be combined with --output")
        spec_path, spec, spec_hash, w0, w0_hash = load_v4_sources(
            args.spec or DEFAULT_V4_SPEC
        )
        output = args.materialize_only.resolve()
        if output.exists():
            raise SystemExit(f"refusing to overwrite materialized ARDY constraints: {output}")
        encoded = canonical_bytes(
            materialize(
                spec,
                w0,
                spec_sha256=spec_hash,
                w0_sha256=w0_hash,
            )
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(encoded)
        print(f"PVP005_ARDY_V4_MATERIALIZED={output}")
        print(f"PVP005_ARDY_V4_MATERIALIZED_SHA256={hashlib.sha256(encoded).hexdigest()}")
        print("PVP005_ARDY_V4_GENERATION=NOT_RUN")
        return

    if args.output is None:
        parser.error("--output is required for proposal generation")

    import numpy as np

    ardy_root = args.ardy_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite ARDY proposal output: {output}")
    authorization = None
    materialized_document = None
    materialized_sha256 = None
    if args.authorization is not None:
        spec_path, spec, spec_hash, w0, w0_hash = load_v4_sources(
            args.spec or DEFAULT_V4_SPEC
        )
        if spec.get("schema") != SPEC_SCHEMA:
            raise SystemExit("certificate-gated generation requires endpoint-v4 constraints")
        materialized_document = materialize(
            spec,
            w0,
            spec_sha256=spec_hash,
            w0_sha256=w0_hash,
        )
        materialized_sha256 = hashlib.sha256(canonical_bytes(materialized_document)).hexdigest()
        authorization = load_authorization_certificate(
            args.authorization,
            spec_path=spec_path,
            spec_sha256=spec_hash,
            spec=spec,
            materialized_sha256=materialized_sha256,
            output=output,
        )
    elif not PVP005_GENERATION_ENABLED:
        raise SystemExit(GENERATION_DISABLED_MESSAGE)
    else:
        spec_path = repository_file(args.spec or DEFAULT_SPEC, "ARDY keypose spec")
        spec, _ = load_strict_json(spec_path, "ARDY keypose spec")
        if spec.get("schema") not in {
            "just-dodge-pvp005-ardy-keyposes-v1",
            "just-dodge-pvp005-ardy-keyposes-v2",
        }:
            raise SystemExit("unsupported ARDY keypose schema")

    controls = authorization if authorization is not None else spec
    seeds = controls["seeds"]
    diffusion_steps = int(controls["diffusion_steps"])
    constraint_weight = float(controls["constraint_weight"])
    revision = git_revision(ardy_root)
    if revision != spec["source_commit"]:
        raise SystemExit(f"ARDY revision drift: {revision} != {spec['source_commit']}")
    if spec.get("text_conditioning") is not False:
        raise SystemExit("PVP-005 ARDY proposals must disable text conditioning")

    sys.path.insert(0, str(ardy_root))
    import torch
    from ardy.model import load_model
    from ardy.motion_rep.tools import length_to_mask
    from ardy.tools import seed_everything
    from huggingface_hub import snapshot_download

    if not torch.cuda.is_available():
        raise SystemExit("pinned ARDY proposal generation requires CUDA")
    device = "cuda:0"
    model_snapshot = Path(
        snapshot_download(repo_id=f"nvidia/{spec['model']}", local_files_only=True)
    )
    with contextlib.redirect_stdout(sys.stderr):
        model = load_model(spec["model"], device=device, text_encoder=False)
    if type(model.skeleton).__name__ != "G1Skeleton34":
        raise SystemExit(f"unexpected ARDY skeleton: {type(model.skeleton).__name__}")
    if int(model.gen_horizon_len) != spec["frames"] or int(model.motion_rep.fps) != spec["fps"]:
        raise SystemExit("ARDY horizon/FPS drift from keypose contract")
    if int(model.diffusion.num_base_steps) != diffusion_steps:
        raise SystemExit("ARDY diffusion-step contract drift")

    output.mkdir(parents=True)
    receipts = []
    frames = int(spec["frames"])
    lengths = torch.tensor([frames], device=device)
    pad_mask = length_to_mask(lengths)
    llm_dim = int(model.denoiser.llm_shape[-1])
    for action in ACTIONS:
        if materialized_document is not None:
            constraints = build_materialized_constraints(
                model.skeleton,
                materialized_document["actions"][action],
                device,
            )
        else:
            keyframes = spec["actions"][action]["keyframes"]
            constraints = build_constraints(model, keyframes, device)
        observed, motion_mask = model.motion_rep.create_conditions_from_constraints_batched(
            constraints,
            lengths,
            to_normalize=True,
            device=device,
        )
        action_root = output / action
        action_root.mkdir()
        for candidate_index, seed in enumerate(seeds):
            seed_everything(int(seed))
            torch.cuda.synchronize()
            started = time.perf_counter()
            with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
                motion = model(
                    [""],
                    frames,
                    num_denoising_steps=diffusion_steps,
                    pad_mask=pad_mask,
                    first_heading_angle=torch.zeros(1, device=device),
                    motion_mask=motion_mask,
                    observed_motion=observed,
                    cfg_weight=(0.0, constraint_weight),
                    text_feat=torch.zeros(1, 1, llm_dim, device=device),
                    text_pad_mask=torch.zeros(1, 1, dtype=torch.bool, device=device),
                )
                decoded = model.motion_rep.inverse(motion, is_normalized=True)
            torch.cuda.synchronize()
            generation_ms = (time.perf_counter() - started) * 1000.0
            required = (
                "posed_joints",
                "global_rot_mats",
                "local_rot_mats",
                "root_positions",
                "foot_contacts",
                "global_root_heading",
            )
            missing = [name for name in required if name not in decoded]
            if missing:
                raise SystemExit(f"ARDY output missing {missing}")
            arrays = {
                name: decoded[name][0].detach().cpu().numpy()
                for name in required
            }
            if not all(np.isfinite(value).all() for value in arrays.values()):
                raise SystemExit(f"non-finite ARDY proposal: {action}/{candidate_index}")
            family = "v4" if materialized_document is not None else "kp"
            candidate = f"{action}_ardy_{family}_{candidate_index:02d}"
            path = action_root / f"{candidate}.npz"
            np.savez_compressed(path, **arrays)
            receipts.append(
                {
                    "action": action,
                    "candidate": candidate,
                    "seed": seed,
                    "generation_ms": round(generation_ms, 3),
                    "path": str(path.relative_to(ROOT)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )

    manifest = {
        "schema": (
            "just-dodge-pvp005-ardy-endpoint-v4-proposals-v1"
            if materialized_document is not None
            else "just-dodge-pvp005-ardy-keypose-proposals-v1"
        ),
        "authority": "offline_motion_proposal_only",
        "admitted": False,
        "runtime_generation": False,
        "source_repository": "https://github.com/nv-tlabs/ardy",
        "source_commit": revision,
        "source_license_sha256": sha256(ardy_root / "LICENSE"),
        "model": spec["model"],
        "model_snapshot": model_snapshot.name,
        "model_license_sha256": sha256(model_snapshot / "LICENSE"),
        "model_config_sha256": sha256(model_snapshot / "config.yaml"),
        "model_denoiser_sha256": sha256(model_snapshot / "denoiser.safetensors"),
        "model_tokenizer_sha256": sha256(model_snapshot / "tokenizer.safetensors"),
        "skeleton": type(model.skeleton).__name__,
        "keypose_spec_path": str(spec_path.relative_to(ROOT)),
        "keypose_spec_sha256": sha256(spec_path),
        "materialized_constraints_sha256": materialized_sha256,
        "authorization_path": (
            str(args.authorization.resolve().relative_to(ROOT))
            if args.authorization is not None
            else None
        ),
        "authorization_sha256": (
            sha256(args.authorization.resolve()) if args.authorization is not None else None
        ),
        "generation_controls": {
            "seeds": seeds,
            "diffusion_steps": diffusion_steps,
            "constraint_weight": constraint_weight,
        },
        "text_conditioning": False,
        "candidates": receipts,
    }
    manifest_path = output / "generation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"PVP005_ARDY_KEYPOSE_MANIFEST_SHA256={sha256(manifest_path)}")
    print(f"PVP005_ARDY_KEYPOSE_PROPOSALS={len(receipts)}")


if __name__ == "__main__":
    main()
