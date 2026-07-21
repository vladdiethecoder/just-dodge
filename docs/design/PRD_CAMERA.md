# PRD: Camera

## 1. Purpose

Frame the duel so opponent intent, action tells, and consequences are readable, while separating gameplay camera needs from developer/replay/fight-film cameras.

## 2. Invariants

- Camera transforms are presentation-only; they never feed into combat truth.
- Player mode uses a gameplay-approved camera; developer camera is forbidden in Player mode.
- Camera framing must account for MotionBricks-driven poses, weapon arcs, and contact keypoints.
- If first-person camera hides MotionBricks tells, the design must switch to a readable alternative before content is added.
- Player camera may never intersect or sit behind the player body, hair, armor or weapon, and may never obscure an essential opponent tell.
- First-person uses an approved eye/camera rig plus truth-isolated near-body culling or dedicated first-person presentation geometry derived from the same admitted pose packet.
- Replay and Fight Film cameras are deterministic and derived from truth events and MotionBricks contact keypoints.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| truth_snapshot | TruthSnapshot | PRD_COMBAT_TRUTH.md | Phase, action, stance, injury, contact |
| mode | CameraMode | Platform shell | Player, Replay, FightFilm, Developer |
| user_input | optional | Platform shell | Manual replay/inspection controls |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| view_matrix | Mat4 | PRD_RENDERER.md | World-to-view transform |
| projection_matrix | Mat4 | PRD_RENDERER.md | Perspective projection |
| camera_event | CameraEvent | PRD_AUDIO.md, PRD_UI_UX.md | Shake, cut notifications |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| camera_cut | { reason, target } | Fight Film or replay inspection |
| camera_shake | { magnitude, duration } | Contact event |

## 4. Data Flow

1. Platform shell selects camera mode.
2. Camera subsystem reads truth snapshot.
3. Player camera uses the approved eye frame, tracks the opponent relative to player position and phase, and applies the versioned near-body visibility policy.
4. Contact events trigger procedural shake.
5. Replay camera supports manual orbit and frame stepping.
6. Fight Film camera chooses cinematic cuts based on replay events.
7. Matrices are passed to renderer.

## 5. Control Flow

- **Who calls it:** Platform shell each render frame; combat truth events drive procedural motion.
- **Tick rate:** Render frame rate with interpolation.
- **Threading model:** Main thread.

## 6. Error Handling

- **Fail-closed in Player mode:** a missing target, invalid eye frame or body/weapon intersection blocks the camera candidate; it cannot silently use Developer camera.
- **Fail-closed:** Player mode cannot activate Developer camera.
- **Degradation:** if first-person fails readability test, switch to DuelReadableCamera.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Camera update | <0.1 ms/frame | 0.5 ms |
| Shake latency | <1 frame | 2 frames |

## 8. Dependencies

- PRD_COMBAT_TRUTH.md — source of state and events.
- PRD_RENDERER.md — consumes camera matrices.
- PRD_MOTION.md — informs framing relative to poses.

## 9. Open Questions

- First-person versus third-person/shoulder camera for Player mode.
- Field of view and peripheral-vision design for readability.
- Fight Film cut grammar.

## 10. Visual gate

Camera promotion follows `CHARACTER_EQUIPMENT_PROMOTION_CONTRACT.md` and `../quality/ADVERSARIAL_VISUAL_CONTRACT.md`. Require both approved FOV extremes, every declared stress pose, complete weapon arcs, zero body/weapon camera intersections, no hidden opponent tells and the blinded action-read gate from the actual player camera.

## 11. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Camera readability beats genre purity; first-person camera must pass an 80%+ blind action-read test or be replaced.
- **Rationale:** The YOMI read fails if the player cannot see opponent tells.
- **Blocker:** None.
- **Status:** ACTIVE.
- **Next:** Run readability prototype (Prototype 4) before finalizing Player camera.
