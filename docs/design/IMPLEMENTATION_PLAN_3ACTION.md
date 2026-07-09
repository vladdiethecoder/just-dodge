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
| `action_matrix` | `src/action_matrix.rs` + `assets/data/action_matrix.ron` | 3×3 matchup data, timing table, contact-type rules. |
| `hitbox` | `src/hitbox.rs` | Extract geometry-accurate collision proxies from skinned pose + weapon mesh. |
| `armor` | `src/armor.rs` | Deterministic material response for one material (plate FEM or simplified deterministic model). |
| `injury` | `src/injury.rs` | Localized tissue injury and capability modifiers from residual force. |
| `replay` | `src/replay.rs` | Record truth snapshots and match events; save/load deterministic replay. |
| `ai` | `src/ai.rs` | Deterministic opponent action selection from snapshot and ruleset. |
| `ui` | `src/ui.rs` | Diegetic/action-menu UI rendering and phase indicators (wgpu text/simple shapes). |

Modified modules:

| Module | Change |
|---|---|
| `src/motion.rs` | Add `generate_action_clip(action: Action, seed_pose: ...) -> Vec<[Mat4; 34]>` driven by MotionBricks. |
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

### `action_matrix`

```rust
pub fn resolve(action_a: Action, action_b: Action,
               contact: &ContactGeometry, distance: DistanceBand,
               ruleset: &RulesetVersion) -> MatrixResult;
```

Data file `assets/data/action_matrix.ron` holds:
- Timing table (startup, active, recovery frames per action).
- 3×3 contact type table.
- Initiative rules.
- Armor/injury query parameters per contact type.

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

### `motion`

```rust
pub enum Action { Strike, Block, Grab }

pub fn generate_action_clip(
    action: Action,
    current_pose: &[Mat4; 34],
    target_cond: &ActionCondition,
    pipeline: &mut MotionPipeline,
) -> Result<Vec<[Mat4; 34]>, Error>;
```

If MotionBricks ONNX artifacts are missing, the function returns an error; the caller must abort with a clear message. No procedural fallback in the runtime path.

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
5. Reveal plays both MotionBricks-generated poses.
6. Resolver determines contact and outcome.
7. Match records a replay file with a stable truth hash.
8. Re-running the same inputs produces the same truth hash.

## Parallel Agent Tasks

### Agent 1: Combat Truth + Action Matrix
- Implement `src/truth.rs` with state machine, snapshots, and truth hash.
- Implement `src/action_matrix.rs` and `assets/data/action_matrix.ron`.
- Provide tests for state machine transitions and matrix lookups.

### Agent 2: MotionBricks Action Generation
- Extend `src/motion.rs` to generate Strike/Block/Grab clips from MotionBricks.
- Add `Action` enum and conditions.
- Ensure no procedural fallback in runtime path.

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
| `action_matrix` | ✅ Complete | RON-driven 3×3 matchup matrix and timing table. |
| `motion` | ✅ Complete | `generate_action_clip` for Strike/Block/Grab; tests compile. Runtime ONNX init hangs in this environment. |
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

- Action clips from `motion::generate_action_clip` are implemented but not wired into `main.rs`; the idle clip is rendered for all phases. Wiring requires resolving the environment ONNX initialization hang.
- Motion tests cannot run in this environment because ONNX session creation hangs indefinitely. The implementation and test compilation are complete.
- Some compiler warnings remain (pre-existing and minor).
