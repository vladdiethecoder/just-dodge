# Just Dodge Combat Blackbox Design Contract

**Status**: design authority for implementation
**Date**: 2026-07-17
**Authority**: user responses to 20 clarifying questions

## Core Principle

Combat is a **deeply simulated blackbox**. The same intent never plays out
identically. Variability emerges from physics, hidden state, and environmental
interaction. No RNG, no fallback clips, no canned outcomes.

## Variability Model

- **Deterministic**: seeded, reproducible from match state.
- **Hidden but with obvious visual tells**: state is not shown on UI, but is
  readable through animation, posture, timing, and physical feedback.
- **Both physics and animation**: variability comes from physics simulation
  (momentum, collision, ragdoll) and animation selection (different motion for
  same intent).

## Hidden State Systems

### Fighter State
- Fatigue, momentum, previous action, stance, footing.
- Affects move timing (startup frames), speed, power, and recovery.
- Tired fighters have slower startups and reduced range.

### Opponent Interaction
- Opponent's hidden state affects how your moves land.
- Opponent's stance, balance, and fatigue change contact outcomes.
- AI opponent has exploitable patterns and weaknesses.

### Weapon State
- **Materials simulated**: sharpness, weight, balance, durability.
- **Weight**: real value affecting movement speed, attack timing, pose recovery.
- **Stances**: hidden stance options unlocked by weapon type/weight.
- **Arts**: special moves with hidden requirements (stance, momentum, timing)
  discovered through experimentation (YOMI Hustle style).
- **Breaking**: weapons break under right conditions and forces.

### Armor State
- **Numerical**: durability affects protection.
- **Visual/physical**: deformation, wearing, cracking, dents, scratches.
- **Breaking**: armor breaks under sufficient force.

### Environment
- Arena, terrain, obstacles affect move outcomes.
- Nearly every layer is a deep simulation.

### Injury
- **Per-match only**: no persistent injury across matches.
- Injury affects movement, timing, and available moves.
- Visible through dramatic animation (limping, favoring, guarding).

## Visual Tells (For Honor fidelity)

- Player can inspect/estimate opponent hidden state through visual tells.
- Tells must be **dramatic**: limping, heavy breathing, favoring sides,
  weapon grip changes, stance shifts, sweat, blood, armor damage.
- No UI hints: purely visual/physical, highest fidelity, For Honor style.

## Outcome Model

- **Same intent can fail entirely**: strikes whiff from footing, blocks fail
  from timing, grabs fail from distance.
- **Physically simulated chance**: failures emerge from physics, not RNG.
- **Full-body physics**: every joint simulated, root + all limbs.
- **Timing affected**: hidden state changes frame data (startup, active, recovery).

## Determinism and Inspection

- **Fully deterministic**: seeded, replayable, hash-bound.
- **Inspectable via replay/debug tools**: all hidden state can be examined
  in replay/debug mode.
- **No truly hidden state**: developers can inspect everything.

## Forbidden

- RNG for outcomes.
- Fallback or pre-baked animations.
- Canned outcomes (same input = same output).
- UI damage numbers or explicit state indicators.
- Persistent injury across matches.
- Non-deterministic variability.

## Implementation Notes

- All state must be hash-bound and replay-verifiable.
- Visual tells must be driven by the same physics that drive outcomes.
- No separate "visual only" state: what you see is what the physics computed.
- Training/lab mode planned for final release.
