# PRD: Asset Pipeline

## 1. Purpose

Convert source art (FBX/GLB) into deterministic runtime binaries with verified metadata, so assets are traceable, reproducible, and validated before entering a build.

## 2. Invariants

- Every runtime asset has a source path, tool version, and verifier log.
- Binary formats are versioned and documented.
- MotionBricks ONNX/NPY artifacts are required runtime dependencies and must be included in packaging or build generation.
- Large source assets are not committed to git; generated binaries are tracked or packaged separately.
- Asset manifest is required for build reproducibility.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| source_asset | FBX/GLB/texture | Artist/tool | Authoring source |
| metadata | JSON sidecar | Artist/tool | Combat metadata, sockets, slots |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| static_mesh_bin | .bin | PRD_RENDERER.md | Runtime static mesh |
| skinned_mesh_skm1 | .bin | PRD_RENDERER.md | Runtime skinned mesh |
| animation_anm1 | .anim | PRD_MOTION.md | Runtime animation clip |
| asset_manifest | JSON | Build/package | Inventory of all assets |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| asset_verified | { asset_id, path } | After verifier passes |

## 4. Data Flow

1. Source asset and metadata are placed in source tree.
2. Extraction tool converts to runtime binary format.
3. Verifier checks counts, bounds, weights, bone mapping, and metadata completeness.
4. Asset manifest is updated with entry.
5. Runtime loader reads manifest and binaries.
6. Visual QA capture validates final appearance.

## 5. Control Flow

- **Who calls it:** Build scripts and artists.
- **Tick rate:** Build-time only.
- **Threading model:** Build tooling.

## 6. Error Handling

- **Fail-closed:** unverified assets are rejected from build.
- **Fail-closed:** missing texture blocks the build; no placeholder checkerboard or fallback texture is permitted.
- **Degradation:** lower LOD or simplified mesh substitutes if high-res asset fails.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Load time per asset | <100 ms | 500 ms |
| Memory per fighter | <64 MB | 256 MB |
| Build tool runtime | <10 s/asset | 60 s |

## 8. Dependencies

- PRD_RENDERER.md — consumes meshes and textures.
- PRD_MOTION.md — consumes animations, skeletons, and MotionBricks ONNX/NPY artifacts.
- PRD_COMBAT_TRUTH.md — may use hitbox proxy meshes derived from MotionBricks poses.

## 9. Open Questions

- GLB vs FBX as canonical source format.
- Git LFS or external asset store for large binaries.
- Combat metadata schema finalization.

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Binary formats SKM1/ANM1/static .bin are canonical runtime formats; source format is FBX/GLB with JSON sidecars.
- **Rationale:** Existing tools and runtime loaders already use these formats.
- **Blocker:** Asset loader and extractor format ordering may mismatch; must be reconciled before next import.
- **Status:** ACTIVE.
- **Next:** Audit and fix format ordering between `tools/extract_mesh.py` and `src/asset.rs`.
