#!/usr/bin/env python3
"""Hard-infill the one PVP005-R6 seed result without another diffusion run.

ARDY's released concat mask is a soft denoiser condition: the hybrid decoder's
``motion_mask`` argument is unused and generated frames are not overwritten by
observed values. This deterministic stage applies the documented mask
semantics in explicit feature space, then recomputes coherent FK, velocities,
and contacts from the repaired rotations/root. It consumes the already-run
candidate and never samples noise or calls the denoiser.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARDY = Path("/run/media/vdubrov/NVMe-Storage1/ardy")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_pvp005_r6_rotation_strike as rotation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ardy-root", type=Path, default=DEFAULT_ARDY)
    parser.add_argument("--failed-manifest", type=Path, required=True)
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--proof", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite hard-infill output: {output}")
    failed_manifest_path = args.failed_manifest.resolve()
    failed = json.loads(failed_manifest_path.read_text(encoding="utf-8"))
    if failed.get("schema") != "just-dodge-pvp005-r6-one-rotation-strike-generation-v1":
        raise SystemExit("unsupported failed-candidate manifest")
    if failed.get("status") != "failed_stop_no_more_seeds" or failed.get("candidate_count") != 1:
        raise SystemExit("hard infill requires exactly the preserved failed one-seed result")
    candidate_path = failed_manifest_path.parent / failed["candidate"]["path"]
    if rotation.sha256(candidate_path) != failed["candidate"]["sha256"]:
        raise SystemExit("failed one-seed candidate hash drift")
    if (args.trajectory is None) != (args.proof is None):
        raise SystemExit("--trajectory and --proof must be supplied together")
    if args.trajectory is None:
        trajectory_path = Path(failed["condition_trajectory"]["path"])
        proof_path = Path(failed["rotation_proof"]["path"])
        if rotation.sha256(trajectory_path) != failed["condition_trajectory"]["sha256"]:
            raise SystemExit("condition trajectory hash drift")
        if rotation.sha256(proof_path) != failed["rotation_proof"]["sha256"]:
            raise SystemExit("rotation proof hash drift")
    else:
        trajectory_path = args.trajectory.resolve()
        proof_path = args.proof.resolve()
        replacement_proof = json.loads(proof_path.read_text(encoding="utf-8"))
        if (
            replacement_proof.get("status") != "pass_representation_proof_no_diffusion_run"
            or rotation.gate_failures(replacement_proof.get("metrics", {}))
        ):
            raise SystemExit("replacement trajectory did not pass rotation proof")

    candidate = np.load(candidate_path)
    trajectory = np.load(trajectory_path)
    sys.path.insert(0, str(args.ardy_root.resolve()))
    import torch

    device = "cuda:0"
    model = rotation.load_pinned_model(args.ardy_root.resolve(), device)
    local = torch.as_tensor(candidate["local_rot_mats"], device=device, dtype=torch.float32)
    root = torch.as_tensor(candidate["root_positions"], device=device, dtype=torch.float32)
    candidate_features = model.motion_rep(
        local[None],
        root[None],
        to_normalize=True,
        lengths=torch.tensor([rotation.FRAMES], device=device),
    )
    target_root = torch.as_tensor(
        trajectory["root_positions"], device=device, dtype=torch.float32
    )
    target_global = torch.as_tensor(
        trajectory["global_rot_mats"], device=device, dtype=torch.float32
    )
    constraint = rotation.DenseRotationConstraint(target_root, target_global)
    lengths = torch.tensor([rotation.FRAMES], device=device)
    observed, mask = model.motion_rep.create_conditions_from_constraints_batched(
        [constraint], lengths, to_normalize=True, device=device
    )
    hard_infilled = candidate_features * (1.0 - mask) + observed * mask
    repaired = model.motion_rep.inverse(hard_infilled, is_normalized=True)
    coherent_features = model.motion_rep(
        repaired["local_rot_mats"], repaired["root_positions"], to_normalize=False, lengths=lengths
    )
    coherent = model.motion_rep.inverse(coherent_features, is_normalized=False)

    from generate_pvp005_ardy_keypose_candidates import load_v4_sources
    from pvp005_ardy_v4_materializer import materialize

    spec_path, spec, spec_hash, w0, w0_hash = load_v4_sources(
        (ROOT / "assets/qa/pvp005_ardy_action_endpoints_v4.json").relative_to(ROOT)
    )
    action = materialize(spec, w0, spec_sha256=spec_hash, w0_sha256=w0_hash)["actions"][
        "strike"
    ]
    solved = {
        "left_hand_targets": torch.as_tensor(trajectory["desired_left_hand"], dtype=torch.float64),
        "right_hand_targets": torch.as_tensor(trajectory["desired_right_hand"], dtype=torch.float64),
        "foot_targets": torch.as_tensor(
            trajectory["desired_foot_positions"], dtype=torch.float64
        ),
    }
    nodes = rotation.parse_g1_hinges(ROOT / "src/g1_articulation.rs")
    measured = rotation.metrics(coherent, solved, action, nodes)
    failures = rotation.gate_failures(measured)

    output.mkdir(parents=True)
    required = (
        "posed_joints",
        "global_rot_mats",
        "local_rot_mats",
        "root_positions",
        "foot_contacts",
        "global_root_heading",
    )
    arrays = {name: coherent[name][0].detach().cpu().numpy() for name in required}
    candidate_output = output / "hero_strike_ardy_r6_hard_infill.npz"
    np.savez_compressed(candidate_output, **arrays)
    rotation_error = np.max(
        np.arccos(
            np.clip(
                (
                    np.trace(
                        np.swapaxes(trajectory["global_rot_mats"], -1, -2)
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
    root_error = np.linalg.norm(
        trajectory["root_positions"] - arrays["root_positions"], axis=-1
    ).max()
    if rotation_error > 1.0e-3:
        failures.append("hard_infill_rotation_preservation")
    if root_error > 1.0e-5:
        failures.append("hard_infill_root_preservation")

    desired_contacts = np.asarray(
        [action["foot_contact_targets"]["left"], action["foot_contact_targets"]["right"]],
        dtype=bool,
    ).T
    observed_contacts = arrays["foot_contacts"][:, [0, 2]]
    contact_match_fraction = float(np.equal(desired_contacts, observed_contacts).mean())
    receipt = {
        "schema": "just-dodge-pvp005-r6-one-seed-hard-infill-v1",
        "status": "pass" if not failures else "fail",
        "authority": "offline_rotation_conditioned_motion_proposal_only",
        "diffusion_candidates_generated": 1,
        "additional_diffusion_runs": 0,
        "seed": failed["seed"],
        "soft_conditioning_failure": {
            "manifest": str(failed_manifest_path),
            "sha256": rotation.sha256(failed_manifest_path),
            "maximum_global_rotation_error_rad": failed["condition_preservation"][
                "maximum_global_rotation_error_rad"
            ],
            "maximum_root_position_error_m": failed["condition_preservation"][
                "maximum_root_position_error_m"
            ],
            "mechanism": "released ARDY concat mask conditions the denoiser but HybridMotionConverter.get_explicit_motion_from_hybrid does not consume motion_mask",
        },
        "hard_infill": {
            "formula": "candidate_features*(1-motion_mask)+observed_motion*motion_mask",
            "maximum_global_rotation_error_rad": float(rotation_error),
            "maximum_root_position_error_m": float(root_error),
            "contact_schedule_match_fraction": contact_match_fraction,
        },
        "candidate": {
            "path": candidate_output.name,
            "bytes": candidate_output.stat().st_size,
            "sha256": rotation.sha256(candidate_output),
        },
        "metrics": measured,
        "failures": failures,
    }
    receipt_path = output / "hard_infill_manifest.json"
    receipt_path.write_bytes(rotation.canonical_bytes(receipt))
    if failures:
        raise SystemExit(
            "PVP005_R6_HARD_INFILL=FAIL "
            + ",".join(failures)
            + f" manifest={receipt_path}"
        )
    print("PVP005_R6_HARD_INFILL=PASS")
    print(f"PVP005_R6_HARD_INFILL_CANDIDATE={candidate_output}")
    print(f"PVP005_R6_HARD_INFILL_SHA256={rotation.sha256(candidate_output)}")
    print(f"PVP005_R6_HARD_INFILL_MANIFEST_SHA256={rotation.sha256(receipt_path)}")
    print(json.dumps(measured, sort_keys=True))


if __name__ == "__main__":
    main()
