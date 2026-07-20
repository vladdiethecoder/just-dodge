# Just Dodge — AAA Finish Backlog (2026-07-19)

Status: owner directive 2026-07-19 — "Finish the game to AAA standards, all scoped
features + 200 proposed features, real Steam-publishable game, generative motion and
combat at high fidelity, competitive mind-game loop, all blockers resolved without
degrading from highest frontier capabilities."

This document is the master execution backlog. It is subordinate to
GAME_CANON.md and GAME_FIRST_INTENT_COMBAT_SPEC.md; where it conflicts, canon wins
until amended. Research proposals are not runtime canon; promotion requires the
verification hierarchy (fmt → clippy -D warnings → tests → golden replay →
ForgeLens/Evidence Studio human gate).

Gate codes used per feature:
H = headless deterministic test/probe; G = golden-replay determinism gate;
V = ForgeLens/Evidence Studio human visual gate; P = measured performance budget;
A = agentic playtest evidence; X = human playtest evidence; S = Steam/platform check.

## Part A — Current state audit (2026-07-19)

Committed and measured: M1 intent module (src/intent/, incl. grab 8-state contact
machine + closing solution + ARDY feasibility), M5 injury truth (stable-ID atlas,
sparse-active state, contact→injury, capability gating), M6 golden replay (7
scenarios × 100 runs, SHA-256 manifest, Python fail-closed verifier), M4 async
motion plan service (non-blocking 120 Hz; current provider is dev scaffolding —
baked clips are forbidden per owner ruling 2026-07-19 and it is not a ship path),
M2 game_loop (debug mannequin, FP/observer camera, flat arena profile), articulated integer physics
(120 Hz quantized, 100-run hash gate). UNIT-2 v11/v13 REVOKED (INVALID_EVIDENCE per RESET-004);
G4 leakage-free MotionSeqModel retrained on Harmony4D paired corpus (67 admitted contact cases pass per-case 15mm gate);
G4/G5 PENDING_HUMAN per RESET-004 STOP STATE.
Workspace green: clippy --all-targets -D warnings clean, cargo test --locked green
(188 lib tests; MotionBricks bridge env-gated test ignored as designed).

In-flight uncommitted: game_loop scripted opponent uses Grab; PlanPhase::new roots
at ±300 mm (600 mm separation, inside GRAB_ACQUIRE_RANGE_MM=650). This is the
grab-closure scenario for the live loop; verification pending this session.

Not started (gated): forecast timeline UI (Hermes Canvas design gate), full 13-action
matrix data authoring, stance/tempo, feint/whiff-cancel runtime, generative runtime
provider, full injury atlas population (500–1000 structures), armor deep sim,
audio, networking, Steam packaging, content scale-out, AAA asset promotion.

Critical path: close grab-closure loop unit → forecast/what-if UI (Canvas gate) →
full action matrix + stance/tempo → generative motion runtime lane → deep injury/
armor → presentation fidelity → replay theater → content → networking → Steam.

## Part B — Scoped canon feature inventory (from canon + PRDs + roadmap)

S-01 Simultaneous-lock intent loop (PlanPhase)                    — IMPLEMENTED
S-02 Live actionability-event forecast window (YOMIH rule)        — IMPLEMENTED (core), UI pending
S-03 Frame-data model (state + hitbox records)                    — PARTIAL (strike/grab/move/dodge/block)
S-04 13-action set (Strike, Block, Grab, Move, Thrust, Slash,
     Dodge, Feint, Cancel, Idle, Clinch sub-menu, +2)             — PARTIAL (variants authored; full matrix data not authored)
S-05 Deterministic truth + truth hash + replay                    — IMPLEMENTED
S-06 Golden-replay determinism gate (100-run)                     — IMPLEMENTED (7 scenarios)
S-07 Injury truth (atlas, capability gating, incapacitation)      — IMPLEMENTED (core), atlas population pending
S-08 Grab → clinch sub-exchange with frame data                   — IMPLEMENTED (W1 lane: SecureGrab→Clinch wired live, commit bface6f; clinch sub-menu UI pending)
S-09 Debug mannequin + skeleton overlay + FP/observer camera      — IMPLEMENTED
S-10 Flat-arena game_loop profile + headless --shot harness       — IMPLEMENTED
S-11 Async motion plan service (non-blocking truth)               — IMPLEMENTED (async service; ship lane = live generative provider, W3; baked clips forbidden)
S-12 Generative conditioning (MotionBricks/ARDY primitives)       — OFFLINE RESEARCHED; runtime lane pending
S-13 Interaction-conditioned grab (UNIT-2 line)                   — MACHINE PASS (v13), human gate pending
S-14 Integer-quantized articulated physics (120 Hz)               — IMPLEMENTED
S-15 Forecast timeline UI + what-if ghost                         — NOT STARTED (Canvas design gate first)
S-16 Stance system (high/low/neutral) + tempo gate                — NOT STARTED
S-17 Feint (Free-cancel, 2 charges) + whiff-cancel (75% burst)    — NOT STARTED
S-18 Armor deep material sim (cloth PBD, mail network, plate FEM,
     Rune-Marble/bone fracture)                                    — NOT STARTED
S-19 Full anatomical atlas (bone/muscle/tendon/ligament/organ,
     500–1000 structures)                                          — NOT STARTED (core pipeline only)
S-20 AI opponent (scripted, then personality/adaptive)            — PARTIAL (scripted only)
S-21 Replay theater + fight film                                  — NOT STARTED
S-22 Tutorial                                                     — NOT STARTED (deferred by canon)
S-23 Audio                                                        — NOT STARTED (deferred by canon)
S-24 Local 2P hidden-input duel                                   — NOT STARTED
S-25 Networking/rollback                                          — NOT STARTED (post-slice)
S-26 Content scale-out (3+ fighters, 6+ weapons, 6 loadouts,
     3+ arenas)                                                    — NOT STARTED
S-27 Steam packaging (Linux+Windows+Deck, artifact packaging)     — NOT STARTED
S-28 Hitbox/visual parity suite                                   — PARTIAL (proxies exist; parity suite pending)
S-29 Accessibility/readability audit                              — NOT STARTED
S-30 Agentic playtest harness                                     — PARTIAL (QA tooling exists)
S-31 Meshy AAA asset promotion (JD_Duelist_001 pipeline G0–G5)    — IN PROGRESS (G1 human gate; deferred until loop proven)
S-32 Performance budgets (RTX 5090 → Steam Deck)                  — NOT STARTED

## Part C — 200 proposed features (F-001..F-200)

Owner design principle (2026-07-19, now canon): the generative motion and combat
systems must allow "infinite" combat states, constrained by character archetypes.
Consequences applied throughout this backlog:
- Motion is generated per tick from the live condition packet and resolved by
  deterministic physics; no discrete clip banks, pose banks, or precomputed
  combat-state tables exist anywhere in any mode.
- Character archetypes (learned combat arts, weapon/build, armor class, current
  physical state) bound the reachable intent/motion families — implemented via
  state-conditioned intent availability (F-017..F-020, F-048), archetype
  conditioning tokens (F-026), and archetype-diverse training corpora (F-031).
- The yomi depth comes from a continuous state space, not from a fixed move
  list: two identical intents resolve differently when archetype, momentum,
  injury, and opponent state differ.

### C.1 Combat truth, intent, and yomi depth (F-001..F-020)
F-001 Data-driven 13×13 matchup matrix with per-cell golden tests — H,G — W2 — DONE (772decc; intent::matrix + 169-cell golden + hit-stun interrupt canon fix)
F-002 Per-action timing table derived from motion analysis — H — W2 — DONE (8f87050 table + invariant tests + generated FRAME_DATA.md; MotionBricks provenance swap pending)
F-003 Stance system high/neutral/low affecting matrix rows — H,G — W2 — DONE (508c34d; tempo-economy effects; matrix-row hooks pending F-001)
F-004 Tempo meter with deterministic gain/loss rules — H,G — W2 — DONE (5b1235d gains; 508c34d cost economy + gate per PRD_STANCE_TEMPO)
F-005 Feint (2-charge free-cancel) with cancel-category resolution — H,G — W2 — DONE (charges/spend/recharge/gate, f2e877d; category-graph widening pending F-012)
F-006 Whiff-cancel 2-frame state at 75% burst — H,G — W2 — DONE (f2e877d)
F-007 Burst resource economy (gain on read, spend on cancel/feint) — H,G — W2 — DONE (spend+regen, f2e877d; gain-on-read tuning pending balance pass)
F-008 Perfect-block frame window with full negate vs chip/durability — H,G — W2 — DONE (5b1235d PERFECT_BLOCK_TICKS=3)
F-009 Parry as timed block variant with deflect outcome — H,G — W2 — DONE (5b1235d attacker stagger)
F-010 Counter-hit state (hit during opponent startup) with damage multiplier — H,G — W2 — DONE (5b1235d; instant hit-cancel; damage multiplier pending injury wiring)
F-011 Hit-cancel windows per action (iasa_on_hit) — H — W2 — DONE (existing iasa_on_hit + hit_cancel; dynamic variant in d42a018)
F-012 Free-cancel category graph (grounded/aerial strings) — H — W2 — DONE (a52b1db grounded strings; aerial deferred to air actions)
F-013 Dynamic IASA from hit/block/landing — H — W2 — DONE (d42a018; landing hook deferred to air lane)
F-014 Clinch sub-exchange full frame data + tech/escape options — H,G — W2 — DONE (a3d47e2 frame table + KneeHit outcome)
F-015 Clinch position states (over/under/back-control) with option gating — H,G — W2 — DONE (bf03b3e controller/Overhook→BackControl + role gating)
F-016 Throw/throw-tech deterministic resolution — H,G — W2 — DONE (fbd111a controller-relative tech/whiff/launch rules)
F-017 Ground/pinned state with reduced intent set (state-conditioned options) — H,G — W2 — DONE (834604d downed + getup gate; throw exits clinch)
F-018 Disarm/armed state machine gating strikes vs unarmed options — H,G — W2 — DONE (2685887 parry-deflect disarm + re-arm gate)
F-019 Weapon draw/sheath as intents with vulnerability windows — H,G — W2 — DONE (47c9978 Draw/Sheath intents + sheathed state + 225-cell matrix)
F-020 Range bands (out/jab/mid/clinch) with intent feasibility gating — H — W1 — DONE (06b220c explicit Close/Mid/Far bands + snapshot/HUD; feasibility gating exists via is_feasible)

### C.2 Generative motion and combat fidelity (F-021..F-040)
F-021 Runtime generative provider (feature-gated dev lane) on MotionBricks — H,P — W3 — DONE (c9663f8 dev lane + persistent worker; live clips verified in be90c3d)
F-022 Ship-lane live generative motion provider: per-tick MotionBricks inference from the full condition packet via the async buffered plan service; no baked clips, pose banks, or clip libraries in any mode — H,G,P — W3 — IN PROGRESS (ed2d0be streaming; a9a164c baked demoted to test-only; render-path swap remains)
F-023 Masked condition packet v1 (root keyframes + full-pose keyframes) runtime — H,G — W3 — DONE (be90c3d bridge unblocked: clips generate; keyed-context retry annotated)
F-024 Condition packet v2 retrain: clearance + limb-state tokens — H — W3
F-025 Condition packet v3 retrain: weapon-hand + opponent-state tokens — H — W3
F-026 Condition packet v4 retrain: momentum/speed/velocity + injury-state + archetype-identity tokens — H — W3
F-027 ARDY masked sparse-constraint integration for strike/thrust lanes — H — W3
F-028 Opponent-aware strike conditioning (UNIT-3 line, paired corpus) — H,V — W3
F-029 Opponent-aware clinch conditioning (UNIT-4 line) — H,V — W3
F-030 Opponent-aware dodge reactive-fit conditioning — H,V — W3
F-031 NVIDIA-scale corpus intake (AMASS + BONES-SEED + CMU + Harmony4D + Kyokushin + KungfuAthleteBot) for full vocabulary — H — W3
F-032 Per-style held-out gates (report per-corpus pass rates, no global best-case) — H — W3
F-033 Exhaustive multiview contact sheets for every trained motion PASS — V — W3
F-034 Distinct readable reveal tells for all 13 actions — V,A — W5
F-035 Locomotion displacement conditioning per truth-tick — H,G — W3
F-036 Transition-blend generation between intents (no pop) — V — W5
F-037 Motion vocabulary manifest with per-action provenance — H — W3
F-038 V2M teacher lane (licensed combat video → retarget) operationalized — H — W3
F-039 In-game visual harness stress-testing motion-system limits (owner mandate) — H,V — W3
F-040 Latency budget harness proving 120 Hz truth never waits on inference — H,P — W3

### C.3 Deep injury and armor simulation (F-041..F-060)
F-041 Anatomical atlas population to 500–1000 stable-ID structures — H — W4
F-042 Bone layer: fracture thresholds + displacement — H,G — W4
F-043 Muscle layer: tear/strain capability loss — H,G — W4
F-044 Tendon/ligament layer: ROM and joint-stability loss — H,G — W4
F-045 Organ layer: vital incapacitation paths — H,G — W4
F-046 Bleeding/fatigue-over-time model (deterministic tick decay) — H,G — W4
F-047 Pain/stagger response affecting IASA and movement — H,G — W4
F-048 Limb capability loss → intent availability gating (state-conditioned options) — H,G — W4
F-049 Injury-conditioned motion (limp, guarded arm) via condition packet — V — W4
F-050 Persistent damage event records for replay/save — H,G — W4
F-051 Cloth armor PBD layer — H — W4
F-052 Chainmail constraint-network layer — H — W4
F-053 Plate armor FEM-lite response — H — W4
F-054 Rune-Marble/bone brittle fracture model — H — W4
F-055 Material resistance table + residual-force routing into injury — H,G — W4
F-056 Armor damage visual state (deformation/decals) driven by truth — V — W5
F-057 Hitbox parity maintained through deformed/destroyed armor — H,V — W4
F-058 AI awareness of injury/armor state in intent selection — H,A — W4
F-059 Incapacitation determination with multi-path endings (KO, bleed-out, limb loss) — H,G — W4
F-060 Injury/armor replay-stable serialization — H,G — W4

### C.4 AI, personalities, and mind games (F-061..F-075)
F-061 Deterministic seeded AI core (same seed = same match) — H,G — W2
F-062 AI personality set (aggressive/turtle/counter/baiter) — H,A — W6
F-063 Pattern-memory AI that punishes repeated player habits — H,A — W6
F-064 Bait behavior (whiff-to-punish) as authored intent strings — H,A — W6
F-065 Conditioning layer (AI feints after conditioning a response) — A,X — W6
F-066 Difficulty ladder (5+ tiers) with measurable win rates — A — W6
F-067 Read-assist trainer AI that exposes its own tells for learning — X — W7
F-068 Agentic self-play harness for balance data — A — W6
F-069 Matchup heatmap from self-play (per-action win rates) — A — W2
F-070 Tilt/adaptation curve per personality — A — W6
F-071 AI use of full intent set incl. clinch/throw/feint — A — W6
F-072 Boss/rival scripted personalities for arcade ladder — X — W8
F-073 Spectator legibility pass (AI choices readable from motion) — V — W5
F-074 Deterministic AI in replays (no divergence on re-sim) — G — W2
F-075 Balance gate: no action >60% pick or <5% pick across self-play — A — W8

### C.5 Renderer and visual fidelity (F-076..F-095)
F-076 PBR material pipeline for characters/weapons/arena — V — W5
F-077 Skeletal skinning parity vs truth proxies (read-only) — H,V — W5
F-078 Contact spark/impact VFX keyed to truth contact events — V — W5
F-079 Blood/wound decals driven by injury truth — V — W5
F-080 Armor deformation/destruction visual states — V — W5
F-081 Motion smear/afterimage for reveal readability — V — W5
F-082 Anime-style rim light + ink line option — V — W5
F-083 Dynamic shadows + contact shadows at target budget — P — W5
F-084 HDR + tonemapping pass — V — W5
F-085 Depth-of-field for fight-film cameras only (never gameplay) — V — W6
F-086 Arena lighting variants (3+ readable lighting moods) — V — W8
F-087 Damage-reactive camera shake (presentation-only, capped) — V,X — W5
F-088 Skeleton/hitbox dev overlay (hidden toggle) — H — W1
F-089 Meshy AAA character promotion (JD_Duelist_001 G1→G5) — V — W8
F-090 Weapon visual set (6+) with silhouette readability — V — W8
F-091 Armor/loadout silhouettes (6 classes) — V — W8
F-092 Arena set (3+) with readability-certified layouts — V — W8
F-093 Cloth/hair sim (presentation-only, deterministic-cost) — V,P — W5
F-084b F-094 GPU skinning path for Deck budget — P — W10
F-095 Visual QA matrix harness (content × lighting × action grid) — V — W8

### C.6 Audio (F-096..F-108)
F-096 Audio engine integration (kira/rodio decision per canon) — H — W5
F-097 Commit/reveal/UI cue set — X — W5
F-098 Per-action wind-up tells synchronized to motion phase markers — V,A — W5
F-099 Contact impact layers by material × force — X — W5
F-100 Armor-class movement noise (ROM/noise modifiers audible) — X — W5
F-101 Injury vocalizations/breathing state layer — X — W5
F-102 Crowd/arena ambience per arena — X — W8
F-103 Adaptive tension score tied to tempo/match state — X — W5
F-104 Clinch/ground foley set — X — W5
F-105 Replay-theater mix mode (cinematic ducking) — X — W6
F-106 Accessibility audio cues (directional contact, action callouts option) — X — W7
F-107 Mix buses + loudness normalization + options sliders — X — W10
F-108 Steam Deck audio latency budget pass — P — W10

### C.7 UI/UX, camera, and readability (F-109..F-125)
F-109 Hermes Canvas design gate for all HUD/menu work (authority) — process — W1 — DONE (FORECAST_HUD_DESIGN.md, canvas-c602d5588727 r4, visual QA pass)
F-110 Forecast timeline UI (predicted frames before lock) — H,V,X — W1 — DONE (engine 49d200c + HUD 3784607; ForgeLens review pending)
F-111 What-if ghost (select opponent move in planning, preview sim) — H,V,X — W1 — DONE (3dba031 ghosts + planning freeze; ForgeLens review pending)
F-112 Intent list UI with state-conditioned availability display — V,X — W1 — DONE (3784607; dimming wired to intent_available)
F-113 Injury readout UI (anatomical, readable, non-debug) — V,X — W4
F-114 Tempo/burst meters UI — V,X — W2
F-115 Match flow states (intro/engage/endslow/results) — X — W5
F-116 First-person camera polish (head-bob none, tells never hidden) — V,X — W5
F-117 Observer/free camera toggle — H — done-partial
F-118 Kill-cam/incapacitation slow-mo from replay system — V — W6
F-119 Main menu + mode select (duel/replay/tutorial/options) — X — W7
F-120 Controls menu + remapping — X — W7
F-121 Options menu (video/audio/gameplay/accessibility) — X — W7
F-122 Pause flow with deterministic state freeze — H,G — W7
F-123 On-screen reveal banners ("I read you" moment framing) — X — W5
F-124 Localization-ready string table — S — W10
F-125 No-placeholder-UI gate for Player mode (canon) — V — W7

### C.8 Replay theater, fight film, and social (F-126..F-140)
F-126 Replay browser with metadata (date/result/duration/actions) — X — W6
F-127 Frame-step + slow-mo scrub in replay — H,X — W6
F-128 Contact inspection view (hitbox/injury visualization) — V — W6
F-129 Truth-hash comparison display in replay — H — W6
F-130 Free cinematic camera with spline paths — V — W6
F-131 Auto fight-film edit (best-exchange selection heuristic) — A,V — W6
F-132 Replay file export/import (shareable) — S — W6
F-133 Clip capture (MP4/GIF export) for creator loop — S — W6
F-134 Highlight tagging (auto-mark reads, perfects, comebacks) — A — W6
F-135 Match stats screen (accuracy, reads, damage by region) — X — W6
F-136 Local 2P hidden-input duel mode — X — W8
F-137 Rivalry tracking (local session history) — X — W8
F-138 Daily seed / challenge modifiers (post-launch lane) — A — W11
F-139 Spectator mode for local sessions — X — W8
F-140 Share-code for replay + loadout — S — W6

### C.9 Tutorial, onboarding, accessibility (F-141..F-152)
F-141 In-match tutorial duel (teach-by-playing per canon) — X — W7
F-142 Triangle lesson (Strike/Block/Grab) scripted sequence — X — W7
F-143 Advanced counters lesson (Dodge/Thrust/Parry/Feint) — X — W7
F-144 Injury/armor lesson — X — W7
F-145 Forecast/what-if lesson — X — W7
F-146 Practice mode (recordable dummy, frame-data overlay) — H,X — W7
F-147 Colorblind-safe UI palette option — V,X — W7
F-148 One-hand / remappable-full control scheme — X — W7
F-149 Photosensitivity-safe flash limits — X — W7
F-150 Subtitle/visual cue equivalents for audio tells — X — W7
F-151 Difficulty assist options (wider perfect-block window etc., labeled) — X — W7
F-152 Accessibility audit receipt — X — W11

### C.10 Networking and competitive (F-153..F-165)
F-153 Remote input source abstraction — H — W9
F-154 Snapshot/restore for rollback — H,G — W9
F-155 Prediction + rollback core (GGRS-pattern, custom) — H,G — W9
F-156 Desync detection + auto-report bundle — H — W9
F-157 Network test harness (simulated latency/loss/jitter) — H — W9
F-158 Direct-IP match flow — X — W9
F-159 Minimal matchmaking (post-launch lane) — S — W9
F-160 Ranked ladder infra (post-launch lane) — S — W11
F-161 Input delay tuning UX — X — W9
F-162 Rollback-safe deep-sim serialization — H,G — W9
F-163 100-match no-unresolved-desync gate — H — W9
F-164 Anti-cheat via deterministic re-sim verification — H — W9
F-165 Spectator netcode (post-launch lane) — S — W11

### C.11 Platform, performance, and Steam (F-166..F-185)
F-166 Linux packaged executable (no repo path) — S — W10
F-167 Windows build + CI — S — W10
F-168 Steam Deck verified performance profile (60 Hz truth, battery) — P,S — W10
F-169 Steamworks SDK integration (achievements/stats/cloud) — S — W10
F-170 Achievement set (20+, incl. read/film/community) — S — W10
F-171 Steam cloud saves — S — W10
F-172 Crash logging + minidump pipeline — S — W10
F-173 Settings persistence + versioning — H — W10
F-174 Asset packaging incl. MotionBricks ONNX/NPY artifacts (canon: missing = build-blocker) — S — W10
F-175 Version/changelog automation — S — W10
F-176 Perf budget: frame time p99 on target hardware — P — W10
F-177 Loading-time budget pass — P — W10
F-178 Memory budget pass (atlas + clips + textures) — P — W10
F-179 Store page material (capsule set, description, tags) — S — W10
F-180 Trailer + fight-film captures for store — V — W10
F-181 Demo build lane (Steam Next Fest style) — S — W10
F-182 Patch policy preserving replay compatibility (canon) — S — W11
F-183 Save/replay forward-compat schema versioning — H — W10
F-184 Clean-machine install test gate — S — W10
F-185 Controller support (gamepad full mapping) — X,S — W7

### C.12 QA, telemetry, and live-ops (F-186..F-200)
F-186 Agentic playtest suite (self-driving matches, bug receipts) — A — W11
F-187 Balance telemetry (opt-in, anonymized; dev-only leaderboard) — A — W11
F-188 Regression suite wiring (fmt/clippy/test/golden/parity in CI) — H — W10
F-189 Hitbox/visual parity suite across all content — H,V — W11
F-190 Replay hash suite across all scenarios — G — W11
F-191 Fuzz harness for intent/matrix resolution (no panic, no desync) — H — W11
F-192 Determinism canary in CI (fixed match hash) — H — W10
F-193 Performance regression gate in CI — P — W10
F-194 Known-blocker register with evidence links — process — W11
F-195 30-minute fun-retention playtest gate — X — W8
F-196 First-time-player onboarding gate (unaided tutorial+match) — X — W7
F-197 Blind read test (80%+ action ID from 8 reveal frames) — A,X — W5
F-198 Clip-worthiness gate (every match ≥1 shareable moment, sampled) — A,X — W8
F-199 Release-candidate checklist execution — S — W11
F-200 Post-launch live-ops cadence (crash review, balance review, content gates) — S — W12

## Part D — Waves

W1 Loop closure (now): F-020, F-088, F-110..F-112 + grab-closure in-flight unit.
W2 Combat depth: F-001..F-013, F-061, F-069, F-074.
W3 Generative motion runtime: F-021..F-040.
W4 Deep injury/armor: F-041..F-060.
W5 Presentation fidelity: F-034, F-036, F-056, F-073, F-076..F-087, F-093,
   F-096..F-105, F-107, F-115..F-116, F-123, F-197.
W6 Replay/social/AI depth: F-062..F-068, F-070..F-072, F-085, F-126..F-135, F-140.
W7 Tutorial/UX/accessibility: F-067, F-106, F-119..F-122, F-124..F-125,
   F-141..F-151, F-185, F-196.
W8 Content complete: F-075, F-086, F-089..F-092, F-095, F-102, F-136..F-139,
   F-195, F-198.
W9 Networking: F-153..F-165.
W10 Platform/Steam/perf: F-094, F-108, F-124, F-166..F-186 (platform subset),
   F-188, F-192..F-193.
W11 Final QA/RC: F-138, F-152, F-160, F-165, F-182, F-186..F-194, F-199.
W12 Launch/live: F-200.

## Part E — Canon amendment record (owner decisions)

E-1 RESOLVED 2026-07-19: baked clips are forbidden in every mode and tier. The
   ship lane is the live generative MotionBricks provider via the async buffered
   plan service (F-022). Documents amended: GAME_CANON.md, PHASED-PRODUCTION-PLAN.md,
   ARCHITECTURE.md, SYSTEMS-DESIGN.md, JD_RC0_TRUTH_BASELINE_2026-07-17.md,
   plans/2026-07-09-just-dodge-9action-expansion.md. The M4 dev-scaffolding
   provider is explicitly not a ship path; W3 replaces it with the runtime
   generative lane before any packaging claim (F-174 gate).
E-2 OPEN: networking pre-launch vs post-launch — roadmap Phase 9 places
   multiplayer before packaging; canon says networking only after vertical slice
   is accepted fun. Backlog sequences W9 after W8 accordingly. Confirm whether
   launch includes online play or launches local-first with online as a
   post-launch patch.
E-3 RESOLVED 2026-07-19: generative motion and combat must allow "infinite"
   combat states constrained by character archetypes — canonized in
   GAME_CANON.md (continuous combat state space + archetype constraint).
