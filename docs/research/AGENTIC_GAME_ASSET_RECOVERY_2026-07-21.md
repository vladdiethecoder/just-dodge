# Agentic Game-Asset Recovery for Just Dodge

**Date:** 2026-07-21
**Unit:** `SG02-AGENTIC-ASSET-RECOVERY-RESEARCH-005`
**Scope:** Research and quarantined-canary design only. No asset is promoted by this document; `runtime_admitted=false` remains mandatory.

## Decision summary

Successful agentic game-asset work is not a one-prompt mesh generator. The repeatable pattern is:

1. Generate or retrieve a candidate.
2. Import it into an authoritative DCC.
3. Inspect real topology, transforms, materials, skeletons and scale.
4. Apply small deterministic DCC operations.
5. Measure each operation and render controlled views.
6. Reject or locally repair a bounded defect.
7. Round-trip through the shipping interchange format.
8. Require a human decision on appearance and feel.

The agent is most valuable as a technical-artist operator, verifier and pipeline orchestrator. The generator supplies uncertain geometry; it does not supply production truth.

For the current SG02 blocker, generating another whole fighter or smoothly skinning the one-piece armor shell is the wrong next step. The best currently authorized route is:

- retain the accepted MPFB body geometry;
- generate a modern Rigify control rig through MPFB's existing integration;
- pose fingers through Rigify's advanced-finger controls, not raw Mixamo local rotations;
- attach the sword through an explicit `Grip_R` frame;
- segment hard armor at mechanical articulation boundaries and bind each rigid plate to one deform bone or an explicit armor pivot;
- use transferred multi-bone weights only for soft/continuous pieces;
- export a deliberately bounded deform skeleton and validate it after GLB reimport;
- keep the result quarantined until machine contact/deformation gates and human multi-view review both pass.

## Evidence classification

| Evidence | Status | What it proves | What it does not prove |
|---|---|---|---|
| UniRig, SIGGRAPH/TOG 2025 | Peer-reviewed method plus released code/model | Automated skeleton and skin-weight prediction is practical; human refinement before skin prediction is explicitly recommended | Correct hand grasp, semantic armor articulation, Just Dodge topology or shipping license lineage |
| SkinTokens/TokenRig, 2026 preprint | Released MIT code/checkpoints | Unified skeleton/skin generation targets disconnected-part bleeding and supports skin-only use with an existing skeleton | Production grasp, deterministic runtime behavior or approval of its training-data lineage for release |
| Puppeteer, NeurIPS 2025 Spotlight | Peer-reviewed method plus Apache-2.0 code/checkpoints | Automated rigging plus video-guided animation and FBX export are reproducible research paths | Just Dodge's no-baked-combat-motion contract, contact fidelity or armor attachment semantics |
| BlenderMCP | Public implementation | An agent can inspect scenes, invoke bounded DCC operations and use screenshots in a closed loop | That free-form Python or a natural-language prompt yields game-ready assets without validators |
| Tripo Blender plug-in | Public MIT integration | Generation can be embedded in Blender with task tracking, multiview inputs, face limits and PBR options | Rig, grasp, articulation, topology quality or current asset acceptance |
| StraySpark weapon workflow, 2026-03-23 | Firsthand commercial tutorial; vendor-affiliated | Practical agentic success comes from generation, measured inspection, cleanup, UVs, PBR, LOD, collision, export and human review | Independent benchmark evidence or character-production parity |
| AI Forge MCP | Early-access creator self-report | A useful architecture pattern: typed DCC tools, specialized stages, rig inspector, test poses, approve/reject/redo and engine handoff | Independent proof of its AAA/full-pipeline claims; its paid product is not authorized for this project |
| Local MPFB/Rigify probes | Direct measurement on the current host | Rigify 0.6.12 enables in Blender 5.1.2; MPFB generates a 930-bone control rig; advanced-finger masters exist and bounded finger motion is possible | A genuine sword grasp, clean export skeleton, equipped armor or human approval |

## Primary-source findings

### UniRig

Official repository SHA observed through GitHub MCP: `3ae2962ab8109b119228ea40e9cd013c33b9e38e`.

- Inputs: `.obj`, `.fbx`, `.glb`, `.vrm` meshes.
- Outputs: predicted skeleton and skin weights; FBX/GLB merge path.
- Released framework stages: autoregressive skeleton-tree prediction and bone-point cross-attention skin prediction.
- Repository warning: skinning degrades when the predicted skeleton is inaccurate; refine the skeleton before skinning.
- Inference requirement: CUDA GPU with at least 8 GB VRAM.
- Training evidence: approximately 18 hours on four RTX 4090 GPUs for the cited scratch configuration; skin training may require at least 60 GB memory.
- Code license: MIT, repository `LICENSE` SHA `a20d482774136ee1858d92964e896031598902b4`.

Disposition: useful as a later independent rigging arm, not the first SG02 recovery. The current body already has an anatomically fitted skeleton candidate and the blocker is control semantics plus semantic equipment attachment.

### SkinTokens / TokenRig

Official repository README SHA: `7b9d14a47adcc29d6bc99367e6d7780980ddd055`; license SHA: `484d9bbef8720dc2797444a18c972a4e6245a07e`.

- Input: one 3D mesh, or a mesh with an existing skeleton using `--use_skeleton`.
- Output: complete GLB rig with hierarchy and dense per-vertex weights.
- Reported method: Qwen3-0.6B autoregressive rig generator plus discrete skin tokens and GRPO rewards for joint coverage, bone containment, sparsity and deformation smoothness.
- Inference: NVIDIA GPU with at least 14 GB VRAM, Python 3.11+, CUDA 12.1+.
- Reported improvement: 98%–133% skinning accuracy and 17%–22% bone prediction over baselines. These are author-reported preprint results, not local measurements.
- Code license: MIT.

Disposition: technically relevant to disconnected-part weight bleeding and suitable for a later same-input comparison. It still does not infer mechanical armor classes or a sword-grip contact plan. Training/model/data provenance needs a separate release review.

### Puppeteer

Official repository README SHA: `f454c82766f1632fa3b8af76b0c5fba765f6a9c1`; license SHA: `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64`.

- Input: a 3D mesh; video guidance for animation.
- Output: skeleton, skin weights, FBX and optimized animation sequence.
- Environment: Python 3.10, PyTorch 2.1.1, CUDA 11.8, PyTorch3D and flash-attn.
- Code license: Apache-2.0.

Disposition: evidence that end-to-end research rigging is reproducible, but its video-guided animation output cannot replace live MotionBricks combat motion and does not resolve grip contact by itself.

### Agentic DCC systems

BlenderMCP README SHA: `da81e8b189f3632af234d600342575afa4e2bc53`.

The implementation provides scene inspection, object/material manipulation, screenshots, model import and arbitrary Blender Python. Its own documentation warns that complex operations must be broken into smaller steps and that arbitrary Python is a security/production risk. This supports Just Dodge's typed, bounded DCC approach rather than monolithic generated scripts.

Tripo Blender plug-in README SHA: `bbac0d71b3224cff3418576f4ac1938782f6c31c`. It exposes generation and task management in Blender but makes no rig, grasp or armor-equipping guarantee.

AI Forge README SHA: `0913f3201c200ca2c1dda36e0a96dc722a6f65a6`. It is explicitly early access and says not everything has been tested. Its strongest transferable lesson is structural: break the pipeline into typed stages, record every operation, inspect rigs under test poses, and retain approve/reject/redo gates. Its commercial subscription and unverified claims are not an allowed implementation dependency.

### Firsthand production workflow

StraySpark's 2026-03-23 weapon tutorial explicitly states that raw 2026 text-to-3D output is not game-ready. Its successful case uses generated weapon variants followed by measured import inspection, retopology, UVs, PBR material construction, LODs, collision, export and human viewport review. The article is vendor-affiliated, so its timing and quality claims are not independent benchmarks. Its operational sequence is nevertheless concrete and consistent with the project's measured experience.

## Local falsification evidence

Direct non-saving probes on Blender 5.1.2 established:

- `bl_ext.user_default.rigify` enables successfully.
- The built-in human metarig contains 159 bones and 30 finger bones.
- A default generated Rigify rig contains 706 bones, 160 `DEF-` bones and advanced-finger controls.
- MPFB's modern `add_rigify_rig` operator converts the accepted body to a 930-bone Rigify control rig and redirects its armature modifiers to that rig.
- The accepted body receives 179 `DEF-` vertex groups.
- Rigify's official manual defines the advanced-finger master as rotating the finger and bending it through local Y scaling.
- On the accepted body, master-Y controls produced finite evaluated vertices, 54.45–89.89 mm fingertip displacement and maximum relative finger-bone length change of `1.4691e-6`. This is a bounded deformation probe, not grasp evidence.

The first full canary harness was stopped after two implementation failures before any candidate was saved:

1. Wrong Blender 5.1 Eevee enum.
2. Iterating `PoseBone` objects as if they were name strings.

Evidence: `assets/foundation/v2/qa/sg02_lifecycle_kit_redo/evidence/rejected/rigify_canary_harness_strike2/`.

These failures do not falsify Rigify. They falsify continued patching of that monolithic harness. The next attempt must switch execution surface.

## Exact SG02 recovery sequence

### 1. Freeze accepted authorities

- Body geometry and body proportions remain unchanged.
- Sword and armor remain source candidates; no promotion state changes.
- Prior Mixamo scenes remain rejected/quarantined evidence.

### 2. Switch from raw deform-bone rotation to production controls

Use MPFB's modern Rigify workflow:

```text
accepted MPFB body
  -> MPFB fitted Rigify metarig
  -> generated Rigify controls
  -> Rigify Advanced Finger master/FK controls
  -> bounded DEF skeleton for export
```

The control rig is authoring infrastructure. No action or combat clip is authored. A future live MotionBricks packet drives the runtime deform skeleton through deterministic retargeting.

### 3. Build the grip as explicit data

Required nodes:

```text
DEF-hand.R
  -> Grip_R socket/frame
     -> sword root
sword root
  -> Grip_R geometry frame
  -> BladeStart
  -> BladeTip
  -> optional Grip_L
```

The sword's grip frame must be measured from the actual handle geometry, not the object origin. For the current sword, PCA inspection found a 1.093 m principal span before normalization and a distinct guard radial peak separating the handle from the blade.

Required solver layers:

1. Dominant-hand socket transform.
2. Wrist/arm IK to the socket.
3. Independent finger and thumb controls.
4. Geometric contact and prohibited-penetration measurement.
5. Optional physical constraint only after geometry passes.

### 4. Decompose armor semantically

- Cuirass, pauldrons, cops, vambraces, greaves and rigid boot shells: rigid islands, one deform bone or explicit armor pivot each.
- Leather/fabric junctions and continuous flexible pieces: transferred/pruned weights.
- Faulds, straps, cloth and hair: separate secondary systems only when their base attachment is already valid.
- Body masks: presentation/readability optimization after fit is proven, never evidence that penetration was fixed.

A 1,246-component disconnected generator mesh is not a semantic plate graph. Agentic clustering must produce named parts and each part must receive an explicit mechanical class before binding.

### 5. Use a typed canary, not another monolithic script

The next canary must be executed through the typed Blender DCC/MPFB operator surface or a separately reviewed minimal harness. It must perform one unit at a time:

1. Generate Rigify rig and inspect controls.
2. Save checkpoint.
3. Create `Grip_R` and attach an analytical cylinder matching the measured handle.
4. Drive one finger, verify finite geometry and invariant segment lengths.
5. Drive four fingers and thumb, verify contact.
6. Substitute the actual sword.
7. Export deform bones only and reimport GLB.
8. Render palm, edge, blade-axis and first-person views.

The canary fails closed on any non-finite vertex, unweighted visible vertex, more than four retained influences, weight-sum error above `1e-5`, relative finger-length error above `1e-4`, contact gap above 15 mm, prohibited penetration above 0.5 mm, missing socket, duplicate skeleton or GLB validator error.

## What the agent should and should not do

Agent-owned:

- source and license retrieval;
- file/hash/task lineage;
- typed DCC operations;
- geometry and skeleton measurements;
- controlled render generation;
- GLB validation/reimport;
- deterministic engine cooking;
- defect localization and bounded repair proposals.

Human-only:

- whether anatomy, armor fit, grip, silhouette and first-person readability are acceptable;
- license/provenance decisions for new dependencies or training data;
- paid service authorization;
- promotion of a quarantined candidate.

The agent must not hide failures with body masks, smooth the whole armor shell, infer success from one render, substitute a baked grip/animation, or treat an auto-rigger's benchmark as local evidence.

## Upgraded executable control plane

The local asset control plane was upgraded and exercised after the earlier
monolithic Rigify canary harness reached Strike 2:

- Blender `5.2.0 LTS` is installed side-by-side and is the active binary;
- `dcc-mcp-cli` and `dcc-mcp-server` are `0.19.62`;
- `dcc-mcp-blender` is `0.1.39`;
- MPFB `2.0.17` and Rigify `0.6.12` are enabled under Blender 5.2;
- the seven stable scene/validation/rigging/interchange/mesh/material/render
  skills are loaded automatically after every typed-DCC service restart;
- community BlenderMCP `1.6.4` runs in a separate factory-startup Xvfb
  process on loopback with telemetry disabled and Poly Haven enabled;
- the arbitrary-Python BlenderMCP process is not allowed to open the Just
  Dodge project or credential-bearing paths;
- GitHub MCP is pinned to official server `v1.6.0` instead of a stale local
  `latest` image;
- Meshy MCP remains `0.4.0-hermes.20260720.1`, current with upstream `0.4.0`.

The official Blender Lab MCP was researched but not added to the production
surface. Blender's own page warns that it executes LLM-generated code without
guards and recommends a VM or a system without sensitive data. Typed DCC-MCP
remains authoritative; isolated BlenderMCP remains a disposable integration
lane for Poly Haven and externally generated candidates.

### Executed end-to-end proof

A typed-only smoke asset was built from primitives, assigned two Principled
materials, transform-frozen, joined, beveled, UV-unwrapped, validated, saved,
exported to GLB, imported into a clean scene, validated again and rendered.
The round-tripped object had:

- 1,968 vertices, 2,430 edges and 964 triangles;
- two material slots (`JD_Smoke_Leather`, `JD_Smoke_Steel`);
- one UV map, 2,892 UV coordinates and 502 islands;
- zero validation warnings/errors;
- passing GLB export-readiness report
  `ddc2b1c8-a533-4f53-95b9-be66f93c918d`;
- a complete, unclipped, machine-reviewed render after one measured camera
  repair.

Evidence is quarantined under
`.temp/verification/blender-agentic-toolchain-2026-07-21/`. It is explicitly
ad-hoc verification, `suite_green=false`, `runtime_admitted=false`, and not a
production Just Dodge asset. The GLB SHA-256 is
`760f249171f722c6ab41398ba6885a7e4d13b88df48c65fa4102e5b7177ba2df`;
the final render SHA-256 is
`c97dd56a2795e6d619061821566df732ee839414d5b5f8ae8b3dca724b94ae50`.

### Recovery-method change dictated by the proof

The next quarantined grip canary must not be another large generated Blender
script. It must use the typed sequence:

1. `search` and `describe` the exact DCC tool.
2. Load only the required authoring skill.
3. Perform one bounded mutation.
4. Read back geometry, transforms, skeleton state or material state.
5. Save a checkpoint before the next mutation.
6. Run the relevant validator immediately.
7. Export and reimport before any visual promotion question.
8. Render orthographic/contact views and stop at the human gate.

The smoke run also falsified two unsafe assumptions: `new_scene` creates an
empty scene, not Blender's default cube scene; and primitive `scale` values at
`size=1` produced the measured final dimensions used by the recipe. The first
render exposed disconnected components, the agent separated the joined mesh,
measured world-space bounds, recomputed touching centers and rebuilt. The
second render clipped the blade tip, so the constrained camera was moved back
and changed from 70 mm to 55 mm. These are the required inspect-repair loops,
not incidental polish.

## X/Twitter workflow synthesis

Direct X posts and attached workflows were independently checked. The
strongest surviving pattern is AssetHub's modular character route:

`GPT-Image2 concept → semantic parts → Tripo 3.1 multi-view candidates →`
`Blender/ZBrush assembly → manual/assisted retopo → UV/material sets →`
`Substance Painter bake/rework → controlled rig/body → Unreal proof`.

This survives scrutiny because the posts expose component generation, named
DCC stages and an engine result. It still does not waive topology budgets,
weight, collision, LOD or round-trip gates. The operational evidence and exact
URLs are recorded in
`docs/research/X_AI_3D_TO_GAME_WORKFLOW_EVIDENCE_20260721.md`.

Other admitted patterns:

- AI models are useful for blockout, candidate geometry, static props,
  environment assembly and rapid playable prototypes;
- agent success improves when the human supplies a stable spatial
  representation, references, explicit dimensions and named anchors;
- the dependable loop is brief/reference, bounded mutation, inspect/render,
  validate, targeted repair, export/reimport, then human acceptance;
- engine placement is evidence of integration only, not hero-asset quality;
- one-prompt fighter-jet, city and game demos are prototype evidence unless
  topology, UVs, materials, rigging, collision and interchange receipts exist;
- rigging remains the weak frontier: firsthand reports still describe more
  than a day of debugging with residual clipping, and UniRig users report raw
  skinning failures.

Rejected claims include “one click,” “production ready,” “10M polygons,” and
“full game in 20 minutes” when no inspectable asset, cleanup sequence, engine
build or measurable receipt is available.

The supplied Grok/X research was then expanded and independently source-checked
in `docs/research/GROK_X_AI_BLENDER_WORKFLOW_VERIFICATION_2026-07-21.md`.
Materially new recovery mechanisms are:

- `@posi_posi8`: isolate modeler, camera/previs, critic and making-of lanes;
  checkpoint/merge through explicit scene contracts; record model/client,
  adapter, Blender version, port, prompt, time and hashes; benchmark model
  authority per task rather than universalizing one author's preference;
- `@hos_giken`: validate proportions with temporary bones before grafting,
  retopologize around articulation/hard zones, quick-bind and pose during
  topology/weight work, and treat single-image PBR maps as relight-tested
  hypotheses;
- `EdgeLoopStitcher`/`CutomWeightPainter`: unequal-count boundary matching,
  pose-during-weight hold/revert/zero, bind reset and influence cleanup are MIT
  mechanisms verified from source and translated into typed Blender contracts;
- `@poistudioltd`: the dotted-old-painting look is a two-Midjourney-moodboard
  method (oil painting + dithering), not a Grok workflow. Just Dodge applies it
  only to far water/sky/divine architecture while keeping sand/combat evidence
  realistic and readable; see
  `docs/research/ARENA_DOTTED_DIVINE_DISTANCE_2026-07-21.md` and concept v1;
- MrLarus/Depth Anything/Seedance: depth-video is admissible only as an offline
  auxiliary teacher channel with held-out RGB/depth/contact-aware ablation.
  Generated video is not skeleton, contact, physics or runtime truth.

These findings refine the next SG02 canary but do not reopen or repair the
Strike-2 script. The new canary must test one selected finger at neutral/30°/60°,
thumb opposition, metacarpal load, hold/revert semantics, and deterministic
loop correspondence before whole-hand grip work.

## Primary sources

- UniRig official code: https://github.com/VAST-AI-Research/UniRig
- UniRig paper/project: https://arxiv.org/abs/2504.12451 and https://zjp-shadow.github.io/works/UniRig/
- SkinTokens official code: https://github.com/VAST-AI-Research/SkinTokens
- Puppeteer official code: https://github.com/Seed3D/Puppeteer
- Puppeteer paper: https://arxiv.org/abs/2508.10898
- BlenderMCP official repository: https://github.com/ahujasid/blender-mcp
- Tripo Blender plug-in: https://github.com/VAST-AI-Research/tripo-3d-for-blender
- Blender Rigify generated-rig features: https://docs.blender.org/manual/en/5.1/addons/rigging/rigify/rig_features.html
- MPFB rigging/posing developer documentation: https://static.makehumancommunity.org/mpfb/developer/rigging_and_posing.html
- StraySpark firsthand workflow: https://www.strayspark.studio/blog/text-prompt-game-ready-asset-blender-mcp-ai
- AI Forge early-access self-report: https://github.com/HurtzDonutStudios/ai-forge-mcp
- Blender 5.2 LTS release notes: https://developer.blender.org/docs/release_notes/5.2/
- Blender Lab MCP security and examples: https://www.blender.org/lab/mcp-server/
- AssetHub modular character workflow: https://x.com/assethub_io/status/2062928898405659040
- AssetHub MetaHuman workflow: https://x.com/assethub_io/status/2068012076673769711
- Kimi/BlenderMCP fighter-jet prototype: https://x.com/Oluwaphilemon1/status/2078442028984107338
- BlenderMCP limitations: https://x.com/Rbaker923456/status/2049259761019871667
- posi_posi8 BlenderMCP evidence: https://x.com/posi_posi8/status/2078853975655530849
- HOS deformation-first topology: https://x.com/hos_giken/status/2071005663182901667
- HOS temporary skinning: https://x.com/hos_giken/status/2077916252153295244
- HOS EdgeLoopStitcher source: https://github.com/hossan-tk9004/EdgeLoopStitcher
- HOS CutomWeightPainter source: https://github.com/hossan-tk9004/CutomWeightPainter
- Bobo Wong two-moodboard technique: https://x.com/poistudioltd/status/2078691339877974518
- MrLarus depth-video reference: https://x.com/MrLarus/status/2079113446105501983
- Depth Anything V2: https://github.com/DepthAnything/Depth-Anything-V2
- ARDY: https://arxiv.org/abs/2607.08741 and https://github.com/nv-tlabs/ardy
