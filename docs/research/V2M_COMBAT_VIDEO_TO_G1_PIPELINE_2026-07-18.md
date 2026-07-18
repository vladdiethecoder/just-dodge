# Video-to-3D Combat Motion → MotionBricks G1Skeleton34

**Research date:** 2026-07-18  
**Audience:** Just Dodge offline teacher-corpus pipeline  
**Scope:** real single-camera combat footage, two-fighter footage, game/anime footage, and already recovered motion. Raw source media remains **offline only**; no recovered video-derived clip is a runtime fallback animation.

## Decision in one page

### Recommended production route

1. **Preserve the immutable source and decode a high-FPS master** (60 fps when available; do not initially low-pass or downsample a punch/kick to 30 fps).
2. **Create persistent fighter identities first.** Use GEM-X's bundled YOLOX + ByteTrack as a cheap first pass, but use **4DHumans/HMR2 + PHALP** or a combat-specific tracker review to resolve ID swaps. GEM-X is explicitly one person per forward pass, so run one track per fighter while retaining shared frame times and the original camera model.
3. **Recover each fighter with GEM-X** as the primary local model. It is the current best practical choice here: current code, 77-joint whole-body SOMA output, world-space root trajectory, Apache-2.0 code, and an NVIDIA Open Model checkpoint that supports Blackwell/CUDA 12.6+.
4. **For two-person clips, optimize the paired output rather than filtering actors independently:** start from **SLAHMR** (multi-person/camera joint optimization) or GEM-X tracks, then use **MultiPhys**-style physics/contact refinement. If the capture can be re-shot, use the 2025 **PhysicsPose** multi-camera boxing formulation (2D tracking → weighted triangulation/spline → SMPL IK → multi-person dynamics); it is the appropriate accuracy ceiling for close contact, but its advertised dataset was still “coming soon” on its project page.
5. **Convert SOMA/SMPL to G1 through an IK/FK pipeline, not a joint-name copy.** SOMA-X is the universal parametric-body pivot; the official SOMA Retargeter produces G1 BVH/CSV. Then use the project MotionBricks converter to produce its 34-node world transforms and its canonical motion representation.
6. **Admit only clip segments that pass reprojection, identity, kinematic, temporal, floor/contact, collision, and human-semantic gates.** Preserve real impact peaks; reject estimator artifacts rather than globally over-smoothing them.

### Model choices by input

| Input/need | First-choice model | Why | Important limit |
|---|---|---|---|
| One clear fighter, modern local pipeline | **GEM-X** | 77-joint SOMA whole body; world root; current 2026 install/output/retarget docs; TensorRT/ONNX demo | Per-person inference only; synthetic-to-real gap; no uncertainty output; fighter occlusion can silently fail |
| Two fighters, moving camera, offline reconstruction | **SLAHMR** as paired initializer, then **MultiPhys** | Jointly estimates people and camera; MultiPhys explicitly adds multi-person physics after SLAHMR | Both releases are older dependency stacks; need a compatibility environment/port on RTX 5090 |
| Single fighter, fast camera/world root cross-check | **GVHMR** or **WHAM**; **TRAM** for dynamic camera/background scale | World-grounded global trajectory; contact-aware root refinement (WHAM); gravity-view coordinate recovery (GVHMR); masked DROID-SLAM (TRAM) | Primarily single-person models; use as independent quality/arbitration signals, not a pair solver |
| Fast, close-contact boxing with synchronized 2+ cameras | **PhysicsPose** (Feiz et al., 2025) methodology | Specifically designed for combat: long-term segmentation/IDs, epipolar matching, confidence-weighted triangulation, spline/IK, multi-person dynamics | Public project says dataset “coming soon”; no public turnkey source repository located in this review |
| Stable ID/bbox and SMPL baseline | **4DHumans (HMR2 + PHALP)** | Strong 3D-aware tracking through occlusion; output tracklets include SMPL pose/shape | 2023 stack, Python 3.10; use as tracking/baseline rather than the main high-motion solver |
| Broad web/anime/game footage | GEM-X / GVHMR only after a human-body eligibility gate | Can establish useful body timing/trajectory teachers from clear human-like motion | Non-human anatomy, cuts, squash/stretch, invisible limbs and impossible timing require quarantine—not “correction” into false ground truth |

## What each model actually returns

### GEM-X — primary recommendation

NVIDIA's public GEM-X release is the strongest current locally runnable starting point for this project:

- Model: 12-layer temporal Transformer, 120-frame training context and sliding-window inference.
- Input contract: RGB frames, a **per-frame person box** `(T, 4)` and camera intrinsics; the demo estimates them when omitted.
- Output: per-frame SOMA pose `(T, 77, 3)` axis-angle, global root orientation `(T, 3)`, world root translation `(T, 3)` meters, identity coefficients and body scale parameters. Its demo saves 77-point 2D observations, boxes and a PyTorch `hpe_results.pt` prediction.
- Tracking: default demo preprocessing is YOLOX + ByteTrack. This is useful but not enough evidence of fighter identity during clinches/crossovers. The demo's `bbx.pt` is a single `(T,4)` series; use a stable external track per fighter for paired combat.
- Licensing: code is Apache-2.0; checkpoint is the NVIDIA Open Model License. The model card says CUDA 12.1+ and Blackwell support. Read the model license before promotion.
- Known hard limitations from NVIDIA's model card: one person per forward pass, no confidence/uncertainty, synthetic-to-real domain gap, world root depends on SLAM, and a fixed temporal context that can create boundary artifacts.

**Assessment:** use GEM-X as the first estimator for every admissible single-fighter track, but make its 2D reprojection/track consistency a gate, not an assumption of truth. For a fixed broadcast camera, run `--static_cam` to avoid invented camera motion. For a moving camera, retain the estimated camera solution and cross-check root with GVHMR/WHAM/TRAM rather than averaging unrelated world frames.

### 4DHumans / HMR2 — best role is identification and a second opinion

4DHumans (ICCV 2023) uses HMR2, a ViT/cross-attention SMPL regressor, as the PHALP tracker backbone. Its release runs `track.py` on a video and writes a rendered tracklet video plus a `.pkl` with 3D pose/shape. It is valuable because it tracks in 3D and was designed to preserve identities through occlusions, but it is not a purpose-trained combat/contact estimator. Use it to:

- establish `fighter_A`/`fighter_B` identity segments,
- export/review bboxes and ID breaks,
- compare camera-relative SMPL pose against GEM-X, and
- quarantine uncertain frames around swaps/occlusions.

Do **not** assume its older Python 3.10/PyTorch-era environment will install unchanged into the project Python 3.14 environment or current Blackwell wheel stack.

### SLAHMR — paired, global, offline optimizer

SLAHMR (CVPR 2023) combines PHALP/4DHumans tracks, ViTPose, DROID-SLAM, HuMoR and SMPL over staged optimization. Its custom-video config accepts `track_ids: "all"` and outputs an `.npz` for all optimized people plus camera intrinsics/extrinsics. That makes it the best open baseline for **pair-preserving** offline recovery from a single video. Configure the decode FPS intentionally; the supplied config defaults to 25 fps, which is too coarse for a punch-impact teacher.

Use it as a pair initialization and camera solution; do not expect it alone to solve a clinch, wrestling hold, or collision/contact geometry.

### WHAM, GVHMR, TRAM and current temporal methods

- **WHAM (CVPR 2024):** lifts 2D temporal motion plus image features to SMPL and uses SLAM angular velocity plus predicted foot contacts for a global trajectory refiner. It offers `--run_smplify` for temporal SMPLify refinement and `--estimate_local_only` to skip SLAM. Good root/foot-contact cross-check.
- **GVHMR (SIGGRAPH Asia 2024; TPAMI 2026):** gravity-view coordinates avoid autoregressive global-drift accumulation. The current release's `gvhmr_siga24_release.ckpt` works locally and supports a static-camera skip option. Good fast single-person world-root cross-check.
- **TRAM (2024, updated 2025):** masked DROID-SLAM detects/tracks people while estimating camera, then VIMO estimates humans. Good when the athlete dominates a moving-camera shot and background scale can be recovered.
- **HTD-Refine (CVPR 2026):** research direction to watch: explicitly aligns high-order temporal dynamics (velocity and acceleration), addressing the common trade-off between smooth and dynamically dead reconstructions. At research date a verified public code repository was not located, so it is not a baseline dependency.

These are **not** replacements for a paired-contact solver. Use two independent world-root estimates only after aligning their coordinate frames by a robust similarity transform on non-contact, high-confidence frames.

### MultiPhys and PhysicsPose — physical plausibility after kinematics

**MultiPhys** (CVPR 2024) starts from SLAHMR motion/camera estimates and uses MuJoCo, imitation and collision/contact-aware refinement to correct multi-person motion. It supports CHI3D, Hi4D and ExPI evaluation and exposes pose, physics and SDF penetration metrics. It is the most directly reusable open reference for this project's post-estimation pair stage.

**PhysicsPose** (Feiz et al., 2025) is the combat-specialized reference: multi-frame/multi-view identities using long-term segmentation and epipolar geometry, confidence-weighted triangulation, spline smoothing, SMPL kinematic optimization, then multi-person iLQR dynamics. It reports >20 minutes of intense elite-boxer sparring plus optical-ground-truth interaction sequences, but the project page currently labels its dataset “Coming Soon.” Treat it as a method and benchmark lead, not an available corpus or a claimed installed tool.

## Parametric-body conversion to Just Dodge's G1Skeleton34

### Body-model facts

- **SMPL** is a skinned body model with a 24-joint body kinematic convention; common video outputs are `global_orient`, `body_pose`, ten `betas`, and translation.
- **SMPL-H** adds articulated hands; **SMPL-X** adds articulated hands and expressive face. SMPL/SMPL-X model files remain separately registration/licensed even when the calling code is open source.
- **SOMA/SOMA-X** (NVIDIA, 2026) is the recommended interchange layer. It uses a canonical rig/topology while supporting SMPL, SMPL-X, MHR, Anny, SOMA shape, and GarmentMeasurements identity backends. Its conversion tools can export SOMA axis-angle poses and root translation from SMPL; analytical inversion is fast, while optional autograd FK refinement is the accuracy mode.

### The required conversion chain

```text
GEM-X SOMA77 or SLAHMR/4DHumans SMPL
  → (if SMPL) SOMA-X SMPL→SOMA pose inversion
  → SOMA FK + conversion quality report
  → official SOMA Retargeter IK (human proportions → Unitree G1)
  → G1 BVH + G1 CSV/qpos
  → Just Dodge MotionBricks converter FK
  → world joint positions + global rotations for G1Skeleton34
  → project motion_rep() → normalized training features
```

Do **not** map `SMPL pelvis → G1 pelvis`, `SMPL elbow → G1 elbow`, etc. by name and call the result G1 motion. SMPL has ball joints and human proportions; G1 has hinge/joint-limit chains. The retarget needs weighted end-effector, center-of-mass/root, orientation, joint-limit, and planted-foot objectives, then FK verification.

### Canonical G1Skeleton34 order

The official MotionBricks source defines the 34 nodes as:

```text
 0 pelvis_skel
 1.. 7 left hip pitch/roll/yaw, knee, ankle pitch/roll, left_toe_base
 8..14 right hip pitch/roll/yaw, knee, ankle pitch/roll, right_toe_base
15..17 waist yaw/roll/pitch
18..25 left shoulder pitch/roll/yaw, elbow, wrist roll/pitch/yaw, hand roll
26..33 right shoulder pitch/roll/yaw, elbow, wrist roll/pitch/yaw, hand roll
```

The MotionBricks paper describes this as the G1 floating pelvis + physical G1 joint structure plus four end-effectors, totaling 34 skeleton nodes. The parent array in `src/motion.rs` agrees with this official order. The required output is therefore **not** a 24- or 55-joint SMPL array.

### Existing project contract to use

The repository already contains the correct project-side bridge:

- `src/motion.rs`: parses raw runtime frames as **413 float32 values**: root xyz (3), heading (2), root-relative joint positions (33×3), global 6D rotations (34×6), local velocity (34×3), foot contacts (4).
- `tools/qa/build_motionbricks_combat_dataset.py`: calls the installed `motionbricks_service` converter to transform a G1 `qpos` sequence into `posed_joints [B,T,34,3]`, `global_joint_rots [B,T,34,3,3]`, contact flags, then calls `motion_rep()`. It asserts a **normalized `(T,414)`** training feature representation.

That apparent 413/414 distinction is real: use the repository's Python `motion_rep()` producer for training data and the documented 413-float runtime serializer for runtime assets. Do not hand-pack either format from a guessed layout.

## Concrete local pipeline

### 0. Isolated environment and source intake

The live project environment is Python **3.14.6**, PyTorch **2.11.0+cu130**, and an RTX 5090. GEM-X officially requires Python 3.12+ and supports CUDA 12.6/13.0 wheels; use an isolated Python 3.12 environment instead of contaminating the project environment. The workstation has `uv 0.9.28`, Git LFS 3.7.1, FFmpeg 8.1.2, 32 GB RTX 5090 VRAM, and NVIDIA driver 595.80.

```bash
cd "/run/media/vdubrov/NVMe-Storage1/Just Dodge"
mkdir -p third_party/v2m inputs/v2m/{source,frames,manifests,raw,curated,rejected}

# Keep the immutable original and capture its checksum/provenance externally.
# Decode at source FPS or 60 fps for the estimator master; do not discard impact detail yet.
ffmpeg -i inputs/v2m/source/CLIP.mp4 -map 0:v:0 -vsync 0 \
  inputs/v2m/frames/CLIP/%08d.png

cd third_party/v2m
git clone --recursive https://github.com/NVlabs/GEM-X.git
cd GEM-X
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
uv pip install -e third_party/soma
(cd third_party/soma && git lfs pull)
bash scripts/install_env.sh
huggingface-cli download nvidia/GEM-X gem_soma.ckpt --local-dir inputs/pretrained
# Optional official G1 retargeting stage:
uv pip install -e third_party/soma-retargeter
```

If a compiled third-party dependency rejects CUDA 13.0, recreate this *isolated* environment using GEM-X's documented `cu126` index; the installed driver is newer than the CUDA 12.6 runtime requirement. Do not downgrade the project runtime to accommodate an estimator.

For headless renders, GEM-X documents `PYOPENGL_PLATFORM=egl EGL_PLATFORM=surfaceless` as the workaround.

### 1. Track identities and choose segments

```bash
# First-pass, one-fighter GEM-X video (auto checkpoint download also works).
python scripts/demo/demo_soma.py \
  --video ../../../inputs/v2m/source/CLIP.mp4 \
  --output_root ../../../inputs/v2m/raw/gem \
  --ckpt inputs/pretrained/gem_soma.ckpt \
  --verbose
```

Expected GEM-X files for visual QA:

```text
raw/gem/CLIP/
  0_kp2d77_overlay.mp4
  CLIP_1_incam.mp4
  CLIP_2_global.mp4
  preprocess/bbx.pt                 # one (T,4) bbox series
  preprocess/vitpose.pt             # (T,77,3): x,y,confidence
  preprocess/hpe_results.pt         # full 3D SOMA prediction
```

For **two fighters**, do this before full 3D recovery:

```bash
# Compatibility environment; tracker has its own older dependencies.
git clone https://github.com/shubham-goel/4D-Humans.git
cd 4D-Humans
conda env create -f environment.yml
conda activate 4D-humans
pip install git+https://github.com/brjathu/PHALP.git
python track.py video.source="/absolute/path/to/CLIP.mp4"
```

Manually inspect every ID swap, overlap, full occlusion and shot cut in the tracking overlay. Split the clip at unresolved events. Feed each **stable** per-frame fighter box to GEM-X's Python input contract while preserving original full-frame intrinsics; do not independently crop and then pretend the crops share a world camera. GEM-X's public demo does not expose a documented multi-ID CLI, so this requires a small adapter around its documented `(T,4)` box input—not an invented CLI flag.

Optional pair initializer:

```bash
# SLAHMR has its own legacy compatibility environment. Its data/video.yaml defaults
# to 25 fps; change frame_opts.fps and root/seq before recovery.
git clone --recursive https://github.com/vye16/slahmr.git
cd slahmr
source install_conda.sh
pip install phalp[all]@git+https://github.com/brjathu/PHALP.git
pip install -e .
pip install -v -e third-party/ViTPose
(cd third-party/DROID-SLAM && python setup.py install)
./download_models.sh
python run_opt.py data=video run_opt=True run_vis=True
```

SLAHMR `motion_chunks/*.npz` carries all optimized people's SMPL parameters and camera intrinsics/extrinsics. It is a pair-stage input, not a final G1 corpus item.

### 2. Convert model output to a common SOMA record

For GEM-X, retain SOMA directly. For SMPL/SMPL-X sources, install SOMA-X in the same or a dedicated Python 3.12 environment and register/download the separately licensed SMPL files:

```bash
uv pip install "py-soma-x[smpl]"
uv pip install --no-build-isolation chumpy
# SMPL_NEUTRAL.pkl / SMPLX_NEUTRAL.npz are separately licensed; do not commit them.
python -m tools.smpl2soma --output-npz out/CLIP_actorA_soma.npz \
  --body-iters 2 --full-iters 1 --autograd-iters 10
```

Expected common record (`.npz`; one file per actor, equal frame timestamps across a pair):

```text
poses              float32 [T,77,3]    SOMA local axis-angle
root_translation   float32 [T,3]       meters, chosen world frame
joint_names        list[str]
identity_coeffs    float32 [T,K] or [K]
scale_params       float32 [T,K] or [K]
kp2d_xyc           float32 [T,77,3]   retained observation evidence
camera             float32 [...]       original camera/SLAM pose and intrinsics
```

SOMA-X's converter documents `per_vertex_error` on its output. Preserve that, conversion version, checkpoint hash and source model/version in the clip manifest.

### 3. Retarget, FK and feature export

```bash
# From the SOMA Retargeter repository after configuring import_folder/export_folder
# in assets/default_bvh_to_csv_converter_config.json:
python app/bvh_to_csv_converter.py \
  --config assets/default_bvh_to_csv_converter_config.json --viewer null
```

Expected official intermediate files:

```text
retarget/CLIP_actorA.bvh
retarget/CLIP_actorA.csv       # robot-playable G1 qpos/joint-angle data
```

Then invoke the **existing Just Dodge** `motionbricks_service` converter, following the exact input reshuffle in `tools/qa/build_motionbricks_combat_dataset.py`, to generate:

```text
canonical/CLIP_actorA.g1.npz
  posed_joints       float32 [T,34,3]       world-space meters
  global_joint_rots  float32 [T,34,3,3]     SO(3)
  foot_contacts      float32 [T,4]
  qpos               float32 [T,36]         project converter input
features/CLIP_actorA.npy
  float32 [T,414]                           normalized MotionBricks training feature
runtime/CLIP_actorA.413.f32                 only if/when runtime serialization is requested
```

For paired clips, retain `actorA` and `actorB` under one `pair_id`, use the same `T`, FPS and world origin, and store cross-person contact/collision annotations. Never turn two fighters into unrelated single-person shards before interaction-conditioned training.

## Filtering that preserves fast combat

### Gate order

1. **Source/identity gate:** known provenance/rights state, no unresolved ID swap, no shot-boundary crossing, synchronized pair timestamps.
2. **Observation gate:** render the recovered mesh/joints onto the original frames. Calculate per-joint confidence and 2D reprojection residual; reject low-confidence/large-residual spans rather than smoothing through missing limbs.
3. **Kinematic gate:** finite tensors; valid SO(3); FK recomputes stored joints; stable subject-specific bone lengths; G1 joint limits respected after IK; no quaternion sign flips/axis-angle wraps.
4. **Temporal gate:** assess velocity and acceleration *relative to the clip/action distribution*. Use confidence-weighted robust outlier detection (median/MAD on derivatives) and only repair isolated estimator spikes. Do not reject the coherent acceleration peak of a punch, kick, throw or landing merely because it is high.
5. **Floor/foot gate:** infer contact from floor distance, foot velocity and temporal duration; split into contiguous contact runs and measure drift **within a run**, never across a legitimate step. Root scale/ground must be solved before evaluating foot slide.
6. **Pair-contact gate:** detect allowed contact candidates (hand/forearm/shoulder/shin to observed opponent region) and reject unexplained inter-person mesh penetration. Do not impose a blanket no-collision objective: a clinch is supposed to contact. Optimize non-contact penetration while preserving 2D-supported contact candidates and their timing.
7. **Semantic gate:** human reviewer checks stance, weight transfer, hip drive, punch extension, guard/recovery, kick support leg and apparent opponent relation. Mechanical validity alone does not make a martial motion useful.

### Recommended repair policy

- Work in world **positions plus local rotations**. Convert axis-angle to a sign-continuous quaternion/6D representation before smoothing, then re-project rotations to SO(3).
- Fill only short, confidence-supported gaps by FK/IK with endpoint and 2D constraints. Long full-body occlusions should split/quarantine a sequence.
- Use a short adaptive Savitzky–Golay/One-Euro/Kalman smoother as a baseline, or SmoothNet only after testing it on held-out combat footage. SmoothNet is a useful plug-in temporal denoiser, but its released checkpoints are trained on non-combat datasets and its repository's non-commercial research terms make it unsuitable as an unquestioned commercial dependency.
- Run a final constrained trajectory solve: weighted 2D reprojection + bone-length + joint-limit + floor/foot + root-velocity + collision/contact terms. Weight 2D observations by their detector confidence and set contact terms only when image evidence supports contact.
- Keep `raw`, `repaired`, `rejected_reason`, and all metrics. Never overwrite raw pose with a “smoothed” result.

### Minimum per-clip report

```json
{
  "schema": "just-dodge-v2m-quality-v1",
  "pair_id": "sourcehash:shot:tracks-A-B",
  "fps": 60,
  "actors": ["fighter_A", "fighter_B"],
  "model": {"name": "GEM-X", "checkpoint_sha256": "..."},
  "quality": {
    "finite": true,
    "so3_valid": true,
    "fk_max_error_m": 0.0,
    "kp2d_reprojection": {"median_px": 0.0, "p95_px": 0.0},
    "identity_breaks": [],
    "contact_runs": [],
    "foot_drift_per_run_m": [],
    "unexpected_penetration_frames": [],
    "joint_limit_violations": []
  },
  "decision": "curated|rejected|needs_human_review"
}
```

The zeroes above are schema placeholders, not acceptance values. Establish numerical thresholds with a labeled calibration set (Kyokushin/Harmony4D/project-owned capture) and keep thresholds fixed across the resulting corpus.

## Existing or usable combat-motion data

| Data | What is actually available | Use status for this pipeline |
|---|---|---|
| **Harmony4D** (NeurIPS 2024) | 208 synchronized >20-camera interaction sequences; 1.66M images / 3.32M instances; wrestling, grappling, MMA, karate, fencing; 2D/3D pose and SMPL mesh annotations | Best public two-person interaction teacher. Project survey records MIT dataset-card terms; preserve dataset revision/license receipt. It has contact/occlusion but is not raw optical BVH. |
| **Kyokushin Karate** | 37 athletes; 1,411 Vicon C3D recordings / 3,229 strikes/kicks; includes attacker/defender opponent recordings | CC0 source in existing project survey. Best license-clean striking/spacing calibration set; reconstruct a skeleton from markers. Not grappling. |
| **CMU direct mocap** | ASF/AMC/C3D boxing, punch/strike, swordplay; limited paired arm-wrestling | Project survey finds permissive direct-use terms subject to no raw-data resale. Good single fighter and limited pair baseline; not real MMA/BJJ. |
| **KungfuAthleteBot** | 992 Wushu samples (fist/sword/staff), GVHMR/SMPL-H predictions and pre-cleaned G1 qpos | Apache-2.0 card. Useful as already-converted high-dynamic G1 augmentation, but provenance is reconstructed video—not optical mocap—and it lacks partner contact. |
| **PhysicsPose boxing** | >20 min elite boxing and optical interaction validation described in paper | Most relevant new boxing benchmark, but project page says dataset coming soon: not downloadable corpus today. |
| **MMA Fighter Pose Estimation Dataset** (Mendeley, 2026) | 5,109 still images from 20 UFC stand-up fights; 17 COCO 2D keypoints/fighter; model-generated labels | Useful for detector/2D QA only. Not 3D motion, excludes grappling/cage clinch, and is CC BY-NC-SA—do not put in commercial training. |
| **BONES-SEED** | 142,220 / ~288h SOMA and G1 motions, public metadata includes 20 martial-arts clips | Technically ideal representation, but project survey records a custom training restriction against substitutive generative motion. Do not use as a commercial motion-teacher corpus without explicit written license. |
| **MotionMillion** | 2,000+ hours web-recovered motion, says 23.7% martial arts; includes `CombatMotion_seperate` packaging | CC BY-NC-SA 4.0; research/non-commercial only. Not commercial corpus. |
| **AMASS / Motion-X / Hi4D** | Broad SMPL/SMPL-X and interaction baselines | Useful for research/pretraining only after source-level licensing audit; not a verified UFC/MMA combat corpus. Hi4D is contact interaction but not combat-specific. |

## Source links

Primary implementation/model sources:

1. [GEM-X code](https://github.com/NVlabs/GEM-X), [installation](https://raw.githubusercontent.com/NVlabs/GEM-X/main/docs/INSTALL.md), [demo/output contract](https://raw.githubusercontent.com/NVlabs/GEM-X/main/docs/DEMO.md), [model card/checkpoint](https://huggingface.co/nvidia/GEM-X), Li et al., *GENMO*, ICCV 2025.
2. [SOMA-X](https://github.com/NVlabs/SOMA-X) and [SOMA Retargeter](https://github.com/NVIDIA/soma-retargeter), Saito et al., 2026.
3. [4DHumans](https://github.com/shubham-goel/4D-Humans), Goel et al., ICCV 2023.
4. [SLAHMR](https://github.com/vye16/slahmr), Ye et al., CVPR 2023.
5. [WHAM](https://github.com/yohanshin/WHAM), Shin et al., CVPR 2024; [GVHMR](https://github.com/zju3dv/GVHMR), Shen et al., SIGGRAPH Asia 2024/TPAMI 2026; [TRAM](https://github.com/yufu-wang/tram), Wang et al., 2024.
6. [MultiPhys](https://github.com/nicolasugrinovic/multiphys), Ugrinovic et al., CVPR 2024; [PhysicsPose project](https://hosseinfeiz.github.io/physpose/), Feiz et al., 2025.
7. [MotionBricks G1 skeleton](https://raw.githubusercontent.com/NVlabs/GR00T-WholeBodyControl/main/motionbricks/motionbricks/motionlib/core/skeletons/g1.py) and [MotionBricks setup/representation](https://raw.githubusercontent.com/NVlabs/GR00T-WholeBodyControl/main/motionbricks/README.md).
8. [Harmony4D](https://jyuntins.github.io/harmony4d/), Khirodkar et al., NeurIPS 2024; [MMA 2D pose data](https://data.mendeley.com/datasets/c456bnk8bm/2); [MotionMillion card](https://huggingface.co/datasets/InternRobotics/MotionMillion).

Project-specific grounding: `docs/reports/COMBAT_MOCAP_DATASET_SURVEY_2026-07-17.md`, `src/motion.rs`, and `tools/qa/build_motionbricks_combat_dataset.py`.
