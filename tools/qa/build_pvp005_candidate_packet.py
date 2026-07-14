#!/usr/bin/env python3
"""Build the hash-bound, not-yet-admitted PVP-005 motion candidate packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SELECTED = {
    "strike": {
        "candidate": "strike_02",
        "seed": 2026071401,
        "prompt": (
            "Plant the feet in a fighting stance, raise both hands together above the right "
            "shoulder as if gripping one weapon, drive both hands forward and downward in one "
            "decisive overhead strike, then recover to guard."
        ),
        "weapon_in_reveal": True,
    },
    "block": {
        "candidate": "block_07",
        "seed": 2026071402,
        "prompt": (
            "Plant the feet in a fighting stance, lift both forearms and both hands together "
            "across the upper chest and face in a compact high defensive guard, brace against "
            "an incoming overhead strike, then recover."
        ),
        "weapon_in_reveal": True,
    },
    "grab": {
        "candidate": "grab_07",
        "seed": 2026071403,
        "prompt": (
            "From a low fighting stance, step forward toward an opponent, extend both open hands "
            "together at chest height, close the distance into a two-handed torso grab, pull "
            "backward, release, and recover."
        ),
        "weapon_in_reveal": False,
    },
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def receipt(path: Path) -> dict[str, object]:
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def copy_receipt(source: Path, destination: Path) -> dict[str, object]:
    if not source.is_file():
        raise SystemExit(f"missing packet input: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return receipt(destination)


def copy_normalized_text_receipt(source: Path, destination: Path) -> dict[str, object]:
    if not source.is_file():
        raise SystemExit(f"missing packet input: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = source.read_text(encoding="utf-8").splitlines()
    destination.write_text("\n".join(line.rstrip() for line in lines) + "\n", encoding="utf-8")
    return receipt(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=ROOT / "qa_runs/pvp005_motion_admission/candidates",
    )
    parser.add_argument(
        "--screen-root",
        type=Path,
        default=ROOT / "qa_runs/pvp005_motion_admission/screen",
    )
    parser.add_argument(
        "--reveal-root",
        type=Path,
        default=ROOT / "qa_runs/pvp005_motion_admission/c0_reveal",
    )
    parser.add_argument("--ardy-root", type=Path, required=True)
    parser.add_argument("--model-snapshot", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "assets/motion/pvp005_candidates",
    )
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite packet: {args.output}")

    screen_path = args.screen_root / "candidate_screen.json"
    screen = json.loads(screen_path.read_text())
    if screen.get("schema") != "just-dodge-pvp005-candidate-screen-v1":
        raise SystemExit("unsupported candidate screen schema")
    metrics_by_name = {
        metric["candidate"]: metric
        for values in screen["actions"].values()
        for metric in values
    }

    args.output.mkdir(parents=True)
    action_receipts = {}
    for action, selection in SELECTED.items():
        candidate = selection["candidate"]
        metric = metrics_by_name[candidate]
        if metric["action"] != action or not metric["structural_pass"]:
            raise SystemExit(f"selected candidate failed screen: {candidate}")
        source = args.candidate_root / action / f"{candidate}.npz"
        f413 = args.screen_root / "f413" / f"{candidate}.413.f32"
        if digest(source) != metric["source_sha256"]:
            raise SystemExit(f"source hash drift: {candidate}")
        if digest(f413) != metric["f413_sha256"]:
            raise SystemExit(f"F413 hash drift: {candidate}")
        action_dir = args.output / action
        source_receipt = copy_receipt(source, action_dir / f"{candidate}.ardy.npz")
        f413_receipt = copy_receipt(f413, action_dir / f"{candidate}.413.f32")
        reveal_receipts = {
            view: copy_receipt(
                args.reveal_root / f"{candidate}_{view}_reveal.png",
                action_dir / f"{candidate}_{view}_reveal.png",
            )
            for view in ("front", "side")
        }
        action_receipts[action] = {
            **selection,
            "frames": metric["frames"],
            "fps": metric["fps"],
            "event_frame": metric["event_frame"],
            "tell_frames": metric["tell_frames"],
            "structural_metrics": {
                key: value
                for key, value in metric.items()
                if key.startswith("max_") or key.startswith("root_height_")
            },
            "semantic_metrics": metric["semantic"],
            "source": source_receipt,
            "f413": f413_receipt,
            "c0_reveal": reveal_receipts,
        }

    third_party = args.output / "third_party"
    provenance = {
        "ardy_code": {
            "repository": "https://github.com/nv-tlabs/ardy",
            "commit": "693f74d13b3d04a0a22ce127ee79c929dd89756b",
            "license": copy_receipt(args.ardy_root / "LICENSE", third_party / "ARDY_CODE_LICENSE.txt"),
        },
        "ardy_model": {
            "repository": "nvidia/ARDY-G1-RP-25FPS-Horizon52",
            "snapshot": "059b8007df0ba194a006a877b59a563955ac7b70",
            "upstream_model_card_sha256": digest(args.model_snapshot / "README.md"),
            "normalized_model_card": copy_normalized_text_receipt(
                args.model_snapshot / "README.md", third_party / "ARDY_MODEL_CARD.md"
            ),
            "license": copy_receipt(
                args.model_snapshot / "LICENSE", third_party / "ARDY_MODEL_LICENSE.txt"
            ),
            "config_sha256": digest(args.model_snapshot / "config.yaml"),
            "denoiser_sha256": digest(args.model_snapshot / "denoiser.safetensors"),
            "tokenizer_sha256": digest(args.model_snapshot / "tokenizer.safetensors"),
        },
    }
    bound_files = {
        "carrier": receipt(
            ROOT
            / "assets/source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin"
        ),
        "retargeter": receipt(ROOT / "src/motion_retarget.rs"),
        "render_harness": receipt(ROOT / "src/bin/shot.rs"),
        "candidate_screen": copy_receipt(
            screen_path, args.output / "candidate_screen.json"
        ),
    }
    manifest = {
        "schema": "just-dodge-pvp005-motion-candidate-packet-v1",
        "status": "pending_blinded_human_trials",
        "runtime_promoted": False,
        "public_distribution_ready": False,
        "generation": {
            "model_alias": "Kimodo-G1-SEED-v1",
            "duration_seconds": 3.0,
            "diffusion_steps": 10,
            "samples_per_action": 8,
        },
        "thresholds": screen["thresholds"],
        "actions": action_receipts,
        "provenance": provenance,
        "bound_files": bound_files,
        "remaining_gates": [
            "at least 20 blinded human participants with >=80% accuracy for every action",
            "source-hash verifier wired into the repository release gate",
            "pose-derived weapon socket/contact proxy parity",
        ],
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"PVP005_CANDIDATE_PACKET={args.output}")
    print(f"PVP005_CANDIDATE_MANIFEST_SHA256={digest(manifest_path)}")


if __name__ == "__main__":
    main()
