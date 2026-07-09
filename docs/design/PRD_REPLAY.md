# PRD: Replay and Truth Hash

## 1. Purpose

Record deterministic match input and state so any match can be reproduced, audited, and shared; provide a canonical truth hash that proves presentation never mutated combat state.

## 2. Invariants

- A replay is initial seed + ruleset version + input stream, not a video.
- Replaying the same inputs produces the same final truth hash.
- Fight Film reads replay events but cannot write to truth.
- Truth hash is computed only from combat truth state, never from presentation.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| match_event | MatchEvent | PRD_COMBAT_TRUTH.md | Phase changes, inputs, outcomes |
| truth_snapshot | TruthSnapshot | PRD_COMBAT_TRUTH.md | Per-frame deterministic state |
| ruleset_version | string | Static data | Versioned matrix and constants |
| initial_seed | u64 | Match setup | Deterministic RNG seed |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| replay_file | bytes | File system, PRD_UI_UX.md | Serialized replay |
| truth_hash | u64 / hex | PRD_QA_AGENTIC.md, PRD_UI_UX.md | Canonical match fingerprint |
| fight_film_events | EventStream | PRD_MOTION.md, PRD_CAMERA.md | Presentation-only cinematic data |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| replay_saved | { path, truth_hash } | Match end |
| hash_stable | { hash } | Every verification pass |

## 4. Data Flow

1. Match start writes header: version, build_id, ruleset_hash, asset_manifest_hash, initial_seed.
2. Every locked input and phase change is appended to the input stream.
3. Combat truth computes a rolling hash from deterministic state.
4. Match end writes final hash and optional cached truth events.
5. Replay validation re-runs combat truth from header+inputs and compares hash.
6. Fight Film consumes replay events for cinematic presentation.

## 5. Control Flow

- **Who calls it:** PRD_COMBAT_TRUTH.md emits events; replay subsystem records them.
- **Tick rate:** Per simulation step and per exchange.
- **Threading model:** Main thread; I/O buffered but flush-on-end.

## 6. Error Handling

- **Fail-closed:** replay file with mismatched version or ruleset is rejected.
- **Fail-closed:** hash mismatch during validation aborts and reports the first divergent frame.
- **Degradation:** if fight-film generation fails, replay viewer still works with default camera.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Hash compute | <0.1 ms/frame | 0.5 ms |
| Replay file size | <100 KB/match | 1 MB |
| Validation time | <1 s/match | 5 s |

## 8. Dependencies

- PRD_COMBAT_TRUTH.md — source of events and snapshots.
- PRD_INPUT.md — input events are recorded.
- PRD_MOTION.md, PRD_CAMERA.md — consumers of fight-film events.

## 9. Open Questions

- Hash algorithm (e.g., FNV-1a, xxHash, custom bit mix).
- Replay file format (binary, JSON, compressed).
- Asset manifest hash inclusion for version safety.

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Replay is deterministic input stream + truth hash; Fight Film is presentation-only.
- **Rationale:** Enables regression testing and sharing while preserving truth isolation.
- **Blocker:** None.
- **Status:** ACTIVE.
- **Next:** Add replay recording and hash computation to the First Playable prototype.
