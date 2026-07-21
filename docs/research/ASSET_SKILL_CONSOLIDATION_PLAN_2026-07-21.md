# Asset Skill Consolidation Plan

**Date:** 2026-07-21
**Scope:** Default-profile Hermes skills under `/home/vdubrov/.hermes/skills`; no other profile may be changed.
**Objective:** one canonical game-asset lifecycle umbrella, a small set of non-overlapping specialists, no lost evidence, no stale unsafe guidance, and verified forwarding for removed duplicates.

## Non-degrading invariants

1. No skill is deleted before its unique procedures, support files, scripts, templates, source citations and current operating evidence are mapped to a surviving authority.
2. Bundled, hub-installed or pinned skills are not deleted. They are retained and cross-referenced if they cannot be absorbed safely.
3. `game-asset-pipeline` owns the source-to-runtime lifecycle and promotion contract; it must not restate complete provider, DCC, format, renderer or specialist-QA manuals.
4. `agentic-blender-production` owns Blender authoring, headless control, functional decomposition, self-critique, rendering, evidence and human review.
5. Provider skills emit candidates only. No generator, DCC bridge, marketing label or engine import is asset authority.
6. Just Dodge canon remains active: no baked runtime combat clips, no procedural/baked fallback motion, no generator-controlled combat truth, no human gate bypass, no full-body generator replacing validated anatomy/rig authority.
7. Version-sensitive evidence lives in references. Stable procedures and routing decisions live in `SKILL.md`.
8. Every removed skill names an existing `absorbed_into` authority so curator/dependency tooling can rewrite references.
9. All subagent reports are proposals until the parent independently reads the exact paths, reruns checks and verifies hashes.

## Canonical ownership map

| Authority | Owns | Explicitly does not own | Disposition |
|---|---|---|---|
| `game-asset-pipeline` | Full game-asset lifecycle: brief/reference, provenance, candidate admission, DCC handoff, class gates, interchange, cook, runtime proof, promotion/human gate | Provider API reference, Blender operation manual, glTF spec, renderer implementation, detailed BVH repair, motion-model internals | Keep and refactor as the class-level umbrella |
| `agentic-blender-production` | Typed/headless Blender control plane, functional/modeling workflow, lookdev, physics/inspection, render/making-of, self-critique, evidence and learning | Provider generation, engine cooker internals, Meshy API | Keep as DCC production specialist |
| `ai-game-content-production` | Current provider/category research, terms/pricing/data posture, capability comparison and evidence-schema design across 2D/3D/audio/NPC/world | Running Meshy/Blender or cooking assets | Keep as research/router specialist |
| `meshy-3d-api` | Complete current Meshy platform/API/MCP capability, costs, request shapes, task lifecycle, printing and provider-side processing | Project-wide DCC/runtime authority | Keep; absorb Meshy duplicates |
| `rust-wgpu-asset-pipeline` | Custom Rust/wgpu loader, binary schema, GPU layouts, converter/runtime debugging and offscreen runtime proof | Asset sourcing, provider selection, DCC artistry | Keep as runtime specialist |
| `gltf-asset-pipeline` | Khronos interchange contract, extensions, validator, PBR packing and glTF cook boundaries | Blender authoring or provider workflows | Keep as interchange specialist |
| `mesh-geometry-qa` | Triangle/BVH geometry findings, posed penetration/clearance, non-destructive repair candidates and efficacy gates | General asset lifecycle | Keep as geometry-QA specialist |
| `meshoptimizer-pipeline` | Cache/overdraw/index/vertex simplification and optimization | Generic validation or creation | Keep as optimization specialist |
| `blender-materials` | Blender Principled/PBR lookdev | Three.js runtime materials | Keep |
| `.agents/materials` | Three.js material loading and runtime surfaces | Blender lookdev | Keep; name collision is domain-specific, not duplication |
| `blender-mcp` | Isolated community BlenderMCP recipes and optional integrations | Production asset authority | Keep as a constrained integration specialist |
| `blender-web-pipeline` | Web/Three.js export optimization | Custom Rust runtime | Keep |
| `skeletal-retargeting`, `combat-motion-teacher-corpus`, `motion-capture-dataset-research`, `ai-motion-inference-engineering` | Motion/rig/data/inference specialist procedures | Generic asset lifecycle | Keep and cross-reference; do not absorb into the asset umbrella |
| `3d-asset-generation-research` | Research methodology for AI 3D producers | Production execution | Keep |
| `3d-model-generation` | each::sense provider-specific generation | General game-asset authority | Keep |

## Planned absorptions

### 1. `meshyai` → `meshy-3d-api`

The enabled entry is a symlink to the external/hub-style
`/home/vdubrov/.agents/skills/meshyai` package, not an agent-created skill
inside the trusted Hermes tree. Do not mutate that source package. Remove or
disable only the default-profile registration with the official skills CLI if
supported; otherwise retain it as an immutable external duplicate and record
that `meshy-3d-api` is authoritative.

Preserve only unique safe details:
- any Three.js `SkeletonUtils`/`fadeToAction` recipe not already owned elsewhere;
- GLB orientation/scale/floor-alignment probes if they are real and portable;
- task metadata sidecar pattern.

Do not preserve these stale/unsafe claims:
- “Meshy is the preferred source for all 3D game assets”;
- “all humanoids must be auto-rigged”;
- prompting users to paste secrets or reading `.env` directly;
- automatic fallback to placeholder/prebuilt/procedural assets;
- “low poly/game ready” prompt language as topology proof;
- automatic optimization through unpinned `npx` dependencies without verification.

### 2. `meshy-api-integration` → `meshy-3d-api`

Absorb the production semantics that are newer and stronger than the generic platform guide:
- retry-versus-regenerate controller;
- component-first measured failures and acceptance ladder;
- exact FBX world-transform/normal cooking;
- measured influence-budget evidence;
- provider reference normalization and monolithic reconstruction gates;
- all six linked references plus the multi-image reference template.

Then delete with `absorbed_into=meshy-3d-api`.

### 3. `blender-dcc-meshy-pipeline` → `game-asset-pipeline`

Split its unique content by authority before deletion:
- producer-router and candidate rules → `game-asset-pipeline` provider-routing reference;
- Meshy request/schema details → `meshy-3d-api`;
- typed DCC setup, isolation and authoring loop → `agentic-blender-production`;
- current local versions/access state → dated control-plane reference, never stable body text;
- all six support references must remain reachable from surviving authorities.

Delete with `absorbed_into=game-asset-pipeline` only after link resolution and representative invocation pass.

### 4. `blender-game-asset-pipeline` → `agentic-blender-production`

Absorb:
- official version/LTS research method;
- Cycles/OptiX qualification;
- glTF/FBX/USD routing;
- baking/color-management/headless rules;
- Blender traceback/exit-code trap;
- both linked evidence files.

Update the surviving control-plane reference from Blender 5.1.2 / DCC 0.19.60 to the live verified Blender 5.2.0 LTS / DCC 0.19.62 state. Delete with `absorbed_into=agentic-blender-production`.

## Skills explicitly retained despite overlap

- `rust-wgpu-asset-pipeline`: its GPU/binary/renderer diagnostics are a distinct executable class. The umbrella must link to it and remove redundant detailed loader tutorials.
- `mesh-geometry-qa`: its triangle-level detection, posed sampling and efficacy logic are not generic validation. Remove the umbrella’s false claim that this skill was already absorbed.
- `gltf-asset-pipeline`: standards authority, not DCC or runtime implementation.
- `meshoptimizer-pipeline`: focused optimization; enhance later rather than duplicate its algorithms.
- `ai-game-content-production`: broader than 3D assets and still useful for current provider research; route production to the asset umbrella.
- `agentic-blender-production`: also covers mechanisms, renders, simulation and filmmaking beyond game assets.
- provider-specific and motion-specific skills: keep narrow and link from decision tables.

## Umbrella rewrite target

`game-asset-pipeline/SKILL.md` becomes a compact operational control plane in this order:

1. When to use / anti-triggers.
2. Authority model and immutable evidence packet.
3. Asset-class decision router.
4. End-to-end stages:
   `brief/reference → candidate → quarantine → DCC → QA → interchange → cook → fresh-runtime proof → human promotion`.
5. Class gates: static prop, modular armor/weapon, deforming character, environment/arena, material/texture, motion-bearing source.
6. Specialist dispatch table with exact skill ownership.
7. Failure/Strike-2 rules.
8. Just Dodge authority addendum.
9. Verification and linked references.

Move long historical Just Dodge narratives and measured receipts into dated references. Remove duplicate tutorials that are already authoritative in provider/DCC/runtime specialist skills. Historical failed approaches remain available as references but must not appear as recommended fallbacks.

## New support files

Under `game-asset-pipeline`:
- `references/asset-skill-ownership-map-2026-07-21.md`
- `references/agentic-game-asset-lifecycle.md`
- `references/ai-3d-x-workflows-2026-07-21.md`
- `references/just-dodge-asset-authority-addendum.md`
- `templates/asset-brief.json`
- `templates/asset-evidence-packet.json`
- `templates/asset-gate-matrix.yaml`

Under `agentic-blender-production`:
- update `references/control-plane.md` for Blender 5.2/DCC 0.19.62;
- add or update the direct-evidence references for `@posi_posi8`, `@hos_giken`, and the current typed-DCC round-trip proof;
- add an arena visual-direction reference after direct-source verification.

Under `meshy-3d-api`:
- copy/absorb the six production references and multi-view template from `meshy-api-integration`;
- add a short routing pointer back to `game-asset-pipeline` for production admission.

## Parallel work packages

Subagents operate on disjoint draft artifacts; none mutate a shared canonical skill concurrently.

- **A — Inventory/authority graph:** every relevant skill, path, origin/protection, trigger, linked files, keep/absorb/delete disposition.
- **B — No-loss migration ledger:** unique paragraphs, commands, evidence, scripts/templates, contradictions and exact source→target mapping.
- **C — Dependency/deletion audit:** references from skills/config/cron/docs, pinned/protected state, broken links, forwarding and rollback.
- **D — Practitioner evidence:** direct X/repository evidence for `@posi_posi8`, `@hos_giken`, `@poistudioltd` and named Grok sources.
- **E — Canon refuter:** identify any guidance that violates Just Dodge no-baked-motion, no-fallback, deterministic-truth or human-gate rules.
- **F — Draft authors:** after A-C converge, create disjoint proposed support files under `/tmp`; parent reviews and writes through `skill_manage`.
- **G — Adversarial verifier:** independently load every survivor, resolve every linked file, test one representative route and search for obsolete names.

## Execution phases

### Phase 0 — Snapshot and rollback

- Record every candidate skill path and SHA-256 tree hash.
- Record `skills_list`, existing linked-file maps, pinned/protected status and references from cron/config/docs.
- Store a local migration manifest outside deleted directories.
- No cross-profile edits.

### Phase 1 — Build authorities before deletion

- Patch surviving skill bodies and metadata first.
- Write/copy support files with `skill_manage`.
- Read back every file.
- Verify no body points to the to-be-removed skill for required content.

### Phase 2 — Remove duplicates

Deletion order:
1. `meshyai` → `meshy-3d-api`.
2. `meshy-api-integration` → `meshy-3d-api`.
3. `blender-game-asset-pipeline` → `agentic-blender-production`.
4. `blender-dcc-meshy-pipeline` → `game-asset-pipeline`.

If a skill is protected or pinned, keep it and replace its body with a concise forwarding/specialist boundary only if editing is allowed; otherwise leave it unchanged and document the immutable duplicate.

### Phase 3 — Repair metadata and references

- Update `related_skills`, tags and descriptions.
- Replace obsolete references to deleted names.
- Remove false “already absorbed” statements where the source still exists.
- Keep old task-specific hashes/receipts in references, not memory or the main skill.
- Patch user-local skills only; never edit other profiles.
- Rewrite `/home/vdubrov/.hermes/skill-bundles/meshy-asset-production.yaml` so
  it loads the surviving authorities (`game-asset-pipeline`, `meshy-3d-api`,
  `agentic-blender-production`, `gltf-asset-pipeline`,
  `skeletal-retargeting`) instead of removed duplicates.

### Phase 4 — Verification

Required checks:

1. `skills_list` shows every survivor and no successfully deleted duplicate.
2. `skill_view` loads each survivor and every linked support file.
3. Search all skill/config/cron/project text for removed names; only explicit “absorbed skill” history may remain.
4. Representative routing probes:
   - “generate Meshy armor candidate” → `game-asset-pipeline` + `meshy-3d-api`;
   - “repair armor penetration” → `game-asset-pipeline` + `mesh-geometry-qa`;
   - “export GLB into Rust/wgpu” → `game-asset-pipeline` + `gltf-asset-pipeline` + `rust-wgpu-asset-pipeline`;
   - “build/render functional Blender asset” → `agentic-blender-production`;
   - “research competing AI content tools” → `ai-game-content-production`.
5. Assert no surviving recommended workflow reads or prints `.env` secrets, enables arbitrary Blender Python as production authority, promotes raw generator output, or allows baked/procedural fallback motion in Just Dodge.
6. Run a focused `/tmp/hermes-verify-...` verifier; label it ad-hoc unless a canonical skill validator exists; remove it afterward.
7. Produce final migration manifest and SHA256SUMS.

## Acceptance criteria

- One canonical source-to-runtime asset umbrella.
- Four planned duplicate skills removed or explicitly retained only because protection prevents removal.
- Every unique support artifact remains reachable.
- No broken relative link.
- No stale Blender 5.1.2/DCC 0.19.60 operating baseline in current control-plane guidance.
- No conflict with Just Dodge live-generative/no-fallback motion canon.
- No secret-handling regression.
- Representative trigger routing is unambiguous.
- Parent independently verifies every subagent artifact and claim.

---

# Default-profile execution record

Executed and ad-hoc verified on 2026-07-21.

## Result

- `game-asset-pipeline` is the canonical lifecycle/router and now owns the
  brief, evidence, gate, provider-routing, practitioner-evidence and absorption
  references.
- `agentic-blender-production` owns the Blender 5.2.0 LTS / DCC 0.19.62
  control plane, Blender ecosystem summary and fail-closed headless exit rule.
- `meshy-3d-api` owns Meshy MCP/provider operations and absorbed the production
  semantics, component cases, FBX normalization, rig cooking, multi-image
  template and external-duplicate disposition.
- `meshyai`, `meshy-api-integration`, `blender-game-asset-pipeline`, and
  `blender-dcc-meshy-pipeline` were removed from the default profile after
  their safe unique procedures were routed or explicitly rejected.
- `gltf-asset-pipeline`, `mesh-geometry-qa`, `rust-wgpu-asset-pipeline`,
  `blender-materials`, `materials`, `blender-web-pipeline`, motion/retarget,
  corpus and provider-research specialists remain separate authorities.
- The `meshy-asset-production` bundle now contains only surviving skills and
  reloads successfully.

## Verification

The focused disposable verifier returned:

```json
{"bundle":"meshy-asset-production","profile_copies_untouched":4,"removed_default":4,"schema":"asset-skill-consolidation-verify-v1","status":"PASS","survivors":6}
```

It parsed JSON/YAML, AST-parsed survivor Python, ran six typed-DCC wrapper
tests, ran the live Blender DCC preflight, tested Blender-DCC and Meshy MCP,
exercised the retained GLB scanner on the real round-trip smoke artifact,
validated the bundle, verified toolchain evidence hashes and removed its
temporary files. This is ad-hoc verification, not a repository-wide suite.

Evidence:

- `.temp/verification/asset-skill-consolidation-2026-07-21/pre-migration.json`
- `.temp/verification/asset-skill-consolidation-2026-07-21/post-migration.json`
- `.temp/verification/asset-skill-consolidation-2026-07-21/SHA256SUMS`
- Curator rollback snapshot:
  `/home/vdubrov/.hermes/skills/.curator_backups/2026-07-21T05-13-45Z`

## Cross-profile boundary

Four profile-local copies of the older asset skills still exist. They were not
modified because this plan's explicit scope is the active default profile and
cross-profile skill/config mutation requires the user to name those profiles.
They are not evidence that the default consolidation failed; they are a
separate authorized migration unit if the user expands scope.
