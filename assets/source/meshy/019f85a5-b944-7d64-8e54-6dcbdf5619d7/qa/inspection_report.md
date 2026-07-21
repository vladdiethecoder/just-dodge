# Meshy Candidate Inspection — 019f85a5-b944-7d64-8e54-6dcbdf5619d7

## Task

- Task ID: `019f85a5-b944-7d64-8e54-6dcbdf5619d7`
- Task type: `image-to-3d`
- Model type: `standard` (Meshy 6/latest)
- Status: `SUCCEEDED` (100%)
- Consumed credits: 30
- Output: textured GLB; `remove_lighting=true`, `hd_texture=true`
- No new Meshy generation or paid processing was performed during this inspection.

## Download

- GLB: `assets/source/meshy/019f85a5-b944-7d64-8e54-6dcbdf5619d7/model.glb`
- Size: 46,313,708 bytes (44.17 MB)
- SHA-256: `fd56385b447244edd0d6f62d84dacf16d9d17d8b322ff6e9676f1b8e4a3e3a95`
- Downloaded texture sidecars are under `model_textures/` (base color, metallic, roughness, normal, emission).

## Blender headless inspection

- Blender: 5.2.0 LTS
- Mesh objects: 1 (`Mesh_0`)
- Vertices: 248,471
- Triangles: 474,758
- Armature objects: 0
- Bones: 0
- Material slots: 1 (`Material_0`)
- UV layers: 1 (`UVMap`)
- Manifold/topology:
  - Closed manifold: **false**
  - Boundary edges: 21,816
  - Non-manifold edges (>2 faces): 0
  - Loose edges: 0
  - Degenerate faces: 0
- World-space bounding box (metric/glTF meters):
  - Min: `[-0.7579810023, -0.1768800020, -0.9504399896]`
  - Max: `[0.7564560175, 0.1793259978, 0.9467890263]`
  - Size: `[1.5144370198, 0.3562059999, 1.8972290158]` m

## Materials / visual evidence

Blender re-imported the GLB with one node-based PBR material. The material contains packed image maps including a 4096x4096 base-color image, 2048x2048 metallic/roughness data, and 4096x4096 normal data. Eevee front/back renders show coherent armor segmentation, readable silhouette, and no obvious missing-texture, UV, or catastrophic shading artifacts. Headless workbench front/back/left/right renders show no obvious floating parts or exploded geometry.

Evidence files:

- `qa/blender_inspection.json`
- `qa/material_probe.json`
- `qa/front_y_minus.png`
- `qa/back_y_plus.png`
- `qa/right_x_plus.png`
- `qa/left_x_minus.png`
- `qa/pbr_front_y_minus.png`
- `qa/pbr_back_y_plus.png`

## Verdict

**NEEDS REPAIR** — good visual source candidate, not ready for direct PH1-FIGHTER-001 admission.

Reasons:

1. The front render is a shallow A-pose / arms-below-horizontal rather than an exact T-pose; this fails the strict rigging-pose gate.
2. 474,758 triangles exceed the Meshy auto-rigging face limit of 300,000 faces.
3. The GLB contains no armature or bones.
4. The mesh is not closed-manifold and has 21,816 boundary edges, although it has no non-manifold, loose, or degenerate edges/faces.

This is repairable in Blender/retopology: preserve the downloaded GLB as the high-detail source, create a deformation-aware lower-poly carrier under the rigging budget, establish an exact validated T-pose, repair or intentionally separate open armor surfaces, then rig/weight and run extreme-pose QA. Do not wire this raw GLB directly into the runtime.
