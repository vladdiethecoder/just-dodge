# Frontier Prompting for Phenomenal Generative Game Assets

**Date:** 2026-07-21
**Project:** Just Dodge
**Scope:** Prompt and reference construction for GPT Image / other image models -> Meshy or frontier image-to-3D -> Blender/LLM cleanup -> custom-engine admission.
**Decision:** Stop treating one long adjective-heavy prompt as the production method. The highest-yield workflow is a specification-driven, image-conditioned, multi-view, generate-select-repair loop with a fixed style system, explicit physical structure, and mechanical Blender validation.

## 1. Result

The strongest repeated result across official model guidance, research systems, user workflows, and Blender automation practice is:

1. **Use the LLM as art director, constraint compiler, critic, and DCC operator.** Do not ask it to hallucinate a finished asset in one step.
2. **Generate a clean 2D reference before 3D.** Microsoft explicitly recommends text -> image -> TRELLIS-image because text-conditioned 3D is less creative and detailed. Meshy says Image to 3D is more precise than text alone. Successful Meshy game users independently converged on ChatGPT/Meshy image generation -> Image to 3D.
3. **Reference-image quality dominates downstream geometry.** One subject, full extents, near-orthographic projection, plain background, even diffuse lighting, sharp focus, and no nonphysical effects or occlusion.
4. **Use multiple consistent views whenever possible.** Front + side + back + 3/4, identical identity/proportions/materials/pose/scale/lighting. This removes hidden-side guesswork.
5. **Separate shape, texture, rigging, and runtime cleanup.** Hunyuan3D uses a two-stage shape-then-texture architecture. Meshy and production user workflows likewise select geometry before spending on texture, rig, or engine integration.
6. **Generate multiple candidates and reject aggressively.** Aiko reports four mesh versions and thirteen texture versions for one chosen asset. StraySpark reports two to three variants per weapon. One-shot acceptance is not supported by successful practice.
7. **In Blender, prompt one bounded transformation at a time after inspection.** The effective prompt contract is exact object IDs + measured baseline + one operation + numeric parameters + invariants + requested verification. “Make it game-ready” is not an executable specification.

“Phenomenal” comes from the closed loop, not from superlatives in the initial prompt.

### Two different prompt regimes

- **GPT Image / reference construction:** a longer labeled specification is useful because the model controls composition, anatomy, materials, exclusions and invariant-preserving edits.
- **Meshy Text to 3D:** successful official/user examples are compact—object first, then roughly 3-5 defining construction/material/style details and technical constraints. Word order matters; adjective accumulation hurts.
- **Meshy Image to 3D:** the image and pose controls dominate shape. Current API text chiefly guides texture, so copying the full GPT Image prompt into Meshy does not create a second reliable geometry-control channel.

## 2. Evidence hierarchy

### Primary / official mechanisms

- Meshy Prompting Best Practices (retrieved 2026-07-21): subject + material/texture + art style + technical constraints; important information first; avoid contradictions and empty adjectives.
  https://docs.meshy.ai/en/webapp/guides/prompting
- Meshy's official pages currently disagree about negative prompts: the Docs prompting page recommends exclusion phrases, while the Help Center article updated 2026-06-10 says negative prompts are not available. This workflow therefore does **not** rely on a Meshy negative-prompt channel; exclusions are enforced in the GPT Image reference, candidate selection, and DCC gates.
  https://help.meshy.ai/en/articles/11972484-best-practices-for-creating-a-text-prompt
- Meshy Image to 3D (retrieved 2026-07-21): clear single subject, simple background, >=512 px; near-orthographic projection; even lighting; Standard for maximum detail; Smart Topology for production-oriented separated parts; custom T/A pose; multi-view for hidden-side accuracy.
  https://docs.meshy.ai/en/webapp/image-to-3d
- Meshy Multi-View help, updated 2026-06-10: 2-4 complementary angles, same character/style/lighting/scale, plain background, >=1040 px, no cropped extremities, neutral T/A pose.
  https://help.meshy.ai/en/articles/12634481-how-to-use-multi-view
- OpenAI GPT Image Generation Models Prompting Guide, 2026-04-21: prompt in stable order; specify intended use, framing, viewpoint, lighting, body framing and interactions; state invariants and exclusions; use small iterative edits instead of overloading.
  https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide
- TRELLIS official repository: image conditioning is recommended over text conditioning; text -> image -> TRELLIS-image is the recommended path because text-conditioned 3D is less creative and detailed. Multi-image conditioning exists but is tuning-free and can fail on some inputs.
  https://github.com/microsoft/TRELLIS
- Hunyuan3D-2 official repository: shape generation and texture generation are separate foundation stages; Hunyuan3D-2mv provides a multi-view image-to-shape model; Hunyuan3D-2.1 adds PBR generation and training code.
  https://github.com/Tencent-Hunyuan/Hunyuan3D-2
- PartCrafter, arXiv:2506.05573: jointly generating semantically distinct parts improves structured fidelity, editability, and texture assignment; monolithic generation causes color bleeding and less plausible part structure.
  https://arxiv.org/abs/2506.05573
- CraftsMan3D official repository: coarse regular mesh first, then normal-guided multi-view geometry refinement; official advice is to vary seed/CFG/scheduler rather than expect a single prompt to dominate stochastic output.
  https://github.com/HKUST-SAIL/CraftsMan3D
- Meshy Auto Split, updated 2026-07: currently a 3D-printing feature for Meshy 6 Standard **untextured drafts**; it finds natural boundaries, cuts, and caps watertight parts. It is not a rigging or deformation-topology repair system.
  https://help.meshy.ai/en/articles/15898622-how-does-auto-split-work-in-meshy

### Successful-user / practitioner signals

These are useful workflow evidence but remain vendor-hosted or practitioner reports, not controlled benchmarks.

- **Soliloquis / Frontiers Reach**: Midjourney -> Meshy was unsatisfactory; Meshy’s own image generation taught him better aesthetic language. Exact successful character structure: “full body shot … [identity/function/style] … full body portrait, arms out in an A-Pose.” He then selected the cleanest mesh, textured/retopologized, and used basic rigging. He explicitly reports missing detailed finger/toe controls, acceptable for background NPCs but not a close-contact hero.
  https://www.meshy.ai/blog/indie-game-character-design-workflow
- **Aiko / Stylized Antiquity**: define persistent color, materials, silhouette language, and mood before generation; repeat the same core descriptors across assets; avoid over-complication; review mesh fidelity first; routinely compare four mesh versions and thirteen texture versions.
  https://www.meshy.ai/blog/3D-prompt-engineering
- **ShawnBuilds / FLOW STATE**: ChatGPT concept -> Meshy Image to 3D -> animation -> engine. Player feedback showed the first enemy did not match the world, so he regenerated a second version. The meaningful gate was in-game style fit, not generation completion.
  https://www.meshy.ai/blog/ai-in-game-development
- **Axx**: ChatGPT writes precise prompts and generates reference images; Meshy converts the selected reference; engine work then fixes scale, pivots, polycount, collision, and PBR bindings.
  https://www.meshy.ai/blog/solo-indie-dev-3d-platformer
- **StraySpark Blender MCP test, 2026-03-23**: prompts each weapon as object + named parts + material construction + real dimensions + game-use constraint, generates 2-3 variants, inspects exact mesh metrics, then issues one numeric Blender operation at a time. Its longsword succeeded better than more compound/occluded objects. This is a practitioner report from an MCP vendor, so its time and quality claims need independent reproduction.
  https://www.strayspark.studio/blog/text-prompt-game-ready-asset-blender-mcp-ai

## 3. The Just Dodge visual system—not “anime” or “realistic”

Style is subordinate to deep-sim readability. Every asset prompt must encode these pillars:

1. **Anatomical hierarchy:** head, ribcage, pelvis, upper/lower limbs, hands and feet remain distinct at gameplay distance.
2. **Physical layer hierarchy:** body -> padded underlayer -> rigid armor -> straps/closures -> weapon. Contact and failure should be attributable to a visible layer.
3. **Joint clearance:** shoulders, elbows, wrists, hips, knees and ankles have visible deformation space; armor plates do not bridge or fuse across joints.
4. **Contact legibility:** striking edges, grip surfaces, guard, pommel, armor coverage and exposed articulation zones are visually obvious.
5. **Material causality:** steel, textile, leather and skin differ in roughness, thickness and response—not merely color.
6. **Silhouette economy:** no ornamental noise that hides limb pose, collision, wound location, weapon orientation or opponent identity.
7. **Runtime viewpoint:** first-person forearms/weapon and third-person opponent must each read clearly. A beautiful turntable that collapses in the combat camera fails.

A style may be graphic, painterly, cel-shaded, sculptural, exaggerated, or semi-naturalistic. It is rejected if it obscures physical state.

This is not a new aesthetic preference layered onto the project. It implements the locked `GAME_CANON.md` pillars “Physical Truth” and “Motion That Reads,” exact visual/collision parity, and the prohibition on player-mode debug overlays (`GAME_CANON.md:20-26,46,55`). It also makes the generation prompt respect the existing mechanism contracts: one canonical carrier/skeleton (`CHARACTER_EQUIPMENT_PROMOTION_CONTRACT.md:26-36`), separate semantic armor clusters rather than smeared joint weights (`:52-56`), named blade/guard/grip/pommel with calibrated socket geometry (`:58-60`), actual palm/finger/handle contact (`:62-74`), and armor fit/clearance through motion (`:76-87`).

## 4. Optimal prompt contract

### 4.1 LLM art-direction request

Ask the LLM to produce a **specification and testable prompt**, not generic prose:

```text
You are the asset art director for a first-person deep-simulation sword-combat game.
Return:
1. one 2D generation prompt;
2. one preserve-list for later edits;
3. one reject-list;
4. a reconstruction-risk checklist.

Asset function: [hero opponent / longsword / armor layer / prop].
Combat-readable requirements: [visible joints, contact zones, grip, armor coverage].
Physical construction: [named layers and how they attach].
Target views: [front, left side, back, front 3/4].
Pose: [strict T-pose or specified rigid prop orientation].
Style pillars: [shape language, palette, material behavior, mood].
Runtime constraints: [screen distance, triangle/texture target, first-/third-person use].
Invariants: one subject; full extents; consistent proportions and equipment; plain neutral background; even diffuse lighting; near-orthographic camera.
Reject: occlusion; cropped fingers/feet; fused limbs; floating pieces; effects; text; logos; dramatic perspective; dramatic shadows; transparent materials; loose cloth crossing limbs.
```

### 4.2 GPT Image character-reference prompt

Use labeled, maintainable sections. Do not lead with “AAA,” “beautiful,” or “masterpiece.” Lead with function and construction.

```text
INTENDED USE
A full-body source reference for image-to-3D reconstruction, rigging, close-contact combat and first-/third-person game cameras.

SUBJECT
One original adult human duelist in a strict neutral T-pose. Entire head, fingertips and boots visible with margin. Anatomically coherent 7.5-head proportions; arms end at mid-thigh when lowered; five distinct fingers per hand; straight symmetric legs; feet parallel.

PHYSICAL CONSTRUCTION
A fitted padded underlayer at every joint. Separate rigid torso, shoulder, forearm, thigh, shin and boot armor plates attached by visible straps and articulated gaps. Compact plates do not bridge the armpits, elbows, wrists, groin, knees or ankles. No weapon in the character reference.

DEEP-SIM READABILITY
The ribcage, pelvis, every limb segment, hand, joint gap and armor coverage boundary must remain distinguishable at gameplay distance. Material boundaries must explain likely contact, sliding, penetration and injury behavior.

STYLE SYSTEM
[project-specific silhouette language]. [restricted palette]. Steel, textile and leather have distinct roughness and thickness. Graphic clarity over photorealism; no ornamental detail that obscures anatomy or contact zones.

CAMERA / LIGHTING / BACKGROUND
Near-orthographic front 3/4 product reference, eye-level, minimal perspective distortion, centered. Neutral mid-gray seamless background with strong silhouette contrast. Two large diffuse lights at 45 degrees, flat exposure, no cast shadow crossing the body, no depth of field.

PRESERVE / EXCLUDE
One subject only. Preserve bilateral anatomy, exact outfit, exact proportions and material placement. No cape, skirt, dangling straps, hair crossing shoulders, weapon, shield, VFX, fog, particles, text, logo, watermark, cropped extremities, floating parts, fused fingers, fused legs, interpenetrating plates or dramatic action pose.
```

This is a generation reference, not final beauty art. A controlled A-pose is acceptable only if the 3D system’s custom pose stage reliably converts it to a verified T-pose.

### 4.3 Multi-view edit prompts

Create one accepted anchor first. Generate each additional view by **editing the anchor**, not independent text-to-image calls.

```text
Create the exact same character as Image 1 from a true left orthographic side view.
Change only camera azimuth to 90 degrees.
Preserve identity, face, body proportions, T-pose joint locations, armor pieces, straps, colors, material roughness, lighting, scale in frame and neutral background.
Do not redesign, mirror asymmetrical details, add or remove equipment, bend limbs, crop extremities, or change perspective.
```

Repeat for back and 3/4. Reject the set if landmarks do not agree across views. Meshy’s current recommendation is 2-4 complementary views; front/side/back/3/4 is the strongest general set.

Run one controlled comparison against Meshy's own `generate_multi_view` image workflow, because those views are optimized for its downstream reconstruction prior. Neither route is accepted by brand name: choose the set with lower cross-view landmark drift in face width, shoulder/hip/knee/ankle positions, armor boundaries and material placement.

### 4.4 Meshy text-to-3D prop prompt

Use this for bounded rigid props, not the hero character when an image reference is available:

```text
[OBJECT AND FUNCTION FIRST]
A functional two-handed longsword for close-range first-person combat.

[PHYSICAL PARTS]
Straight double-edged 92 cm steel blade with a continuous central fuller; 22 cm grip sized for two gloved hands; compact cross-guard; mechanically joined pommel; visible blade tang alignment. Every part connected; no sheath.

[MATERIALS]
Tempered dark steel blade, forged steel guard and pommel, tightly wrapped matte leather grip. Material boundaries follow construction.

[SHAPE / STYLE]
Readable, restrained silhouette with a clearly identifiable cutting edge, point, guard, grip and pommel. Styling follows the project’s [shape/palette] pillars and serves contact readability rather than realism or ornament.

[TECHNICAL CONSTRAINTS]
One centered isolated object; straight neutral orientation; exact 1.14 m total length; bilateral blade symmetry; clean hard-surface edges; no background geometry; no runes, glow, particles, chains, tassels, floating ornaments, text or labels.
```

Successful practitioner prompts use real dimensions and named construction, then generate 2-3 variants. Do not ask one generation to contain an entire weapon set or scene.

### 4.5 Meshy image-to-3D settings

For a hero character:

- Meshy 6 / latest.
- Multi-view when consistent views exist.
- Custom T-pose for rigging even if the anchor is a mild A-pose.
- Image enhancement **off** for an already sharp, controlled GPT Image reference; on only for genuinely weak inputs.
- Remove lighting on base color.
- Standard/high-detail first to test shape fidelity; do not spend downstream work on a failed silhouette.
- Generate PBR/HD texture only after geometry survives the 360-degree inspection.
- If a production low mesh is needed, derive it after approving the high-detail source. Smart Topology T2 is a candidate for separated parts and a controlled 100-15,000 triangle count, not proof of deformation-ready edge loops.
- Generate at least 3 candidates or vary seeds/settings. Select by back/side anatomy, hand separation and joint clearance—not front-view beauty.
- Do not assume text exclusions control Image-to-3D geometry. In the current API, `texture_prompt` guides texturing; the reference image and pose controls are the shape authorities.

### 4.6 Blender + LLM prompt schema

Every Blender MCP prompt should have seven fields:

```text
CONTEXT: immutable source path/hash and intended game role.
TARGETS: exact object/material/bone names; no broad “all character objects.”
OBSERVED BASELINE: measured verts/tris/islands/materials/UVs/manifold defects/bounds/influences.
ONE OPERATION: the exact import, repair, retopo, unwrap, material, rig or export unit.
PARAMETERS: numeric target and algorithm settings.
INVARIANTS: what must not move, merge, rename, lose UVs, lose weights, or change scale.
VERIFY: exact metrics, reimport checks and screenshots to return.
```

Example inspection prompt:

```text
Import candidate.glb into collection SG02_INCOMING without modifying the source file.
For every mesh and armature report: object name, world bounds in meters, vertex/triangle count, connected islands, non-manifold and degenerate counts, material slots, UV layers, armature modifier, bone count, unbound vertices, maximum and p95 influences per vertex. Do not repair anything. Save the report as JSON and return the exact path and SHA-256.
```

Example bounded repair prompt:

```text
Target only mesh JD_Duelist_LOD0 and bones LeftHand/RightHand.
Observed defect: finger webbing contains N bridge faces between named digit islands.
Separate only the measured bridge faces, preserve wrist seam, existing armature, material slots, UV layer names, world transform and vertex-group weights. Do not remesh the palm or alter any other body region.
Afterward report manifold/degenerate counts, digit island count, unbound vertices, max influences, and render front/back closeups of both hands in neutral and 45-degree flex poses.
```

Effective LLM/DCC work descends from data to one operation. A single prompt requesting import + retopo + rig + texture + LOD + collision + export hides failures and prevents falsification.

## 5. Meshy Split: useful, but not the claimed hand/limb repair

The user correctly identified separation as strategically useful. Two Meshy capabilities must not be conflated:

1. **Smart Topology / meshy-t2:** native separated parts with controllable triangle count. This is relevant for isolating armor plates, clothing shells and rigid accessories before Blender cleanup.
2. **Auto Split (July 2026):** currently accepts Meshy 6 Standard **untextured drafts**, finds natural structural boundaries, cuts them, and caps each result watertight for printing. It costs 10 credits per attempt and does not support textured models.

As of this research date, Auto Split is documented as a web/printing workflow and is not exposed by the current Meshy API/MCP tool surface. `meshy-t2` Smart Topology is exposed through Image-to-3D and is the automatable separated-parts experiment. Auto Split would require an explicit web interaction until Meshy publishes an API.

Therefore:

- Use Auto Split to recover or isolate **rigid semantic components** from an otherwise good untextured draft.
- Do not treat capped cuts as character deformation topology.
- Do not use it to claim fingers are anatomically reconstructed. A cut can separate geometry without creating correct interdigital surfaces, knuckle loops, UV continuity, weights or a hand rig.
- After split, Blender must inspect interfaces, remove caps where articulation is required, rebuild topology, transfer/bind weights, and run flex/extreme-pose tests.
- For fused fingers, the preferred first move is a better reference with clearly separated fingers and consistent multi-view silhouettes. Split is a salvage path, not an excuse to admit a poor source.

PartCrafter’s research result supports the larger direction: part-aware generation can improve structure and reduce color bleeding. But it does not make Meshy Auto Split a rigging tool.

## 6. Candidate selection rubric

Score each candidate before download/rigging; any hard failure rejects it.

| Gate | Hard requirement |
|---|---|
| 360-degree coherence | No melted back, duplicated limb, hidden cavity, floating shell or fused legs |
| Anatomy | Segment lengths plausible for the chosen style; hands/feet present; five distinct digits where close-contact interaction requires them |
| Joint clearance | Shoulder/elbow/wrist/hip/knee/ankle boundaries remain separable |
| Physical layering | Armor/cloth/straps attach coherently and do not bridge joints |
| Contact surfaces | Weapon edge, point, guard, grip and armor coverage are unambiguous |
| Material segmentation | Metal/textile/leather regions align with geometry and intended physical behavior |
| Camera readability | First-person weapon and third-person rival silhouettes remain readable at target FOV/distance |
| Repair cost | Defects are local and measurable; no full-body remesh or truth-changing presentation shortcut |
| Runtime budget | DCC metrics and target-device profile meet project limits after LOD/texture normalization |

Do not average hard failures into a passing score.

## 7. Rejected prompt patterns

- “AAA masterpiece, ultra detailed, 8K, cinematic” without construction, view and use constraints.
- Contradictory style stacks (“photorealistic cel-shaded painterly low-poly”).
- Full scenes, multiple subjects, equipment piles or front/back views inside one image.
- Dramatic perspective, foreshortening, rim light, heavy shadow, depth of field or motion blur in reconstruction references.
- Smoke, sparks, magic, transparency, loose chains, hair strands or particles that become floating geometry.
- Hidden/crossed hands, cropped feet, weapons covering limbs or clothing crossing the arm-body silhouette.
- Independent front/side/back generations that merely share a text prompt.
- “Game-ready,” “clean topology,” “proper rig,” or “make it good” as substitutes for measurable output constraints.
- A monolithic Blender prompt that performs every pipeline stage without intermediate inspection.

## 8. Falsifiable production experiment for Just Dodge

No further character promotion should occur until this experiment completes:

1. Generate four GPT Image anchor candidates using the deep-sim reference template and one fixed style-pillar block.
2. Reject any anchor that is not reconstruction-safe even if visually attractive.
3. For the best two anchors, create side/back/3/4 views through high-fidelity edits with explicit preserve lists.
4. Run Meshy 6 multi-view Standard/custom T-pose shape generation for both.
5. Inspect 360-degree shape before texture/rig. Record anatomy, joint clearance, islands and fused geometry.
6. Run one meshy-t2 Smart Topology comparison on the better anchor to test whether separated armor reduces Blender repair cost.
7. Auto Split is invoked only if a high-quality untextured Standard draft has a rigid-part fusion that aligns with natural armor boundaries. It is not used on hands as an automatic acceptance path.
8. Import surviving candidate(s) into Blender. First prompt is inspection-only. Subsequent prompts perform one measured repair each.
9. Keep only a candidate that passes hand flex, shoulder/elbow/knee extreme-pose, grip socket, weapon alignment, material segmentation and native first-/third-person camera checks.
10. Compare against the rejected SG02 carrier using new actual native captures. Human visual rejection remains authoritative.

### Competing hypotheses

- **H1 — prompt wording is the main limiter.** Prediction: better text alone fixes hidden-side anatomy across seeds. Falsifier: multi-view references dominate while wording changes do not.
- **H2 — reference construction is the main limiter.** Prediction: controlled multi-view, neutral-pose references sharply reduce fused anatomy and back-side hallucination. Falsifier: defects persist across consistent views and providers.
- **H3 — generator prior is the main limiter.** Prediction: the same reference produces materially different structural quality in Meshy Standard, meshy-t2, Hunyuan3D/TRELLIS/other providers. Falsifier: all fail at the same reference ambiguities.
- **H4 — DCC repair can reliably promote near-misses.** Prediction: bounded Blender repairs preserve identity/UV/weights and pass deformation checks. Falsifier: repairs repeatedly require full remesh, destroy weights or create new joint defects.

Results, not prompt elegance, choose the method.

## 9. Current empirical state

- The borrowed Ruby candidate was explicitly rejected and fully rolled back. It is not a future option.
- A new original deep-sim armored-duelist reference was generated with GPT Image. It is materially coherent but the image model produced a lowered-arm A-pose despite “strict T-pose”; this confirms that pose text is not a sufficient gate.
- Meshy task `019f85a5-b944-7d64-8e54-6dcbdf5619d7` then succeeded using Meshy 6/latest with custom `t-pose`, Standard, PBR, HD texture and no remesh. It consumed 30 credits. Per owner direction, the completed GLB has **not** been downloaded or promoted pending this research. Its quality is unknown until actual inspection.

### Prompt postmortem

The reference prompt did several high-value things correctly: one isolated full body; complete fingers and boots; plain gray background; even product lighting; named armor layers; no weapon/cape/effects. The image confirms those controls worked. It also exposed three prompt defects:

1. “AAA-quality,” “anime,” “realistic first-person,” and “PBR” mixed prestige/style labels instead of defining one game-functional visual system. The revised template replaces them with anatomy/contact/material-readability constraints.
2. “Front three-quarter but nearly orthographic” is useful as a secondary depth view but weaker than a true front anchor for landmark-controlled multi-view work. The next experiment starts with a true front and derives 3/4 by edit.
3. Repeating “strict T-pose” did not mechanically produce horizontal arms. Pose must be measured in the image, corrected by a surgical edit or downstream custom pose control, and verified again in 3D.

The next action after this research is not automatic integration. It is to retrieve and inspect that already-paid candidate as an empirical test of the protocol, then decide whether to reject it, use it only as a baseline, or generate the full controlled multi-view experiment above.
