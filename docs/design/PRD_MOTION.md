# PRD: Motion and Martial-Arts Animation

## 1. Purpose

Generate authentic, readable martial-arts motion at For Honor-level fidelity using MotionBricks as the sole engine, translating committed combat events into character poses, weapon arcs, and movement while preserving the truth/presentation boundary.

## 2. Invariants

- Motion is presentation-only; it never changes action IDs, timing, hit outcomes, injury values, or truth hashes.
- MotionBricks is the sole source for all combat stances, actions, transitions, and retargeting.
- Every action must have a unique first-six-frame tell after reveal.
- Motion must read as authentic martial arts: correct weight transfer, hip drive, weapon arcs, and recovery.
- Motion may read combat truth (action, stance, injury, armor ROM) but may not read hidden intent.
- Prebaked action clips and motion fallbacks are disallowed. MotionBricks must produce valid output for every required action.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| truth_snapshot | TruthSnapshot | PRD_COMBAT_TRUTH.md | Current combat state including action, stance, injury |
| motion_request | MotionRequest | PRD_COMBAT_TRUTH.md | Action transition, timing, intent class |
| armor_modifiers | CapabilityDelta | PRD_ARMOR.md | ROM/noise/mass modifiers |
| injury_modifiers | CapabilityDelta | PRD_INJURY.md | ROM/posture modifiers |
| weapon_profile | WeaponProfile | Static data | Weapon mass, length, grip style |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| skin_matrices | Mat4[] | PRD_RENDERER.md | Per-bone transform matrices |
| weapon_transform | Mat4 | PRD_RENDERER.md | Weapon socket transform |
| plan_proposal | NeuralPlanPacketCandidate | Packet validator | Versioned, quantized proposal; not truth until admitted and hash-bound |
| presentation_proxies | ProxyAov[] | PRD_RENDERER.md, PRD_QA_AGENTIC.md | Visualization of truth-owned proxies from the same admitted packet sample |
| audio_cue_request | AudioCue | PRD_AUDIO.md | Wind-up/contact event requests |
| contact_keypoints | Keypoint[] | PRD_CAMERA.md | Hands, feet, weapon tip for framing |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| pose_transition_started | { action_id, plan_packet_id, duration_ticks } | When an admitted live plan begins |
| contact_pose_held | { action_id, frame_index } | On active/contact frame |
| martial_arts_quality_fail | { reason } | When motion fails authenticity audit |

## 4. Data Flow

1. Combat truth emits a motion request at reveal.
2. Motion subsystem queries MotionBricks for the action/stance pose and transition, conditioned on weapon, stance, injury, and armor.
3. 29-joint MotionBricks output is retargeted to the ~120-bone mannequin skeleton.
4. Spine, fingers and toes are solved from live biomechanical/contact constraints on the admitted rig; local-axis heuristics, authored grip poses and pose-bank lookups are forbidden.
5. Weapon arc and hip rotation are validated against weapon profile.
6. Injury and armor ROM clamps are applied as presentation modifiers.
7. Combat truth evaluates its canonical body/weapon/armor contact proxies from the admitted quantized packet and truth-owned geometry. Renderer output is never read back.
8. Final skin matrices, weapon transform, contact keypoints and proxy AOVs are sent to renderer, camera and QA from that same sample.

## 5. Control Flow

- **Who calls it:** the asynchronous plan service produces candidates; the packet validator admits canonical quantized packets; combat truth consumes admitted/recorded packets without reading presentation state.
- **Tick rate:** Asynchronous plan horizons feeding quantized samples at the deterministic 120 Hz contact cadence; rendering interpolates admitted samples without changing truth bytes.
- **Threading model:** Neural inference runs outside the truth tick and publishes complete validated packets through the versioned buffer. Stale, missing or mismatched packets fail closed; the truth tick never synchronously waits for inference.

## 6. Error Handling

- **Fail-closed:** missing or unloadable MotionBricks output blocks the match and is treated as a build/runtime defect.
- **Fail-closed:** if motion would alter truth timing or hitbox parity, the motion request is rejected.
- **Degradation:** MotionBricks latency/artifact/martial-arts quality issues are fixed by optimizing inference, retargeting, model export, or conditioning data. No substitute motion source is permitted.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Motion generation | <8 ms/action | 16 ms |
| Retarget + IK + hitbox proxy update | <4 ms/frame | 12 ms |
| Memory per skeleton | <2 MB | 8 MB |

## 8. Dependencies

- PRD_COMBAT_TRUTH.md — source of motion requests and state; consumer of hitbox proxies.
- PRD_RENDERER.md — consumes matrices.
- PRD_CAMERA.md — consumes contact keypoints.
- PRD_AUDIO.md — receives wind-up/contact cue requests.
- PRD_ARMOR.md, PRD_INJURY.md — provide capability modifiers.

## 9. Open Questions

- Runtime MotionBricks latency and artifact quality at martial-arts fidelity.
- Cost and quantization of truth-owned proxy evaluation from each admitted packet sample.
- Live recurrent/sequence conditioning for hold, idle and recovery without authored loops, discrete pose banks or baked clips.

## 10. Character, grip, and equipment dependency

Every body/armor/weapon pose follows `CHARACTER_EQUIPMENT_PROMOTION_CONTRACT.md`. The sword socket and finger/hand solution must prove measured handle contact, anatomical volume, causal response to grip geometry and parity across the declared stress/action suite. Proximity to the wrist is not grip evidence.

## 11. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** MotionBricks is the sole motion engine; prebaked clips and motion fallbacks are disallowed.
- **Rationale:** User canon amendment: fallbacks are disallowed in game development; MotionBricks must be production-ready for every action.
- **Blocker:** ONNX/NPY artifacts are gitignored and must be generated/included in packaging. Any missing or broken MotionBricks output blocks the build/match.
- **Status:** ACTIVE.
- **Next:** Validate MotionBricks output for one complete action (e.g., Strike) including hip drive, weapon arc, and hitbox parity before scaling to all 13 actions.
