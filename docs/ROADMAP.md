# Full Roadmap — Just Dodge

## Philosophy

No production code until the corresponding prototype says CONTINUE. Every stage ends with a verification gate. If a gate fails, we do not advance; we fix or kill the feature.

This roadmap assumes a solo developer with mentoring, building a custom Rust/wgpu engine. Scale timelines if scope or availability changes.

Expanded architecture, systems, QA, and full production planning lives in:

- `docs/ARCHITECTURE.md`
- `docs/SYSTEMS-DESIGN.md`
- `docs/PHASED-PRODUCTION-PLAN.md`
- `docs/QA-AGENTIC-PLAYTESTING.md`
- `docs/FILE-INVENTORY-AUDIT.md`

## Stage 0: Foundation (Weeks 1–3)

**Goal:** Lock the core design and prove it is fun on paper and with the smallest possible custom engine.

- [ ] Complete `docs/GDD.md` v1.
- [ ] Complete `docs/COMBAT-SYSTEM.md` v1 (13-action matrix).
- [ ] Complete `docs/TECH-STACK.md` v1 (custom Rust/wgpu).
- [ ] Complete `docs/ENGINE-SKELETON.md` v1.
- [ ] Complete `docs/MOTIONBRICKS-RETARGETING.md` v1.
- [ ] Complete `docs/ARMOR-DAMAGE-SYSTEM.md` v1.
- [ ] Paper prototype: 3-action YOMI triangle.
- [ ] Paper prototype report: result + decision.
- [ ] Shape prototype: 3-action triangles in minimal custom engine.
- [ ] Shape prototype report: result + decision.
- [ ] Initialize Rust project with `cargo init`.
- [ ] Set up git + `.gitignore` + `docs/CHANGELOG.md`.

**Gate:** Shape prototype is measurably fun in a 2-minute playtest.

## Stage 1: First Playable (Weeks 4–10)

**Goal:** A complete, ugly, single-exchange duel that can be played start to finish in the custom engine.

- [ ] Implement minimal engine skeleton (window, input, renderer, text).
- [ ] Implement combat state machine: Observe → Plan → Commit → Reveal → Resolve → Consequence → loop.
- [ ] Implement 3-action resolver with health and win/loss.
- [ ] Local input: hidden selection for two players or player vs simple AI.
- [ ] Basic UI: health, selected action, opponent reveal, result text.
- [ ] Simple audio feedback: beeps for wind-up, contact, block.
- [ ] Replay recording and playback of one exchange.
- [ ] Packaged executable for Linux.

**Gate:** A first-time player can play one full match without explanation.

## Stage 2: Vertical Slice (Weeks 11–26)

**Goal:** Expand to 13 actions, add localized injury, AI personalities, and readable motion.

- [ ] Implement full 13×13 matchup matrix as data.
- [ ] Localized body-part injury system.
- [ ] Armor slot/integrity/persistent-damage model connected to localized injury.
- [ ] Stance system (high / low / neutral).
- [ ] Tempo / stamina gate.
- [ ] Deterministic AI with personalities.
- [ ] MotionBricks-style procedural pose interpolation.
- [ ] MotionBricks retargeting from 29-joint output to mannequin skeleton.
- [ ] Weapon socket attachment and basic weapon models.
- [ ] Readable action tells: pose, audio, camera.
- [ ] Post-match replay viewer.
- [ ] Fight Film auto-cinematic.
- [ ] Packaging + clean executable verification.

**Gate:** 10 internal playtests produce at least one "great exchange" each; truth hash stable; armor/loadout choices create readable counterplay instead of hidden stat arithmetic.

## Stage 3: Content & Polish (Weeks 27–50)

**Goal:** Multiple fighters, weapons, arenas, and a coherent progression loop.

- [ ] 3+ distinct fighters with different base stats.
- [ ] 6+ weapons with unique timing profiles.
- [ ] 6 armor/loadout identities with visible tradeoffs in ROM, noise, and protection.
- [ ] 3+ arenas with different lighting/readability challenges.
- [ ] Tutorial mode.
- [ ] Local duel mode for two human players.
- [ ] Basic progression: unlocks via matches played, not loot boxes.
- [ ] Options menu: controls, video, audio.
- [ ] Full sound design pass.
- [ ] UI/UX readability pass.

**Gate:** Game is fun for 30+ minutes in one sitting; no placeholder UI in player mode.

## Stage 4: Multiplayer & Steam (Weeks 51–74)

**Goal:** Online 1v1 with rollback netcode and Steam release.

- [ ] Local simulation supports remote input injection.
- [ ] Rollback netcode implementation.
- [ ] Matchmaking or direct IP.
- [ ] Steam integration (API, invites, leaderboards).
- [ ] Achievements.
- [ ] Closed beta with external players.
- [ ] Balance tuning from telemetry.

**Gate:** 100+ online matches played with < 100 ms perceived latency; no desyncs.

## Stage 5: Launch + Live Ops (Weeks 75+)

**Goal:** Ship and support.

- [ ] Final QA pass.
- [ ] Store page, trailer, press kit.
- [ ] Launch.
- [ ] Post-launch balance patches.
- [ ] New content drops (fighters, arenas).

**Gate:** Player reviews reflect the core fantasy; retention metrics meet target.

## Milestone Cadence

- Every stage is split into 2-week sprints.
- Each sprint ends with a playable build.
- Each build is recorded and reviewed.
- No sprint advances until the previous one is accepted.

## Scope Kill Criteria

We will cut any feature that:
- does not directly improve the YOMI exchange,
- cannot be verified in under 2 weeks,
- destabilizes the truth hash,
- is justified by "AAA games do it" rather than "our game needs it."
