# P3 Vertical Strike Lane — Corpus Authoring Record (2026-07-17)

Stage: genuine-conditioning corpus authored and mechanically validated. This is
NOT a motion-quality admission, runtime admission, or human-approval claim.

## What was built

`tools/qa/build_p3_vertical_strike_corpus.py` generates 9 distinct endpoint-spec
variants of the vertical Strike (3 targets × 3 timings) and authors each through
the existing optimization builder `tools/qa/build_pvp005_r6_rotation_strike.py`
against the pinned endpoint spec `assets/qa/pvp005_ardy_action_endpoints_v4.json`
and pinned ARDY source revision.

- Targets: high_left (X −0.28 m), high_center (X 0.0), high_right (X +0.28 m),
  applied to the contact (apex) keypose terminal weapon pommel/tip.
- Timings: early (−4 frames), nominal (0), late (+4), applied to the contact
  keypose frame and the `weapon_contact_proposal` event frame.
- Each cell produces `specs/<cell>.json`, `trajectories/<cell>.npz`,
  `proofs/<cell>.json` under `qa_runs/p3_vertical_strike_corpus/` (gitignored).

## Genuine-conditioning statement

The target/timing is an INPUT to the optimization author (via the spec keypose
schedule and contact-schedule/event frames), NOT a post-decode position/rotation
replacement. This satisfies the WO §3 rule that direct post-decode replacement
must not be described as learned conditioning. The previous
`hero_strike.motionbricks.interaction` checkpoint (hard-masked channels, 0.0
reported error) is NOT the P3 result and remains exploratory-only.

## Validated evidence (measured, this session)

All 9 cells authored with `PVP005_R6_ROTATION_PROOF=PASS`. Final solve:
`--steps 4000 --hand-weight 600` (a tighter solve; thresholds were NOT weakened).
Per-cell metrics:

| cell | hand mm | foot mm | grip deg | grip pos mm |
|---|---|---|---|---|
| high_left:early | 0.50 | 2.98 | 0.134 | 0.50 |
| high_left:nominal | 0.60 | 4.03 | 0.097 | 0.60 |
| high_left:late | 0.83 | 2.98 | 0.140 | 0.83 |
| high_center:early | 0.46 | 2.65 | 0.094 | 0.46 |
| high_center:nominal | 0.53 | 3.28 | 0.096 | 0.53 |
| high_center:late | 0.71 | 2.66 | 0.130 | 0.71 |
| high_right:early | 0.43 | 4.31 | 0.106 | 0.43 |
| high_right:nominal | 0.56 | 2.08 | 0.100 | 0.56 |
| high_right:late | 0.58 | 2.58 | 0.110 | 0.58 |

WO thresholds: hand ≤ 2 mm, planted foot ≤ 5 mm, grip angle ≤ 1°, grip pos ≤ 1 mm.

- hand endpoint: 9/9 within 2 mm (worst 0.83 mm)
- planted foot: 9/9 within 5 mm (worst 4.31 mm)
- grip angle: 9/9 within 1° (worst 0.14°)
- grip position: 9/9 within 1 mm (worst 0.83 mm) — the earlier 5/9 over-threshold
  gap (up to 1.86 mm at the default 1500-step solve) is CLOSED by the tighter
  solve, not by weakening the threshold. No joint-limit violations in any cell.

Distinctness (not label swaps): minimum pairwise mean-abs difference of the
right-hand target trajectory across the 9 cells = 15.6 mm. Contact-region
right-hand X lands at −0.28 / 0.0 / +0.28 for the three targets (nominal timing).

## Mechanical proofs (validate_p3_vertical_strike_mechanics.py, this session)

Final solve: `--steps 4000 --hand-weight 600 --foot-weight 600`. Per-cell measured
properties (WO §3 mechanical bounds, no opponent model required):

| property | result | bound |
|---|---|---|
| SO(3) local/global orth+det error | 6.0e-7 – 7.6e-7 | exact (finite, orthonormal, det +1) |
| independent FK recompute error | 0.00 m | — |
| planted-foot slide (within planted window) | 0.14 – 0.73 mm | ≤ 5 mm |
| grip span deviation from 0.160 m | 0.18 – 0.39 mm | ≤ 2 mm |
| impact timing error | 0 frames (all 9) | ± 1 tick |

`P3_MECH_PROOF cells=9 failures=0`.

During validation a genuine single-cell defect was found and fixed, not hidden:
`high_right:early` initially showed 6.43 mm left-foot slide in the recovery window
[36,51] (the builder's endpoint metric passed it; the slide was mid-window). Raising
the planted-foot solve weight to 600 re-authored it to 0.14 mm. All 9 cells were then
re-solved uniformly at foot-weight 600; slide is now ≤ 0.73 mm everywhere. This is
recorded as a falsification-and-repair, not a threshold change.

## Harness falsification recorded (valuable negative result)

A naive kimodo `EndEffectorConstraintSet` with an arbitrary target point and an
identity pose does NOT move the hand to the target (measured 0.71 m error); the
constraint holds whatever pose is supplied. Genuine target-direction requires an
authored target-reaching pose (the optimization builder), which is the path used
here. Ad-hoc harness `/tmp/hermes-verify-p3-kimodo.py` (removed after run).

## Open gaps (not claimed)

1. These are AUTHORED conditioning targets, not yet a trained interaction-
   conditioned MotionBricks checkpoint. Training + clip-separated held-out
   evaluation + the remaining WO §3 proofs (SO(3), FK, socket, timing, no foot
   slide, replay/truth agreement) are forward work.
2. Blinded human distinguishability trial (all 9 from full-res motion) not yet run.

## DECIDED: adapt-path falsified (2026-07-17, this session)

The train-vs-adapt question is now answered by measurement, not preference. The
existing interaction checkpoint (`hero_strike.motionbricks.interaction`, a
"trained temporal residual extension with HARD sparse/dense constraint channels")
depends on post-decode FK replacement (`apply_fk_targets`) to hit its targets —
exactly the mechanism the WO forbids calling learned conditioning.

Adapt-path test (ad-hoc harness, since removed): fed each cell's authored FK
targets to `generate_interaction_clip` as CONDITIONING INPUT with the post-decode
replacement removed, and measured the generated prediction independent of the
input target. Result across all 9 cells:

- prediction is a genuine generation (passthrough=false), valid SO(3) (~1e-7),
  32-frame clip.
- interaction hand error vs authored target: 1126–1313 mm.

The checkpoint produces a plausible generic strike transition but does NOT reach
the conditioned target/timing. Removing the forbidden post-decode mask exposes
that the current checkpoint does not generalize from target conditioning.

Conclusion: genuine interaction-conditioning REQUIRES training a checkpoint on
target-directed data (the train-path). Adapt-path via the existing hard-mask
checkpoint is not admissible. The 9 authored trajectories are valid teachers, but
9 clips are too few to train a generalizing generator without synthetic padding
(forbidden). The honest next unit is building a larger REAL target-directed
vertical-Strike corpus (kimodo/ARDY target-directed clips with distinct source
identity), then fine-tuning MotionBricks with a clip-separated held-out split.

## Reproduce

```
python3 tools/qa/build_p3_vertical_strike_corpus.py \
  --out qa_runs/p3_vertical_strike_corpus \
  --steps 4000 --hand-weight 600 --foot-weight 600
python3 tools/qa/validate_p3_vertical_strike_mechanics.py
```

Requires the pinned ARDY source tree at `/run/media/vdubrov/NVMe-Storage1/ardy`
(revision bound by the spec) and the pinned strike source
`assets/motion/pvp005_candidates/strike/strike_02.ardy.npz`.
