# Visual QA Report: CMU Strike / Idle Primitives

**Run:** `qa_runs/visual_primitives_20260709_214311`  
**Verifier:** `tools/qa/visual_verify_primitives.py` + `tools/qa/compare_source_retarget.py` + `cargo run --bin shot`  
**Verdict:** FAIL — primitives are syntactically valid but visually/semantically broken.

---

## 1. What was tested

- `cargo run --bin shot` → bind-pose screenshots (`/tmp/jd_bind_*.png`).
- Python MotionBricks service `generate_clip('Strike','Longsword','Top', seed=1)`.
- Python MotionBricks service `generate_clip('Idle','Longsword','Top', seed=1)`.
- Raw CMU source (`14_01.bvh`, `140_06.bvh`) vs. retargeted G1 output.

---

## 2. Positive signals

- The Rust wgpu renderer boots headlessly and produces recognizable bind-pose mannequins.
- `assets/data/primitives.ron` no longer contains `TEST_FIXTURE_DO_NOT_SHIP` markers.
- `cargo test --test motion_service_integration` passes.
- The Python service successfully decodes conditioned clips of 32 frames each from the new primitives.
- Raw CMU source clips are healthy standing/boxing motion (hips ~16–17 cm high in source units, poses are human-readable).

---

## 3. Critical blockers

### 3.1 Retargeting produces broken G1 poses

`tools/qa/compare_source_retarget.py` compares raw CMU `140_06` frame 0 with the retargeted G1 output:

- **Raw CMU:** normal standing human, arms slightly out, legs straight.
- **Retargeted G1:** legs crossed into an X, arms raised above head, overall twisted silhouette.

Root cause (preliminary): `tools/retarget_to_g1.py` copies CMU world-space rotation matrices directly onto the G1 skeleton without reconciling the two skeletons' local joint-frame conventions. G1Skeleton34 has many intermediate roll/pitch/yaw joints (e.g. `left_hip_pitch_skel`, `left_hip_roll_skel`, `left_hip_yaw_skel`) whose offsets and local frames differ from CMU's simple `LeftUpLeg -> LeftLeg -> LeftFoot` chain. Forcing world rotations onto that structure produces incoherent local rotations and the crossed-limb artifacts visible in the screenshots.

Impact: the generated `Strike` and `Idle` clips inherit these broken poses. They are not usable as production combat animation.

### 3.2 Generated clips have runaway root translation

| action | frames | root path (m) | max joint velocity (m/frame) |
|--------|--------|---------------|------------------------------|
| Strike | 32     | 17.45         | 1.36                         |
| Idle   | 32     | 11.94         | 1.29                         |

A 1-second idle that slides the character ~12 meters, or a strike that slides ~17 meters, is far outside acceptable bounds for a foot-planted melee exchange. The root trajectory should be sub-meter for an idle and typically <2 m for a committed strike.

This drift likely stems from the same retargeting issue: when the limb rotations are wrong, the MotionBrains model compensates with large global root motion during generation.

### 3.3 Semantic mismatch of selected source clips

- `Strike` primitive is sourced from CMU `14_01`, which is a **boxing** clip. A boxing punch is not a longsword top strike; weapon/timing semantics differ.
- `Idle` primitive is sourced from CMU `140_06`, labeled "Idle". The raw pose is standing, but the retargeted output is twisted.

Even if retargeting is fixed, the action library should source motions that match the weapon/stance labels.

### 3.4 Rust ONNX motion pipeline hangs on model load

`cargo run --bin mb_probe` stalls indefinitely at `MotionPipeline::new (loads 5 ONNX models)`. After 300 s it had not completed encoder load. The Python service path works, so the ONNX models themselves are present, but the Rust `ort` inference path is non-functional. Until this is fixed, the game cannot drive MotionBricks from Rust/wgpu.

---

## 4. Screenshots / artifacts

- `strike_keyframes.png` — generated Strike stick figures across 5 keyframes.
- `idle_keyframes.png` — generated Idle stick figures across 5 keyframes.
- `source_vs_retarget.png` — raw CMU `140_06` vs. retargeted G1 frame 0.
- `report.json` — quantitative metrics.
- `/tmp/jd_bind_*.png` — bind-pose renderer output.

---

## 5. Recommended next steps

1. **Fix `tools/retarget_to_g1.py`**: rewrite the rotation mapping to operate in local parent-relative space for both skeletons, not world-space matrix copy. For each mapped joint, compute the CMU local rotation and apply it to the corresponding G1 joint; leave intermediate G1 detail joints at identity or derive them from the mapped parent's chain.
2. **Add a retargeting validation gate**: before any primitive is encoded, render raw source vs. retargeted side-by-side and require a human-readable match.
3. **Select semantically appropriate CMU clips**: longsword top strike should come from a weapon/sword motion set, not boxing; idle should be a calm standing loop, not a T-pose or calibration frame.
4. **Fix or bypass the Rust ONNX hang**: determine whether `ort` is waiting on CUDA initialization, external data loading, or a provider mismatch. The Python path proves the models are valid, so this is an execution-provider/configuration issue.
5. **Re-run this visual QA** after the above fixes and require root path < 1 m for idle and < 3 m for strike before accepting the primitives.

---

## 6. Summary

The placeholder primitives have been replaced with CMU-derived data, but the retargeting pipeline is not production-ready. The generated animation is visually broken and the Rust inference path is blocked. **Do not claim completeness** for this milestone until retargeting, source-clip selection, and the Rust ONNX loader are fixed and re-verified.
