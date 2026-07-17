## Verified production plan — Just Dodge high-fidelity phase

**Decision:** keep all generative services **offline candidate producers**. Blender + versioned headless workers remain the **sole asset-authority and promotion boundary**; cooked Rust/wgpu assets are the shipping form. No model/service ships in the executable.

This aligns with the repo’s ordering: P0 is the deterministic debug-mannequin loop; high fidelity starts only afterward, and the fused C0 is explicitly not the path forward (`GAME_FIRST_INTENT_COMBAT_SPEC.md:9–14, 117–130`). The visual contract already requires purpose-built, separated Meshy components and makes pinned Blender/headless scripts authoritative (`ADVERSARIAL_VISUAL_CONTRACT.md:37–43`).

### 1) Division of labor

| Asset class | FAL | Meshy | Blender / Just Dodge worker | Shipping decision |
|---|---|---|---|---|
| **Armored duelist** | Generate signed-off concept sheets, orthographic/multi-view references, material callouts; video only for motion/readability reference. FAL 3D may make an alternate *single-object* candidate, never the accepted anatomical source. | Generate **one component per task** from coherent 1–4 view sheets: body carrier, helmet, cuirass, pauldron, gauntlet, greave, boot, sword, guard, grip, etc. Meshy’s Smart Topology may produce natively separated parts, but is not a semantic/anatomical guarantee. | Authoritative component assembly; exact scale/origin; retopo and UVs; canonical skeleton, skin weights, sockets, collision/damage/armor proxies; bake; stress-pose, penetration, GLB, and runtime-cook validation. | Purpose-built, named, separately addressable components only. Never repair/promote the fused C0 as this source. |
| **Weapons** | Concept variants, engraving/material references; optional video for impact/handling reference. | Strong use case for a single hard-surface component: blade, guard, grip, scabbard, breakable subpart as separate requests. | Enforce pivot/socket, blade/guard clearance, collision and fracture pieces; make LODs; bake normal/AO; validate weapon-to-hand and weapon-to-body clearance. | GLB interop → cooked runtime mesh/material tables. |
| **Arena** | Mood, architecture, decal, trim-sheet, and tileable-material concepts; video only as lighting/VFX reference. | Generate modular, **single-object** props (pillar, brazier, rubble, door, pedestal), not an entire arena scene. | Build deterministic modular kit, terrain/collision/navmesh proxies, texel-density/LOD/material budgets, fixed arena lighting validation. | Hand-assembled modular arena, not a generated scene or splat. |
| **VFX** | Image/video reference and source plates for sparks, dust, cloth, blood/magic visual language. | Generally not primary. Small static proxy props only. | Create deterministic sprite/flipbook/mesh-particle textures, shader inputs, and engine timing; VFX must never affect truth/collision. | Baked textures/meshes + deterministic runtime parameters. |
| **Textures** | Primary ideation source: material boards, decals, masks, trim-sheet concepts. | PBR retexture candidate when geometry/UVs are already accepted. Meshy 6 can provide base color + metallic/roughness/normal (+ emission) maps. | UV ownership, color-space correction, PBR node graphs, local physical-material correction and Cycles baking. Base/emissive = sRGB; normal/roughness/metal/AO = non-color/linear. | Standardized baseColor, normal, ORM, emissive texture set; runtime cooker verifies each binding. |

### 2) Current provider capabilities and boundaries

#### FAL: use as reference/variant generator, not the final DCC authority

Verified FAL model endpoints and contracts:

| Role | Verified FAL endpoint | Inputs / outputs relevant to pipeline | Plan use |
|---|---|---|---|
| High-resolution concept / texture reference | `fal-ai/flux-pro/v1.1-ultra` | Required `prompt`; optional `seed`, image conditioning, ratios, PNG/JPEG. Returns `images[]`, resulting `seed`, prompt and timing data. | Generate silhouette/multi-angle briefs, material callouts, decals/trim concepts. Archive selected image bytes and seed. |
| Motion, camera and FX reference | `fal-ai/kling-video/v2.1/master/text-to-video` | `prompt`, 5/10 s duration, aspect ratio, negative prompt, CFG. Returns a video file. | Reference-only for sword trails, cloth rhythm, sparks, environmental atmosphere. Do **not** turn video directly into gameplay animation or collision. |
| Image-to-3D alternate candidate | `tripo3d/tripo/v2.5/image-to-3d` | Required `image_url`; optional seed, face limit, PBR, texture tier, auto-size, quad. Returns `model_mesh` plus preview; quad forces FBX. | Fast single-object comparison candidate for props/weapon variants. Not a part-aware character source. |
| Image/text-guided 3D alternate candidate | `fal-ai/hyper3d/rodin/v2.5/fast` | Up to five `image_urls`, prompt, seed, GLB/FBX/OBJ/etc., PBR/shaded/none, T/A-pose. Returns model file, seed and texture files. Fast endpoint is documented as prototyping/testing and capped at 20K geometry. | Evaluate only as a reference or prop candidate. Its documented API has no semantic component-separation, clean-rig, or runtime-readiness guarantee. |

**FAL calling contract:** use the official queue, not an invented FAL MCP server: `fal_client.submit(model_id, arguments, webhook_url)` → status/webhook → `get()`. FAL documents queue `submit()` as the production-recommended path; `run()` has no queue/retry durability. Do not expose `FAL_KEY` to client/end-user code.

#### Meshy: component-candidate 3D source, not final character authority

Verified Meshy API:

- **Text-to-3D:** `POST /openapi/v2/text-to-3d`, two steps: `mode:"preview"` produces untextured geometry; `mode:"refine"` takes `preview_task_id` and textures it.
- **Image-to-3D:** `POST /openapi/v1/image-to-3d`; **Multi-Image-to-3D:** `POST /openapi/v1/multi-image-to-3d`, accepting 1–4 consistent views. Both offer `should_texture`, `enable_pbr`, 4K base color (`hd_texture`) with 2K PBR maps, `remove_lighting`, GLB/FBX outputs, T/A-pose, and raw vs remeshed geometry.
- **Topology:** the Image-to-3D docs identify `model_type:"smart-topology"` with `meshy-t2` as cleaner topology with natively separated parts and a 100–15,000 target face range. This is useful, **but it is not a substitute for the Just Dodge component contract**. The currently discovered Meshy MCP tool schema exposes `standard`/`lowpoly`, so invoke Smart Topology through a versioned REST adapter only after its tool schema is confirmed; do not silently pretend the existing MCP wrapper supports it.
- **Post-processing:** `POST /openapi/v1/remesh` supports quad-dominant/triangle topology, 100–300,000 target polygons and GLB/FBX/OBJ/USDZ/BLEND/STL/3MF output. `POST /openapi/v1/uv-unwrap` gives a fresh non-overlapping UV GLB, but has a **40k-face cap** and triangulates quad/n-gon input.
- **Texture:** `POST /openapi/v1/retexture`; with Meshy 6/latest, PBR means metallic/roughness/normal plus emission; `hd_texture` is 4K base color while PBR remains 2K.
- **Rig:** `POST /openapi/v1/rigging` returns rigged GLB/FBX and basic walk/run clips. It is only for clearly defined textured bipeds; model-url input must face **+Z**, and input-task meshes must be ≤300k faces. Treat it as **rig diagnostics/source skeleton only**, never as Just Dodge’s motion authority.
- **Formats:** default to GLB for interchange; request FBX only when the rig/cooker route requires it. GLB/FBX are both documented outputs.
- **Quality posture:** Meshy uses `latest` = Meshy 6, but no provider “production ready” claim substitutes for geometry, deformation, or runtime QA.

### 3) Exact character pipeline: one purpose-built part-separated armored duelist

**Deliverable definition before a generation call**

A `JD_Duelist_001` component manifest must enumerate, at minimum:

1. `body_anatomy_carrier` / undersuit;
2. helmet/head and neck guard;
3. torso plates, pauldrons, vambraces, gauntlets;
4. belt/fauld/tassets;
5. thighs, greaves, boots;
6. sword blade, guard, grip, pommel, scabbard;
7. breakable/fracture and collision/damage proxy objects;
8. canonical skeleton mapping, weapon socket, meter scale, forward axis, material slots, allowed overlap/clearance, LOD and texture budgets.

No body/armor/weapon mesh may be fused merely to obtain a prettier thumbnail.

| Order | Operation and tool chain | Automated acceptance / failure fallback | Human gate |
|---:|---|---|---|
| 0 | Freeze `asset_id`, component manifest, scale, canonical skeleton/weapon socket, material and LOD budget, target combat metadata, source-rights register. Hash the selected FAL/Meshy terms pages and model-page contracts. | Missing licensed input, term snapshot, or component definition = stop before spending credits. | **G0 — art + legal brief approval.** |
| 1 | FAL image queue: produce a **coherent front/right/back/three-quarter reference sheet** in neutral T-pose, isolated on plain background; separate sheets for each armor family and weapon. FAL video is optional reference only. | Identity/costume mismatch, visible fused layers, unclear hands/weapon = regenerate concept, not geometry. | **G1 — silhouette, component boundaries, materials, and no-IP-copy review.** |
| 2 | Archive approved reference bytes; generate a source manifest and hashes. Produce an **untextured** Meshy task per component using `mcp__meshy__meshy_multi_image_to_3d` (or audited REST for Smart Topology). For the body carrier use `pose_mode:"t-pose"`, `should_texture:false`, `should_remesh:false`, GLB, cardinal thumbnails. | Any task failure, inconsistent views, hidden limbs, fused armor, or unclear articulated boundaries: reject and alter the source sheet/prompt; do not patch a bad whole-body output. | None; automatic source intake only. |
| 3 | `mcp__meshy__meshy_get_task_status(wait:true)` then `mcp__meshy__meshy_download_model` for the accepted **GLB only**; archive original response/task JSON and source bytes immediately. | Missing GLB/output map, expired URL, or digest mismatch = re-download/reject; no URL is a durable source. | **G2 — raw component geometry review** using cardinal/clay/wireframe evidence. |
| 4 | Blender DCC import each raw candidate into a disposable scene. Establish meters, +Z-forward contract, named collections, origins, pivots, and actual object separation. Use typed DCC import/mesh/UV tools; save an owned `.blend`. | Wrong axes/scale, non-manifold mesh, degenerate geometry, missing UVs/materials, or a component touching the wrong layer = reject/regenerate or manually rebuild that **one** component. | **G3 — topology / anatomical-fit approval.** This is the point at which a component becomes worth retopologizing. |
| 5 | Blender performs authoritative retopo/manual corrective modeling; re-create clean deformation loops, seam/clearance margins, UVs, and LODs. Use Meshy Remesh/UV Unwrap only as a candidate utility, not as approved character deformation topology. | UV Unwrap >40k faces → reduce/remesh first; remesh is unsatisfactory → retain a Blender-owned manual retopo. | None; versioned script output only. |
| 6 | Assemble components in Blender without joining them. Build material slots, parent armor appropriately, add canonical skeleton, skin body/soft layers, rigid-parent plates where appropriate, create sockets and explicit collision/damage/fracture proxies. | Unbound vertices, >influence budget, bind-pose mismatch, incorrect sword socket, non-finite matrices = fail. Meshy auto-rig may be compared here but is not canonical. | **G4 — bind pose / stress-pose / component-clearance review.** |
| 7 | Run stress poses plus Mesh Doctor. Existing `mesh_doctor_detect.py` handles non-adjacent self-intersection within one mesh; run `mesh_doctor_pair_detect.py` for body↔armor, armor↔armor, weapon↔body pairs. | Crossing depth over contract threshold, collision proxy mismatch, missing pair object names = reject or make a new immutable corrective candidate. | **G5 — repair disposition.** Never accept “looks fine in one thumbnail.” |
| 8 | If repair is suitable, invoke the headless non-destructive repair worker against an immutable copy, then rerun every geometry/stress test. | A repair candidate cannot clear the gate, alters seams/weights, or creates a new defect → return to component rebuild/retopo. | Explicit approval required before replacing a candidate. |
| 9 | Only after geometry admission: Meshy `retexture` from approved UV geometry **or** Blender-local authored/baked PBR. Require `enable_original_uv:true` only after Blender has verified the UVs; use `enable_pbr:true`, `remove_lighting:true`, and archive all maps. | Missing PBR map, baked lighting, incorrect colorspace/ORM packing, weak texel density = texture redo; do not alter admitted geometry to fix texture. | **G6 — material/readability approval.** |
| 10 | Blender Cycles selected-to-active bakes owned normal/AO/material corrections, then exports deterministic GLB. Use pinned exporter options and an extension allowlist. | Khronos GLB structural/material validation or re-import fails = return to DCC source. | None. |
| 11 | Cook through existing Just Dodge path. The current `extract_fbx_skinned.py` preserves positions/normals/UVs, hierarchy, inverse binds, and top-8 normalized weights to SKM1/ANM1; `verify_skinned_bin.py` checks index bounds, hierarchy, weight sums, humanoid height, and animation integrity. | Cooker discards UVs/PBR/material data, loads legacy mannequin, or asset format fails = cooker contract failure, not an art promotion. | **G7 — runtime integration approval.** |
| 12 | Run the visual contract in raw / Blender / cooked / live stages: 16 fixed views, clay/wire/normals/UV/weights/socket/proxy AOVs, first-person frames, and metrics. | Any visual contract requirement missing or threshold breach: promotion blocked. | **G8 — final blinded first-person and evidence-packet sign-off.** |
| 13 | Promote only content-addressed cooked bytes plus manifest/receipts. Runtime never calls FAL/Meshy. | Any source, script, model, terms, config, or byte hash change invalidates approval. | Release owner signs promotion. |

### 4) Agentic MCP/tool loop

**FAL adapter (not currently an assumed MCP tool):**

```text
fal.submit(model_id, exact_arguments, webhook_url)
  → persist request receipt before queueing
  → webhook/status handler
  → download exact output bytes
  → hash + provider response receipt
  → human concept gate
```

Use FAL’s official `submit()` queue pattern; record its returned request ID, model ID, exact arguments, returned seed if supplied, and output hashes.

**Meshy component loop:**

```text
mcp__meshy__meshy_check_balance
mcp__meshy__meshy_multi_image_to_3d(
  file_paths|image_urls=[1..4 coherent views],
  ai_model="latest",
  pose_mode="t-pose" for body,
  should_texture=false,
  should_remesh=false,
  target_formats=["glb"],
  response_format="json"
)
mcp__meshy__meshy_get_task_status(task_id, wait=true)
mcp__meshy__meshy_download_model(task_id, format="glb", destination=immutable/raw/)
→ sha256 + receipt + Blender intake
```

For an accepted geometry source that requires provider utilities:

```text
mcp__meshy__meshy_remesh  # only with explicit mesh/LOD target
mcp__meshy__meshy_uv_unwrap  # only at <=40k faces
mcp__meshy__meshy_retexture  # after Blender UV acceptance
mcp__meshy__meshy_rig  # optional diagnostic source rig only
```

**Blender/DCC and local deterministic worker loop:**

```text
mcp__blender_dcc__load_skill("blender-import-to-scene" / "blender-validation" / ...)
import → named collections + units/axis/pivots
mcp__blender_dcc__validate_mesh(object_name, rules)
mcp__blender_dcc__validate_materials(...)
mcp__blender_dcc__validate_animation(...)
mcp__blender_dcc__validate_export_readiness(object_names, target_format="glb")
headless Blender:
  mesh_doctor_detect.py
  mesh_doctor_pair_detect.py
  mesh_doctor_repair.py  # candidate only
  rerun detection / stress poses / export / re-import
Khronos GLB validation → cooker → SKM1/ANM1 verifier → runtime visual gate
```

The local DCC bridge is live and reports its process/DCC/catalog/dispatcher healthy. The current executable is **Blender 5.1.2**, which matches the repo’s pinned DCC authority. Blender 5.2 LTS is current upstream, but **do not upgrade this pipeline ad hoc**: the visual contract pins the existing Blender build, and a version change must be an ADR/baseline migration.

**Mesh Doctor caveat:** it is useful because a separated duelist unlocks real pair detection—the pair worker explicitly describes fused C0 as unsuitable—but its repair output is deliberately unpromoted. Also, the current repair worker’s `protected_seam_verts` remains zero and its `smooth_iters` argument is not applied in the shown code. Therefore, treat it as a candidate-shape-key experiment, never a silent automatic repair system. Full animated validation must invoke the workers over actual sampled pose frames, not infer success from a static bind pose.

### 5) Provenance / determinism receipt

For every provider operation, write an immutable, canonical-JSON receipt before promotion:

```json
{
  "schema": "just-dodge.asset-provenance.v1",
  "asset_id": "jd_duelist_001.cuirass",
  "stage": "raw|dcc|cooked|runtime",
  "parent_sha256": ["..."],
  "provider": {
    "name": "fal|meshy|blender",
    "endpoint_or_model": "...",
    "request_id_or_task_id": "...",
    "request_canonical_sha256": "...",
    "response_redacted_sha256": "...",
    "model_version": "...",
    "seed": 0,
    "credits_or_cost": 0
  },
  "rights": {
    "input_origin": "owned|licensed|generated",
    "input_license_ref": "...",
    "provider_terms_url": "...",
    "provider_terms_retrieved_at": "RFC3339",
    "provider_terms_sha256": "...",
    "human_rights_gate_receipt_sha256": "..."
  },
  "toolchain": {
    "git_sha": "...",
    "dirty_worktree": false,
    "blender_build": "...",
    "script_hashes": {},
    "export_settings_sha256": "..."
  },
  "artifacts": [{"path": "...", "format": "glb", "sha256": "..."}],
  "validation": {"status": "candidate|rejected|approved", "reports": ["..."]}
}
```

Canonicalize JSON before hashing; redact API keys and signed-query secrets. Store raw provider response separately under restricted storage, while committing only manifests/small evidence. Download Meshy outputs immediately: non-Enterprise API outputs are deleted after three days.

### 6) License and rights constraints

| Provider | Verified constraint | Pipeline requirement |
|---|---|---|
| **FAL** | Model pages carry a “Commercial use” label, but that is not blanket rights clearance. FAL’s terms say customers must have all input rights; output can be non-unique and FAL gives no warranty that it is original or non-infringing. Third-party models/materials can have additional terms. FLUX page additionally requires FLUX.1 Pro terms. | Snapshot **FAL ToS + each selected model-page/model-provider term** at generation. Use cleared inputs only. Legal/human approval is required; do not claim copyright exclusivity or non-infringement from an API result. |
| **Meshy free** | Meshy’s Mar. 7, 2026 terms say Meshy owns free-plan AI Customer Output and grants CC BY 4.0: commercial adaptation is permitted with attribution. | Do not ship free-plan output unless the attribution and corresponding rights decision is explicit. |
| **Meshy paid / Enterprise** | Paid users can keep content private, but terms also say Meshy may use non-Enterprise input/output to train/validate/test/improve services unless an Order says otherwise. The terms do not provide a simple blanket exclusive-ownership warranty. Community uploads are CC0. | Do not publish accepted assets to the Meshy Community. Preserve plan/Order evidence; resolve privacy/training and ownership requirements contractually before sending proprietary designs. |
| **Meshy outputs** | API content is retained only three days outside Enterprise; outputs and services are supplied as-is, with no accuracy/non-infringement/IP-protection warranty. | Immediate durable archival plus source/rights receipt is mandatory. |
| **Blender** | Blender is GPL software; Blender Foundation says artwork, including `.blend` and generated files, is the artist’s sole property and may be used commercially. Published Blender Python add-ons/scripts using `bpy` require GPL-compatible licensing. | Blender does not taint game artwork/assets by itself. Keep proprietary game assets distinct from any distributed Blender add-on/scripts; assess script licensing if publishing them. |

### 7) First build recommendation

After the P0 debug-mannequin visual check passes, **do not start with the arena, final textures, or a repaired C0.**

Build the **`JD_Duelist_001` untextured “fit/rig/proxy vertical slice” first**:

- one clean T-pose anatomical carrier;
- separately named armor panels with physical clearance;
- a separate sword blade/guard/grip with a canonical right-hand socket;
- canonical skeleton, weights, OBB/damage proxies, and stress-pose/pair-penetration evidence;
- deterministic GLB → cooked SKM1 proof in the first-person duel camera.

This is the shortest high-fidelity unit that tests every load-bearing requirement: component boundaries, deep injury/armor attachment, Mesh Doctor pair detection, weapon socket correctness, canonical retargetability, PBR readiness, and the Rust/wgpu cooker. Texture it only after that geometry/rig/proxy package clears its gates; then use the same admitted component contract for the second duelist, weapon variants, and modular arena kit.

### Primary sources checked

- FAL inference/queue: <https://fal.ai/docs/documentation/model-apis/inference>
- FAL terms, updated Mar. 3, 2026: <https://fal.ai/legal/terms-of-service>
- FAL FLUX image: <https://fal.ai/models/fal-ai/flux-pro/v1.1-ultra/api>
- FAL Kling video: <https://fal.ai/models/fal-ai/kling-video/v2.1/master/text-to-video/api>
- FAL Tripo 3D: <https://fal.ai/models/tripo3d/tripo/v2.5/image-to-3d/api>
- FAL Rodin 3D: <https://fal.ai/models/fal-ai/hyper3d/rodin/v2.5/fast/api>
- Meshy API: <https://docs.meshy.ai/en/api/text-to-3d>, <https://docs.meshy.ai/en/api/image-to-3d>, <https://docs.meshy.ai/en/api/multi-image-to-3d>, <https://docs.meshy.ai/en/api/remesh>, <https://docs.meshy.ai/en/api/uv-unwrap>, <https://docs.meshy.ai/en/api/rigging>, <https://docs.meshy.ai/en/api/retexture>
- Meshy retention: <https://docs.meshy.ai/en/api/asset-retention>
- Meshy terms, updated Mar. 7, 2026: <https://www.meshy.ai/terms-of-use>
- Blender headless CLI / glTF / baking / license: <https://docs.blender.org/manual/en/5.2/advanced/command_line/render.html>, <https://docs.blender.org/manual/en/5.2/addons/scene_gltf2.html>, <https://docs.blender.org/manual/en/5.2/render/cycles/baking.html>, <https://www.blender.org/about/license/>

### Completion notes

- **Performed:** repo/spec/tooling inspection; live DCC bridge health check; current official FAL/Meshy/Blender documentation and terms verification; MCP tool-surface discovery.
- **No assets generated and no repository files modified.**
- The repository had pre-existing dirty/untracked worktree items; I left all of them untouched.