# AI 3D → Blender → Game Engine: Evidence-backed conversion research

**Research date:** 2026-07-20
**Scope:** Meshy/FAL-like image/text-to-3D outputs converted through Blender into Unity/Unreal/custom engines. Focus: part decomposition, armor fitting, retopology, UV/PBR repair, rigging, >4-weight reduction, material preservation, LODs, and high-poly/OOM avoidance.

## Findings that survived cross-checking

1. **Treat cloud output as a source/high-poly or draft, not as the final skinned asset.** Recent production-oriented workflows explicitly split body/armor/wings/weapons, generate or retain low-poly per part, clean UVs in Blender, then rig and validate in-engine. See Customuse (2026-06-22), FAL Hunyuan v3 guide (2025-12-20), and the Meshy→Blender→RetopoFlow→Auto-Rig Pro pipeline repository.
2. **Do not use Edit Mode > Separate by Loose Parts as the first operation on a very dense AI mesh.** A Reddit user reported a 1,033,588-vertex / 2,057,795-face image-to-3D mesh taking about two minutes just to enter Edit Mode; another reported Separate by Loose Parts hanging for 20 minutes. For the observed 353k-vertex / 196k-face Meshy limb, precompute connected components or spatial partitions outside Blender (trimesh/mesh processing), or decimate a disposable proxy first.
3. **Armor is a modular-character problem, not only a shrinkwrap problem.** Production/game discussions converge on: share one skeleton, use master/copy pose, mask/delete hidden body under armor, transfer weights from a clean base, and add low-poly collision proxies for unavoidable exposed skin. A shrinkwrap modifier is useful for fitting the base pose, but it does not replace rigging and should follow the Armature modifier when wrapping the deformed cloth/armor to the deformed body.
4. **Retopo is still the deformation gate.** Decimate/remesh can make an AI mesh interactive, but it is a temporary reference or bake source. Build a deformation-aware low-poly mesh with loops at shoulders, elbows, knees, wrists, and digit joints; preserve the untouched high source for baking.
5. **A game-engine skinning contract must be explicit.** Reduce to four influences per vertex before export, normalize, and verify that every vertex has at least one deform group. glTF issue #1151 shows unassigned vertices are invalid; glTF-Blender-IO issue #1970 shows a parent-only armature setup can silently export without JOINTS_0/WEIGHTS_0. Use an Armature modifier and round-trip the exported file.
6. **PBR preservation is a round-trip test, not an assumption.** GLB can bundle textures/materials, but FBX requires explicit path/embedding choices. Verify actual Principled BSDF connections, image paths, color spaces, UV maps, material-slot names, and an exported/re-imported GLB/FBX under the target engine's lighting.
7. **LOD generation should duplicate and protect the source.** Use LOD0 as the approved source, generate LOD1+ on copies, preserve UV/material slots and important edge/bone regions, and test posed deformation at every level. Unreal exposes Max Bone Influence, Bones/Sections to Prioritize, Lock Mesh Edges, and vertex/triangle termination criteria; Unity exposes project skin-weight quality and LODGroup.

## Source ledger (exact URLs and dates)

### AI-service / production workflow sources

- **FAL, Hunyuan 3D v3 prompt guide** — last updated **2025-12-20**. Explains `Normal`, `LowPoly`, and `Geometry` modes; recommends LowPoly and reduced face count for real-time; describes optional PBR, GLB/OBJ outputs, stochastic rerolls, and the fact that multiple objects should be generated as individual assets and composited downstream.
  https://fal.ai/learn/devs/hunyuan-3d-v3-prompt-guide
- **FAL Hunyuan 3D landing page** — current page, accessed **2026-07-20**. Advertises explicit post-processing endpoints for **part splitting** and **Smart Topology**, and supports PBR maps plus GLB/OBJ. Use this as a service capability, not proof that a particular output is game-ready.
  https://fal.ai/hunyuan-3d
- **Meshy Blender plugin: Model Analysis** — current Meshy docs, accessed **2026-07-20**; footer ©2026. The plugin exposes volume/area, solid/non-manifold, intersections, degenerate, non-planar, thickness, overhang, sharp, and small-piece checks; results select bad geometry in Edit Mode.
  https://docs.meshy.ai/en/webapp/plugins/blender/model-analysis
- **Meshy Blender plugin: Model Cleanup** — current Meshy docs, accessed **2026-07-20**; footer ©2026. Describes Analyze → Make Manifold/Delete Small Pieces → Analyze again, with conservative thresholds and visual review. These checks are print-oriented but useful as a first geometry gate for AI outputs.
  https://docs.meshy.ai/en/webapp/plugins/blender/model-cleanup
- **Meshy export-to-Blender workflow guide** — 2026 guide, accessed **2026-07-20**. Recommends inspecting before export, remeshing dense assets, using GLB for bundled geometry/materials/textures, or FBX with Path Mode Copy + Embed Textures, and validating after cleanup.
  https://www.meshy.ai/tutorials/export-to-blender-workflow
- **Customuse, “AI to 3D Game Character With Skins”** — **2026-06-22**. A concrete walkthrough: clean A-pose reference; remove wings/weapons from the body; extract armor as parts; generate low-poly per object; inspect wireframes; manually clean/mirror/unwrap in Blender; reuse one body geometry for original/gold/crimson skins; AccuRIG; add wing rigging/physics; retarget and test in Unreal Engine 5.
  https://customuse.com/learn/ai-to-3d-game-character-with-skins
- **80 Level / Hyper3D Rodin Gen-2.5 interview** — **2026-06-03**. The producer frames AI output as a controllable workflow rather than a one-click final: part-level decomposition, high-poly as a bake source, Smart Low-Poly for real-time, 3D-native PBR, and explicit caution that complex assets still need human refinement for topology, animation edge flow, and art direction.
  https://80.lv/articles/how-hyper3d-rodin-gen-2-5-is-bringing-production-level-control-to-ai-3d-generation
- **Hunyuan3D Studio technical report** — submitted **2025-09-16**. Describes a modular pipeline containing part-level generation, autoregressive polygon generation, semantic UV, 4K PBR maps, and an animation module. It is research/author evidence, not independent validation of every claimed output.
  https://arxiv.org/abs/2509.12815
  HTML: https://arxiv.org/html/2509.12815v1
- **73K-Y production workflow repository** — repository page accessed **2026-07-20**. Documents Meshy → Blender 4.x → RetopoFlow 4 → Auto-Rig Pro with hard stage gates, source/high-poly collection, transform application, manual deformation loops, rebaking after retopo, and engine export. Treat it as a documented user pipeline; its one-star repository is not independent production-scale validation.
  https://github.com/73K-Y/3D-Workflow-Pipeline

### User experience: high-poly, decomposition, and AI cleanup

- **Reddit r/blender: “Having problems with separating objects in edit mode”** — submitted **2023-04-09**. User reports Edit Mode → Separate by Loose Parts freezing for more than 20 minutes; a reply suspects too many loose parts and suggests selecting linked geometry with `L` and separating by selection. This is direct evidence that the operator can be an interactive failure point even when the user calls the mesh “not complex.”
  https://old.reddit.com/r/blender/comments/12gn21i/having_problems_with_separating_objects_in_editing/
- **Reddit r/blender: “Some dense scary topology”** — submitted **2023-11-17**. Image-to-3D user reports **1,033,588 vertices, 3,091,374 edges, 2,057,795 faces**; entering Edit Mode took about two minutes. A high-scoring practical answer recommends decimating only until interactive, retopologizing on that proxy, and projecting/baking maps from the original high mesh. Other replies recommend manual retopo and warn that the geometry is not game-ready.
  https://old.reddit.com/r/blender/comments/17xmheg/some_dense_scary_topology/
- **Reddit r/blender: “Is this the end?”** — submitted **2024-01-26**. The discussion explicitly identifies retopo and UV work as the remaining human bottlenecks for AI 3D; one comment notes that Meshy-like systems are useful for background assets but not a substitute for proper topology. Use as community sentiment, not a measured benchmark.
  https://old.reddit.com/r/blender/comments/1abenio/is_this_the_end/
- **Blender Artists: “Try the AI-retopo tool I’ve built?”** — **2025-10-15**. The developer describes the tool as high-poly in / low-poly out and an improvement on ZRemesher with user-controlled edge loops; commenters emphasize that animation-ready topology remains the differentiator.
  https://blenderartists.org/t/try-the-ai-retopo-tool-ive-built/1615309

### Armor / clothing fitting and modular character experience

- **Blender Artists: “How to make clothes fit a character instead of the character fitting the clothes”** — **2025-10-14 to 2025-10-15**. Practical consensus: shrinkwrap works for single-sided clothing; thick clothing needs proportional editing/sculpting/manual work; there is no universal one-click fit for arbitrary topology; after fitting, clothing still needs weight transfer/rigging, and tight folds commonly need manual polish.
  https://blenderartists.org/t/how-to-make-clothes-fit-a-character-instead-of-the-character-fitting-the-clothes/1615158
- **Blender Artists: “Autofitting tool for Clothing/Armor”** — **2023-12-28; updates 2024-01-13, 2025-01-18, 2025-02-12**. The author tries matching a clothing rig to a target rig, applies it, transfers weights, and then develops distance/AO/displacement corrections for areas that end up inside the body. The post explicitly reports problems at sleeves/edges, AO baking automation, multiple material slots, and different bone hierarchies. This is valuable evidence that armor fitting needs more than a bone-copy pass.
  https://blenderartists.org/t/autofitting-tool-for-clothing-armor/1506512
- **Blender Artists: “Shrinkwrap modifier on rigged body animation”** — **2019-02-13**, answer **2019-02-14**. Mechanical order: the cloth must have an Armature modifier and weights; put Shrinkwrap **after** Armature so it wraps the already deformed mesh to the deformed target. Nearest Vertex/Nearest Surface can be more stable than Project for a suitable starting pose.
  https://blenderartists.org/t/shrinkwrap-modifier-on-rigged-body-animation/1147006
- **Blender Artists: “How should I create clothes for a character in a game engine using Blender?”** — **2024-07-02**, replies **2024-07-03** and **2024-10-23**. Recommends same-skeleton clothing plus additional bones for skirts, coats, bags, sabers, and hair; for tight clothing, duplicating the weighted skin is a practical low-poly method; “least of everything” and LODs matter in game assets.
  https://blenderartists.org/t/how-should-i-create-clothes-for-a-character-in-a-game-engine-using-blender/1537099
- **Blender Artists: “Right way to prevent Clothing Clipping”** — **2026-05-04 to 2026-05-06**. Recent game-oriented consensus favors deleting/masking hidden body geometry for non-removable clothing; for exposed skin that cannot be deleted, use a low-poly invisible collision mesh; weight transfer alone breaks at armpits, elbows, hips, crotch, and knees.
  https://blenderartists.org/t/right-way-to-prevent-clothing-clipping/1639772
- **Blender Stack Exchange: “How can I prevent the body object slipping through the clothing object?”** — asked **2016-04-10**; key answer **2017-02-14**. Suggestions: make clothing topology similar to the body; use Solidify/Subdivision or Shrinkwrap; or drive both body and clothing with a simpler armature-driven Mesh Deform cage. Another answer proposes weight the clean skin first and transfer weights to clothing.
  https://blender.stackexchange.com/questions/50456/how-can-i-prevent-the-body-object-slipping-through-the-clothing-object
- **Blender Stack Exchange: “Rigging Armor to Player”** — asked **2018-07-16**; answer **2018-07-29**. When Data Transfer behaves incorrectly, clear existing vertex groups and nonessential modifiers, add Data Transfer to a blank shirt, apply it, then add the Armature modifier. This is a practical reset order for AI armor that arrives with partial groups.
  https://blender.stackexchange.com/questions/114026/rigging-armor-to-player
- **Blender Stack Exchange: “Masking body parts underneath clothes and armor?”** — asked/answered **2019-05-12**. Uses a vertex group plus Mask modifier to hide skin under armor and notes the resulting asset must be integrated with the Unity clothing-swapping system.
  https://blender.stackexchange.com/questions/140424/masking-body-parts-underneath-clothes-and-armor
- **Blender Stack Exchange: “Skin Clipping through Clothing”** — asked **2021-10-13**; answer **2021-12-25**, later comment **2025-12-29**. For separate clothing exported to Unity, use Mask or delete hidden skin; for weight transfer, start from clothing with all vertex groups removed, parent with empty groups, then transfer from the skin. The later user reports this worked well for a coat but not perfectly for jeans shorts, matching the need for manual fixes in deformation zones.
  https://blender.stackexchange.com/questions/240519/skin-clipping-through-clothing
- **Epic Developer Community: “Blender to Unreal Armor Pieces”** — **2022-05-25 to 2022-05-26**. Unreal users describe modular characters: separate head/body/legs/feet skeletal meshes sharing a skeleton, Master Pose/Copy Pose, sockets for attached armor, and a second body mesh with covered regions removed to prevent clipping.
  https://forums.unrealengine.com/t/blender-to-unreal-armor-pieces/566198
- **Epic Developer Community: “UE5.03 Skeletal Mesh Clipping help”** — **2022-12-13**. A user reports no clipping in Blender after weight transfer but severe clipping in UE5, especially glutes/calves. This demonstrates that bind-pose Blender review is insufficient; the actual imported skeletal mesh, physics asset, and engine animation must be tested.
  https://forums.unrealengine.com/t/ue5-03-skeletal-mesh-clipping-help-noob-warning/726997

### Rigging, >4 weights, and exporter failure modes

- **Khronos glTF issue #1275: “Max bone influences per vertex”** — opened **2018-03-07**. Tracking issue for supported influences per vertex across the glTF ecosystem. Use four influences as the conservative interchange contract unless the target runtime explicitly supports more.
  https://github.com/KhronosGroup/glTF/issues/1275
- **Khronos glTF-Blender-IO issue #1151: unassigned vertices** — opened **2020-07-28**. glTF requires every vertex to be assigned to at least one joint; Blender vertices with no bone groups were exported with zero weights and invalid output. Gate unbound vertices before export.
  https://github.com/KhronosGroup/glTF-Blender-IO/issues/1151
- **Khronos glTF-Blender-IO issue #1970: weights silently dropped with parent-only armature setup** — opened **2023-08-21**, still listed open when checked **2026-07-20**. If the mesh is only an armature child, Blender 3.6.2's glTF exporter omitted JOINTS_0/WEIGHTS_0; the issue author found that an Armature modifier is required. Always inspect the modifier stack and re-import the exported file.
  https://github.com/KhronosGroup/glTF-Blender-IO/issues/1970
- **three.js issue #12127: “increase skinning weight limit per vertex from 4 to 8”** — opened **2017-09-05**. A real user reports Mixamo meshes with >4 weights losing extra weights in three.js, causing finger/head/jitter deformation; FBX/Collada/JSON round-trips through 3ds Max/Blender also corrupted the model in that case. This supports an explicit top-4 reduction and deformed-pose comparison rather than silent runtime truncation.
  https://github.com/mrdoob/three.js/issues/12127
- **Blender Artists: “Weight painting issue with loose geometry”** — **2019-09-05**. Automatic weights are reported as “very bad for loose parts,” attaching hair-like geometry to wrong bones. Replies recommend separating loose pieces, weighting the manifold base, transferring weights to the loose parts, and shrinkwrapping margins before transfer.
  https://blenderartists.org/t/weight-painting-issue-with-loose-geometry/1178703
- **Reddit: automatic weights failures** — result pages accessed **2026-07-20**; representative threads include **2019-03-04** and **2021-11-29**. Users report that intersecting or disconnected teeth/hair/armor confuse automatic weights; common workaround is separate pieces, parent with empty groups, then assign/transfer weights.
  https://www.reddit.com/r/blender/comments/asi6k5/failure_when_trying_to_parent_armature_to_mesh/
  https://www.reddit.com/r/blender/comments/r1y0ms/im_new_to_blender_once_i_parent_my_armature_with_automatic_weights/

### Official Blender / engine / validation references

- **Blender 5.2 LTS manual: Retopology/Remeshing** — accessed **2026-07-20**.
  https://docs.blender.org/manual/en/latest/modeling/meshes/retopology.html
- **Blender 5.2 LTS manual: Shrinkwrap modifier** — accessed **2026-07-20**.
  https://docs.blender.org/manual/en/latest/modeling/modifiers/deform/shrinkwrap.html
- **Blender 5.2 LTS manual: Data Transfer modifier** — accessed **2026-07-20**.
  https://docs.blender.org/manual/en/latest/modeling/modifiers/modify/data_transfer.html
- **Blender 5.2 LTS manual: Decimate modifier** — accessed **2026-07-20**.
  https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/decimate.html
- **Blender 5.2 LTS manual: Clean Up → Limit Total Vertex Groups** — accessed **2026-07-20**. The operator removes lowest weights until the requested limit; use it with all relevant groups selected, followed by Normalize All.
  https://docs.blender.org/manual/en/latest/scene_layout/object/editing/cleanup.html
- **Blender 5.2 LTS manual: Weight Paint editing** — accessed **2026-07-20**. Normalize All makes per-vertex group sums equal to 1; Clean/Quantize/Mirror are available for cleanup.
  https://docs.blender.org/manual/en/latest/sculpt_paint/weight_paint/editing.html
- **Blender 5.2 LTS manual: Armature Deform parenting** — accessed **2026-07-20**. Documents armature parent plus Armature modifier and the Empty Groups/Automatic Weights paths.
  https://docs.blender.org/manual/en/latest/animation/armatures/skinning/parenting.html
- **Blender 5.2 LTS manual: Cycles baking** — accessed **2026-07-20**. The active Image Texture node is the bake target; use explicit high→low selection, cage/extrusion, and saved images.
  https://docs.blender.org/manual/en/latest/render/cycles/baking.html
- **Khronos glTF Validator** — accessed **2026-07-20**. Use it after GLB export to catch schema/accessor/material/skin errors; it does not replace visual/posed QA.
  https://github.khronos.org/glTF-Validator/
- **Khronos PBR guide** — accessed **2026-07-20**. Reference for metallic/roughness workflow and glTF material expectations.
  https://www.khronos.org/gltf/pbr
- **Unreal Engine Skeletal Mesh Editor / LOD docs** — accessed **2026-07-20**. The Skeletal Mesh Reduction tool exposes Max Bone Influence, Bones to Prioritize, Sections to Prioritize, Termination Criterion (triangles/vertices), and Lock Mesh Edges.
  https://dev.epicgames.com/documentation/en-us/unreal-engine/skeletal-mesh-editor-in-unreal-engine?lang=en-US
  https://dev.epicgames.com/documentation/en-us/unreal-engine/skeletal-mesh-lods-in-unreal-engine?lang=en-US
- **Unity 6 `QualitySettings.skinWeights`** — current 6000.0 API page, accessed **2026-07-20**. The project setting controls maximum bone influences per vertex; use it as a runtime contract, not as a substitute for authoring cleanup.
  https://docs.unity3d.com/6000.0/Documentation/ScriptReference/QualitySettings-skinWeights.html
- **Blender Extensions: Game Asset Optimizer** — published **2025-11-18**, version 1.0.2 updated **2025-11-21**. Provides batch optimization, 2–8 LOD generation, dual UVs, smart decimation, vertex merge, Unity/Unreal naming, and context safety checks.
  https://extensions.blender.org/add-ons/asset-optimizer/
- **GitHub: LOD Architect Lite** — latest release **2026-05-11**. Batch LOD0–LOD6 generation with live Decimate modifiers, Unreal/Unity presets, UV preservation, weighted normals/Data Transfer options, high-poly confirmation, and source collection preservation.
  https://github.com/Colosyn/LOD-Architect-Lite

### YouTube technical writeups / walkthroughs

YouTube pages did not expose full transcripts through the extractor; exact upload dates below were verified with `yt-dlp --dump-single-json` on 2026-07-20. Treat these as walkthrough references, not benchmark evidence.

- **Clean Up AI 3D Models Like a Pro | Blender Tutorial 2025** — **2025-10-16**.
  https://www.youtube.com/watch?v=vi3JGtG4_uw
- **Meshy 5 – Game Changing AI 3D Model generator / Full Review & Blender / UE5 Tutorial** — **2025-08-28**.
  https://www.youtube.com/watch?v=9zUOvhQ828g
- **Easiest 3D Asset Workflow with Meshy-5 AI** — **2025-05-26**.
  https://www.youtube.com/watch?v=IbQxqbDQjtk
- **Reduce 50k Polys to 7k in Minutes (AI Mesh Cleanup)** — **2025-12-03**.
  https://www.youtube.com/watch?v=cnsFesewZdg
- **How I 10x My 3D Workflow with AI + Blender** — **2025-09-27**; covers Hunyuan generation, retopo, UVs, baking, and game-scene preparation.
  https://www.youtube.com/watch?v=XBXWgb-uzI0
- **Blender 2.82: Rigged Character Weight Paint Transfer (in 60 Seconds!)** — linked from a **2021** Stack Exchange answer; useful for the mechanical transfer step, but Blender 2.82 UI is historical.
  https://youtu.be/bR_Vke__voU

## Mechanical Blender QA workflows

### 0. Intake manifest and “do not destroy source” rule

For every downloaded GLB/FBX/OBJ, create a `SOURCE_HIGH` collection and an immutable manifest before editing:

- source URL/task ID, file SHA-256, Blender version, importer settings;
- object names, evaluated vertex/face/triangle counts, world-space bounds and height;
- material-slot names and image paths; UV layer names; armature name/bone count;
- modifier stack and parent relationships;
- loose-component count/size histogram (computed without invoking `Separate by Loose Parts`).

Duplicate the file before applying Make Manifold, remesh, Decimate, modifiers, or weight cleanup.

### 1. Non-blocking high-poly triage

1. Import in Object Mode, keep the source collection hidden/locked.
2. Run `mesh.validate(verbose=True)` and `mesh.update()`; record removed/fixed elements.
3. Measure evaluated counts and bounds through the depsgraph.
4. Compute connected components with a streaming adjacency pass or external `trimesh`/mesh-tool code. Do not call `bpy.ops.mesh.separate(type='LOOSE')` on a 350k+ vertex source merely to discover parts.
5. If interactive performance is poor, duplicate to `WORK_PROXY`, add Decimate (or external simplification) until orbit/Edit Mode is responsive, and retopologize against the proxy while preserving `SOURCE_HIGH` for baking.
6. If semantics matter (body vs armor vs weapon), prefer service-side part splitting, material/region masks, spatial face partitions, or deliberate cuts over connectivity-only separation.

### 2. Armor fitting and clipping gate

1. Put body and armor in the same bind pose and apply transforms.
2. For tight armor, duplicate the already-weighted skin region, separate it, reshape/solidify, and keep an intentional clearance shell.
3. For arbitrary armor, clear stale vertex groups and nonessential modifiers first; parent armor to the target armature with **empty groups**.
4. Transfer body vertex groups to armor using Data Transfer/Weight Paint Transfer. For different topology, use nearest-face or projected mapping and manually repair shoulders, armpits, elbows, hips, knees, and cuffs.
5. If the armor must remain conformal in Blender, modifier order should normally be `Armature → Shrinkwrap` so the deformed armor wraps the deformed body. Apply/bake this only if the target engine will not reproduce the modifier.
6. For swappable armor, create body-region masks or delete hidden body geometry per equipment combination. Do not keep hidden high-poly body under every armor layer.
7. For skirts/capes/exposed skin, use an invisible low-poly collision proxy or engine cloth/collision system; do not expect weight transfer alone to solve arbitrary animation clipping.
8. Test bind pose plus extreme poses and actual engine animation. A Blender bind-pose pass is not sufficient (Epic UE5 clipping report, 2022-12-13).

### 3. Retopo and bake gate

1. Keep the original AI mesh untouched as `BAKE_HIGH`.
2. Build `RETOPO_LOW` with deformation loops and intentional hard-surface seams; use Shrinkwrap/RetopoFlow/manual snapping to the high surface.
3. Apply scale/rotation before baking and ensure low/high normals are coherent.
4. UV unwrap the low mesh with seams around limbs/armor boundaries, pack islands, and enforce a texel-density budget.
5. In Cycles, select low as active target, high as selected source; create explicit blank Image Texture nodes for Normal/Color/Roughness bake targets; use a cage or small Extrusion; bake Normal first, then Color/AO/Roughness as appropriate.
6. Inspect the baked normal under a neutral studio light and a mirrored/backface view. Search for skewed tangents, cage rays, seams, and missing backside coverage.
7. If a retopo/decimate candidate changes silhouette or causes holes, reject it and return to the high source; never “fix” the only copy.

### 4. Skinning / four-influence gate

1. Ensure every mesh has an Armature modifier whose `object` is the intended armature. Do not rely on parent-only armature relationships for glTF.
2. Delete stale/foreign vertex groups on generated armor before transfer.
3. Assign or transfer weights; run **Normalize All**.
4. Run **Limit Total Vertex Groups = 4** over all deform groups, then Normalize All again. Preserve a named report of vertices that lost influences.
5. Fail if any vertex has zero deform weights, negative/NaN values, or a sum outside tolerance (e.g. `abs(sum - 1) > 1e-4`).
6. Pose at representative extremes: shoulder abduction, elbow/knee 90°, wrist/ankle twist, crouch, finger/toe flex, and armor-specific stress poses.
7. Compare the pre-limit and post-limit deformation; top-4 reduction is accepted only if the target engine's visual gate passes.

Minimal Blender Python probe for the count/sum gate:

```python
import math

def deform_groups(obj, arm):
    deform = {b.name for b in arm.data.bones if b.use_deform}
    return {g.index: g.name for g in obj.vertex_groups if g.name in deform}

def weight_report(obj, arm, eps=1e-8):
    idx_to_name = deform_groups(obj, arm)
    out = {"unbound": [], "over4": [], "bad_sum": [], "max_influences": 0}
    for v in obj.data.vertices:
        ws = [g.weight(v.index) for g in v.groups if g.group in idx_to_name and g.weight(v.index) > eps]
        n, s = len(ws), sum(ws)
        out["max_influences"] = max(out["max_influences"], n)
        if n == 0: out["unbound"].append(v.index)
        if n > 4: out["over4"].append(v.index)
        if n and abs(s - 1.0) > 1e-4: out["bad_sum"].append((v.index, s))
    return out
```

For deterministic top-4 cleanup outside the UI, sort each vertex's positive deform weights descending, keep the first four, delete the rest, renormalize, then write a JSON report. The Blender UI operator is acceptable only if all deform groups are selected and the result is rechecked.

### 5. Materials / PBR gate

For every material slot:

- verify a Principled BSDF is connected to Material Output;
- verify Base Color, Metallic, Roughness, Normal, and optional Emission sockets point to the intended images/nodes;
- verify normal images are Non-Color and color images are sRGB as appropriate;
- verify UV node/map names and material-slot names survive object duplication;
- pack images for `.blend` review or export GLB for a self-contained round trip; for FBX use Path Mode Copy + Embed Textures;
- export, re-import to a clean Blender scene, and compare names, counts, bounds, material slots, UV layers, and image dimensions;
- open the result in the target engine under a neutral light, because shader conversion can expose issues invisible in Blender.

Run the Khronos glTF Validator on every GLB; treat warnings as review items and errors as a hard fail.

### 6. LOD gate

1. Freeze approved `LOD0`; generate LOD1/LOD2/LOD3 on duplicates.
2. Start with measured percentages rather than a universal number; a practical first pass is 50%, 25%, 12.5% of LOD0 triangles, then tune by silhouette and frame-time budget.
3. Preserve UVs/material slots and protect silhouette, seams, joint loops, and high-value armor sections. For Unreal skeletal reduction, set Max Bone Influence explicitly and prioritize bones/sections; use Lock Mesh Edges when silhouette edges are being damaged.
4. Recheck all LODs for zero-area/degenerate faces, normals, UV bounds, material slot parity, and weight limits.
5. Pose every LOD at the same stress frames and compare silhouette/penetration. The far LOD may simplify detail, but it must not explode, detach, or expose the body under armor.
6. Import to Unity/Unreal and verify actual screen-space transition, hysteresis, material/shader parity, and memory/triangle metrics.

### 7. Round-trip / engine admission gate

A candidate is admitted only after:

- Blender source → exported GLB/FBX → clean Blender re-import;
- glTF Validator (for GLB) passes;
- object/material/bone/UV/bbox manifest matches expected values;
- all vertices are bound and ≤4 influences with normalized sums;
- representative animation frames pass geometry-anchored body↔armor penetration checks;
- target engine import has correct scale, orientation, materials, sockets, and LOD transitions;
- final output is hashed and accompanied by the manifest, QA report, and source provenance.

Do not use GLB re-import manifold counts as the sole topology gate: UV, normal, material, and skin seams can duplicate vertices on export. Gate names, materials, dimensions, skin attributes, validator status, and visible/posed parity instead.

## Research limitations

- Reddit is user-generated and sometimes anecdotal; the high-poly reports are useful for failure modes and operator latency, not universal performance limits.
- YouTube extraction did not expose transcripts; the five current workflow videos have exact upload dates from `yt-dlp`, while the older weight-transfer link is dated by the 2021 Stack Exchange answer that cites it.
- Vendor pages (Meshy, FAL, Hyper3D/80 Level, Customuse) describe intended capabilities and example workflows, not independent acceptance tests.
- The strongest evidence for this project’s 353k-vertex Meshy limb remains the local observed failure: Blender loose-part separation hung twice while an external spatial face partition succeeded. This report uses community evidence to support the same fail-closed workflow, not to claim identical hardware timings.
