# Just Dodge — Development Roadmap

## Overview

This roadmap defines the phased path from the current Rust/wgpu prototype through a shippable deterministic melee duel game with For Honor fidelity and YOMI Hustle game loop. Each phase has a duration, goal, deliverables, dependencies, risk, and exit gate. No phase begins before the prior phase's exit gate is met.

Current baseline: Rust/wgpu custom engine, textured arena renderer, orbital camera, skinned mannequin, MotionBricks ONNX integration work, and extensive design docs. The next phases pull the project back to executable-first verification while preserving useful existing work.

---

## Phase 0 — Canon Lock / Strategy Canvas
**Duration:** 1–3 days

**Goal:** Lock the design canon and make the project governable before further implementation.

**Deliverables:**
- `docs/design/GAME_CANON.md`
- `docs/design/GAME_CONCEPT.md`
- `docs/design/CORE_LOOPS.md`
- `docs/design/PRD_*.md` for all subsystems
- `docs/design/ROADMAP.md` (this document)
- `docs/design/VIRAL_CHECKLIST.md`
- `docs/design/AGENT_NOTES.md`
- Drift register reconciling existing docs with current code

**Verification:**
- Someone can explain the game from one sentence and one screenshot.
- All design docs are internally consistent with Rust/wgpu direction.
- `validate_design.py docs/design/` passes.

**Dependencies:** None.

**Risk:** Existing doc/code drift is larger than expected; canon lock takes too long.

**Exit Gate:** ✅ Canon and design docs approved.

---

## Phase 1 — Baseline Recovery: Playable Loop + Hitbox Parity Foundation
**Duration:** 3–5 weeks

**Goal:** Convert the current rendering/motion-heavy baseline into a playable 3-action match loop and prove that hitbox proxies can match visual geometry.

**Deliverables:**
- Refactored `src/combat.rs` into a deterministic state machine (see PRD_COMBAT_TRUTH.md).
- 3-action resolver (Strike/Block/Grab) using PRD_ACTION_MATRIX.md; timing derived from MotionBricks.
- Geometry-accurate hitbox proxy extraction from one MotionBricks pose (PRD_MOTION.md, PRD_COMBAT_TRUTH.md).
- Hitbox/visual parity test for one action (PRD_QA_AGENTIC.md).
- Player input via Z/X/C (PRD_INPUT.md).
- Simple AI opponent (PRD_AI.md).
- Minimal Player-mode UI (PRD_UI_UX.md).
- Replay recording and truth hash (PRD_REPLAY.md).
- Basic audio or visual cues (PRD_AUDIO.md).
- MotionBricks pipeline proves it can generate/observe a 3-action pose on demand.

**Explicitly Excluded:**
- Full 13 actions, deep armor/injury solvers, networking, new arenas, PBR/damage decals, Steam packaging beyond local runnable executable.

**Verification:**
- `cargo test` passes.
- `cargo run` launches the match loop.
- Human or agent completes 5 full matches.
- At least one replay produces the same truth hash on playback.
- Hitbox overlay matches visual geometry for the tested action within tolerance.
- Player can explain at least one "I read you" or "AI read me" moment.

**Dependencies:** Phase 0 complete.

**Risk:** Existing code mixes platform/camera/renderer/MotionBricks; refactoring and hitbox parity take longer than building from scratch.

**Exit Gate:** ✅ Shape/First Playable prototype report says CONTINUE and hitbox parity test passes for one action.

---

## Phase 2 — First Playable Hardening + Deterministic Simulation Foundation
**Duration:** 3–5 weeks

**Goal:** Make the 3-action duel robust enough to serve as the permanent truth foundation, with deterministic hooks for deep injury and armor.

**Deliverables:**
- Fixed-step simulation independent of rendering.
- Renderer-independent truth test.
- Deterministic seeded AI.
- Packaged Linux executable.
- Clean Player/Developer mode split.
- No placeholder UI in Player mode.
- Basic audio cues for commit/reveal/contact.
- Deterministic tissue injury prototype for one body region (PRD_INJURY.md).
- Deterministic material response prototype for one armor piece (PRD_ARMOR.md).
- Hitbox parity test expanded to all 3 actions.

**Verification:**
- Renderer enabled/disabled truth hashes match.
- Replay playback matches original hash.
- Packaged executable runs outside repo path.
- 10 internal matches produce at least one good exchange each.
- Deep injury and armor prototypes produce deterministic, hash-stable output for their one region/piece.
- Hitbox parity passes for all 3 actions.

**Dependencies:** Phase 1 complete.

**Risk:** Truth hash instability, deep solver determinism, or packaging issues consume the phase.

**Exit Gate:** ✅ First Playable milestone accepted and deterministic deep-simulation foundation proven.

---

## Phase 3 — 13-Action Matrix Prototype
**Duration:** 2–4 weeks

**Goal:** Determine whether the full 13-action set adds depth without overwhelming players.

**Deliverables:**
- Data-authored 13×13 matrix (PRD_ACTION_MATRIX.md).
- Action timing table derived from MotionBricks motion analysis.
- Stance system (high/low/neutral) per PRD_STANCE_TEMPO.md with martial-arts authenticity.
- Tempo gate.
- AI that can select all valid actions.
- Text or simple visual feedback for each action.
- Exhaustive matrix test coverage for all 169 cells.
- Hitbox parity test expanded to cover all 13 actions where geometry exists.

**Verification:**
- Matrix tests pass.
- Returning player intentionally uses at least 6 actions across 10 matches.
- Agentic playtest explores every action at least once.
- Player can name at least three counter relationships beyond Strike/Block/Grab.
- Hitbox parity passes for all authored action poses.

**Dependencies:** Phase 2 complete.

**Risk:** Players collapse back to 3 actions; matrix needs simplification or better tutorialization.

**Exit Gate:** ✅ 13-action prototype report says CONTINUE.

---

## Phase 4 — Motion, Camera, and Audio Readability
**Duration:** 4–6 weeks

**Goal:** Make opponent intent readable through authentic martial-arts pose, timing, camera, and audio.

**Deliverables:**
- Action-to-motion presentation bridge (PRD_MOTION.md).
- Distinct reveal tells for all 13 actions generated by MotionBricks with martial-arts authenticity.
- Weapon/hand/stance readability driven by MotionBricks output.
- First-person or readability-approved combat camera (PRD_CAMERA.md).
- Action wind-up/contact audio cues synchronized to MotionBricks phase markers (PRD_AUDIO.md).
- Visual QA capture set focused on MotionBricks motion quality and martial-arts authenticity.
- Hitbox parity maintained across all readable poses.

**Verification:**
- Blind test: player or visual agent identifies action from first 8 reveal frames at 80%+.
- Motion presentation does not alter truth hash.
- Camera does not hide opponent tell.
- No hitbox/visual parity violations in tested poses.

**Dependencies:** Phase 3 complete.

**Risk:** MotionBricks inference is too slow or produces unreadable or inauthentic poses; first-person camera hides tells. Prebaked clips are not the default solution.

**Exit Gate:** ✅ Readability prototype report says CONTINUE.

---

## Phase 5 — Deep Localized Injury and Armor Simulation
**Duration:** 5–8 weeks

**Goal:** Integrate deep tissue injury and deep material simulation so loadout and damage create readable counterplay at For Honor fidelity.

**Deliverables:**
- Full anatomical injury model: bone, muscle, tendon, ligament, organ, joint layers (PRD_INJURY.md).
- Full armor material simulation: cloth/leather PBD, chainmail constraint networks, plate FEM, Rune-Marble/bone brittle fracture (PRD_ARMOR.md).
- Six loadout classes with readable silhouette, sound, movement, and failure behavior.
- Persistent damage event records for replay and save/load.
- Material resistance table and residual-force routing.
- ROM/speed/noise modifiers.
- Visual/audio presentation of injury and armor state (PRD_RENDERER.md, PRD_AUDIO.md).
- AI awareness of injury and armor state.
- Hitbox parity maintained through deformed/destroyed armor states.

**Verification:**
- Returning player can explain why they changed weapon/action choice against at least 3 loadouts.
- Armor damage and injury state survive replay/save-load test.
- Heavy/light loadouts are visually and audibly distinguishable.
- Deep solvers produce deterministic truth hashes.
- Player changes tactics in response to injury in at least 5/10 matches.

**Dependencies:** Phase 4 complete.

**Risk:** Armor/injury perceived as hidden stat math; solvers break determinism or performance; hitbox parity fails on damaged geometry.

**Exit Gate:** ✅ Deep injury/armor prototype report says CONTINUE.

---

## Phase 6 — Replay Theater and Fight Film
**Duration:** 2–4 weeks

**Goal:** Turn deterministic matches into reviewable and shareable post-match artifacts without replacing gameplay.

**Deliverables:**
- Replay browser and frame stepping.
- Contact inspection with geometry-accurate hitbox visualization.
- Fight Film cinematic playback generated from replay (PRD_MOTION.md, PRD_CAMERA.md).
- Truth hash comparison.
- Exportable report/capture set for QA.

**Verification:**
- Any completed match can be replayed.
- Replay hash equals original hash.
- Fight Film has no write path into truth.
- Fight Film clearly shows hitbox contact and material/injury consequences.

**Dependencies:** Phase 5 complete.

**Risk:** Replay becomes more fun than playing; core loop needs attention.

**Exit Gate:** ✅ Replay/Fight Film QA accepted.

---

## Phase 7 — Tutorial and UX Completion
**Duration:** 2–4 weeks

**Goal:** Teach the game without external explanation.

**Deliverables:**
- Tutorial duel (PRD_TUTORIAL.md).
- Action introduction sequence.
- Read/commit/reveal explanation.
- Injury and armor tutorial steps.
- Controls menu.
- Options menu.
- Clean Player mode UI.

**Verification:**
- First-time player completes tutorial and a match unaided.
- Player can explain the core triangle, at least one advanced counter, and why armor/injury changed an exchange.
- No placeholder UI in Player mode.

**Dependencies:** Phase 6 complete.

**Risk:** Tutorial is too long or too shallow given deep systems.

**Exit Gate:** ✅ Tutorial playtest accepted.

---

## Phase 8 — Content Complete
**Duration:** 4–8 weeks

**Goal:** Scale content after systems are proven.

**Deliverables:**
- 3+ fighters, 6+ weapons, 6 armor/loadout identities, 3+ arenas.
- Local duel mode.
- AI duel mode.
- Replay/fight-film accessible from menus.
- Settings/options.
- Full sound design pass.
- PBR material pipeline and damage decal system.

**Verification:**
- 30+ minute play session remains fun.
- No placeholder UI in Player mode.
- Visual QA matrix passes for representative content combinations.
- Performance budget holds.
- Hitbox parity passes for all content combinations.

**Dependencies:** Phase 7 complete.

**Risk:** Content production outpaces system stability; asset pipeline blocks production.

**Exit Gate:** ✅ Content Complete milestone accepted.

---

## Phase 9 — Multiplayer / Rollback
**Duration:** 4–8 weeks

**Goal:** Add online 1v1 only after local game is fun, deterministic, and deep-simulation stable.

**Deliverables:**
- Remote input source (PRD_INPUT.md).
- State snapshot/restore and prediction/rollback (PRD_NETWORKING.md).
- Desync detection.
- Network test harness.
- Direct IP or minimal matchmaking.

**Verification:**
- 100+ online test matches.
- No unresolved desyncs.
- <100 ms perceived latency target.
- Deep simulation state serializes/restores deterministically for rollback.

**Dependencies:** Phase 8 complete.

**Risk:** Desyncs caused by deep simulation determinism or rollback artifacts corrupt experience.

**Exit Gate:** ✅ Multiplayer QA accepted.

---

## Phase 10 — Platform Packaging and Store Preparation
**Duration:** 3–6 weeks

**Goal:** Prepare clean builds and distribution pipeline.

**Deliverables:**
- Linux packaged executable.
- Windows build path.
- Clean asset packaging including MotionBricks ONNX/NPY artifacts.
- Version/changelog.
- Crash logs.
- Settings persistence.
- Store page material.
- Trailer/fight-film captures.

**Verification:**
- Clean machine install and run.
- No repo path required.
- Build includes required generated MotionBricks/assets and deep-simulation data.

**Dependencies:** Phase 9 complete (or Phase 8 if multiplayer deferred).

**Risk:** Asset packaging misses runtime-required ONNX/NPY artifacts or deep-simulation assets.

**Exit Gate:** ✅ Packaged build QA accepted.

---

## Phase 11 — Final QA and Release Candidate
**Duration:** 2–4 weeks

**Goal:** Stabilize the finished scoped game.

**Deliverables:**
- Build/test/regression suite.
- Replay hash suite.
- Visual QA matrix.
- Hitbox parity suite.
- Agentic playtest suite.
- Human playtest sessions.
- Performance budget pass.
- Accessibility/readability audit.
- Packaging verification.
- Risk register review.

**Verification:**
- All evidence artifacts pass.
- Known blocker list is documented.

**Dependencies:** Phase 10 complete.

**Risk:** Late-blockers from deep simulation or parity issues delay launch.

**Exit Gate:** ✅ Release candidate accepted.

---

## Phase 12 — Launch and Live Support
**Duration:** First 90 days live

**Goal:** Ship and maintain the game without breaking deterministic foundations.

**Deliverables:**
- Launch operations.
- Replay-compatible patch policy.
- Balance data review.
- Crash log collection.
- Content updates only after regression pass.
- Multiplayer monitoring if shipped.

**Verification:**
- Player reviews reflect core fantasy.
- Retention metrics meet target.
- No unintentional replay hash changes.
- Patch policy preserves deep-simulation replay compatibility.

**Dependencies:** Phase 11 complete.

**Risk:** Live ops burn out the solo developer.

**Exit Gate:** ✅ Live ops cadence proven.

---

## Cross-Phase Dependencies Diagram

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6
Canon       Loop +      Harden +    13-Action   Readability Deep        Replay
            Parity      Deep Sim    Matrix                  Injury/Armor

Phase 6 ──► Phase 7 ──► Phase 8 ──► Phase 9 ──► Phase 10 ──► Phase 11 ──► Phase 12
Replay      Tutorial    Content     Network     Packaging   Final QA    Launch
```

**Hard rule:** No phase may begin before the prior phase's exit gate is met. If an exit gate fails, return to the previous phase or cut scope.

---

## Subsystem PRD Reference

- [PRD_INPUT.md](PRD_INPUT.md)
- [PRD_COMBAT_TRUTH.md](PRD_COMBAT_TRUTH.md)
- [PRD_ACTION_MATRIX.md](PRD_ACTION_MATRIX.md)
- [PRD_STANCE_TEMPO.md](PRD_STANCE_TEMPO.md)
- [PRD_INJURY.md](PRD_INJURY.md)
- [PRD_ARMOR.md](PRD_ARMOR.md)
- [PRD_AI.md](PRD_AI.md)
- [PRD_REPLAY.md](PRD_REPLAY.md)
- [PRD_MOTION.md](PRD_MOTION.md)
- [PRD_CAMERA.md](PRD_CAMERA.md)
- [PRD_RENDERER.md](PRD_RENDERER.md)
- [PRD_AUDIO.md](PRD_AUDIO.md)
- [PRD_UI_UX.md](PRD_UI_UX.md)
- [PRD_ASSET_PIPELINE.md](PRD_ASSET_PIPELINE.md)
- [PRD_NETWORKING.md](PRD_NETWORKING.md)
- [PRD_TUTORIAL.md](PRD_TUTORIAL.md)
- [PRD_QA_AGENTIC.md](PRD_QA_AGENTIC.md)
