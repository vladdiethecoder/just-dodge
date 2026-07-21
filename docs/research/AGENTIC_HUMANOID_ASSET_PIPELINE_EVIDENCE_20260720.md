# Recent real-world evidence: agentic humanoid game-asset pipelines

**Research cut-off:** 2026-07-20
**Scope:** Blender- and engine-centered pipelines using Meshy, Rodin, Tripo, Hunyuan3D, MetaHuman, Character Creator, MPFB/MakeHuman, and agentic control surfaces (MCP/Claude Code/Codex-style tools).
**Evidence policy:** primary/community sources are preferred. Vendor claims are kept separate from measured or user-reproduced outcomes. A source that demonstrates agentic orchestration is not treated as proof that the generated humanoid is game-ready.

## Executive finding

The recent evidence supports a **hybrid, component-first pipeline**, not an autonomous prompt-to-shipping-humanoid pipeline:

- **AI/agents are succeeding at:** concept exploration, image-to-3D blockout, isolated component variants, batch generation, Blender scene operations, texture/material hypotheses, and orchestration of repeatable tool calls.
- **Parametric/sculpt/DCC work is still authoritative for:** the body-carrier topology, deformation loops, hands/feet, UV ownership, weights, canonical skeleton, sockets, clearance, collision/fracture proxies, LODs, and engine export/cook.
- **The most repeated failure boundary is humanoid deformation.** Attractive generated meshes frequently fail exact pose, hand/foot articulation, vertex order/topology invariants, or downstream rig/conform requirements.
- **For a custom engine, the safe architecture is:** agents propose and execute bounded operations; Blender owns geometry; a deterministic cooker owns runtime compatibility; promotion is hash- and evidence-gated.

## Evidence matrix

Strength labels:

- **A — measured project artifact:** reproducible local geometry/QA output with numeric gates.
- **B — primary/community reproduction:** an actual user or maintainer reports a concrete success/failure and gives a workflow or artifact.
- **C — practitioner pipeline documentation:** a real maintained repository describes a production-shaped workflow, but does not provide an independent pass-rate study.
- **D — vendor/marketing or sponsored claim:** useful for capability discovery, not sufficient for adoption or readiness.

| ID | Date | Source | Class / lane | Concrete evidence | What it means for a humanoid game pipeline |
|---|---|---|---|---|---|
| L1 | 2026-07-20 | Just Dodge local Meshy-6 candidate 002: [`report.json`](../../assets/foundation/v2/fighters/f0_body_carrier/qa/candidate_002/report.json), [`generation_parameters.json`](../../assets/foundation/v2/fighters/f0_body_carrier/candidates/meshy6_002/generation_parameters.json) | **A — measured Meshy image-to-3D failure** | The generated body measured 109,423 vertices / 218,902 triangles, had **0 UV layers**, and failed the machine gate for `MESH_TOO_MANY_TRIANGLES` and `MESH_MISSING_UVS`. Visual QA recorded fused blade-like finger masses, pinched wrists, non-deformation-ready shoulders/armpits, broken hair sheets, and under-resolved feet/toes. The asset was quarantined, not promoted. | This is direct evidence that a contemporary high-quality Meshy model can be a useful silhouette/reference but still be unsuitable for rigging or runtime without a separate topology and UV authority. The raw GLB must never enter the engine path. |
| L2 | 2026-07-13 | Just Dodge local Meshy text-to-3D rigging-pose study: `/home/vdubrov/.hermes/skills/gamedev/game-asset-pipeline/references/meshy-text-to-3d-rigging-pose-strike2-2026-07-13.md` | **A — measured exact-pose failure** | Two Meshy-6 text-to-3D attempts requested `pose_mode: t-pose` with explicit symmetry/T-pose constraints. One produced bent/raised arms and asymmetric legs; the other bent arms, asymmetric feet, and an unwanted back prop. Both failed visual QA. | Natural-language “T-pose” is not an exact rigging contract. Exact pose must be measured after import, and controlled multi-view reference should replace prompt retries after a small failure budget. |
| L3 | 2026-07-10 / recorded in project design | Just Dodge local MPFB2 + bounded Meshy-detail transfer: [`MESHY_ASSET_PIPELINE.md`](../design/MESHY_ASSET_PIPELINE.md), lines 51 and 117–119 | **A — measured parametric-base success** | MPFB2 2.0.17 was accepted as the articulation carrier: one closed 13,380-vertex / 13,378-face body, 163 bones, 38 finger bones, 28 toe bones, zero unbound vertices. Simultaneous 60° finger/toe flex had 0.142 mm worst-case error and zero vertices over 1 mm. A bounded Meshy surface-detail transfer changed 5,326 vertices by at most 4 mm while preserving face indices and weights exactly; rerun was byte-identical. | The strongest working pattern is **parametric base + bounded generative surface detail**. AI supplies appearance/silhouette variation; the base mesh supplies deformation topology, skeleton, and weights. |
| L4 | 2025-06-04 to 2025-06-09 | Epic Developer Community Forum, “Is MetaHuman 5.6 Body Conform feature broken in the public release?” [`thread`](https://forums.unrealengine.com/t/is-metahuman-5-6-body-conform-feature-broken-in-the-public-release/2540575) | **B — community MetaHuman failure/recovery** | Users reported “vertex monsters,” “inconsistent topology” errors, and failures even after exporting/importing an apparently unchanged MetaHuman body. A Maya `Transfer Attributes` workflow was proposed as a workaround; one user reported that a modified head could be imported/rigged after transferring vertices from the original, while a self-modeled head still failed. | Production conform systems depend on topology **and vertex order**, not only visual similarity or vertex count. A Blender/custom-engine pipeline needs explicit topology identity, vertex-order preservation, and round-trip tests; visual likeness is insufficient. |
| L5 | 2025-06-26, with follow-up 2025-07-20 | Epic Developer Community Forum, “UE 5.6 MetaHuman Creator fails to bring in a custom character effectively.” [`thread`](https://forums.unrealengine.com/t/ue-5-6-metahuman-creator-fails-to-bring-in-a-custom-character-effectively/2577929) | **B — community MetaHuman failure** | The user used Blender, Wrap4D, a conforming MetaHuman head, and the MetaHuman DNA Blender add-on. The DNA file reproduced the intended small jaw in Blender, but UE 5.6 consistently enlarged/misrepresented the jaw. A follow-up user reported Blender DNA edits that worked in Blender but failed during Blender→UE import. | Even when an intermediate DCC representation is correct, the destination solver/import path can change the shape. Treat each DCC/engine boundary as a separately validated authority; do not assume DNA/FBX/GLB round-trip fidelity. |
| L6 | 2025-08-15 to 2026-03-15 | Epic Developer Community Forum, “Issue with Neck Deformation When Using Custom Body Template in MetaHuman Creator (UE5.6).” [`thread`](https://forums.unrealengine.com/t/issue-with-neck-deformation-when-using-custom-body-template-in-metahuman-creator-ue5-6/2642824) | **B — community MetaHuman failure with workaround** | A custom body whose proportions, seam, topology, pivots, and coordinates matched the standard still produced stretched neck deformation and a shifted `neck_01` bone. Another user confirmed the same issue. A later reply suggested disabling alignment and `Adapt Neck`; one user reported that workaround helped. The thread notes the option was missing in 5.7 for another user. | Reference-pose alignment, skeleton adaptation, and version-specific importer settings are part of the asset contract. Version-pin the DCC/engine route and record workaround settings; do not rely on “matching topology” alone. |
| L7 | 2026-06-09 | 73K-Y, `3D-Workflow-Pipeline`: [`README`](https://github.com/73K-Y/3D-Workflow-Pipeline/blob/main/README.md), [`commit history`](https://github.com/73K-Y/3D-Workflow-Pipeline/commits/main/) | **C — practitioner Meshy→Blender→retopo→rig pipeline** | The maintained README explicitly maps `Meshy → Blender → RetopoFlow 4 → Auto-Rig Pro`, says each stage has a strict gate, labels the humanoid path “most complex; joint loops required,” and states: “The AI mesh is triangle soup, it is a sculpt reference, not a production mesh. Never use it directly. Never skip retopology.” It also documents manual weight fixes at shoulders, hips, wrists, knees, and neck. Commit history shows the pipeline documentation was actively revised on 2026-06-09. | This is a real practitioner workflow, not a one-click claim: AI is upstream reference generation; retopo, rigging, weights, deformation testing, and export remain explicit stages. It is close to the required custom-engine division of labor. |
| L8 | 2025-12-27 | `lapaelp-ui/tripoAiModelAddon`: [`README`](https://github.com/lapaelp-ui/tripoAiModelAddon/blob/main/README.md), [`commit history`](https://github.com/lapaelp-ui/tripoAiModelAddon/commits/main/) | **B/C — real Tripo Blender integration, with failure handling** | The add-on implements image-texture→Tripo→Blender import, optional humanoid auto-rig, and preset Idle/Walk/Run/Jump animation. Its own troubleshooting documents 403 failures from invalid/expired keys, insufficient credits, or endpoint restrictions; “auto rig fails or bones look wrong” when the model is not humanoid; and the fallback “Generate Only” path. | Agentic/Blender integration can collapse UI steps, but service quotas, credential state, humanoid classification, and bone quality remain failure surfaces. The add-on demonstrates orchestration, not proof that arbitrary generated characters are game-ready. |
| L9 | 2025-03-16 | `ahujasid/blender-mcp` Discussion #47, “Attempt on character dance”: [`discussion`](https://github.com/ahujasid/blender-mcp/discussions/47) | **B — community agentic Blender success, narrow scope** | A user posted an actual character-animation screen recording from Blender MCP; the maintainer replied “Love this, so good!!” The thread does not provide topology, rig, export, or engine metrics. | Agent control can produce visible character-animation experiments. This is evidence for the **presentation/prototyping** lane only, not for deformable production topology or runtime admission. |
| L10 | 2025-10-21 and 2026-01-21 | `ahujasid/blender-mcp` Discussion #158, “Works with Codex CLI from Chat GPT”: [`discussion`](https://github.com/ahujasid/blender-mcp/discussions/158) | **B — agentic integration success** | A user wrote “The plugin also works with the Codex CLI.” A later reply gave a `config.toml` MCP setup and said “it worked for me as well.” | The connectivity layer—agent → Blender via MCP—has real user confirmation. That validates investing in typed/bounded DCC operations, but says nothing about the geometric quality of generated humanoids. |
| L11 | 2025-04-06 | `ahujasid/blender-mcp` Discussion #98, “Hyper3D Rodin Error”: [`discussion`](https://github.com/ahujasid/blender-mcp/discussions/98) | **B — unresolved Rodin integration failure** | The only user post is an attached `readme.md`; the question remained unanswered at extraction time. | Rodin/Blender agent integration had unresolved user support cases in this period. Do not make a provider a hard pipeline dependency without a fallback lane and durable task/error receipts. |
| L12 | 2025-09-22 | `ahujasid/blender-mcp` Discussion #153, “Hunyuan3D local integration”: [`discussion`](https://github.com/ahujasid/blender-mcp/discussions/153) | **B — unmet/feature-request evidence** | A user asked for an MCP tool so an LLM could call a local Hunyuan3D installation to generate models or textures. The post had no maintainer response at extraction time. | Local Hunyuan3D availability and agent control were not the same thing. A local generator needs a versioned adapter, queue/status handling, output validation, and safe file boundaries before it is an agentic pipeline component. |
| L13 | 2026-02-06 to 2026-03-25 | `RFingAdam/mcp-blender`: [`commit history`](https://github.com/RFingAdam/mcp-blender/commits/main/) | **B/C — agentic DCC infrastructure with live-test evidence** | The history records “Add AI-driven 3D modeling with self-refinement loop,” a multi-backend AI generation system, “Merge v0.3.0: 218 tools, live-tested on Blender 4.2,” and “Fix 9 bugs found during live Blender 4.2 testing.” | Self-refinement and broad typed tool surfaces are becoming practical, but the evidence is infrastructure-level. A self-refinement loop must still be bounded by hard geometry/deformation gates; more tools do not make topology correct. |
| L14 | 2026-05-15 / June 2026 showcase | World Labs IMAGE-BLASTER: [`GitHub`](https://github.com/neilsonnn/image-blaster), [`showcase`](https://www.worldlabs.ai/labs/showcase/image-blaster) | **B/C — agentic multi-provider pipeline success, non-humanoid focus** | The project takes one image and orchestrates Claude skills, World Labs Marble, Hunyuan 3D through FAL, image cleanup, object extraction, physics, lighting, and SFX. The README says it can produce an explorable environment in under five minutes and export assets for Unity, Unreal, Godot, Blender, and other clients. The showcase explicitly describes dynamic objects becoming standalone editable meshes while the static environment is generated separately. | This is strong evidence for **orchestration and decomposition**: agents can coordinate multiple generators and produce editable outputs. It is not evidence that a generated humanoid is rig-ready; the same separation principle should be applied more strictly to body, armor, hands, feet, and weapons. |
| L15 | 2025-01-28 | MPFB2 2.0.8 official release notes: [`release notes`](https://static.makehumancommunity.org/mpfb/releases/release_208.html), [`about MPFB`](https://static.makehumancommunity.org/mpfb/about.html) | **C/D — parametric baseline and honest limitation disclosure** | MPFB describes one-click humanoid generation, parametric body modeling, automatic rig choices, Rigify, IK/FK, procedural skin/eyes, and asset libraries. The first stable 2.0.8 release explicitly says asset-creation tools had limited testing, the integrated MakeTarget lacked features, and the “Game Engine” material had very limited testing. | Parametric generators are valuable because they preserve a known body topology/rig contract, but even they require release pinning and engine-specific validation. “Parametric” is a better starting point for the carrier, not a reason to skip QA. |
| L16 | 2026-06-03 | Hyper3D CTO interview in 80 Level: [`Rodin Gen-2.5 interview`](https://80.lv/articles/how-hyper3d-rodin-gen-2-5-is-bringing-production-level-control-to-ai-3d-generation) | **D — vendor statement, useful boundary acknowledgement** | The CTO says AI 3D is “best understood as part of a workflow,” that outputs reduce workload rather than replace the pipeline, and that complex cases requiring strict topology, animation-ready edge flow, or specific art direction still need human refinement. The article also says Smart Low-Poly was still beta. | Even the provider’s own production framing supports a hybrid interpretation. Treat “Smart Low-Poly,” high-poly, and native texturing as candidate accelerators; retain Blender/engine gates. |

## Cross-source pattern

### 1. The successful unit is smaller than “a humanoid”

The local Just Dodge evidence accepted or conditionally accepted isolated blade/guard and separate body/extremity components, while whole-body and whole-sword attempts produced fused or under-resolved interfaces. IMAGE-BLASTER likewise separates dynamic objects from the static environment. The practical unit of generation is therefore a **semantic component with a declared boundary**, not a full character scene.

### 2. Humanoid topology is a hard exception

Static props can tolerate imperfect edge flow if silhouette, materials, collision, and budgets pass. A humanoid cannot: shoulders, elbows, wrists, hips, knees, neck, face, palms, fingers, ankles, and toes require deformation-aware topology. The MetaHuman threads show that even a visually matching mesh can fail due to vertex order or solver-specific topology expectations. The local Meshy result shows the same boundary in a more direct form: fused digits and pinched wrists are not fixed by a texture pass.

### 3. Auto-rig is a diagnostic, not the canonical rig

Meshy and Tripo can supply auto-rigged outputs or animation presets, and agent demos show visible character motion. However, the evidence does not establish that these rigs preserve the project’s canonical bone IDs, finger/toe articulation, bind pose, influence budgets, or retarget semantics. Use auto-rig for a fast plausibility test or source skeleton; do not let it replace a pinned production skeleton.

### 4. DCC round trips are part of the problem

MetaHuman failures surfaced at Blender→DNA→UE and FBX/export/import boundaries. Tripo’s add-on documents service and humanoid-classification failures. The custom engine must therefore validate after every boundary:

- source GLB/FBX import;
- Blender-owned `.blend` save/reopen;
- rig/weight export and re-import;
- GLB/FBX interchange parity;
- cooker output;
- runtime bind-pose and stress-pose capture.

### 5. More autonomy increases the need for gates

MCP/Codex/Claude integrations are now demonstrably usable, and self-refinement loops are being implemented. But agentic loops make it easier to repeat the wrong repair or silently promote a visually appealing failure. Every operation needs typed inputs, explicit rejection conditions, immutable before/after evidence, and a strike/rollback policy.

## Recommended component-first pipeline for a custom engine

This is the implementation recommendation derived from the evidence and aligned with the project’s existing authority docs.

### G0 — manifest, rights, and acceptance contract

Create a versioned manifest before any paid generation call:

- stable `asset_id` and component IDs;
- body carrier vs armor vs weapon vs collision/fracture role;
- metric dimensions and axes;
- canonical skeleton and sockets;
- face/texture/LOD budgets;
- required body↔armor and hand↔weapon clearance pairs;
- input/reference rights and provider/model/version receipt;
- explicit non-goals (for example: “not a final rig” or “reference only”).

### G1 — concept and reference control

Use the cheapest image-generation path for coherent front/side/back/three-quarter sheets. Require one semantic object or component group per sheet. Reject inconsistent views, occluded hands, fused equipment, or ambiguous boundaries before spending 3D credits.

### G2 — isolated 3D candidates

Generate one component per task:

- body carrier or undersuit;
- helmet/head guard;
- torso/pauldrons/gauntlets/greaves;
- blade/guard/grip/pommel;
- collision/fracture proxy candidates.

Prefer multi-view image-to-3D for proportion-critical pieces. Keep raw outputs quarantined and preserve task JSON, source bytes, output hashes, and provider terms.

### G2a — raw geometry gate

Before rigging, texture refinement, or assembly, fail closed on:

- wrong dimensions/axis/origin;
- fused semantic components;
- non-manifold or degenerate geometry;
- missing UVs where required;
- excessive faces;
- missing articulated digits or deformation zones;
- exact T-pose/symmetry failure;
- loose props or invented geometry.

The local Meshy candidate 002 demonstrates why this gate must be machine-readable.

### G3 — Blender authority: carrier, retopo, rig, and materials

Use a known-good parametric body carrier (MPFB2 or equivalent) for the deforming anatomical core. Use AI meshes for bounded surface/reference transfer or replaceable armor, not as an excuse to rewrite the carrier’s topology.

For each candidate:

1. import to a disposable Blender scene;
2. bake and measure transforms in world space;
3. create a Blender-owned `.blend` and named collections;
4. fit/retopologize manually or with a constrained, reviewed tool;
5. create or preserve canonical bones and inverse binds;
6. temporary-rig and stress-test before finalizing topology;
7. author UVs, materials, sockets, collision and fracture proxies;
8. preserve components as separate objects until clearance passes.

### G4 — deformation and pair-clearance gate

Run neutral, 30°, and 60° stress poses for all articulation zones, plus body↔armor and weapon↔hand/body clearance. Check vertex displacement, joint contact, influence count, zero-weight vertices, segment lengths, and visual continuity. Do not accept clean neutral wireframes without deformed evidence.

### G5 — deterministic engine cook

The cooker, not the generator or Blender viewport, is the final runtime gate. Validate:

- vertex/index/bone counts;
- canonical bone IDs and hierarchy;
- inverse binds and normalized weights;
- scale and axis conversion;
- UV/material bindings;
- collision/fracture/socket metadata;
- LOD budgets;
- re-import parity;
- runtime bind pose and fixed stress/contact captures.

Runtime must not call Meshy, Rodin, Tripo, Hunyuan3D, or an agent. It loads only content-addressed, accepted cooked assets.

## What to automate vs what to keep human/DCC-owned

| Function | Agent/AI role | Authority |
|---|---|---|
| Style exploration and variants | Generate, rank, preserve receipts | Human-approved reference set |
| Silhouette/blockout | Propose candidates and isolate components | Blender geometry gate |
| Retopology | Suggest/accelerate repetitive operations | Artist/Blender topology contract |
| UVs and texture hypotheses | Generate candidate maps/materials | Blender UV/PBR validation and bake |
| Rig placement | Mark joints / compare auto-rigs | Canonical skeleton and bind tests |
| Weight painting | Suggest or initialize | Stress-pose QA and human repair |
| Armor fit and assembly | Run bounded fit/clearance tools | Blender pair-clearance gate |
| Collision/fracture/LOD | Generate candidates | Engine budgets and deterministic cook |
| Final acceptance | Summarize evidence and flag defects | Independent visual review + human decision |

## Bottom line

The real-world 2025–2026 record supports an **agentic technical-art assistant**, not an autonomous humanoid asset factory. The highest-confidence production strategy is:

> **Parametric/artist-authored carrier for deformation truth; AI for reference, surface, and component variation; agentic Blender orchestration for repeatable bounded operations; deterministic custom-engine cooking and fail-closed evidence for promotion.**

This architecture preserves the speed benefits demonstrated by Blender MCP, Tripo/Blender integrations, Meshy agent skills, Hunyuan/IMAGE-BLASTER orchestration, and Rodin/AI generation while respecting the failures repeatedly observed in Meshy humanoid outputs, MetaHuman conform, vertex-order round trips, and auto-rigging.

## Source notes and limits

- The local Just Dodge entries are primary project evidence, not general population statistics.
- The 73K-Y, Tripo add-on, RFingAdam, Blender MCP, and IMAGE-BLASTER repositories demonstrate maintained workflows or integrations; they do **not** publish independent humanoid pass rates.
- The 80 Level Rodin piece is a sponsored vendor interview and is explicitly classified as a vendor statement.
- The MetaHuman forum threads are user reports with useful reproductions/workarounds, not official Epic bug resolutions.
- Search did not yield a strong, independently measured 2025–2026 Tripo/Rodin/Hunyuan humanoid-to-shipping-engine success study. That absence is itself a reason to require a local bake-off and evidence packet before selecting a provider.

## Primary URLs

1. https://github.com/73K-Y/3D-Workflow-Pipeline
2. https://github.com/lapaelp-ui/tripoAiModelAddon
3. https://github.com/RFingAdam/mcp-blender
4. https://github.com/ahujasid/blender-mcp/discussions/47
5. https://github.com/ahujasid/blender-mcp/discussions/98
6. https://github.com/ahujasid/blender-mcp/discussions/153
7. https://github.com/ahujasid/blender-mcp/discussions/158
8. https://github.com/neilsonnn/image-blaster
9. https://www.worldlabs.ai/labs/showcase/image-blaster
10. https://forums.unrealengine.com/t/is-metahuman-5-6-body-conform-feature-broken-in-the-public-release/2540575
11. https://forums.unrealengine.com/t/ue-5-6-metahuman-creator-fails-to-bring-in-a-custom-character-effectively/2577929
12. https://forums.unrealengine.com/t/issue-with-neck-deformation-when-using-custom-body-template-in-metahuman-creator-ue5-6/2642824
13. https://static.makehumancommunity.org/mpfb/about.html
14. https://static.makehumancommunity.org/mpfb/releases/release_208.html
15. https://80.lv/articles/how-hyper3d-rodin-gen-2-5-is-bringing-production-level-control-to-ai-3d-generation
