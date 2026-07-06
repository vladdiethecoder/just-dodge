# Master Development Checklist — Just Dodge

## Pre-Production

- [ ] Read `docs/GDD.md`, `docs/ROADMAP.md`, `docs/LESSONS-FROM-OATHYARD.md`, `docs/ENGINE-SKELETON.md`, `docs/MOTIONBRICKS-RETARGETING.md`, and `docs/ARMOR-DAMAGE-SYSTEM.md`.
- [ ] Install Rust toolchain and verify `cargo` works.
- [ ] Initialize git repo in project root.
- [ ] Add `.gitignore` for Rust projects.
- [ ] Create `docs/reports/` directory.
- [ ] Verify no production code exists yet.

## Paper Prototype (Milestone 1) — SKIPPED

- [x] Skipped by user decision.
- [ ] First design validation will happen in the Shape Prototype.

## Shape Prototype (Milestone 2)

- [ ] Run `cargo init` in project root.
- [ ] Add `winit`, `wgpu`, `glam` to `Cargo.toml`.
- [ ] Open a window.
- [ ] Render two colored triangles.
- [ ] Render text for health and state.
- [ ] Add player input script: Strike (Z), Block (X), Grab (C).
- [ ] Add AI script: random or last-action counter.
- [ ] Implement simultaneous reveal countdown.
- [ ] Implement 3×3 matchup resolver.
- [ ] Add health bars and win/loss text.
- [ ] Add restart on R.
- [ ] Play 50 matches and log.
- [ ] Write `docs/reports/PROTOTYPE_02_SHAPE_PROTOTYPE_REPORT.md`.
- [ ] Decide KILL / PIVOT / CONTINUE.

## First Playable (Milestone 3)

- [ ] Rewrite production code from scratch (do not reuse prototype).
- [ ] Implement minimal engine skeleton cleanly.
- [ ] Implement combat state machine.
- [ ] Implement 3-action resolver + injury.
- [ ] Implement match setup (fighter/weapon/arena selection screens).
- [ ] Implement HUD with state-specific text.
- [ ] Implement first-person placeholder camera.
- [ ] Implement opponent visible in scene.
- [ ] Implement replay recording of one exchange.
- [ ] Implement packaged Linux build script.
- [ ] Verify executable runs on clean machine.
- [ ] First-time player plays unaided.

## Vertical Slice (Milestone 4)

- [ ] Author full 13×13 matchup matrix as data.
- [ ] Implement localized body-part injury.
- [ ] Implement armor slots, integrity states, and residual-force injury routing.
- [ ] Implement stance system.
- [ ] Implement tempo gate.
- [ ] Implement AI personalities.
- [ ] Implement MotionBricks pose interpolation.
- [ ] Retarget MotionBricks 29-joint output onto the combat mannequin.
- [ ] Attach weapon models to fighters.
- [ ] Add readable action tells (pose + audio + camera).
- [ ] Add replay viewer.
- [ ] Add fight film cinematic.
- [ ] Run truth hash regression test.
- [ ] Run 10 playtests, log "great exchange" count.

## Content Complete (Milestone 5)

- [ ] Create 3+ fighters with distinct stats.
- [ ] Create 6+ weapons with timing profiles.
- [ ] Create armor/loadout identities with visible ROM, noise, weight, and protection tradeoffs.
- [ ] Create 3+ arenas.
- [ ] Build tutorial mode.
- [ ] Build local 2P mode.
- [ ] Build options menu.
- [ ] Final UI/UX pass; no placeholder UI in player mode.
- [ ] Full sound design pass.

## Multiplayer (Milestone 6)

- [ ] Refactor input system for remote injection.
- [ ] Implement rollback netcode.
- [ ] Implement matchmaking or direct IP.
- [ ] Run 100+ network matches.
- [ ] Fix all desyncs.

## Launch (Milestone 7)

- [ ] Final QA pass.
- [ ] Create Steam store page.
- [ ] Create trailer and press kit.
- [ ] Upload build to Steam.
- [ ] Launch.

## Weekly Rituals

- [ ] Record 2 minutes of own play.
- [ ] Note exact moment of boredom or friction.
- [ ] Fix that one thing before adding features.
- [ ] Update `docs/CHANGELOG.md`.
- [ ] Commit working state.

## Mentor Review Gates

- [ ] Before Stage 1: review paper + shape prototype reports.
- [ ] Before Stage 2: review first playable build.
- [ ] Before Stage 3: review vertical slice evidence.
- [ ] Before Stage 4: review content-complete build.
- [ ] Before Stage 5: review multiplayer stress test.
- [ ] Before Stage 6: review launch readiness evidence.
