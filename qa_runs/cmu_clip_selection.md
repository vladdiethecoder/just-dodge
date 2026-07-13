# CMU MoCap Clip Selection Report

Date: 2026-07-09
Dataset: `/tmp/cmu-mocap/data/` (CMU Graphics Lab Motion Capture Database, BVH conversion by Bruce Hahne / cgspeed.com)

## Objective
Find better source clips for the `Strike/Longsword/Top` and `Idle` primitives than the previous selections (`14_01` boxing and `140_06` idle).

## Method
1. Consulted the CMU mocap index to identify semantically relevant subjects:
   - Subject 2: "various expressions and human behaviors" — includes `02_07`, `02_08`, `02_09` labeled **swordplay**.
   - Subject 113: "various everyday behaviors" — includes `113_21` labeled **Standing Still**.
2. Parsed each candidate BVH header and sampled frames using `tools/retarget_to_g1.py` and `tools/qa/inspect_bvh.py`.
3. Rendered front/side stick-figure keyframes for visual QA.
4. Computed motion statistics (root height stability, hand range, foot displacement) to avoid T-poses, calibration frames, and walking.

## Selected Clips

### Strike / Longsword / Top
- **Clip:** `02_07.bvh` (Subject 2, trial 07)
- **Index description:** swordplay
- **Duration / frames:** 18.77 s / 2252 frames @ 120 Hz
- **Why selected:**
  - Actual swordplay, not boxing — semantically correct for a longsword strike.
  - Longest swordplay take in Subject 2; actor remains relatively planted while producing clear overhead/overhand striking arcs.
  - Hand height range ~20 units, with distinct high-hand poses suitable for a top-strike primitive.
- **Alternatives considered:** `02_08` (more footwork), `02_09` (more acrobatic/spinning). Both are usable swordplay but less stable for a single top-strike reference.
- **Compromise note:** CMU does not contain true longsword motion. `02_07` is a one-handed/rapier-style swordplay take. It is the closest semantic match in the dataset; the retargeted motion reads as an overhead weapon swing and is far preferable to a boxing punch.

### Idle
- **Clip:** `113_21.bvh` (Subject 113, trial 21)
- **Index description:** Standing Still
- **Duration / frames:** 11.40 s / 1368 frames @ 120 Hz
- **Why selected:**
  - Explicitly labeled "Standing Still" and visually matches calm, breathing-in-place idle.
  - Root height very stable (15.70–16.30), low foot displacement, minimal arm motion.
  - Avoids T-poses (e.g., `87_02`, `93_01`, `140_05`) and wandering/idling-with-movement clips (e.g., `140_06`, `140_07`, `77_02`).
- **Alternatives considered:** `140_06` (previous selection, too much wandering/arm swing), `140_07` (better but still shifts weight noticeably), `77_02` (labeled "standing" but contains large arm calisthenics).

## Pipeline Outputs
- Raw BVH copied to `data/cmu/02_07.bvh` and `data/cmu/113_21.bvh`.
- Retargeted G1 clips: `data/cmu/02_07_retargeted.npy`, `data/cmu/113_21_retargeted.npy`.
- MotionBricks features: `data/cmu/02_07_features.npy`, `data/cmu/113_21_features.npy`.
- Primitive library `assets/data/primitives.ron` updated:
  - `Strike/Longsword/Top` now uses `source_id: "cmu_02_07"` (peak frame 336 in 30 Hz features).
  - `Idle/Longsword/Top` now uses `source_id: "cmu_113_21"` (peak frame 250 in 30 Hz features).
- Manifest updated: `tools/data/mocap_manifest.json`.

## Visual QA Keyframes
- `qa_runs/cmu_clip_selection_20260709/strike_02_07_keyframes.png`
- `qa_runs/cmu_clip_selection_20260709/idle_113_21_keyframes.png`

Each image shows front and side views at multiple sample frames (frame 1 is the BVH T-pose added by the cgspeed conversion; subsequent frames are the actual motion).

## Verdict
`02_07` and `113_21` are substantially better semantic matches for `Strike/Longsword/Top` and `Idle` than the previous boxing and wandering-idle selections. The manifest, primitive library, and QA artifacts have been updated accordingly.
