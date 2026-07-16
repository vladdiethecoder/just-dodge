#!/usr/bin/env python3
"""Compile v4 constraints through the pinned ARDY motion representation on CPU.

This gate loads the released model only to access its motion-representation
normalization and condition compiler. It never calls the model forward path.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""

ROOT = Path(__file__).resolve().parents[2]
ARDY_ROOT = Path(os.environ.get("JUST_DODGE_ARDY_ROOT", "/run/media/vdubrov/NVMe-Storage1/ardy"))
SPEC = ROOT / "assets/qa/pvp005_ardy_action_endpoints_v4.json"
ACTIONS = ("strike", "block", "grab")
EXPECTED_SHAPE = (1, 52, 414)
EXPECTED_CONDITION_SHA256 = {
    "strike": "ea8f7392445479d4c52a2ab7bb1b0de4c78be6f01f8cce253d722f5f85f10866",
    "block": "8f3c62ad915ea91588ed82edf46c61092ff2703ce303204d3c252ec1b4a4de53",
    "grab": "65c9e03a2bec2f85dcb141a85c098bae8d2efbb8fb8ab9202ced3d6aba0a565c",
}

sys.path.insert(0, str(ROOT / "tools/qa"))
sys.path.insert(0, str(ARDY_ROOT))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tensor_hash(observed, mask) -> str:
    payload = observed.detach().contiguous().numpy().tobytes()
    payload += mask.detach().contiguous().numpy().tobytes()
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    import torch
    from ardy.model import load_model
    from generate_pvp005_ardy_keypose_candidates import (
        PVP005_GENERATION_ENABLED,
        build_materialized_constraints,
    )
    from pvp005_ardy_v4_materializer import materialize

    require(PVP005_GENERATION_ENABLED is False, "repository ARDY generation gate was enabled")
    require(not torch.cuda.is_available(), "condition-tensor gate must not expose CUDA")
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
    document = materialize(
        spec,
        w0,
        spec_sha256=sha256(SPEC),
        w0_sha256=sha256(w0_path),
    )

    with contextlib.redirect_stdout(sys.stderr):
        model = load_model(spec["model"], device="cpu", text_encoder=False)
    require(type(model.skeleton).__name__ == "G1Skeleton34", "ARDY skeleton drift")
    require(int(model.gen_horizon_len) == spec["frames"], "ARDY horizon drift")
    require(int(model.motion_rep.fps) == spec["fps"], "ARDY FPS drift")
    lengths = torch.tensor([spec["frames"]], dtype=torch.long)

    hashes = []
    for action_name in ACTIONS:
        constraints = build_materialized_constraints(
            model.skeleton,
            document["actions"][action_name],
            "cpu",
        )
        first_observed, first_mask = model.motion_rep.create_conditions_from_constraints_batched(
            constraints,
            lengths,
            to_normalize=True,
            device="cpu",
        )
        second_observed, second_mask = model.motion_rep.create_conditions_from_constraints_batched(
            constraints,
            lengths,
            to_normalize=True,
            device="cpu",
        )
        require(tuple(first_observed.shape) == EXPECTED_SHAPE, f"{action_name}: observed shape drift")
        require(tuple(first_mask.shape) == EXPECTED_SHAPE, f"{action_name}: mask shape drift")
        require(torch.isfinite(first_observed).all().item(), f"{action_name}: non-finite observed motion")
        require(torch.isfinite(first_mask).all().item(), f"{action_name}: non-finite motion mask")
        require(set(torch.unique(first_mask).tolist()) <= {0.0, 1.0}, f"{action_name}: non-binary motion mask")
        require(torch.equal(first_observed, second_observed), f"{action_name}: observed motion is nondeterministic")
        require(torch.equal(first_mask, second_mask), f"{action_name}: motion mask is nondeterministic")
        digest = tensor_hash(first_observed, first_mask)
        require(
            digest == EXPECTED_CONDITION_SHA256[action_name],
            f"{action_name}: normalized condition receipt drift",
        )
        hashes.append(digest)
        print(
            f"PVP005_ARDY_V4_CONDITION action={action_name} "
            f"shape={EXPECTED_SHAPE} mask_true={int(first_mask.sum())} sha256={digest}"
        )

    require(len(set(hashes)) == len(ACTIONS), "action-specific normalized conditions converged")
    require(not torch.cuda.is_initialized(), "condition-tensor gate initialized CUDA")
    print(f"PVP005_ARDY_V4_CONDITION_SOURCE={revision}")
    print("PVP005_ARDY_V4_NORMALIZED_CONDITIONS=PASS_CPU_NO_GENERATION")
    print("PLAYABLE_PROOF=false")


if __name__ == "__main__":
    main()
