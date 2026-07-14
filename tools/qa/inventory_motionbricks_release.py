#!/usr/bin/env python3
"""Inventory the exact released MotionBricks source and full checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME = Path("/run/media/vdubrov/NVMe-Storage1/gr00t/motionbricks")
DEFAULT_SOURCE = ROOT / "GR00T-WholeBodyControl"
DEFAULT_PROBE = ROOT / "qa_runs/m3_contact_truth_001/b14w_online_solver_contract/metrics.json"


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def git(source: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-C", str(source), *args],
        input=input_bytes,
        check=True,
        capture_output=True,
    ).stdout


def git_blob(source: Path, revision: str, path: str) -> dict[str, object]:
    content = git(source, "show", f"{revision}:{path}")
    return {
        "git_path": path,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--probe", type=Path, default=DEFAULT_PROBE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime_root.resolve()
    source = args.source_root.resolve()
    probe = args.probe.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite MotionBricks inventory: {output}")
    if not runtime.is_dir() or not source.is_dir() or not probe.is_file():
        raise SystemExit("MotionBricks runtime, source object database, or probe receipt is unavailable")

    revision = git(source, "rev-parse", "HEAD").decode().strip()
    remote = git(source, "remote", "get-url", "origin").decode().strip()
    status_lines = git(source, "status", "--short").decode(errors="replace").splitlines()
    staged_deleted = sum(line.startswith("D ") for line in status_lines)
    untracked = sum(line.startswith("??") for line in status_lines)
    if staged_deleted == 0 or untracked == 0:
        raise SystemExit("expected dirty/deleted-index source worktree condition was not reproduced")

    required_blobs = (
        "LICENSE",
        "motionbricks/README.md",
        "motionbricks/motionbricks/motion_backbone/inference/motion_inference.py",
        "motionbricks/motionbricks/motion_backbone/neural_modules/pose_backbone.py",
        "motionbricks/motionbricks/motion_backbone/neural_modules/root_backbone.py",
        "motionbricks/motionbricks/motionlib/core/skeletons/g1.py",
    )
    source_blobs = [git_blob(source, revision, path) for path in required_blobs]

    files = []
    for path in sorted((runtime / "out").rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": str(path.relative_to(runtime)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    checkpoint_paths = [item for item in files if "/checkpoints/" in item["path"]]
    if len(checkpoint_paths) != 3 or any(item["bytes"] < 100_000_000 for item in checkpoint_paths):
        raise SystemExit("full pose/root/VQ-VAE checkpoint set is incomplete")

    runtime_readme = runtime / "README.md"
    readme_blob = next(item for item in source_blobs if item["git_path"] == "motionbricks/README.md")
    if sha256(runtime_readme) != readme_blob["sha256"]:
        raise SystemExit("installed MotionBricks README drifts from the source Git object")
    probe_data = json.loads(probe.read_text())
    expected_verdict = "released_checkpoint_requires_interaction_conditioning_extension"
    if probe_data.get("verdict") != expected_verdict:
        raise SystemExit("online-conditioning probe verdict drift")

    manifest = {
        "schema": "just-dodge-motionbricks-release-inventory-v1",
        "verdict": expected_verdict,
        "runtime_authority": "full_external_checkpoint_tree_not_repo_local_lfs_pointers",
        "source": {
            "repository": remote,
            "commit": revision,
            "git_object_blobs": source_blobs,
            "worktree_admitted": False,
            "worktree_reason": "dirty_deleted_index_with_untracked_repopulation",
            "worktree_status_counts": {
                "total": len(status_lines),
                "staged_deleted": staged_deleted,
                "untracked": untracked,
            },
        },
        "runtime_root": str(runtime),
        "runtime_files": files,
        "probe": {"path": str(probe), "sha256": sha256(probe), "facts": probe_data["facts"]},
        "architecture_decision": {
            "released_checkpoint_native_physics_feedback": False,
            "released_checkpoint_boundary_transition_candidate": True,
            "compatible_trained_interaction_extension_required": True,
            "safe_next_atomic_unit": "define_and_test_canonical_neural_plan_packet_and_async_fail_closed_buffer_without_relabelling_or_invoking_the_released_checkpoint_as_feedback_authority",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"MOTIONBRICKS_RELEASE_INVENTORY_SHA256={sha256(output)}")
    print(f"MOTIONBRICKS_RELEASE_CHECKPOINTS={len(checkpoint_paths)}")
    print(f"MOTIONBRICKS_RELEASE_VERDICT={expected_verdict}")


if __name__ == "__main__":
    main()
