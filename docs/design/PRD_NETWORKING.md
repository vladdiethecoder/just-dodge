# PRD: Networking and Rollback

## 1. Purpose

Add online 1v1 play only after local gameplay is deterministic and fun, using rollback netcode that preserves the combat-truth boundary.

## 2. Invariants

- Networking is added only after local vertical slice is accepted.
- Remote input is injected through the same path as local input.
- Simulation remains deterministic; rollback restores state from snapshots.
- Desyncs are detected by truth hash and treated as P0 bugs.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| remote_input | InputEvent | Network layer | Opponent input with frame delay |
| local_input | InputEvent | PRD_INPUT.md | Local player input |
| state_snapshot | bytes | PRD_COMBAT_TRUTH.md | Compressed deterministic state |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| predicted_input | InputEvent | PRD_COMBAT_TRUTH.md | Predicted opponent input until real input arrives |
| rollback_request | RollbackRequest | PRD_COMBAT_TRUTH.md | Frame to restore and re-simulate |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| desync_detected | { frame_index, local_hash, remote_hash } | When truth hashes disagree |

## 4. Data Flow

1. Local and remote inputs are queued with frame stamps.
2. Missing remote input is predicted from last known input.
3. Combat truth simulates forward.
4. When remote input arrives late, the latest state snapshot is restored.
5. Simulation is re-run from that frame with corrected input.
6. Truth hash is compared periodically to detect desync.

## 5. Control Flow

- **Who calls it:** Network layer and platform shell.
- **Tick rate:** Per simulation step.
- **Threading model:** Network I/O on separate thread; input injection on main thread.

## 6. Error Handling

- **Fail-closed:** desync aborts the match and reports both replay files.
- **Fail-open:** packet loss is handled by prediction and rollback.
- **Degradation:** if rollback quality is poor, reduce input delay or disable ranked play.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Rollback perceived latency | <3 frames | 6 frames |
| State snapshot size | <64 KB | 256 KB |
| Snapshot save/restore | <1 ms | 4 ms |

## 8. Dependencies

- PRD_COMBAT_TRUTH.md — owns deterministic state and snapshots.
- PRD_INPUT.md — receives remote input as normal input.
- PRD_REPLAY.md — replay used for desync investigation.

## 9. Open Questions

- Matchmaking versus direct IP.
- Steam networking integration.
- Input delay and frame delay values.

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Networking is gated after Vertical Slice; no netcode before local game is fun.
- **Rationale:** Avoids building netcode for a game that may need design pivots.
- **Blocker:** None.
- **Status:** ACTIVE.
- **Next:** Refactor input abstraction during First Playable to support remote injection later.
