# Implementation Plan: Just Dodge 3-Action Prototype

## Goal

Produce a playable local 1v1 duel with the actions **Strike**, **Block**, and **Grab** against a deterministic AI. The player commits one hidden action per exchange; the AI commits one; both reveal simultaneously; the resolver determines contact, armor/injury consequences, and the next state. The build records a deterministic replay and computes a stable truth hash.

## Baseline

- Workspace: `/run/media/vdubrov/NVMe-Storage1/Just Dodge`
- Revision: published PVP-005 feature baseline `4e481ccd59602c1cb4eda97183c32dec48f9a801` on `pvp-005-readable-live-motion`; public `main` remains the historical `2677b4a7dd050e7f4c5ee03881aa16035e413a8b`; one worktree exists.
- Selected live path: `main::App` → `milestone3::Session/Match` → `m3_cleanbox` → `cleanbox/duel_world/duel_physics` → `PhysicalContactBatch` → immutable `milestone3::Snapshot` → renderer/UI/replay.
- Fresh baseline: warning-denying all-target check passes; 233 all-target tests pass; release `just-dodge` and `m3_match` build; deterministic autoplay ends at frame 342/hash `d1a3cc1bfb9c2f67`; 100 replay reconstructions pass.
- Current inherited closure: fmt, warning-denying clippy/check, 237 tests, release autoplay/replay, a hydrated clean-checkout mirror, two byte-identical local packages, repository/package verifiers, and automated OS-input flow pass at their recorded revisions. Canonical gameplay media and human motion-readability evidence do not exist yet.

## Canon Constraints

- Official pinned ARDY is an offline proposal source only. Runtime motion is a frozen, canonical-payload-hashed packet. MotionBricks is admitted only if its exact source/checkpoint/license are recorded and an A/B gate proves it improves continuity/readability over the simpler frozen-source path. No runtime neural generation or silent fallback is allowed.
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

Implementation history was consolidated onto `main`. The status below distinguishes the live M3 path from supporting or isolated foundations; no old worktree is authoritative.

| Module | Status | Notes |
|---|---|---|
| `truth` | ✅ Complete | State machine, snapshots, deterministic FNV-1a truth hash, phase budgets. |
| `action_matrix` | ⚠️ Legacy QA only | It is not production outcome authority; measured `PhysicalContactBatch` data drives truth. |
| `motion` | ⚠️ Isolated foundations | Public post-Reveal requests, ARDY proposals, MotionBricks receipts, quantized plan packets, G1 articulation, hinge projection, and independent-joint tracking exist. None drives `App::current_pose()` or live contact. |
| `hitbox` | ✅ Complete | Bone-aligned AABBs, weapon proxy, AABB-AABB contact, debug lines. |
| `armor` | ✅ Complete | Deterministic threshold/integrity/coverage model for plate/leather/cloth. |
| `injury` | ✅ Complete | Trauma accumulation, capability penalties, fracture, lethal torso threshold. |
| `replay` | ✅ Complete | Deterministic save/load with `JDRP` header and postcard encoding. |
| `ai` | ✅ Complete | Deterministic xoshiro256++ opponent; never sees hidden Plan intent. |
| `input` | ✅ Complete | Plan-phase action/stance selection and confirm. |
| `ui` | ✅ Complete | Bitmap-font wgpu UI: phase banner, HP/STA bars, action menu, stance indicator, result text, match-over overlay. |
| `renderer` | ✅ Complete | Hitbox debug line rendering, UI overlay integration. |
| `main.rs` | ⚠️ Mechanically complete flow, unproven package cadence | Wires M3 truth → AI → replay → renderer → UI; provides Menu/Establishing/duel/Result/validated Replay, rematch/menu/quit, and cursor ownership. Packaged human interaction proof, admitted action poses, and socket-derived weapons remain absent. |

## Verification Results

- `RUSTFLAGS='-Dwarnings' cargo check --locked --all-targets` passes.
- `RUSTFLAGS='-Dwarnings' cargo test --locked --all-targets` passes 237 tests, including both live MotionBricks integrations.
- `cargo test --locked --lib milestone3::tests::one_hundred_replay_reconstructions_keep_the_same_truth_hash -- --nocapture` passes.
- `RUSTFLAGS='-Dwarnings' cargo build --locked --release --bin just-dodge --bin m3_match` passes.
- Release launch initializes the Vulkan renderer/UI and writes a terminal replay under deterministic autoplay; `m3_match --verify` reconstructs frame 342/hash `d1a3cc1bfb9c2f67`.
- Runtime-flow regressions prove Menu/Establishing truth isolation and Replay reconstruction without terminal-session mutation; release Menu and Result captures are recorded locally.
- `cargo fmt --check`, warning-denying clippy, two byte-identical local package assemblies, complete manifest verification, packaged replay reconstruction, `/tmp` launch, and automated OS-level keyboard/mouse cadence pass. Five human matches and canonical-media verification do not pass yet.

## Known Limitations

- The runtime renders bind matrices for both actors. ARDY, plan-packet, G1 articulation, hinge projection, and active-ragdoll code is isolated from gameplay.
- The current active-ragdoll tracker advances independent joint/root states; it does not yet implement parent-child coupling, gravity, limits, balance, ground, grips, or shared-world contacts.
- M3 contact is reduced from action-authored cleanbox geometry, not pose-derived weapon/guard/body proxies.
- The first-person sword uses an independent camera/action transform rather than the posed hand socket used by CCD/contact.
- Normal gameplay lacks human-match evidence, calibrated motion/contact/camera metrics, and canonical media. The first Replay capture also shows its footer overlapping stale Plan instructions.
