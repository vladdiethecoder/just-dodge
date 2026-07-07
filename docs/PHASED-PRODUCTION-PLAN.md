# Phased Production Plan — Just Dodge

## Purpose

This document expands the roadmap into a full scoped plan from current repository state through completed game, with evidence gates and QA/visual/agentic playtesting requirements at every phase.

This is a plan and documentation pass only. It does not authorize code edits.

## Planning Principles

1. Fun executable beats architecture elegance.
2. Local deterministic gameplay beats networking.
3. Readable combat beats visual fidelity.
4. Truth hash stability beats presentation polish.
5. Evidence beats claims.
6. Every phase ends in a playable build or a documented kill/pivot decision.
7. Agentic QA supports playtesting; it never replaces human play feel.

## Current State Assessment From Repository Review

The repository contains:

- Rust/wgpu/winit custom engine source.
- Static textured arena rendering.
- Vulkan backend forcing.
- Orbital camera.
- Static and skinned mannequin paths.
- MotionBricks ONNX Runtime integration in progress.
- Meshy-derived arena and mannequin assets.
- Skinned mesh/animation extraction and verification tools.
- Extensive combat, armor, MotionBricks, prototype, risk, and milestone docs.

The repository also contains drift:

- Some docs still describe an empty repo/minimal triangle prototype.
- Current source is already past that minimal prototype in renderer/assets but not yet past it in actual playable combat loop.
- Current source has significant presentation/motion work before a complete game loop is verified.

Therefore the next phases must preserve useful work while pulling the project back to game-driven executable verification.

## Phase 0 — Documentation and Architecture Lock

### Goal

Make the project understandable and governable before further implementation.

### Scope

- Architecture contract.
- Systems design contract.
- Full phase plan.
- QA/agentic visual playtesting protocol.
- File inventory/audit record.
- Documentation drift updates.

### Required Artifacts

- `docs/ARCHITECTURE.md`
- `docs/SYSTEMS-DESIGN.md`
- `docs/PHASED-PRODUCTION-PLAN.md`
- `docs/QA-AGENTIC-PLAYTESTING.md`
- `docs/FILE-INVENTORY-AUDIT.md`

### Acceptance Criteria

- All docs are internally consistent with Rust/wgpu custom engine direction.
- All existing file categories are acknowledged.
- No code files changed during this pass.
- Roadmap clearly reaches finished game and QA/visual/agentic verification.

### Verification

- `git diff --name-only` contains docs only for this pass.
- `git diff --check` passes.
- File inventory notes every tracked/untracked repo file reviewed in this pass.

## Phase 1 — Baseline Recovery: Playable Loop First

### Goal

Convert the current rendering/motion-heavy baseline into a playable 3-action match loop without expanding visual scope.

### Design Question

Can a player complete a fun Strike/Block/Grab match against AI in the current executable?

### Must-Have Systems

- 3-action combat truth resolver.
- Observe → Plan → Commit → Reveal → Resolve → Consequence → loop.
- Player input commit using Z/X/C.
- AI commit before reveal.
- Match result and restart.
- Minimal player-mode UI or equivalent readable presentation.
- Truth hash for a known match.
- Replay input stream for one match.

### Explicitly Excluded

- Full 13 actions.
- Armor simulation.
- Network code.
- New arena content.
- New renderer features not needed for readability.
- FEM/cloth/fracture.
- Steam/packaging polish beyond local runnable executable.

### Evidence Gate

- `cargo test` or equivalent unit tests pass.
- `cargo run` launches the match loop.
- A human or agent can play 5 full matches.
- At least one match produces a replay file/input log.
- Same replay produces same truth hash.
- Player can explain at least one “I read you” or “AI read me” moment.

### QA Playtest

Agentic playtest objective:

```text
Win or complete five matches using only Strike, Block, Grab, and Restart.
Record every input, screenshot each phase, and report confusion/blockers.
```

Human playtest objective:

```text
Play five matches without instructions. Afterward explain what Strike, Block, and Grab beat.
```

### Stop/Pivot Conditions

- If no “read” moments occur after 20 matches, revise timing/AI/reveal feedback before adding systems.
- If players do not understand phases, fix UI/feedback before adding actions.

## Phase 2 — First Playable Hardening

### Goal

Make the 3-action duel robust enough to serve as the permanent truth foundation.

### Must-Have Systems

- Fixed-step simulation.
- Renderer-independent truth test.
- Replay record/playback.
- Deterministic seeded AI.
- Packaged Linux executable.
- Clean Player/Developer mode split.
- No placeholder UI in Player mode.
- Basic audio or visible cues for commit/reveal/contact.

### Evidence Gate

- Renderer disabled/enabled truth hashes match.
- Replay can be played back from file and matches hash.
- Packaged executable runs outside repo path.
- 10 internal matches produce at least one good exchange each.
- No debug overlay in Player mode.

### QA Matrix

| Test | Method | Pass |
|---|---|---|
| Build | cargo build | exits 0 |
| Unit | combat/replay tests | all pass |
| Runtime smoke | launch executable | no crash |
| Replay | seed + input stream | identical hash |
| Visual phase capture | screenshot per phase | phase readable |
| Agentic playtest | 10 matches | completes, logs inputs |
| Human playtest | 3 sessions | unaided completion |

### Stop/Pivot Conditions

- If truth hash is unstable, stop all presentation work.
- If Player mode still needs debug labels, fix UX before expanding action set.

## Phase 3 — 13-Action Matrix Prototype

### Goal

Determine whether the full 13-action set adds depth without overwhelming players.

### Must-Have Systems

- Data-authored 13×13 matrix.
- Action timing table.
- Stance: high/low/neutral.
- Tempo gate.
- AI that can select all valid actions.
- Text or simple visual feedback for each action.
- Matrix test coverage for all 169 cells.

### Explicitly Excluded

- Full asset polish.
- Full armor simulation.
- Network rollback.
- Complex tutorial content beyond minimal explanation.

### Evidence Gate

- Exhaustive matrix tests pass.
- Returning player intentionally uses at least 6 actions across 10 matches.
- Agentic playtest explores every action at least once.
- No action is strictly dominated without documented reason.
- Player can name at least three counter relationships beyond Strike/Block/Grab.

### QA Agent Roles

- Explorer Agent: tries every action.
- Win-Seeking Agent: chooses actions to win.
- Confusion Agent: reports unclear phases/actions.
- Regression Agent: replays golden input streams.

### Stop/Pivot Conditions

- If players collapse back to 3 actions, simplify, gate, or tutorialize the matrix before adding motion/armor.
- If matrix is fun in text but unreadable visually, stop on motion/camera/audio readability.

## Phase 4 — Motion, Camera, and Audio Readability

### Goal

Make opponent intent readable through pose, timing, camera, and audio.

### Must-Have Systems

- Action-to-motion presentation bridge.
- Distinct reveal tells for actions.
- MotionBricks or prebaked/action-authored fallback clips.
- Weapon/hand/stance readability.
- First-person combat camera or revised readable camera.
- Action wind-up/contact audio cues.
- Visual QA capture set.

### Current Assets to Use

- Verified SKM1 male/female mannequin assets.
- Verified ANM1 running/merged clips as pipeline proof.
- Existing MotionBricks ONNX pipeline as research/possible runtime path.
- Existing arena meshes as cleanbox context only.

### Evidence Gate

- Blind test: player or visual agent identifies action from first 8 reveal frames at 80%+ for required action subset.
- No floating weapons/armor in target captures once equipment is introduced.
- Camera does not hide opponent tell.
- Motion presentation does not alter truth hash.
- Human reports readability improved over text/triangle phase.

### QA Visual Capture Set

For each tested action:

1. Observe phase.
2. Commit locked.
3. Reveal first frame.
4. Mid-startup.
5. Contact/active frame.
6. Consequence.
7. Recovery/return to observe.

Each capture is audited for:

- fighter identity;
- action pose;
- weapon/hand location;
- stance;
- contact readability;
- injury/armor if present;
- UI cleanliness;
- camera framing;
- lighting/silhouette.

### Stop/Pivot Conditions

- If MotionBricks inference is too slow or unstable, use prebaked clips and continue playable loop.
- If first-person camera fails readability, test alternate camera before adding content.

## Phase 5 — Localized Injury

### Goal

Make injury produce readable capability consequences without hiding outcome math.

### Must-Have Systems

- Body region state.
- Injury thresholds.
- Capability deltas: arm speed, grip, dodge, limp, vision/stamina.
- Presentation cues for injury.
- Replay serialization.
- AI awareness of injury.

### Evidence Gate

- Player changes tactics in response to injury in at least 5/10 matches.
- Injury is visible/audible enough to explain without debug overlay.
- Replay hash stable.
- Agentic playtest can intentionally target or observe at least 3 injury categories.

### Stop/Pivot Conditions

- If injury feels like hidden HP, reduce granularity or improve feedback before adding armor.

## Phase 6 — Armor and Loadout Readability

### Goal

Add armor/loadout classes that create readable counterplay.

### Must-Have Systems

- Six loadout classes.
- Armor slots mapped to body regions/bones.
- Simplified integrity state.
- Persistent damage event records.
- Material resistance table.
- ROM/speed/noise modifiers.
- Residual force routing to injury.
- Visual/audio presentation of armor state.

### Explicitly Excluded Initially

- Full FEM.
- Full cloth solver.
- Per-ring chainmail simulation.
- Runtime Voronoi fracture.

### Evidence Gate

- Returning player can explain why they changed weapon/action choice against at least 3 loadouts.
- Armor damage survives replay/save-load test where applicable.
- Heavy/light loadouts are visually distinguishable.
- Armor is not perceived as hidden stat math.

### Agentic Playtest

- Loadout Counter Agent: tries actions/weapons against each armor class.
- Readability Agent: identifies armor class and visible damage without state labels.
- Regression Agent: replays identical armor hit sequence and compares damage state hash.

### Stop/Pivot Conditions

- If armor choices are read as cosmetics, improve silhouette/material/audio or cut complexity.
- If armor math dominates YOMI, simplify material model.

## Phase 7 — Replay Theater and Fight Film

### Goal

Turn deterministic matches into reviewable and shareable post-match artifacts without replacing gameplay.

### Must-Have Systems

- Replay browser.
- Frame stepping.
- Contact inspection.
- Fight Film cinematic playback generated from replay.
- Truth hash comparison.
- Exportable report/capture set for QA.

### Evidence Gate

- Any completed match can be replayed.
- Replay hash equals original hash.
- Fight Film uses the same truth events but has no write path into truth.
- Player can use replay to understand at least one loss.

### Stop/Pivot Conditions

- If replay becomes more fun than playing, the match loop needs work.

## Phase 8 — Tutorial and UX Completion

### Goal

Teach the game without external explanation.

### Must-Have Systems

- Tutorial duel.
- Action introduction sequence.
- Read/commit/reveal explanation.
- Injury and armor tutorial steps.
- Controls menu.
- Options menu.
- Clean Player mode UI.

### Evidence Gate

- First-time player completes tutorial and a match unaided.
- Player can explain the core triangle and at least one advanced counter.
- No placeholder UI in Player mode.
- Agentic tutorial test completes without dead ends.

## Phase 9 — Content Complete

### Goal

Scale content after systems are proven.

### Must-Have Content

- 3+ fighters.
- 6+ weapons.
- 6 armor/loadout identities.
- 3+ arenas.
- Local duel mode.
- AI duel mode.
- Replay/fight-film accessible from menus.
- Settings/options.

### Evidence Gate

- 30+ minute play session remains fun.
- No placeholder UI in Player mode.
- Visual QA matrix passes for all fighter/weapon/loadout/arena combinations selected for release scope.
- Performance budget holds.

### Agentic QA Matrix

For each fighter × weapon × loadout representative subset:

- launch match;
- play N exchanges;
- capture observe/reveal/contact/consequence;
- verify fighter identity;
- verify weapon visible/attached;
- verify armor class readable;
- verify no crash/desync;
- save replay;
- replay hash check.

## Phase 10 — Multiplayer / Rollback

### Goal

Add online 1v1 only after local game is fun and deterministic.

### Must-Have Systems

- Remote input source.
- State snapshot/restore.
- Prediction/rollback.
- Desync detection.
- Network test harness.
- Direct IP or minimal matchmaking.

### Evidence Gate

- 100+ online test matches.
- No unresolved desyncs.
- <100 ms perceived latency target.
- Rollback artifacts do not corrupt presentation/truth boundary.

### Stop/Pivot Conditions

- If desync cannot be resolved, networking does not ship until deterministic root cause is fixed.

## Phase 11 — Platform Packaging and Store Preparation

### Goal

Prepare clean builds and distribution pipeline.

### Must-Have Systems

- Linux packaged executable.
- Windows build path.
- Clean asset packaging.
- Version/changelog.
- Crash logs.
- Settings persistence.
- Store page material.
- Trailer/fight-film captures.

### Evidence Gate

- Clean machine install and run.
- No repo path required.
- Build includes required generated MotionBricks/assets or documented fallback.
- QA pass from packaged build, not dev workspace.

## Phase 12 — Final QA and Release Candidate

### Goal

Stabilize the finished scoped game.

### Required QA

- Build/test/regression suite.
- Replay hash suite.
- Visual QA matrix.
- Agentic playtest suite.
- Human playtest sessions.
- Performance budget pass.
- Accessibility/readability audit.
- Packaging verification.
- Risk register review.

### Release Candidate Gate

Use concrete evidence only:

- executable path and build hash;
- test outputs;
- replay hash report;
- visual QA report;
- agentic playtest logs;
- human playtest notes;
- performance report;
- known blocker list.

Do not use readiness language unless separately requested.

## Phase 13 — Launch and Live Support

### Goal

Ship and maintain the game without breaking deterministic foundations.

### Post-Launch Systems

- replay-compatible patch policy;
- balance data review;
- bug triage;
- crash log collection;
- content updates only after regression pass;
- multiplayer monitoring if shipped.

### Patch Gate

- No patch ships if golden replay hashes change unintentionally.
- Balance changes that intentionally change truth must bump ruleset version.
- Old replays either remain playable under old ruleset or are explicitly marked incompatible.

## Cross-Phase Evidence Requirements

Every phase report must contain:

- phase goal;
- build/commit identifier;
- changed files summary;
- test commands and outputs;
- replay/hash evidence;
- screenshots/video/captures where relevant;
- agentic playtest log where relevant;
- human playtest notes where relevant;
- blockers;
- decision: continue, fix, simplify, defer, or cut.

## Cross-Phase Kill Criteria

Cut, defer, or redesign any feature that:

- does not improve the YOMI exchange;
- cannot be explained by a player after a match;
- destabilizes truth hash;
- requires ongoing manual tooling to prove it works;
- needs too much code before it can be playtested;
- makes combat less readable;
- is justified only by reference-game prestige.

## Final Scoped Game Definition

A fully scoped Just Dodge build includes:

- deterministic 1v1 local duel;
- first-person or readability-approved combat camera;
- 13-action YOMI matrix;
- stance, tempo, injury, armor/loadout counterplay;
- readable motion/audio/camera tells;
- deterministic AI personalities;
- tutorial duel;
- local duel mode;
- replay theater;
- fight-film generator;
- multiple fighters/weapons/arenas within scoped count;
- clean Player mode UI;
- visual/agentic/human QA evidence;
- packaged executable;
- optional rollback multiplayer only if deterministic local foundation passes.
