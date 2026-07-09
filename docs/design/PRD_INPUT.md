# PRD: Input

## 1. Purpose

Collect, timestamp, and route player intent into the combat simulation as discrete, frame-stamped input events, ensuring human, AI, replay, network, and test agents enter combat truth through the same logical path.

## 2. Invariants

- Input events are frame-stamped, not wall-clock stamped.
- Hidden intent cannot be altered after the Commit phase lock.
- AI and replay inputs use the same event shape as human inputs.
- The presentation layer receives no raw input events; it consumes combat state snapshots only.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| raw_key_event | winit event | Platform shell | Physical key press/release |
| raw_mouse_event | winit event | Platform shell | Mouse movement, buttons |
| ai_intent | InputEvent | PRD_AI.md | AI-chosen action per exchange |
| replay_intent | InputEvent | PRD_REPLAY.md | Recorded input stream playback |
| test_intent | InputEvent | PRD_QA_AGENTIC.md | Agent-driven or scripted input |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| validated_input_event | InputEvent | PRD_COMBAT_TRUTH.md | Frame-stamped, source-tagged intent |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| input_committed | { player_id, action_id, stance_id, frame_index } | When both players have locked intent for the current exchange |

## 4. Data Flow

1. Platform shell receives raw hardware events.
2. Input subsystem maps keys to action IDs and stances using a configurable binding table.
3. For human input, only pressed events generate action intents; holds do not repeat.
4. AI, replay, and test agents produce `InputEvent` directly, bypassing hardware mapping.
5. All events are tagged with source, player_id, frame_index, action_id, stance_id, and sequence_number.
6. Events are queued and consumed by combat truth at the start of the Commit phase.

## 5. Control Flow

- **Who calls it:** Platform shell calls per raw event; AI/replay/test agents push directly.
- **Tick rate:** Event-driven for hardware; per-exchange for AI/replay.
- **Threading model:** Single main thread; combat truth consumes events synchronously.

## 6. Error Handling

- **Fail-closed** for hidden intent: if a late input arrives after lock, it is discarded and logged.
- **Fail-open** for unknown keys: unbound keys are ignored.
- **Degradation:** if input source disconnects (e.g., network remote), combat truth treats missing input as a forfeit or Disengage depending on mode.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Input-to-event latency | <1 frame | 2 frames |
| Event queue memory | <1 KB | 16 KB |
| Bind lookup | O(1) | O(n) |

## 8. Dependencies

- PRD_COMBAT_TRUTH.md — consumes validated input events.
- PRD_AI.md — produces AI intent events.
- PRD_REPLAY.md — produces replay intent events.
- PRD_QA_AGENTIC.md — produces test/agent intent events.

## 9. Open Questions

- Default key bindings for 13 actions (prototype uses Z/X/C for Strike/Block/Grab).
- Hidden input method for local 2P (screen hiding, controller assignment, or phone-as-controller).

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Input events must be source-agnostic so AI, replay, network, and human players enter combat truth identically.
- **Rationale:** Preserves determinism and prevents AI/replay from bypassing rules.
- **Blocker:** None.
- **Status:** ACTIVE.
- **Next:** Define default bindings and hidden-input UX during First Playable implementation.
