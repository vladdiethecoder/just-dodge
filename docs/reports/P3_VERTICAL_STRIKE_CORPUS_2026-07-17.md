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

All 9 cells authored with `PVP005_R6_ROTATION_PROOF=PASS`. Per-cell metrics:

| cell | hand mm | foot mm | grip deg | grip pos mm |
|---|---|---|---|---|
| high_left:early | 1.11 | 3.19 | 0.283 | 1.11 |
| high_left:nominal | 1.29 | 4.37 | 0.199 | 1.29 |
| high_left:late | 1.76 | 3.15 | 0.286 | 1.76 |
| high_center:early | 1.01 | 2.67 | 0.181 | 1.01 |
| high_center:nominal | 1.18 | 3.36 | 0.196 | 1.18 |
| high_center:late | 1.86 | 3.74 | 0.315 | 1.86 |
| high_right:early | 0.83 | 2.49 | 0.214 | 0.83 |
| high_right:nominal | 0.94 | 2.19 | 0.199 | 0.94 |
| high_right:late | 1.20 | 2.61 | 0.226 | 1.20 |

WO thresholds: hand ≤ 2 mm, planted foot ≤ 5 mm, grip angle ≤ 1°, grip pos ≤ 1 mm.

- hand endpoint: 9/9 within 2 mm
- planted foot: 9/9 within 5 mm
- grip angle: 9/9 within 1°
- grip position: 4/9 within 1 mm; 5/9 exceed (max 1.86 mm) — HONEST GAP, not
  weakened, not hidden. See "Open gaps" below.

Distinctness (not label swaps): minimum pairwise mean-abs difference of the
right-hand target trajectory across the 9 cells = 15.6 mm. Contact-region
right-hand X lands at −0.28 / 0.0 / +0.28 for the three targets (nominal timing).

## Harness falsification recorded (valuable negative result)

A naive kimodo `EndEffectorConstraintSet` with an arbitrary target point and an
identity pose does NOT move the hand to the target (measured 0.71 m error); the
constraint holds whatever pose is supplied. Genuine target-direction requires an
authored target-reaching pose (the optimization builder), which is the path used
here. Ad-hoc harness `/tmp/hermes-verify-p3-kimodo.py` (removed after run).

## Open gaps (not claimed)

1. Grip-position 1 mm threshold: 5/9 cells exceed (up to 1.86 mm). This is an
   authoring-tolerance gap in the optimization solve, to be tightened (more
   steps / tighter grip loss weight) before any quality admission. Not waived.
2. These are AUTHORED conditioning targets, not yet a trained interaction-
   conditioned MotionBricks checkpoint. Training + clip-separated held-out
   evaluation + the remaining WO §3 proofs (SO(3), FK, socket, timing, no foot
   slide, replay/truth agreement) are forward work.
3. Blinded human distinguishability trial (all 9 from full-res motion) not yet run.

## Reproduce

```
python3 tools/qa/build_p3_vertical_strike_corpus.py --out qa_runs/p3_vertical_strike_corpus
```

Requires the pinned ARDY source tree at `/run/media/vdubrov/NVMe-Storage1/ardy`
(revision bound by the spec) and the pinned strike source
`assets/motion/pvp005_candidates/strike/strike_02.ardy.npz`.
