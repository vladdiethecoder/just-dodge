# Just Dodge — Game Canon (Locked)

## Authority

This document is the locked design canon for Just Dodge. Where existing docs contradict each other or the current codebase, this document resolves the contradiction. Older documents (`docs/GDD.md`, `docs/COMBAT-SYSTEM.md`, `docs/ARMOR-DAMAGE-SYSTEM.md`, `docs/SYSTEMS-DESIGN.md`, `docs/MOTIONBRICKS-RETARGETING.md`, `docs/ROADMAP.md`, `docs/PHASED-PRODUCTION-PLAN.md`, `docs/QA-AGENTIC-PLAYTESTING.md`, `docs/MILESTONES.md`, `docs/PROTOTYPES.md`, `docs/LESSONS-FROM-OATHYARD.md`, `docs/RISK-REGISTER.md`) and `docs/design/RESEARCH_SYNTHESIS.md` are source material, not overrides.

## Locked Product Identity

**Working Title:** Just Dodge  
**Genre:** First-person deterministic melee duel  
**Players:** 1v1 (local first, networked later)  
**Session Length:** 1–5 minutes per duel  
**Platforms:** Linux, Windows (Steam), macOS if feasible  
**Monetization:** Premium one-time purchase (no F2P, no loot boxes)  

## Locked One-Sentence Promise

"Just Dodge is a first-person duel game where you and your opponent each commit to one hidden action, reveal simultaneously, and live or die by the physics, timing, and reading of that single exchange — so you can feel like a mind-reading duelist, and you will want to share it because every match produces a clip-worthy 'I knew you would do that' moment."

## Locked Core Pillars

1. **Mind-Game First** — every exchange is a YOMI read, not a reaction test.
2. **Physical Truth** — hitboxes, timing, and consequences are deterministic and simulation-backed.
3. **Motion That Reads** — every action is readable through pose, weapon motion, and audio before contact.
4. **Emergent Depth** — simple rules, complex outcomes through matchup matrices, capability injury, and state adaptation.
5. **Presentation Isolated** — renderer, animation, camera, and audio never mutate combat truth.

## Locked Engine Decision

- **Engine:** Custom Rust + wgpu.
- **Windowing:** winit 0.30.
- **Math:** glam 0.28.
- **Audio:** rodio or kira (decided at implementation).
- **Physics:** none for prototype; deterministic geometric collision only.
- **Networking:** added only after local vertical slice is accepted fun.

This overrides any older doc language describing a "minimal triangle prototype" or "Godot project." The current repository is a Rust/wgpu custom engine.

## Locked Scope Boundaries

- **In scope:** 1v1 simultaneous-reveal dueling, 13-action matrix, deep localized injury and tissue damage, deep armor/material simulation, deep martial-arts motion via MotionBricks, deterministic AI, replay theater, fight film, local 2P, tutorial, Steam launch.
- **Fidelity target:** For Honor visual and physical fidelity combined with YOMI Hustle simultaneous-reveal game loop.
- **Motion engine lock:** MotionBricks is the sole animation, stance, pose, combat motion, and retargeting engine. Prebaked action clips and motion fallbacks are disallowed. MotionBricks must work for every required action; missing or broken motion is a build-blocking defect. (Owner ruling 2026-07-19: baked clips are forbidden in every mode and tier — no baked clip libraries, pose banks, or runtime clip playback exist anywhere in the game.)
- **Continuous combat state space:** the combat state space is continuous ("infinite"). All motion is generated per tick from the live condition packet (intent, displacement, limb state, weapon hand, opponent state, injury, momentum, speed, velocity, root transform) and resolved by deterministic physics. The game never selects from a discrete set of precomputed combat states or animations.
- **Archetype constraint:** the infinite state space is bounded by character archetypes. A fighter's learned combat arts, weapon/build, and current physical state define which intents and motion families are reachable. Archetypes constrain options and conditioning; they never quantize motion into clips.
- **Hitbox parity:** Collision proxies must match visual geometry exactly. No oversized hitboxes, no ghost hits, no phantom range.
- **Out of scope:** open world, crafting/loot, MMO, narrative/dialogue trees, physics-driven comedy, networking before vertical slice.

## Locked Verification Doctrine

- The game is developed to its full potential and full fidelity, regardless of single-developer constraints or engineering difficulty.
- Fun is measured by replay requests, story retelling, clip creation, and friend referrals — not by screenshots.
- Every stage ends with a playable build and evidence report.
- Truth hash must remain stable across presentation changes.
- Player mode must never show placeholder UI or debug overlays.
- No production scope advance until the corresponding prototype report says CONTINUE and the evidence gate passes.
- Hardship or resource constraints do not justify fallbacks, placeholders, or reduced fidelity.

## Drift Resolutions

| Drift | Resolution |
|---|---|
| README says repo is code-empty. | Repo has substantial Rust/wgpu/MotionBricks code; this canon acknowledges the real baseline. |
| Milestone 2 mentions Godot project. | Engine is Rust/wgpu custom; milestone text is superseded. |
| Shape prototype plans triangles-only. | Current source has textured arena and skinned mannequin; next prototype still targets a 3-action playable loop, using existing renderer as context only. |
| Asset loader/extractor format ordering may mismatch. | Accept as known pipeline risk; fix before next asset import. |
| Motion dimensions in older docs (241/329) vs code (304/413). | Current exported model metadata wins; reconcile with actual ONNX metadata before next motion milestone. |
| Older docs permit prebaked/baked fallback clips. | SUPERSEDED by owner ruling 2026-07-19: baked clips forbidden in all modes; ship lane is the live generative MotionBricks provider via the async buffered plan service. |
| ONNX/NPY artifacts are gitignored. | Runtime requires externally generated artifacts; packaging must include them. Missing artifacts block the build; no motion fallback exists. |

## Next Canon Amendment

This canon is amended only by explicit user decision, never by drift. Any amendment must update this file and the affected PRDs.
