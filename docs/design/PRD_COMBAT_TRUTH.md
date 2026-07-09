# PRD: Combat Truth

## 1. Purpose

Own the authoritative, deterministic state machine for a duel: match phase, fighter state, action lifecycle, geometry-accurate contact detection, and the transition from committed intent to resolved consequence.

## 2. Invariants

- Combat truth never depends on renderer, camera, sampled animation poses, audio, or frame time.
- Action timing and pose profile data may be derived from MotionBricks output but are authored into deterministic constants before runtime.
- Hitbox proxies must match visual geometry exactly; no oversized hitboxes or ghost hits are permitted.
- Contact detection uses geometry-accurate proxies from PRD_MOTION.md, not abstract spheres/capsules unless they exactly match a visual object.
- The same initial seed + input stream always produces the same final state and truth hash.
- Presentation may read snapshots; it may not write back into truth.
- Match phases advance only on deterministic events.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| input_event | InputEvent | PRD_INPUT.md | Committed action and stance per player |
| hitbox_proxies | HitboxProxy[] | PRD_MOTION.md | Geometry-accurate collision proxies per fighter |
| delta_time | fixed step | Platform shell | Fixed 60 Hz simulation step |
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
| contact_detected | { frame_index, proxy_pairs, contact_point, normal } | When geometry proxies intersect during active frames |
| exchange_resolved | { exchange_index, outcome } | Resolver finishes an exchange |
| match_ended | { winner_id, reason } | Incapacitation or time limit |

## 4. Data Flow

1. Combat truth receives locked input events.
2. State machine advances from Observe → Plan → Commit → Reveal → Resolve → Consequence.
3. During Active frames, combat truth receives hitbox proxies from PRD_MOTION.md and performs geometry-accurate contact detection.
4. On contact, PRD_ACTION_MATRIX.md is consulted for matchup outcome; PRD_ARMOR.md and PRD_INJURY.md apply deep material and tissue consequences.
5. A truth snapshot is emitted every simulation frame.
6. Match events are recorded by PRD_REPLAY.md.
7. Parity report is generated for QA comparison of hitbox vs visual geometry.

## 5. Control Flow

- **Who calls it:** Platform shell drives the fixed-step tick.
- **Tick rate:** 60 Hz fixed step, independent of render frame rate.
- **Threading model:** Main thread; all presentation reads snapshots asynchronously but never writes.

## 6. Error Handling

- **Fail-closed:** invalid state transitions are rejected and logged as deterministic errors.
- **Fail-closed:** missing required input at Commit advances to a forfeit/Disengage outcome.
- **Fail-closed:** hitbox/visual parity mismatch blocks the build until fixed.
- **Degradation:** if a resolver call returns unknown, combat truth falls back to "clash/reset" and emits a warning event.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|---|
| Simulation tick | <1 ms | 4 ms |
| Contact detection | <0.5 ms | 2 ms |
| Truth hash compute | <0.1 ms | 0.5 ms |
| Snapshot allocation | zero per frame | bounded pool |

## 8. Dependencies

- PRD_INPUT.md — receives committed actions.
- PRD_ACTION_MATRIX.md — resolves exchanges.
- PRD_INJURY.md — applies deep localized tissue injury.
- PRD_ARMOR.md — applies deep armor/material consequences.
- PRD_MOTION.md — provides geometry-accurate hitbox proxies.
- PRD_AI.md — receives AI state and snapshot for decision-making.
- PRD_REPLAY.md — records match events.

## 9. Open Questions

- Exact bit layout of truth hash.
- Continuous distance/position versus discrete bands.
- Handling of simultaneous incapacitation (double KO).
- Hitbox proxy update frequency (per frame vs per sub-step).

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Combat truth uses geometry-accurate hitbox proxies from MotionBricks poses; perfect parity with visual geometry is mandatory.
- **Rationale:** User canon amendment: no ghost hits or oversized hitboxes.
- **Blocker:** Hitbox proxy extraction from skinned meshes must be deterministic and fast; deep material/injury solvers must remain deterministic.
- **Status:** ACTIVE.
- **Next:** Implement a per-frame hitbox proxy extractor and parity checker for one action before expanding to full combat.
