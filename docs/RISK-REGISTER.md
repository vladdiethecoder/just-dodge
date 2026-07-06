# Risk Register — Just Dodge

## How to Use This

Every risk has a likelihood, impact, mitigation, and owner. Review this weekly. New risks are added at the bottom. Closed risks are moved to `docs/reports/CLOSED-RISKS.md`.

## Active Risks

### RISK-001: Scope expands to match AAA reference games

- **Likelihood:** High
- **Impact:** Project never ships.
- **Mitigation:** Enforce vertical-slice gates. Any feature not improving the core YOMI exchange is cut. Weekly scope review with mentor.
- **Owner:** Developer

### RISK-002: Custom engine scope expands beyond the game’s needs

- **Likelihood:** High
- **Impact:** Months lost to engine infrastructure before combat is fun.
- **Mitigation:** `docs/ENGINE-SKELETON.md` is binding. Build only what the current prototype needs. General engine features are forbidden unless required by the next milestone. Mentor will push back.
- **Owner:** Developer + Mentor

### RISK-003: Physics engine built before gameplay loop is proven

- **Likelihood:** Medium
- **Impact:** Determinism nightmares, slow iteration, unreadable combat.
- **Mitigation:** No physics engine in Stages 0–2. Use deterministic geometric collision and authored matchup data. Physics is only added if the vertical slice proves it is necessary.
- **Owner:** Developer

### RISK-004: 13-action matrix is too complex for novices

- **Likelihood:** Medium
- **Impact:** Players bounce off the tutorial.
- **Mitigation:** Prototype 3 tests the full matrix. If players use < 6 actions, simplify or gate unlocks.
- **Owner:** Developer

### RISK-005: Determinism breaks silently

- **Likelihood:** Medium
- **Impact:** Replays desync, netcode impossible, truth hash drifts.
- **Mitigation:** Truth hash test runs on every build. Presentation layer explicitly isolated. No unseeded randomness in combat.
- **Owner:** Developer

### RISK-006: Network rollback added too early

- **Likelihood:** Medium
- **Impact:** Months spent on netcode for a game that is not fun locally.
- **Mitigation:** Networking is Stage 4, gated by vertical-slice acceptance. Direct IP only at first.
- **Owner:** Mentor

### RISK-007: Asset pipeline blocks production

- **Likelihood:** Medium
- **Impact:** No credible fighters/weapons in build.
- **Mitigation:** Build with triangles until Milestone 4. Asset validator tool created early. Use Meshy/Rodin/AAA assets only after pipeline is proven.
- **Owner:** Developer

### RISK-008: First-person camera hides opponent tells

- **Likelihood:** High
- **Impact:** YOMI read becomes impossible; game is random.
- **Mitigation:** Prototype 4 is a readability blind test. If player cannot identify action 80%+ of the time, redesign tells (camera, audio, peripheral vision) before adding content.
- **Owner:** Developer

### RISK-009: Solo development burnout

- **Likelihood:** High
- **Impact:** Project abandoned mid-stage.
- **Mitigation:** 2-week sprints with playable builds. Celebrate small wins. Cut scope aggressively. Mentor provides external accountability.
- **Owner:** Developer + Mentor

### RISK-010: Placeholder UI becomes permanent

- **Likelihood:** Medium
- **Impact:** Player mode feels unfinished at launch.
- **Mitigation:** Explicit no-placeholder-UI rule. Separate dev/player modes. UI/UX pass scheduled in Milestone 5.
- **Owner:** Developer

## Closed Risks

None yet.

## Risk Review Schedule

- Weekly: scan active risks and update status.
- Per milestone: add new risks, close mitigated risks.
- Per pivot: re-evaluate all risks against new direction.
