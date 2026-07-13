# PRD: Combat Truth

## 1. Purpose

Own the authoritative, deterministic state machine for a duel: match phase, fighter state, action lifecycle, geometry-accurate contact detection, and the transition from committed intent to resolved consequence.

## 2. Invariants

- Combat truth never depends on renderer, camera, sampled animation poses, audio, or frame time.
- Motion synthesis supplies only target motion. It never supplies a contact, impulse, block, parry, injury, or outcome.
- The shared physics world solves both fighters, weapons, armor, and arena together. Hitbox/mesh proxies are broad-phase or parity aids, never an action-matrix substitute.
- Every same-substep injury is evaluated from the same pre-contact state and applied at the next substep boundary without actor-order bias.
- The same initial seed + input stream always produces the same final state and truth hash.
- Presentation may read snapshots; it may not write back into truth.
- Match phases advance only on deterministic events.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| input_event | InputEvent | PRD_INPUT.md | Committed action and stance per player |
| target_buffers | MotionTargetBuffer[2] | Motion Synthesis | Read-only desired motion for each fighter |
| physical_contacts | BilateralContactPacket[] | Shared Duel Physics | Complete canonical 120 Hz manifold batch |
| delta_time | fixed step | Platform shell | Fixed 120 Hz physics substep; exactly two per action tick |
| ruleset | RulesetVersion | Static data | Matrix, timings, injury tables |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| truth_snapshot | TruthSnapshot | All presentation PRDs | Immutable combat state at a frame |
| match_event | MatchEvent | PRD_REPLAY.md, PRD_UI_UX.md | Phase changes, contact, injury |
| truth_hash | u64 / hex | PRD_REPLAY.md, PRD_QA_AGENTIC.md | Canonical deterministic hash |
| parity_report | ParityReport | PRD_QA_AGENTIC.md | Hitbox/visual mismatch evidence |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| phase_changed | { old, new, frame_index } | Match phase transition |
| contact_detected | { physics_tick, packets } | Shared world returns a canonical manifold batch |
| exchange_resolved | { exchange_index, outcome } | Resolver finishes an exchange |
| match_ended | { winner_id, reason } | Incapacitation or time limit |

## 4. Data Flow

1. Combat truth receives locked input events.
2. State machine advances from Observe → Plan → Commit → Reveal → Resolve → Consequence.
3. Shared Duel Physics samples both target buffers, applies capability-limited torques, and solves both fighters, weapons, armor, and arena in one world.
4. Combat truth derives labels from the complete physical packet batch; PRD_ARMOR.md and PRD_INJURY.md apply bilateral material/tissue consequences.
5. Capability deltas are merged and take effect at the next physics substep. A truth snapshot is emitted every 120 Hz substep.
6. Match events are recorded by PRD_REPLAY.md.
7. Parity report is generated for QA comparison of hitbox vs visual geometry.

## 5. Control Flow

- **Who calls it:** Platform shell drives the fixed-step tick.
- **Tick rate:** 120 Hz fixed physics substep, exactly two per 60 Hz action tick, independent of render frame rate.
- **Threading model:** Main thread; all presentation reads snapshots asynchronously but never writes.

## 6. Error Handling

- **Fail-closed:** invalid state transitions are rejected and logged as deterministic errors.
- **Fail-closed:** missing required input at Commit advances to a forfeit/Disengage outcome.
- **Fail-closed:** a missing physical contact batch holds Resolve; it is never converted into a synthetic whiff, hit, clash, or reset.
- **Fail-closed:** hitbox/visual parity mismatch blocks the build until fixed.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|---|
| Simulation tick | <1 ms | 4 ms |
| Contact detection | <0.5 ms | 2 ms |
| Truth hash compute | <0.1 ms | 0.5 ms |
| Snapshot allocation | zero per frame | bounded pool |

## 8. Dependencies

- PRD_INPUT.md — receives committed actions.
- PRD_SHARED_DUEL_PHYSICS.md — canonical clocks, physical ownership, bilateral packets, and label derivation.
- PRD_ACTION_MATRIX.md — action intent/timing metadata; never manufactures a physical result.
- PRD_INJURY.md — applies deep localized tissue injury.
- PRD_ARMOR.md — applies deep armor/material consequences.
- PRD_MOTION.md — provides motion targets and visual parity data only.
- PRD_AI.md — receives AI state and snapshot for decision-making.
- PRD_REPLAY.md — records match events.

## 9. Open Questions

- Exact bit layout of truth hash.
- Continuous distance/position versus discrete bands.
- Exact quantized bilateral packet layout and stable feature IDs.
- Deterministic solver selection after 120 Hz CCD/impulse convergence gates.

## 10. Agent Notes

### 2026-07-11 — Shared-world correction
- **Decision:** MotionBricks is an intent-to-target-motion planner. Shared physics is the only source of contact, impulse, injury, and outcome.
- **Rationale:** Generated keyframe error and lack of physical feasibility make clip-based combat resolution invalid.
- **Status:** ACTIVE. See PRD_SHARED_DUEL_PHYSICS.md for the ordering and acceptance gates.
