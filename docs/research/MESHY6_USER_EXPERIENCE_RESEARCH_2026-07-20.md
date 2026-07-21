# Meshy 6 User-Experience Research for Just Dodge

**Date:** 2026-07-20
**Scope:** Meshy 6 image-to-3D, Multi-View / Multi-Image to 3D, text/image reference generation, remesh, AI texturing, and rigging. Focus is hard-surface props, armor, weapons, humanoids, and downstream game use.
**Evidence rule:** firsthand community reports and transcript-backed tests are separated from official/marketing claims. No source was treated as proof of production readiness merely because it used that phrase.

## Executive findings

1. **Meshy 6 is materially better as a fast base-mesh generator than as a final AAA asset generator.** The strongest recurring success zone is discrete props: weapons, crates, barrels, furniture, rocks, simple environment pieces. Independent/firsthand users repeatedly report that props are usable after light cleanup, while hero humanoids, faces, fingers, loose clothing, and complex mechanical assemblies remain high-risk.
2. **Image-first beats unconstrained text for a specific design.** The most useful route is usually: design/clean the 2D reference first -> Image to 3D -> inspect geometry -> Remesh/UV -> texture -> DCC cleanup. A text prompt is best when exploring a new form or when a reference does not exist. The official docs state the same choice, and a 2026 firsthand Reddit report says image-to-3D “vastly improved” results over text prompts.
3. **Multi-View is not automatically better.** It improves hidden-side fidelity when the views are genuinely consistent, but a 2025 user report on hard-surface cottages says Multi-View produced worse geometry than a single image. In late 2025, the feature was still changing; early users report that the UI/availability and quality were not stable. Treat Multi-View as a controlled reconstruction route, not as a universal quality switch.
4. **For AAA, use Standard/high-detail generation when shape fidelity matters, then Remesh before downstream work.** Current official docs explicitly recommend remeshing before texturing/rigging and warn that remeshing after texturing breaks UV alignment. Use direct Low Poly/Topology Mesh only when the target is already a stylized low-poly asset and the generated topology is acceptable; do not assume it is suitable for hero deformation.
5. **AI texturing is high leverage on an accepted mesh, but it does not repair geometry.** A firsthand 2026 user reports reusing one sword mesh for several material variants. Another reports that Meshy textures are much better when painted over in Substance Painter: 20–30 minutes of human work versus 2–4 hours from scratch. Check UVs first; current official docs recommend UV Unwrap before retexturing if seams/distortion appear.
6. **Auto-rigging is a background-NPC accelerator, not a hero-character solution.** Official API docs limit reliable rigging to textured, standard humanoids with clear limbs/body structure and <=300,000 faces. Community reports say closed mouths, fused dangling parts, fingers, and facial controls still need manual modeling/weight work. A 2026 user reports a 20–30 minute generate -> rig -> animate -> Unreal flow for background NPCs, explicitly not hero characters.
7. **The most reliable Just Dodge armor workflow is modular, not “full armored humanoid in one shot.”** Generate or author a stable body/base first; generate torso armor, shoulder plates, gauntlets, greaves, helmet, and weapons as separately controlled components; mirror/symmetrize in Blender where required; assemble and validate fit in the DCC. This directly addresses the observed oversized/awkward armor and the community reports of fused or ambiguous clothing/accessories.
8. **Documentation is internally inconsistent and changes quickly.** Current official Help Center guidance says Multi-View is Meshy 6-only, up to three additional images (four total), while some current docs/repository pages still say 2–8 or 4–8 images. The Help Center says negative prompts are not currently available, while the newer docs expose negative-prompt examples. Pin the exact web/API behavior used in each run and do not encode stale limits into the pipeline.

## Evidence quality and source inventory

### Source classes

- **Firsthand community:** Reddit users describing their own runs, generated assets, engine imports, printing, or cleanup. Useful but unreplicated and sometimes low-context.
- **Transcript-backed creator test:** YouTube video with accessible auto-captions or a concrete test description. Stronger than a thumbnail/description, still not a controlled benchmark; affiliate links and sponsorship language are noted.
- **Independent test/review:** A publication or reviewer describing tests outside Meshy’s own marketing channel. Check whether it exposes the actual input/output and cleanup measurements.
- **Official documentation / Help Center:** authoritative for current UI/API constraints and intended workflow; not independent evidence of output quality.
- **Official marketing / customer story:** useful for supported workflows and examples, but claims such as “production-ready” are not acceptance evidence.
- **GitHub issue / maintainer workflow:** useful for integration bugs and intended pipeline shape; not a model-quality benchmark.

## Verified source records

### Firsthand Reddit reports

| Date | Source class | Exact observation | Practical implication |
|---|---|---|---|
| 2025-09-16 | Firsthand Reddit, `r/aigamedev` | [Anyone here tried Meshy 6 Preview yet?](https://www.reddit.com/r/aigamedev/comments/1nidvco/anyone_here_tried_meshy_6_preview_yet/) shows excitement about much higher detail. Replies immediately question topology; one says Meshy’s remesh tools are useful but “you don’t care about topology” only for printing. Other replies say AI topology is full of triangles and needs retopology for games; one notes image imperfections become geometry imperfections (example: car wheel becomes a many-sided, non-manufacturing shape). | Meshy 6 Preview detail is not a substitute for edge flow. For a weapon/prop, inspect manufacturing logic and silhouette; for a character, plan retopo/repair before animation.
| 2025-10-29 | Firsthand Reddit, `r/meshyai` | [Meshy AI Multiview Function Not Working](https://www.reddit.com/r/meshyai/comments/1oj8kzd/meshy_ai_multiview_function_not_working/) says Multi-View produced worse results than one image for hard-surface cottages, despite the author having images from different angles. Replies mention the feature was still evolving; one user reports a backpack disappearing/being changed even with front/back/left/right inputs. | Do not blindly upgrade a successful single-view prop to Multi-View. Validate the generated Multi-View turntable before paying for the final mesh. Use Multi-View only when the images are consistent and hidden-side fidelity matters.
| 2025-11-23 | Firsthand Reddit, `r/meshyai` | [Functionality for two images – Does that exist?](https://www.reddit.com/r/meshyai/comments/1p4zg26/functionality_for_two_images_does_that_exist/) asks for a character from two images because one view cannot provide enough depth; the author tried Batch Images, which created two separate models rather than fusing views. | Batch Images and Multi-View are not interchangeable. The intended operation must be explicit: multiple views of one subject -> Multi-View/Multi-Image endpoint; unrelated images -> Batch.
| 2025-12-23 | Firsthand Reddit, `r/meshyai` | [Can I add a text prompt to an image-to-3D model?](https://www.reddit.com/r/meshyai/comments/1ptin8u/can_i_add_a_text_prompt_to_an_imageto3d_model/) reports a front-view cat reconstructed well except the tail was omitted. Adding a prompt caused Meshy to generate a new cat rather than preserve the uploaded image. | Image-to-3D and text-to-3D are not a reliable “image plus corrective text” hybrid. Fix the reference image itself (draw/AI-edit the missing tail, then re-upload) or use a DCC edit; do not expect a late prompt to surgically repair geometry.
| 2026-01-13 | Firsthand Reddit, `r/meshyai` | [Smoothing Rough Texture](https://www.reddit.com/r/meshyai/comments/1qbj72f/smoothing_rough_texture/) reports that small 2–3 cm miniature exports crush detail and produce many mesh errors. Exporting at a larger scale and scaling down in a 3D application preserves detail and leaves fewer auto-fixable errors. | Keep a working master at a sensible/larger scale; apply final physical scale in Blender/slicer. Do not generate/export tiny final dimensions when fine details matter.
| 2026-02-05 | Firsthand Reddit, `r/meshyai` | [My One Month Meshy Review: Cool, but often frustrating](https://www.reddit.com/r/meshyai/comments/1qwuali/my_one_month_meshy_review_cool_but_often/) reports text prompts producing floating hands, fused legs, double headset microphones, inconsistent sleeves/cuffs, and repeated errors. Switching to Image to 3D “vastly improved” results. The author used AI Helper to create multiple-angle images and got “pretty nice models,” but downloaded meshes were non-manifold/low-resolution at default size. They found scaling at download to a much larger size helped; generation retries tended to reproduce the same error and did not accept a corrective prompt. | For humanoids, spend iteration budget on a clean T/A-pose reference or turnaround, not on repeated unconstrained text retries. Treat retries as stochastic re-rolls, not fixes. Inspect manifoldness and scale immediately after download.
| 2026-03-19 | Firsthand Reddit, `r/aigamedev` | [Indie game using Meshy AI to improve characters](https://www.reddit.com/r/aigamedev/comments/1mq5l5h/indie_game_using_meshy_ai_to_improve_characters/) reports Meshy as a shortcut for characters/props, but says small props work better than characters and that generated assets still require manual cleanup, retopology, and engine integration. | Use Meshy to reduce base-mesh time, not to remove technical-art ownership. Build acceptance around cleanup minutes, not preview appearance.
| 2026-04-09 | Firsthand Reddit, `r/meshyai` | [Is Meshy better at organic or hard surface models?](https://www.reddit.com/r/meshyai/comments/1sgw0ay/is-meshy-better-at-organic-or-hard-surface-models/) reports characters/creatures with solid overall shapes but imperfect anatomy; vehicles/mechanical assets with clipping and lumpy wheels; simple architecture works while complex windows get muddy; weapons and props are “the most reliable” category. A reply recommends primitive blockout guides for wheel/volume placement and generating subassemblies separately; repeating patterns remain difficult. | Weapons and discrete props are the best Meshy candidates. For vehicles/armor with repeated panels, use blockout/reference guides and generate subassemblies; avoid one-shot full assemblies.
| 2026-04-12 | Firsthand Reddit, `r/meshyai` | [Using AI generated 3D assets in my game, 3 months in, honest take](https://www.reddit.com/r/meshyai/comments/1sjig1n/using_ai_generated_3d_assets_in_my_game_3_months/) reports props/environment pieces (barrels, crates, weapons, potions, furniture, rocks, trees) at roughly 80% usable for a top-down Godot game. Creatures/enemies need Blender cleanup; retopo is about 30 minutes/model. After roughly 50 failed player-character attempts, the developer commissioned the hero character and used AI for the rest. Follow-up: generating 70–80% and polishing manually was faster than chasing perfection. | Strong support for “AI for broad asset coverage, commissioned/manual hero character.” For Just Dodge, reserve Meshy for weapons, armor components, enemy variants, and set dressing; protect the duelists/hero body from unconstrained generation.
| 2026-04-15 | Firsthand Reddit, `r/meshyai` | [The AI texturing feature is slept on](https://www.reddit.com/r/meshyai/comments/1sm7drl/the_ai_texturing_feature_is_slept_on_completely/) retextured the same medieval sword into cursed, ice-enchanted, and rusty variants using short material prompts. The author says each took roughly 30 seconds and that the generated PBR maps worked in Unreal/Unity; a reply notes the need to keep the model under 100 MB. | Maintain a clean base-mesh library and branch materials late. Retexturing is usually cheaper and more consistent than regenerating geometry for every faction/variant. Verify actual map packing/channel conventions in the target engine.
| 2026-04-21 | Firsthand Reddit, `r/meshyai` | [My Experience Using Meshy for Game Models](https://www.reddit.com/r/meshyai/comments/1ss07jr/my_experience_using_meshy_for_game_models/) reports GLB export into Godot as easy, Remesh reducing 700k-poly characters to about 1–1.5k triangles for a distant tower-defense camera, and built-in animation being adequate at distance but not robust enough for a third-person shooter. Separate tower and cannon meshes were used when animation/control of the gun tower was needed. | Use Remesh/low-poly aggressively for distant NPCs and props, but do not infer hero-combat readiness from a tower-defense success. Split mechanically controlled parts (weapon, cannon, shield) into separate meshes.
| 2026-04-30 | Firsthand Reddit plus official reply | [Rigability](https://www.reddit.com/r/meshyai/comments/1szqrkj/rigability/) asks whether closed mouths, teeth/tongue, eyelids, and dangly ears can be face/secondary-rigged. Meshy’s reply says outputs are usually closed meshes/surface detail; dangling parts may be separate or fused, and fused parts need manual separation or cloth/soft-body work. The reply recommends Meshy as a base mesh followed by topology/refinement in Blender/Maya. | Do not use a Meshy humanoid as an assumed facial-rig source. For Just Dodge, author facial/hand/cloth topology in the canonical body; use Meshy for visual concepts or rigid armor components.
| 2026-05-10 | Firsthand Reddit | [Symmetry trick that fixed my character models](https://www.reddit.com/r/meshyai/comments/1t99kwv/symmetry_trick_that_fixed_my_character_models/) reports adding “symmetrical, bilateral symmetry” improved symmetric results from roughly 2/10 to 6/10; “matching armor on both sides” and “identical shoulder pads” helped. The author’s more reliable fallback is deleting half in Blender and mirroring it. The same trick helped vehicles and weapons. | Add explicit symmetry language for humanoid armor, weapons, and mechanical props, but use Blender mirror as the authority. Never accept two subtly different shoulder plates/gauntlets in a competitive combat asset.
| 2026-05-21 | Firsthand Reddit | [Full character pipeline: generate, rig, animate, export to Unreal in under an hour](https://www.reddit.com/r/meshyai/comments/1tjqfcx/full_character_pipeline_generate_rig_animate_export/) reports a repeatable background-NPC recipe: “humanoid proportions, clear joint definition, no loose clothing elements”; generate 2–3, choose clear neck/shoulders/separated legs, auto-rig, apply walk/run/idle, export FBX, and retarget to Unreal Mannequin. Claimed total is 20–30 minutes for a background NPC, 45–60 when picky; author explicitly says this is not for hero characters. | Exact actionable rig prompt: clear joints, no loose clothing, neutral silhouette. Use this for background NPCs only and still test deformation in the target engine.
| 2026-06-24 | Firsthand Reddit | [Painting over AI textures in Substance Painter](https://www.reddit.com/r/meshyai/comments/1uejd74/painting_over_ai_textures_in_substance_painter/) uses Meshy textures as a base, then adds curvature-driven edge wear, AO dirt/grime, and hand-painted scratches/wood/fabric detail. Reported time is 20–30 minutes/model versus 2–4 hours from scratch; raw Meshy texture is acceptable for background props, painted-over is suitable for hero assets. | Adopt a two-tier material route: raw Meshy PBR for low-screen-time props; Substance Painter pass for hero/close combat assets. Budget the human pass instead of expecting AI texture output to be final.
| 2026-06-28 | Firsthand Reddit | [Models uploaded to Meshy explode in size](https://www.reddit.com/r/meshyai/comments/1uhim8g/models_uploaded_to_meshy_explode_in_size/) reports an STL exported from Meshy growing from hundreds of thousands to several million vertices when uploaded again for texturing, producing grainy/awful results. Support did not answer; resizing did not solve the reported regression. | Avoid unnecessary STL round-trips for texturing. Keep GLB/OBJ with known UVs as the texturing master; if an uploaded external mesh changes size or density, fail the task and texture locally/through a controlled re-export.

### Transcript-backed YouTube tests

| Date | Source class | Exact observation | Caveat |
|---|---|---|---|
| 2025-07-31 | Independent creator test, unsponsored but affiliate link disclosed | [Text Prompt to 3D Models! Honest Meshy AI Review](https://www.youtube.com/watch?v=btljwy0AZzE), Jenn Jager. The creator says text prompts repeatedly outperformed image uploads in her side-by-side tests for simple objects, but a clean, evenly lit multi-angle Rubik’s-cube capture still produced a melted/non-Rubik result. A handbag reconstruction was lumpy, with a chain that looked like it came “off the bottom of the ocean.” The creator recommends a real scanner/photogrammetry route for physical-object capture because four images were not enough for her test. A beagle model had good colors but rough spots; rigging required manual marker placement. The creator also notes that quad topology is preferable if editing in Blender; triangle is fine for direct use. | This predates Meshy 6 full release and therefore is historical baseline, not a direct Meshy 6 benchmark. It is still valuable evidence that clean lighting alone does not guarantee multi-view correctness and that topology choice must follow destination.
| 2026-05-25 | Creator test / promotional tone | [Meshy 6 Is Insane for AI Game Assets](https://www.youtube.com/watch?v=xSNSbWu_xOE), Web3World. The creator says they used their own Atom Assault project to test soldiers, zombies, tanks, buildings, props, rigging, animations, high-poly vs low-poly output, and printing. Transcript-backed claims: one zombie image produced a full model; high-poly gave more detail; Low Poly mode was more game-friendly; characters could be rigged and animated; the workflow was used for multiple enemy classes. | Useful as a real project demonstration and route inventory, but the video is strongly enthusiastic and does not report topology counts, failure rate, cleanup time, or engine deformation QA. Treat “much easier to use” as creator opinion, not acceptance evidence.
| 2025-02-19 | Affiliate creator / marketing-weighted | [Revolutionize Game Development with Meshy AI](https://www.youtube.com/watch?v=LZ-_L362z9E), SoloDev Tom. Description claims 62 game-ready assets in one hour and automated rigging/animation. | Not used as evidence for quality because it is affiliate-linked, claims “game-ready,” and exposes no reproducible failure/cleanup measurements. It is a useful example of marketing language to reject in our own gates.

### Official Meshy sources: supported behavior and intended workflows (not independent quality proof)

| Date | Source | Verified guidance / contradictions |
|---|---|---|
| 2026-01-18 | [Meshy-6 launch](https://www.meshy.ai/blog/meshy-6-launch) | Meshy’s official release claims refined organic geometry, sharper hard-surface detail, Low Poly Mode, multi-color printing, and API upgrades. Treat these as product claims; validate the exact asset class in our own QA.
| 2026-06-10 | [Multi-View Help Center](https://help.meshy.ai/en/articles/12634481-how-to-use-multi-view) | Multi-View is Meshy 6-only, requires an initial image, and allows up to three additional images (four total). Image order does not matter. Avoid multiple objects/angles collaged into one image. Recommended capture: front/back/left/right or front/side/back/3/4, same distance/lighting, plain background, full subject, >=1040x1040 px. It says 2–4 angles are usually enough and recommends Multi-View when hidden sides matter.
| 2026-07-13 | [Multi-View tutorial](https://www.meshy.ai/tutorials/multi-view-image-to-3d) | The current tutorial says Standard + Multi-View first, then Remesh; Multi-View is not available in Topology Mesh mode. It says generated missing views are still inferred, so more real views reduce invention. It explicitly advises fixing bad generated views before generating the model.
| Current docs retrieved 2026-07-20 | [Text vs Image vs Multi-View vs 3D Agent](https://docs.meshy.ai/en/webapp/guides/choosing/generation-method) | Intended decision matrix: Text for concept exploration; single Image for clear visual reference; Multi-View for high-fidelity multi-angle reconstruction; 3D Agent for guided ideation/style-consistent batch concepts. The matrix says Multi-View 2–8 images, conflicting with the Help Center/tutorial’s current four-total webapp limit.
| Current docs retrieved 2026-07-20 | [Image to 3D docs](https://docs.meshy.ai/en/webapp/image-to-3d) | Standard is for maximum detail; Smart Topology is for optimized real-time meshes. Current docs describe Custom Pose, with T/A-pose recommended for rigging. They recommend single subjects, simple backgrounds, and reviewing from all angles. The page also lists “multiple (2–8)” despite the separate four-total Help Center guidance.
| Current docs retrieved 2026-07-20 | [3D Prompting Guide](https://docs.meshy.ai/en/webapp/guides/prompting) | Formula: `[Subject] + [Material/Texture] + [Art Style] + [Technical Constraints]`. Put key information first; longer prompts are not automatically better. Examples include a plasma rifle with a glowing blue core, carbon fiber/chrome materials, cyberpunk style, game-ready low-poly; and a knight helmet with scratched iron. For games, use “low-poly/game-ready,” “clean edges,” “minimal geometry”; for printing, “solid,” “watertight,” “no floating parts,” “no thin overhangs.”
| 2026-06-10 | [Advanced prompt practices](https://help.meshy.ai/en/articles/11972484-best-practices-for-creating-a-text-prompt) | Structure is Subject + Modifiers + Style; material/detail/pose keywords include polished metal, aged wood, circuitry, glowing runes, T/A pose, and clear style families. Important contradiction: this Help Center article says “At the moment, Meshy does not allow for negative prompts,” while newer docs show negative-prompt examples. Do not depend on a negative-prompt field without checking the actual API/UI version.
| Current docs retrieved 2026-07-20 | [AI Image Generation](https://docs.meshy.ai/en/webapp/guides/image/ai-image-generation) and [text-to-image workflow](https://www.meshy.ai/blog/transform-text-into-ai-images-for-3d-creation) | Generate a 2D reference first when visual style needs control. Use front or 3/4 view, clean/white background, complete subject, single object. The official workflow says Auto Refine can improve structure but may make the image more cartoonish/simplified; image strength controls reference adherence. External image editing is still appropriate.
| Current docs retrieved 2026-07-20 | [AI Texturing](https://docs.meshy.ai/en/webapp/guides/3d-model/ai-texturing) | Supports external OBJ/FBX/GLB input, text/image style prompts, Remove Lighting, PBR maps, and HD texture. If seams/distortion appear, run Unwrap UV first. The page’s example uses an untextured sword with “ancient elvish blade, silver with blue rune engravings, fantasy style,” PBR/HD/Remove Lighting on. It says Remesh should precede texturing.
| Current docs retrieved 2026-07-20 | [Remesh API](https://docs.meshy.ai/en/api/remesh) and [low-poly guide](https://www.meshy.ai/tutorials/make-low-poly-3d-models) | Remesh reduces/redistributes geometry and supports target budgets; current guide recommends remeshing the final mesh before UV, texture, or rigging. Its reference bands are under 5K for mobile/casual, 5–20K mobile/web, 20–50K PC/console games, 50–100K high-quality renders, >100K cinematic. These are planning bands, not universal AAA budgets.
| Current docs retrieved 2026-07-20 | [Rigging API](https://docs.meshy.ai/en/api/rigging) | Reliable only for textured standard humanoids with clear limbs/body. Not suitable for untextured, non-humanoid, or ambiguous anatomy; input-task models over 300,000 faces are unsupported and should be remeshed first. URL inputs must face +Z. This matches community failure reports.
| Current docs retrieved 2026-07-20 | [Multi-Image API](https://docs.meshy.ai/en/api/multi-image-to-3d) | API accepts 1–4 images or a completed 1–4 image-generation task. This is the current API value to use for automation; do not copy older repository text that says 4–8.
| 2025-07-24 | Official customer story / marketing | [Aiko: Stylized Antiquity prompt engineering](https://www.meshy.ai/blog/3D-prompt-engineering) gives a repeatable style-code approach: define color/material/silhouette/mood pillars; repeat descriptors; use “type of object + carved ivory/aged stone/brushed gold + style + classical proportions + mechanical elements + matte + ornamental + symmetrical.” Aiko usually starts Image to 3D, rejects meshes that vary too far from the source, then makes multiple texture versions. Useful for style consistency, not proof of geometry quality.

### GitHub / integration evidence

| Date | Source class | Observation |
|---|---|---|
| 2026-06-26 | Official-repo GitHub issue / firsthand integration bug | [meshy-mcp-server issue #3](https://github.com/meshy-dev/meshy-mcp-server/issues/3), titled “Rigged GLB export: 0.01 object scale with 100x baked data, bundled Icosphere helper, and foot skin-weight stretching,” is open. This is direct evidence that automated rig/export integration still needs scale, helper-object, and deformation QA even when generation succeeds.
| 2026-04-23 | Maintainer workflow / marketing-weighted | [Meshy-guide README](https://github.com/meshy-dev/Meshy-guide) and [game-asset-pipeline README](https://github.com/meshy-dev/game-asset-pipeline) document intended API/game workflows, prompt examples, preview->refine, GLB/FBX imports, Remesh, and Humanoid/Unreal/Unity integration. They use “game-ready” and “under two minutes” language; treat the repos as implementation references, not independent validation. Their older 4–8-image wording conflicts with the current Multi-Image API/Help Center limit.

### X and Discord coverage

- **X:** searched for Meshy 6 image-to-3D, Multi-View, remesh, texturing, armor/weapons, and rigging posts. The accessible result with a concrete workflow was an adjacent non-Meshy post by [AssetHub](https://x.com/assethub_io) (2026-01-29) describing GPT-Image2 -> multi-view -> high-poly -> remesh -> UV -> retexture using other tools. It is useful as a general pipeline pattern but was **excluded from Meshy quality evidence**.
- **Discord/forum mirrors:** Meshy’s Help Center links the official Discord, but no publicly accessible, independently verifiable 2025–2026 Discord mirror with concrete Meshy 6 asset tests was found. This report does not infer anything from that absence. Reddit and transcript-backed YouTube provide the accessible firsthand corpus.

## Practical prompt and image setups

### A. Hard-surface props and weapons

**Preferred route when a design exists:**

1. Create or clean one reference image first. Use a single centered object, isolated on white/neutral/transparent background, full silhouette visible, no crop, sharp focus, even diffuse lighting, and no text/logos unless they are intentionally part of the geometry.
2. Use Image to 3D Standard for first geometry when surface design/identity matters. For a symmetric sword, shield, helmet, buckle, or isolated prop, single-view is a good first pass; the backside can be rebuilt or mirrored in Blender.
3. Use Multi-View only when the backside/underside/handles/attachment points are materially important. Supply complementary, consistent views; do not mix sketches, rendered views, photos, close-ups, or different scales.
4. Inspect all generated views before committing the mesh. If the generated Multi-View set already invents/loses a part, fix the image set rather than hoping generation will repair it.
5. Remesh before final UV/texturing. For a PC/console prop, start a budget experiment around 20–50K faces and raise/lower based on silhouette, camera distance, and interaction requirements. Keep a high-detail source for baking/hero closeups.
6. Run UV Unwrap if the UV layout is suspect; then AI Texture with explicit material/era/wear language and Remove Lighting/PBR as appropriate. Finish hero assets in Substance Painter.

**Prompt pattern:**

> `single [asset], [primary construction/material], [recognizable parts], [surface wear/detail], [style], [technical use]`

Example:

> `single fantasy longsword, symmetrical double-edged steel blade, readable fuller and guard, wrapped dark leather grip, brushed steel with restrained engraved runes, realistic PBR game prop, clean hard-surface edges, isolated centered object`

For a sci-fi weapon:

> `single sci-fi plasma rifle, symmetrical industrial chassis, distinct stock/grip/barrel/energy core modules, carbon-fiber body with brushed alloy and chrome accents, restrained blue emissive core, realistic PBR, clean panel seams, game prop, no extra objects`

Use symmetry language when needed: `symmetrical`, `bilateral symmetry`, `matching left/right armor`, `identical shoulder pads`. Do not assume the model will respect it perfectly; mirror the accepted half in Blender for combat-critical symmetry.

### B. Armor

Do **not** ask for “a fully armored fighter” when the output must fit a canonical body and preserve readable joints. Prefer:

- canonical body/reference -> separate torso armor -> separate shoulders -> separate gauntlets -> separate greaves/boots -> helmet -> weapon;
- each component uses the same style-code block (palette, metal, edge wear, panel language);
- use a simple primitive blockout or a clean multi-view component reference to constrain volume;
- specify `rigid plates, clear joint gaps, no cloth/cape, no floating parts, no fused fingers, symmetrical left/right layout` as positive constraints where the UI accepts them;
- attach/kitbash and mirror in Blender, then validate range of motion and collision in the actual combat rig.

Armor is exactly where a visually impressive single-image humanoid can produce oversized shoulder pads, fused sleeves, armor/body intersections, and unriggable loose elements. Meshy’s own rigging constraints and user reports support keeping the body and rigid armor under separate control.

### C. Humanoids

**For background NPCs:**

- Use an AI-generated or authored full-body T/A-pose turnaround rather than a dynamic single illustration.
- Keep the silhouette clean: `humanoid proportions, clear neck/shoulders/hips/knees, separated legs, clear joint definition, no loose clothing elements`.
- Generate 2–3 variants; select by silhouette and limb separation before texture.
- Remesh to the NPC budget, texture, then rig. Export FBX/GLB and test the target engine’s humanoid mapping.

**For Just Dodge hero/duelist bodies:**

- Keep the canonical body, hands, fingers, face, mouth/eyes, and deformation topology outside Meshy’s unconstrained body generation.
- Use Meshy for armor/weapon/accessory concepts and rigid component base meshes.
- If using Meshy for a full body, treat it as a visual blockout or sculpt reference; expect manual fingers, face, mouth, eyelid, cloth, topology, weights, and animation repair.

### D. Text -> image -> 3D

Use this when the design is under-constrained but must become a specific, controllable visual. Iterate cheaply in 2D first:

> `full-body humanoid duelist, neutral T-pose, readable proportions, segmented dark steel armor, narrow shoulder profile, exposed joint gaps, simple boots and gloves, clean front 3/4 view, plain white background, realistic game concept sheet`

Then generate matching side/back views with the same style/pose/scale or use a tool that can produce a consistent turnaround. Check every view for disappearing accessories, changed armor, extra limbs, and inconsistent weapon placement before sending to Multi-Image.

The 2026 Reddit reviewer’s AI Helper workflow supports this direction: multi-angle image preparation improved their result much more than unconstrained text. The official Meshy image-generation docs also recommend front/3/4, clean background, and complete subject. The author’s external ChatGPT workaround is a reasonable credit-saving option when Meshy’s own image generation is expensive, but keep the image-generation tool separate from the Meshy evidence gate.

## Route-selection rules for Just Dodge

| Need | Route | Why / gate |
|---|---|---|
| New weapon/prop concept, no reference | Text to 3D Meshy 6, 2–4 variants | Best creative freedom; use subject/material/style/technical prompt. Choose by silhouette before texture.
| Specific sword/weapon/prop concept exists | Single Image to 3D Standard | Faster and often more reliable than unconstrained text for a clean, symmetric object. Mirror/rebuild hidden side if needed.
| Back/side/underside/attachment geometry matters | Multi-Image to 3D Standard, 2–4 consistent views | Use only if the real views add information. Validate generated views. Current API/webapp supports 1–4; ignore stale 2–8/4–8 text.
| Stylized low-poly prop with a fixed tight budget | Direct Low Poly/Topology Mesh | Use when low-poly is the intended visual style and components do not need hero deformation. Still inspect topology.
| Detailed prop needs both a source and runtime mesh | Standard/Image/Multi-View -> review -> Remesh -> UV -> texture | Preserves shape first, then creates a controllable runtime budget. Keep high-detail source for baking.
| Armor that must fit a canonical humanoid | Separate component generation from canonical body | Reduces oversized/fused armor, preserves body rig, enables mirror/kitbash and per-part collision.
| Background humanoid NPC | Clean T/A-pose image or turnaround -> Standard/Smart Topology -> Remesh -> Texture -> Rig | Auto-rig is appropriate only when limbs/body are clear; test walk/run/idle in engine.
| Hero humanoid/duelist | Canonical body + manual/controlled rig; Meshy for rigid armor/accessories | Fingers, face, mouth, eyelids, loose clothing, and deformation remain recurring failure points.
| Same mesh, multiple factions/materials | Accepted mesh -> UV check -> AI Texture/retexture -> Substance polish | Avoid regenerating geometry for material variants; branch late.
| Meshy-generated texture looks promising but seams | UV Unwrap -> retexture; do not remesh afterward | Official docs and community workflow agree that UV quality is the failure point.
| Export to texturing pipeline | Keep GLB/OBJ/FBX master; avoid STL upload round-trip | A 2026 report observed vertex explosion and grainy texture after STL export/re-upload.

## Raw vs Remesh sequencing

### Recommended production order

1. **Reference preparation**: isolate subject, correct scale/camera/background/lighting, and make the intended pose/turnaround explicit.
2. **Preview generation**: text, single image, or Multi-View Standard; generate variants and reject wrong silhouettes before spending on texture.
3. **Geometry acceptance**: rotate 360 degrees; inspect underside, joins, thin parts, armor/body intersections, duplicated/floating parts, and mechanical logic.
4. **Remesh**: select topology and target budget for the destination. Preserve the original high-detail mesh as a source.
5. **UV validation/unwrap**: if seams/overlaps are present, unwrap before texturing.
6. **AI texture/retexture**: use material, era, wear, palette, and PBR/Remove Lighting controls. Treat AI maps as a fast base.
7. **DCC polish**: mirror, separate parts, rebuild critical edges, correct pivots/origins/scale, bake details, and paint hero wear.
8. **Rig/animate**: only after the mesh is at a sensible budget and the humanoid structure is clear. Test deformation and engine import, not only Meshy’s preview.
9. **Engine gate**: verify materials, normals, scale, skeleton, absence of Player-mode clip/pose-bank dependencies, equipment manifests, sockets/grip, collision/proxy lineage, LODs, and combat-camera readability.

### What not to do

- Do not texture an unaccepted geometry result because the texture makes the preview look better.
- Do not remesh after applying the final UV-dependent texture unless you are willing to redo UVs and textures.
- Do not use STL as the canonical texturing interchange when GLB/OBJ/FBX can preserve a controlled mesh/UV path.
- Do not treat “Smart Topology/Low Poly” as a universal replacement for hero retopology; verify part segmentation, deformation, normals, and silhouette.
- Do not repeatedly retry a failed humanoid while changing nothing. One user reports retries reproduce the same error; change the reference or route.

## Failure-mode catalogue and mitigations

- **Extra fingers/hands/arms, fused legs:** clean full-body T/A-pose turnaround, one subject, no overlapping accessories; use a canonical body for hero characters.
- **Missing tail/backpack/weapon/back armor:** add the missing feature visibly in the reference from multiple angles; do not rely on a corrective text prompt after Image to 3D.
- **Multi-View destroys a hard-surface asset:** check that views are same object, scale, lighting, and camera logic; inspect generated views; fall back to single-view plus manual mirror/blockout.
- **Lumpy wheels/repeating panels/windows:** use primitive blockout/reference geometry; generate chassis/subassemblies separately; kitbash repeated parts.
- **Oversized/awkward armor:** avoid full-body one-shot; generate rigid components around a known body and specify narrow/segmented joint-clear silhouettes.
- **Fused capes/hair/dangling accessories:** remove them from the rig-critical generation or author them as separate meshes; use cloth/secondary rig manually.
- **Poor topology/excess triangles:** keep high-detail source, Remesh before UV/texture/rig; for hero assets manually retopo and bake.
- **Texture seams/distortion:** UV Unwrap first, then retexture; inspect in the target renderer. Do not accept a pretty viewport as proof of correct UVs.
- **Texture looks painted on:** use AI Texture as a base; add curvature edge wear, AO dirt, scratches, and directionality in Substance Painter.
- **Wrong scale/tiny detail crushed:** export/download at a sensible working size and apply final scale in Blender/slicer; test real dimensions and engine unit conversion.
- **Vertex/size explosion on re-upload:** avoid STL re-import for texturing; retain GLB/OBJ/FBX, and fail/inspect any density jump.
- **Rigging succeeds but feet/scale/deformation fail:** run a smoke test with idle/walk/run, inspect foot weights and scale, remove helper objects, verify skeleton/orientation, and test the exact FBX/GLB engine import. Official GitHub issue #3 confirms this class of integration defect exists.

## Suggested Just Dodge acceptance gates

Every Meshy asset entering the repo should carry:

- input route: `text`, `image`, or `multi-image`;
- source image set and whether it was generated or photographed;
- Meshy model/version and date;
- raw face/vertex count and remesh target;
- UV status and texture source;
- whether parts are intentionally separate;
- rig status and engine smoke-test result;
- known manual fixes;
- final camera-distance use (`hero`, `midground`, `background`);
- license/plan provenance.

Minimum gates:

1. 360-degree silhouette and underside review.
2. No floating/fused combat-critical parts.
3. No non-manifold or density surprise after export.
4. UV/material round-trip in Blender and the target engine.
5. For characters: T/A-pose source, clear joints, retargeted idle/walk/run, and deformation check.
6. For armor: canonical-body fit, shoulder/hip/elbow/knee clearance, mirror/symmetry check, and collision readability.
7. For weapons: straightness, symmetry, grip/guard/blade relationships, pivot/origin, and in-game camera readability.
8. For hero assets: human Substance/DCC pass; raw Meshy output is never the final AAA acceptance state.

## Bottom line

Meshy 6 is worth keeping in the Just Dodge pipeline as a **reference-driven base-mesh and material-variant accelerator**. It is a strong candidate for weapons, props, rigid armor components, enemy variants, and background NPC coverage. It is not yet a reliable authority for canonical humanoid anatomy, fingers/face topology, complex articulated armor, or hero deformation. The safest route is **image-first, modular, geometry-gated, remesh-before-UV/texture/rig, and human-polished at the hero tier**.
