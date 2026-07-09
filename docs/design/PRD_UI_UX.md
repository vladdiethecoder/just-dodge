# PRD: UI and UX

## 1. Purpose

Communicate match phase, intent confirmation, consequence, and menu navigation with minimal, diegetic, or final-quality UI that never breaks Player-mode cleanliness.

## 2. Invariants

- Player mode shows no debug overlays, placeholder panels, raw IDs, or evidence scoring.
- Developer mode may show diagnostics; Presentation mode may show curated labels.
- Every UI element specifies which modes it is allowed in.
- UI never receives hidden intent; it reads truth snapshots only.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| truth_snapshot | TruthSnapshot | PRD_COMBAT_TRUTH.md | Phase, health/injury, tempo, result |
| mode | AppMode | Platform shell | Player, Presentation, Developer |
| menu_action | MenuAction | Input/Platform shell | Navigation, settings, replay selection |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| ui_draw_commands | UIDrawCmds | PRD_RENDERER.md | Text, panels, cursors |
| menu_state | MenuState | Platform shell | Current screen/flow |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| phase_label_shown | { phase, duration } | Phase transition in Player mode |
| result_shown | { winner, reason } | Match end |

## 4. Data Flow

1. Platform shell sets app mode.
2. UI subsystem reads truth snapshot and menu state.
3. Player mode draws only approved elements: phase hints, minimal injury/tempo, result text, menus.
4. Developer mode adds overlays: hash, FPS, IDs, skeleton, replay cursor.
5. Draw commands are sent to renderer.

## 5. Control Flow

- **Who calls it:** Platform shell per render frame.
- **Tick rate:** Render frame rate.
- **Threading model:** Main thread.

## 6. Error Handling

- **Fail-closed:** a UI element without an approved mode list is hidden in Player mode.
- **Fail-open:** missing font/glyph falls back to system font or placeholder glyph temporarily.
- **Degradation:** minimal text labels replace rich UI when resources fail.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| UI render | <1 ms/frame | 4 ms |
| Font atlas | <32 MB | 128 MB |

## 8. Dependencies

- PRD_COMBAT_TRUTH.md — truth snapshots.
- PRD_RENDERER.md — draw commands consumer.
- PRD_REPLAY.md — replay/fight-film menu data.

## 9. Open Questions

- Text rendering solution (custom, egui, glyphon).
- Diegetic UI versus minimal HUD.
- Menu flow for tutorial, local 2P, replay theater.

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Player mode is strictly clean; debug UI is gated behind mode flags.
- **Rationale:** Prevents placeholder UI from becoming permanent, per OATHYARD lesson.
- **Blocker:** None.
- **Status:** ACTIVE.
- **Next:** Implement a minimal Player-mode HUD for the First Playable prototype.
