# Just Dodge — Game-First Intent Combat Spec (2026-07-17)

Status: DRAFT awaiting owner confirmation. Owner directive: PROVE THE GAME FIRST
with basic visual fidelity; high-fidelity (Mesh Doctor, ForgeLens, AAA Meshy
assets) is SECOND phase. This spec supersedes the capture-scope of
JD-RC0-MESHDOCTOR-GRAB07-003 (that unit's hand-authored approach is rejected).
50-question clarification complete; this is the consolidated result.

## 0. North-star ordering

1. P0 — playable deterministic intent loop on a debug mannequin.
2. High visual fidelity only after the loop is proven.
3. Purpose-built models for deep sims come later (the C0 armored fused mesh is a
   blocker; it is removed from the game-loop path, not from the repo).

## 1. Core loop (Yomi-Hustle-style)

- Simultaneous-lock turn forecast: both players lock an intent each plan phase;
  the engine resolves the interleaved result deterministically, freezes at the
  phase boundary, both pick the next intent.
- Re-prompt cadence: based on the fastest move used in the duel (exact rule
  pending YOMIH research, deleg_5f675007).
- Goal-directed intents, not fixed animations. Example: to Grab an out-of-reach
  opponent the engine auto-runs into reach, then grabs.
- Frame cost: FIXED per action family (Strike/Block/Grab canonical cost, tuned
  by data).
- Feasibility: re-evaluated MID-EXECUTION at each plan-phase boundary; if the
  goal can't be achieved in-cost, the engine does NOT lock into a whiff — it
  re-prompts (continue / feint / cancel).
- Feint: BOTH cheap cancel-feint AND committed feint actions.
- Cancel: costs a fixed penalty (frames or a vulnerable window) to prevent spam.
- Emergent brutal combos: cancel-into rules + free chaining at phase boundaries
  + juggles (launched/airborne opponents re-struck before landing).

## 2. Fighters, arena, camera, control

- Controllers: human vs AI now, PvP-capable architecture. AI plays a FIXED
  SCRIPTED intent sequence (deterministic, replayable).
- Body: debug mannequin exposing joints/bones/weights defects (c0_base_fighter
  24-bone, flat-shaded + skeleton overlay). Enables extensive visual
  verification of AI/game-asset issues. NOT a capsule blob, NOT the fused
  armored production mesh.
- Arena: flat plane + distance markers/readout for spacing verification.
- Movement: full 3D (circle, approach, retreat, lateral).
- Camera: first-person (shipped perspective) + free/observer toggle.
- Intent selection: YOMIH-style forecast timeline UI showing predicted frames
  before locking; player can ALSO select the opponent's move in planning to
  preview the what-if ghost (full-information tactics). UI requires a Paper
  Design visual-design gate before implementation.
- Forecast: deterministic forward simulation of both fighters' chosen intents
  for the window (authoritative, same code as truth). Ghosted predicted motion +
  contact outcome shown before locking.

## 3. Actions (classic 13)

Strike, Block, Grab, Move, named strike variants (thrust/slash), dodge, feint,
cancel, idle (+ clinch sub-menu).
- Weapon state: Grab is unarmed (empty hands); strikes need the sword drawn.
- Grab success → CLINCH state with its own simultaneous-lock sub-exchange and
  its own frame data (grab-tech to counter/escape).
- Block: a perfect-frame block entirely negates damage (else chip/durability).
- Dodge: pure reposition, NO i-frames; the motion engine must dynamically react
  to the opponent's move so the dodge truth holds visually.

## 4. Match / win / replay / tutorial / audio

- Match: single continuous exchange until one fighter is incapacitated (injury
  truth). No timer.
- Replay: exact truth re-simulation (deterministic, free camera) + cinematic
  angles.
- Tutorial: straight into a match; tutorial later.
- Audio: none for the proof; add later.
- UI/HUD: clean gameplay UI (intent list + forecast timeline + injury readout,
  no debug clutter) + hidden toggleable dev overlay (frame data, contact boxes,
  truth hash) for verification.

## 5. Injury truth

- Deterministic injury truth from day one (the locked 500–1000-structure
  anatomical model). Deep simulations, visually coherent. Injury-state is a
  conditioning primitive; limb capability loss drives available intents;
  incapacitation = loss.

## 6. Physics / determinism

- Fixed 120 Hz physics + 60 Hz truth, integer cadence, fully deterministic.
- Cross-platform bit-exact (Linux/Windows x64 + Steam Deck) via fixed-point /
  quantized truth.
- Contact: oriented boxes (OBB) per bone (tighter than current AABB), swept CCD.
- Body dynamics: kinematic standing/locomotion + deterministic ballistic
  launch/knockdown (NO continuous ragdoll). Recommended + confirmed.
- Determinism verification: scripted-match golden replays covering each intent +
  clinch + combo + injury.

## 7. Motion (MotionBricks)

- MotionBricks generates ALL body motion conditioned on intent + displacement +
  opponent action (fully generative). Runtime inference in the loop.
- Never blocks 120 Hz truth: async/deferred (predict next intent's motion; hold
  last pose if not ready) AND pre-generate per-intent at plan-phase lock.
- Locomotion: hybrid — engine computes required displacement per truth-tick,
  MotionBricks conditions on it, deterministic physics authoritative.
- Reactive-fit: conditioned generation (feed clearance/target/limb-state/
  weapon-hand/opponent/injury/momentum/speed/velocity conditions into
  MotionBricks so it generates fitting motion). NO post-decode position/rotation
  replacement passed off as learned conditioning. ARDY supplies intent proposals
  + richer token primitives (limb states, weapon hand, contact/clearance,
  momentum/speed/velocity). Grounding research running (deleg_5a23797f).

## 8. Build architecture

- New clean game-loop module built for the intent model, reusing
  physics/truth/motion primitives (duel_world, duel_physics, hitbox, truth,
  motion, motion_retarget). Do NOT refactor milestone3 in place.
- Rust/wgpu/winit retained. No Unity/Unreal/React/new framework.

## 9. P0 acceptance (all deterministic, evidenced)

- Intent loop playable on debug mannequin: Strike/Block/Grab/Move/Feint/Cancel/
  Idle + clinch + combos.
- Forecast timeline UI with what-if ghost (Paper-gated).
- Replay (deterministic re-sim, free camera + cinematic).
- Deterministic injury truth driving incapacitation.
- Scripted AI opponent.
- Golden-replay determinism tests green; 120 Hz truth never blocked by motion.

## 10. Explicitly deferred (NOT in P0)

Mesh Doctor penetration repair, ForgeLens evidence surface, AAA Meshy assets,
Steam packaging, high visual fidelity, tutorial, audio, Steam Deck tuning.

## Research dependencies (running)

- deleg_5f675007 — YOMIH re-prompt/forecast-window + fastest-move rule +
  what-if opponent forecast.
- deleg_5a23797f — MotionBricks/GR00T conditioned generation (clearance,
  limb-state, weapon-hand, opponent, momentum/speed/velocity), ARDY primitives,
  latency vs 120 Hz.
