# MotionBricks Neural Animation Pipeline — Implementation Plan

> **For Hermes:** Use this plan task-by-task. Each task is 2–5 min of focused work.

**Goal:** Export the three MotionBricks ONNX models (VQVAE, Pose transformer, Root transformer), integrate ONNX Runtime into the Rust engine, build the inference pipeline, connect combat actions → motion primitives, and render an animated mannequin on the arena.

**Architecture:**
- Export all sub-networks as separate ONNX files from the trained checkpoints
- Rust inference pipeline loads ONNX models via `ort` crate, runs the denoising/generation loop on GPU (CUDA via ONNX Runtime)
- The mannequin is skinned via a compute-shader vertex skinning pass in wgpu, driven by predicted joint transforms
- Combat actions map to token-level conditioning masks in the pose transformer

**Tech Stack:**
- Python: PyTorch 2.x, ONNX (opset 17), MotionBricks codebase
- Rust: ort (ONNX Runtime C++ bindings), wgpu 22.0, winit 0.30, glam 0.28
- Models: G1 skeleton (34 joints), 30 fps, down_t=2 → 4 frames per token

**Current baseline (verified):**
- Rust/wgpu engine: arena rock rendering, camera, depth buffer, texture
- 3 arena assets extracted (GLB → .bin format)
- MotionBricks repo at `/run/media/vdubrov/Bulk-SSD/gr00t/motionbricks`
- Checkpoints: pose, root, VQVAE — all version_1/model-step=2000000.ckpt
- VQVAE: 8 heads, 256 code dim, nb_code=1e8 (large vocab), down_t=2
- Pose backbone: 16-layer transformer, n_embd=1024, n_head=16
- Root backbone: 3+3 layer transformer, n_embd=512, n_head=16

---

## Phase 0: Research & Validation (read-only)

### Task 0.1: Verify ONNX export path in Python

**Objective:** Confirm the PyTorch model loading + ONNX export works before writing Rust code.

**Files:**
- Verify: `tools/export_motionbricks_onnx.py`
- Verify: `$MB_VENV` and dependencies available

**Step 1: Check Python environment availability**

Run:
```bash
source /run/media/vdubrov/Bulk-SSD/gr00t/motionbricks/venv/bin/activate && \
python -c "import torch; import onnx; print('PyTorch', torch.__version__, 'ONNX', onnx.__version__)"
```

Expected: PyTorch 2.x + ONNX available.

**Step 2: Check checkpoint integrity**  

Run:
```bash
python -c "
import torch
for p in ['pose', 'root']:
    ckpt = torch.load(f'/run/media/vdubrov/Bulk-SSD/gr00t/motionbricks/out/motionbricks_{p}/version_1/checkpoints/model-step=2000000.ckpt', map_location='cpu', weights_only=True)
    print(f'{p} keys:', list(ckpt.keys())[:5])
"
```

Expected: `state_dict` and `hyper_parameters` / `config` keys present.

**Step 3: Understand the exact forward signatures**

Read the model source to determine precise tensor shapes for ONNX export.

From analysis:
- VQVAE encoder: input `[B, 241, T]` (feature-extracted motion, channels-first), output `[B, 256, T/4]`
- VQVAE decoder: input `[B, 256, T/4]` (quantized), output `[B, 329, T]`
- Pose backbone: input `pose_tokens[B, N, 8]`, `local_root_values[B, N*4, 4]`, `pose_cond[B, N*4, feat]`, `has_pose_cond[B, N*4]`, `num_tokens[B, 1]`. Output `pose_logits[B, N, 8, nb_code_per_head]`
- Root backbone: input `global_root_values[B, 8, 5]`, `has_global_root[B, 8]`, `local_root_values[B, 8, 4]`, `has_local_root[B, 8]`, `poses[B, 8, feat]`, `has_poses[B, 8]`, `num_tokens[B, 1]`. Output `pred_global_root_values[B, maxTokens*4, 5]`, `num_token_logits[B, classes]`

---

## Phase 1: ONNX Export Script

### Task 1.1: Rewrite export script with correct model instantiation

**Objective:** Load checkpoints with correct `pose_vqvae_network`, `backbone_network`, etc. and export each sub-network.

**Files:**
- Rewrite: `tools/export_motionbricks_onnx.py`

The key challenge is that the checkpoint stores the full `LightningModule` but we need to export the sub-networks:
- `pose_model.supporting_nets['pose_net']` → VQVAE (encoder + decoder separately)
- `pose_model.backbone_net` → Pose transformer
- `root_model.backbone_net` → Root network (shared + root_token transformers + conv decoder)

**Step 1: Create the instantiation function**

The hparams.yaml contains `_target_` directives. We need to:
1. Load the skeleton: `G1Skeleton34`
2. Build `motion_rep` from it: `GlobalRootGlobalJoints(name='g1skel34_dual_root_global_joints')`
3. Build `pose_vqvae_network` (VQVAE with pose_root_mode='pose')
4. Build `pose_backbone_network` with `motion_rep` and args from hparams
5. Load state dicts from checkpoint
6. Export each sub-network

**Export targets (separate ONNX files):**

| ONNX File | Network | Input | Output |
|-----------|---------|-------|--------|
| `vqvae_encoder.onnx` | `vqvae.encoder` | `[B, 241, T]` | `[B, 256, T/4]` |
| `vqvae_decoder.onnx` | `vqvae.decoder` | `[B, 256, T/4]`, `target_cond`, `external_cond` | `[B, 329, T]` |
| `vqvae_quantizer.onnx` | `vqvae.quantizer` | `[B, 256, T/4]` | `indices[B, H, T/4]` |
| `vqvae_dequantizer.onnx` | `vqvae.quantizer.dequantize` | `indices[B, H, T/4]` | `[B, 256, T/4]` |
| `pose_backbone.onnx` | `pose_model.backbone_net` | tokens, root_values, pose_cond, num_tokens | `pose_logits` |
| `root_backbone.onnx` | `root_model.backbone_net` | root_values, poses, num_tokens | `pred_global_root_values` |

**NOTE:** The quantizer uses EMA codebooks with 1e8 codes (large) — ONNX export of the
`forward_into_idx` may need a custom export step since it's not a standard torch op.
Fallback: implement nearest-neighbour codebook lookup as a `torch.nn.Module` wrapper.

**Step 2: Write the complete export script**

See new script at `tools/export_motionbricks_onnx.py`.

**Step 3: Run the export**

```bash
source /run/media/vdubrov/Bulk-SSD/gr00t/motionbricks/venv/bin/activate && \
python tools/export_motionbricks_onnx.py
```

Expected: 5-6 `.onnx` files created in `assets/`.

**Step 4: Validate exported models**

```bash
python -c "
import onnx
for name in ['vqvae_encoder', 'vqvae_decoder', 'pose_backbone', 'root_backbone']:
    m = onnx.load(f'assets/motionbricks_{name}.onnx')
    onnx.checker.check_model(m)
    print(f'{name}: {len(m.graph.node)} ops, {len(m.graph.input)} inputs → {len(m.graph.output)} outputs')
"
```

Expected: All models pass ONNX checker.

---

## Phase 2: Add `ort` Crate to Rust Engine

### Task 2.1: Add ort dependency to Cargo.toml

**Objective:** Add ONNX Runtime Rust bindings.

**Files:**
- Modify: `Cargo.toml`

**Step 1: Add ort dependency**

```toml
ort = { version = "1.16", features = ["load-dynamic", "cuda"] }
```

The `cuda` feature enables GPU execution via ONNX Runtime CUDA EP.

**Step 2: Verify build**

```bash
cargo check
```

Expected: Clean compile. First build downloads + compiles ONNX Runtime C++ lib (may take a few minutes).

### Task 2.2: Verify ort works with a minimal test

**Objective:** Confirm ort can load + run inference on one ONNX model.

**Step 1:** Create a smoke test that loads the encoder ONNX, creates random input, runs inference.

Place in `src/tests/motion_test.rs` or just run via a small binary.

---

## Phase 3: Rust ONNX Inference Pipeline

### Task 3.1: Create `motion` module

**Objective:** New `src/motion.rs` module that encapsulates the full inference pipeline.

**Files:**
- Create: `src/motion.rs`
- Modify: `src/main.rs` (add `mod motion;`)

**Module structure:**

```rust
pub struct MotionPipeline {
    // Loaded ONNX sessions
    encoder: ort::Session,
    decoder: ort::Session,
    pose_backbone: ort::Session,
    root_backbone: ort::Session,
    // Codebook (matrix of size [num_heads * nb_code_per_head, code_dim_per_head])
    codebook: ndarray::Array2<f32>,
}

impl MotionPipeline {
    pub fn new(assets_path: &str) -> Result<Self>;

    /// Encode motion frames to discrete tokens
    pub fn encode(&self, frames: ndarray::Array3<f32>) -> Result<Vec<u32>>;

    /// Sample a pose token sequence (denoising loop)
    pub fn sample_pose_tokens(&self, 
        root_cond: &[f32],  // local_root_values
        num_tokens: usize,
        num_steps: usize,
    ) -> Result<Vec<u32>>;

    /// Decode tokens back to motion frames
    pub fn decode(&self, tokens: &[u32], 
        external_cond: ndarray::Array2<f32>,
    ) -> Result<ndarray::Array3<f32>>;

    /// Predict root trajectory from conditions
    pub fn predict_root(&self,
        global_root_values: &ndarray::Array2<f32>,
        local_root_values: &ndarray::Array2<f32>,
        poses: &ndarray::Array2<f32>,
        num_tokens: usize,
    ) -> Result<ndarray::Array3<f32>>;

    /// Full generation: combat action → motion frames + root trajectory
    pub fn generate_motion(&self, action: &str, duration_frames: usize) -> Result<(ndarray::Array3<f32>, ndarray::Array3<f32>)>;
}
```

### Task 3.2: Implement `encode` — VQVAE encoder + quantization

The Rust-side quantization bypasses the ONNX quantizer export complexity. Instead:
1. Run ONNX encoder: input `[1, 241, T]` → output `[1, 256, T/4]`
2. In Rust, compute nearest-neighbour search against codebook: for each of 8 heads, at each time-position, find closest codebook entry.
3. Return indices.

**Codebook extraction:** Load from the trained VQVAE checkpoint and save as a `.bin` file alongside ONNX.

### Task 3.3: Implement `sample_pose_tokens` — iterative denoising

The denoising loop:
1. Start with all-MASK tokens
2. For each step (e.g., 10 steps):
   a. Run pose_backbone ONNX forward
   b. Apply gumbel_sample to get token predictions
   c. Unmask a fraction of tokens (confidence-based scheduling)
3. Return the final token sequence

Inputs to pose_backbone:
- `pose_tokens`: `[1, num_tokens, 8]` — current token state (mask tokens for unknown positions)
- `local_root_values`: `[1, num_tokens*4, 4]` — root motion condition
- `pose_cond`: `[1, num_tokens*4, feat_dim]` — optional pose keyframes
- `has_pose_cond`: `[1, num_tokens*4]` — which frames have conditions
- `num_tokens`: `[1]` scalar

Output: `pose_logits` `[1, num_tokens, 8, nb_code_per_head]`

### Task 3.4: Implement `decode` — VQVAE decoder

1. Dequantize: look up each code index in the codebook → `[1, 256, T/4]` (channels-first for conv decoder)
2. If target_cond or external_cond are needed, prepare them
3. Run ONNX decoder: `[1, 256, T/4]` + conditions → `[1, 329, T]`

Output: local motion frames (local_root + local_joints dimensions)

### Task 3.5: Implement `predict_root` — root trajectory

1. Build condition tensors from start/end frames
2. Run ONNX root_backbone: conditions → `[1, maxTokens*4, 5]`
3. Output global root values (x, z position, heading angle, velocity)

### Task 3.6: Implement `generate_motion` — full pipeline

1. Build action-specific conditioning from combat module
2. Sample pose tokens via iterative denoising
3. Decode to local motion
4. Predict root trajectory
5. Combine local_pose + root → global joint positions (convert to joint transforms)

---

## Phase 4: Connect Combat Actions → MotionBricks Primitives

### Task 4.1: Analyze the combat module

**Objective:** Understand what `combat.rs` outputs and how to map it to token conditioning.

**Files:**
- Read: `src/combat.rs` (currently empty)
- Read: `src/input.rs` (has Strike/Block/Grab)

**Observation:** combat is currently an empty module. We need to design how actions map to motion.

**Motion primitive mapping (proposed):**

Each action (Strike/Block/Grab) becomes:
1. A "motion prompt" — a set of keyframe pose conditions (start pose = current pose, end pose = action-specific)
2. A root trajectory profile (step forward for strike, hold for block, lunge for grab)
3. A token mask schedule (which tokens to keep vs. predict)

The pose backbone receives:
- Known frames: first 4 frames (current pose), last 4 frames (target pose)
- Unknown frames in between → predicted by the transformer

### Task 4.2: Create `combat_action_mapping.rs`

**Files:**
- Create: `src/combat.rs` (replace empty with actual implementation)

Define:
```rust
pub struct CombatAction {
    pub keyframes: Vec<Keyframe>,      // constraint frames
    pub root_trajectory: RootTrajectory,
    pub duration_tokens: usize,        // how many tokens this action spans
    pub denoising_steps: usize,        // iterative refinement steps
}

pub struct Keyframe {
    pub time: f32,                     // seconds from action start
    pub local_pose: [f32; 329],       // full local motion state
}

pub struct RootTrajectory {
    pub start_xz: [f32; 2],
    pub end_xz: [f32; 2],
    pub start_heading: f32,
    pub end_heading: f32,
}
```

Initial motion primitives (hardcoded for shape prototype):
- **Strike:** 8 tokens (32 frames ≈ 1s), forward weight shift, right arm extended
- **Block:** 6 tokens (24 frames), hold position, arms up
- **Grab:** 10 tokens (40 frames), lunge forward, arms extended

---

## Phase 5: Render Animated Mannequin

### Task 5.1: Create mannequin mesh

**Objective:** Load or create a simple humanoid mesh for the arena.

Options (cheapest first):
1. Generate a simple capsule/cylinder-based humanoid procedurally in Rust
2. Download a free CC3+ mannequin GLB and convert it via existing `extract_mesh.py`
3. Generate one via Meshy text-to-3d (prefer t-pose for rigging)

**Recommended (Phase 5a):** Procedural mannequin — build from geometric primitives (torso=box, head=sphere, arms=cylinders). This avoids external asset dependencies for the shape prototype.

```rust
pub struct MannequinMesh {
    pub positions: Vec<[f32; 3]>,
    pub normals: Vec<[f32; 3]>,
    pub uvs: Vec<[f32; 2]>,
    pub indices: Vec<u32>,
    pub joints: Vec<Joint>,            // skeleton hierarchy
    pub skin_weights: Vec<[f32; 4]>,   // per-vertex weight to 4 joints
    pub skin_indices: Vec<[u32; 4]>,   // per-vertex joint indices
}
```

### Task 5.2: Joint transforms from motion data

**Objective:** Convert predicted local motion + root trajectory into per-frame joint matrices.

The VQVAE decoder outputs local motion frames (local_root + local_joints). We need:
1. Convert local representation to global joint positions + rotations
2. Build joint transform matrices for each frame

This is the motion_rep inverse transform — the most math-heavy part.

```rust
pub fn local_to_global_joints(
    local_motion: &ndarray::Array2<f32>,  // [num_frames, 329] 
    root_trajectory: &ndarray::Array2<f32>, // [num_frames, 5]
) -> Vec<[nalgebra::Isometry3<f32>; 34]> // per-frame joint transforms
```

### Task 5.3: Compute shader vertex skinning

**Objective:** Add a wgpu compute shader that transforms mannequin vertices by the joint matrices.

**Files:**
- Create: `src/skinning.wgsl`
- Create: `src/skinning.rs`
- Modify: `src/renderer.rs`

The skinning pipeline:
1. CPU computes joint matrices per frame (from Task 5.2)
2. Write joint matrices to a storage buffer each frame
3. Compute shader reads vertex buffer + skin weights + joint matrices
4. Outputs transformed vertex positions to a second vertex buffer
5. Standard render pass draws from the transformed buffer

```wgsl
struct JointMatrix {
    matrix: mat4x4<f32>,
}

@group(2) @binding(0) var<storage, read> joints: array<JointMatrix, 34>;
@group(2) @binding(1) var<storage, read> skin_weights: array<vec4<f32>>;
@group(2) @binding(2) var<storage, read> skin_indices: array<vec4<u32>>;
```

### Task 5.4: Wire motion pipeline into render loop

**Objective:** On each `RedrawRequested`, advance the animation frame, update joint matrices, dispatch skinning compute, render.

**Files:**
- Modify: `src/main.rs`
- Modify: `src/renderer.rs`

The game loop becomes:
1. Read input → queue combat action
2. Sample motion pipeline → get current animation frame
3. Compute joint transforms
4. Compute MVP from camera + root trajectory
5. Update skinning storage buffer
6. Render skinned mannequin + arena meshes

---

## Phase 6: Verification & Polish

### Task 6.1: Verify end-to-end pipeline

**Step 1:** Run the game and verify:
- Mannequin visible on arena
- Animation plays when action is triggered
- No frame drops (target: 30+ fps)
- No ONNX Runtime errors in console

**Step 2:** Add debug overlay (keyboard toggle, not on by default):
- Show current action, frame number, token state
- Render skeleton overlay (lines connecting joints)

**Step 3:** Profile:
- ONNX inference time per frame
- GPU-compute skinning time
- Overall frame budget

### Task 6.2: Sanity test — known motion playback

**Objective:** Play back a known motion sequence from the MotionBricks dataset to verify the decode path works end-to-end without the denoising loop.

**Step 1:** Pick one sequence from the dataset, extract its tokens via VQVAE encoder.
**Step 2:** Save the token sequence as a `.bin` file.
**Step 3:** Load in Rust, run decoder only → verify output looks like motion.
**Step 4:** If geometry is correct, the denoising/sampling path is the only remaining variable.

---

## Risks, Tradeoffs, and Open Questions

### High Risk
1. **ONNX export of multi-head quantizer** — The `QuantizeEMAResetMultiHead` with 1e8 codes is exotic. The nearest-neighbour lookup (`forward_into_idx`) may fail ONNX tracing. **Mitigation:** Implement quantizer as pure Rust, export only encoder/decoder as ONNX, keep codebook search in Rust land.

2. **Model dimensions may be wrong** — The exact `encoder_state_dim` (241) and `decoder_state_dim` (329) depend on the G1 motion representation. If the motion_rep object isn't correctly instantiated, dimensions will mismatch. **Mitigation:** Extract dimension metadata from the actual checkpoint's state_dict keys.

3. **ONNX Runtime CUDA on AMD iGPU** — The RTX 5090 is the GPU for ONNX inference, but ort must be compiled with CUDA support. **Mitigation:** Use `load-dynamic` feature to link against system ONNX Runtime.

### Medium Risk
4. **Transformer denoising speed** — 16-layer transformer with n_embd=1024 is large. Inference at 30 fps requires sub-33ms per step. With 10 denoising steps, that's 330ms per action. **Mitigation:** Reduce steps, quantize to FP16, or run on GPU.

5. **Skinning shader correctness** — Vertex skinning with 34 joints × 4 weights needs careful implementation. **Mitigation:** Test with identity joints first, then simple rotations, then full motion data.

### Open Questions
- Should we batch multiple denoising steps into one ONNX call?
- What's the fallback when ONNX Runtime isn't available (e.g., macOS)?
- Do we need to convert skeleton output to the game engine's coordinate system?
- Should motion data be pre-baked (compute once at action start) or streamed (compute per frame)?

### Known Scope Boundary
This plan assumes GPU-accelerated ONNX inference. The shape prototype can fall back to pre-baked motion recordings (compute denoising once, cache result, replay) if real-time inference proves too slow initially. Only switch to pre-baking if the ONNX inference path is confirmed as a performance blocker.

---

## Files Likely to Change

```
Create:
  tools/export_motionbricks_onnx.py        (rewrite)
  assets/motionbricks_*.onnx               (generated)
  src/motion.rs                             (new module)
  src/skinning.rs                           (new module)
  src/skinning.wgsl                         (new compute shader)
  
Modify:
  Cargo.toml                                (add ort dependency)
  src/main.rs                               (add modules, wire pipeline)
  src/renderer.rs                           (dual render path: arena + mannequin)
  src/combat.rs                             (action→primitive mapping)

Verify:
  cargo check
  cargo run
  python tools/export_motionbricks_onnx.py  (regenerate on checkpoint change)
```

## Verification Steps (Final)

1. `python tools/export_motionbricks_onnx.py` → all `assets/motionbricks_*.onnx` created
2. `cargo check` → clean compile
3. `cargo run` → window opens, arena visible
4. Press Z/X/C → mannequin plays Strike/Block/Grab animation
5. No console errors, framerate ≥ 30 fps
