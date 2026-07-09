# PRD: Armor, Material, and Damage Simulation

## 1. Purpose

Simulate armor and material response at For Honor-level physical fidelity, producing readable protection, mobility, noise, and failure consequences that create deep counterplay.

## 2. Invariants

- Armor truth state is deterministic and serializable.
- Material response uses physics-backed models: XPBD/PBD for cloth/leather, rigid-body constraint networks for chainmail, corotational tetrahedral FEM for plate, brittle fracture for Rune-Marble and bone.
- Visual damage may exceed truth detail, but gameplay consequences derive only from truth state.
- Armor failure events are deterministic and data-authored, not random.
- Loadout classes are distinguishable by silhouette, sound, movement, and damage behavior.
- Persistent damage records survive replay and save/load.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| contact_event | ContactEvent | PRD_COMBAT_TRUTH.md | Force vector, damage type, hit location, contact area, angle |
| loadout | Loadout | Static data + match setup | Armor pieces, materials, weapon |
| ruleset | RulesetVersion | Static data | Material thresholds, resistance tables, fracture parameters |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| armor_result | ArmorResult | PRD_INJURY.md | Residual force, penetrated regions, secondary fragments |
| armor_state | ArmorState | PRD_COMBAT_TRUTH.md | Updated piece integrity, deformation, cracks, ring gaps |
| capability_modifiers | CapabilityDelta | PRD_COMBAT_TRUTH.md, PRD_MOTION.md | ROM, speed, noise, stamina modifiers |
| material_event | MaterialEvent | PRD_RENDERER.md, PRD_AUDIO.md | Dent, tear, crack, shatter for presentation |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| armor_damaged | { piece_id, damage_type, integrity_delta, deformation } | When a piece absorbs significant force |
| armor_destroyed | { piece_id, exposed_regions, fragments } | When integrity reaches zero |
| material_deflected | { piece_id, angle, force } | When force is below deflection threshold |
| ring_gap_opened | { piece_id, location } | Chainmail ring separation |
| crack_propagated | { piece_id, crack_graph_delta } | Rune-Marble/bone fracture growth |

## 4. Data Flow

1. Match setup initializes armor pieces from loadout with material properties.
2. On contact, armor subsystem queries the piece covering the hit location.
3. Effective force is computed from weapon mass, velocity, contact area, and contact angle.
4. Material solver evaluates response:
   - Cloth/leather: XPBD/PBD tear/crease.
   - Chainmail: rigid-body ring constraint network.
   - Plate: corotational tetrahedral FEM for dent/buckling/petal hole.
   - Rune-Marble/bone: brittle fracture and Voronoi shatter.
5. Integrity, deformation maps, crack graphs, and ring states are updated deterministically.
6. Residual force, exposed regions, and secondary fragments are returned to injury.
7. Capability modifiers are derived from mass, ROM clamps, and noise.

## 5. Control Flow

- **Who calls it:** PRD_COMBAT_TRUTH.md during Resolve phase after hitbox contact.
- **Tick rate:** Per exchange resolution; material solvers may run sub-steps for stability.
- **Threading model:** Main thread; GPU compute optional for cloth/chainmail/FEM.

## 6. Error Handling

- **Fail-open:** uncovered body regions pass full force to injury.
- **Fail-closed:** unknown material defaults to bare skin.
- **Fail-closed:** non-deterministic material solver output aborts the match with a determinism error.
- **Degradation:** if a full solver is not ready for a material, a deterministic simplified response is used temporarily and logged.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Armor resolution | <2 ms | 8 ms |
| FEM/cloth sub-step | <1 ms | 4 ms |
| State memory | <32 KB per fighter | 128 KB |

## 8. Dependencies

- PRD_COMBAT_TRUTH.md — caller and state owner.
- PRD_ACTION_MATRIX.md — provides contact parameters.
- PRD_INJURY.md — receives residual force and fragments.
- PRD_MOTION.md — receives ROM/noise modifiers.
- PRD_RENDERER.md — consumes material events and deformation state.
- PRD_AUDIO.md — consumes material events for impact sounds.

## 9. Open Questions

- Solver determinism strategy for cloth/FEM (fixed substeps, integer math, deterministic RNG).
- How to serialize deformation maps and crack graphs deterministically.
- Whether persistent armor damage survives across matches or resets per duel.

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Armor must be deep material simulation at For Honor fidelity (cloth/leather PBD, chainmail constraint networks, plate FEM, brittle fracture).
- **Rationale:** User canon amendment: deep material, injury, motion, and martial-arts simulations are required.
- **Blocker:** Determinism and truth-hash stability for solvers must be proven before netcode; performance budget is now much tighter.
- **Status:** ACTIVE.
- **Next:** Prototype a deterministic plate-FEM dent and chainmail ring-gap solver for one armor piece before expanding to all materials.
