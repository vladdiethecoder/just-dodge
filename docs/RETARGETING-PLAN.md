# Local-Space Retargeting Plan (r5)

## Problem

`retarget.rs` does world-space matrix interpolation (`lerp_mat4` on Mat4) which
produces shearing/scaling artifacts. World matrices between non-coplanar bones
cannot be linearly interpolated without distorting bone lengths.

## Principle

Retarget in **local space** (parent-relative), then rebuild world matrices via
forward kinematics. Local transforms preserve bone lengths because they're
relative rotations/translations from a parent — no cross-bone blending.

## Data flow

```
G1 world[34]                    Rich local[103]            Skin[24]
    │                                │                        │
    ▼                                ▼                        ▲
world_to_local()              map_g1_locals()                │
    │                                │                        │
    ▼                                ▼                        │
G1 local[34] ──────────────► rich local[103]                  │
                                  │                           │
                                  ▼                           │
                           fk_world(rich_local)               │
                                  │                           │
                                  ▼                           │
                           rich world[103] ─── map_to_skin ───┘
```

## Step 1: `world_to_local(world: &[Mat4; N], parents: &[i32; N]) -> [Mat4; N]`

```
local[i] = world[parent[i]].inverse() * world[i]   // if parent != -1
local[i] = world[i]                                 // if root
```

## Step 2: `map_g1_locals(g1_local: &[Mat4; 34]) -> [Mat4; BONE_COUNT]`

### 2a. Direct 1:1 mapping (legs, arms — ~13 bones)
G1_MAP already maps rich indices → G1 source indices.

For bones where `G1_MAP[i] != -1`:
```
src = G1_MAP[i]
rich_local[i] = g1_local[src]
```

### 2b. Spine interpolation (19 vertebrae from 3 anchors)

G1 anchors: waist_yaw(15)→L5[1] & T12[6], waist_roll(16)→T7[11], waist_pitch(17)→C7[13] & C1[19]

Strategy: distribute the 3-anchor spine rotation across 19 vertebrae using
fractional rotation weights. For each vertebra `v` between anchors:

```
t = normalized position of v between anchor_a and anchor_b
local_rot(v) = slerp(anchor_a_rot, anchor_b_rot, t)
local_pos(v) = lerp(anchor_a_pos, anchor_b_pos, t)
```

Positions are root-relative offsets (not world). Rotation is the slerp of
the quaternion extracted from the G1 local matrix.

### 2c. Propagation (no-G1 bones: fingers, foot details, extra spine bones)

Bones without G1 data use **rest-pose local** transforms:
```
rich_local[i] = rest_pose[i]  // identity or precomputed
```

### 2d. IK stubs (hands, feet, head)
For IK-target bones (LeftHandIK, RightHandIK, LFootIK, RFootIK, HeadIK):
keep them at rest pose for now. Real IK solver deferred to combat phase.

## Step 3: `fk_world(local: &[Mat4; BONE_COUNT]) -> [Mat4; BONE_COUNT]`

Forward kinematics — accumulate hierarchy:
```
world = [Mat4::IDENTITY; BONE_COUNT]
for i in 0..BONE_COUNT:
    if bone_parent(i) >= 0:
        world[i] = world[bone_parent(i) as usize] * local[i]
    else:
        world[i] = local[i]
```

## Step 4: `map_to_skin(rich_world: &[Mat4; BONE_COUNT]) -> [Mat4; 24]`

Same as current `asset::compute_skin_matrices` but using rich world instead
of G1 world:

```
align = inv_bind[0].inverse() * rich_world[PELVIS].inverse()
for i in 0..24:
    skin_idx = SKIN_MAP[i]
    skin[i] = align * rich_world[skin_idx] * inv_bind[i]
```

## Rest pose requirement

`default_rest_transforms()` in skeleton.rs must be replaced with real rest-pose
local transforms derived from the mannequin mesh's inverse_bind matrices:

```
for i in 0..BONE_COUNT:
    skin_idx = SKIN_MAP[i]
    if skin_idx >= 0:
        world[i] = inv_bind[skin_idx].inverse()
```

Then compute local from world using bone_parent.

This ensures the rich skeleton's rest pose matches the mannequin's bind pose,
so bones without G1 data (fingers, feet) stay in their correct positions.

## File changes

1. `src/retarget.rs` — rewrite:
   - `world_to_local()`
   - `map_g1_locals()` with spine slerp
   - `fk_world()`
   - `map_to_skin()` (replaces `rich_to_skin_matrices`)
   - `g1_to_skin()` entry point (replaces current)

2. `src/skeleton.rs` — `default_rest_transforms()`:
   - Read mannequin_male.bin at compile time? No — pass at runtime.
   - Add `fn rest_pose_from_mesh(mesh: &SkinnedMeshData) -> [Mat4; BONE_COUNT]`

3. `src/main.rs` & `src/bin/mb_probe.rs` — swap back:
   - `asset::compute_skin_matrices` → `retarget::g1_to_skin`
   - (only after retarget.rs is rewritten with local-space approach)

## Verification criteria

1. Unit test: spine interpolation produces continuous rotation curve
2. Unit test: spread pose (same as current no-shear test) passes with retarget
3. Unit test: identity G1 → identity skin (rest pose)
4. Visual: shot harness showing no shearing on animated frames
5. Visual: Xvfb live game with MotionBricks pipeline (after ONNX fix)