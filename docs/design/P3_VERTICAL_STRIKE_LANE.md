# P3 Vertical Strike Lane — Design Contract (JD-RC0 §3)

Status: DESIGN + harness-validation stage. No motion-quality claim is made here.

## Scope

One motion-quality lane: the vertical Strike family.

- Targets: `high_left`, `high_center`, `high_right`
- Timings: `early`, `nominal`, `late`
- 3 × 3 = 9 clips, each genuinely target/timing-directed, each with distinct
  source clip identity.

## Honest conditioning requirement (the hard rule)

WO §3 forbids describing direct post-decode position/rotation replacement as
learned conditioning. The existing `hero_strike.motionbricks.interaction`
checkpoint uses hard sparse/dense constraint channels (`apply_fk_targets` does
post-decode replacement) and therefore reports 0.0 foot/hand error by masking —
that is NOT learned conditioning and is not admissible as the P3 result.

Genuine conditioning means the target/timing is an INPUT the model consumes at
generation/training time, and the held-out error is measured WITHOUT re-applying
the constraint after decode.

## Conditioning channel (validated against installed kimodo)

- kimodo `EndEffectorConstraintSet` constrains a joint to the FK of a *provided
  pose* on a target frame. Validated finding (ad-hoc harness, 2026-07-17): passing
  an arbitrary target point with an identity pose does NOT move the hand to the
  target (measured error 0.71 m); the constraint holds whatever pose is supplied.
  Conditioning on a target therefore requires authoring a pose whose FK actually
  reaches the target (optimization/IK or retargeting a real reference), then using
  that authored pose as the interaction-conditioning input. This falsifies the
  naive "pass target point → model reaches it" assumption.
- Genuine target/timing authoring substrate that already exists:
  `tools/qa/build_pvp005_r6_rotation_strike.py` solves a strike onto G1Skeleton34
  by optimization against the endpoint spec `assets/qa/pvp005_ardy_action_endpoints_v4.json`
  (endpoint error < 10 mm, grip angle < 3°, floor clearance, temporal guards). The
  9 target/timing vertical-Strike cells are authored this way, not by post-decode
  masking.
- kimodo G1 model (`Kimodo-G1-SEED-v1`, `G1Skeleton34`) shares the MotionBricks
  skeleton, so teachers do not need a SOMA77→G1 retarget; `["RightHand"]` expands
  to the wrist/hand chain with `right_hand_roll_skel` (index 33) as the hand
  end-effector.
- Target/timing → authored-conditioning mapping:
  - target: weapon-hand (and weapon-socket proxy) terminal pose per
    high_left / high_center / high_right, expressed in the endpoint spec.
  - timing: contact frame offset per early / nominal / late, expressed in the
    endpoint spec contact_schedule.
- ARDY supplies proposals (root/locomotion intent); MotionBricks supplies
  admitted transitions; deterministic bilateral physics stays authoritative and
  is never fed model output as truth.

## Held-out separation (WO §3, not random windows)

Clips are separated by source clip identity: the 9 clips are partitioned into
train / held-out by clip (and by target/timing cell), never by frames/windows
within a clip and never by Cartesian variants of one template. A held-out cell
is fully absent from training.

## Required proof thresholds (measured, not asserted)

- valid finite SO(3) rotations (orthonormal, det +1)
- full-body FK endpoint error < 10 mm
- planted-foot error ≤ 5 mm
- hand constraint error ≤ 2 mm (held-out, no post-decode re-application)
- weapon-socket relative error ≤ 1 mm
- weapon orientation error ≤ 1 degree
- impact timing within ±1 truth tick
- no visible foot slide / pose pop / hand-socket separation
- replay/render pose, weapon path, contact, result truth agree
- blinded human distinguishes all 9 target/timing clips from full-res motion

## Plan

1. Build the vertical-Strike corpus generator: produce the 9 target-directed
   teacher clips via kimodo EndEffector constraints (distinct prompts + distinct
   end-effector target/contact constraints), each with provenance (source clip
   id, prompt, constraint, seed, hash).
2. Validate ONE clip end-to-end: constraint → generation → measured terminal
   hand position vs. target → confirm the conditioning is real (not masked).
3. Train the interaction-conditioned MotionBricks extension with the
   target/timing tensor as a model INPUT (no post-decode replacement).
4. Evaluate on the clip-separated held-out set against the thresholds above.
5. Blinded human distinguishability trial (existing `blinded_motion_trial.py`).

## Out of scope (WO stop conditions)

No new combat actions, arenas, or model providers. ARDY / MotionBricks /
Fast-SAM-3D-Body are not replaced. Thresholds are not weakened to get green.
