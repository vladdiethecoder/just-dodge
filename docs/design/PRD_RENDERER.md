# PRD: Renderer

## 1. Purpose

Draw fighters, weapons, armor, and arena at For Honor visual fidelity with silhouette readability, material identity, deep damage visualization, and hitbox/visual parity support, while never mutating combat truth.

## 2. Invariants

- Renderer reads only presentation snapshots; it never writes to combat truth.
- Player mode shows no debug overlays, placeholder UI, or evidence scoring.
- Developer mode may overlay hitbox proxies and parity visualization for QA.
- Static arena is context only; combat-critical silhouettes and MotionBricks-driven poses take priority.
- Visual damage (dents, cracks, tears, blood) reflects deterministic truth state; gameplay consequences are not computed here.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| render_snapshot | RenderSnapshot | Presentation-truth bridge | Meshes, transforms, materials, damage state, UI requests |
| camera_matrices | View + Projection | PRD_CAMERA.md | Camera state |
| mode | RenderMode | Platform shell | Player, Presentation, Developer |
| hitbox_overlays | HitboxProxy[] | PRD_MOTION.md | Optional proxy geometry for Developer mode |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| frame_buffer | pixels | Window surface | Final rendered frame |
| capture_png | bytes | PRD_QA_AGENTIC.md | On-demand screenshot capture |
| timing_debug | FrameTiming | Developer UI only | GPU/frame timing in Developer mode |
| parity_capture | PNG | PRD_QA_AGENTIC.md | Render + hitbox overlay frame |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| frame_rendered | { frame_index, draw_calls } | Every rendered frame |
| capture_taken | { path, frame_index } | QA capture trigger |

## 4. Data Flow

1. Platform shell requests a frame.
2. Renderer receives render snapshot, camera matrices, and mode.
3. Static arena, skinned fighters, weapons, armor damage state, and VFX are drawn with depth buffer.
4. Developer mode may render hitbox proxy wireframes for parity comparison.
5. UI layer is drawn according to mode rules.
6. Frame is presented; QA captures are saved on request.

## 5. Control Flow

- **Who calls it:** Platform shell per render frame.
- **Tick rate:** Uncapped render frame rate, decoupled from 60 Hz simulation.
- **Threading model:** Main thread; GPU work submitted via wgpu queue.

## 6. Error Handling

- **Fail-open:** missing texture falls back to checkerboard/magenta.
- **Fail-closed:** renderer crash must not corrupt combat truth; simulation continues and can be replayed.
- **Degradation:** low quality settings reduce environment detail, never fighter readability or hitbox parity evidence.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Frame time 1080p | <16 ms | 33 ms |
| Draw calls | <1000 | 3000 |
| Texture memory | <1 GB | 2 GB |
| Damage decal memory | <128 MB | 512 MB |

## 8. Dependencies

- PRD_CAMERA.md — view/projection matrices.
- PRD_MOTION.md — skin matrices, weapon transforms, hitbox proxies.
- PRD_ARMOR.md, PRD_INJURY.md — damage state for visuals.
- PRD_ASSET_PIPELINE.md — meshes, textures, materials.
- PRD_UI_UX.md — UI draw requests.

## 9. Open Questions

- Lighting model needed for silhouette readability and material identity.
- PBR material pipeline and damage decal system.
- Render scaling and quality settings.

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Renderer targets For Honor visual fidelity with hitbox parity overlays and deep damage visualization.
- **Rationale:** User canon amendment: For Honor fidelity with perfect hitboxes.
- **Blocker:** Current wgpu pipeline is basic; PBR, damage decals, and hitbox overlays must be built.
- **Status:** ACTIVE.
- **Next:** Audit current renderer and plan PBR/damage/hitbox-overlay additions for Vertical Slice.
