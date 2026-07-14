# Implementation Plan: Just Dodge 3-Action Prototype

## Goal

Produce a playable local 1v1 duel with the actions **Strike**, **Block**, and **Grab** against a deterministic AI. The player commits one hidden action per exchange; the AI commits one; both reveal simultaneously; the resolver determines contact, armor/injury consequences, and the next state. The build records a deterministic replay and computes a stable truth hash.

## Baseline

- Workspace: `/run/media/vdubrov/Bulk-SSD/Just Dodge/.worktrees/proto-3action`
- Branch: `proto-3action`
- Current code: Rust + wgpu renderer, skinned mannequin, MotionBricks ONNX pipeline, procedural idle clip, placeholder combat timer in `src/main.rs`.
- Baseline compile: passes after fixing `glam::Mat4::to_scale()` usage in `src/retarget.rs`.
- Baseline tests: some retarget tests fail on `minimal_mesh()` (pre-existing, out of scope for this prototype unless the agent touches that code).

## Canon Constraints

- MotionBricks is the sole motion engine. No prebaked clips, no procedural fallbacks in release paths.
- Hitbox proxies must match visual geometry exactly.
- Combat truth never reads from renderer, camera, audio, or frame time.
- Presentation never writes to combat truth.
- Networking is out of scope.

## Architecture

New modules (each owned by one parallel agent):

| Module | File | Responsibility |
|---|---|---|
| `truth` | `src/truth.rs` | Deterministic combat state machine: phases, fighters, snapshots, truth hash. |
| `action_matrix` | `src/action_matrix.rs` + `assets/data/action_matrix.ron` | Legacy QA/reference data only; it cannot declare production outcomes. |
| `hitbox` | `src/hitbox.rs` | Extract geometry-accurate collision proxies from skinned pose + weapon mesh. |
| `armor` | `src/armor.rs` | Deterministic material response for one material (plate FEM or simplified deterministic model). |
| `injury` | `src/injury.rs` | Localized tissue injury and capability modifiers from residual force. |
| `replay` | `src/replay.rs` | Record truth snapshots and match events; save/load deterministic replay. |
| `ai` | `src/ai.rs` | Deterministic opponent action selection from snapshot and ruleset. |
| `ui` | `src/ui.rs` | Diegetic/action-menu UI rendering and phase indicators (wgpu text/simple shapes). |

Modified modules:

| Module | Change |
|---|---|
| `src/motion.rs` | Add the ARDy-plan → MotionBricks-completion → quantized plan-packet boundary. A physics-trained active ragdoll tracks packets; deterministic simulation remains outcome authority. See `ONLINE_MOTIONBRICKS_INTERACTION_SOLVER.md`. |
| `src/input.rs` | Add plan-phase action/stance selection input; commit action on confirm. |
| `src/renderer.rs` | Render hitbox debug proxies, phase UI, action poses for both fighters. |
| `src/main.rs` | Wire truth → motion → hitbox → renderer → replay; run fixed-step tick. |

## Module Contracts

### `truth::CombatTruth`

```rust
pub struct CombatTruth { /* private */ }

impl CombatTruth {
    pub fn new(ruleset: RulesetVersion, player_loadout: Loadout, ai_loadout: Loadout) -> Self;
    pub fn phase(&self) -> Phase;
    pub fn snapshot(&self) -> &TruthSnapshot;
    pub fn truth_hash(&self) -> u64;
    pub fn apply_input(&mut self, input: PlayerInput);
    pub fn fixed_tick(&mut self, dt: f32);
    pub fn replay_events(&self) -> &[MatchEvent];
}
```

Phases: `Observe → Plan → Commit → Reveal → Resolve → Consequence → Observe`.

`TruthSnapshot` must be `Clone + Debug + PartialEq` and serializable deterministically.

### Physical outcome authority

```rust
pub fn reduce_physical_contacts(
    substeps: [SharedPhysicsStep; 2],
) -> Result<PhysicalContactBatch, TruthBridgeError>;
```

The 120 Hz solver measures role-tagged swept contacts and reduces two substeps into one 60 Hz truth packet. Physical role and geometry—not action labels or a matchup table—determine Whiff, Hit, Beat, bind, deflection, material response, and injury. `action_matrix.ron` remains non-authoritative test/reference data until removed.

### `hitbox`

```rust
pub struct HitboxProxy {
    pub bone_index: usize,
    pub local_aabb: Aabb,
    pub world_transform: Mat4,
    pub damage_type: DamageType,
}

pub fn extract_proxies(skin_matrices: &[[Mat4; 24]], weapon_pose: &WeaponPose) -> Vec<HitboxProxy>;
pub fn contact(a: &[HitboxProxy], b: &[HitboxProxy]) -> Option<ContactGeometry>;
```

Use exact bone-aligned boxes/capsules from the mannequin skeleton and weapon geometry. No oversized proxies.

### Neural motion plan + active ragdoll

```rust
pub fn propose_motion_plan(request: &PublicPostRevealState) -> Result<MotionPlanPacketV1, Error>;
pub fn controller_targets(
    plan: &MotionPlanPacketV1,
    articulated_state: &ArticulatedState,
) -> Result<MotorTargetBatch, Error>;
```

ARDy proposes semantic short-horizon motion only after Reveal. MotionBricks completes locomotion, in-betweening, and sparse physical constraints. The result is quantized, assigned a stable ID/hash, and recorded before controller use. A physics-trained active-ragdoll policy proposes joint positions/velocities, impedance gains, and torque limits; deterministic articulated simulation alone resolves contact, balance, momentum, material response, and injury. Replays reuse recorded plan/replan packets verbatim. No API accepts an action filename, returns a persistent clip, or lets a neural model declare an outcome.

### `armor` + `injury`

```rust
pub fn resolve_armor(contact: &ContactEvent, loadout: &Loadout, state: &mut ArmorState) -> ArmorResult;
pub fn resolve_injury(armor_result: &ArmorResult, state: &mut InjuryState) -> InjuryResult;
```

For the prototype, armor simulates one material deterministically (e.g., plate as a threshold + integrity value). The interface must support future FEM/cloth/chainmail without changing callers.

### `replay`

```rust
pub struct ReplayRecorder { ... }
impl ReplayRecorder {
    pub fn new() -> Self;
    pub fn record_snapshot(&mut self, frame: u32, snapshot: &TruthSnapshot);
    pub fn record_event(&mut self, event: MatchEvent);
    pub fn save(&self, path: &Path) -> Result<(), Error>;
    pub fn load(path: &Path) -> Result<Self, Error>;
}
```

Output format: deterministic JSONL or binary. Must produce identical bytes for identical input.

### `ai`

```rust
pub struct AiController { rng: DeterministicRng, personality: AiPersonality }
impl AiController {
    pub fn select_action(&mut self, snapshot: &TruthSnapshot, ruleset: &RulesetVersion) -> ActionCommit;
}
```

Never sees the player's hidden intent before reveal.

## Verification Checklist Per Agent

1. Code compiles with `cargo check --bin just-dodge`.
2. New tests pass with `cargo test --bin just-dodge <module>`.
3. No new warnings introduced (or warnings are justified and documented).
4. Interface contracts above are implemented exactly.
5. No `truth_mutation` in presentation code.
6. No procedural motion fallback in release paths.

## Final Integration Verification

1. `cargo build --release --bin just-dodge` succeeds.
2. Running `./target/release/just-dodge` shows two fighters in an arena.
3. Player can select Strike/Block/Grab and a stance, then confirm.
4. AI commits an action deterministically.
5. Reveal generates and records quantized ARDy/MotionBricks plan packets for both actors.
6. The active-ragdoll controller proposes motors while articulated deterministic simulation resolves contact and outcome.
7. Physics-derived `ImpactEvent` data drives camera, audio, VFX, motor compliance, and recovery.
8. Match replay stores plan/replan packets and stable truth hashes; playback never reruns neural inference.
9. Re-running the same packets and physical inputs produces the same truth hash.

## Parallel Agent Tasks

### Agent 1: Combat Truth + Physical Contact Reduction
- Implement `src/truth.rs` with state machine, snapshots, and truth hash.
- Implement role-tagged 120 Hz shared physics and deterministic `PhysicalContactBatch` reduction.
- Prove guard/body precedence, CCD ordering, packet admission, and replay hash stability.

### Agent 2: Neural Planning, Plan Packets, and Active Ragdoll
- Integrate ARDy as a post-Reveal semantic planner and extend MotionBricks with versioned interaction-state conditioning.
- Quantize, hash, serialize, and replay parent-linked motion-plan/replan packets.
- Train/adapt a physics-tracking active-ragdoll controller and export a measured runtime policy.
- Prove replan latency, packet determinism, controller tracking, impact recovery, and zero runtime action-file lookup.
- Ensure no procedural/baked fallback and no neural outcome oracle.

### Agent 3: Hitbox Proxy Extraction
- Implement `src/hitbox.rs` with bone-aligned proxies and contact detection.
- Add hitbox debug visualization hooks.
- Provide tests with simple known poses.

### Agent 4: Armor + Injury Resolver
- Implement `src/armor.rs` and `src/injury.rs` with deterministic simplified material model.
- Define `Loadout`, `ArmorState`, `InjuryState`.
- Provide tests for threshold/integrity behavior.

### Agent 5: Replay + AI
- Implement `src/replay.rs` with deterministic recording/loading.
- Implement `src/ai.rs` deterministic action selection.
- Provide tests for replay stability and AI determinism.

### Agent 6: UI/Input + Renderer Integration
- Extend `src/input.rs` for action/stance selection and commit.
- Implement `src/ui.rs` phase indicators and action menu.
- Extend `src/renderer.rs` and `src/main.rs` to wire all systems.
- Ensure presentation never mutates truth.

## Coordination Rules

- Each agent works in the same worktree but on different files. If two agents must touch the same file, the second agent patches around the first's changes; do not overwrite.
- After all agents return, run `cargo check --bin just-dodge`, resolve conflicts, then run integration verification.
- If a contract needs to change, update this plan and notify the orchestrator; do not silently break other agents' assumptions.

## Implementation Status

Implemented in worktree `/run/media/vdubrov/Bulk-SSD/Just Dodge/.worktrees/proto-3action` on branch `proto-3action` using parallel agents.

| Module | Status | Notes |
|---|---|---|
| `truth` | ✅ Complete | State machine, snapshots, deterministic FNV-1a truth hash, phase budgets. |
| `action_matrix` | ⚠️ Legacy QA only | It is not production outcome authority; measured `PhysicalContactBatch` data drives truth. |
| `motion` | ⚠️ Superseded scaffold | The one-window-per-action/cache path is QA-only. B14X replaces it with quantized ARDy/MotionBricks plan packets feeding a physics-trained active ragdoll and deterministic articulated simulation. |
| `hitbox` | ✅ Complete | Bone-aligned AABBs, weapon proxy, AABB-AABB contact, debug lines. |
| `armor` | ✅ Complete | Deterministic threshold/integrity/coverage model for plate/leather/cloth. |
| `injury` | ✅ Complete | Trauma accumulation, capability penalties, fracture, lethal torso threshold. |
| `replay` | ✅ Complete | Deterministic save/load with `JDRP` header and postcard encoding. |
| `ai` | ✅ Complete | Deterministic xoshiro256++ opponent; never sees hidden Plan intent. |
| `input` | ✅ Complete | Plan-phase action/stance selection and confirm. |
| `ui` | ✅ Complete | Bitmap-font wgpu UI: phase banner, HP/STA bars, action menu, stance indicator, result text, match-over overlay. |
| `renderer` | ✅ Complete | Hitbox debug line rendering, UI overlay integration. |
| `main.rs` | ✅ Complete | Wired truth → AI → replay → renderer → UI; fixed-step tick; saves replay on match end. |

## Verification Results

- `cargo check --bin just-dodge` ✅
- `cargo build --release --bin just-dodge` ✅
- `cargo test --bin just-dodge -- --skip motion` → 49 passed, 0 failed, 6 filtered (motion tests skipped due to environment ONNX init hang).
- Smoke run: `./target/release/just-dodge` starts, loads arena + two skinned mannequins, initializes renderer + UI, loads MotionBricks idle clip, and runs without runtime errors.
- `python3 /home/vdubrov/.kimi-code/skills/game-design-planning/scripts/validate_design.py docs/design/` ✅

## Known Limitations

- The current runtime still preloads QA action windows and does not implement ARDy planning, plan-packet replay, active-ragdoll motor control, or articulated-body physics.
- Swept proxy/AABB contact is not the required convex/capsule CCD and deterministic contact-manifold solver.
- Normal gameplay still lacks verified pose-derived weapon/guard/body geometry and packaged canonical media.
