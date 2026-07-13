# Verifiable Milestones — Just Dodge

## Milestone 0: Design Lock

**Definition:** Core design is written, reviewed, and accepted.
**Acceptance Criteria:**
- [ ] `docs/GDD.md` approved.
- [ ] `docs/COMBAT-SYSTEM.md` approved.
- [ ] `docs/TECH-STACK.md` approved.
- [ ] `docs/ROADMAP.md` approved.

**Evidence:** All docs committed to git.

## Milestone 1: Paper Prototype Pass

**Definition:** 3-action paper prototype proves YOMI fun.
**Acceptance Criteria:**
- [ ] `docs/reports/PROTOTYPE_01_PAPER_YOMI.md` exists.
- [ ] Result is PASS or PIVOT with clear next step.
- [ ] At least 10 matches played and logged.

**Evidence:** Report file + playtest notes.

## Milestone 2: Shape Prototype Pass

**Definition:** Digital 3-action prototype is playable and fun.
**Acceptance Criteria:**
- [ ] Rust/wgpu executable compiles and runs.
- [ ] Player can complete 5 matches without explanation.
- [ ] `docs/reports/PROTOTYPE_02_SHAPE_PROTOTYPE.md` says CONTINUE.
- [ ] No production code claimed; prototype code is throwaway.

**Evidence:** Playable build + report + screen recording.

## Milestone 3: First Playable

**Definition:** Complete single-exchange duel, ugly but functional.
**Current status:** BLOCKED. Packet-driven deterministic core, replay verification, 120 Hz cleanbox reduction, and static armored-duelist import are verified. Runtime action motion, pose-derived contact, five human packaged matches, canonical media, and redistribution-rights evidence are not. See `docs/reports/MILESTONE_03_FIRST_PLAYABLE_REPORT.md` and `docs/reports/DEVELOPMENT_TASKLIST.md`.
**Acceptance Criteria:**
- [ ] Full match loop: menu → setup → observe → plan → commit → reveal → resolve → consequence → match result.
- [ ] 3 actions with injury and win/loss.
- [ ] Packaged Linux executable runs on clean machine.
- [ ] First-time player plays one match unaided.

**Evidence:** Executable + playtest video + no-crash verification.

## Milestone 4: Vertical Slice

**Definition:** 13 actions, localized injury, armor/loadout consequences, AI, readable motion.
**Acceptance Criteria:**
- [ ] Full 13×13 matrix resolves correctly.
- [ ] Localized injury affects gameplay.
- [ ] Armor integrity, persistent damage state, ROM, noise, and residual-force routing affect gameplay without hiding the YOMI read.
- [ ] AI has 3+ personalities.
- [ ] MotionBricks interpolation and retargeting active.
- [ ] Truth hash stable across runs.
- [ ] 10 playtests, each with at least one "great exchange."

**Evidence:** Playtest logs + truth hash report + build.

## Milestone 5: Content Complete

**Definition:** Multiple fighters, weapons, arenas, tutorial, and local 2P.
**Acceptance Criteria:**
- [ ] 3+ fighters, 6+ weapons, 3+ arenas.
- [ ] Tutorial mode teaches the triangle.
- [ ] Local duel mode for two human players.
- [ ] No placeholder UI in player mode.

**Evidence:** Feature-complete build + UI/UX review.

## Milestone 6: Multiplayer Ready

**Definition:** Online 1v1 with rollback netcode.
**Acceptance Criteria:**
- [ ] Remote matches run without desync.
- [ ] Rollback is imperceptible in typical conditions.
- [ ] 100+ test matches played.

**Evidence:** Network test logs + stress test report.

## Milestone 7: Steam Launch

**Definition:** Game is released on Steam.
**Acceptance Criteria:**
- [ ] Store page live.
- [ ] Build uploaded and passed Steam review.
- [ ] Trailer and press kit complete.

**Evidence:** Steam store URL + launch announcement.

## Milestone Review Process

1. Declare milestone target at start.
2. Build toward acceptance criteria.
3. Run verification commands and capture output.
4. Write milestone report in `docs/reports/`.
5. Mentor review: challenge evidence, accept or reject.
6. Only advance on acceptance.
