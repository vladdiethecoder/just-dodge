# Just Dodge — 9-Action MotionBricks-Only Expansion (Phases 0-2)

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Enable the Rust game to generate one combat action (Strike) at runtime using the full MotionBricks root + pose + VQVAE pipeline, with real combat mocap primitives, perfect hitbox parity, and no prebaked clips or motion fallbacks.

**Architecture:** MotionBrains remains the sole motion engine. Phase 0 sources and retargets real combat mocap to the G1 skeleton. Phase 1 exports the full pose/root backbones and encodes a primitive library. Phase 2 bridges the Python MotionBrains inference stack into Rust via a deterministic Python service (PyO3) so the game can request a clip for `(action, weapon, stance, context)` and receive 34-joint world matrices on demand.

**Tech Stack:** Rust 2024, wgpu, ONNX Runtime (`ort`), PyO3, Python 3.11, PyTorch, MotionBricks/GR00T WBC, G1Skeleton34, ndarray.

---

## Current Context / Assumptions

- The repo already loads a partial MotionBrains stack in `src/motion.rs`: VQVAE encoder/decoder, pose_transformer, root_shared, root_token, root_conv.
- `assets/` has VQVAE artifacts but **lacks** the full `motionbricks_pose_backbone.onnx` and `motionbricks_root_backbone.onnx`.
- `tools/export_motionbricks_onnx.py` exists and exports the full backbones from the GR00T checkout at `/run/media/vdubrov/Bulk-SSD/gr00t/motionbricks`.
- `cargo check` passes; `cargo test` times out because the MotionPipeline tests load heavy ONNX models on every run (to be fixed in Task 17).
- The 3-action truth/combat code in `src/truth.rs` and `src/action_matrix.rs` will be expanded to 9 actions in a follow-on plan; this plan only wires the motion layer.
- No hitbox parity tooling exists yet; it is deferred to Phase 4 (follow-on plan).
- Deep armor/injury simulations are deferred to Phase 5 (follow-on plan).

---

## Phase 0 — Combat Mocap Sourcing & Retargeting

### Task 1: Create mocap provenance manifest schema

**Objective:** Define a machine-readable record of every motion source, license, and retargeting status.

**Files:**
- Create: `tools/data/mocap_manifest_schema.json`
- Test: validate it against an empty manifest

**Step 1: Write the schema**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "JustDodgeMocapManifest",
  "type": "object",
  "properties": {
    "version": { "type": "string" },
    "sources": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string" },
          "name": { "type": "string" },
          "url": { "type": "string" },
          "license": { "type": "string" },
          "license_url": { "type": "string" },
          "redistributable": { "type": "boolean" },
          "raw_format": { "enum": ["bvh", "fbx", "c3d"] },
          "local_path": { "type": "string" },
          "actions": {
            "type": "array",
            "items": { "enum": ["Strike", "Block", "Grab", "Thrust", "Feint", "DodgeAttack", "Bash", "Riposte", "Lunge"] }
          },
          "weapons": {
            "type": "array",
            "items": { "enum": ["Longsword", "Spear", "Dagger", "Mace"] }
          },
          "retargeted": { "type": "boolean" },
          "retargeted_path": { "type": "string" }
        },
        "required": ["id", "name", "license", "redistributable", "raw_format", "actions", "retargeted"]
      }
    }
  },
  "required": ["version", "sources"]
}
```

**Step 2: Validate with empty manifest**

Run: `python3 -c "import json; json.load(open('tools/data/mocap_manifest_schema.json'))"`
Expected: exit 0, no output.

**Step 3: Commit**

```bash
git add tools/data/mocap_manifest_schema.json
git commit -m "data: add mocap provenance manifest schema"
```

---

### Task 2: Audit free/commercial mocap sources and populate manifest

**Objective:** Decide which sources can supply the 9 actions × 4 weapons cells and record their licenses.

**Files:**
- Create: `tools/data/mocap_manifest.json`
- Modify: `docs/design/MOCAP_PROVENANCE.md`

**Step 1: Populate the manifest with known sources**

```json
{
  "version": "2026-07-09",
  "sources": [
    {
      "id": "cmu_boxing",
      "name": "CMU MoCap Boxing and Kicking",
      "url": "http://mocap.cs.cmu.edu/search.php?subjectnumber=13",
      "license": "CC-BY-4.0",
      "license_url": "http://mocap.cs.cmu.edu/",
      "redistributable": true,
      "raw_format": "c3d",
      "local_path": "",
      "actions": ["Strike", "DodgeAttack", "Bash"],
      "weapons": ["Longsword"],
      "retargeted": false,
      "retargeted_path": ""
    },
    {
      "id": "mixamo_sword",
      "name": "Mixamo Sword/Shield Pack",
      "url": "https://www.mixamo.com/",
      "license": "Adobe Standard EULA (embedded use permitted, raw redistribution prohibited)",
      "license_url": "https://helpx.adobe.com/manage-account/using/profile-terms.html",
      "redistributable": false,
      "raw_format": "fbx",
      "local_path": "",
      "actions": ["Strike", "Block", "Thrust", "Lunge", "DodgeAttack"],
      "weapons": ["Longsword", "Spear", "Dagger", "Mace"],
      "retargeted": false,
      "retargeted_path": ""
    },
    {
      "id": "mocaponline_ninja",
      "name": "MoCap Online Ninja Sword Pack",
      "url": "https://mocaponline.com/",
      "license": "Commercial (purchased seat)",
      "license_url": "",
      "redistributable": false,
      "raw_format": "fbx",
      "local_path": "",
      "actions": ["Strike", "Block", "Thrust", "Feint", "DodgeAttack", "Lunge", "Riposte"],
      "weapons": ["Longsword", "Dagger"],
      "retargeted": false,
      "retargeted_path": ""
    }
  ]
}
```

**Step 2: Validate manifest against schema**

Run: `python3 -c "import json, jsonschema; jsonschema.validate(json.load(open('tools/data/mocap_manifest.json')), json.load(open('tools/data/mocap_manifest_schema.json')))"`
Expected: exit 0, no output.

**Step 3: Write provenance doc**

Create `docs/design/MOCAP_PROVENANCE.md` summarizing:
- Which sources are redistributable (only CMU can live in the repo).
- Raw files must stay outside the repo for non-redistributable sources.
- Every committed retargeted clip must have a `source_id` field.

**Step 4: Commit**

```bash
git add tools/data/mocap_manifest.json docs/design/MOCAP_PROVENANCE.md
git commit -m "data: populate mocap provenance manifest and license notes"
```

---

### Task 3: Create G1Skeleton34 retargeting bone map

**Objective:** Map common source skeletons to the MotionBricks G1Skeleton34 hierarchy.

**Files:**
- Create: `tools/data/g1_retarget_map.json`
- Create: `tools/retarget_to_g1.py`

**Step 1: Write the bone map**

```json
{
  "comment": "Maps source skeleton joint names to G1Skeleton34 indices. Add entries per source.",
  "g1_skeleton": {
    "joint_count": 34,
    "parents": [-1, 0, 1, 2, 3, 4, 5, 6, 0, 8, 9, 10, 11, 12, 13, 0, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 17, 26, 27, 28, 29, 30, 31, 32],
    "names": ["pelvis", "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle", "left_foot",
              "left_toe", "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
              "right_foot", "right_toe", "waist_yaw", "waist_roll", "waist_pitch", "left_shoulder_pitch",
              "left_shoulder_roll", "left_shoulder_yaw", "left_elbow", "left_forearm", "left_wrist",
              "left_hand", "right_shoulder_pitch", "right_shoulder_roll", "right_shoulder_yaw", "right_elbow",
              "right_forearm", "right_wrist", "right_hand"]
  },
  "maps": {
    "mixamo": {
      "Hips": 0,
      "LeftUpLeg": 1,
      "LeftLeg": 4,
      "LeftFoot": 6,
      "LeftToeBase": 7,
      "RightUpLeg": 8,
      "RightLeg": 11,
      "RightFoot": 13,
      "RightToeBase": 14,
      "Spine": 15,
      "Spine1": 16,
      "Spine2": 17,
      "LeftShoulder": 18,
      "LeftArm": 20,
      "LeftForeArm": 21,
      "LeftHand": 24,
      "RightShoulder": 25,
      "RightArm": 27,
      "RightForeArm": 28,
      "RightHand": 31
    }
  }
}
```

**Step 2: Create stub retargeting script**

```python
#!/usr/bin/env python3
"""Retarget a source FBX/BVH clip to G1Skeleton34 and export numpy features."""
import json
import numpy as np


def load_retarget_map():
    with open("tools/data/g1_retarget_map.json") as f:
        return json.load(f)


def retarget(source_path: str, source_format: str, out_path: str):
    """TODO: implement with pymuscle/bvh parser + FK retargeting."""
    raise NotImplementedError("retargeting implementation follows mocap acquisition")


if __name__ == "__main__":
    print("Retarget map loaded:", load_retarget_map()["g1_skeleton"]["joint_count"], "joints")
```

**Step 3: Verify the map loads**

Run: `python3 tools/retarget_to_g1.py`
Expected: `Retarget map loaded: 34 joints`

**Step 4: Commit**

```bash
chmod +x tools/retarget_to_g1.py
git add tools/data/g1_retarget_map.json tools/retarget_to_g1.py
git commit -m "data: add G1 retargeting bone map and stub retargeter"
```

---

### Task 4: Create MotionBricks feature extractor stub

**Objective:** Provide the tooling that turns retargeted G1 poses into the MotionBricks feature representation used by primitives.

**Files:**
- Create: `tools/extract_motion_features.py`

**Step 1: Write feature extractor stub**

```python
#!/usr/bin/env python3
"""Extract MotionBricks GlobalRootGlobalJoints features from retargeted G1 poses."""
import numpy as np


def extract_features(joint_positions: np.ndarray, joint_rotations: np.ndarray, fps: int = 30) -> np.ndarray:
    """
    joint_positions: [T, 34, 3] in world meters.
    joint_rotations: [T, 34, 3, 3] rotation matrices.
    Returns: [T, 414] feature vector (global root + global joints subset).
    """
    T = joint_positions.shape[0]
    root_pos = joint_positions[:, 0, :]  # [T, 3]
    root_heading = np.arctan2(joint_rotations[:, 0, 0, 2], joint_rotations[:, 0, 2, 2])
    root_heading_cs = np.stack([np.cos(root_heading), np.sin(root_heading)], axis=-1)
    # Placeholder: real implementation computes ric_data, global_rot_data (6D), local_vel, foot_contacts.
    features = np.concatenate([root_pos, root_heading_cs, joint_positions.reshape(T, -1)], axis=-1)
    return features


if __name__ == "__main__":
    dummy = np.zeros((30, 34, 3))
    dummy[:, 0, 1] = 0.9
    rots = np.tile(np.eye(3), (30, 34, 1, 1))
    f = extract_features(dummy, rots)
    print("feature shape:", f.shape)
```

**Step 2: Run stub**

Run: `python3 tools/extract_motion_features.py`
Expected: `feature shape: (30, 104)`

**Step 3: Commit**

```bash
chmod +x tools/extract_motion_features.py
git add tools/extract_motion_features.py
git commit -m "tools: add MotionBricks feature extractor stub"
```

---

### Task 5: Define the primitive library schema

**Objective:** Establish the file format for 108+ combat primitives (action × weapon × stance).

**Files:**
- Create: `assets/data/primitive_schema.ron`

**Step 1: Write schema**

```ron
// Primitive library schema for MotionBrains condition-to-pose generation.
// Each primitive is a 4-frame target constraint, NOT a final animation clip.
(
    version: "2026-07-09",
    skeleton: G1Skeleton34,
    feature_dim: 414,
    frames_per_token: 4,
    primitives: [
        (
            action: Strike,
            weapon: Longsword,
            stance: Top,
            source_id: "cmu_boxing_01",
            feature_window: [[0.0; 414], [0.0; 414], [0.0; 414], [0.0; 414]],
            root_target: (position: [0.0, 0.0, 0.3], heading: 0.0),
        ),
    ],
)
```

**Step 2: Validate RON syntax**

Run: `cargo run --example ron_smoke -- assets/data/primitive_schema.ron` (if no example exists, skip and use `python3 -c "import ron; ..."` after adding the example in Task 8).

For now: `python3 -c "import ron; ron.load(open('assets/data/primitive_schema.ron'))"` if `python-ron` is available, else manual review.

**Step 3: Commit**

```bash
git add assets/data/primitive_schema.ron
git commit -m "data: add primitive library RON schema"
```

---

## Phase 1 — Full Backbone Export & Primitive Encoding

### Task 6: Export full MotionBrains ONNX backbones

**Objective:** Produce `motionbricks_pose_backbone.onnx` and `motionbricks_root_backbone.onnx` in `assets/`.

**Files:**
- Modify: `tools/export_motionbricks_onnx.py:274-562` (ensure output paths match expected names)
- Create: `assets/motionbricks_pose_backbone.onnx`
- Create: `assets/motionbricks_root_backbone.onnx`

**Step 1: Activate environment and run export**

```bash
export MOTIONBRICKS_DIR=/run/media/vdubrov/Bulk-SSD/gr00t/motionbricks
source /run/media/vdubrov/Bulk-SSD/mb_venv/bin/activate
python3 tools/export_motionbricks_onnx.py
```

**Step 2: Verify expected outputs exist**

Run:
```bash
ls -lh assets/motionbricks_pose_backbone.onnx assets/motionbricks_root_backbone.onnx assets/motionbricks_vqvae_encoder.onnx assets/motionbricks_vqvae_decoder.onnx assets/motionbricks_codebook.npy
```
Expected: all files present and non-zero size.

**Step 3: Commit**

```bash
git add -f assets/motionbricks_pose_backbone.onnx assets/motionbricks_root_backbone.onnx
git commit -m "assets: export full MotionBrains pose and root backbones"
```

---

### Task 7: Verify ONNX artifacts with a smoke test

**Objective:** Confirm the exported backbones accept their declared inputs and produce finite outputs.

**Files:**
- Create: `tools/verify_onnx.py`

**Step 1: Write verifier**

```python
#!/usr/bin/env python3
"""Smoke-test exported MotionBrains ONNX artifacts."""
import os
import numpy as np
import onnxruntime as ort

ASSETS = "assets"


def run_pose_backbone():
    sess = ort.InferenceSession(os.path.join(ASSETS, "motionbricks_pose_backbone.onnx"))
    n_tokens = 8
    pose_tokens = np.random.randint(0, 11, (1, n_tokens, 8), dtype=np.int64)
    local_root = np.random.randn(1, n_tokens * 4, 4).astype(np.float32)
    pose_cond = np.zeros((1, n_tokens * 4, 304), dtype=np.float32)
    has_pose = np.zeros((1, n_tokens * 4), dtype=np.float32)
    num_tokens = np.array([[n_tokens]], dtype=np.int64)
    out = sess.run(None, {
        "pose_tokens": pose_tokens,
        "local_root_values": local_root,
        "pose_cond": pose_cond,
        "has_pose_cond": has_pose,
        "num_tokens": num_tokens,
    })
    logits = out[0]
    assert logits.shape == (1, n_tokens, 8, 11), logits.shape
    assert np.isfinite(logits).all()
    print("pose_backbone OK", logits.shape)


def run_root_backbone():
    sess = ort.InferenceSession(os.path.join(ASSETS, "motionbricks_root_backbone.onnx"))
    n = 8
    g = np.random.randn(1, n, 5).astype(np.float32)
    hg = np.ones((1, n), dtype=np.float32)
    l = np.random.randn(1, n, 4).astype(np.float32)
    hl = np.ones((1, n), dtype=np.float32)
    p = np.random.randn(1, n, 304).astype(np.float32)
    hp = np.ones((1, n), dtype=np.float32)
    nt = np.array([[8]], dtype=np.int64)
    out = sess.run(None, {
        "global_root_values": g, "has_global_root": hg,
        "local_root_values": l, "has_local_root": hl,
        "poses": p, "has_poses": hp, "num_tokens": nt,
    })
    pred_global, num_logits = out
    assert pred_global.shape[1] >= n, pred_global.shape
    assert num_logits.shape == (1, 3), num_logits.shape  # num_token_classes typically 3
    assert np.isfinite(pred_global).all() and np.isfinite(num_logits).all()
    print("root_backbone OK", pred_global.shape, num_logits.shape)


if __name__ == "__main__":
    run_pose_backbone()
    run_root_backbone()
```

**Step 2: Run verifier**

Run: `python3 tools/verify_onnx.py`
Expected:
```
pose_backbone OK (1, 8, 8, 11)
root_backbone OK (1, 32, 5) (1, 3)
```

**Step 3: Commit**

```bash
chmod +x tools/verify_onnx.py
git add tools/verify_onnx.py
git commit -m "tools: add ONNX artifact smoke verifier"
```

---

### Task 8: Write primitive encoder

**Objective:** Encode validated retargeted clips into the primitive library RON format.

**Files:**
- Create: `tools/encode_primitives.py`
- Modify: `assets/data/primitive_schema.ron` (replace placeholder)

**Step 1: Write encoder stub**

```python
#!/usr/bin/env python3
"""Encode retargeted G1 clips into the primitive library."""
import json
import numpy as np


def encode_primitive(action, weapon, stance, source_id, features: np.ndarray, peak_idx: int):
    """Extract 4-frame peak window from features and emit RON snippet."""
    assert features.shape[1] == 414, features.shape
    window = features[peak_idx:peak_idx + 4]
    assert window.shape[0] == 4
    root = window[-1, :3]
    heading = np.arctan2(window[-1, 5], window[-1, 4])
    ron = f"""(
    action: {action},
    weapon: {weapon},
    stance: {stance},
    source_id: "{source_id}",
    feature_window: {json.dumps(window.tolist())},
    root_target: (position: [{root[0]:.6f}, {root[1]:.6f}, {root[2]:.6f}], heading: {heading:.6f}),
),"""
    return ron


if __name__ == "__main__":
    dummy = np.zeros((30, 414), dtype=np.float32)
    print(encode_primitive("Strike", "Longsword", "Top", "test", dummy, 10))
```

**Step 2: Run encoder stub**

Run: `python3 tools/encode_primitives.py`
Expected: a valid RON primitive entry printed.

**Step 3: Commit**

```bash
chmod +x tools/encode_primitives.py
git add tools/encode_primitives.py
git commit -m "tools: add primitive encoder stub"
```

---

### Task 9: Encode first real primitive

**Objective:** Produce at least one production primitive from real mocap to validate the pipeline end-to-end.

**Files:**
- Modify: `assets/data/primitives.ron`
- Modify: `tools/data/mocap_manifest.json` (mark source retargeted)

**Step 1:** Acquire/retarget one CMU or purchased clip for `Strike/Longsword/Top` and run:

```bash
python3 tools/retarget_to_g1.py --source <path> --format bvh --out clips/strike_longsword_top.npy
python3 tools/extract_motion_features.py clips/strike_longsword_top.npy --out clips/strike_longsword_top_features.npy
python3 tools/encode_primitives.py --action Strike --weapon Longsword --stance Top --source cmu_boxing_01 --features clips/strike_longsword_top_features.npy --peak 15 --out assets/data/primitives.ron
```

**Step 2: Verify the primitive loads**

Run: `python3 -c "import ron; print(ron.load(open('assets/data/primitives.ron'))['primitives'][0]['action'])"`
Expected: `Strike`

**Step 3: Commit**

```bash
git add assets/data/primitives.ron tools/data/mocap_manifest.json
git commit -m "data: add first production Strike/Longsword/Top primitive"
```

---

## Phase 2 — Rust MotionBrains Bridge

### Task 10: Add PyO3 dependency and scaffold Python inference service

**Objective:** Create a minimal Python package that loads MotionBrains models and exposes a `generate_clip` function callable from Rust.

**Files:**
- Modify: `Cargo.toml:6-24` (add `pyo3` feature)
- Create: `motionbricks_service/__init__.py`
- Create: `motionbricks_service/generate.py`
- Create: `motionbricks_service/requirements.txt`

**Step 1: Add PyO3 to Cargo.toml**

```toml
[dependencies]
pyo3 = { version = "0.23", features = ["auto-initialize"] }
```

**Step 2: Create service package**

`motionbricks_service/__init__.py`:
```python
from .generate import generate_clip, init_service
__all__ = ["generate_clip", "init_service"]
```

`motionbricks_service/generate.py`:
```python
"""Deterministic MotionBrains inference service for Just Dodge."""
import os
import torch
import numpy as np

_SERVICE = None


def init_service(
    mb_dir: str = "/run/media/vdubrov/Bulk-SSD/gr00t/motionbricks",
    checkpoint_dir: str = "/run/media/vdubrov/Bulk-SSD/gr00t/motionbricks/out",
):
    global _SERVICE
    if _SERVICE is not None:
        return _SERVICE
    # TODO: load pose_model, root_model, vqvae, motion_rep, clip_holder
    _SERVICE = {"ready": True, "mb_dir": mb_dir}
    return _SERVICE


def generate_clip(
    action: str,
    weapon: str,
    stance: str,
    context_frames: list,  # list of [34, 4x4] world matrices
    seed: int = 0,
) -> bytes:
    """
    Returns raw float32 bytes of [N, 413] frames (same layout as parse_g1_frame).
    """
    svc = init_service()
    assert svc["ready"]
    # TODO: run full_agent.generate_new_frames with the combat primitive.
    # Stub: return deterministic zero frames to prove the bridge.
    frames = np.zeros((30, 413), dtype=np.float32)
    frames[:, 1] = 0.9  # pelvis height
    return frames.tobytes()
```

`motionbricks_service/requirements.txt`:
```
torch>=2.0
numpy
motionbricks @ file:///run/media/vdubrov/Bulk-SSD/gr00t/motionbricks
```

**Step 3: Verify Python import**

Run:
```bash
cd /run/media/vdubrov/Bulk-SSD/Just Dodge
python3 -c "from motionbricks_service.generate import generate_clip; print(len(generate_clip('Strike','Longsword','Top',[])))"
```
Expected: `120` (30 frames × 4 bytes per float).

**Step 4: Commit**

```bash
git add Cargo.toml motionbricks_service/
git commit -m "feat: scaffold PyO3 MotionBrains inference service"
```

---

### Task 11: Implement full-agent inference inside the Python service

**Objective:** Replace the stub with the real MotionBrains root + pose + VQVAE pipeline.

**Files:**
- Modify: `motionbricks_service/generate.py`

**Step 1: Replicate the demo pipeline**

Load `motion_inference`, `clip_holder_G1`, `get_mujoco_converter`, build a `full_navigation_agent` equivalent, and call `generate_new_frames` with:
- `context_mujoco_qpos` derived from the incoming context matrices
- `mode` mapped to the `(action, weapon, stance)` primitive
- `movement_direction` and `facing_direction` toward the opponent
- `target_global_joint_positions` / `target_global_joint_rotations` from the selected primitive

**Step 2: Convert output to the G1 413-byte layout**

Use `motion_rep.inverse()` on the generated features and serialize `[frame, 413]` float32 bytes.

**Step 3: Determinism check**

Run twice with the same seed and compare bytes.

Run:
```bash
python3 -c "
from motionbricks_service.generate import generate_clip
a = generate_clip('Strike','Longsword','Top',[], seed=42)
b = generate_clip('Strike','Longsword','Top',[], seed=42)
assert a == b, 'non-deterministic'
print('determinism OK', len(a))
"
```
Expected: `determinism OK <N>`

**Step 4: Commit**

```bash
git add motionbricks_service/generate.py
git commit -m "feat: implement full MotionBrains inference in Python service"
```

---

### Task 12: Create Rust `MotionService` struct

**Objective:** Add a Rust wrapper that calls the Python service and returns `Vec<[Mat4; 34]>`.

**Files:**
- Create: `src/motion_service.rs`
- Modify: `src/main.rs:16-31` (add module)

**Step 1: Implement wrapper**

```rust
// Deterministic bridge to the Python MotionBrains inference service.
use anyhow::{Context, Result};
use glam::Mat4;
use pyo3::prelude::*;
use pyo3::types::PyList;

use crate::motion;

pub struct MotionService;

impl MotionService {
    pub fn new() -> Result<Self> {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let sys = py.import("sys")?;
            let path: &PyList = sys.getattr("path")?.downcast()?;
            let cwd = std::env::current_dir()?;
            path.insert(0, cwd.to_str().context("invalid cwd")?)?;
            let _ = py.import("motionbricks_service")?;
            Ok(Self)
        })
    }

    pub fn generate_clip(
        &self,
        action: &str,
        weapon: &str,
        stance: &str,
        context: &[[Mat4; 34]],
        seed: u64,
    ) -> Result<Vec<[Mat4; 34]>> {
        Python::with_gil(|py| {
            let svc = py.import("motionbricks_service")?;
            let ctx_list = PyList::empty(py);
            for frame in context {
                let flat: Vec<f32> = frame.iter().flat_map(|m| m.to_cols_array()).collect();
                let arr = numpy::PyArray1::from_vec(py, flat);
                ctx_list.append(arr)?;
            }
            let bytes: &[u8] = svc
                .getattr("generate_clip")?
                .call1((action, weapon, stance, ctx_list, seed))?
                .extract::<&[u8]>()?;
            motion::load_g1_frames_from_bytes(bytes)
        })
    }
}
```

**Step 2: Add helper in `src/motion.rs`**

Add near `load_g1_frames`:

```rust
/// Parse G1 frames from raw float32 bytes (same layout as .g1 files).
pub fn load_g1_frames_from_bytes(data: &[u8]) -> Result<Vec<[Mat4; 34]>> {
    if data.len() % (413 * 4) != 0 {
        anyhow::bail!("G1 byte length {} not a multiple of frame size {}", data.len(), 413 * 4);
    }
    let frame_count = data.len() / (413 * 4);
    let floats = bytemuck::cast_slice::<u8, f32>(data);
    let mut frames = Vec::with_capacity(frame_count);
    for f in 0..frame_count {
        let base = f * 413;
        frames.push(MotionPipeline::parse_g1_frame(&floats[base..base + 413]));
    }
    Ok(frames)
}
```

**Step 3: Add module in main.rs**

```rust
mod motion_service;
```

**Step 4: Build check**

Run: `cargo check --quiet 2>&1 | tail -20`
Expected: no errors (warnings OK).

**Step 5: Commit**

```bash
git add src/motion_service.rs src/motion.rs src/main.rs
git commit -m "feat: add Rust MotionService PyO3 bridge"
```

---

### Task 13: Add numpy conversion support

**Objective:** The Rust service needs to pass context matrices to Python as NumPy arrays. Add the `numpy` crate for PyO3.

**Files:**
- Modify: `Cargo.toml:6-24`

**Step 1: Add dependency**

```toml
numpy = { version = "0.23", features = ["nalgebra"] }
```

**Step 2: Update `src/motion_service.rs`**

Replace the placeholder `numpy::PyArray1::from_vec` usage with the real `numpy` crate API and ensure context is reshaped to `[frames, 34, 4, 4]` before crossing the boundary.

**Step 3: Build check**

Run: `cargo check --quiet 2>&1 | tail -20`
Expected: no errors.

**Step 4: Commit**

```bash
git add Cargo.toml src/motion_service.rs
git commit -m "deps: add numpy crate for PyO3 context marshalling"
```

---

### Task 14: Replace `generate_action_clip` with service call

**Objective:** The game runtime no longer uses hand-authored joint seeds; it requests MotionBrains-generated clips.

**Files:**
- Modify: `src/motion.rs:806-842`

**Step 1: Rewrite `generate_action_clip`**

```rust
pub fn generate_action_clip(
    condition: &ActionCondition,
    service: &crate::motion_service::MotionService,
) -> Result<Vec<[Mat4; 34]>, anyhow::Error> {
    let action_name = format!("{:?}", condition.action);
    let stance_name = format!("{:?}", condition.stance);
    // Weapon is not part of ActionCondition yet; default to Longsword for Phase 2.
    service.generate_clip(&action_name, "Longsword", &stance_name, &[condition.from_pose], 0)
}
```

**Step 2: Remove old VQVAE-only path from public API**

Keep `MotionPipeline` for decoding/encoding utilities but no longer use it as the primary generation path.

**Step 3: Update tests**

Temporarily gate the existing `generate_action_clip` tests behind a `#[cfg(feature = "legacy-vqvae")]` or convert them to service-call tests in Task 15.

**Step 4: Build check**

Run: `cargo check --quiet 2>&1 | tail -20`
Expected: no errors.

**Step 5: Commit**

```bash
git add src/motion.rs
git commit -m "feat: route action generation through MotionService"
```

---

### Task 15: Add Rust integration test for Strike generation

**Objective:** Prove the Rust bridge produces deterministic, finite G1 frames.

**Files:**
- Create: `tests/motion_service_integration.rs`

**Step 1: Write test**

```rust
use just_dodge::motion::{Action, ActionCondition, Stance};
use just_dodge::motion_service::MotionService;
use glam::Mat4;

#[test]
fn strike_generates_finite_frames() {
    let svc = MotionService::new().expect("Python service must initialize");
    let pose = [Mat4::IDENTITY; 34];
    let condition = ActionCondition {
        action: Action::Strike,
        stance: Stance::Top,
        from_pose: pose,
    };
    let clip = just_dodge::motion::generate_action_clip(&condition, &svc)
        .expect("service should return a clip");
    assert!(!clip.is_empty(), "clip must contain frames");
    for (fi, frame) in clip.iter().enumerate() {
        for (ji, m) in frame.iter().enumerate() {
            assert!(m.is_finite(), "non-finite matrix at frame {fi} joint {ji}");
        }
    }
}

#[test]
fn strike_is_deterministic() {
    let svc = MotionService::new().expect("Python service must initialize");
    let pose = [Mat4::IDENTITY; 34];
    let condition = ActionCondition {
        action: Action::Strike,
        stance: Stance::Top,
        from_pose: pose,
    };
    let a = just_dodge::motion::generate_action_clip(&condition, &svc).unwrap();
    let b = just_dodge::motion::generate_action_clip(&condition, &svc).unwrap();
    assert_eq!(a.len(), b.len());
    assert_eq!(a, b, "same seed must produce identical frames");
}
```

**Step 2: Expose modules as `pub`**

Modify `src/main.rs` to expose `pub mod motion; pub mod motion_service;` when built as a library, or create `src/lib.rs`:

```rust
pub mod motion;
pub mod motion_service;
```

Then change `main.rs` to `mod motion; mod motion_service;` and add `lib.rs`.

**Step 3: Run the test**

Run: `cargo test --test motion_service_integration -- --nocapture`
Expected: 2 passed.

**Step 4: Commit**

```bash
git add tests/motion_service_integration.rs src/lib.rs src/main.rs
git commit -m "test: add MotionService integration tests for Strike"
```

---

### Task 16: Wire generated clip into the main render loop

**Objective:** When the player commits Strike during Commit/Reveal, generate and play the MotionBrains clip instead of the idle loop.

**Files:**
- Modify: `src/main.rs:76-91, 284-303, 562-578`

**Step 1: Add service and per-actor clip slots**

```rust
struct App {
    // ... existing fields ...
    motion_service: motion_service::MotionService,
    player_clip: Option<Vec<[Mat4; 34]>>,
    opponent_clip: Option<Vec<[Mat4; 34]>>,
}
```

**Step 2: Initialize service in `main()`**

```rust
motion_service: motion_service::MotionService::new().expect("MotionBrains service required"),
player_clip: None,
opponent_clip: None,
```

**Step 3: Generate clips on commit**

In `render_frame`, after both sides are committed and truth enters Reveal, spawn a worker that calls `generate_action_clip` and stores the result:

```rust
if snapshot.phase == truth::Phase::Reveal && self.player_clip.is_none() {
    if let Some(action) = snapshot.player.action {
        let condition = motion::ActionCondition {
            action: map_truth_action(action),
            stance: map_truth_stance(snapshot.player.stance),
            from_pose: self.current_neutral_pose(),
        };
        let svc = &self.motion_service;
        if let Ok(clip) = motion::generate_action_clip(&condition, svc) {
            self.player_clip = Some(clip);
        }
    }
}
```

Add `map_truth_action` and `map_truth_stance` helpers to convert `truth::Action/Stance` to `motion::Action/Stance`.

**Step 4: Use generated clip in `current_pose()`**

```rust
fn current_pose(&self) -> ([Mat4; 24], [Mat4; 24]) {
    // Use generated combat motion only; if generation is not ready, hold the last validated pose. Clip fallback is forbidden (owner ruling 2026-07-19).
    let identity = [Mat4::IDENTITY; 24];
    // ... existing idle logic ...
}
```

**Step 5: Build and smoke test**

Run: `cargo build --release 2>&1 | tail -20`
Expected: successful build.

**Step 6: Commit**

```bash
git add src/main.rs
git commit -m "feat: play MotionBrains-generated Strike clip in main loop"
```

---

### Task 17: Fix `cargo test` timeout

**Objective:** Existing MotionPipeline tests load heavy ONNX models synchronously, causing CI timeouts. Make them opt-in.

**Files:**
- Modify: `src/motion.rs:852-995`

**Step 1: Gate heavy tests behind an environment variable**

Wrap the heavy tests:

```rust
fn heavy_tests_enabled() -> bool {
    std::env::var("JUSTDODGE_HEAVY_TESTS").is_ok_and(|v| !v.is_empty())
}
```

And at the top of each heavy test:

```rust
if !heavy_tests_enabled() {
    eprintln!("skipping heavy ONNX test; set JUSTDODGE_HEAVY_TESTS=1 to run");
    return;
}
```

**Step 2: Run fast tests**

Run: `cargo test --quiet`
Expected: finishes in <60s, all non-heavy tests pass.

**Step 3: Run heavy tests explicitly**

Run: `JUSTDODGE_HEAVY_TESTS=1 cargo test --quiet`
Expected: all tests pass (may take longer).

**Step 4: Commit**

```bash
git add src/motion.rs
git commit -m "test: gate heavy ONNX tests behind JUSTDODGE_HEAVY_TESTS"
```

---

## Verification Gates

Before this plan is considered complete, the following must be true:

1. `assets/motionbricks_pose_backbone.onnx` and `assets/motionbricks_root_backbone.onnx` exist and pass `tools/verify_onnx.py`.
2. `assets/data/primitives.ron` contains at least one production primitive from real mocap.
3. `cargo test --quiet` passes in <60s.
4. `cargo test --test motion_service_integration -- --nocapture` passes.
5. Running the game and committing Strike shows a generated combat clip (not idle).
6. Same inputs produce byte-identical G1 frame output from the Python service.

---

## Follow-On Plans

After this plan merges, open separate implementation plans for:

- **Phase 3 — 9×9 Action Matrix:** expand `src/action_matrix.rs` and `src/truth.rs` to the 9 universal actions with weapon/armor modifiers.
- **Phase 4 — Hitbox Parity:** per-frame skinned-mesh proxy extraction, weapon proxies, parity checker, and QA capture.
- **Phase 5 — Systems:** deterministic AI, replay/fight film, localized injury, deep armor/material solvers.

---

## Agent-Swarm Execution Notes

Dispatch these subagents in parallel where possible:

- **Agent A (Data):** owns Tasks 1-5 and Task 9 (mocap sourcing, retargeting, primitive encoding).
- **Agent B (Models):** owns Tasks 6-8 (ONNX export, verification, primitive tooling).
- **Agent C (Rust Bridge):** owns Tasks 10-17 (PyO3 service, Rust integration, tests, main loop wiring).

Agent C depends on Agent B's ONNX artifacts and Agent A's first primitive. Agent B depends on the GR00T checkout being intact. Use `subagent-driven-development` with two-stage review per task.
