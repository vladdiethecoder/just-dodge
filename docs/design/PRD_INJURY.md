# PRD: Injury and Tissue Damage

## 1. Purpose

Simulate localized anatomical injury at For Honor-level fidelity, producing deterministic capability modifiers and readable consequences without reducing combat to a single HP bar.

## 2. Invariants

- Injury is the result of the resolver, never the cause.
- Tissue damage is modeled at bone, muscle, tendon, ligament, organ, and joint levels where gameplay-relevant.
- Every injury region has structural, pain/shock, and bleed thresholds with capability consequences.
- Injury state is deterministic, part of the truth hash, and survives replay and save/load.
- Incapacitation rules are deterministic and data-authored.
- Visual injury presentation may exceed truth detail, but gameplay consequences derive only from truth state.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| contact_event | ContactEvent | PRD_COMBAT_TRUTH.md | Contact type, force vector, impact point, weapon data |
| armor_result | ArmorResult | PRD_ARMOR.md | Residual force, damage type, contact angle, exposed regions |
| fighter_anatomy | Anatomy | Static data | Skeleton, tissue layers, vital thresholds |
| ruleset | RulesetVersion | Static data | Injury thresholds, bleed rates, shock curves |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| injury_state | InjuryState | PRD_COMBAT_TRUTH.md | Updated anatomical region state |
| capability_deltas | CapabilityDelta | PRD_COMBAT_TRUTH.md, PRD_MOTION.md | Speed, ROM, grip, vision, balance, etc. |
| incapacitation_flag | bool | PRD_COMBAT_TRUTH.md | Whether fighter can no longer fight |
| tissue_event | TissueEvent | PRD_RENDERER.md, PRD_AUDIO.md | Wound description for presentation |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| injury_applied | { region, tissue_layers, severity, capability_changes } | After contact resolves |
| bleed_started | { region, rate } | When vascular damage exceeds threshold |
| shock_threshold_crossed | { player_id, new_shock_level } | When cumulative pain/shock changes tier |
| incapacitated | { player_id, reason } | When incapacitation rule triggers |
| joint_destroyed | { joint_id } | When joint structural integrity reaches zero |

## 4. Data Flow

1. Resolver produces a contact event with force vector, impact point, and weapon damage family.
2. Armor subsystem computes residual force, damage type, and contact angle.
3. Injury subsystem queries the anatomical region at the impact point.
4. Force is distributed through tissue layers: skin/subcutaneous, muscle, bone, organ/vital, joint.
5. Each layer has thresholds for bruise, tear, fracture, rupture, or severance.
6. Structural damage, pain/shock, and bleed are accumulated per region.
7. Capability deltas are derived from anatomical state (e.g., fractured forearm reduces grip, torn hamstring reduces dodge).
8. Incapacitation rules are evaluated.
9. Tissue events are emitted for presentation.

## 5. Control Flow

- **Who calls it:** PRD_COMBAT_TRUTH.md after armor and hitbox contact resolution.
- **Tick rate:** Per exchange resolution; bleed/shock may tick per simulation step during prolonged states (if enabled by ruleset).
- **Threading model:** Main thread.

## 6. Error Handling

- **Fail-closed:** unknown body region defaults to torso damage and logs an error.
- **Fail-open:** negligible residual force below a tissue threshold produces no injury to avoid noise.
- **Degradation:** if full tissue model is not yet implemented, a region-level simplified model may be used for early prototypes, explicitly marked as temporary.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Injury resolution | <0.5 ms | 2 ms |
| State memory | <8 KB per fighter | 32 KB |
| Tissue query | <0.1 ms | 0.5 ms |

## 8. Dependencies

- PRD_COMBAT_TRUTH.md — caller and state owner.
- PRD_ACTION_MATRIX.md — provides hit location and contact parameters.
- PRD_ARMOR.md — provides residual force and exposed regions.
- PRD_MOTION.md — consumes capability deltas and ROM clamps.
- PRD_RENDERER.md — consumes tissue events for wound visuals.
- PRD_AUDIO.md — consumes tissue events for injury sounds.

## 9. Open Questions

- Exact anatomical granularity (per-bone, per-muscle-group, or per-region).
- Whether to model bleeding over time or only instantaneous consequences.
- How to present deep tissue injury clearly without debug overlays.

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Injury must be deep tissue simulation at For Honor fidelity, not a simplified capability bar.
- **Rationale:** User canon amendment: deep material, injury, motion, and martial-arts simulations are required.
- **Blocker:** Deterministic tissue simulation and truth-hash stability must be proven early; visual wound fidelity must not outpace readable gameplay consequences.
- **Status:** ACTIVE.
- **Next:** Prototype a deterministic per-layer injury model for one body region before expanding to full anatomy.
