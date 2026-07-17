#!/usr/bin/env python3
"""Generate exactly one ARDY candidate from the admitted PVP005-R6 rotation proof."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARDY = Path("/run/media/vdubrov/NVMe-Storage1/ardy")
DEFAULT_SPEC = ROOT / "assets/qa/pvp005_ardy_action_endpoints_v4.json"
SEED = 2026071601
DIFFUSION_STEPS = 10
CONSTRAINT_WEIGHT = 3.0

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_pvp005_r6_rotation_strike as rotation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ardy-root", type=Path, default=DEFAULT_ARDY)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite one-candidate output: {output}")
    proof_path = args.proof.resolve()
    trajectory_path = args.trajectory.resolve()
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    if proof.get("schema") != "just-dodge-pvp005-r6-rotation-conditioning-proof-v1":
        raise SystemExit("unsupported rotation-proof schema")
    if proof.get("status") != "pass_representation_proof_no_diffusion_run":
        raise SystemExit("rotation representation proof has not passed")
    if proof.get("diffusion_candidates_generated") != 0:
        raise SystemExit("rotation proof is not the pre-generation certificate")
    current_revision = __import__("subprocess").check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    if proof.get("repository_revision") != current_revision:
        raise SystemExit("repository revision drift from rotation proof")
    if proof.get("ardy_revision") != __import__("subprocess").check_output(
        ["git", "-C", str(args.ardy_root.resolve()), "rev-parse", "HEAD"], text=True
    ).strip():
        raise SystemExit("ARDY revision drift from rotation proof")

    archive = np.load(trajectory_path)
    required_input = {
        "global_rot_mats": (rotation.FRAMES, 34, 3, 3),
        "root_positions": (rotation.FRAMES, 3),
        "desired_left_hand": (rotation.FRAMES, 3),
        "desired_right_hand": (rotation.FRAMES, 3),
        "desired_foot_positions": (rotation.FRAMES, 4, 3),
    }
    for name, shape in required_input.items():
        if name not in archive or archive[name].shape != shape or not np.isfinite(archive[name]).all():
            raise SystemExit(f"rotation trajectory field drift: {name}")

    sys.path.insert(0, str(args.ardy_root.resolve()))
    import torch
    from ardy.motion_rep.tools import length_to_mask
    from ardy.tools import seed_everything

    device = "cuda:0"
    model = rotation.load_pinned_model(args.ardy_root.resolve(), device)
    if int(model.diffusion.num_base_steps) != DIFFUSION_STEPS:
        raise SystemExit("ARDY diffusion-step drift")
    root = torch.as_tensor(archive["root_positions"], device=device, dtype=torch.float32)
    global_rotations = torch.as_tensor(
        archive["global_rot_mats"], device=device, dtype=torch.float32
    )
    constraint = rotation.DenseRotationConstraint(root, global_rotations)
    lengths = torch.tensor([rotation.FRAMES], device=device)
    observed, motion_mask = model.motion_rep.create_conditions_from_constraints_batched(
        [constraint], lengths, to_normalize=True, device=device
    )
    global_mask = motion_mask[0, :, model.motion_rep.slice_dict["global_rot_data"]]
    root_mask = motion_mask[0, :, model.motion_rep.slice_dict["root_pos"]]
    if not bool(global_mask.all()) or not bool(root_mask.all()):
        raise SystemExit("generation mask lost dense root/rotation coverage")

    seed_everything(SEED)
    pad_mask = length_to_mask(lengths)
    llm_dim = int(model.denoiser.llm_shape[-1])
    torch.cuda.synchronize()
    started = time.perf_counter()
    with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
        motion = model(
            [""],
            rotation.FRAMES,
            num_denoising_steps=DIFFUSION_STEPS,
            pad_mask=pad_mask,
            first_heading_angle=torch.zeros(1, device=device),
            motion_mask=motion_mask,
            observed_motion=observed,
            cfg_weight=(0.0, CONSTRAINT_WEIGHT),
            text_feat=torch.zeros(1, 1, llm_dim, device=device),
            text_pad_mask=torch.zeros(1, 1, dtype=torch.bool, device=device),
        )
        decoded = model.motion_rep.inverse(motion, is_normalized=True)
    torch.cuda.synchronize()
    generation_ms = (time.perf_counter() - started) * 1_000.0

    required_output = (
        "posed_joints",
        "global_rot_mats",
        "local_rot_mats",
        "root_positions",
        "foot_contacts",
        "global_root_heading",
    )
    arrays = {name: decoded[name][0].detach().cpu().numpy() for name in required_output}
    if not all(np.isfinite(value).all() for value in arrays.values()):
        raise SystemExit("one generated Strike contains non-finite output")

    from generate_pvp005_ardy_keypose_candidates import load_v4_sources
    from pvp005_ardy_v4_materializer import materialize

    spec_path, spec, spec_hash, w0, w0_hash = load_v4_sources(
        args.spec.resolve().relative_to(ROOT)
    )
    action = materialize(spec, w0, spec_sha256=spec_hash, w0_sha256=w0_hash)["actions"][
        "strike"
    ]
    solved = {
        "left_hand_targets": torch.as_tensor(archive["desired_left_hand"], dtype=torch.float64),
        "right_hand_targets": torch.as_tensor(archive["desired_right_hand"], dtype=torch.float64),
        "foot_targets": torch.as_tensor(archive["desired_foot_positions"], dtype=torch.float64),
    }
    nodes = rotation.parse_g1_hinges(ROOT / "src/g1_articulation.rs")
    measured = rotation.metrics(decoded, solved, action, nodes)
    failures = rotation.gate_failures(measured)

    output.mkdir(parents=True)
    candidate_path = output / "hero_strike_ardy_r6_00.npz"
    np.savez_compressed(candidate_path, **arrays)
    trajectory_rotation_error = np.max(
        np.arccos(
            np.clip(
                (
                    np.trace(
                        np.swapaxes(archive["global_rot_mats"], -1, -2)
                        @ arrays["global_rot_mats"],
                        axis1=-2,
                        axis2=-1,
                    )
                    - 1.0
                )
                * 0.5,
                -1.0,
                1.0,
            )
        )
    )
    trajectory_root_error = np.linalg.norm(
        archive["root_positions"] - arrays["root_positions"], axis=-1
    ).max()
    if trajectory_rotation_error > 1.0e-3:
        failures.append("conditioned_rotation_preservation")
    if trajectory_root_error > 1.0e-5:
        failures.append("conditioned_root_preservation")

    manifest = {
        "schema": "just-dodge-pvp005-r6-one-rotation-strike-generation-v1",
        "status": "pass" if not failures else "failed_stop_no_more_seeds",
        "authority": "offline_motion_proposal_only",
        "repository_revision": current_revision,
        "ardy_revision": proof["ardy_revision"],
        "model": rotation.G1_MODEL,
        "seed": SEED,
        "candidate_count": 1,
        "generation_ms": round(generation_ms, 3),
        "diffusion_steps": DIFFUSION_STEPS,
        "constraint_weight": CONSTRAINT_WEIGHT,
        "text_conditioning": False,
        "rotation_proof": {"path": str(proof_path), "sha256": rotation.sha256(proof_path)},
        "condition_trajectory": {
            "path": str(trajectory_path),
            "sha256": rotation.sha256(trajectory_path),
        },
        "candidate": {
            "path": candidate_path.name,
            "bytes": candidate_path.stat().st_size,
            "sha256": rotation.sha256(candidate_path),
        },
        "condition_preservation": {
            "maximum_global_rotation_error_rad": float(trajectory_rotation_error),
            "maximum_root_position_error_m": float(trajectory_root_error),
        },
        "metrics": measured,
        "failures": failures,
    }
    manifest_path = output / "generation_manifest.json"
    manifest_path.write_bytes(rotation.canonical_bytes(manifest))
    if failures:
        raise SystemExit(
            "PVP005_R6_ONE_STRIKE=FAIL_STOP_NO_MORE_SEEDS "
            + ",".join(failures)
            + f" candidate={candidate_path} manifest={manifest_path}"
        )
    print("PVP005_R6_ONE_STRIKE=PASS")
    print(f"PVP005_R6_ONE_STRIKE_CANDIDATE={candidate_path}")
    print(f"PVP005_R6_ONE_STRIKE_SHA256={rotation.sha256(candidate_path)}")
    print(f"PVP005_R6_ONE_STRIKE_MANIFEST_SHA256={rotation.sha256(manifest_path)}")
    print(json.dumps(measured, sort_keys=True))


if __name__ == "__main__":
    main()
