# Just Dodge Meshy-6 Asset Pipeline

Date: 2026-07-09
Primary source/interchange: FBX
Auxiliary format: GLB for Meshy rigging and validation

## Product boundary

- Just Dodge is not a medieval game. For Honor/Elden Ring are intensity and fidelity references, not setting references.
- The setting is not locked. Provisional asset tests use a setting-neutral, severe, timeless/brutalist proving-ground language.
- Characters, anatomy, clothes, armor layers, weapons, shields, breakable parts, and arena modules remain separate physical assets.
- Meshy supplies candidate outer bodies, equipment, weapons, and environment components. Registered anatomical internals are a separate medically grounded pipeline.
- MotionBricks remains motion authority. Meshy walk/run output is rig-diagnostic evidence only.

## Production route

1. Generate high-quality orthographic reference turnarounds with the configured GPT Image 2 generator.
2. Crop front/right/back/left or component-specific views into separate files. Remove adjacent fragments/background graphics, normalize scale and baseline, hash inputs, then vision-check coherence.
3. Generate geometry-only Meshy-6 candidates with:
   - `should_texture:false`
   - `should_remesh:false`
   - `pose_mode:"t-pose"` for humanoids
   - `target_formats:["fbx","glb"]`
   - `alpha_thumbnail:true`
   - `multi_view_thumbnails:true`
4. Validate every FBX mechanically in Blender/bmesh and visually from cardinal renders. Regenerate with one controlled reference change until geometry passes.
5. Retexture only accepted geometry with Meshy-6:
   - `enable_original_uv:true`
   - `enable_pbr:true`
   - `hd_texture:true`
   - `remove_lighting:true`
   - FBX + GLB output
6. Preserve the highest-precision source. Use standalone Remesh only on an explicit branch after geometry acceptance; compare silhouette, thickness, component boundaries, and joints.
7. Auto-rig only a textured, clearly humanoid model under 300,000 faces. Keep rigged FBX as source; use returned GLB/walk/run only for validation.
8. Cook FBX deterministically into engine-native assets. Verify scale, +Z front, origin, hierarchy, bind pose, normalized weights, material slots, cooked hash, MotionBricks stress motion, and live visual output.
9. Do not delete or replace current assets until all gates pass.

## Component-first rule

Measured Meshy-6 trials show that complex objects simplify or fuse small/mechanical parts even from strong references:

- Four full-body candidates remained mitten-handed/toeless. Candidate 003 is retained only as a torso/body-core source.
- A separate right-hand task produced a closed manifold 191,792-polygon source with five digits.
- A separate right-foot task produced complete toes but has three nonmanifold edges requiring repair.
- Two whole-sword tasks stayed under-resolved at the point, fuller/bevels, guard, wrap, pommel interfaces, and fracture boundaries.
- Component-first W0 tasks validated the strategy: the separate blade and guard pass geometry. The separate grip fails because its wrap became stacked ribs and its through-channel is ambiguous; the separate pommel fails because the peen recess/keyed interface is absent. These are localized repair/regeneration problems instead of a fused whole-weapon failure.
- One arena-threshold geometry task passed cardinal silhouette/manifold review, but remains one fused mesh requiring local component split, pivots, sockets, collision and fracture metadata. Two Meshy-6 PBR retexture attempts failed the requested concrete/steel/graphite material zones, inventing pale patches or tan/bronze/yellow surfaces. Final physically calibrated materials must follow component separation and local material assignment.

Therefore generate and validate mechanically distinct pieces separately: hands, feet, blade, guard, grip, pommel, armor layers, shield layers, straps, hinges, fracture parts, and modular arena chunks. Assemble and retopologize locally. Retexturing cannot repair absent geometry or missing break boundaries.

Humanoid deformation topology is a stricter exception. Whole-hand/foot Meshy meshes, isolated Meshy digit shells, and procedural Blender Skin/voxel cages all failed 60-degree articulation gates. Production C0 topology now starts from the CC0 MPFB2 base mesh at commit `26c811d307b57e2f9f3d743b92d69681b1704e85`, using its one closed 13,380-vertex body, 163-bone default rig, 38 finger bones, and 28 toe bones. Meshy hand/foot outputs are bounded surface references only: transfer may move vertices but must preserve topology, weights, and joint structure exactly.

## Retry versus regenerate

- Persist exact endpoint, payload, task/parent ID, returned seed, model, timestamps, credit result, error, artifacts, and hashes.
- Retry the unchanged payload only for transport failure before a known task ID, HTTP 429 after jittered backoff, or task errors `timeout`, `service_unavailable`, and `server_error` after confirming `consumed_credits:0`.
- Reconcile task listings before resubmitting when creation may have succeeded; Meshy exposes no documented idempotency key.
- Never retry `invalid_input` unchanged. Correct the exact field, view consistency, source format, UV, face count, or orientation.
- Quality rejection is a new paid candidate, not a retry. Change exactly one reference/silhouette/component hypothesis and preserve the rejected lineage.
- Poll at least every five seconds or use SSE/webhooks. Stop on `SUCCEEDED`, `FAILED`, or `CANCELED`.
- Download FBX and task metadata immediately. Non-Enterprise outputs expire after at most three days.
- The API returns a seed, but documented creation schemas do not accept one; do not claim deterministic seed replay.

## Validation gates

### Reference

- One coherent subject per file; exact useful views; no occlusion, adjacent fragments, labels, or perspective contradiction.
- Humanoid T-pose with readable hands/feet and separate equipment.

### Geometry

- Cardinal silhouette/proportions; finite dimensions; +Z front; correct origin and scale.
- Mesh object/shell/component count, vertices/faces, boundaries, manifold edges, loose/duplicate vertices, normals, self-intersections, and dimensions.
- No fused anatomy/components, missing parts, floating shells, rounded weapon points, lost thickness, or invented geometry.

### Materials

- PBR base color has no baked lighting; complete metallic/roughness/normal bundle; coherent texel density; physical substances have distinct assignments.

### Rig

- Complete hierarchy and weights; no unbound vertices; normalized influences; joint placement and extreme bend tests; walk/run diagnostic pass.

### Runtime

- Raw FBX preserved; deterministic cooker output; bind pose and MotionBricks stress clips; zero exploded vertices; stable full-rate live render.

## Validation batch

### C0 — base fighter

Setting-neutral realistic adult human in exact T-pose, close-fitting neutral underlayer, separate equipment, anatomically plausible proportions.

Acceptance requires a complete body with production hands/feet, clean shoulder/axilla/groin/joints, no open/nonmanifold geometry, and accepted MotionBricks deformation. Full-body Meshy candidates may supply the body core; high-resolution component grafts supply extremities where required.

### W0 — two-handed sword combat instrument

Separate blade/tang, guard, grip, collars, and pommel. Straight double-edged blade with acute point, distal taper, engineered cross-section/fullers, measurable thickness, physically plausible assembly, material regions, and fracture interfaces. Generate components separately after whole-object candidates demonstrated lost detail.

### S0 — shield

Separate core, rim, boss/reinforcement, straps, grip, material regions, and planned fracture boundaries.

### E0 — arena module

Setting-neutral brutalist threshold: concrete/black stone, structural steel, replaceable impact panels, separate breakable modules, known sockets/pivots. No monolithic scene generation.

## Recorded task lineage

- Rejected Meshy 2D task: `019f49f4-f03e-73fe-81cd-3a0eec09bc13` (incorrect medieval framing; never chain).
- C0 body: `019f4a03-ecca-7af9-81bb-659e42c2e354`, `019f4a0d-3d0a-7c92-b797-981fa6688bb6`, `019f4a0d-7b8e-75a9-939a-a575cae48168`, `019f4a13-e77f-7ee7-8013-164f61434a2a`.
- C0 hand/foot: hand `019f4a19-7e38-7ff2-ada0-c4e64a65c187` accepted; initial foot `019f4a1e-1c72-7926-b2a4-31f87708b7a4` rejected; corrected coherent five-toe foot `019f4bef-03fa-7e89-beb5-747f41519a96` accepted conditionally for grafting.
- C0 assembly `C0-ASM-001` accepted source geometry: normalized candidate 003 to 1.80 m, removed mitten/toeless extremities with closed wrist/ankle cuts, added mirrored accepted five-digit hands and corrected five-toe feet as separate overlapping graft components, and preserved the raw body candidate hidden in BLEND provenance. FBX/GLB contain five named components with 1.79 m arm span, symmetric T-pose and explicit graft metadata. Unified retopology/weights, seam smoothing, rigging and MotionBricks deformation remain required before runtime acceptance. Source: `assets/source/meshy/c0_base_fighter/assembled_001/`.
- C0 retopology `C0-RETOPO-003` accepted rig-input geometry: measured the actual body/extremity graft cross-sections, translated foot ankle centers by 76 mm onto lower-leg centers, tapered hand stump radii over x=0.705–0.780 m, inset the top 60 mm of each foot stump, pre-simplified components, and exact-unioned them. Result: one closed manifold 290,325-face/146,356-vertex mesh, all five digits preserved per extremity, no visible graft cuffs/rings, FBX/GLB parity, deterministic rerun. Source: `assets/source/meshy/c0_base_fighter/retopo_001/`.
- C0 Meshy rig task `019f4c2a-73ff-7bd1-950d-f3f5cee8a2dc` accepted as a body-rig source (5 credits): one 24-bone armature, 96,822 vertices/193,940 faces, zero unbound vertices, normalized weights, and stable bind/walk/run visual diagnostics without explosion or graft pumping. Included walking (32 frames at 30 fps) and running (20 frames at 30 fps) remain diagnostics only. The rig has no finger bones and up to nine influences per vertex. Naive top-four pruning is rejected because sampled max deformation error reached 27.9 mm despite ~0.15 mm mean error. `MESHY-SKIN8-001` extended SKM extraction/loading, the 96-byte wgpu vertex layout, and WGSL LBS to eight influences; top-eight pruning drops only 79 assignments and measured ≤0.165 mm maximum error across 16 walk/run samples. World-transform baking also corrected the cooked height from the erroneous 1.47 m mesh-local result to 1.80 m. Cooked SKM/ANM diagnostics are preserved under `rigged_001/cooked/`; MotionBricks runtime replacement remains gated. Source: `assets/source/meshy/c0_base_fighter/rigged_001/`.
- `C0-BASETOPO-001` accepted the MPFB2 2.0.17 default topology as C0's full-articulation carrier. Official MPFB assets—including base mesh and rigs—are CC0. Helper removal produced one closed manifold 13,380-vertex/13,378-face body with 163 bones, 38 finger bones, 28 toe bones, and zero unbound vertices. Top-eight reduction affected 920 vertices but produced only 0.142 mm worst-case position error and zero vertices over 1 mm during simultaneous 60-degree finger/toe flex. FBX re-import preserved topology, 163 bones, zero unbound vertices, and at most six serialized influences. A symmetric, wrist/ankle-blended Meshy detail transfer changed 5,326 vertices by at most 4 mm while preserving face indices and weights exactly; rerun comparison was bit-exact at the vertex/weight/topology level. This remains a source asset—not a runtime replacement—until whole-body C0 silhouette transfer, C0 wrist/ankle graft alignment, MotionBricks retargeting, cook, and live visual QA pass. Sources: `assets/source/reference_humans/mpfb2_base_001/`, `assets/source/meshy/c0_base_fighter/basetopo_001/`, and `tools/transfer_mpfb_extremity_detail.py`.
- `C0-POSE-CARRIER-001` resolved the whole-body integration boundary without rewriting the proven MPFB bind. Two bind-rewrite units were rejected after neutral fits tore fingers/toes under 60-degree stress: Blender cannot store the idealized cross-axis similarity scales used by the attempted mesh/rest conversions. The accepted source instead uses a deterministic male/muscular MPFB macro body (`gender=1.0`, `muscle=0.72`, `weight=0.52`, `height=0.62`), the same bounded Meshy extremity transfer, and a one-frame `C0_REFERENCE_POSE` action that rotates 33 major source-bone directions to the measured C0 directions while leaving all 13,380 bind vertices, face indices, weights, 163 rest bones and inverse binds unchanged. The reference action measures 1.958757 m high ×1.920826 m arm span and carries a deterministic uniform runtime scale of `0.9189499701711632` for 1.8 m output. Direction error is 0°, simultaneous 60-degree fingers/toes remain coherent, FBX re-import is one closed manifold with zero unbound vertices and at most six influences, and `c0_reference_pose.json` reproduces byte-identically. This JSON—not a rebaked T-pose mesh—is the reference alignment authority for MotionBricks. Source: `assets/source/meshy/c0_base_fighter/pose_carrier_001/`; tool: `tools/create_c0_reference_pose.py`.
- `C0-RETARGET-FRAME-CAL-001` accepted the structural G1→C0 calibration on measured primitive motion. The retargeter transfers world-frame source rotation deltas, derives target locals causally against each updated parent, and distributes one sparse G1 joint cumulatively across multi-bone C0 limb/spine chains. The measured four-frame strike primitive preserves G1 segment lengths within 0.000000209 m; C0 local lengths are bit-stable, skin determinants remain 0.999996662–1.000000834, and visual QA shows connected non-exploding anatomy. Neural `generate_clip` output remains rejected as source data: source-only G1 renders are already severely contorted before retargeting. Production integration must fail closed on source validity and may not tune the C0 mesh around invalid generated frames. Evidence: `assets/source/meshy/c0_base_fighter/pose_carrier_001/qa/frame_calibration_001/`.
- W0 whole-sword rejected: `019f4a25-ee87-7e95-bdc9-7631abb18b71`, `019f4a2a-3e64-73e5-b561-bbbad5dbff95`.
- W0 component tasks: blade `019f4a46-38c7-7949-82c9-c7d00993094a` accepted; guard `019f4a4c-046a-7a38-8d93-c51896189157` accepted; grip `019f4a4c-0aec-774d-81ca-e1f6c6790a8f` rejected; pommel `019f4a4c-12e7-72fa-820d-1a085d29f74e` rejected.
- W0 assembly `W0-ASM-002` accepted geometry: baked FBX world transforms before metric scaling; retained separate blade/tang, guard, grip core, continuous helical wrap, two collars, repaired pommel, tang extension, and peen. FBX re-import preserves nine closed-manifold components, names, dimensions, and five material IDs; GLB preserves object/material/dimension parity but is view interchange rather than topology authority. Source: `assets/source/meshy/w0_sword/assembled_001/`.
- E0 geometry accepted conditionally: `019f4a33-b425-7dc6-94c7-80ad8493004f`; E0 texture attempts rejected: `019f4a36-fe9c-761b-a7ed-e0c8a2dad9d4`, `019f4a3b-1af8-76ec-90cd-45f17674e942`.
- E0 assembly `E0-ASM-001` accepted geometry: reconstructed the Meshy gateway silhouette as 115 named closed-manifold objects—structural pylons/feet/caps/beam, replaceable front/back impact panels, braces, socket plates/pins, and individually batchable fasteners. Final dimensions 3.62×0.668×3.0 m with a 2.35×2.48 m opening. The raw Meshy shell is retained hidden in the BLEND as design provenance and excluded from FBX/GLB. Source: `assets/source/meshy/e0_arena_threshold/assembled_001/`.

Every candidate has a local manifest under `assets/source/meshy/` containing request lineage, hashes, metrics, credits, acceptance state, and rejection evidence.
