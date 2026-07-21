# PRD: Armor, Material, and Damage Simulation

## 1. Purpose

Simulate armor and material response at For Honor-level physical fidelity, producing readable protection, mobility, noise, and failure consequences that create deep counterplay.

## 2. Invariants

- Armor truth state is deterministic and serializable.
- Gameplay authority is a bounded sparse per-object material/SDF field plus quantized cut, stress, connectivity and constraint events. Triangle meshes, neural deformation and asynchronous remeshing are presentation only.
- Rigid plates are semantic links with explicit sockets, pivots, limits and contact proxies; flexible straps/cloth may use XPBD/PBD or offline-derived deterministic correctives.
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
4. Truth updates the bounded material/SDF cells and quantized cut, stress, connectivity, ring, plate-constraint and fracture events.
5. Presentation consumes those events for cloth/leather motion, chainmail, plate dent/buckling, brittle fracture and asynchronous surface reconstruction; presentation geometry cannot author the event.
6. Residual force, exposed regions, and secondary fragments are returned to injury.
7. Capability modifiers are derived from mass, ROM clamps, and noise.

## 5. Control Flow

- **Who calls it:** PRD_COMBAT_TRUTH.md during Resolve phase after hitbox contact.
- **Tick rate:** Deterministic 120 Hz truth/contact updates plus exchange-level material events.
- **Threading model:** Canonical truth update in stable object/cell order. GPU/neural/mesh presentation work is asynchronous and cannot gate or mutate a truth tick.

## 6. Error Handling

- **Fail-open:** uncovered body regions pass full force to injury.
- **Fail-closed:** unknown material or missing material/SDF schema blocks the loadout or match before simulation.
- **Fail-closed:** non-deterministic material solver output aborts the match with a determinism error.
- **No silent degradation:** an unimplemented material remains unavailable; it is not silently replaced with bare skin or a weaker solver in a release candidate.

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

- Fixed-point/quantized representation and tolerances for material/SDF cells and connectivity events.
- How to serialize bounded fields, cut/stress events and connectivity graphs deterministically.
- Whether persistent armor damage survives across matches or resets per duel.

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Armor must be deep material simulation at For Honor fidelity (cloth/leather PBD, chainmail constraint networks, plate FEM, brittle fracture).
- **Rationale:** User canon amendment: deep material, injury, motion, and martial-arts simulations are required.
- **Blocker:** Determinism and truth-hash stability for solvers must be proven before netcode; performance budget is now much tighter.
- **Status:** ACTIVE.
- **Next:** Prototype one deterministic bounded material/SDF plate region and one chainmail ring-gap region, with quantized event/replay hashes, before expanding to all materials.

## 11. Character-equipment promotion dependency

Armor geometry, attachment and clearance follow `CHARACTER_EQUIPMENT_PROMOTION_CONTRACT.md`. Nearest-surface weight transfer cannot promote a rigid plate across a joint. A single front render cannot prove fit, reverse topology, stress-pose clearance, LOD, cooker preservation or live-runtime attachment.
