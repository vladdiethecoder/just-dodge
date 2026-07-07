# Architecture — Just Dodge

## Purpose

This document is the architecture contract for Just Dodge. It consolidates the existing repository state, source inspection, asset inventory, design documents, MotionBricks plan, armor/damage plan, and OATHYARD lessons into one implementation-neutral blueprint.

This is a documentation pass only. It does not authorize code changes. Production work still advances through prototype gates, milestone evidence, and player-experience verification.

## Core Product Architecture

Just Dodge is a first-person deterministic melee duel game. The game is not a reaction brawler. It is a simultaneous-reveal YOMI duel where both players commit to one hidden action, reveal together, resolve deterministic consequences, and loop until incapacitation.

The architecture exists to protect four invariants:

1. Combat truth is deterministic and replayable.
2. Presentation improves readability but never mutates truth.
3. Every system is justified by player-readable duel decisions.
4. The project remains solo-developer feasible through phase gates and ruthless scope control.

## Repository-Derived Current Baseline

Inspected files show the repository has moved beyond the README's older “code-empty” description.

Current source/code baseline:

- `Cargo.toml`: Rust 2024 project using `winit 0.30`, `wgpu 30.0`, `glam 0.28`, `image 0.25`, `fbxcel 0.9`, `ort 2.0.0-rc.12` with `load-dynamic` and `cuda`, `ndarray`, `anyhow`.
- `src/main.rs`: winit 0.30 `ApplicationHandler` event loop, forced Vulkan backend, orbital camera, render loop, MotionBricks clip generation path, current input print path.
- `src/renderer.rs`: multi-object wgpu renderer with textured static meshes, procedural checkerboard ground, depth buffer, skinned mannequin render pipeline, per-frame joint-matrix storage buffer.
- `src/asset.rs`: static mesh `.bin` loader, SKM1 skinned mesh loader, ANM1 animation loader, G1-to-mannequin retarget map, skin-matrix computation.
- `src/motion.rs`: ONNX Runtime MotionBricks VQVAE pipeline, NPY codebook loader, quantize/dequantize helpers, decoded G1 frame parsing, synthetic idle encoder seed, 34-joint world matrix reconstruction.
- `src/combat.rs`: 3-action Strike/Block/Grab action profiles mapped to MotionBricks-style local/global root constraints and replanning logic.
- `src/input.rs`: key mapping Z/X/C to Strike/Block/Grab.
- `src/shader.wgsl`: textured static mesh shader with simple directional light.
- `src/skin.wgsl`: skinned mannequin shader using 24 joint matrices in storage buffer.
- `tools/*.py`: Meshy/GLB/FBX extraction, MotionBricks ONNX export, backbone export, SKM1/ANM1 verification.

Current asset baseline:

- Static arena binary meshes:
  - `assets/arena_rock.bin`: 209,869 vertices, 1,259,202 indices.
  - `assets/lintel_gate.bin`: 116,218 vertices, 697,428 indices.
  - `assets/rune_pillar.bin`: 184,033 vertices, 1,104,741 indices.
  - `assets/mannequin_male.bin`: 40,654 vertices, 244,308 indices.
- Textures:
  - Arena rock/gate/pillar textures are 4096² base/normal-class maps and 2048² grayscale metallic/roughness maps, depending on source asset.
  - Mannequin texture is 4096² RGBA.
- Skinned character assets:
  - `assets/characters/mannequin_male.bin`: SKM1, 68,107 vertices, 244,308 indices, 24 bones, verified weights, 1.556 game-unit height.
  - `assets/characters/mannequin_male_running.anim`: ANM1, 39 frames, 60 fps, 24/24 animated bones.
  - `assets/characters/mannequin_female.bin`: SKM1, 163,211 vertices, 871,596 indices, 24 bones, verified weights, 1.551 game-unit height.
  - `assets/characters/mannequin_female_merged.anim`: ANM1, 39 frames, 30 fps, 24/24 animated bones.
  - Dummy SKM1 male/female meshes also verify.
- Source assets:
  - Meshy FBX files for mannequin, running, walking, arena rock, lintel gate, rune pillar.
  - PBR texture sets for arena assets and mannequin.

Current design baseline:

- `docs/GDD.md`: target game identity, 13 actions, localized injury, armor/loadouts, modes, success metrics.
- `docs/COMBAT-SYSTEM.md`: action matrix intent, timing phases, injury, armor handoff, AI, replay/fight film, truth isolation.
- `docs/MOTIONBRICKS-RETARGETING.md`: 29-joint MotionBricks source to richer mannequin skeleton, injury/IK layers, truth-isolated presentation.
- `docs/ARMOR-DAMAGE-SYSTEM.md`: armor slots, materials, resistance, persistent damage records, per-material simulation notes, loadout identities.
- `docs/LESSONS-FROM-OATHYARD.md`: truth hash stability, renderer-driven development trap, PresentationBricks, no placeholder UI, executable-first verification.
- `docs/ROADMAP.md`, `docs/MILESTONES.md`, `docs/PROTOTYPES.md`, `docs/CHECKLIST.md`: current phase structure and gates.

## Architectural Layers

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ PLAYER / TEST AGENT INPUT                                                    │
│ Human controls, deterministic playtest agents, recorded replays              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │ frame-stamped committed inputs
┌──────────────────────────────────▼───────────────────────────────────────────┐
│ PLATFORM SHELL                                                                │
│ winit lifecycle, window, device/surface, input collection, file paths         │
│ Files now: src/main.rs, src/input.rs                                          │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │ discrete commands only
┌──────────────────────────────────▼───────────────────────────────────────────┐
│ COMBAT TRUTH SIMULATION                                                       │
│ fixed-step state machine, matchup matrix, injury, armor truth state, AI       │
│ planned authoritative module group; current partial: src/combat.rs            │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │ immutable snapshots / events
┌──────────────────────────────────▼───────────────────────────────────────────┐
│ PRESENTATION-TRUTH BRIDGE                                                     │
│ converts committed truth events into pose, camera, audio, VFX, UI requests    │
│ must be one-way; no renderer/animation feedback into combat truth             │
└──────────────────────────────────┬───────────────────────────────────────────┘
                 ┌─────────────────┴──────────────────┐
┌────────────────▼────────────────┐  ┌────────────────▼───────────────────────┐
│ MOTION / RETARGETING             │  │ ASSET / MATERIAL / DAMAGE PRESENTATION │
│ MotionBricks, clips, IK, ROM      │  │ meshes, textures, armor damage maps    │
│ Files now: src/motion.rs          │  │ Files now: src/asset.rs, assets/       │
└────────────────┬────────────────┘  └────────────────┬───────────────────────┘
                 └─────────────────┬──────────────────┘
┌──────────────────────────────────▼───────────────────────────────────────────┐
│ RENDER / AUDIO / UI PRESENTATION                                              │
│ wgpu pipelines, shaders, camera, player/presentation/developer mode UI        │
│ Files now: src/renderer.rs, src/shader.wgsl, src/skin.wgsl                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Hard Boundaries

### Combat truth cannot import presentation

Combat truth owns:

- action IDs,
- committed inputs,
- reveal timing,
- matchup outcome,
- hit/contact type,
- injury values,
- armor truth state,
- stamina/tempo,
- AI decision state,
- replay event stream,
- truth hash.

Combat truth must not depend on:

- wgpu device/surface/queue,
- shader outputs,
- camera transforms,
- texture sampling,
- animation interpolation,
- frame time jitter,
- MotionBricks sampling nondeterminism,
- visual-agent scores.

### Presentation can read truth snapshots only

Presentation receives immutable event/state snapshots:

```text
TruthSnapshot {
  frame_index,
  rng_seed_id,
  match_phase,
  fighters[],
  committed_actions[],
  revealed_actions[],
  contact_events[],
  injury_events[],
  armor_events[],
  replay_cursor,
}
```

Presentation may derive:

- pose/animation selection,
- MotionBricks conditions,
- camera shake,
- audio cues,
- VFX events,
- UI labels,
- fight-film cuts,
- visual QA captures.

Presentation may not write back into truth. If a presentation result should alter gameplay, it must become an explicit deterministic truth event in the next design pass, not an implicit renderer side effect.

## Runtime State Machines

### Match State Machine

Target state machine:

```text
Boot
  → MainMenu
  → MatchSetup
  → Observe
  → Plan
  → Commit
  → Reveal
  → Resolve
  → Consequence
  → Observe | MatchResult
  → ReplayTheater | FightFilm | Rematch | MainMenu
```

Stage-gated subset:

- Shape prototype: Observe → Commit → Reveal → Resolve → Consequence → MatchResult/Restart.
- First playable: add MatchSetup, AI opponent, replay record, restart/rematch.
- Vertical slice: full 13-action matrix, localized injury, armor/loadout, readable motion, fight-film.
- Content complete: tutorial, local 2P, options, multiple fighters/weapons/arenas.
- Multiplayer: remote input injection, rollback, desync tools.

### Action Lifecycle

Target action lifecycle:

```text
Selectable
  → PlannedHidden
  → CommittedLocked
  → Revealed
  → Startup
  → Active
  → Recovery
  → ConsequenceApplied
  → NeutralReady
```

Current `src/combat.rs` provides only 3 authored action profiles and `ActionState` frame ticking. It is a useful MotionBricks-action constraint scaffold, not the full authoritative resolver.

### Replay Lifecycle

Replay is not a video. Replay is deterministic truth input:

```text
ReplayHeader {
  version,
  build_id,
  ruleset_hash,
  asset_manifest_hash,
  initial_seed,
}

ReplayInputStream {
  frame_index,
  player_id,
  input_action,
  stance,
  optional_menu_action,
}

ReplayTruthEvents {
  optional cached outcome events for audit only,
  recomputed during validation,
}
```

Replay validation recomputes truth and compares hash. Fight Film consumes replay truth and renders cinematic presentation; it cannot become the authoritative match.

## Subsystem Architecture

### 1. Platform Shell

Current files:

- `src/main.rs`
- `src/input.rs`

Current responsibilities:

- winit 0.30 lifecycle via `ApplicationHandler`.
- Window creation and close handling.
- Vulkan backend selection for wgpu.
- Surface/device/queue/config setup.
- Mouse drag/scroll orbital camera.
- Per-frame redraw request.
- Z/X/C input print path.
- MotionBricks clip construction on resume.

Target responsibilities:

- collect physical input and normalize into frame-stamped intent events;
- maintain app mode: Developer, Presentation, Player;
- hold platform devices and presentation resources;
- call fixed-step simulation with deterministic input buffer;
- call renderer with immutable presentation snapshot;
- never contain combat rules.

Architecture debt observed:

- `src/main.rs` currently mixes platform lifecycle, camera, renderer ownership, MotionBricks clip construction, and action print handling.
- That is acceptable for a prototype shell but must be split before first playable acceptance.
- Desired future split is app/platform shell, simulation owner, presentation owner, and QA hooks.

### 2. Input

Current file:

- `src/input.rs`

Current shape:

- Z = Strike.
- X = Block.
- C = Grab.
- Only pressed events return actions.

Target input model:

```text
InputEvent {
  frame_index,
  source: HumanLocal | AI | Replay | NetworkRemote | TestAgent,
  player_id,
  action_id,
  stance_id,
  sequence_number,
}
```

Rules:

- Human, AI, replay, network, and QA agent input must enter through the same logical path.
- Hidden action commit must be impossible to alter after lock.
- AI must commit before player reveal and cannot inspect hidden player intent.
- Input timestamps use simulation frames, not wall-clock time.

### 3. Combat Truth

Current file:

- `src/combat.rs`

Current shape:

- Three actions: Strike, Block, Grab.
- MotionBricks keyframe/root constraints.
- Action durations in tokens/frames.
- Replan trigger logic.
- Unit tests for profiles/lifecycle/replanning.

Target modules:

```text
combat/
  action.rs          action IDs, phases, timings, stance tags
  matrix.rs          13x13 data-authored matchup matrix
  state.rs           match state machine
  resolver.rs        deterministic resolve function
  injury.rs          localized injury state
  armor_truth.rs     slots, integrity, persistent damage truth
  ai.rs              deterministic AI personalities
  replay.rs          input stream + truth hash
  hash.rs            canonical truth hash
```

Target resolver contract:

```text
ResolveInput:
  ruleset_version
  frame_index
  player_state_before
  opponent_state_before
  committed_action_a
  committed_action_b
  stance_a
  stance_b
  distance_state
  armor_state_snapshot
  rng_seed_stream_position

ResolveOutput:
  contact_type
  winner_role / initiative_role
  hit_locations
  residual_force_events
  injury_events
  armor_damage_events
  tempo_delta
  next_phase_flags
  truth_hash_delta
```

The full 13×13 matrix must be authored as data, not hard-coded branching. That preserves inspectability, testability, and balance iteration.

### 4. Injury and Armor Truth

Current design files:

- `docs/COMBAT-SYSTEM.md`
- `docs/ARMOR-DAMAGE-SYSTEM.md`

Target responsibilities:

- localized body damage;
- capability deltas: grip, speed, dodge availability, arm speed, vision, stamina regen;
- armor coverage by bone/joint slot;
- material thresholds;
- integrity;
- persistent damage events;
- deterministic damage maps/crack/ring truth state;
- residual force routing.

Armor truth is not visual decals. Armor truth must serialize enough state to make gameplay consequences reproducible after save/load and replay.

Minimum deterministic armor record:

```text
ArmorPieceTruth {
  piece_id,
  slot_id,
  material_id,
  integrity_0_to_1,
  coverage_bones[],
  damage_events[],
  deformation_samples[],
  ring_states[] optional,
  crack_graph optional,
  detached_flag,
  exposed_injury_nodes[],
}
```

Presentation may render more detail than truth stores, but gameplay consequences derive only from truth state.

### 5. MotionBricks / Motion Presentation

Current files:

- `src/motion.rs`
- `src/combat.rs`
- `docs/MOTIONBRICKS-RETARGETING.md`
- `tools/export_motionbricks_onnx.py`
- `tools/export_backbones.py`

Current runtime path:

1. Load ONNX sessions from assets path.
2. Load NPY codebook.
3. Build synthetic idle encoder input.
4. Run VQVAE encoder.
5. Use quantized continuous output.
6. Decode to reconstructed `[1,T,413]` motion.
7. Parse G1 34-joint frames.
8. Retarget to 24 mannequin bones.
9. Upload matrices to renderer.

Target runtime path:

```text
CommittedCombatEvent
  → MotionIntentRequest
  → pose/root conditions
  → MotionBricks or prebaked/action clip fallback
  → 34-joint G1 motion
  → retarget map + IK + injury ROM clamps
  → 24+ mannequin skin matrices
  → render-only presentation
```

Important boundary:

- Motion may improve readability and style.
- Motion may not alter hit outcomes already resolved by combat truth.
- If motion changes apparent contact timing, the resolver and presentation are out of sync; fix the authoring/bridge, not the truth hash.

Motion risk areas observed:

- Code comments and docs disagree across older plans on encoder dimensions: some docs mention 241/329, current code uses 304/413. The next documentation/implementation unit should reconcile these with actual exported model metadata.
- ONNX files and NPY files are ignored by `.gitignore`, so runtime success depends on external generated artifacts not visible in tracked repo state.
- The current rendered clip is synthetic idle through VQVAE, not committed action-driven MotionBricks combat motion.

### 6. Asset Pipeline

Current files:

- `tools/extract_mesh.py`
- `tools/extract_fbx_mesh.py`
- `tools/extract_fbx_skinned.py`
- `tools/verify_skinned_bin.py`
- `assets/`
- `src/assets/`

Static mesh format currently used by `src/asset.rs`:

```text
u32 vertex_count
u32 index_count
f32 positions[vertex_count * 3]
f32 normals[vertex_count * 3]
f32 indices[index_count] as u32 bytes
f32 uvs[vertex_count * 2]
```

Note: `tools/extract_mesh.py` and `tools/extract_fbx_mesh.py` write UVs before indices, while current `load_binary` reads indices before UVs. The existing runtime may be using binaries generated by a different/fixed exporter or modified source. This mismatch must be documented as an asset-format risk before the next asset pipeline change.

SKM1 format currently used by `src/asset.rs` and verified by `tools/verify_skinned_bin.py`:

```text
b"SKM1"
u32 vertex_count
u32 index_count
u32 bone_count
vertices: pos[3], normal[3], uv[2]
indices: u32[index_count]
bones: name_len, name, parent, rest_local[16], inverse_bind[16]
skin: count, repeated joint_index/weight
```

ANM1 format:

```text
b"ANM1"
u32 bone_count
u16 fps
u32 frame_count
frames[frame][bone] = local_matrix[16]
```

Target asset pipeline:

```text
source FBX/GLB + texture set
  → extraction tool
  → deterministic binary mesh/skin/anim artifact
  → verifier
  → asset manifest
  → runtime loader
  → visual QA capture
```

Every asset that enters a build needs an asset manifest entry:

```text
AssetManifestEntry {
  asset_id,
  source_path,
  generated_paths[],
  source_tool,
  tool_version,
  vertex_count,
  index_count,
  bone_count optional,
  texture_dimensions[],
  license/source_note,
  gameplay_role,
  visual_readability_role,
}
```

### 7. Rendering

Current files:

- `src/renderer.rs`
- `src/shader.wgsl`
- `src/skin.wgsl`

Current renderer capabilities:

- wgpu render pipeline for static textured meshes;
- depth buffer;
- procedural ground texture;
- directional lighting;
- static arena objects in circular layout;
- a static mannequin object through old binary mesh path;
- a skinned mannequin through SKM1 path and joint storage buffer;
- separate skin shader.

Target renderer responsibilities:

- render state snapshots;
- support Player/Presentation/Developer modes;
- draw combat-readable silhouettes;
- support material and armor visual states;
- produce QA captures on demand;
- never alter simulation truth.

Renderer must eventually distinguish:

- gameplay camera vs free/debug camera;
- player mode UI vs debug overlays;
- live match rendering vs replay/fight-film rendering;
- static environment props vs combat-critical silhouettes;
- visual-only damage vs deterministic armor damage state.

### 8. Audio

Current docs mention audio as information-bearing but source has no audio system.

Target audio responsibilities:

- wind-up signatures per action;
- contact signatures per material/outcome;
- armor noise as gameplay read;
- injury/breathing/stamina cues;
- UI confirmation sounds;
- replay/fight-film mix.

Audio cannot be a polish-only stage. In this game, audio is part of action readability. It should arrive when motion readability becomes a gate, not after content complete.

### 9. UI / UX Modes

Hard requirement from project memory and docs:

- Developer mode may show diagnostics.
- Presentation mode may show curated evidence/capture overlays.
- Player mode must not show placeholder UI, debug HUD, evidence overlays, or development scoring.

Target mode contract:

```text
Mode::Developer:
  debug overlays, truth hash, frame timing, capture controls, action IDs
Mode::Presentation:
  clean build with optional curated labels for demos/reports
Mode::Player:
  only final/diegetic/minimal UI; no debug labels; no placeholder panels
```

Every UI element must specify which modes it is allowed in.

### 10. QA / Automation Interface

QA agents must use the same game surfaces a player or tester uses:

- input stream;
- screenshots/video;
- optional JSON state snapshot from a dedicated QA endpoint/log;
- replay recording;
- crash/build/test outputs.

QA agents must not become gameplay substitutes. A successful agentic playtest produces:

- replay input stream;
- capture set;
- bug reports or regression artifacts;
- pass/fail decision against acceptance criteria;
- evidence of what was actually played.

## Architecture Decision Records Needed

Create ADRs before implementing major changes:

1. ADR-001: Deterministic Combat Truth Boundary.
2. ADR-002: Replay and Truth Hash Contract.
3. ADR-003: PresentationBridge One-Way Data Flow.
4. ADR-004: Asset Binary Formats: static `.bin`, SKM1, ANM1.
5. ADR-005: MotionBricks Runtime vs Prebaked Fallback.
6. ADR-006: Player/Presentation/Developer UI Mode Separation.
7. ADR-007: QA Agent Interface and Capture Contract.
8. ADR-008: Armor Truth State vs Visual Damage State.
9. ADR-009: Network Input/Rollback Boundary.
10. ADR-010: Large Binary Asset Storage Policy.

## Drift and Risk Observations from File Review

Observed documentation/source drift:

- README says repo is code-empty; repo now has substantial Rust/wgpu/MotionBricks code.
- Milestone 2 says “Godot project compiles and runs”; current project is Rust/wgpu custom engine.
- Existing docs plan a minimal triangle shape prototype, while current source already includes textured 3D arena objects, skinned characters, and MotionBricks runtime work.
- `docs/.temp*` source notes are partially folded into docs but still exist as raw planning fragments.
- Asset loader and extractor format ordering may be inconsistent.
- Motion dimensions in older plan docs and current code may differ.
- `.gitignore` excludes ONNX/NPY artifacts required by current MotionBricks runtime, so reproducibility requires external generation steps.

These are not code-change requests. They are planning facts that must inform the phased plan.

## Golden Architecture Rules

1. If it changes match outcome, it belongs in combat truth.
2. If it changes only readability, it belongs in presentation.
3. If it must survive replay/save/load, serialize it as deterministic state.
4. If it is only visual evidence, it cannot be an acceptance gate by itself.
5. If a player cannot read the decision, the system failed even if the simulation is correct.
6. If a QA agent cannot reproduce a bug from input stream + seed + build, the test is not complete.
7. If a feature does not improve the YOMI exchange, cut it or defer it.
8. If renderer/asset work outpaces fun, stop and return to executable playtesting.
