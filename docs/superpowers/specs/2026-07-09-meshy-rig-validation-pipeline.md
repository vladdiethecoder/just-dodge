# Meshy Rig → MotionBricks Validation Pipeline

> **Date:** 2026-07-09  
> **Scope:** Just Dodge 3D fighter asset pipeline  
> **Authority:** Meshy official docs (`/tmp/meshy_official_docs_2026-07-09`)  
> **Constraint:** No API calls. This is a design/spec artifact only.

---

## Executive Summary

Meshy rigging is a **source-rig generator**, not the runtime motion authority. Just Dodge uses NVIDIA MotionBricks as its motion engine and a rich 103-bone combat skeleton. The Meshy rig is therefore useful only as one possible **starting armature** for a fighter model. Before it can drive MotionBricks or the rich skeleton, it must pass a strict validation/remapping pipeline.

**Key decision:** Meshy rigging is **not on the critical runtime path**. The canonical runtime skeleton is the existing MotionBricks-compatible G1Skeleton34 (34 joints) and the rich 103-bone combat skeleton. Meshy can supply a humanoid source rig; if it fails, we fall back to hand-authored/source-rig alternatives without blocking MotionBricks generation.

---

## 1. Exact Constraints from Official Meshy Docs

### 1.1 Rigging API (`POST /openapi/v1/rigging`)

| Constraint | Value | Implication for Just Dodge |
|------------|-------|----------------------------|
| Input | `input_task_id` **or** `model_url` | Use `input_task_id` from a Meshy text-to-3D / image-to-3D fighter task, or upload a textured GLB. |
| Format | `.glb` only for `model_url` | Any fighter mesh must be exported to GLB before rigging. |
| Face limit | **300,000 faces** for `input_task_id` | Must remesh high-res anatomy-aware fighters before rigging. |
| Forward axis | `model_url` face must point **+Z** | GLB exporter must orient fighter facing +Z; otherwise pose estimation fails (422). |
| `height_meters` | default 1.7, must be positive | Set to in-game fighter height (e.g. 1.75 m). |
| `texture_image_url` | optional PNG UV texture | Only needed if GLB texture is missing/separate. |
| Suitability | textured humanoid with clear limbs | Not for untextured meshes, non-humanoids, or anatomical-internal meshes. |

### 1.2 Rigging Outputs

On `SUCCEEDED`, the rigging task returns:

- `rigged_character_fbx_url`
- `rigged_character_glb_url`
- `basic_animations` (included free):
  - `walking_glb_url` / `walking_fbx_url` / `walking_armature_glb_url`
  - `running_glb_url` / `running_fbx_url` / `running_armature_glb_url`

**Cost:** 5 credits per rigging task (refunded on failure).

**Status lifecycle:** `PENDING` → `IN_PROGRESS` → `SUCCEEDED` / `FAILED` / `CANCELED`.

### 1.3 Animation API (`POST /openapi/v1/animations`)

| Constraint | Value | Implication |
|------------|-------|-------------|
| Input | `rig_task_id` + `action_id` | Only works on a completed rigging task. |
| Post-process | `change_fps` (24/25/30/60), `fbx2usdz`, `extract_armature` | FPS conversion is the only operation likely useful for MotionBricks source inspection. |
| Cost | 3 credits per animation task | Avoid if only the rig is needed; walking/running are free from rigging. |

### 1.4 Animation Library

- Catalog is dynamic JSON at `https://api.meshy.ai/web/public/animations/resources`.
- Docs explicitly say: **for applying animations to a rigged character, see Animation API**.
- Action IDs are integers; the docs only give the example `92` (Double Combo Attack).

---

## 2. Just Dodge Architecture: Meshy as Source Rig, MotionBricks as Authority

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. Fighter mesh generation (Meshy text/image-to-3D)         │
│    → textured GLB, ≤300k faces, facing +Z                   │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│ 2. Meshy Rigging                                            │
│    → GLB/FBX with Mixamo-style humanoid skeleton            │
│    → free walk/run animations                               │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│ 3. Rig Validation Gate (this pipeline)                      │
│    A. Skeleton topology check                               │
│    B. Joint-name canonicalization                           │
│    C. Retarget to G1Skeleton34 (34 joints)                  │
│    D. Retarget to rich skeleton (103 bones)                 │
│    E. Bind-pose parity check against mannequin              │
│    F. MotionBricks seed compatibility                       │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│ 4. Runtime Motion                                           │
│    MotionBricks VQVAE → G1Skeleton34 world matrices         │
│    → rich skeleton FK → 24 skinning matrices → GPU          │
└─────────────────────────────────────────────────────────────┘
```

**Important:** MotionBricks does **not** consume Meshy animations. The Animation API is therefore only useful for:

1. Visual QA of the rigged character in a generic action.
2. Extracting the armature for inspection.
3. Converting a generic clip to 60 fps for side-by-side comparison.

---

## 3. Maximally Reliable Rig-Validation Pipeline

### 3.1 Pre-Rig Mesh Validation

| Check | Tool/Method | Failure Action |
|-------|-------------|----------------|
| Face count ≤ 300,000 | `trimesh` / `pymeshlab` face count | Run Meshy Remesh API or local decimation; retry rigging. |
| Textured / humanoid | Visual QA + heuristics | Reject non-humanoid; use anatomical reference strategy instead. |
| Forward axis = +Z | Bounding-box major extent on Z at bind pose | Re-export with corrected orientation before rigging. |
| Manifold, watertight | `pymeshlab` / `trimesh` repair | Repair with Meshy `print-repair` or local remesh. |
| Height matches `height_meters` | Bounding-box height | Set accurate `height_meters` parameter. |

### 3.2 Rigging Task Lifecycle

1. **Create task** with `input_task_id` (preferred) or `model_url`.
2. **Poll** `GET /openapi/v1/rigging/:id` or **SSE stream** `/rigging/:id/stream`.
3. **Handle failures**:
   - `400 Face count exceeded` → remesh, retry.
   - `422 Pose estimation failed` → check +Z orientation and humanoid clarity; retry once, then reject asset.
   - `429` → exponential backoff.
   - `FAILED` → credits refunded; log and reject or retry with adjusted mesh.
4. **Download** `rigged_character_glb_url` and optionally `walking_glb_url` for QA.
5. **Cache** task metadata and asset paths in `tools/data/meshy_rig_manifest.json`.

### 3.3 Skeleton Topology Check

When the rigged GLB is downloaded, verify the skeleton is usable as a source rig:

| Check | Acceptance Criteria |
|-------|---------------------|
| Root bone exists | Exactly one node with no parent in the skeleton subtree. |
| Required major bones present | hips, spine, chest/upper chest, neck, head, left/right upper leg/lower leg/foot/toes, left/right shoulder/upper arm/lower arm/hand, and at least 3 fingers per hand (thumb, index, middle). |
| No bone cycles | Parent graph is a DAG. |
| Reasonable bone count | 40–120 bones. More than 120 is acceptable but complicates retargeting. |
| No zero-length bones | Bone length > 1 mm (avoids divide-by-zero in retargeting). |
| Scale | Bind-pose scale is uniform and positive. |

**Tool:** Python script `tools/validate_meshy_rig.py` using `pygltflib` or `trimesh`.

### 3.4 Joint-Name Canonicalization

Meshy uses its own bone names. Map them to a canonical set before retargeting. Example mapping table (to be extended after inspecting actual Meshy output):

| Canonical | Likely Meshy Names |
|-----------|--------------------|
| Hips / Pelvis | `Hips`, `pelvis`, `root` |
| Spine | `Spine`, `spine`, `Spine001` |
| Chest | `Chest`, `chest`, `Spine002`, `UpperChest` |
| Neck | `Neck`, `neck` |
| Head | `Head`, `head` |
| LeftUpperLeg | `LeftUpLeg`, `LeftThigh` |
| LeftLowerLeg | `LeftLeg`, `LeftShin` |
| LeftFoot | `LeftFoot` |
| LeftToes | `LeftToeBase`, `LeftToe` |
| LeftShoulder | `LeftShoulder`, `LeftClavicle` |
| LeftUpperArm | `LeftArm`, `LeftUpperArm` |
| LeftLowerArm | `LeftForeArm`, `LeftLowerArm` |
| LeftHand | `LeftHand` |
| ... | ... |

The canonicalizer must be **fuzzy** (substring/regex) but emit a warning for every unmatched required bone.

### 3.5 Retarget to G1Skeleton34

Use the existing `tools/retarget_to_g1.py` infrastructure. Map canonical Meshy joints to G1Skeleton34 indices as defined in `src/motion.rs`:

| G1 Index | G1 Name | Source Joint |
|----------|---------|--------------|
| 0 | pelvis | Hips |
| 1 | left_hip_yaw | LeftUpperLeg |
| 4 | left_knee | LeftLowerLeg |
| 5 | left_ankle_pitch | LeftFoot |
| 7 | left_toe_base | LeftToes |
| 8 | right_hip_yaw | RightUpperLeg |
| 11 | right_knee | RightLowerLeg |
| 12 | right_ankle_pitch | RightFoot |
| 14 | right_toe_base | RightToes |
| 15 | waist_yaw | Spine/Chest blend |
| 16 | waist_roll | Chest |
| 17 | waist_pitch | Neck/Head blend |
| 18 | left_shoulder_pitch | LeftShoulder |
| 19 | left_shoulder_roll | LeftUpperArm |
| 21 | left_elbow | LeftLowerArm |
| 23 | left_wrist_pitch | LeftHand |
| 26 | right_shoulder_pitch | RightShoulder |
| 27 | right_shoulder_roll | RightUpperArm |
| 29 | right_elbow | RightLowerArm |
| 31 | right_wrist_pitch | RightHand |

Validation:

- All mapped G1 joints have finite transforms.
- Root height is within ±10% of expected `height_meters`.
- Armspan and leg length are within biological limits relative to height.

### 3.6 Retarget to Rich Skeleton (103 bones)

Reuse `src/retarget.rs` (`g1_to_skin` and FK pipeline):

1. Convert G1 world matrices to G1 local matrices.
2. Map G1 locals to rich skeleton locals via `skeleton::G1_MAP`.
3. Interpolate spine vertebrae and detail bones (fingers, feet, head).
4. Forward-kinematics to rich world matrices.
5. Compute 24 skinning matrices with `asset::compute_skin_matrices`.

Validation:

- All 103 rich bones have finite world transforms.
- All 24 skinning matrices have positive determinant (no shearing).
- Bind pose matches the mannequin within a tolerance.

### 3.7 Bind-Pose Parity Check

| Check | Tolerance | Failure Action |
|-------|-----------|----------------|
| Feet on ground (Y ≈ 0) | ±2 cm | Apply root offset / rescale. |
| Upright orientation | pelvis up-axis within 5° of world +Y | Reject or manually fix bind pose. |
| Arms symmetric at sides | left/right clavicle/humerus within 5° | Warn; optional manual correction. |
| Head facing +Z | head forward within 10° of +Z | Re-export with corrected orientation. |
| No interpenetration | mesh self-collision heuristic | Warn artist; not a hard fail. |

### 3.8 MotionBricks Seed Compatibility

A Meshy-rigged fighter is **game-ready** only if it can accept a MotionBricks-generated clip:

1. Load `assets/motionbricks_vqvae_encoder.onnx`, decoder, codebook, etc.
2. Build a neutral encoder input from the fighter's bind pose.
3. Run encode → decode and confirm output is finite and visually neutral.
4. Run `tools/qa/visual_verify_primitives.py` keyframe render.

If the VQVAE decode explodes or produces non-finite matrices, the fighter's bind pose / scale is incompatible with MotionBricks training distribution.

---

## 4. Failure / Retry Behavior

| Stage | Failure Mode | Retry Policy | Escalation |
|-------|--------------|--------------|------------|
| Mesh generation | anatomy wrong / non-humanoid | 1 prompt refinement | Use anatomical reference strategy instead. |
| Pre-rig validation | face count > 300k | remesh + retry once | Local decimation + retry. |
| Rigging | 422 pose estimation | check +Z orientation + retry once | Reject asset. |
| Rigging | 429 rate limit | exponential backoff (5s, 15s, 45s, 2m) | Log and defer. |
| Topology check | missing required bones | n/a | Reject or use Mixamo source rig. |
| Retarget | non-finite matrices | n/a | Reject asset. |
| Bind-pose parity | feet/head/orientation out of tolerance | scale/orientation fix once | Manual artist cleanup. |
| MotionBricks seed | decode non-finite | n/a | Reject asset; scale/bind mismatch. |

---

## 5. Files and Data Artifacts

| File | Purpose |
|------|---------|
| `tools/validate_meshy_rig.py` | Skeleton topology, bone-name canonicalization, G1 retarget validation. |
| `tools/data/meshy_rig_manifest.json` | Record of rig tasks, outputs, validation status, and failure reasons. |
| `tools/data/meshy_to_canonical_bones.json` | Fuzzy joint-name mapping from Meshy to canonical skeleton. |
| `docs/superpowers/specs/2026-07-09-meshy-rig-validation-pipeline.md` | This design document. |

---

## 6. Costs & Economics

| Operation | Credits | When Used |
|-----------|---------|-----------|
| Meshy text-to-3D preview | 5–20 | Fighter mesh generation. |
| Meshy rigging | 5 | Per fighter source rig. |
| Meshy animation | 3 | Only for QA, not runtime. |
| MotionBricks generation | local compute | Runtime motion authority. |

**Recommendation:** Budget 5–10 rigging attempts per fighter design. Use the free walking/running animations only for visual QA, never as runtime clips.

---

## 7. Summary of Design Decisions

1. **MotionBricks remains the sole motion authority.** Meshy animations are not loaded by the game.
2. **Meshy rigging is a source-rig convenience.** The canonical skeletons are G1Skeleton34 and the 103-bone rich skeleton.
3. **Strict validation gate before runtime.** Every rigged fighter must pass topology, retarget, bind-pose, and MotionBricks seed checks.
4. **Fail fast and preserve determinism.** Failed rigs are logged, credits are refunded, and the pipeline falls back to non-Meshy source rigs rather than producing bad runtime data.
5. **No runtime dependency on Meshy asset URLs.** All validated artifacts are downloaded and version-controlled locally.
