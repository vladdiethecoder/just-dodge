# Dynamic Momentum/Velocity/Angular-Momentum Conditioning for Combat Motion

Date: 2026-07-17
Status: design for implementation

## Problem

Current motion targets are kinematically valid but feel "meek": they lack the
visible momentum, anticipation, follow-through, and angular commitment that
make combat animation feel juicy and alive. A vertical strike looks like a
stick figure raising and lowering its arms; a real strike looks like the whole
body winds up, commits, and recoils with physical weight.

## Sources studied

- `combat-motion-teacher-corpus` skill: conversion pipeline, rights matrix,
  no-fallback rule, human semantic gate.
- `overgrowth-character-physics` skill: active-to-ragdoll momentum
  preservation, contact impulse feedback, short deterministic reaction windows.
- For Honor / Elden Ring / TEKKEN / YOMI research (web): these games achieve
  juicy combat through motion matching, root motion, anticipation,
  follow-through, and physics-driven reaction, not static pose playback.

## Animation principles to encode

1. **Anticipation**: before the main action, the body moves slightly in the
   opposite direction to build momentum. A strike starts with a small backward
   lean and shoulder windup.
2. **Follow-through**: after contact, the body continues moving past the
   contact point, then recovers. The blade doesn't stop dead at the target.
3. **Squash and stretch**: the torso and limbs compress during windup and
   extend during release. This is subtle in a humanoid but readable.
4. **Overlapping action**: different body parts move at different rates. The
   hips start rotating before the shoulders; the sword lags behind the hands.
5. **Angular momentum**: the torso rotates around the vertical axis; the
   strike has a visible arc, not a straight vertical drop.

## Conditioning inputs to add

For each interaction example, add:

- `root_velocity_mm_s`: [vx, vy, vz] at each frame
- `root_angular_velocity_mrad_s`: [wx, wy, wz] at each frame
- `root_acceleration_mm_s2`: [ax, ay, az] at each frame
- `anticipated_backswing_frames`: how many frames of opposite-direction motion
- `follow_through_frames`: how many frames past the nominal contact point
- `squash_stretch_q8`: compression/extension factor for torso/limbs
- `overlapping_action_lag_frames`: per-joint lag relative to root
- `contact_impulse_milli_ns`: expected impulse at contact
- `contact_energy_millijoules`: expected energy transfer

## Target trajectory changes

1. **Root motion**: the root translates and rotates during the action. A
   strike has forward momentum; a dodge has lateral momentum; a block has
   slight backward momentum from impact.
2. **Anticipation window**: frames [0, windup_end] move the root and hands
   slightly backward relative to the main action direction.
3. **Commitment window**: frames [windup_end, contact_frame] accelerate the
   root and hands forward with increasing velocity.
4. **Follow-through window**: frames [contact_frame, contact_frame + ft] carry
   the hands past the contact point with decaying velocity.
5. **Recovery window**: frames [contact_frame + ft, T] return to guard with
   damped oscillation.

## Verification

- All examples must still pass zero foot/grip/hand error.
- New metrics:
  - `root_translation_range_m`: max - min root position across the action
  - `root_rotation_range_rad`: max - min root yaw/pitch/roll
  - `anticipation_amplitude_m`: backward displacement during windup
  - `follow_through_amplitude_m`: forward displacement past contact
  - `angular_momentum_peak_mrad_s`: peak torso angular velocity
- These metrics must be nonzero for every example and must vary with
  opponent geometry and action intent.

## Forbidden

- Static root.
- Straight vertical hand paths.
- Instant velocity changes.
- No follow-through.
- No anticipation.
