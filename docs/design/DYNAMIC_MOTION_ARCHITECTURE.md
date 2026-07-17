# Just Dodge — Dynamic Motion Architecture

Date: 2026-07-17
Status: governing design correction

## The problem with text-to-motion for this game

Text-to-motion (Kimodo/ARDY prompted with "perform a strike") produces one
canonical animation per prompt. Every Strike looks the same. Every Block is
identical. That defeats the fundamental purpose of the engine:

- The game is a YOMI duel where physical geometry, timing, spacing, and the
  opponent's actual attack determine what the correct motion looks like.
- A Block against a high diagonal cut must be a different motion than a Block
  against a low thrust. A Dodge must adapt to the actual weapon corridor.
- Fixed clips make the game readable in the wrong way: the opponent learns to
  pattern-match canned animations instead of reading live physical geometry.

## The correct architecture

Production motion is synthesized live, per exchange, from:

1. **Intent** — the committed action (Strike/Block/Dodge/Parry/Grab/Thrust/Move)
2. **Opponent geometry** — attack origin, direction, side, height, reach,
   velocity, predicted contact window, weapon corridor
3. **Physical state** — actor pose, footing, balance, injury, recovery,
   clearance, weapon/armor state
4. **Deterministic 120 Hz physics feedback** — measured contact, impulses,
   balance, momentum transfer

The interaction-conditioned MotionBricks model receives all of this as
time-varying conditioning input and produces a motion plan specific to this
exchange. The active-ragdoll controller tracks the plan. Deterministic physics
resolves contact, injury, and outcome.

## What Kimodo and ARDY are for

Kimodo and ARDY are not the runtime motion engine. They serve two roles:

1. **Offline corpus generation** — generate diverse, constraint-driven training
   examples across the combat space (different attack angles, heights, timings,
   distances, defensive responses). These become training data for the
   interaction-conditioned MotionBricks extension.
2. **Online semantic planning (future)** — ARDY can propose a short-horizon
   semantic plan from public post-Reveal state. That plan feeds MotionBricks,
   not the renderer. The plan is quantized, hashed, and recorded. MotionBricks
   completes the kinematics. Physics resolves the outcome.

## What the combat-move batch is for

The `tools/qa/r6k_combat_move_batch.py` pipeline generates diverse training
examples across the combat space:

- different strike angles (vertical, diagonal, thrust)
- different defensive responses (high block, lateral dodge)
- different ranges and timings
- opponent-relative geometry

These are training fixtures, not runtime assets. The production model learns
from these examples to synthesize novel, context-appropriate motion at runtime.

## Hard rule

A motion that is the same every time for a given intent is a clip, regardless
of how it was generated. The engine must produce a different motion when the
opponent's geometry, timing, or the actor's physical state differs.
