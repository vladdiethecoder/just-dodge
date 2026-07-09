# PRD: Audio

## 1. Purpose

Provide information-bearing sound that helps players read actions, contact, material, and state before and during contact.

## 2. Invariants

- Audio is presentation-only; it never changes combat truth.
- Every action has a distinct wind-up signature synchronized to MotionBricks motion events.
- Contact sounds vary by material and outcome.
- Audio cues are deterministic events triggered by truth state changes and MotionBricks phase markers.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| audio_request | AudioRequest | PRD_MOTION.md, PRD_COMBAT_TRUTH.md | Wind-up, contact, material cues |
| mode | AudioMode | Platform shell | Player, Presentation, Developer |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| mixed_audio | samples | Platform audio backend | Final audio stream |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| audio_cue_played | { cue_id, frame_index } | Every cue trigger |

## 4. Data Flow

1. Combat truth and motion generate audio requests at phase transitions and contact events.
2. Audio subsystem selects cue by action, material, and outcome.
3. Cues are mixed with ambient arena sound.
4. Player mode receives final mix; Developer mode may isolate channels.

## 5. Control Flow

- **Who calls it:** PRD_COMBAT_TRUTH.md and PRD_MOTION.md emit requests.
- **Tick rate:** Audio thread or callback at device sample rate.
- **Threading model:** Dedicated audio thread or callback.

## 6. Error Handling

- **Fail-open:** missing cue is silent; gameplay continues.
- **Fail-closed:** audio latency must not delay simulation.
- **Degradation:** simplified beeps substitute final cues during prototypes.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Audio latency | <50 ms | 100 ms |
| Mix CPU | <1 ms/frame | 4 ms |
| Memory | <64 MB | 256 MB |

## 8. Dependencies

- PRD_COMBAT_TRUTH.md — contact and phase events.
- PRD_MOTION.md — wind-up and movement cues.
- PRD_ARMOR.md — material/noise data.

## 9. Open Questions

- Audio backend choice (rodio vs kira).
- Spatial audio requirements for first-person camera.
- Accessibility options (visualize sound, subtitles).

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Audio is a readability system, not a polish pass; it ships with the readable-motion milestone.
- **Rationale:** Sound is part of the YOMI read.
- **Blocker:** None.
- **Status:** ACTIVE.
- **Next:** Add beep cues for commit/reveal/contact in the First Playable prototype.
