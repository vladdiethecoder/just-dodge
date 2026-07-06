# Technical Stack Decision — Just Dodge

## Decision Summary

Engine: **Custom Rust + wgpu**
Windowing: **winit**
Math: **glam** or **nalgebra**
Rendering: **wgpu** (same lineage as OATHYARD)
Audio: **rodio** or **kira**
Input: **winit** event loop
Asset format: **GLB** with `combat_metadata.json` sidecars
Physics: **none for prototype; deterministic geometric collision only**
Networking: added after local gameplay is verified fun
Platform: Linux-first, Windows second, macOS if feasible

## Why Custom Engine

The project requires deep control over:
- deterministic combat simulation,
- truth-isolated presentation,
- MotionBricks-style procedural animation,
- replay and fight-film systems,
- rollback netcode integration.

A custom engine lets us enforce these invariants at the architecture level. This is the path chosen for Just Dodge.

## Architecture Layers

```
┌─────────────────────────────────────────────┐
│  Presentation Layer                         │
│  wgpu renderer, camera, animation, VFX, UI  │
├─────────────────────────────────────────────┤
│  Presentation-Truth Bridge                  │
│  read combat state → drive renderer nodes   │
│  never write back to combat state           │
├─────────────────────────────────────────────┤
│  Combat Simulation (deterministic)          │
│  state machine, matchup matrix, injury      │
│  truth hash, replay recording               │
├─────────────────────────────────────────────┤
│  Platform Layer                             │
│  winit, input, file I/O, audio, networking  │
└─────────────────────────────────────────────┘
```

## What We Do NOT Build at the Start

- A general-purpose physics engine.
- A 3D scene editor.
- A material/shader pipeline beyond flat colors.
- Audio beyond beeps.
- Asset import beyond hard-coded shapes.

The shape prototype uses:
- one window,
- one colored triangle for the player,
- one colored triangle for the opponent,
- text rendering for state,
- keyboard input for 3 actions,
- a 3×3 matchup resolver,
- a win/loss loop.

## Determinism Contract

- All combat logic uses deterministic operations.
- Randomness uses seeded deterministic RNG.
- Input is captured as discrete events with frame timestamps.
- Replay is a log of inputs + initial seed; simulation reproduces deterministically.
- Frame timing is fixed-step; rendering is decoupled with interpolation.
- Presentation interpolation, camera shake, and VFX never influence the simulation.

## Action & Contact Data Model

```rust
// Conceptual only — exact schema decided at implementation
pub struct CombatAction {
    pub id: String,
    pub stance: Stance,
    pub startup_frames: u32,
    pub active_frames: u32,
    pub recovery_frames: u32,
    pub hitbox_profile: HitboxProfile,
    pub damage_profile: DamageProfile,
    pub commitment_flags: u32,
}
```

## Asset Pipeline

- Characters/weapons: GLB format, PBR materials.
- Each asset must include a `combat_metadata.json` sidecar:
  - bone names for weapon socket, head, torso, arms, legs
  - hitbox proxy mesh paths
  - material slots
- Validator tool checks every imported asset before it enters a build.

## Tooling to Build

- `tools/asset_validator.py` — validates GLB + metadata sidecar.
- `tools/truth_hash_test.rs` — runs a known match and compares hash.
- `tools/package_build.sh` — exports clean executable for testing.
- `tools/replay_analyzer.rs` — converts replay trace to readable timeline.

## Version Control Rules

- Git from day one.
- No large binary assets in git; use Git LFS or external asset store.
- Every commit message references a milestone or prototype.
- `main` branch is always playable; experiments live in feature branches.

## Performance Targets

- 60 FPS on mid-tier hardware at 1080p.
- Input latency < 3 frames.
- Match replay file < 100 KB.
- Load time from executable launch to menu < 5 seconds.
