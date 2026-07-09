# PRD: AI Opponent

## 1. Purpose

Provide fair, readable, deterministic dueling pressure for single-player modes without cheating or hiding the core YOMI read.

## 2. Invariants

- AI commits before reveal and cannot inspect hidden player intent.
- AI uses the same action set, rules, and timing as the player.
- AI choices are deterministic under a seed.
- Difficulty is expressed through intentional mistakes and personality, not hidden bonuses.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| truth_snapshot | TruthSnapshot | PRD_COMBAT_TRUTH.md | Current deterministic combat state |
| personality | AiPersonality | Match setup | Aggressive, Defensive, Trickster, Mirror, etc. |
| seed | u64 | Match setup | Deterministic RNG seed |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| ai_input_event | InputEvent | PRD_INPUT.md | Frame-stamped AI action and stance |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| ai_decision | { action_id, stance_id, reason_tag } | When AI commits |

## 4. Data Flow

1. At Plan phase, AI receives the truth snapshot (without hidden player intent).
2. Personality weights bias action selection.
3. Memory histogram counters influence prediction.
4. Injury awareness on both sides adjusts risk tolerance.
5. Mistake rate injects intentional suboptimal reads at lower difficulty.
6. AI produces an InputEvent locked before reveal.

## 5. Control Flow

- **Who calls it:** PRD_COMBAT_TRUTH.md during Plan phase, before Commit lock.
- **Tick rate:** Per exchange.
- **Threading model:** Main thread.

## 6. Error Handling

- **Fail-open:** if AI fails to decide, it defaults to Neutral/Disengage.
- **Fail-closed:** if AI somehow accesses hidden player intent, the match is aborted with a determinism error.
- **Degradation:** lower difficulty increases mistake rate and simplifies memory window.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Decision latency | <0.1 ms | 1 ms |
| Memory per AI | <4 KB | 16 KB |

## 8. Dependencies

- PRD_COMBAT_TRUTH.md — provides snapshot and calls decision.
- PRD_INPUT.md — receives AI intent as a normal input event.
- PRD_ACTION_MATRIX.md — AI may query matrix for counter probabilities.

## 9. Open Questions

- Default mistake rate curve per difficulty.
- Whether AI should simulate human reaction limitations.
- How many personality profiles for Vertical Slice.

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** AI is deterministic, seed-based, and forbidden from reading hidden player intent.
- **Rationale:** Keeps single-player fair and replay-verifiable.
- **Blocker:** None.
- **Status:** ACTIVE.
- **Next:** Implement a random/counter-last-action AI for the Shape Prototype, then add personalities for First Playable.
