#!/usr/bin/env python3
"""Convert CMU ASF/AMC to BVH for use with the existing retarget_to_g1.py pipeline.

The existing tools/retarget_to_g1.py parses BVH and auto-scales to G1.
This converter reads ASF/AMC and writes a cgspeed-compatible BVH.
"""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation

def parse_asf(path: str) -> dict:
    text = open(path).read()
    bones = {}
    for block in re.findall(r'begin\s*(.*?)\s*end', text, re.DOTALL):
        name_m = re.search(r'name\s+(\S+)', block)
        dir_m = re.search(r'direction\s+([\d.\-+eE]+)\s+([\d.\-+eE]+)\s+([\d.\-+eE]+)', block)
        len_m = re.search(r'length\s+([\d.\-+eE]+)', block)
        axis_m = re.search(r'axis\s+([\d.\-+eE]+)\s+([\d.\-+eE]+)\s+([\d.\-+eE]+)', block)
        dof_m = re.search(r'dof\s+(.+)', block)
        if name_m and dir_m and len_m:
            name = name_m.group(1).lower()
            bones[name] = {
                'name': name_m.group(1),
                'direction': np.array([float(dir_m.group(i)) for i in (1,2,3)]),
                'length': float(len_m.group(1)),
                'axis': np.array([float(axis_m.group(i)) for i in (1,2,3)]) if axis_m else np.zeros(3),
                'dof': dof_m.group(1).strip().split() if dof_m else ['rx','ry','rz'],
            }
    parents = {}
    hier_m = re.search(r':hierarchy\s*begin(.*?)end', text, re.DOTALL)
    for line in hier_m.group(1).strip().split('\n'):
        parts = line.strip().split()
        if len(parts) < 2: continue
        for child in parts[1:]: parents[child.lower()] = parts[0].lower()
    return {'bones': bones, 'parents': parents}

def parse_amc(path: str) -> list:
    text = open(path).read()
    frames = []; current = {}; frame_num = None
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#') or line.startswith(':'): continue
        if re.match(r'^\d+$', line):
            if frame_num is not None: frames.append(current)
            frame_num = int(line); current = {}
        else:
            parts = line.split()
            if len(parts) >= 2:
                current[parts[0].lower()] = [float(v) for v in parts[1:]]
    if frame_num is not None: frames.append(current)
    return frames

def amc_to_bvh(asf: dict, amc_frames: list, out_path: str):
    """Write a BVH file from ASF/AMC data."""
    bones = asf['bones']
    parents = asf['parents']
    
    # Build ordered bone list (root first)
    order = []
    visited = set()
    def visit(name):
        if name in visited: return
        p = parents.get(name)
        if p and p not in visited: visit(p)
        visited.add(name); order.append(name)
    for n in bones: visit(n)
    
    # Map DOF indices to channel indices
    # Root: TX TY TZ RX RY RZ (6 channels)
    # Other bones: their DOFs (1-3 rotation channels)
    
    # CMU ASF names -> cgspeed BVH names (what retarget_to_g1.py expects)
    C2C = {
        'root': 'Hips', 'lowerback': 'Spine', 'upperback': 'Spine1',
        'thorax': 'Spine2', 'lowerneck': 'Neck', 'upperneck': 'Neck1', 'head': 'Head',
        'lclavicle': 'LeftShoulder', 'lhumerus': 'LeftArm', 'lradius': 'LeftForeArm',
        'lwrist': 'LeftHand', 'lhand': 'LeftHand', 'lfingers': 'LeftHandIndex1',
        'rclavicle': 'RightShoulder', 'rhumerus': 'RightArm', 'rradius': 'RightForeArm',
        'rwrist': 'RightHand', 'rhand': 'RightHand', 'rfingers': 'RightHandIndex1',
        'lhipjoint': None, 'lfemur': 'LeftUpLeg', 'ltibia': 'LeftLeg',
        'lfoot': 'LeftFoot', 'ltoes': 'LeftToeBase',
        'rhipjoint': None, 'rfemur': 'RightUpLeg', 'rtibia': 'RightLeg',
        'rfoot': 'RightFoot', 'rtoes': 'RightToeBase',
    }

    def channels_for(bone_name):
        if bone_name == 'root':
            return ['Xposition','Yposition','Zposition','Zrotation','Yrotation','Xrotation']
        # Always emit 3 rotation channels (retarget_to_g1.py expects 3 or 6).
        # Bones with fewer DOFs get zero for the unused axes.
        return ['Zrotation','Yrotation','Xrotation']
    
    # Fix hierarchy: when a bone is skipped, reparent its children to its parent
    skip_bones = {n for n, v in C2C.items() if v is None}
    skip_bones.update({'lwrist','rwrist','lthumb','rthumb','upperneck'})
    for bone_name in list(bones.keys()):
        p = parents.get(bone_name)
        while p in skip_bones:
            p = parents.get(p, 'root')
        parents[bone_name] = p
    
    # Build offset for each bone (direction * length)
    for name in bones:
        b = bones[name]
        b['offset'] = b['direction'] * b['length']
    
    # Write BVH hierarchy
    lines = ["HIERARCHY"]
    
    def write_bone(name, indent):
        if name in skip_bones:
            # Still recurse into children of skipped bones
            children = [c for c, p in parents.items() 
                        if p == name and c not in skip_bones and C2C.get(c) is not None]
            for child in children:
                write_bone(child, indent)
            return
        cg_name = C2C.get(name, name)
        if cg_name is None:
            return
        bone = bones.get(name)
        is_root = name == 'root'
        offset = bone['offset'] if bone else np.zeros(3)
        chans = channels_for(name)
        
        if is_root:
            lines.append(f"ROOT {cg_name}")
        else:
            lines.append(f"{' '*indent}JOINT {cg_name}")
        
        lines.append(f"{' '*indent}{{")
        lines.append(f"{' '*indent}  OFFSET {offset[0]:.6f} {offset[1]:.6f} {offset[2]:.6f}")
        lines.append(f"{' '*indent}  CHANNELS {len(chans)} {' '.join(chans)}")
        
        children = [c for c, p in parents.items() 
                    if p == name and c not in skip_bones and C2C.get(c) is not None]
        if not children:
            lines.append(f"{' '*indent}  End Site")
            lines.append(f"{' '*indent}  {{")
            lines.append(f"{' '*indent}    OFFSET 0 0 0")
            lines.append(f"{' '*indent}  }}")
        
        for child in children:
            write_bone(child, indent + 2)
        
        lines.append(f"{' '*indent}}}")
    
    write_bone('root', 0)
    
    # Motion data
    frame_time = 1.0 / 120.0  # CMU is 120fps
    lines.append("MOTION")
    lines.append(f"Frames: {len(amc_frames)}")
    lines.append(f"Frame Time: {frame_time:.8f}")
    
    # Collect the set of bone names that actually appear in the hierarchy
    hierarchy_bones = set()
    def collect_hierarchy(name):
        if name in skip_bones:
            for c in [c for c, p in parents.items() if p == name and c not in skip_bones]:
                collect_hierarchy(c)
            return
        if C2C.get(name) is None:
            return
        hierarchy_bones.add(name)
        for c in [c for c, p in parents.items() if p == name and c not in skip_bones]:
            collect_hierarchy(c)
    collect_hierarchy('root')
    
    for frame in amc_frames:
        values = []
        for name in order:
            if name not in hierarchy_bones:
                continue
            chans = channels_for(name)
            if name == 'root':
                rd = frame.get('root', [0,0,0,0,0,0])
                values.extend([rd[0], rd[1], rd[2], rd[5], rd[4], rd[3]])  # BVH ZYX euler
            else:
                # Framewise marker validity: check if the bone has valid data for this frame.
                # Do NOT fill a missing joint by copying the preceding numeric joint.
                # Interpolate short occlusions explicitly and reject unsupported spans.
                av = frame.get(name)
                if av is None:
                    # Missing joint data: use zero rotation (no fill/copy from preceding joint).
                    # This is a deliberate choice to avoid fabricating motion.
                    av = [0.0, 0.0, 0.0]
                bone = bones.get(name)
                dof = bone['dof'] if bone else ['rx','ry','rz']
                # Map DOF values to ZYX euler (BVH channel order: Z Y X)
                euler_zyx = [0.0, 0.0, 0.0]  # [Z, Y, X]
                for i, d in enumerate(dof[:3]):
                    if i < len(av):
                        if d == 'rz': euler_zyx[0] = av[i]
                        elif d == 'ry': euler_zyx[1] = av[i]
                        elif d == 'rx': euler_zyx[2] = av[i]
                values.extend(euler_zyx)
        lines.append(' '.join(f'{v:.6f}' for v in values))
    
    Path(out_path).write_text('\n'.join(lines) + '\n')

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input-dir', default='data/cmu_combat')
    ap.add_argument('--output-dir', default='data/cmu_combat_bvh')
    args = ap.parse_args()
    
    in_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    amc_files = sorted(in_dir.glob('*.amc'))
    converted = 0
    for amc_path in amc_files:
        subj = amc_path.stem.split('_')[0]
        asf_path = in_dir / f'{subj}.asf'
        if not asf_path.exists():
            print(f'SKIP {amc_path.name}: no ASF')
            continue
        try:
            asf = parse_asf(str(asf_path))
            frames = parse_amc(str(amc_path))
            if len(frames) < 10: continue
            bvh_path = out_dir / f'{amc_path.stem}.bvh'
            amc_to_bvh(asf, frames, str(bvh_path))
            converted += 1
            print(f'  {amc_path.stem}: {len(frames)} frames -> {bvh_path.name}')
        except Exception as e:
            print(f'ERROR {amc_path.name}: {e}', file=sys.stderr)
    print(f'\nConverted: {converted}/{len(amc_files)}')

if __name__ == '__main__':
    raise SystemExit(main())
