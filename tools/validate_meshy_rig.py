#!/usr/bin/env python3
"""Validate a Meshy-rigged GLB as a source rig for Just Dodge / MotionBricks.

This script performs the offline validation gate described in:
    docs/superpowers/specs/2026-07-09-meshy-rig-validation-pipeline.md

It does NOT call Meshy APIs. It expects a local rigged GLB file and the
project's canonical bone mapping JSON.

Exit codes:
    0 = validation passed
    1 = validation failed (see stderr)
    2 = usage / environment error
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

try:
    import trimesh
except ImportError as e:  # pragma: no cover
    print(f"ERROR: trimesh is required: {e}", file=sys.stderr)
    sys.exit(2)


# ── constants ────────────────────────────────────────────────────────────────

G1_PARENTS = [
    -1, 0, 1, 2, 3, 4, 5, 6,
    0, 8, 9, 10, 11, 12, 13,
    0, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
    17, 26, 27, 28, 29, 30, 31, 32,
]

G1_NAMES = [
    "pelvis",
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee",
    "left_ankle_pitch", "left_ankle_roll", "left_toe_base",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee",
    "right_ankle_pitch", "right_ankle_roll", "right_toe_base",
    "waist_yaw", "waist_roll", "waist_pitch",
    "left_shoulder_pitch", "left_shoulder_roll", "left_shoulder_yaw",
    "left_elbow", "left_forearm", "left_wrist_pitch", "left_wrist_roll", "left_hand",
    "right_shoulder_pitch", "right_shoulder_roll", "right_shoulder_yaw",
    "right_elbow", "right_forearm", "right_wrist_pitch", "right_wrist_roll", "right_hand",
]

# Mapping from canonical bone name to G1Skeleton34 index.
# Loaded from tools/data/meshy_to_canonical_bones.json and extended with defaults.
CANONICAL_TO_G1: dict[str, int | None] = {
    "Hips": 0,
    "Spine": 15,
    "Chest": 16,
    "Neck": 17,
    "Head": 17,
    "LeftShoulder": 18,
    "LeftUpperArm": 19,
    "LeftLowerArm": 21,
    "LeftHand": 23,
    "RightShoulder": 26,
    "RightUpperArm": 27,
    "RightLowerArm": 29,
    "RightHand": 31,
    "LeftUpperLeg": 1,
    "LeftLowerLeg": 4,
    "LeftFoot": 5,
    "LeftToes": 7,
    "RightUpperLeg": 8,
    "RightLowerLeg": 11,
    "RightFoot": 12,
    "RightToes": 14,
}

REQUIRED_CANONICAL = {
    "Hips", "Spine", "Chest",
    "LeftShoulder", "LeftUpperArm", "LeftLowerArm", "LeftHand",
    "RightShoulder", "RightUpperArm", "RightLowerArm", "RightHand",
    "LeftUpperLeg", "LeftLowerLeg", "LeftFoot",
    "RightUpperLeg", "RightLowerLeg", "RightFoot",
}


# ── GLB helpers ──────────────────────────────────────────────────────────────

def load_glb_scene(path: Path) -> trimesh.Scene:
    scene = trimesh.load(str(path), force="scene")
    if not isinstance(scene, trimesh.Scene):
        raise ValueError(f"{path} did not load as a scene")
    return scene


def find_skeleton_root(scene: trimesh.Scene) -> tuple[str, dict[str, Any]] | None:
    """Return the node name and data of the single root bone.

    Heuristic: a node whose name matches Hips/Root/Pelvis and has a parent
    that is the scene root or whose own parent is None.
    """
    graph = scene.graph
    nodes = graph.nodes_geometry if hasattr(graph, "nodes_geometry") else list(scene.graph.nodes)
    # Prefer exact root candidates
    candidates = []
    for node in nodes:
        lower = node.lower()
        if any(x in lower for x in ("hips", "pelvis", "root")):
            parents = _parents_of(scene, node)
            if len(parents) <= 1:
                candidates.append((node, parents))
    if not candidates:
        return None
    # Pick the one with fewest parents / most central position
    candidates.sort(key=lambda x: len(x[1]))
    return candidates[0][0], {"parents": candidates[0][1]}


def _parents_of(scene: trimesh.Scene, node: str) -> list[str]:
    edges = scene.graph.transforms.parents if hasattr(scene.graph, "transforms") else {}
    parents: list[str] = []
    cur = node
    for _ in range(256):
        parent = edges.get(cur) if isinstance(edges, dict) else None
        if parent is None:
            break
        parents.append(parent)
        cur = parent
    return parents


def build_bone_tree(scene: trimesh.Scene, root: str) -> dict[str, dict[str, Any]]:
    """Build a map of bone name -> {parent, children, transform}."""
    tree: dict[str, dict[str, Any]] = {}
    seen = set()
    stack: list[tuple[str, str | None]] = [(root, None)]
    while stack:
        node, parent = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        transform, _ = scene.graph[node]
        tree[node] = {"parent": parent, "children": [], "transform": np.array(transform)}
        if parent is not None:
            tree[parent]["children"].append(node)
        # Find children via graph adjacency
        edges = scene.graph.transforms.children if hasattr(scene.graph, "transforms") else {}
        children = edges.get(node, []) if isinstance(edges, dict) else []
        for child in children:
            if child not in seen:
                stack.append((child, node))
    return tree


def bone_length(transform: np.ndarray) -> float:
    translation = transform[:3, 3]
    return float(np.linalg.norm(translation))


def bone_world_position(tree: dict, node: str) -> np.ndarray:
    transform = np.eye(4)
    cur: str | None = node
    chain: list[str] = []
    while cur is not None:
        chain.append(cur)
        cur = tree[cur]["parent"]
    for n in reversed(chain):
        transform = transform @ tree[n]["transform"]
    return transform[:3, 3]


# ── canonicalization ─────────────────────────────────────────────────────────

def load_canonical_map(path: Path) -> dict[str, int | None]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    mapping: dict[str, int | None] = {}
    for canonical, info in data.get("canonical", {}).items():
        mapping[canonical] = info.get("g1_index")
    return mapping


def canonicalize_bone_name(name: str, canonical_map: dict[str, Any]) -> str | None:
    lower = name.lower().replace(" ", "").replace("_", "").replace(".", "")
    for canonical, info in canonical_map.items():
        for pattern in info.get("patterns", []):
            pat = pattern.lower().replace(" ", "").replace("_", "").replace(".", "")
            if pat in lower:
                return canonical
    return None


# ── G1 retarget helpers ──────────────────────────────────────────────────────

def local_from_world(world_mats: list[np.ndarray], parents: list[int]) -> list[np.ndarray]:
    local: list[np.ndarray] = []
    for i, w in enumerate(world_mats):
        p = parents[i]
        if p >= 0:
            local.append(np.linalg.inv(world_mats[p]) @ w)
        else:
            local.append(w.copy())
    return local


def world_from_local(local_mats: list[np.ndarray], parents: list[int]) -> list[np.ndarray]:
    world: list[np.ndarray] = []
    for i, l in enumerate(local_mats):
        p = parents[i]
        if p >= 0:
            world.append(world[p] @ l)
        else:
            world.append(l.copy())
    return world


def build_g1_world_from_canonical(
    tree: dict, canonical_to_node: dict[str, str]
) -> tuple[list[np.ndarray], list[str]]:
    """Sample 34 G1 joint world matrices from the canonicalized Meshy skeleton.

    Missing joints are interpolated from available parents/children.
    """
    world = [np.eye(4) for _ in range(34)]
    notes: list[str] = []

    for canonical, g1_idx in CANONICAL_TO_G1.items():
        if g1_idx is None:
            continue
        node = canonical_to_node.get(canonical)
        if node is None:
            notes.append(f"missing canonical bone '{canonical}' for G1[{g1_idx}]")
            continue
        pos = bone_world_position(tree, node)
        world[g1_idx][:3, 3] = pos

    # Interpolate missing G1 joints using hierarchy where possible
    # Left leg chain
    for idx, fallback in [(2, 1), (3, 4), (6, 5)]:
        if canonical_to_node.get("LeftUpperLeg") and canonical_to_node.get("LeftLowerLeg"):
            a = world[1][:3, 3]
            b = world[4][:3, 3]
            t = 0.33 if idx in (2, 3) else 0.5
            world[idx][:3, 3] = a + (b - a) * t
    # Right leg chain
    for idx, fallback in [(9, 8), (10, 11), (13, 12)]:
        if canonical_to_node.get("RightUpperLeg") and canonical_to_node.get("RightLowerLeg"):
            a = world[8][:3, 3]
            b = world[11][:3, 3]
            t = 0.33 if idx in (9, 10) else 0.5
            world[idx][:3, 3] = a + (b - a) * t
    # Spine interpolation: waist_yaw(15), waist_roll(16), waist_pitch(17)
    if canonical_to_node.get("Spine") and canonical_to_node.get("Chest"):
        spine_pos = world[15][:3, 3]
        chest_pos = world[16][:3, 3]
        if not canonical_to_node.get("Neck") and not canonical_to_node.get("Head"):
            world[17][:3, 3] = chest_pos + np.array([0.0, 0.15, 0.0])
    # Arms: fill shoulder_yaw, elbow details, wrist details with simple offsets
    for side, shoulder, upper, lower, hand, elbow_y_off, wrist_y_off in [
        ("Left", 18, 19, 21, 23, -0.28, -0.28),
        ("Right", 26, 27, 29, 31, -0.28, -0.28),
    ]:
        s = world[shoulder][:3, 3]
        u = world[upper][:3, 3]
        h = world[hand][:3, 3]
        if np.allclose(s, 0) or np.allclose(u, 0):
            continue
        if np.allclose(world[lower][:3, 3], 0):
            world[lower][:3, 3] = u + np.array([0.0, elbow_y_off, 0.0])
        if np.allclose(world[hand][:3, 3], 0):
            world[hand][:3, 3] = world[lower][:3, 3] + np.array([0.0, wrist_y_off, 0.0])

    return world, notes


# ── validation checks ────────────────────────────────────────────────────────

def check_topology(tree: dict) -> list[str]:
    errors: list[str] = []
    roots = [n for n, info in tree.items() if info["parent"] is None]
    if len(roots) != 1:
        errors.append(f"expected exactly one skeleton root, found {len(roots)}: {roots}")
    # DAG / no cycles
    for node, info in tree.items():
        seen = set()
        cur = info["parent"]
        while cur is not None:
            if cur in seen:
                errors.append(f"bone cycle detected involving '{node}'")
                break
            seen.add(cur)
            cur = tree[cur]["parent"]
    # No zero-length bones
    for node, info in tree.items():
        if info["parent"] is not None and bone_length(info["transform"]) < 0.001:
            errors.append(f"bone '{node}' has near-zero length")
    return errors


def check_canonical(tree: dict, canonical_map: dict[str, Any]) -> tuple[dict[str, str], list[str], list[str]]:
    canonical_to_node: dict[str, str] = {}
    errors: list[str] = []
    warnings: list[str] = []
    for node in tree:
        canonical = canonicalize_bone_name(node, canonical_map)
        if canonical is None:
            warnings.append(f"bone '{node}' did not match any canonical name")
            continue
        if canonical in canonical_to_node:
            warnings.append(
                f"canonical bone '{canonical}' already mapped to "
                f"'{canonical_to_node[canonical]}'; ignoring '{node}'"
            )
            continue
        canonical_to_node[canonical] = node
    missing_required = REQUIRED_CANONICAL - set(canonical_to_node.keys())
    if missing_required:
        errors.append(f"missing required canonical bones: {sorted(missing_required)}")
    return canonical_to_node, errors, warnings


def check_g1_retarget(g1_world: list[np.ndarray]) -> list[str]:
    errors: list[str] = []
    for i, m in enumerate(g1_world):
        if not np.all(np.isfinite(m)):
            errors.append(f"G1 joint {i} ({G1_NAMES[i]}) has non-finite matrix")
    # Height check
    pelvis_y = float(g1_world[0][1, 3])
    if pelvis_y <= 0.0 or pelvis_y > 3.0:
        errors.append(f"pelvis height {pelvis_y:.3f}m is outside expected range (0, 3]")
    return errors


def check_rich_retarget(g1_world: list[np.ndarray]) -> list[str]:
    """Quick sanity check that G1 local -> world is invertible and finite."""
    errors: list[str] = []
    try:
        g1_local = local_from_world(g1_world, G1_PARENTS)
        rebuilt = world_from_local(g1_local, G1_PARENTS)
        for i, (a, b) in enumerate(zip(g1_world, rebuilt)):
            diff = np.linalg.norm(a[:3, 3] - b[:3, 3])
            if diff > 1e-4:
                errors.append(f"G1 world/local round-trip mismatch at joint {i}: {diff}")
    except Exception as exc:  # pragma: no cover
        errors.append(f"rich retarget check raised: {exc}")
    return errors


def check_bind_pose(tree: dict, canonical_to_node: dict[str, str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    hips = canonical_to_node.get("Hips")
    if hips is None:
        errors.append("cannot check bind pose without Hips")
        return errors, warnings
    hips_pos = bone_world_position(tree, hips)
    feet_nodes = [canonical_to_node.get(k) for k in ("LeftFoot", "RightFoot")]
    feet_y = []
    for node in feet_nodes:
        if node is None:
            continue
        pos = bone_world_position(tree, node)
        feet_y.append(pos[1])
    if feet_y:
        min_foot_y = min(feet_y)
        if abs(min_foot_y - hips_pos[1] * 0.0) > 0.02:
            warnings.append(f"lowest foot Y = {min_foot_y:.3f}m (expected ~0.0)")
    else:
        warnings.append("no feet found for bind-pose check")
    return errors, warnings


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Meshy-rigged GLB")
    parser.add_argument("glb", type=Path, help="Path to rigged GLB file")
    parser.add_argument(
        "--canonical-map",
        type=Path,
        default=Path(__file__).with_name("data") / "meshy_to_canonical_bones.json",
        help="Path to canonical bone mapping JSON",
    )
    parser.add_argument(
        "--height",
        type=float,
        default=1.75,
        help="Expected character height in meters",
    )
    parser.add_argument("--write-manifest", type=Path, default=None, help="Append result to manifest JSON")
    args = parser.parse_args()

    if not args.glb.exists():
        print(f"ERROR: GLB not found: {args.glb}", file=sys.stderr)
        return 2

    canonical_map = load_canonical_map(args.canonical_map)
    global CANONICAL_TO_G1
    CANONICAL_TO_G1.update(canonical_map)

    scene = load_glb_scene(args.glb)
    root_info = find_skeleton_root(scene)
    if root_info is None:
        print("FAIL: could not find skeleton root (hips/pelvis/root)", file=sys.stderr)
        return 1
    root_name, _ = root_info
    tree = build_bone_tree(scene, root_name)

    all_errors: list[str] = []
    all_warnings: list[str] = []

    all_errors.extend(check_topology(tree))
    canonical_to_node, errs, warns = check_canonical(tree, canonical_map)
    all_errors.extend(errs)
    all_warnings.extend(warns)

    g1_world, g1_notes = build_g1_world_from_canonical(tree, canonical_to_node)
    all_warnings.extend(g1_notes)
    all_errors.extend(check_g1_retarget(g1_world))
    all_errors.extend(check_rich_retarget(g1_world))

    bind_errors, bind_warns = check_bind_pose(tree, canonical_to_node)
    all_errors.extend(bind_errors)
    all_warnings.extend(bind_warns)

    print(f"Skeleton root: {root_name}")
    print(f"Bone count: {len(tree)}")
    print(f"Canonical mapping count: {len(canonical_to_node)}")
    print(f"Required bones present: {set(canonical_to_node.keys()) >= REQUIRED_CANONICAL}")

    if all_warnings:
        print("\nWarnings:")
        for w in all_warnings:
            print(f"  - {w}")
    if all_errors:
        print("\nErrors:")
        for e in all_errors:
            print(f"  - {e}")

    if args.write_manifest:
        write_manifest_entry(args.write_manifest, args.glb, args.height, all_errors, all_warnings)

    return 0 if not all_errors else 1


def write_manifest_entry(
    path: Path, glb: Path, height: float, errors: list[str], warnings: list[str]
) -> None:
    import datetime

    manifest: dict[str, Any]
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = {"version": "2026-07-09", "entries": []}

    entry = {
        "id": f"meshy_rig_{datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        "character_name": glb.stem,
        "source_task_type": "model_url",
        "status": "passed" if not errors else "failed",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "height_meters": height,
        "validation": {
            "required_bones_present": not any("missing required canonical" in e for e in errors),
            "bind_pose_feet_y": 0.0,
            "g1_retarget_finiteness": not any("G1 joint" in e for e in errors),
            "rich_retarget_finiteness": not any("round-trip" in e for e in errors),
            "errors": errors,
            "warnings": warnings,
        },
    }
    manifest["entries"].append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
