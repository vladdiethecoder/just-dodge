# Just Dodge — Combat Motion Training Architecture
# Designed: 2026-07-18
# Status: ARCHITECTURE — ready to implement when data lands

## Purpose
Complete training system for physics-based emergent combat motion.
Every step measurable, checkable, testable. No wasted cycles.

## Design Principles
1. DATA-FIRST: never train until corpus passes quality gates
2. MEASURE EVERYTHING: every training run emits metrics, curves, distributions
3. FALSIFY BEFORE COMMIT: every checkpoint passes ablation + held-out + contact sheet
4. INCREMENTAL: add one action family at a time, verify before next
5. REPRODUCIBLE: seeds, configs, data hashes, environment pinned per run

## Pipeline Stages

### Stage 0: Data Ingestion and Quality Gate
Every raw motion source (CMU, KungfuAthleteBot, Harmony4D, V2M, Kyokushin)
passes through a unified ingestion gate BEFORE entering the training corpus.

Gates:
  - skeleton_finite: all joint positions finite, no NaN/Inf
  - skeleton_valid: 34 joints, Y-up convention, root at pelvis
  - human_scale: root Y in [0.3, 1.2]m, total height in [0.8, 2.2]m
  - motion_alive: frame-to-frame displacement > 0.001m (not static)
  - no_collapse: max joint-to-joint distance < 3.0m (no explosion)
  - no_teleport: max per-frame root displacement < 0.5m
  - fps_normalized: resampled to 60fps
  - provenance: source ID, license, hash recorded

### Stage 1: Segmentation and Labeling
Each clip is segmented into action-labeled windows (120 frames = 2s).

Labels (per MOTION_VOCABULARY.json, 438 types):
  - Auto-classify by motion pattern (hand reach, foot extension, root travel)
  - Manual review for ambiguous segments (ForgeLens contact sheet)
  - Each segment gets: action_label, contact_frame, peak_reach, intensity_score

Quality gate per segment:
  - peak_reach in valid range for the action type
  - root travel plausible (not teleport)
  - grip span plausible for grab-type actions
  - foot contact runs are contiguous (slide measured within runs only)

### Stage 2: Corpus Splitting (Leakage-Resistant)
Split by SOURCE IDENTITY (never by segment within a source):
  - Train: 70% of source identities (subjects/clips)
  - Held-out: 20% of source identities (never seen in training)
  - Eval: 10% of source identities (for final metrics)

Verification:
  - No subject appears in both train and held-out
  - No derivative window of a held-out sequence in training
  - Split hash recorded in receipt

### Stage 3: Conditioner Training (per action family)
Each action family (grab, strike, kick, block, etc.) gets its own conditioner.

Architecture (Option B — sequence model):
  - Temporal CNN with concatenation-based conditioning (v6 proven)
  - Condition vector: target contact pos + reach axis + phase + cell ID
  - Dual backbone: separate pose (34x3) and root (3) streams
  - Dropout 0.3, CosineAnnealing scheduler
  - Early stopping: STOP if loss < 1e-4 for 100 consecutive steps (not immediate)

Training protocol:
  - Batch size: min(16, len(train_segments))
  - Learning rate: 3e-4 with cosine decay
  - Max steps: 50000 (but early stop will trigger much sooner with enough data)
  - Seed: fixed per run (20260718)
  - Device: CUDA (RTX 5090)
  - Precision: fp32 (not mixed — reproducibility over speed)

Per-run outputs:
  - checkpoint (.pt)
  - train_report.json (loss curves, held-out metrics, ablation)
  - contact_sheet_*.png (visual verification for all held-out segments)
  - receipt.json (commands, config, hashes, verdict)

### Stage 4: Evaluation (Exhaustive, No Outliers)
Gate: MEDIAN held-out hand-surface error <= 15mm at GRAB_REACH_MM=650

Metrics (all computed on held-out, never train):
  - hand_surface_err_mm: abs(peak_reach - 0.650) * 1000
  - fullbody_err_mm: mean joint position error
  - grip_span_err_mm: for grab-type actions
  - foot_slide_mm: for locomotion actions
  - ablation_delta_mm: median(cond_err) - median(abl_err), must be positive

Distribution requirements (NOT best-case):
  - median pass rate across held-out >= 50% (not 1%)
  - P75 error <= 2x gate threshold
  - No SUSPICIOUS_ZERO (0.0mm = masking)
  - Ablation inversion rate < 30%

Contact sheet verification:
  - Every held-out segment rendered (GT / conditioned / ablated)
  - Multi-view: front, side, top-down
  - Reach-over-time plots
  - Failure cases highlighted and catalogued

### Stage 5: Physics Integration Test
The trained conditioner generates motor targets. The articulated physics
solver resolves them. Verify:
  - Motor targets are finite and within joint limits
  - Physics solver produces stable body (no collapse, no explosion)
  - Contact events match truth-side clinch timing
  - Deterministic replay: 100-run identical hashes
  - 120Hz truth tick never blocks on conditioner inference

### Stage 6: Promotion Gate (MACHINE_ELIGIBLE only)
All of the following must pass:
  - Stage 4 median gate: PASS
  - Stage 4 ablation: PASS
  - Stage 4 distribution: PASS (>= 50% pass rate)
  - Stage 5 physics: PASS
  - Contact sheet: visually verified
  - cargo fmt/check/clippy/test: PASS
  - Bridge tests 3/3: PASS

Then: MACHINE_ELIGIBLE_FOR_LATER_HUMAN_REVIEW
Never: promote, ship, or visually approve without human G4/G5.

## Data Sources (current + in-flight)
| Source | Status | Format | Segments (est) | Priority |
|--------|--------|--------|-----------------|----------|
| CMU mocap | Downloaded (59 clips) | BVH->G1 | 304 | P0 |
| KungfuAthleteBot | Downloaded (924 clips) | MuJoCo->G1 | 791 | P0 |
| Harmony4D grappling | Downloading (41GB) | SMPL->G1 | ~2000 est | P0 |
| Harmony4D MMA | Identified (62GB) | SMPL->G1 | ~1500 est | P1 |
| Kyokushin karate | Downloading (9.19GB) | C3D->G1 | ~500 est | P1 |
| V2M pipeline | Research complete | Video->G1 | Unlimited | P1 |
| UFC/MMA video | Via V2M | Video->G1 | Unlimited | P2 |
| Fighting games | Via V2M | Video->G1 | Unlimited | P2 |

Estimated total with Harmony4D: 1095 (current) + 3500 (Harmony4D) + 500 (Kyokushin)
= ~5000+ segments. This should be sufficient for genuine generalization.

## Action Family Training Order
Train one at a time, verify before next:
1. Grab/clinch (current focus — UNIT-2)
2. Strike (punch/elbow/knee)
3. Kick (front/roundhouse/side)
4. Block/parry
5. Dodge/evasion
6. Footwork/pacing (For Honor-style circling)
7. Weapon arts (sword draw/thrust/slash)
8. Gun arts (draw/reload/fire)
9. Dagger arts
10. Special arts (projectile cut, mid-air roundhouse)

## Checklist Before Any Training Run
- [ ] Corpus quality gate (Stage 0) passed for all sources
- [ ] Segmentation (Stage 1) complete with labels
- [ ] Split (Stage 2) verified leakage-resistant
- [ ] Config recorded (seeds, lr, batch_size, steps, architecture)
- [ ] Data hashes recorded in manifest
- [ ] GPU free (no orphaned processes)
- [ ] Receipt template ready
- [ ] Contact sheet rendering script ready
- [ ] Evaluation script uses MEDIAN, not best-case
- [ ] Ablation test enabled
