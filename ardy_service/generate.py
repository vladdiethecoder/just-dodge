#!/usr/bin/env python3
"""Isolated ARDY-G1 post-Reveal feasibility service.

Protocol: one JSON request per stdin line, one JSON response per stdout line.
Model logs and progress bars are redirected to stderr so stdout remains parseable.
This service proposes quantization-ready movement only; it never emits outcomes.
"""

from __future__ import annotations

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

ARDY_ROOT = Path(os.environ.get("JUST_DODGE_ARDY_ROOT", "/run/media/vdubrov/NVMe-Storage1/ardy"))
MODEL_NAME = "ARDY-G1-RP-25FPS-Horizon52"
MODEL_REPO = f"nvidia/{MODEL_NAME}"
ALLOWED_PHASES = frozenset(("Reveal", "Resolve", "Consequence"))
MAX_ROOT_METERS = 3.0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest_sha256(snapshot: Path) -> str:
    digest = hashlib.sha256()
    suffixes = {".json", ".npy", ".safetensors", ".yaml", ".yml"}
    for path in sorted(path for path in snapshot.rglob("*") if path.is_file() and path.suffix in suffixes):
        digest.update(path.relative_to(snapshot).as_posix().encode("utf-8"))
        digest.update(bytes.fromhex(_sha256_file(path)))
    return digest.hexdigest()


def _source_commit() -> str:
    return subprocess.run(
        ["git", "-C", str(ARDY_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _canonical_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite_pair(value: Any, field: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{field} must be [x, z]")
    result = (float(value[0]), float(value[1]))
    if not all(math.isfinite(component) and abs(component) <= MAX_ROOT_METERS for component in result):
        raise ValueError(f"{field} components must be finite and within +/-{MAX_ROOT_METERS} m")
    return result


class ArdyG1Service:
    def __init__(self) -> None:
        if not (ARDY_ROOT / "ardy").is_dir():
            raise RuntimeError(f"official ARDY checkout missing at {ARDY_ROOT}")
        sys.path.insert(0, str(ARDY_ROOT))

        import torch
        from huggingface_hub import snapshot_download

        if not torch.cuda.is_available():
            raise RuntimeError("ARDY-G1 service requires CUDA for this feasibility unit")

        with contextlib.redirect_stdout(sys.stderr):
            snapshot = Path(snapshot_download(repo_id=MODEL_REPO, local_files_only=True))
            from ardy.model import load_model

            model = load_model(MODEL_NAME, device="cuda:0", text_encoder=False)

        self.torch = torch
        self.model = model
        self.snapshot = snapshot
        self.llm_dim = int(model.denoiser.llm_shape[-1])
        self.receipt = {
            "model_repo": MODEL_REPO,
            "model_revision": snapshot.name,
            "model_manifest_sha256": _manifest_sha256(snapshot),
            "license_file_sha256": _sha256_file(snapshot / "LICENSE"),
            "source_commit": _source_commit(),
            "skeleton": type(model.skeleton).__name__,
            "fps": int(model.motion_rep.fps),
            "horizon_frames": int(model.gen_horizon_len),
            "frames_per_token": int(model.num_frames_per_token),
            "denoising_steps": int(model.diffusion.num_base_steps),
            "text_encoder": "disabled-constraint-only",
        }

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": "ardy-g1-feasibility-v1",
            "model": self.receipt,
            "authority": "motion-proposal-only",
        }

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        from ardy.constraints import Root2DConstraintSet
        from ardy.motion_rep.tools import length_to_mask
        from ardy.tools import seed_everything

        phase = request.get("public_phase")
        if phase not in ALLOWED_PHASES:
            raise ValueError(f"public_phase must be one of {sorted(ALLOWED_PHASES)}")
        request_id = int(request["request_id"])
        if request_id <= 0:
            raise ValueError("request_id must be positive")
        seed = int(request.get("seed", 0))
        if not 0 <= seed <= 0xFFFF_FFFF:
            raise ValueError("seed must fit u32")
        start_xz = _finite_pair(request.get("start_root_xz_m", [0.0, 0.0]), "start_root_xz_m")
        target_xz = _finite_pair(request["target_root_xz_m"], "target_root_xz_m")
        constraint_weight = float(request.get("constraint_weight", 2.0))
        if not math.isfinite(constraint_weight) or not 0.0 <= constraint_weight <= 10.0:
            raise ValueError("constraint_weight must be finite and within 0..10")
        if request.get("text", "").strip():
            raise ValueError("text is disabled in the constraint-only feasibility service")

        torch = self.torch
        model = self.model
        frames = int(model.gen_horizon_len)
        device = "cuda:0"
        lengths = torch.tensor([frames], device=device)
        pad_mask = length_to_mask(lengths)
        root = torch.tensor([start_xz, target_xz], dtype=torch.float32, device=device)
        constraint = Root2DConstraintSet(
            model.skeleton,
            torch.tensor([0, frames - 1]),
            root,
        )
        observed, motion_mask = model.motion_rep.create_conditions_from_constraints_batched(
            [constraint],
            lengths,
            to_normalize=True,
            device=device,
        )

        seed_everything(seed)
        torch.cuda.synchronize()
        started = time.perf_counter()
        with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
            motion = model(
                [""],
                frames,
                num_denoising_steps=int(model.diffusion.num_base_steps),
                pad_mask=pad_mask,
                first_heading_angle=torch.zeros(1, device=device),
                motion_mask=motion_mask,
                observed_motion=observed,
                cfg_weight=(0.0, constraint_weight),
                text_feat=torch.zeros(1, 1, self.llm_dim, device=device),
                text_pad_mask=torch.zeros(1, 1, dtype=torch.bool, device=device),
            )
            output = model.motion_rep.inverse(motion, is_normalized=True)
        torch.cuda.synchronize()
        generation_ms = (time.perf_counter() - started) * 1000.0

        required = ("root_positions", "posed_joints", "local_rot_mats", "foot_contacts")
        missing = [key for key in required if key not in output]
        if missing:
            raise RuntimeError(f"ARDY output missing required fields: {missing}")
        if not all(torch.isfinite(output[key]).all().item() for key in required):
            raise RuntimeError("ARDY output contains non-finite values")

        root_positions = output["root_positions"][0]
        posed_joints = output["posed_joints"][0]
        local_rotations = output["local_rot_mats"][0]
        foot_contacts = output["foot_contacts"][0]
        rotation_6d = torch.cat((local_rotations[..., :, 0], local_rotations[..., :, 1]), dim=-1)

        quantized = {
            "root_positions_mm": torch.round(root_positions * 1000.0).to(torch.int32).cpu().tolist(),
            "posed_joints_mm": torch.round(posed_joints * 1000.0).to(torch.int32).cpu().tolist(),
            "joint_rotations_6d_q15": torch.round(rotation_6d.clamp(-1.0, 1.0) * 32767.0)
            .to(torch.int16)
            .cpu()
            .tolist(),
            "foot_contacts_q16": torch.round(foot_contacts.clamp(0.0, 1.0) * 65535.0)
            .to(torch.int32)
            .cpu()
            .tolist(),
        }
        response = {
            "ok": True,
            "service": "ardy-g1-feasibility-v1",
            "request_id": request_id,
            "public_phase": phase,
            "seed": seed,
            "constraint_weight": constraint_weight,
            "target_root_xz_mm": [round(target_xz[0] * 1000.0), round(target_xz[1] * 1000.0)],
            "generation_ms": round(generation_ms, 3),
            "model": self.receipt,
            "motion": quantized,
            "authority": "motion-proposal-only",
        }
        hash_payload = {key: value for key, value in response.items() if key != "generation_ms"}
        response["proposal_sha256"] = _canonical_sha256(hash_payload)
        return response

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        operation = request.get("op")
        if operation == "health":
            return self.health()
        if operation == "generate_root_plan":
            return self.generate(request)
        raise ValueError("op must be health or generate_root_plan")


def main() -> int:
    service = ArdyG1Service()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = service.handle(request)
        except Exception as error:
            response = {
                "ok": False,
                "error_type": type(error).__name__,
                "error": str(error),
            }
        print(json.dumps(response, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
