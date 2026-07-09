# PRD: Action Matrix

## 1. Purpose

Author, store, and resolve the 13×13 simultaneous-reveal matchup matrix and action timing data so every action pair produces a deterministic contact type, initiative result, and deep consequence rule.

## 2. Invariants

- The matrix is data-authored, not hard-coded branching logic.
- Every cell resolves to a defined contact type and next-state flags.
- Timing is expressed in simulation frames; presentation interpolation cannot shift truth frames.
- Action timing profiles are derived from MotionBricks motion analysis and authored as deterministic constants.
- Contact type is informed by geometry-accurate hitbox intersection, not by abstract range checks.
- Consequence rules feed into deep armor and tissue injury systems.
- Intentional asymmetries are documented in the matrix metadata.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| action_a | ActionId | PRD_COMBAT_TRUTH.md | Committed action of player A |
| action_b | ActionId | PRD_COMBAT_TRUTH.md | Committed action of player B |
| stance_a | Stance | PRD_COMBAT_TRUTH.md | Stance of player A |
| stance_b | Stance | PRD_COMBAT_TRUTH.md | Stance of player B |
| contact_geometry | ContactGeometry | PRD_COMBAT_TRUTH.md | Hitbox intersection points, normals, active weapon/limb proxies |
| distance_state | DistanceBand | PRD_COMBAT_TRUTH.md | Discrete distance band |
| ruleset | RulesetVersion | Static data | Matrix version |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| matrix_result | MatrixResult | PRD_COMBAT_TRUTH.md | Contact type, initiative, hit location rule, force vector, tempo delta |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| matrix_cell_resolved | { action_a, action_b, contact_geometry, result } | Every exchange resolution |

## 4. Data Flow

1. Static data file defines the 13×13 matrix plus timing table.
2. At runtime, the matrix is loaded into memory as a lookup table.
3. Combat truth calls `resolve(action_a, action_b, context)` per exchange with geometry contact data.
4. The matrix returns contact type, initiative role, hit location rule, force vector, armor query rule, injury rule, tempo delta, and next-state flags.
5. Combat truth applies the result through PRD_ARMOR.md and PRD_INJURY.md.

## 5. Control Flow

- **Who calls it:** PRD_COMBAT_TRUTH.md during Resolve phase.
- **Tick rate:** On demand per exchange.
- **Threading model:** Main thread; read-only after load.

## 6. Error Handling

- **Fail-closed:** a missing or malformed matrix cell resolves to "unknown" and aborts the match with a deterministic error.
- **Scope reduction:** if full 13-action matrix is not yet authored, a reduced 3×3 prototype matrix is used, explicitly versioned separately. This is not a runtime fallback; it is a temporary scope reduction until all 13 actions are implemented.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Lookup latency | <1 µs | 10 µs |
| Memory footprint | <64 KB | 1 MB |
| Load time | <10 ms | 100 ms |

## 8. Dependencies

- PRD_COMBAT_TRUTH.md — caller, context provider, and hitbox contact source.
- PRD_INJURY.md — applies deep tissue injury rules from matrix result.
- PRD_ARMOR.md — applies deep armor/material rules from matrix result.
- PRD_STANCE_TEMPO.md — stance and tempo rules feed matrix context.

## 9. Open Questions

- File format for matrix data (TOML, JSON, custom).
- Whether distance/stance modify matrix cells or are separate filters.
- Exact timing values for all 13 actions derived from MotionBricks.

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Matrix must be data-authored, versioned separately, and feed deep armor/injury systems with geometry contact data.
- **Rationale:** User canon amendment: deep material/injury/motion simulations with perfect hitbox parity.
- **Blocker:** Geometry contact detection and force vectors must be deterministic and fast.
- **Status:** ACTIVE.
- **Next:** Author the reduced 3×3 prototype matrix with geometry contact rules for the First Playable prototype; expand to 13×13 for Vertical Slice.
