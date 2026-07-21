# Just Dodge Agentic Asset Foundation v2

Status: active replacement foundation, 2026-07-20. All legacy visual/audio/motion assets were retired by owner direction. Their hashes and retained provenance text are in `docs/provenance/RETIRED_ASSET_CORPUS_20260720.json`; retired files are not runtime-admissible.

## Research-backed operating model

- Ubisoft DigiPro 2026 describes brief analysis -> structured casting list/concept previz -> semantic asset discovery -> Blender MCP layout, with generated/retrieved content used primarily for rapid prototyping rather than self-certifying final art (ACM DOI `10.1145/3819990.3820033`, 2026-07-18).
- World Labs/fal's IMAGE-BLASTER showcase uses Claude orchestration, fal/Hunyuan mesh generation, object extraction, and Blender/Unreal downstream editing; generation is infrastructure input, not final output.
- Meshy's April 2026 game workflow requires concept, high-poly, retopology, UVs, PBR, baking, rigging, animation, export, and early engine tests. Its own guidance says AI is a starting point and character deformation loops still need manual/DCC correction.
- Current user reports converge on the same failure boundary: AI outputs can accelerate blockout and concepts, but raw topology is frequently unsuitable for rigging/animation until Blender retopology, UV, weights, scale, and in-engine checks are completed.

## Authority boundary

1. FAL/OpenAI image generation creates reference candidates only.
2. Meshy/Hunyuan/Hyper3D creates one isolated component candidate per task: body carrier, one armor piece, one weapon component, or one arena module. Never generate character + armor + weapon as one fused object.
3. Blender is the geometric, material, assembly, scale, socket, rig, collision, fracture, LOD, and export authority.
4. GameFlow Studio is the reproducible node graph. Every node records exact inputs, model/tool version, parameters, hashes, and output paths.
5. The Rust cooker and runtime are the final mechanical compatibility gate. Rendered screenshots cannot override geometry, rig, contact, collision, or deterministic-truth failures.
6. Independent AI visual review precedes human taste approval. Neither one substitutes for machine validation.

## Canonical component hierarchy

`fighter/body_carrier -> fighter/rig -> armor/{head,torso,arms,legs} -> weapon/{blade,guard,grip,pommel} -> arena/{floor,boundary,architecture,props} -> runtime/{LOD,collision,fracture,materials}`

Armor is fitted against the versioned body-carrier surface and skeleton. Weapons are dimensioned from hand anthropometry and socket frames. Arena modules are dimensioned from fighter reach, camera envelope, rollback collision needs, and destruction cells.

## 100 critical agentic-asset features

### A. Brief, identity, and provenance
1. Typed per-component brief with objective, non-goals, dimensions, style, function, and acceptance bounds.
2. Stable asset ID independent of filename and generator task ID.
3. Parent/child lineage from concept to candidate to Blender authority to cooked runtime asset.
4. SHA-256 for every input, intermediate, `.blend`, export, texture, and cooked file.
5. Generator/provider/model/version/seed/parameters receipt for every candidate.
6. Source URL, creator, license, retrieval date, intended use, and rights snapshot for every external reference.
7. Explicit generated-content ownership and commercial-use status field.
8. Supersedes/revokes links so retired assets cannot silently return.
9. Immutable failure history for rejected candidates.
10. Human decision record bound to exact artifact hash, never a mutable pathname.

### B. Reference and concept control
11. Separate concept tasks for body, each armor identity, each weapon, and each arena kit.
12. Orthographic front/side/back views generated and stored as separate images.
13. Identity-consistency score across views before 3D generation.
14. Silhouette target mask and screen-space readability target.
15. Real-world anatomy, armor, weapon, and architecture references alongside style references.
16. Neutral-light material reference board separate from beauty art.
17. Deformation-zone callouts for shoulders, elbows, wrists, hips, knees, ankles, fingers, and face.
18. Exploded-view reference for modular assemblies.
19. Contact/load-path reference for grips, straps, hinges, plates, and destructible joints.
20. Negative-reference set documenting forbidden shapes, fused parts, baked lighting, and style drift.

### C. Generation orchestration
21. One semantic object or component per generation task.
22. Geometry preview gate before any paid texture/refine task.
23. Multi-view reconstruction preferred over text-to-3D for shape-critical parts.
24. Alpha-background references for clean segmentation.
25. Provider bake-off lane (Meshy, Hunyuan, Hyper3D) with identical briefs and blind scoring.
26. Candidate count and credit/time budget reserved before dispatch.
27. Async task IDs and queue state persisted durably.
28. Immediate durable download before provider URL expiry.
29. Automated file decoding and format sanity check after download.
30. Candidate quarantine; no generator output enters runtime paths directly.

### D. Blender node-graph authority
31. GameFlow node graph materializes every pipeline stage and dependency.
32. Blender collection graph mirrors component hierarchy and asset IDs.
33. Geometry Nodes graphs carry procedural armor fitting, LOD, collision, and fracture operations where appropriate.
34. Shader node groups are versioned by material class and export contract.
35. Compositor node graph produces neutral QC, silhouette, normal, depth, object-ID, and beauty passes.
36. Node-group inputs use named units and explicit defaults.
37. Node-group versions are content-addressed and migration-tested.
38. No hidden scene state: units, scale, FPS, color management, render engine, and frame range are explicit.
39. Every node graph has a machine-readable interface manifest.
40. Re-running the graph from the same inputs reproduces identical topology/material/export receipts where Blender permits determinism.

### E. Geometry and topology
41. Metric units and canonical +Z-up/+Y-forward export orientation.
42. Exact bounding-box and anatomical landmark measurements.
43. Watertightness policy declared per component rather than assumed globally.
44. Non-manifold, degenerate, zero-area, loose-part, self-intersection, and inverted-normal checks.
45. Deformation-aware quad loops for shoulders, elbows, wrists, hips, knees, ankles, fingers, neck, and face.
46. Even polygon density with explicit exceptions for silhouette and deformation.
47. Hard-surface bevel width tied to real scale and target pixel coverage.
48. Thin-part minimum thickness and collision-safe clearance checks.
49. Symmetry is explicit and breakable only after base topology passes.
50. High-poly and game mesh remain linked for rebakes and later LOD regeneration.

### F. UV, bake, material, and texture
51. Non-overlapping UV policy per material channel and lightmap use.
52. Texel-density budget by asset class and expected screen coverage.
53. Hidden seams and mirrored-island policy documented per component.
54. Cage-based normal/AO/curvature bake with ray-distance receipts.
55. Tangent basis pinned to runtime convention and round-trip tested.
56. Base color contains no baked directional lighting.
57. Normal, roughness, metallic, AO, height, and masks are Non-Color data.
58. Metallic values are physically binary except documented composite surfaces.
59. Material response validated under neutral HDRI, key/fill/rim, and engine arena lighting.
60. Texture mip, compression, channel packing, alpha, and VRAM budgets validated on desktop and Steam Deck targets.

### G. Modular assembly and scale inheritance
61. Body carrier is the canonical scale and surface-fit authority for all armor.
62. Versioned skeleton and landmark sockets define armor and weapon attachment frames.
63. Armor fitting uses shrinkwrap/cage or equivalent reproducible node operation, not eyeballed transforms.
64. Layered clearance budget prevents body/underlayer/plate interpenetration through the full pose set.
65. Armor parts remain separate objects with explicit coverage zones and material layers.
66. Weapon blade, guard, grip, and pommel remain separate components until Blender authority assembly.
67. Grip diameter, length, and guard clearance derive from hand anthropometry and glove thickness.
68. Pivot/origin/socket transforms are serialized in integer micrometres or exact matrices.
69. Left/right and variant assemblies inherit from one canonical component source.
70. Arena modules snap to a metric grid with deterministic pivots and connection sockets.

### H. Rigging, motion, and contact mechanics
71. One canonical production skeleton with stable bone IDs and names.
72. Source rigs are adapters; MotionBricks-compatible skeleton remains runtime authority.
73. Bind-pose parity and inverse-bind reconstruction tests.
74. Per-vertex influence count, normalization, and zero-weight checks.
75. Weight-paint stress poses for every major joint and extreme combat reach.
76. Twist distribution for forearm, upper arm, thigh, and calf.
77. Foot sole, hand palm, weapon edge, armor plate, and body-region contact landmarks.
78. Active-ragdoll mass, inertia, joint limit, motor, and collision-proxy manifests derived from geometry.
79. Motion proposals are tested on the actual production rig; no baked combat clip may substitute.
80. Contact measurements use synchronized rendered pose, collision proxies, and deterministic truth tick.

### I. Collision, destruction, LOD, and runtime cook
81. Separate visual mesh, broadphase proxy, narrowphase proxy, hit region, and navigation geometry.
82. Convex decomposition and proxy error measured against the visual surface.
83. Sparse material/SDF destruction cells are bounded per object and never replace world truth.
84. Fracture seeds, cut planes, connectivity, mass conservation, and debris budgets are explicit.
85. Armor dent/cut/penetration layers map to real material thickness and energy response.
86. LOD0/1/2/3 generated from the accepted authority mesh with silhouette-error metrics.
87. Bone and influence reduction per LOD is validated against deformation error.
88. Impostors/HLODs permitted only for distant environment assets, never combat-contact authorities.
89. Cooker rejects missing UVs, materials, sockets, bones, proxies, hashes, or lineage.
90. Export round-trip reimports GLB/FBX into a clean Blender scene and compares counts, transforms, materials, and animation channels.

### J. Visual QA, performance, and repair loop
91. Turntable coverage includes front, back, side, three-quarter, top, underside, close-up, and silhouette views.
92. Animation contact sheets sample bind, locomotion, all 13 intents, impacts, recovery, and failure poses.
93. Object-ID, depth, normal, wireframe, UV, weight, collision, and beauty passes are separate non-duplicate evidence.
94. Independent critic cannot be the producer and must cite pixel/object/frame locations.
95. Automated framing checks enforce full-body and component fill ratios.
96. Engine capture must match Blender authority within declared material/pose tolerances.
97. Triangle, draw-call, texture, VRAM, skinning, load-time, and frame-time budgets gate promotion.
98. Repair nodes operate on one defect class at a time and rerender identical views.
99. Two failed repairs trigger rollback and a new falsifiable method rather than threshold weakening.
100. Human visual approval occurs only after all machine geometry, rig, material, collision, export, runtime, and independent-AI gates pass.

## Initial acceptance sequence

Every step inherits `CHARACTER_EQUIPMENT_PROMOTION_CONTRACT.md` and `../quality/ADVERSARIAL_VISUAL_CONTRACT.md`; no isolated thumbnail or front still can advance the sequence.

1. Body-carrier concept views.
2. Isolated body-carrier 3D candidate.
3. Blender retopology and canonical rig.
4. Neutral body material and engine cook.
5. One torso armor component fitted to the accepted body.
6. One weapon blade component, then guard, grip, and pommel; assemble only in Blender.
7. One arena floor/boundary module scaled from fighter reach and camera envelope.
8. Only after each isolated component passes: assemble one complete fighter kit and run full pose/contact/LOD/runtime visual gates.
