#!/usr/bin/env python3
"""Retarget a source FBX/BVH clip to G1Skeleton34 and export numpy features."""
import argparse
import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation


@dataclass
class Joint:
    name: str
    parent: Optional["Joint"]
    offset: np.ndarray
    channels: List[str] = field(default_factory=list)
    children: List["Joint"] = field(default_factory=list)
    # Index of this joint's first channel in the flat motion array (root has 6, others 3)
    channel_start: int = 0


def _parse_bvh(text: str) -> Tuple[Joint, np.ndarray, float]:
    """Parse a BVH file into a root joint, motion array, and frame time."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    hierarchy_match = re.search(r"HIERARCHY(.*?)MOTION", text, re.DOTALL | re.IGNORECASE)
    if not hierarchy_match:
        raise ValueError("Could not find HIERARCHY section")
    motion_match = re.search(r"MOTION\s*Frames:\s*(\d+)\s*Frame Time:\s*([0-9.eE+\-.]+)\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    if not motion_match:
        raise ValueError("Could not find MOTION section")

    hierarchy_text = hierarchy_match.group(1)
    num_frames = int(motion_match.group(1))
    frame_time = float(motion_match.group(2))
    motion_body = motion_match.group(3).strip()

    # Tokenize hierarchy
    tokens = re.findall(r"\{|\}|[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|[A-Za-z_][A-Za-z0-9_]*", hierarchy_text)
    idx = 0

    def parse_joint(expected_root: bool = False) -> Joint:
        nonlocal idx
        if expected_root:
            if tokens[idx].upper() != "ROOT":
                raise ValueError(f"Expected ROOT, got {tokens[idx]}")
            idx += 1
        else:
            if tokens[idx].upper() != "JOINT":
                raise ValueError(f"Expected JOINT, got {tokens[idx]}")
            idx += 1
        name = tokens[idx]
        idx += 1
        if tokens[idx] != "{":
            raise ValueError(f"Expected {{, got {tokens[idx]}")
        idx += 1
        if tokens[idx].upper() != "OFFSET":
            raise ValueError(f"Expected OFFSET, got {tokens[idx]}")
        idx += 1
        offset = np.array([float(tokens[idx]), float(tokens[idx + 1]), float(tokens[idx + 2])], dtype=np.float32)
        idx += 3
        channels: List[str] = []
        if tokens[idx].upper() == "CHANNELS":
            idx += 1
            num_channels = int(tokens[idx])
            idx += 1
            channels = [tokens[idx + i] for i in range(num_channels)]
            idx += num_channels
        joint = Joint(name=name, parent=None, offset=offset, channels=channels)
        while idx < len(tokens) and tokens[idx] != "}":
            upper = tokens[idx].upper()
            if upper == "JOINT":
                child = parse_joint(expected_root=False)
                child.parent = joint
                joint.children.append(child)
            elif upper == "END":
                # End Site - skip
                idx += 1
                if tokens[idx].upper() != "SITE":
                    raise ValueError(f"Expected SITE, got {tokens[idx]}")
                idx += 1
                if tokens[idx] != "{":
                    raise ValueError(f"Expected {{, got {tokens[idx]}")
                idx += 1
                if tokens[idx].upper() != "OFFSET":
                    raise ValueError(f"Expected OFFSET, got {tokens[idx]}")
                idx += 1
                idx += 3  # skip offset values
                if tokens[idx] != "}":
                    raise ValueError(f"Expected }}, got {tokens[idx]}")
                idx += 1
            else:
                raise ValueError(f"Unexpected token in joint {name}: {tokens[idx]}")
        if tokens[idx] != "}":
            raise ValueError(f"Expected }}, got {tokens[idx]}")
        idx += 1
        return joint

    root = parse_joint(expected_root=True)

    # Flatten joints and assign channel indices
    joints: List[Joint] = []

    def visit(j: Joint):
        j.channel_start = sum(len(j2.channels) for j2 in joints)
        joints.append(j)
        for c in j.children:
            visit(c)

    visit(root)

    values = [float(v) for v in motion_body.split()]
    expected = num_frames * sum(len(j.channels) for j in joints)
    if len(values) != expected:
        raise ValueError(f"Motion data length mismatch: expected {expected}, got {len(values)}")
    motion = np.array(values, dtype=np.float32).reshape(num_frames, -1)
    return root, motion, frame_time


def _euler_to_matrix(order: List[str], angles: np.ndarray) -> np.ndarray:
    """Convert BVH Euler angles to a rotation matrix.

    BVH channels are applied in order to the local joint frame (intrinsic).
    CMU uses Zrotation Yrotation Xrotation -> scipy 'zyx' intrinsic.
    """
    if len(order) == 3 and all("rotation" in c.lower() for c in order):
        # 3-channel joint: Zrotation Yrotation Xrotation
        z = angles[0] if "Z" in order[0] else 0.0
        y = angles[1] if "Y" in order[1] else 0.0
        x = angles[2] if "X" in order[2] else 0.0
        return Rotation.from_euler("zyx", [z, y, x], degrees=True).as_matrix().astype(np.float32)
    elif len(order) == 6:
        # root: Xposition Yposition Zposition Zrotation Yrotation Xrotation
        z = angles[3] if len(angles) > 3 else 0.0
        y = angles[4] if len(angles) > 4 else 0.0
        x = angles[5] if len(angles) > 5 else 0.0
        return Rotation.from_euler("zyx", [z, y, x], degrees=True).as_matrix().astype(np.float32)
    else:
        raise ValueError(f"Unsupported channel order: {order}")


def _forward_kinematics(root: Joint, motion: np.ndarray) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    """Compute world positions and rotations for all joints."""
    T = motion.shape[0]
    positions: Dict[str, np.ndarray] = {}
    rotations: Dict[str, np.ndarray] = {}

    def compute(j: Joint, parent_pos: Optional[np.ndarray], parent_rot: Optional[np.ndarray]):
        channels = j.channels
        if j.parent is None:
            # Root joint
            pos = np.array([motion[:, 0], motion[:, 1], motion[:, 2]], dtype=np.float32).T
            rot = np.array([_euler_to_matrix(channels, motion[t, :6]) for t in range(T)])
        else:
            local_rot = np.array([_euler_to_matrix(channels, motion[t, j.channel_start:j.channel_start + 3]) for t in range(T)])
            rot = parent_rot @ local_rot
            pos = parent_pos + (parent_rot @ j.offset[None, :, None]).squeeze(-1)

        positions[j.name] = pos
        rotations[j.name] = rot
        for c in j.children:
            compute(c, pos, rot)

    compute(root, None, None)
    return positions, rotations


def load_retarget_map():
    with open("tools/data/g1_retarget_map.json") as f:
        return json.load(f)


def _g1_fk(local_rots: np.ndarray, root_pos: np.ndarray, parents: List[int], offsets: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Run forward kinematics on the G1 skeleton.

    local_rots: [T, 34, 3, 3]
    root_pos: [T, 3]
    Returns world_pos [T, 34, 3], world_rot [T, 34, 3, 3].
    """
    T = local_rots.shape[0]
    world_pos = np.zeros((T, 34, 3), dtype=np.float32)
    world_rot = np.zeros((T, 34, 3, 3), dtype=np.float32)
    world_pos[:, 0] = root_pos
    world_rot[:, 0] = local_rots[:, 0]
    for j in range(1, 34):
        p = parents[j]
        world_rot[:, j] = world_rot[:, p] @ local_rots[:, j]
        world_pos[:, j] = world_pos[:, p] + (world_rot[:, p] @ offsets[j][None, :, None]).squeeze(-1)
    return world_pos, world_rot


def _resample(data: np.ndarray, source_fps: float, target_fps: float) -> np.ndarray:
    """Resample motion data along the time axis using linear interpolation."""
    if source_fps == target_fps:
        return data
    T = data.shape[0]
    old_times = np.arange(T) / source_fps
    new_times = np.arange(0, T / source_fps, 1.0 / target_fps)
    # Avoid extrapolating past the last frame.
    new_times = new_times[new_times <= old_times[-1]]
    # For rotation matrices, linear interpolation is approximate but acceptable for retargeting.
    # Interpolate flattened dimensions independently.
    flat = data.reshape(T, -1)
    new_flat = np.zeros((len(new_times), flat.shape[1]), dtype=data.dtype)
    for d in range(flat.shape[1]):
        new_flat[:, d] = np.interp(new_times, old_times, flat[:, d])
    return new_flat.reshape(len(new_times), *data.shape[1:])


def _orthonormalize_rotations(rots: np.ndarray) -> np.ndarray:
    """Gram-Schmidt orthonormalize rotation matrices [T, J, 3, 3]."""
    T, J = rots.shape[:2]
    out = np.zeros_like(rots)
    for t in range(T):
        for j in range(J):
            R = rots[t, j]
            x = R[:, 0]
            y = R[:, 1]
            xn = x / (np.linalg.norm(x) + 1e-8)
            yn = y - xn * np.dot(xn, y)
            yn = yn / (np.linalg.norm(yn) + 1e-8)
            zn = np.cross(xn, yn)
            out[t, j] = np.stack([xn, yn, zn], axis=1)
    return out


def _minimal_rotation(from_dir: np.ndarray, to_dir: np.ndarray) -> np.ndarray:
    """Return the minimal rotation matrix that maps unit vector from_dir to to_dir."""
    dot = float(np.dot(from_dir, to_dir))
    if dot > 0.999999:
        return np.eye(3, dtype=np.float32)
    if dot < -0.999999:
        # 180 degree rotation: pick any perpendicular axis.
        axis = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        if abs(from_dir[0]) > 0.9:
            axis = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        axis = np.cross(from_dir, axis)
        axis /= np.linalg.norm(axis) + 1e-8
        return Rotation.from_rotvec(axis * np.pi).as_matrix().astype(np.float32)
    axis = np.cross(from_dir, to_dir)
    axis /= np.linalg.norm(axis) + 1e-8
    angle = np.arccos(dot)
    return Rotation.from_rotvec(axis * angle).as_matrix().astype(np.float32)


def _joint_by_name(root: Joint, name: str) -> Optional[Joint]:
    if root.name == name:
        return root
    for c in root.children:
        found = _joint_by_name(c, name)
        if found is not None:
            return found
    return None


def _cmu_parent_map(root: Joint) -> Dict[str, str]:
    """Return a mapping from each CMU joint name to its parent joint name."""
    parents: Dict[str, str] = {}

    def visit(joint: Joint, parent_name: Optional[str]):
        if parent_name is not None:
            parents[joint.name] = parent_name
        for child in joint.children:
            visit(child, joint.name)

    visit(root, None)
    return parents


def _offset_chain_length(root: Joint, chain: List[str]) -> float:
    """Sum of offset lengths along a named joint chain."""
    total = 0.0
    for name in chain:
        j = _joint_by_name(root, name)
        if j is None:
            raise ValueError(f"Joint {name} not found in source skeleton")
        total += float(np.linalg.norm(j.offset))
    return total


def retarget(source_path: str, source_format: str, out_path: str, target_fps: float = 30.0, synthetic: bool = False):
    """Retarget a source clip to G1Skeleton34."""
    if synthetic:
        clip = generate_synthetic_clip()
        np.save(out_path, clip)
        return

    if source_format.lower() != "bvh":
        raise NotImplementedError(f"Retargeting from {source_format} is not implemented.")

    with open(source_path, "r", encoding="utf-8") as f:
        text = f.read()

    root, motion, frame_time = _parse_bvh(text)
    source_fps = 1.0 / frame_time

    cmu_positions, cmu_rotations = _forward_kinematics(root, motion)

    cfg = load_retarget_map()
    g1 = cfg["g1_skeleton"]
    parents = g1["parents"]
    offsets = np.array(g1["offsets"], dtype=np.float32)
    cmu_map = cfg["maps"]["cmu"]
    # Load Harmony4D-specific retarget map if available
    h4d_map_path = Path("tools/data/g1_retarget_map_harmony4d.json")
    if h4d_map_path.exists():
        h4d_cfg = json.load(open(h4d_map_path))
        cmu_map = h4d_cfg["maps"]["cmu"]

    # Compute scale factor so that CMU leg length matches G1 leg length.
    # Use left leg: LeftLeg -> LeftShin -> LeftFoot (or LeftUpLeg -> LeftLeg -> LeftFoot for CMU)
    leg_chain = ["LeftLeg", "LeftShin", "LeftFoot"]
    try:
        cmu_hip_to_ankle = _offset_chain_length(root, leg_chain)
    except ValueError:
        leg_chain = ["LeftUpLeg", "LeftLeg", "LeftFoot"]
        cmu_hip_to_ankle = _offset_chain_length(root, leg_chain)
    g1_hip_to_ankle = float(
        np.linalg.norm(offsets[1])
        + np.linalg.norm(offsets[2])
        + np.linalg.norm(offsets[3])
        + np.linalg.norm(offsets[4])
        + np.linalg.norm(offsets[5])
    )
    scale = g1_hip_to_ankle / cmu_hip_to_ankle if cmu_hip_to_ankle > 1e-6 else 0.01

    T = motion.shape[0]

    # Invert the map: G1 index -> CMU name.
    g1_to_cmu = {g1_idx: cmu_name for cmu_name, g1_idx in cmu_map.items()}

    # Pre-compute G1 bind bone directions (unit vectors in parent space).
    g1_bind_dirs = np.zeros((34, 3), dtype=np.float32)
    for j in range(34):
        norm = np.linalg.norm(offsets[j])
        if norm > 1e-8:
            g1_bind_dirs[j] = offsets[j] / norm

    # Pre-compute CMU bind bone directions for mapped joints.
    cmu_bind_dirs: Dict[int, np.ndarray] = {}
    for cmu_name, g1_idx in cmu_map.items():
        if cmu_name == "Hips":
            continue
        j = _joint_by_name(root, cmu_name)
        if j is None:
            raise ValueError(f"CMU joint {cmu_name} not found in source skeleton")
        norm = np.linalg.norm(j.offset)
        if norm > 1e-8:
            cmu_bind_dirs[g1_idx] = (j.offset / norm).astype(np.float32)

    # Build G1 local rotations so that each G1 bone points in the same direction
    # (in its G1 parent frame) as the corresponding CMU bone points in its CMU
    # parent frame.  Intermediate unmapped detail joints keep identity local
    # rotation.  Joints with no meaningful offset inherit the CMU world rotation.
    local_rots = np.zeros((T, 34, 3, 3), dtype=np.float32)
    world_rots = np.zeros((T, 34, 3, 3), dtype=np.float32)

    for t in range(T):
        for j in range(34):
            p = parents[j]
            parent_world = world_rots[t, p] if p >= 0 else np.eye(3, dtype=np.float32)
            if j in g1_to_cmu:
                cmu_name = g1_to_cmu[j]
                cmu_world = cmu_rotations[cmu_name][t]
                if j not in cmu_bind_dirs or np.linalg.norm(g1_bind_dirs[j]) < 1e-8:
                    # No meaningful bone direction: copy world rotation.
                    local_rots[t, j] = parent_world.T @ cmu_world
                else:
                    cmu_dir = cmu_bind_dirs[j]
                    g1_dir = g1_bind_dirs[j]
                    # Desired CMU bone direction expressed in G1 parent frame.
                    desired_dir = parent_world.T @ cmu_world @ cmu_dir
                    local_rots[t, j] = _minimal_rotation(g1_dir, desired_dir)
            else:
                local_rots[t, j] = np.eye(3, dtype=np.float32)
            world_rots[t, j] = parent_world @ local_rots[t, j]

    # Scale CMU root trajectory and place G1 pelvis at the scaled CMU Hips position.
    root_pos = cmu_positions["Hips"] * scale

    # Run G1 FK to get consistent world positions and rotations.
    g1_positions, g1_rotations = _g1_fk(local_rots, root_pos, parents, offsets)

    # Resample to target fps.
    g1_positions = _resample(g1_positions, source_fps, target_fps)
    g1_rotations = _resample(g1_rotations, source_fps, target_fps)

    # Orthonormalize rotation matrices after resampling.
    g1_rotations = _orthonormalize_rotations(g1_rotations)

    clip = {"joint_positions": g1_positions, "joint_rotations": g1_rotations, "fps": target_fps}
    np.save(out_path, clip)


def generate_synthetic_clip(frames: int = 60, joint_count: int = 34, seed: int = 0):
    """Deterministic test fixture: neutral standing pose with small sway."""
    rng = np.random.default_rng(seed)
    positions = np.zeros((frames, joint_count, 3), dtype=np.float32)
    # Pelvis height around 0.9 m.
    positions[:, 0, 1] = 0.9
    # Slight deterministic sway.
    t = np.arange(frames, dtype=np.float32) / frames
    positions[:, 0, 0] = np.sin(t * 2 * np.pi) * 0.05
    positions[:, 0, 2] = np.cos(t * 2 * np.pi) * 0.05
    # Add tiny noise to non-root joints so features are not all zeros.
    positions[:, 1:, :] = rng.normal(0.0, 0.02, (frames, joint_count - 1, 3)).astype(np.float32)
    rotations = np.tile(np.eye(3, dtype=np.float32), (frames, joint_count, 1, 1))
    return {"joint_positions": positions, "joint_rotations": rotations}


def main():
    parser = argparse.ArgumentParser(description="Retarget mocap to G1Skeleton34")
    parser.add_argument("--source", help="Source clip path")
    parser.add_argument("--format", choices=["bvh", "fbx", "c3d"], help="Source format")
    parser.add_argument("--out", help="Output .npy path")
    parser.add_argument("--fps", type=float, default=30.0, help="Target frame rate")
    parser.add_argument("--synthetic", action="store_true", help="Generate a deterministic test fixture instead of retargeting")
    args = parser.parse_args()
    if args.source is None and args.format is None and args.out is None:
        print("Retarget map loaded:", load_retarget_map()["g1_skeleton"]["joint_count"], "joints")
        return
    if not args.source or not args.format or not args.out:
        parser.error("--source, --format, and --out are required together")
    retarget(args.source, args.format, args.out, target_fps=args.fps, synthetic=args.synthetic)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
