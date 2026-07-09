# Frontier Techniques for Just Dodge — Consolidated Research Synthesis

**Purpose:** Ground the deep-simulation subsystems (motion, cloth/leather, chainmail, plate-FEM, brittle fracture, tissue injury, determinism, hitbox parity, camera, AI) in frontier 2023–2026 primary research, reconciled against `docs/design/GAME_CANON.md` and the repo's actual constraints (Rust 2024 + wgpu 30 + winit 0.30 + glam 0.28 + ONNX Runtime 2.0/ort with CUDA; 60 Hz deterministic combat truth; stable truth hash; presentation-isolated; MotionBricks is the sole motion engine; no motion fallbacks; hitbox parity mandatory).

**Governing authorities:**
- `docs/design/GAME_CANON.md` — locked canon; "no fidelity compromises or fallbacks due to resource limitations." MotionBricks is the sole motion engine; prebaked clips/motion fallbacks disallowed; hitbox parity mandatory; truth isolation absolute.
- `docs/design/ROADMAP.md` (phased) + `docs/PHASED-PRODUCTION-PLAN.md` — Phase 1 (playable loop + hitbox parity), Phase 2 (deterministic deep-sim foundation), Phase 4 (readability), Phase 5 (deep injury/armor), Phase 9 (rollback after local fun).
- Existing PRDs under `docs/design/PRD_*.md`.

**Structure of this doc:** per subsystem → recommended frontier approach → how it satisfies canon/constraints → concrete risks → single most-likely failure mode → key citations. Full per-track reports:
- `docs/MOTION-GENERATION-RESEARCH-REVIEW.md` (motion)
- `research_armor_fem_fracture.md` (plate-FEM + fracture)
- `docs/research/DEEP_LOCALIZED_INJURY_RESEARCH_REVIEW.md` (tissue injury)
- `docs/reports/FRONTIER_TECHNIQUES_RESEARCH_REVIEW.md` (determinism/hitbox/camera/AI)
- `docs/research/CLOTH_CHAINMAIL_RESEARCH_REVIEW.md` (cloth/leather + chainmail — pending re-dispatch)

---

## 0. Cross-Cutting Determinism Contract (applies to every subsystem)

The single architectural invariant that makes all deep simulation tractable: **combat truth is deterministic, serializable, and never written to by presentation.** Everything below is downstream of this.

Hard rules (from the determinism/hitbox/camera/AI track, cross-checked against GAME_CANON):
1. **Fixed timestep:** 60 Hz only; render interpolates between snapshots. Variable `dt` is forbidden in truth.
2. **Controlled float now, fixed-point option later:** `f32` is locally deterministic on one build/OS/CPU. Cross-platform parity requires `libm`/`nalgebra` transcendental substitution, no `-ffast-math`, no FMA reordering, `BTreeMap`/`IndexMap` instead of `HashMap` in truth paths. Build a fixed-point (`Q32.32`/fixed-int) drop-in for truth math before cross-platform replay/rollback.
3. **One seeded deterministic RNG** whose state is part of truth; no `rand::random()`, no `SystemTime`, no pointer addresses in truth.
4. **Truth hash** over compact `bincode` LE serialization every frame/checkpoint (FNV-1a or xxHash, fixed seed). This is the regression gate for every subsystem.
5. **GPU compute only for per-element math; truth-critical solve/accumulation stays CPU.** WGSL float atomics and workgroup scheduling are non-deterministic bit-for-bit; do global solves and force reductions on CPU.
6. **Presentation bridge is one-way.** Motion, camera, VFX, audio read immutable `TruthSnapshot`; they never feed back. Any subsystem that needs "style" must read *committed* truth (action/stance/injury/armor ROM), never hidden intent.
7. **Rollback-ready input abstraction now:** `enum InputSource { HumanLocal | AI | Replay | NetworkRemote | TestAgent }` with frame-stamped `InputEvent`. Remote injection requires no later refactor.

**Recommended rollback library when Phase 9 arrives:** Fortress Rollback (Rust, `BTreeMap` determinism, TLA+/Kani/Z3 verified) or backroll-rs (GGPO-style). State snapshots must be compact contiguous byte buffers for <1 ms save/restore.

**Cross-subsystem single most-likely failure mode:** a hidden non-determinism source (HashMap iteration, system RNG, `Instant`, float transcendental) enters truth and diverges the hash → replay/desync. Mitigation: treat determinism as a hard boundary + a `SyncTestSession`-style self-check that rolls back every frame and compares hashes.

---

## 1. Motion — MotionBricks as sole engine (canon-locked)

**Recommended approach:** MotionBricks (Wang et al., SIGGRAPH 2026, arXiv 2604.24833; NVIDIA GEAR/GR00T Whole-Body Control).

- **What it is:** modular latent generative model + "smart primitives." 34-joint G1 representation (29 actuated hinge DOFs + 2 dummy toes + free pelvis); 418-dim per-frame (414 shared body in world frame + root features). Multi-head VQ-VAE tokenizer + autoregressive pose/root modules. **Not diffusion** — single forward pass per replan, 2 ms latency / 15,000 FPS reported. Trained on 350k mocap clips; BONES-SEED open subset (~140k).
- **Conditioning:** keyframe-driven, not action-labeled. Just Dodge combat layer translates `action_id` → keyframe packet (target pose + root trajectory). Weapon/stance → target keyframes + root style bias. Injury/armor ROM → applied *after* decode on the retargeted skeleton (MotionBricks has no per-DOF ROM channel). First-6-frame tell → author τ=0 hard-constrained keyframes indexed by `(action, stance, weapon, injury_level)`.
- **Why not alternatives:** diffusion (MDM/MotionGPT/MotionLCM/MMM) too slow or not keyframe-action-conditioned for melee; motion matching (For Honor/Ubisoft, Learned MM, Lipschitz MM) is deterministic and For-Honor-fidelity but violates the no-fallback canon if used as primary; physics (DeepMimic/AMP/PFNN/SCONE) mutates character state → only cosmetic; SOTA humanoid (SONIC/ExBody2) are robot policies, not cinematic generators. MotionBricks is the only published method meeting latency + no-fallback + keyframe control.

**Retargeting (local-space, per RETARGETING-PLAN.md r5):**
- 34-joint G1 world → ~120-bone mannequin via parent-relative local-space mapping (avoids shear/scaling from world-space lerp).
- Spine: spline interpolation across the 3-anchor G1 spine to ~19 mannequin vertebrae (slerp rotations, lerp root-relative positions).
- Fingers/toes: procedural IK (MotionBricks has none). This is the highest animation-quality risk for a first-person melee game (hands/blades prominent).
- Injury/armor ROM: clamps applied post-decode.
- Skin matrices: Dual-Quaternion Skinning (Kavan et al. 2007) on GPU; CPU-side copy for hitbox extraction so render and hitbox share identical pose.

**Hitbox parity (mandatory):** analytical bone-attached proxies (capsules/OBBs) transformed by the same world skin matrices used for rendering; blade proxy follows weapon bone (part of committed truth). No GPU mesh readback for collision. Verify against posed mesh in a debug overlay pass.

**Concrete risks:**
1. NVIDIA Open Model License — legal review before ship (attribution + "trustworthy AI" terms).
2. Latency jitter in ort/CUDA sidecar — budget 4–6 ms worst case, profile early.
3. Replanning pop when action commits mid-replan (3–9 frame interval) — author overlap-compatible keyframes.
4. No finger/toe data — procedural IK quality risk.
5. Spine oversimplification (3 DOF) — add artist-corrected spine curves.
6. ONNX/CUDA non-determinism — validate bit-exact replay hashes.
7. Proxy authoring burden — ongoing content cost, not one-time.

**Single most-likely failure mode:** **MotionBricks softmax token sampling left non-greedy (temperature/top-k) → slightly different joint trajectories across runs/clients → breaks replay determinism/desync.** Mitigation: force **argmax**, fixed seed-derived stream only for *committed* cosmetic variation, determinism smoke test (same input twice → identical pose+truth hash).

**Key citations:** MotionBricks (Wang et al. 2026, arXiv:2604.24833); SONIC (Luo et al. 2025); ExBody2 (Ji et al. 2024); MDM (Tevet et al. 2022); MotionLCM (Dai et al. 2024); MotionGPT (Jiang et al. 2023); For Honor Motion Matching (Clavet GDC 2016); Learned MM (Holden et al. 2020); Lipschitz MM (Kleanthous & Martini 2024); DeepMimic (Peng et al. 2018); AMP (Peng et al. 2021); PFNN (Holden et al. 2017); DQS (Kavan et al. 2007); BONES-SEED; GR00T-WholeBodyControl/MotionBricks.

---

## 2. Plate Deformation (corotational tet FEM) + Brittle Fracture (Voronoi)

**Recommended approach — plate:** **Operator-splitting corotational linear FEM** (Kugelstadt, Koschier & Bender 2018). Decouples stretch/volume → small well-conditioned sub-steps, avoids changing global stiffness matrix, deterministic-friendly. Avoids full Projective Dynamics (step-count/stiffness-dependent, harder exact replay) and ARCSim (adaptive remesh, non-deterministic at game budgets). Per-element kernels (deformation gradient F, polar rotation R via Müller 2016 stable polar decomposition, strain, stress) on GPU; **global solve on CPU** (prefactored Cholesky / small PCG) for hash stability. Plate mesh of a few hundred–low-thousands of tets solvable in <1 ms sub-step on modern CPU.

**Recommended approach — fracture:** **Pre-fractured Voronoi (VACD, Müller et al. 2013)** as the default for Rune-Marble/bone. Offline author fragment geometries + crack graph; runtime swaps intact→pre-fractured and walks the crack graph deterministically (`σ_tensile > σ_threshold × material_factor`), with seeded RNG micro-variation. Shards promoted to rigid bodies with deterministic initial velocity from impact point/normal/impulse (optionally secondary projectiles). Organic bone upgrade path: *Breaking Good* fracture modes (Sellán et al. 2022) for non-convex splinters. **No online adaptive mesh cutting** (non-deterministic topology).

**Determinism:** fixed substeps (no adaptive dt), fixed iteration counts (never residual-tolerance termination), sorted/stable-ID loops, no HashMap in hot paths, libm/nalgebra transcendentals, integer/fixed-point accumulation if GPU used.

**Concrete risks:** solver stiffness↔stability; GPU non-determinism; fracture serialization size (shard budget 8–16/impact); FEM↔rigid-body coupling; cross-platform float.

**Single most-likely failure mode:** **determinism↔stability tension** — FEM tuned for the <1 ms budget goes unstable on a heavy hit; "fix" adds substeps/iterations that change the numerical path and thus the truth hash, invalidating prior replays. Mitigation: **fix iteration/substep counts up front; author impacts to stay in the stable regime**; never tune the solver reactively.

**Key citations:** Müller et al. 2001 (real-time deformation/fracture); McAdams et al. 2011 (elasticity for skinning); Barbič 2012 (exact corotational stiffness); ARCSim (Narain et al. 2012); Projective Dynamics (Bouaziz et al. 2014); Kugelstadt et al. 2018 (operator-splitting fast corotated FEM); Müller et al. 2016 (stable polar decomposition); Wang et al. 2025 (group-based corotational FEM); Müller et al. 2013 (VACD fracture); Sellán et al. 2022 (Breaking Good); Hahn et al. 2016 (BEM brittle fracture); Rapier determinism guide; Fenris (Rust FEM); Vega FEM.

---

## 3. Deep Localized Tissue Injury (biomechanical)

**Recommended approach — data-driven layered region model:**
- Resolver emits a discrete `ContactEvent` (force vector, damage family, impact point, angle). Injury subsystem is pure consequence (never cause).
- Per region: bone / muscle / tendon / ligament / organ / joint layers, each with `structural`, `pain/shock`, `bleed` thresholds (grounded in literature, scaled for duel pacing).
- **Capability deltas derived from discrete state every frame** (grip, arm_speed, dodge, limp, vision, balance, stamina_regen, incapacitation_flags) via additive-impairment model — deterministic, hash-stable.
- **Integer/fixed-point truth:** tissue damage as integer ticks/counts/enumerated severity; truth hash over compact byte serialization.

**Grounded thresholds (anchor points, tune per character/weapon):** skin penetration ~20–95 N (O'Callaghan 1999); compact bone 1–4 kN / femur 3.5–10 kN (NHTSA/PMHS); rib 1–4 kN (Yoganandan & Pintar 2007); muscle strain 15–35% (Noonan 1994, Garrett 1995); tendon >4% yield (Physiopedia); ACL 600–2300 N (Cole 1999); brain HIC-15 250/700/1000 (Viano 2005, NHTSA), BrIC 0.5/0.8/1.0+ (Takhounts 2013); organs by AIS/AAST grades (spleen/liver/kidney hemorrhage→shock). Use Keaveny & Bouxsein (2008) Φ = impact force / bone strength ratio as the deterministic fracture rule.

**Readable, non-hidden-HP presentation (canon + Dwarf Fortress model):** named severity states (bruised/strained/torn/ruptured/fractured/broken/missing/function-loss); per-layer status icons + body-region world cues; every capability degradation emits a world-readable event (pose change, VFX, audio, UI). Replay inspector shows layer-by-layer derivation.

**Concrete risks:** presentation physics leaking into truth; float drift in capability multipliers; combinatorial state explosion (cap 6–8 regions, 4 severity levels/layer); over-realistic thresholds unfun; animation cannot express consequences (co-author with injury tables).

**Single most-likely failure mode:** **capability-derivation becomes opaque → players blame "hidden numbers."** Fix: authorable/visible derivation rules, gate major incapacitations on named thresholds, always emit world-readable events.

**Key citations:** HIC (Gadd/WSTC/NHTSA); Takhounts et al. 2013 (BrIC); Viano 2005; Gennarelli & Wodzin 2006 (AIS); Yoganandan & Pintar 2007; NHTSA 2013; Keaveny & Bouxsein 2008; Noonan 1994; Garrett 1995; Luetkemeyer 2023 (multimodal ligament); Nölle 2024; Maganaris/Physiopedia; Cole 1999; O'Callaghan 1999; AAST organ scales; Todorov 2012 (MuJoCo); Peng 2018 (DeepMimic); Featherstone 2008 (ABA); Macklin/Müller 2016 (XPBD); Rapier/Jolt determinism; Dwarf Fortress wound model; MuscleMimic (Li et al. 2026).

---

## 4. Hitbox Parity, Camera Readability, and Fair Deterministic AI

### 4.1 Hitbox parity (mandatory)
- **Proxy source:** bone-local convex hulls + swept capsules for blades; truth pose is canonical, renderer derives from it.
- **CCD:** swept capsule vs skinned-mesh triangles for active frames; budget permits at 60 Hz for the small proxy count.
- **Verification tooling (P0 gate, per PRD_QA_AGENTIC):** overlay renderer (proxy vs mesh), golden-state tests, ghost-hit fuzzer (random inputs → assert no phantom/missed hits).
- **Failure mode:** renderer adds interpolation/IK/cloth not in truth → phantom/missed hits. Mitigation: truth pose canonical; automated overlay parity.

### 4.2 Camera readability
- **Primary:** first-person, 75–90° FOV, elevated eye, low self-weapon — but **must pass the 80% blind action-read test** (8 reveal frames, 13 actions, ≥50 trials).
- **Fallback (canon-approved):** hybrid side-view reveal camera during the action phase if first-person fails the test. Camera readability beats genre purity.
- **Aids:** exaggerated anticipation, audio tells, peripheral motion cues (not UI clutter).
- **Failure mode:** first-person occludes opponent tells in first 8 frames → game feels random. Mitigation: blind-read test gates the camera; switch if <80%.

### 4.3 Fair deterministic AI
- **Core:** ISMCTS (Cowling et al. 2012) over the 13-action matrix with a belief model updated only *after* reveal (hidden intent never observable).
- **Personality via mistakes:** data-driven `mistake_rate` + `mistake_profile` + risk weight; lower difficulty = more intentional suboptimal reads, not hidden bonuses.
- **Determinism:** AI RNG is a sub-stream of truth RNG; commits before reveal like the human.
- **Failure mode:** AI accidentally reads hidden player intent (shared ref/debug hook/input router) → perfect input-reader, feels unfair. Mitigation: architecturally separate hidden intent from observable state; audit all AI inputs.

**Key citations:** Fiedler 2010 (float determinism); Mighty Professional 2026 (netcode); GGPO (Cannon 2009); Fortress Rollback 2025/2026; backroll-rs 2021; Rapier determinism; For Honor deterministic sim (Henry GDC 2019); Ericson 2004 (RTCD); GJK/EPA (FCL); CCD (DigitalRune); Colantonio GDC 2007 (first-person melee); Ljung & Skärner 2015 (FOV); Rivals/anticipation-action-recovery; YOMI Hustle; ISMCTS (Cowling 2012); MCTS fighting AI (IEEE 2016, Kim 2019); Mick West 2009 (intelligent mistakes); behavior trees (Simpson 2014); Ubisoft For Honor bot ML (Azzouni 2025, Romoff 2024).

---

## 5. Cloth / Leather (XPBD/PBD) + Chainmail (rigid-body constraint network)

**Recommended approach (from `docs/research/CLOTH_CHAINMAIL_RESEARCH_REVIEW.md`):**

**Cloth/leather — XPBD with fixed substeps (Macklin et al. 2016, 2019 "small steps"):** one XPBD iteration per fixed substep (10–30 substeps/frame), not many iterations at one large step — more robust for a fixed 60 Hz truth loop. Distance + bending constraints (per-edge rest length + damage/dangling flag); **not** shape-matching (SVD too expensive on GPU). Plasticity/tear: track per-edge rest-length plastic offset; when strain > threshold, increment damage; at damage=1 mark edge broken and exclude from solving; render mesh spawns a visual crack/decal. **No dynamic remeshing in truth** (topology mutation only at explicit event boundaries, stored as broken-edge bitset). Leather = same XPBD framework with higher bending stiffness, plastic rest-angle offsets for creases, higher damping, thicker collision proxy.

**Chainmail — simplified state-machine truth graph, NOT per-ring rigid-body in truth (critical decision):** a full rigid-body ring network (one rigid body per ring, hinge/sliding/friction/break constraints, PBD-RBD per Deul et al. 2014) is feasible for *visuals* (NVIDIA FleX precedent) but too expensive and non-deterministic for a 60 Hz truth loop with stable hash (<2 ms). Instead: truth layer = low-res node graph (one node per ~4–16 ring cluster) with states `intact | deformed | breached | torn`; transitions driven deterministically by weapon hit events (pierce/blunt/cleave) via fixed per-cell thresholds + seeded RNG graph traversal (BFS/DFS). Visual layer = actual ring mesh driven deterministically by the truth graph (pre-draped poses, broken/dangling rings, debris particles). This mirrors exactly the plate-fracture track's pre-fracture-Voronoi philosophy: abstract deterministic truth + expensive visual-only fracture.

**Determinism (consistent with §0):** fixed `dt=1/60`, fixed substep count, no adaptive solver params; deterministic seeded RNG (xoshiro256**/PCG64 from global seed + slot salt + frame) — never wall-clock/OS RNG; graph coloring for order-independent constraints; **CPU truth solver, GPU visual only**; truth hash computed from CPU truth state only (GPU visual never hashed, never feeds truth). Full state serialization (positions, velocities, rest lengths, damage, broken-edge bitset, node states) or inputs+events after desync ruled out. Disable `-ffast-math`; avoid FMA/transcendentals in truth; same build target for hash parity (cross-vendor GPU parity is a stretch goal → fixed-point if required).

**Open-source Rust/WGSL starting points:** `wasm-cloth-sim` (txst54 — Rust/WebGPU/XPBD), `xpbdrs` (nikhilr612 — serde/bincode XPBD), `PositionBasedDynamics` (Bender et al. — C++ constraint-math reference), `gpu-cloth-sim2` (ThomasConrad), `FleX` (Macklin et al. — constraint design).

**Concrete risks:** GPU float non-determinism (keep truth CPU); self-collision cost/non-determinism (conservative proxy, omit full self-collision in truth); topology change serialization (event-boundary only, explicit bitset); chainmail visual/truth mismatch (strong deterministic coupling + debris); solver stiffness/explosion (moderate compliance, damping, ≥10 substeps); replay size (delta-compress); CPU perf (reduce res / SIMD / validated deterministic GPU).

**Single most-likely failure mode:** chainmail forces a choice between (a) faithful per-ring rigid-body truth that is too expensive/non-deterministic for 60 Hz, or (b) simplified state-machine truth that is deterministic but lacks compelling visual feedback. Mitigation: **commit early to the simplified truth model** and invest in the visual layer (pre-authored drape, deterministic debris, tight truth→VFX coupling) so the abstraction is imperceptible. Insisting on true per-ring truth risks a budget/desync/replay breakdown surfacing only after weeks of integration.

**Key citations:** Müller et al. 2007 (PBD); Macklin/Müller/Chentanez 2016 (XPBD); Macklin & Müller 2019 (small steps); Macklin et al. 2014 (FleX/unified); Bender et al. 2017 (PBD survey); Jiang et al. 2017 (anisotropic elastoplasticity); Yu et al. 2024 (XPBI plasticity); Garrison 2024 (PBD tearing); Wang 2026 (Rust/WebGPU XPBD); Deul et al. 2014 (PBD-RBD); Wijnhoven & Moskvin 2020 (mail armour replication); Fiedler 2004 (Fix Your Timestep). Plus the Rust/WGSL repos above.

---

## 6. Synthesis — What "develop to our standards" requires

**Non-negotiable architecture (all tracks agree):**
1. Truth is deterministic, serializable, hash-stable, presentation-isolated. This is the load-bearing invariant; every deep-sim subsystem is a *truth* subsystem first.
2. MotionBricks is the only motion source; keyframe-driven; argmax inference; retarget local-space; DQS; analytical hitbox proxies share the render pose.
3. Deep sims (cloth, chainmail, plate-FEM, fracture, tissue) are deterministic solvers with **fixed substep/iteration counts chosen up front** — never tuned reactively, or replays break.
4. Hitbox parity is a P0 gate with automated overlay + ghost-hit fuzzer.
5. Camera must earn its first-person view via the 80% blind-read test or yield to a hybrid reveal camera.
6. AI is ISMCTS + mistake-based personality, hidden-intent-isolated, seed-deterministic.

**The recurring single failure mode across ALL subsystems is the same:** a truth/runtime decision made for *stability* or *visual convenience* silently breaks determinism (hash divergence) or truth isolation (presentation feeds back). The mitigation is uniform: fix the solver contract up front, ban non-deterministic constructs in truth, and gate every phase on the truth-hash regression + a parity/blind-read test.

**Phasing (per PHASED-PRODUCTION-PLAN):** Phase 1 = playable loop + hitbox parity for one action; Phase 2 = deterministic deep-sim *foundation* (one region tissue + one piece plate, hash-stable); Phase 4 = readability (MotionBricks tells, camera, audio); Phase 5 = full deep injury/armor; Phase 9 = rollback after local fun. No subsystem may advance past its phase gate without the corresponding evidence gate.

**Canon amendments required:** None. The research confirms the locked architecture; it refines *how* to implement it (operator-splitting FEM, pre-fractured Voronoi, integer/fixed-point injury, ISMCTS AI, keyframe-driven MotionBricks). All consistent with GAME_CANON's full-fidelity / no-fallback / truth-isolation mandates.
