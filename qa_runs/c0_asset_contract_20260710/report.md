# C0-ASSET-CONTRACT-001

## Scope

Inspected the canonical C0 pose carrier in Blender through the constrained typed DCC MCP surface. No source blend was saved or altered.

## Canonical source

- `assets/source/meshy/c0_base_fighter/pose_carrier_001/c0_pose_carrier.blend`
  - SHA-256: `ebfb845d1e70f0c058f17d4eb79b9e3d0d8ad988cc67c09ea58c89f9ea23b5da`
- `assets/source/meshy/c0_base_fighter/pose_carrier_001/model.fbx`
  - SHA-256: `1969d95d793a112119a7384dd73695bc5fadb52750cec8dee06b8e7adfaef086`
- `c0_reference_pose.json` is the C0 reference-pose authority: 163 bones, 1.958757 m reference height, 1.920826 m arm span, and deterministic runtime scale `0.9189499701711632`.

`assembled_001` and `retopo_001` remain upstream Meshy geometry lineage, not the runtime carrier. C0 runtime work targets `pose_carrier_001`.

## Blender observation

Opened `c0_pose_carrier.blend` in Blender 4.3.2. Scene contains three meshes, two armatures, one camera, and one material datablock. The accepted pair is `Human_clean` plus `Human.rig_clean`.

Typed validator evidence:

| Gate | Result |
|---|---|
| Mesh | 13,380 vertices; 13,378 polygons; one UV layer; no validator error |
| Rig/reference animation | Valid at frame 1 with required keyframes |
| Export readiness | `Human_clean` + `Human.rig_clean` valid for FBX |
| Geometry provenance | 163 bones, zero boundary/nonmanifold edges, zero unbound vertices, maximum six serialized influences |
| 60-degree finger/toe stress | Existing authoritative evidence passes; no visible spikes, detached limbs, toe collapse, or finger fusion |
| Materials | Blocked for PBR: `Human_clean` has zero assigned material slots; no PBR texture contract exists |

## Render evidence

- `c0_pose_carrier_close_workbench.png` — current controlled Blender Workbench render. Full neutral/reference silhouette is coherent, limbs are continuous, and fingers/toes are visible. This is geometry/rig evidence only.
- `c0_pose_carrier_camera.png` — current source-camera EEVEE render. It is intentionally retained as evidence that the source camera/light configuration is too dark for acceptance.
- `c0_pose_carrier_workbench.png` — current source-camera Workbench render; improved readability but insufficient close detail.

## Contract decision

C0 is accepted as the runtime geometry, skeleton, bind/reference-pose, and retarget target. It is not accepted as a final textured/PBR render asset. The renderer must use an explicit carrier fallback material until a separately accepted PBR material contract exists; it must not silently substitute the legacy mannequin or a debug texture path.

## Next gate

`C0-RUNTIME-CLOSURE-001`:

1. Load the C0 cooked carrier rather than `mannequin_male.bin`.
2. Size joint storage and animation APIs from actual mesh bone count (163 for C0), per actor.
3. Consume `c0_reference_pose.json` and calibrated world-frame C0 retargeting through the runtime path.
4. Update the headless shot harness for C0 static/reference and measured primitive frames.
5. Do not enable generated MotionBricks playback until its raw G1 source passes source-validity gates.
