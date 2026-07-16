#!/usr/bin/env python3
"""Validate v4 constraint compilation against pinned ARDY APIs without a model."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARDY_ROOT = Path(os.environ.get("JUST_DODGE_ARDY_ROOT", "/run/media/vdubrov/NVMe-Storage1/ardy"))
SPEC = ROOT / "assets/qa/pvp005_ardy_action_endpoints_v4.json"
ACTIONS = ("strike", "block", "grab")
SIDES = ("left", "right")

sys.path.insert(0, str(ROOT / "tools/qa"))
sys.path.insert(0, str(ARDY_ROOT))

def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    import torch
    from ardy.motion_rep.conditioning import build_condition_dicts
    from ardy.skeleton.definitions import G1Skeleton34
    from generate_pvp005_ardy_keypose_candidates import (
        G1_ROOT_HEIGHT_M,
        build_materialized_constraints,
    )
    from pvp005_ardy_v4_materializer import materialize

    revision = subprocess.run(
        ["git", "-C", str(ARDY_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    require(revision == spec["source_commit"], "pinned ARDY revision drift")
    w0_path = ROOT / spec["w0_contract"]["path"]
    w0 = json.loads(w0_path.read_text(encoding="utf-8"))
    document = materialize(spec, w0, spec_sha256=sha256(SPEC), w0_sha256=sha256(w0_path))

    skeleton_dir = ARDY_ROOT / "ardy/assets/skeletons/g1skel34"
    skeleton = G1Skeleton34(folder=str(skeleton_dir))
    require(skeleton.nbjoints == 34, "G1 skeleton joint-count drift")
    require(torch.isfinite(skeleton.neutral_joints).all().item(), "G1 neutral joints are non-finite")
    require("ardy.model" not in sys.modules, "condition validator imported the ARDY model")
    require(not torch.cuda.is_initialized(), "condition validator initialized CUDA")

    hand_indices = {
        "left": skeleton.bone_index["left_hand_roll_skel"],
        "right": skeleton.bone_index["right_hand_roll_skel"],
    }
    foot_indices = {
        "left": (
            skeleton.bone_index["left_ankle_roll_skel"],
            skeleton.bone_index["left_toe_base"],
        ),
        "right": (
            skeleton.bone_index["right_ankle_roll_skel"],
            skeleton.bone_index["right_toe_base"],
        ),
    }

    for action_name in ACTIONS:
        action = document["actions"][action_name]
        constraints = build_materialized_constraints(skeleton, action, "cpu")
        index_dict, data_dict = build_condition_dicts(constraints)

        root_indices = torch.cat(index_dict["root_2d"])
        root_data = torch.cat(data_dict["root_2d"])
        require(torch.equal(root_indices, torch.arange(spec["frames"])), f"{action_name}: root index drift")
        require(torch.equal(root_data, torch.tensor(action["root_xz_m"])), f"{action_name}: root data drift")

        root_y_indices = torch.cat(index_dict["root_y_pos"])
        root_y_data = torch.cat(data_dict["root_y_pos"])
        require(torch.equal(root_y_indices, torch.arange(spec["frames"])), f"{action_name}: root-y index drift")
        require(
            torch.equal(root_y_data, torch.full((spec["frames"],), G1_ROOT_HEIGHT_M)),
            f"{action_name}: root-y data drift",
        )

        actual_indices = torch.cat(index_dict["global_joints_positions"])
        actual_data = torch.cat(data_dict["global_joints_positions"])
        require(torch.isfinite(actual_data).all().item(), f"{action_name}: non-finite position constraints")
        actual_pairs = [tuple(int(value) for value in row) for row in actual_indices.tolist()]
        require(len(actual_pairs) == len(set(actual_pairs)), f"{action_name}: duplicate position constraint")
        actual = {pair: actual_data[index] for index, pair in enumerate(actual_pairs)}

        expected: dict[tuple[int, int], torch.Tensor] = {}
        for frame, (root_x, root_z) in enumerate(action["root_xz_m"]):
            expected[(frame, skeleton.root_idx)] = torch.tensor(
                [root_x, G1_ROOT_HEIGHT_M, root_z],
                dtype=torch.float32,
            )
        for pose in action["hand_keyposes"]:
            expected[(pose["frame"], hand_indices["left"])] = torch.tensor(pose["left_hand_world_m"])
            expected[(pose["frame"], hand_indices["right"])] = torch.tensor(pose["right_hand_world_m"])
        for target in action["planted_foot_targets"]:
            side = target["side"]
            offset_x, offset_z = target["anchor_offset_xz_m"]
            offset = torch.tensor(
                [offset_x, G1_ROOT_HEIGHT_M, offset_z],
                dtype=torch.float32,
            )
            for joint_index in foot_indices[side]:
                expected[(target["frame"], joint_index)] = (
                    skeleton.neutral_joints[joint_index].to(dtype=torch.float32) + offset
                )

        require(set(actual) == set(expected), f"{action_name}: sparse position index set drift")
        for pair, expected_position in expected.items():
            require(torch.equal(actual[pair], expected_position), f"{action_name}/{pair}: position data drift")

        for side in SIDES:
            for frame, target in enumerate(action["foot_contact_targets"][side]):
                for joint_index in foot_indices[side]:
                    present = (frame, joint_index) in actual
                    require(present == (target == 1), f"{action_name}/{side}/f{frame}: swing-foot constraint leak")

    require("ardy.model" not in sys.modules, "condition compilation loaded the ARDY model")
    require(not torch.cuda.is_initialized(), "condition compilation initialized CUDA")
    print(f"PVP005_ARDY_V4_CONDITION_SOURCE={revision}")
    print("PVP005_ARDY_V4_CONDITION_BUILD=PASS_SPARSE_CPU_NO_MODEL")
    print("PVP005_ARDY_V4_GENERATION=NOT_RUN")
    print("PLAYABLE_PROOF=false")


if __name__ == "__main__":
    main()
