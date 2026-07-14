# Just Dodge — Development Task List

Branch: `main`, based on clean-checkout gate revision `f41cde635c607b33bbf04c2dd4621222359df73f`; one worktree.
Last updated: 2026-07-14
Active implementation unit: `PVP-005-ADMITTED-THREE-ACTION-MOTION`.
Current mechanical blockers: bind-pose runtime, no admitted readable Strike/Block/Grab source set, action-authored rather than pose-derived cleanbox geometry, independent weapon transform, Replay-footer overlap, no calibrated camera/readability evidence, and no canonical packaged human-play evidence. PVP-004 closed the reproducible local package and automated OS input-path gates; it did not establish five human matches or public redistribution rights.

The Phase A/B tables below preserve detailed task history. The controlling PLAYABLE-PROOF order is now: reconcile → clean-checkout gates → full runtime flow → packaged interaction/cadence proof → admitted motion plans → coupled articulated physics → pose/socket contact → camera/readability → truth-driven presentation → human/package evidence.

---

## Phase A — Hygiene (stabilize the branch before new work)

| ID | Task | Files | Work | Acceptance | Depends |
|---|---|---|---|---|---|
| A.0 | Commit armored-duelist integration | `src/renderer.rs`, `src/main.rs`, `src/bin/shot.rs`, `src/m3_cleanbox.rs`, `src/milestone3.rs`, `src/action_matrix.rs`, `src/lib.rs`, `src/cleanbox.rs`, `assets/source/meshy/c0_armored_duelist_001/`, `qa_runs/m3_contact_truth_001/*` | Stage all contact-truth and model changes. Delete stale `qa_runs/bind_pose_*` noise. | `git status --short` clean; only reviewed evidence remains. | — |
| A.1 | Update project status reports | `docs/reports/TERRA_AGENTIC_BUILD.md`, `docs/reports/MILESTONE_03_FIRST_PLAYABLE_REPORT.md`, `README.md`, `CHANGELOG.md`, `docs/MILESTONES.md` | Replace nude-carrier references with armored-duelist evidence. Record new SHA-256 hashes. | Reports reflect current state; no stale language. | A.0 |
| A.2 | Record final ad-hoc verification | `/tmp/hermes-verify-final-*.sh`, `qa_runs/m3_contact_truth_001/armored_final_ad_hoc.log` | Run `cargo check --all-targets`, `cargo test --lib`, `cargo run --bin shot`, `cargo fmt --check`, `git diff --check`. Remove script. | Exit 0, `AD_HOC_FINAL_PASS`. | A.0 |

---

## Phase B — Core Gameplay Loop (M3 First Playable critical path)

### B.1 — Motion

Current status at `2677b4a` (2026-07-14): B.1.1 request isolation, fail-closed source/cache loading, numeric G1→24-bone transport, post-Reveal ARDY feasibility, quantized plan/replan packets, MotionBricks receipts, official G1 articulation data, integer hinge projection, and independent-joint tracking exist and are tested in isolation. The former Hugging Face authorization failure is historical. Runtime promotion remains blocked because `App::current_pose()` returns bind matrices, no complete three-action source has passed the first-eight-frame semantic gate, MotionBricks completion is not live, and the active-ragdoll core is not yet a coupled articulated/contact world.

| ID | Task | Files | Work | Acceptance | Depends |
|---|---|---|---|---|---|
| B.1.1 | M3-MOTION-CONTRACT — Motion request contract | `src/main.rs`, `src/milestone3.rs`, `src/motion.rs`, `src/motion_service.rs` | Define `MotionRequest` from public `m3::Snapshot` state (action, side, phase, phase frame, injury modifiers, deterministic request ID). Hidden Plan intent must not reach motion generation before Reveal. | Same replay yields identical request sequence. Hidden-intent isolation test. Motion request generation cannot alter truth hash. | A.* |
| B.1.2 | M3-MOTION-LOAD — MotionBricks runtime adapter | `src/motion.rs`, `src/motion_service.rs`, `src/main.rs` | Load ONNX/NPY artifacts at runtime. Generate G1 pose frames for Strike, Block, Grab. Fail closed if artifacts missing/invalid. No silent fallback to bind pose in Player mode. | Valid finite G1 matrices for all three actions. Missing assets fail clearly before match start. Per-action inference timing ≤16 ms. | B.1.1 |
| B.1.3 | M3-MOTION-RETARGET — Retarget to armored 24-bone C0 | `src/motion_retarget.rs`, `src/asset.rs`, `src/motion_runtime.rs`, `src/bin/shot.rs` | Create 24-bone MotionBricks-to-armored-duelist mapping and standardized QA rendering. Keep `App::current_pose()` bind-pose output until B.1.4 accepts a semantic source. Verify root alignment, bone orientation, weapon-hand socket. | Numeric transport passes: finite positive-determinant matrices, no collapse/inversion, deterministic pose receipts, bind regression valid. Runtime promotion remains gated on B.1.4. | B.1.2 |
| B.1.4 | M3-MOTION-TELLS — Motion readability gate | `src/bin/shot.rs`, new motion QA tool/report | Capture standardized reveal-frame strips per action. Define first-six/eight-frame visual tells. Review camera-visible silhouette and weapon motion. | Strike, Block, Grab visually distinguishable before contact. No action accepted merely because it deforms. Evidence images and frame metadata recorded. | B.1.3 |
| B.1.4a | M3-MOTION-SOURCE — Neural combat-source admission | `tools/kimodo_generate.py`, `tools/encode_primitives.py`, `assets/data/primitives.ron`, source QA reports | Generate provenance-captured G1 candidates for Strike/Block/Grab, select by source and retarget visual gates, then encode only admitted candidates. | At least eight readable reveal frames/action, visible weapon/hand intent where applicable, G1 continuity/topology pass, 24-bone QA pass. The former authorization blocker was cleared by B14Z; no complete three-action source set is admitted. | B.1.4 |
| B.1.5 | M3-MOTION-WEAPON — Weapon socket attachment | `src/renderer.rs`, `src/main.rs`, `src/hitbox.rs` | Attach W0 sword to deterministic hand/socket transforms from retargeted C0 pose instead of first-person-only placement. | Sword transform follows retargeted hand. Weapon arc, visible model, hand socket, and contact proxy agree. | B.1.3 |
| B.1.6 | M3-MOTION-PERF — MotionBricks performance budget | `src/telemetry.rs`, `src/motion.rs`, `src/main.rs` | Measure inference, retarget, and skin upload costs. | Motion generation ≤16 ms/action worst acceptable. Retarget + skin upload ≤12 ms/frame. | B.1.3 |

### B.2 — Contact Parity

| ID | Task | Files | Work | Acceptance | Depends |
|---|---|---|---|---|---|
| B.2.1 | M3-CONTACT-PROXIES — Pose-derived body/weapon/guard proxies | `src/m3_cleanbox.rs`, `src/hitbox.rs`, `src/duel_physics.rs`, `src/main.rs` | Derive body/guard/weapon proxies from retargeted poses and weapon socket. Replace action-label-derived proxy placement. | Visible weapon/body overlap → matching contact packet. Visible miss → Whiff. Visible guard intercept → Guard. | B.1.3 |
| B.2.2 | M3-CONTACT-CLEANBOX — Two 120 Hz substeps per 60 Hz tick | `src/m3_cleanbox.rs`, `src/cleanbox.rs`, `src/milestone3.rs` | Feed two 120 Hz pose-derived cleanbox substeps into one 60 Hz Resolve `PhysicalContactBatch`. Contact packets remain frame-exact and single-use. | Guard outranks equal-time body contact. Deterministic replay reconstruction. | B.2.1 |
| B.2.3 | M3-CONTACT-REGRESSION — Contact parity regression suite | `src/m3_cleanbox.rs`, `src/milestone3.rs`, new fixtures | Add strike-vs-block, strike-vs-grab, grab-vs-block, no-contact fixtures. Exercise all outcomes from real pose-derived proxy geometry. | 30/60/144 Hz render cadence → identical truth and replay hashes. 100 replay reconstructions stable. No synthetic action-table results. | B.2.1 |
| B.2.4 | M3-CONTACT-WEAPON — Weapon visual/contact alignment | `src/renderer.rs`, `src/main.rs`, `src/hitbox.rs` | Attach W0 sword visually to same hand/socket used for physical proxy extraction. Remove independent first-person visual weapon positioning where it contradicts contact geometry. | Screenshot overlay shows sword visual and weapon proxy share transform. Contact tip/edge positions match visible weapon within tolerance. | B.2.1 |

### B.3 — Camera and Readability

| ID | Task | Files | Work | Acceptance | Depends |
|---|---|---|---|---|---|
| B.3.1 | M3-CAMERA-CONTRACT — Player camera contract | `src/main.rs`, `src/renderer.rs`, `src/ui.rs` | Formalize Player, Replay, Presentation, Developer camera modes. Frame opponent torso, weapon, action tell during Reveal. Remove developer-only behavior from Player mode. | Opponent weapon/upper body visible during reveal. Camera consumes only snapshots/pose keypoints. No truth mutation. Debug overlay disabled in Player mode. | B.1.4 |
| B.3.2 | M3-CAMERA-PLAYTEST — Action-read playtest | QA script/report, captured frame sequences | Blind-test action identification from reveal frames. Compare first-person framing against readable alternative if needed. | ≥80% action-read rate before contact, or canon-approved camera revision. | B.3.1 |

### B.4 — Audio

| ID | Task | Files | Work | Acceptance | Depends |
|---|---|---|---|---|---|
| B.4.1 | M3-AUDIO-BACKEND — Audio backend spike | `Cargo.toml`, new `src/audio.rs`, test harness | Evaluate `rodio` vs `kira` against Linux/PipeWire availability, latency, deterministic event dispatch, packaging. Pick one. | Minimal cue plays without delaying simulation. Latency and device-failure behavior documented. | — |
| B.4.2 | M3-AUDIO-CUES — Deterministic cue dispatcher | `src/audio.rs`, `src/main.rs`, `src/milestone3.rs` | Emit presentation-only cues from public phase/contact/consequence transitions. Cue types: plan/commit, reveal, wind-up, guard, hit, whiff, injury, terminal, restart. | Cue event sequence is replay-auditable. Audio never mutates truth. Missing audio device fails open to silence. | B.4.1, B.2.2 |
| B.4.3 | M3-AUDIO-REPLAY — Audio cue replay evidence | `src/audio.rs`, `src/milestone3.rs`, `src/bin/m3_match.rs` | Record audio cue receipts by truth frame. Prove cue sequence replays identically. | Same replay → identical audio cue log. | B.4.2 |

### B.5 — Player Loop

| ID | Task | Files | Work | Acceptance | Depends |
|---|---|---|---|---|---|
| B.5.1 | M3-UI-PLAYER — Complete hidden-choice loop | `src/input.rs`, `src/ui.rs`, `src/main.rs` | Make Plan selection, Commit confirmation, Reveal, outcome, injury, result, restart states player-readable. Hidden action remains hidden until Reveal. Remove placeholder/debug terminology. | Full match understood without terminal telemetry. UI public state matches immutable M3 snapshot. UI cannot expose opponent choice during Plan. | B.1.4 |
| B.5.2 | M3-INPUT-PLAYER — Finalize player input | `src/input.rs`, `src/main.rs`, `docs/design/PRD_INPUT.md` | Keyboard/controller input for selection, commit, restart, pause. Replay-safe hidden intent. | Input isolation test. No input leak into truth before Reveal. | B.5.1 |
| B.5.3 | M3-AI-PUBLIC — AI upgrade | `src/ai.rs`, `src/milestone3.rs` | Use only public revealed history and tunable difficulty. Cannot inspect hidden player intent. | AI passes intent-isolation contract test. Difficulty tunable. | B.5.1 |
| B.5.4 | M3-LOCAL — Local human-vs-human mode | `src/input.rs`, `src/main.rs`, `src/ui.rs`, `src/milestone3.rs` | Support local two-player hidden commitment. Make AI optional. | Both players commit without observing the other's selection. Replay replays identically. | B.5.1 |
| B.5.5 | M3-PLAYER-LOOP — Complete launch-to-restart flow | `src/main.rs`, `src/ui.rs`, `src/input.rs` | Separate Player/Developer/Presentation modes. Selection → commit → reveal → consequence → terminal → restart. AI hidden-intent isolation. | Five real keyboard/mouse packaged matches from launch through restart. Each saves a replay; replay reconstructs final hash. No debug overlay in Player mode. | B.5.1–B.5.4 |

### B.6 — Presentation

| ID | Task | Files | Work | Acceptance | Depends |
|---|---|---|---|---|---|
| B.6.1 | RENDER-PBR-MATERIAL — Material import contract | `tools/extract_fbx_skinned.py`, `src/asset.rs`, `src/renderer.rs`, `src/skin.wgsl` | Preserve material references through asset cooking. Define base-color, normal, metallic-roughness, emissive, texture-color-space semantics. Stop relying on raw generated PBR maps without shader support. | Asset cooker emits material manifest with source hashes. Missing maps use deliberate neutral defaults. Renderer logs exact material assets. | — (parallel) |
| B.6.2 | RENDER-PBR-SHADER — Skin shader PBR implementation | `src/skin.wgsl`, `src/renderer.rs` | Add tangent-space normal mapping if tangent generation available. Add metallic/roughness lighting and readable key/fill/rim lighting. Preserve skinned vertex performance budget. | Engine front/side/duel render materially comparable to Blender reference. No mottled baked-light artifact. GPU timing captured. | B.6.1 |
| B.6.3 | RENDER-LIGHTING — Duel readability lighting | `src/renderer.rs`, arena asset config | Add lighting that separates dark armor, weapon, floor, background. Key/fill/rim lighting and color-management baseline. | Armor silhouette and action posture visible in first-person capture. No crushed-black opponent or weapon. | B.6.2 |
| B.6.4 | RENDER-CHARACTER-QA — Character asset quality gate | character source manifests, `tools/verify_skinned_bin.py`, `src/bin/shot.rs` | Formal geometry, UV, texture, rig, pose, scale, visible-defect checks. Reject generated assets with asymmetry, floating components, missing hands, unexpected props, invalid rigging. | Every runtime character has source task ID, hashes, rig report, bind render, engine render. No generated model promoted solely because it compiles. | — (parallel) |
| B.6.5 | RENDER-WEAPON — W0 sword integration | `src/renderer.rs`, weapon asset manifests, `src/main.rs` | Bind sword to character hand in opponent and player views. Drive sword transform from pose, not separate fixed camera model. | Sword arc, visible model, hand socket, contact proxy agree. First-person and opponent views show correct scale and orientation. | B.2.4 |

---

## Phase C — Engine Foundation

| ID | Task | Files | Work | Acceptance | Depends |
|---|---|---|---|---|---|
| C.1 | ENGINE-MODE — Runtime mode isolation | new `src/runtime_mode.rs`, `src/main.rs`, `src/ui.rs`, `src/renderer.rs` | Define Player, Developer, Replay, Presentation modes. Gate debug overlays, asset overrides, test autoplay, telemetry verbosity, camera behavior. | Player mode cannot enable unsafe override/debug paths. Replay/Presentation mode cannot write combat truth. Mode-specific tests. | B.5.5 |
| C.2 | ENGINE-ASSET — Asset cooker reproducibility | `tools/extract_fbx_skinned.py`, `tools/verify_skinned_bin.py`, manifests | Make source GLB/FBX → cooked SKM1 conversion reproducible with explicit version/tool metadata. Emit manifests for mesh, textures, skeleton, materials, hashes, source task, cook command. | Clean checkout can regenerate byte-identical or structurally equivalent cooked asset. Cooker validates indices, normals, UVs, joints, weights, bone hierarchy, texture paths. | — (parallel) |
| C.3 | ENGINE-SKM2 — Next skinned mesh format | `src/asset.rs`, `tools/extract_fbx_skinned.py` | Design SKM2 for material slots, texture paths, tangents, bounds, skeleton metadata. | Backward-compatible with SKM1. New format supports PBR material contract. | C.2 |
| C.4 | ENGINE-INPUT — Input abstraction | `src/input.rs`, `src/main.rs`, `docs/design/PRD_INPUT.md` | Keyboard/mouse + gamepad support. Rebindable keys. Deterministic input recording. | Remap persists. Input→present latency recorded. No truth change. | B.5.2 |
| C.5 | ENGINE-REPLAY — Replay schema/version policy | `src/milestone3.rs`, `src/bin/m3_match.rs`, replay docs | Add replay schema version and compatibility policy. Record physical-contact batches, action inputs, seed, asset/content version, presentation receipt version separately. | Old incompatible replays fail with clear version message. Canonical truth replay isolated from presentation asset revisions. | B.5.5 |
| C.6 | ENGINE-TELEMETRY — Performance and truth telemetry | `src/telemetry.rs`, `src/main.rs`, renderer/motion timing hooks | Record truth tick, input timestamp, phase, contact packet ID, replay hash, inference duration, skin upload duration, render duration. | Telemetry proves no skipped 60 Hz truth ticks. Optional, no truth effect. Machine-readable reports. | B.1.6 |
| C.7 | ENGINE-PLATFORM — Linux/X11/Wayland support matrix | package scripts, CI/docs, QA tools | Test native Wayland, forced X11, PipeWire audio, keyboard/mouse focus, capture, package launch. | Supported runtime matrix documented with pass/fail evidence. Player input works without automation tooling. | B.5.5 |
| C.8 | ENGINE-PERF — Frame-time budgets | telemetry/profiling reports | Establish CPU/GPU/inference/skin-upload targets for RTX 5090 and Steam-Deck-class hardware. | 60 Hz truth remains fixed. Measured frame pacing, memory, latency meet declared budgets. | B.1.6, B.6.2 |
| C.9 | ENGINE-ERRORS — Fail-closed diagnostics | `src/main.rs`, `src/renderer.rs`, `src/asset.rs` | Replace panics in player-facing loaders with fail-closed diagnostics, clear error screens, QA logs. | Missing asset/device produces a readable error, not a panic/crash. | — (parallel) |
| C.10 | ENGINE-PACKAGE — Reproducible package pipeline | `dist/`, package scripts, CI | Build release package from clean worktree. Verify hashes, startup, assets, replay runner, dependency diagnostics outside repository. | Package launches from clean directory. Replay verification works with packaged `m3_match`. No repository-relative asset dependency. | B.5.5, C.2 |

---

## Phase D — Content and Assets

| ID | Task | Files | Work | Acceptance | Depends |
|---|---|---|---|---|---|
| D.1 | CONTENT-CHAR — Character roster | `assets/source/meshy/`, `src/renderer.rs`, `src/asset.rs`, `src/retarget.rs` | Import 2–3 additional armored duelists via GLB→FBX→SKM1 cook. Rig-conform to 24-bone carrier. Selectable in UI. | Each character loads with valid SKM1 + PBR. Retarget produces finite matrices. Selection does not alter truth. | B.6.4, C.2 |
| D.2 | CONTENT-WEAPON — Weapon profile system | `src/renderer.rs`, `assets/data/`, `docs/design/PRD_MOTION.md` | Data-driven weapon length/grip/mass profiles. Socket transform from hand joint. W0 variants. | Weapon transform follows retargeted hand. Mass feeds motion request only. | B.1.5, B.6.5 |
| D.3 | CONTENT-ARENA — Arena variants + lighting | `src/renderer.rs`, `assets/source/meshy/e0_arena_threshold/` | 2–3 arena layouts with distinct lighting. Keep deterministic truth. | Arena swap is data-only. No truth coupling. PBR contract holds. | B.6.3, C.2 |
| D.4 | CONTENT-MOTION — MotionBricks source clips per action | `assets/motion/`, `src/motion.rs` | One validated clip per action: Strike, Block, Grab at minimum. Hip drive, weapon arc, readable tell. | Per-clip QA report + video frames. | B.1.4 |
| D.5 | CONTENT-AUDIO — Audio assets | `assets/audio/`, `src/audio.rs` | Wind-up, contact, material, UI, ambient cues. Mixed at consistent levels. | Audio event log + mixed sample. | B.4.2 |
| D.6 | CONTENT-VFX — Hit feedback, impact, readability VFX | `src/renderer.rs`, `src/skin.wgsl`, new `src/vfx.rs` | Spark/impact/debris at contact keypoint. Guard-flash. Whiff wind. Presentation-only. | VFX spawns only from truth contact events. Zero truth mutation. GPU budget measured. | B.2.1, B.6.2 |

---

## Phase E — QA and Evidence

| ID | Task | Files | Work | Acceptance | Depends |
|---|---|---|---|---|---|
| E.1 | QA-REPLAY-SOAK — Extended replay determinism | `src/bin/m3_match.rs`, CI | Expand replay soak beyond 100 reconstructions. Include contact-driven pose-derived packets. | Truth hash stable across soak. | B.2.3 |
| E.2 | QA-HUMAN-MATCHES — Five real matches | `qa_runs/`, replay files, reports | Run five human keyboard/mouse packaged matches. Save replays and verify each independently. | Five launch-to-result-to-restart runs. Inputs visible in telemetry/replay. Hashes verified. | B.5.5 |
| E.3 | QA-MEDIA — Canonical gameplay media | `docs/media/latest/`, `tools/verify_latest_media.py` | Capture rendering overview, continuous gameplay MP4, manifest, source commit, hashes, truth hash list, known defects, acceptance status. | `python3 tools/verify_latest_media.py` passes fail-closed. Media current relative to presentation-affecting changes. | E.2 |
| E.4 | QA-VISUAL — Recurring visual QA | `tools/verify_latest_media.py`, `vision_analyze` | Checklist for model integrity, lighting, occlusion, weapon readability, T-pose regressions, material artifacts. Every presentation-affecting change has a screenshot. | No mesh explosion, missing texture, or regression. | — (ongoing) |
| E.5 | QA-PLATFORM — Cross-platform smoke | CI, package scripts | Linux packaged smoke now. Windows/macOS smoke once packaging is portable. | Package launches outside repo on target OS. | C.7, C.10 |
| E.6 | QA-RIGHTS — Distribution-rights closure | asset manifests, `docs/reports/ASSET_PROVENANCE_M3.md`, package manifest | Every shipped asset maps to license/terms, source, task ID, hash. Replace or exclude assets without adequate rights. | Package can truthfully be described as distributable. | — (parallel) |
| E.7 | CI — Maintain warning-clean deterministic CI | `.github/workflows/ci.yml` | Formatting, warning-denying all-target build/tests, replay soak, cooked-asset validation, media-manifest verification. | CI fails on any warning, replay regression, invalid cooked asset, or stale/invalid media manifest. | — (ongoing) |
| E.8 | QA-MOTION-FLAKE — Stabilize primitive rigidity gate | `tests/motion_service_integration.rs`, `motionbricks_service/` | Reproduce and eliminate the transient `all_top_primitives_are_present_and_rigid` segment-length failure without weakening geometry tolerance. Persist per-action/frame/joint diagnostics and isolate any Python-service state leakage. | Ten consecutive full integration runs pass; diagnostic receipt identifies exact action/frame/joint if a regression occurs. | — (parallel) |

---

## Phase F — Depth and Expansion (post 3-action slice)

| ID | Task | Files | Work | Acceptance | Depends |
|---|---|---|---|---|---|
| F.1 | GAME-ACTION-SCHEMA — Lock expanded action/stance schema | canon amendment, `assets/data/action_matrix.ron`, PRDs | Decide exact next actions, stance data, weapon assumptions, timing windows, expected counterplay. | Canon, matrix, animation, contact, audio, UI requirements agree. No action added as isolated resolver row. | B.5.5 |
| F.2 | GAME-ACTION-PIPELINE — Add actions vertically, one at a time | `src/milestone3.rs`, `src/motion.rs`, `src/m3_cleanbox.rs`, replay | Per action: truth rule + deterministic tests, MotionBricks request + readable tell, pose-derived contact parity, audio/VFX/UI feedback, replay + determinism fixtures. | Each action satisfies all five layers before next begins. | F.1 |
| F.3 | GAME-INJURY — Tactical injury slice | `src/injury.rs`, `src/milestone3.rs`, UI/motion request contract | One localized injury that visibly affects capability and decision-making. | Deterministic, replay-stable, visible, tactically meaningful. | B.2.2, B.4.2 |
| F.4 | GAME-ARMOR — One armor-material slice | `src/armor.rs`, `src/milestone3.rs`, materials/audio | One material interaction through hit, damage reduction, sound, visible result, replay. | Armor changes gameplay and feedback coherently, not just damage numbers. | F.3, B.6.2 |
| F.5 | GAME-DEEPSIM — Deepen shared duel physics | `src/duel_physics.rs`, `src/cleanbox.rs`, `src/hitbox.rs`, `src/milestone3.rs` | Promote 120 Hz cleanbox from contact-only to sustained force/impulse accumulation, stagger, knockback. Anatomical region routing for injury. | Contact impulses reproducible from same pose+timing seed. No truth-hash change from presentation. Deep-sim replay reconstructs identically at 30/60/144 Hz. | B.2.2 |
| F.6 | GAME-TUTORIAL — First-time player onboarding | `src/ui.rs`, `src/main.rs`, new `src/tutorial.rs` | Scripted commit/reveal/read loop. Opponent-tell callouts. Restart literacy. Gate behind first launch only. | New player reaches completed match without external help. No debug overlay. Truth untouched. | B.5.5, B.3.1 |
| F.7 | GAME-BALANCE — Balance data + tuning harness | `assets/data/action_matrix.ron`, `src/milestone3.rs`, `tools/` | Externalize timing/injury/armor numbers. Headless balance sweep over `m3_match` seeds. | Balance change does not require code edit. Sweep report is deterministic. | F.2, F.3 |
| F.8 | GAME-FIGHTFILM — Replay viewer + fight-film camera | `src/main.rs`, `src/renderer.rs`, `src/ui.rs` | Deterministic replay camera with manual orbit/step and cinematic cut grammar from replay events. | Replay camera reproduces match from truth+contact events only. No truth write. | C.1, B.5.5 |
| F.9 | GAME-NETCODE — Deterministic rollback netcode | `src/milestone3.rs`, `src/input.rs`, new `src/net.rs` | Lockstep/seeded-rollback over existing truth core. Input-only network path. Peer replay verification. | Two processes reach identical truth hash from exchanged inputs. Rollback restores exact state. | B.5.5, F.2 |

---

## Phase G — Live Ops and Polish

| ID | Task | Files | Work | Acceptance | Depends |
|---|---|---|---|---|---|
| G.1 | OPS-UI — Menus, HUD, settings, accessibility | `src/ui.rs`, `src/main.rs`, new `src/menu.rs` | Title, mode select, pause, HUD with phase/action/consequence, settings panel, colorblind/audio-subtitle options. | Player mode shows no placeholder/debug. HUD reads from snapshot only. | C.1, B.5.5 |
| G.2 | OPS-SETTINGS — Persistent settings/save | new `src/settings.rs`, `src/main.rs`, `src/ui.rs` | Serialize control, video, audio, accessibility prefs. Load on boot. | Settings survive restart. No truth coupling. | G.1, B.4.2 |
| G.3 | OPS-LOCALIZATION — i18n + accessible text | `src/ui.rs`, `assets/`, `docs/` | String table, RTL/scale support, subtitle-for-audio option. | All player-facing strings externalized. Subtitle toggle works with audio. | G.1, B.4.2 |
| G.4 | OPS-CROSSPLAT — Windows/macOS packaging | `dist/`, `Cargo.toml`, CI | Cross-compile release, sign/notarize, include MotionBricks artifacts. | Package runs outside repo on target OS. Replay hash matches Linux. | C.10, C.2 |
| G.5 | OPS-LAUNCH — Launch ops cadence | `docs/`, CI, `CHANGELOG.md` | Replay-compatible patch policy, crash log collection, content updates only after regression. | Patch preserves deep-sim replay compatibility. No truth-hash regression. | C.10, C.5, F.9 |

---

## Dependency Summary

```
A.* → B.1.1 → B.1.2 → B.1.3 → B.1.4 → B.1.5 → B.1.6
                                    ↓
                               B.2.1 → B.2.2 → B.2.3 → B.2.4
                                    ↓
                               B.3.1 → B.3.2
                                    ↓
                          B.4.1 → B.4.2 → B.4.3
                                    ↓
                          B.5.1 → B.5.2 → B.5.3 → B.5.4 → B.5.5
                                    ↓
                               C.1  C.5  C.7  C.10
                                    ↓
                               E.2 → E.3
                                    ↓
                          F.1 → F.2 → F.3 → F.4 → F.5 → F.6 → F.7 → F.8 → F.9
                                    ↓
                          G.1 → G.2 → G.3 → G.4 → G.5

Parallel (no truth risk, can run alongside B.1–B.5):
  B.6.1 → B.6.2 → B.6.3
  B.6.4  B.6.5
  C.2 → C.3  C.9
  E.6  E.7
  D.4  D.5
```

**Current unit: PVP-005-ADMITTED-THREE-ACTION-MOTION.** PVP-004 now builds two byte-identical local packages, validates complete SHA-256 coverage, reconstructs packaged replay truth, launches outside the repo cwd, and exercises the actual OS input event path through Replay/rematch/menu/quit. Admit readable, provenance-recorded Strike/Block/Grab source motion before any live-pose promotion; five human packaged matches remain a later gate.
