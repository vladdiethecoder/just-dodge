# Just Dodge — Aggregated Agent Notes

## Canon Lock Notes

### 2026-07-09 — @kimi
- **Decision:** Existing docs are source material; `docs/design/GAME_CANON.md` is the locked authority.
- **Rationale:** Resolves drift between README (code-empty), Milestone 2 (Godot), and current Rust/wgpu baseline.
- **Status:** ACTIVE.
- **Next:** Update older docs with deprecation pointers to the canon after user review.

### 2026-07-09 — @kimi
- **Decision:** The game will be developed to full potential and full fidelity regardless of single-developer constraints or engineering hardship.
- **Rationale:** User canon amendment: no fidelity compromises or fallbacks due to resource limitations.
- **Status:** ACTIVE.
- **Next:** Scope each phase to be achievable, but do not reduce fidelity targets; increase timeline or seek tooling/automation as needed.

## Subsystem PRD Index

This project uses the following subsystem PRDs. Each PRD contains its own Agent Notes section with active decisions, blockers, and next steps.

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

## Active Cross-Subsystem Decisions

### 2026-07-09 — @kimi
- **Decision:** MotionBricks is the sole animation, stance, pose, combat motion, and retargeting engine. Prebaked clips and motion fallbacks are disallowed.
- **Rationale:** User canon amendment: fallbacks are disallowed in game development; MotionBricks must be production-ready for every action.
- **Blocker:** ONNX/NPY artifacts are gitignored and must be generated/included in packaging. Any missing or broken MotionBricks output blocks the build/match.
- **Status:** ACTIVE.
- **Next:** Validate MotionBricks output for one complete action before scaling to all 13 actions; fix latency/artifact issues inside the MotionBricks pipeline.

### 2026-07-09 — @kimi
- **Decision:** The game targets For Honor visual and physical fidelity combined with YOMI Hustle simultaneous-reveal game loop.
- **Rationale:** User canon amendment: deep material, injury/damage, motion, and martial-arts simulations are required.
- **Blocker:** Scope and determinism are now much harder; solo-developer feasibility depends on disciplined phase gates.
- **Status:** ACTIVE.
- **Next:** Prototype one deep system at a time (hitbox parity, then one material solver, then one tissue layer) before scaling.

### 2026-07-09 — @kimi
- **Decision:** Hitbox proxies must match visual geometry exactly. No oversized hitboxes, no ghost hits, no phantom range.
- **Rationale:** User canon amendment: perfect hitbox parity is mandatory.
- **Blocker:** Requires per-frame or per-pose proxy extraction from MotionBricks-driven skinned meshes; must be deterministic and fast.
- **Status:** ACTIVE.
- **Next:** Build hitbox/visual overlay tool and parity test for Strike action in Phase 1.

### 2026-07-09 — @kimi
- **Decision:** Armor/loadout uses deep material simulation: cloth/leather PBD, chainmail constraint networks, plate FEM, Rune-Marble/bone brittle fracture.
- **Rationale:** User canon amendment: deep material simulation at For Honor fidelity.
- **Blocker:** Deterministic solvers must be proven before netcode; performance budget is tight.
- **Status:** ACTIVE.
- **Next:** Prototype deterministic plate-FEM dent and chainmail ring-gap solvers in Phase 2; scale in Phase 5.

### 2026-07-09 — @kimi
- **Decision:** Injury uses deep tissue simulation: bone, muscle, tendon, ligament, organ, and joint layers.
- **Rationale:** User canon amendment: deep injury/damage simulation.
- **Blocker:** Must avoid hidden-HP feel; presentation must make consequences readable.
- **Status:** ACTIVE.
- **Next:** Prototype a deterministic per-layer injury model for one body region in Phase 2; scale in Phase 5.

### 2026-07-09 — @kimi
- **Decision:** Networking is gated after Content Complete; input abstraction must support remote injection from First Playable.
- **Rationale:** Deep simulation determinism must be proven before rollback netcode can be trusted.
- **Status:** ACTIVE.
- **Next:** Refactor input abstraction during Phase 1/2.

### 2026-07-09 — @kimi
- **Decision:** First-person camera must pass an 80%+ blind action-read test; otherwise switch to a readability-approved camera.
- **Rationale:** Camera readability beats genre purity.
- **Status:** ACTIVE.
- **Next:** Run blind readability test in Phase 4.

## Known Drift and Risks

| Item | Source | Status | Owner |
|---|---|---|---|
| Asset loader/extractor format ordering | `src/asset.rs` vs `tools/extract_mesh.py` | ACTIVE | Developer |
| Motion dimensions mismatch | Older docs (241/329) vs code (304/413) | ACTIVE | Developer |
| ONNX/NPY runtime artifacts not tracked | `.gitignore` | ACTIVE | Developer |
| `src/main.rs` mixes shell/camera/renderer/MotionBricks | Architecture debt | ACTIVE | Developer |
| Player-mode UI not yet implemented | Source inspection | ACTIVE | Developer |
| Deep solver determinism unproven | New canon amendment | ACTIVE | Developer |
| Hitbox parity tooling does not exist | New canon amendment | ACTIVE | Developer |
| Solo-developer scope vs For Honor fidelity | New canon amendment | ACTIVE | Developer + Mentor |

## Next Implementation Target

After design review approval, the next work unit is Phase 1: Baseline Recovery / Playable Loop + Hitbox Parity Foundation. The goal is a Strike/Block/Grab match loop against simple AI with replay, truth hash, and a hitbox/visual parity proof for one action. See [PRD_COMBAT_TRUTH.md](PRD_COMBAT_TRUTH.md), [PRD_MOTION.md](PRD_MOTION.md), [PRD_ACTION_MATRIX.md](PRD_ACTION_MATRIX.md), [PRD_INPUT.md](PRD_INPUT.md), and [PRD_QA_AGENTIC.md](PRD_QA_AGENTIC.md).
