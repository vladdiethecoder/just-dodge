# Just Dodge — Game Canon (Locked)

**Amended:** 2026-07-21 — post-exhaustive-interview reset
**Authority:** This document is the locked design canon. Older docs are source material only.

## Locked Product Identity

**Working Title:** Just Dodge
**Genre:** First-person deep-simulation intent-combat game
**Players:** 1v1 (local first, networked later)
**Session Length:** 1–5 minutes per duel
**Platforms:** Linux, Windows (Steam), Steam Deck
**Monetization:** Premium one-time purchase

## Locked One-Sentence Promise

"Just Dodge is a first-person deep-simulation combat game where your grab, strike, or dodge resolves differently every time based on your exact body arrangement, limb positioning, momentum, and the opponent's state — so you read conditions, not memorize frame data, and every exchange produces an unscripted 'how did that happen' moment."

## Core Combat Vision

This is a **strategy game disguised as a fighting game.** Players do not memorize per-frame move properties or canned animation timings. Instead they learn to read:

- Body arrangement: stance, limb positions, joint angles
- Environmental conditions: distance, terrain, relative momentum
- Opponent state: injury, armor integrity, weapon position, balance

The same Grab intent produces a different animation and outcome depending on these conditions. The deterministic physics engine resolves contact truth; MotionBricks generates the visual motion conditioned on the full state. Complexity emerges from continuous state interaction, not from a large move list.

**Key differentiator (the selling point):** No two exchanges look the same. Condition-driven generative motion + deterministic physics = unscripted, clip-worthy combat that players share.

## Locked Core Pillars

1. **Read Conditions, Not Frame Data** — every exchange outcome depends on body arrangement, limb state, environment, and opponent condition. The same intent resolves differently depending on state.
2. **Physical Truth** — deterministic 60 Hz truth, 120 Hz contact, stable hashes, replay-identical across platforms.
3. **Generative Motion, No Clips** — MotionBricks generates all motion per tick from the live condition packet. No canned animations, no baked pose banks, no fallback clips. Motion that fails is a build-blocking defect repaired at the source.
4. **Emergent Depth** — simple intent rules, complex outcomes through continuous state interaction and condition-driven motion.
5. **Presentation Isolated** — renderer, animation, camera, and audio never mutate combat truth.

## Locked Engine Decision

- **Engine:** Custom Rust + wgpu 0.30, winit 0.30, glam 0.28
- **Physics:** deterministic fixed-step contact, active-ragdoll, injury, bounded per-object material/SDF truth
- **Motion:** MotionBricks sole animation authority; live generative, condition-driven, no clips
- **Assets:** Meshy web (primary) + API (batch/repeatable); Blender as DCC authority; GPT Image for concepts
- **Audio:** rodio or kira (implemented at need)
- **Networking:** after local vertical slice accepted

## Locked Scope Boundaries

- **In scope:** 1v1 simultaneous-intent dueling, 13-action matrix, deep localized injury, armor/material simulation, generative MotionBricks motion, deterministic AI, replay theater, fight film, local 2P, tutorial, Steam launch.
- **Motion engine lock:** MotionBricks generates all motion conditioned on intent, displacement, limb state, weapon hand, opponent state, injury, momentum, speed, velocity, root transform. Continuous state space; archetype-constrained, never clip-quantized. If MotionBricks cannot generate acceptable motion for a required action, the pipeline is repaired or retrained — never downgraded to procedural fallback.
- **Hitbox parity:** collision proxies match visual geometry. No oversized hitboxes, ghost hits, phantom range.
- **Out of scope:** open world, crafting/loot, MMO, narrative/dialogue trees, networking before vertical slice.

## Visual-First Pipeline (replaces SG01-SG10 sequential gating)

The old SG01→SG10 infrastructure-first approach consumed ~95% of development time on evidence gates with ~5% on gameplay. This is now replaced:

**Phase 1 — Asset & Motion Proof (current)**
1. Generate properly proportioned fighter in Meshy web (multi-view, T-pose, clean topology)
2. Show owner: screenshot + GIF checklist → 30-second accept/reject
3. If accepted: import to Blender, validate geometry/rig, cook for engine
4. Generate one clean strike motion (MotionBricks → retarget → skinned render)
5. Show owner: GIF of the strike → accept/reject
6. If accepted: generate block, grab → show GIFs → iterate

**Phase 2 — Playable Vertical Slice**
7. Wire the accepted fighter + motion into game_loop
8. Implement full match flow: Boot → Observe → Plan Intent → Commit → Reveal → Resolve → Consequence → Result → Rematch
9. Show owner: video of a complete match → accept/reject
10. If accepted: add AI opponent, injury, camera, basic UI

**Phase 3 — Full Game**
11. Expand to 13 actions, multiple fighters/weapons/arenas
12. Add replay theater, fight film, audio, tutorial
13. Steam packaging

**Every gate is a visual decision:** screenshot/GIF/video + multiple-choice checklist. No verbose evidence reports, no machine-only gates, no sequential infrastructure prerequisites blocking gameplay.

## Evidence Portal (ADHD-Style)

The evidence review tool must follow these rules (derived from `ayghri/i-have-adhd`, 6.5K stars, GitHub trending #4, 2026-07-21):

1. Lead with the visual (screenshot/GIF/video), not text
2. One decision at a time, not a multi-page report
3. Multiple choice: Accept / Reject / Needs Changes
4. No verbose explanations, no log dumps, no "hope this helps"
5. Show concrete next step after each decision
6. Cap lists at 5 items
7. Make wins visible: "3/7 accepted, 1 rejected, 3 pending"

## Locked Verification Doctrine

- Fun is measured by replay requests, story retelling, clip creation, and friend referrals — not screenshots.
- Every stage ends with a playable build and a visual (not text) evidence checkpoint.
- Truth hash must remain stable across presentation changes.
- Player mode must never show placeholder UI or debug overlays.
- No production scope advance until the visual gate passes.
- Hardship or resource constraints do not justify fallbacks, placeholders, or reduced fidelity.
- Character, equipment, weapon grip and player-camera promotion must satisfy `CHARACTER_EQUIPMENT_PROMOTION_CONTRACT.md`.

## Lessons Learned (from OATHYARD, Hustle & Honor, and Just Dodge SG01-SG02)

1. **Infrastructure gates expand infinitely.** Evidence quarantine, cross-platform parity receipts, and CI matrices can consume 95% of development time while producing zero gameplay. Infrastructure serves the game; the game does not serve the infrastructure.
2. **Visual evidence must be fast to judge.** If the owner cannot decide in 30 seconds from a screenshot/GIF and a multiple-choice prompt, the evidence system is broken.
3. **The core loop must be proven before anything else.** A playable mannequin duel with basic intent→motion→contact→result teaches more than months of infrastructure work.
4. **No asset promotion without visual acceptance.** A generated mesh that hasn't been seen in-engine is not an asset — it's a candidate. Promote only after owner visual gate.
5. **MotionBricks must produce visual evidence or the game cannot ship.** The entire selling point depends on generative motion. The first deliverable is proof that the pipeline works end-to-end.

## Drift Resolutions

| Drift | Resolution |
|---|---|
| Old SG01-SG10 sequential gating | Replaced by visual-first pipeline (2026-07-21) |
| Evidence review prioritized logs over visuals | Replaced by ADHD-style visual checklist (2026-07-21) |
| Asset pipeline used MCP API as primary | Meshy web is now primary; API for batch/repeatable (2026-07-21) |
| Game described as "simultaneous-reveal duel" | Amended to "deep-simulation intent-combat" emphasizing condition-driven emergent motion (2026-07-21) |
| README says repo is code-empty | Repo has substantial Rust/wgpu code; canon acknowledges real baseline |
| Older docs permit prebaked fallback clips | SUPERSEDED: baked clips forbidden in all modes |
| ONNX/NPY artifacts gitignored | Runtime requires externally generated artifacts; packaging must include them |

## Next Canon Amendment

This canon is amended only by explicit user decision, never by drift. Any amendment must update this file and the affected PRDs.
