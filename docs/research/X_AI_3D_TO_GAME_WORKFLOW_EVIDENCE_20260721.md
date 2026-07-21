# Verified AI-3D → game workflows shared on X

**Research date:** 2026-07-21
**Scope:** Meshy, Tripo, Hyper3D/Rodin, Hunyuan3D and adjacent AI-3D workflows that show an actual game/build/engine result or a concrete production cleanup sequence.
**Evidence rule:** An X post is primary evidence of what its author claims or demonstrates. It is not independent proof of shipping quality. Broad “game-ready” or “one-click” claims without a visible build, repo, or exact process are rejected.

## Bottom line

The strongest repeatable pattern is **AI for controlled base/component generation, then DCC cleanup and engine validation**. The best X evidence is AssetHub’s modular Tripo 3.1 → Blender/Maya/ZBrush → Substance Painter → Blender rig → Unreal workflow. It explicitly shows an in-engine result and names the cleanup stages. The strongest independent process description is kano’s Tripo → Blender auto-retopo → UV → Substance Painter → Unity/Unreal post, but it exposes no asset, repository, metrics, or engine capture. Tripo’s official racing post and George Kal’s Rodin/Byrsa post show engine/prototype integration, but are vendor-affiliated or paid and omit the hard gates needed for a combat asset.

**No X source found in this pass proves a shipped, hero-quality, AI-generated humanoid with measured topology, skin-weight, collision, LOD, and engine-deformation QA.** The evidence supports AI-assisted prototypes, background/NPC assets, props, and modular rigid armor—not replacing Just Dodge’s canonical body, hands, skeleton, or combat-authoritative pipeline.

## Admitted X evidence

### 1. AssetHub modular character — strongest cleanup evidence

- **X URL:** https://x.com/assethub_io/status/2062928898405659040
- **Author/handle:** AssetHub, `@assethub_io`
- **Date:** 2026-06-05 (post timestamp shown as 4:05 PM)
- **Observed claim/result:** “New 3D AI Workflow for Modular Game Characters Running in-game in Unreal Engine!” The post includes a video and states that the character is assembled and brought into Unreal with a dynamic cloth-sim rig.
- **Visible/tool lineage stated in post:** Concept image from Nano Banana 2; Tripo 3.1 for most parts; Hitem3D for a few parts.
- **Exact observed workflow:**
  1. Break the concept into modular head, torso, arms, armor and accessories.
  2. Auto-detect pose, split into parts, and generate reference images for each piece.
  3. Generate high-poly meshes per part.
  4. Assemble in Blender.
  5. AI + manual retopo.
  6. AI UV and unwrap in 3ds Max.
  7. AI texture with Tripo/Hitem3D, then rework in Substance Painter.
  8. Add normals, roughness and micro-details.
  9. Rig in Blender.
  10. Bring the result into Unreal Engine with a dynamic cloth-simulation rig.
- **Evidence grade:** **B+** — direct original post, specific stage list, and a video framed as an in-engine result; vendor-affiliated and no public asset/repo, polygon counts, weight report, collision recipe, LOD measurements, or independent reproduction.
- **Failure/omission:** No evidence that all parts pass deformation stress poses, no stated body masking/clearance method, no collision/physics-asset details, and no export/reimport validation.
- **Just Dodge value:** Strong precedent for a modular armor/weapon route. Use the process as a candidate-production template, not as proof that Tripo/Hitem3D output is already acceptable for a hero duelist.

### 2. AssetHub + MetaHuman modular character — strongest character-production pattern

- **X URL:** https://x.com/assethub_io/status/2068012076673769711
- **Author/handle:** AssetHub, `@assethub_io`
- **Date:** 2026-06-19 (post timestamp shown as 4:44 PM)
- **Observed claim/result:** “New 3D AI + MetaHuman Workflow for a Modular Game Character Running in-game in Unreal Engine!” A video accompanies the post.
- **Visible/tool lineage stated in post:** Concept from GPT-Image2; all part references and base meshes generated through AssetHub using Tripo 3.1 multi-view → 3D.
- **Exact observed workflow:**
  1. Use the AI-generated full body as a proportion guide.
  2. Scale-match and assemble all parts in ZBrush.
  3. Sculpt a MetaHuman base to match the AI-generated face/body and detail it in ZBrush.
  4. Assemble the remaining parts.
  5. Manual retopo in Maya with Quad Draw.
  6. Create UVs and material sets in Maya.
  7. Bake, then texture in Substance Painter: skin, cloth, leather, gold embroidery and metal, including normals, roughness and micro-details.
  8. Groom hair in XGen.
  9. Show the assembled result running in Unreal Engine.
- **Evidence grade:** **B+** — exact DCC/tool sequence plus in-engine video; vendor-affiliated, no independent asset package or measurable deformation/export report.
- **Failure/omission:** The post says “clean, animation-ready topology” but does not show vertex/triangle budgets, joint influence limits, collision, LODs, or a round-trip validator result. The MetaHuman body is a controlled replacement/carrier, so this is not evidence that an unconstrained AI humanoid can be shipped directly.
- **Just Dodge value:** This is the clearest evidence for **AI concept/proportion reference + canonical/controlled body + manual retopo**. It aligns with retaining the accepted MPFB/C0 body and using generated armor/face references rather than replacing the combat body wholesale.

### 3. Tripo racing prototype in Unity

- **X URL:** https://x.com/tripoai/status/2065449043510100067
- **Author/handle:** Tripo, `@tripoai`
- **Date:** 2026-06-12 (post timestamp shown as 3:00 PM)
- **Observed claim/result:** A video/post says multiple AI-generated characters and vehicles were brought into one racing scene; textures and motion were refined; animations were polished in Blender; the result was assembled into a racing prototype in Unity.
- **Exact observed workflow:** AI-generated assets → texture/motion refinement → Blender animation polish → Unity prototype assembly.
- **Evidence grade:** **B-** — original tool-vendor post with a visible prototype claim and an explicit Blender-to-Unity stage; no independent build/repo and no technical metrics.
- **Failure/omission:** Does not state model version beyond the Tripo brand, retopo method, UV checks, collision setup, LODs, engine import settings, or whether the models were created by the same pipeline shown.
- **Just Dodge value:** Supports using AI assets for a playable prototype, but not promotion to combat assets without a separate topology, skinning, collision and animation gate.

### 4. George Kal / Byrsa web-first engine + Rodin Gen-2.5

- **X URL:** https://x.com/georgevibing/status/2057039145294266662
- **Author/handle:** George Kal, `@georgevibing`
- **Date:** 2026-05-20 (post timestamp shown as 10:02 AM)
- **Disclosure:** X labels the post “Paid partnership.”
- **Observed claim/result:** While building Byrsa, described as a web-first game engine, the author tested Rodin Gen-2.5 to create dungeon-scene assets and load them in-engine. The post claims 1M-poly models in about 4 seconds, up to 10M+ detail, 3D-native PBR, and speed/detail modes.
- **Exact observed workflow:** Rodin Gen-2.5 generation → asset loading into the Byrsa engine → dungeon-scene assembly.
- **Evidence grade:** **B- for engine loading / C for production readiness** — actual engine context is stated and shown, but the partnership disclosure and lack of public asset/repo/cleanup metrics limit independent verification.
- **Failure/omission:** No retopo, semantic part split, UV repair, rigging, collision, LOD, or engine-deformation evidence. The post emphasizes raw polygon count and native materials, which are not substitutes for a runtime budget.
- **Just Dodge value:** Rodin is a plausible environment/prop candidate. Prefer Quad mode and an explicit face budget for real-time work; treat Raw/high-poly output as bake/source data, not directly renderable combat geometry.

### 5. kano’s 10-minute Tripo game-asset workflow

- **X URL:** https://x.com/Aoleihal/status/2032669333873373614
- **Author/handle:** kano, `@Aoleihal`
- **Date:** 2026-03-14 (post timestamp shown as 4:05 AM)
- **Observed claim:** “My AI 3D workflow for game dev (10 min per asset).”
- **Exact observed workflow and claimed timings:**
  1. Generate base model in Tripo — 30 seconds.
  2. Auto-retopo in Blender — 2 minutes.
  3. UV unwrap — 1 minute.
  4. Substance Painter materials — 5 minutes.
  5. Export to Unity/Unreal.
- **Evidence grade:** **C+** — firsthand post with a clear, reproducible sequence; no attached asset, engine capture, repo, polygon/UV/material report, collision, or deformation test.
- **Failure/omission:** “Export to Unity/Unreal” is not demonstrated in the extracted post; no distinction between prop and character; no stated version of Tripo, Blender, or Substance Painter; no manual repair allowance despite the 10-minute claim.
- **Just Dodge value:** Good fast-path candidate for simple static props and disposable prototype assets. Do not use the timing as a production estimate for articulated armor, weapons with sockets, hands, or the hero body.

### 6. Jade Truong / Meshy playable prototype

- **X URLs:**
  - https://x.com/JadeTruong3107/status/2032687602797785219
  - https://x.com/JadeTruong3107/status/2033026182275608992
- **Author/handle:** Jade Truong, `@JadeTruong3107`
- **Dates:** 2026-03-14 and 2026-03-15 (the second post timestamp shown as 3:43 AM)
- **Observed claim/result:** A small game prototype was made with Codex CLI, GPT-5.4 and Meshy; the later post says Meshy generated 3D models and handled rigging/animation, while Codex wired the result into a playable prototype. The post includes fighting footage and says there is already a clip of the two characters fighting in the game.
- **Exact observed workflow:** Prototype game concept/logic → concept art/visual direction → Meshy models → Meshy rigging/animation → Codex wiring → playable game-engine prototype → iterate.
- **Evidence grade:** **C** — a real playable prototype is claimed/shown, but the post does not expose cleanup, topology, UV, material, collision, engine, model version, or export steps.
- **Failure/omission:** This is prototype evidence only. It cannot establish hero-character deformation quality or a production pipeline.
- **Just Dodge value:** Validates the use of Meshy for rapid gameplay/visual prototyping, not for replacing the accepted duelist body or combat rig.

## Rejected X claims / non-admissions

- **Amit, `@HeyAmit_`, 2026-03-07:** https://x.com/HeyAmit_/status/2030247191508623792 — says Meshy fits Unreal/Unity/Blender/animation/printing workflows and summarizes “Text → Image → 3D → Export → Use,” but provides no identifiable build, repo, asset lineage, cleanup steps, or QA. **Rejected as production evidence (D).**
- **Meshy official DCC-bridge post, 2025-11-14:** https://x.com/MeshyAI/status/1989351908029644817 — says the DCC Bridge can send a model to Blender, but a bridge capability is not proof of a successful game asset. **Capability reference only.**
- **Hyper3D/Deemos Rodin Gen-2.5 launch, 2026-05-19:** https://x.com/deemostech/status/2056744290689441833 — 10M-polygon and native-texture claims without a specific game/build cleanup path. **Rejected as production evidence (D).**
- **Tencent Hunyuan3D Engine integration, 2025-11-26:** https://x.com/TencentHunyuan/status/1993501416036745377 — claims OBJ/GLB integration with Unreal, Unity and Blender, but no identifiable game/build or cleanup evidence. **Rejected as production evidence (D).**
- **Rodin texture/export post, 2026-06-03:** https://x.com/svpino/status/2062245722658054195 — demonstrates/claims textured output and export targets, but no game/build or cleanup proof. **Not admitted beyond export capability.**

## Primary-source corroboration

These sources establish supported capabilities and required production steps. They do **not** independently validate the X creators’ specific assets.

### Tripo official guidance

- **H3.1 announcement:** https://www.tripo3d.ai/blog/introducing-hd-model-v3-1 — describes H3.1 as high-density/PBR-oriented and links DCC bridges for Unreal, 3ds Max and Unity. Use as capability/context, not game-readiness proof.
- **Blender-to-Tripo workflow:** https://www.tripo3d.ai/education/blender-poly-to-ai-sculpting-workflow — concrete guidance to block out the silhouette, apply modifiers, Merge by Distance, apply scale, use OBJ/FBX with `-Z Forward / Y Up`, inspect the generated draft, return to Blender for manual sculpting, and use Quad Remesher or Voxel Remesh before baking high-detail maps onto a lower mesh. It also describes auto-rigging and FBX export to Unity/Unreal, while explicitly saying manual topology/material work remains necessary.
- **Game retopo/UV/engine article:** https://www.tripo3d.ai/game-development/ai-3d-modeling-tools-with-automatic-uv-mapping-and-retopology-for-games — vendor guidance on Smart Low Poly, quad vs triangle topology, target face limits, UV/PBR generation, and DCC bridges. Marketing-weighted; treat as supported workflow shape, not validation.
- **Weapons/armor article:** https://www.tripo3d.ai/game-development/generating-fantasy-weapons-and-armor-assets-using-ai-3d-tools-for-rpgs — describes Smart Part Segmentation for pauldrons/breastplates/gauntlets/greaves, Smart Mesh/retopology, Magic Brush/PBR texturing, and Blender/Unity/Unreal bridges. It supports a modular armor strategy but is not independent evidence.

### Hyper3D/Rodin official guidance

- **Rodin Gen-2.5 API specification:** https://developer.hyper3d.ai/api-specification/rodin-gen2.5 — exposes `geometry_file_format` (`glb`, `usdz`, `fbx`, `obj`, `stl`), PBR/shaded materials, quality tiers, `TApose`, `mesh_mode` (`Raw` or `Quad`), and quality/face-count ranges. The docs state Quad mode targets real-time-oriented lower budgets while Raw can be very dense. For a game candidate, record the exact tier, mesh mode, quality override, pose flag and export format.
- **Rodin Unreal add-on:** https://docs.deemos.dev/addon/readme-ue — supports Unreal Engine 5.1–5.6, single-image and multiview inputs, ControlNet, manual/one-click generation, and automatic import into an Unreal scene. This proves integration capability, not that the imported asset passes collision/rig/LOD gates.
- **Hyper3D API introduction:** https://developer.hyper3d.ai/ — states Rodin outputs CG-friendly assets for Unity, Unreal and Maya; this is vendor positioning, not independent validation.

### Meshy official guidance

- **Game asset workflow:** https://docs.meshy.ai/en/webapp/guides/use-cases/game-assets — explicit sequence: Generate → Remesh to a target budget → AI Texturing with PBR maps → Rig → Animate → export FBX/GLB. It lists rough planning bands of 3K–5K for mobile characters, 20K–50K for PC/console characters, and 5K–15K for PC/console props.
- **Rigging:** https://docs.meshy.ai/en/webapp/guides/3d-model/rigging — says Remesh before Rig, use T/A pose, and that facial expressions/tail physics require manual DCC rigging. It documents clipping from dense/uneven topology and abnormal deformation from non-standard proportions.
- **Animate:** https://docs.meshy.ai/en/webapp/guides/animate — supports 500+ presets and FBX/GLB export, but says custom choreography/facial work requires Blender/Maya/manual retargeting.

### Engine and DCC primary sources for the missing hard gates

- **Unreal Skeletal Mesh assets:** https://dev.epicgames.com/documentation/en-us/unreal-engine/skeletal-mesh-assets-in-unreal-engine — FBX from a DCC imports the mesh/skeleton/animations; Unreal then exposes Skeletal Mesh, Skeleton, Physics Asset, Animation Sequence and Character Blueprint integration. It documents modular characters assembled from multiple skeletal meshes sharing a skeleton.
- **Unreal Physics Asset Editor:** https://dev.epicgames.com/documentation/en-us/unreal-engine/physics-asset-editor-in-unreal-engine — Physics Assets define rigid bodies/constraints used for skeletal collision and simulation. This is the authoritative reason not to use AI render geometry as combat collision.
- **Unreal skeletal LOD import:** https://dev.epicgames.com/documentation/en-us/unreal-engine/importing-skeletal-mesh-lods-using-fbx-in-unreal-engine — supports LODs from Blender/Maya/3ds Max; the Unreal FBX pipeline uses FBX 2020.2 and warns that a different export version can be incompatible.
- **Unity model import:** https://docs.unity3d.com/6000.3/Documentation/Manual/ImportingModelFiles.html — documents FBX as the primary model path, model/rig/animation/material import settings, normal-map import considerations and prefab/Animator use.
- **Unity skinned-mesh limits:** https://docs.unity3d.com/2019.1/Documentation/Manual/ImportingSkinnedMeshes.html — documents the default four bone influences per vertex and warns that exceeding the limit can cause choppy/distorted animation unless influences are reduced or otherwise handled before export.
- **Blender Shrinkwrap:** https://docs.blender.org/manual/en/latest/modeling/modifiers/deform/shrinkwrap.html — supports controlled fitting/clearance with offsets and vertex groups, but is not a replacement for deformation-aware retopology or manual armor clearance.
- **Blender retopology:** https://docs.blender.org/manual/en/latest/modeling/meshes/retopology.html
- **Blender baking:** https://docs.blender.org/manual/en/latest/render/cycles/baking.html

## Exact production cleanup recipe for Just Dodge

This is the operational recipe synthesized from the admitted X sequences, primary tool docs, engine docs, and the existing Just Dodge asset gates. It is a recommendation, not a claim that every X post completed every step.

1. **Intake and quarantine**
   - Record source X/URL, generator, exact model/version, date, plan/license, source image set, SHA-256, file format, Blender/DCC version and importer settings.
   - Keep the untouched result as `SOURCE_HIGH` / `BAKE_HIGH`; never apply remesh, Make Manifold, Decimate or destructive modifiers to the only copy.
   - Measure evaluated vertices/faces/triangles, world-space bounds/height, material slots, image paths, UV layers, armature/bone count and loose-component histogram.

2. **Semantic decomposition before cleanup**
   - Prefer generator/service-side part splitting, explicit component generation, material/region masks or controlled cuts.
   - Name parts by mechanical role: body, cuirass, pauldron, vambrace, gauntlet, greave, boot, weapon, grip, blade, cloth, hair and collision proxy.
   - Do not start with Blender `Separate by Loose Parts` on a dense AI mesh. Use a streaming connected-component/spatial partition pass or a disposable proxy first.

3. **Build a deformation-aware low mesh**
   - Create `RETOPO_LOW` with loops around shoulders, elbows, wrists, hips, knees, ankles and any remaining digit joints.
   - For rigid armor, preserve hard plate boundaries and explicit pivots; for soft/continuous pieces, maintain continuous edge flow.
   - Use AI/Quad Remesher/Voxel Remesh only as a starting point or budget tool; inspect silhouette, holes, normals, manifoldness and part boundaries. Preserve the high source for projection/baking.

4. **Fit, clear and assemble modular armor**
   - Align body and armor in the same bind pose; apply transforms only after measuring world-space bounds.
   - Clear stale/foreign groups and modifiers on generated armor; parent to the canonical armature with empty groups.
   - Transfer/paint weights from the clean body for soft pieces; bind rigid plates to one deform bone or explicit armor pivot.
   - Use `Armature → Shrinkwrap` only when the engine will not reproduce the modifier; keep a deliberate offset/clearance shell.
   - Mask/delete hidden body under non-removable armor combinations. Add a separate low-poly collision proxy for exposed skin/skirts/capes; do not treat a body mask as proof that penetration is solved.

5. **UV and material pass**
   - UV unwrap the low mesh; use separate material sets/texture sets for armor, cloth, leather, skin, metal and weapon parts.
   - Bake high → low for normal/AO/color/roughness as appropriate using a cage/extrusion; inspect cage rays, seams and tangent direction.
   - Verify Principled/PBR connections, image color spaces, UV map names and material-slot parity. AI textures are a base pass; paint hero wear, AO/grime, scratches and readable edge treatment in Substance Painter or equivalent.

6. **Skeleton, weights and articulation**
   - Keep the accepted C0/MPFB body skeleton as the authority for Just Dodge hero characters.
   - Normalize weights, limit retained deform influences to four for Unity-compatible interchange, normalize again, and fail on unbound/non-finite/non-normalized vertices.
   - Test bind pose and extreme poses: shoulder abduction, elbow/knee 90°, wrist/ankle twist, crouch, hand/finger flex, weapon grip and armor-specific stress poses.
   - For generated background NPCs, Meshy/Tripo/Rodin auto-rig can be a candidate path only after remesh, T/A-pose validation and engine deformation review.

7. **Collision and LOD**
   - Never use the detailed render mesh as combat collision. Author low-poly per-part/body collision proxies; in Unreal create/edit a Physics Asset with bodies and constraints; in the custom engine keep collision geometry separate from the render asset.
   - Freeze approved LOD0; generate LOD1+ from duplicates, protect silhouette, seams, joint loops and material slots, and re-test weights/deformation at every LOD.

8. **Export, round-trip and engine proof**
   - Export the interchange format required by the target: FBX for Unreal/Unity skeletal pipelines; GLB for self-contained material/visual review. Use FBX 2020.2 for the Unreal path.
   - Re-import into a clean DCC scene and compare counts, bounds, materials, UVs, skeleton and animation clips. Run the Khronos glTF Validator on GLB.
   - In Unity, verify rig mapping, max skin weights, materials, normals/tangents, Animator clips and prefab scale. In Unreal, verify Skeleton, Physics Asset, Animation Blueprint, LODs, sockets and modular assembly.
   - For Just Dodge, run the existing Blender/FBX extraction and SKM1/ANM1 validators, verify engine-space height/axis conversion, then run the actual engine smoke scene with bind pose and representative animation frames.

9. **Promotion rule**
   - Promote only after machine gates and human multi-view review pass. A post showing a model inside an engine is evidence of integration/prototyping, not a waiver for topology, weights, material, collision, LOD, license or combat-readability gates.

## Recommendations

- **Adopt now:** Tripo/Meshy/Rodin for weapons, rigid armor plates, environment pieces, NPC variants and prototype coverage; use image/multi-view references and component-first generation.
- **For the hero/duelist:** retain the accepted canonical body, hands, fingers, face and skeleton. Use AI meshes as armor/weapon/accessory candidates or surface/detail references.
- **Use the AssetHub sequence as the closest external pattern:** semantic parts → DCC assembly → manual or AI-assisted retopo → UV/material sets → bake → Substance Painter → rig → engine test. Add the missing Just Dodge gates for collision, LOD, four weights, round-trip validation and combat pose QA.
- **Use Rodin Gen-2.5 in Quad mode with an explicit face budget** for real-time candidates; keep Raw/high-density outputs only as source/bake material.
- **Use Meshy’s Generate → Remesh → Texture → Rig → Animate → Export route only for standard humanoids/background NPCs**; custom facial, cloth, finger and combat articulation remain manual/controlled DCC work.
- **Reject any candidate whose only evidence is a marketing phrase:** “game-ready,” “production-ready,” “one click,” “10M polygons,” or “full pipeline” without a concrete engine/build/process and a measurable acceptance receipt.

## Source notes

- X page text was fetched directly from the exact post URLs via the web extractor on 2026-07-21; timestamps, handles, disclosures, text and view/reply counts reflect the accessible X pages at retrieval time.
- No generation task, paid credit, or external asset download was initiated.
- Existing repository research used as local context: `docs/research/AI_3D_TO_BLENDER_ENGINE_EVIDENCE_20260720.md`, `docs/research/MESHY6_USER_EXPERIENCE_RESEARCH_2026-07-20.md`, and `docs/research/AGENTIC_GAME_ASSET_RECOVERY_2026-07-21.md`.
