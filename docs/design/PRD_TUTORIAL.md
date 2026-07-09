# PRD: Tutorial

## 1. Purpose

Teach the YOMI read, commitment timing, and counter relationships without external explanation or lecture-heavy sequences.

## 2. Invariants

- Tutorial teaches reads, not just buttons.
- Each step is playable and falsifiable.
- Tutorial may reveal hidden intent for teaching but never in real matches.
- Player must complete a full match unaided before tutorial is considered passed.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| tutorial_script | TutorialStep[] | Static data | Ordered teaching steps |
| player_input | InputEvent | PRD_INPUT.md | Player actions during tutorial |
| combat_events | MatchEvent | PRD_COMBAT_TRUTH.md | Outcomes for feedback |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| tutorial_prompt | UIPrompt | PRD_UI_UX.md | Contextual instruction |
| tutorial_progress | Progress | Save system | Completion state |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| step_completed | { step_id, frame_index } | When player satisfies step condition |
| tutorial_completed | { final_score } | After unaided match |

## 4. Data Flow

1. Tutorial selects a scripted opponent and action sequence.
2. Player practices one action or concept at a time.
3. Feedback is immediate: why the action won or lost.
4. Steps progress from triangle to stance/tempo to injury/armor.
5. Final step is an unaided match against a forgiving AI.

## 5. Control Flow

- **Who calls it:** Platform shell in Tutorial mode.
- **Tick rate:** Per exchange.
- **Threading model:** Main thread.

## 6. Error Handling

- **Fail-open:** if player fails a step repeatedly, the tutorial offers a hint or repeats the step.
- **Fail-closed:** tutorial cannot modify real-match rules or unlock hidden actions early.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Step load time | <1 s | 5 s |
| Tutorial duration | <15 minutes | 30 minutes |

## 8. Dependencies

- PRD_COMBAT_TRUTH.md — runs tutorial matches.
- PRD_UI_UX.md — displays prompts.
- PRD_AI.md — scripted/tutorial AI.

## 9. Open Questions

- Whether tutorial is skippable after first completion.
- How to teach 13 actions without overwhelming beginners.
- Daily challenge or training mode scope.

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Tutorial is part of Content Complete milestone, after core loop and readability are proven.
- **Rationale:** Teaching is easier when the underlying loop is fun and readable.
- **Blocker:** None.
- **Status:** ACTIVE.
- **Next:** Design tutorial script after First Playable proves the 3-action loop.
