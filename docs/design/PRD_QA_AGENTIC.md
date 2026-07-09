# PRD: QA and Agentic Playtesting

## 1. Purpose

Make every build falsifiable, replayable, and inspectable through deterministic tests, hitbox/visual parity checks, deep simulation verification, visual QA captures, and bounded agentic playtesting without replacing human feel judgment.

## 2. Invariants

- QA agents use the same surfaces as players: input, screenshots, replay.
- Agentic playtesting produces reproducible bugs or regression candidates.
- Human playtesting remains required for fun/readiness gates.
- Hitbox/visual parity mismatches are P0 bugs; no build advances with ghost hits or oversized hitboxes.
- Deep simulation outputs (material, injury, motion) must be deterministic and truth-hash stable.
- No screenshot-only progress claims are accepted.

## 3. Interface Contract

### Inputs
| Name | Type | Source | Description |
|---|---|---|---|
| build_artifact | executable | Build system | Game build under test |
| test_plan | TestPlan | QA protocol | Objectives, allowed inputs, pass criteria |
| replay_file | bytes | PRD_REPLAY.md | Golden regression inputs |
| parity_report | ParityReport | PRD_COMBAT_TRUTH.md | Hitbox/visual mismatch evidence |

### Outputs
| Name | Type | Consumer | Description |
|---|---|---|---|
| test_report | Report | Development team | Pass/fail, evidence, bugs |
| bug_report | BugReport | Issue tracker | Reproducible bug with replay |
| capture_set | PNGs/video | Visual audit | Screenshots per phase |
| parity_audit | ParityAudit | Development team | Hitbox/visual overlay comparison |

### Events / Signals
| Event | Payload | When Fired |
|---|---|---|
| test_failed | { reason, evidence } | When a test does not pass |
| regression_found | { expected_hash, actual_hash } | Golden replay mismatch |
| parity_violation | { frame_index, proxy_id, visual_id, mismatch } | Hitbox does not match visual geometry |

## 4. Data Flow

1. Build artifact is produced.
2. Deterministic tests run: resolver, matrix, replay hash, renderer on/off equivalence.
3. Hitbox/visual parity tests compare collision proxies against rendered geometry.
4. Deep simulation determinism tests run for armor, injury, and motion.
5. Runtime smoke tests launch the executable and complete basic interactions.
6. Agentic playtests run bounded scenarios.
7. Visual QA captures are audited for MotionBricks-driven readability tiers and material fidelity.
8. Human playtests evaluate fun, friction, and hitbox trust.
9. Reports are written to `docs/reports/`.

## 5. Control Flow

- **Who calls it:** CI or developer manually.
- **Tick rate:** Build-time and test-time.
- **Threading model:** Deterministic tests run single-threaded; agentic tests may run in parallel.

## 6. Error Handling

- **Fail-closed:** any failed truth hash test blocks advancement.
- **Fail-closed:** any hitbox/visual parity violation blocks advancement.
- **Fail-open:** visual QA issues are tiered; lower tiers do not block but must be tracked.
- **Degradation:** if agentic tools are unavailable, human playtests and deterministic tests remain mandatory.

## 7. Performance Budget

| Metric | Target | Worst Acceptable |
|---|---|---|
| Deterministic test suite | <30 s | 120 s |
| Hitbox parity test | <10 s/action | 60 s |
| Agentic smoke test | <5 min | 15 min |
| Visual QA capture | <2 min per state | 10 min |

## 8. Dependencies

- PRD_COMBAT_TRUTH.md — deterministic tests, hitbox parity reports.
- PRD_REPLAY.md — regression tests use replay files.
- PRD_RENDERER.md — visual QA captures frames.
- PRD_MOTION.md — hitbox proxy source for parity checks.
- PRD_ARMOR.md, PRD_INJURY.md — deep simulation determinism tests.
- PRD_UI_UX.md — mode-correctness checks.

## 9. Open Questions

- Agent framework (cua-driver, custom script, external tool).
- Automated hitbox/visual overlay comparison method.
- JSON QA state snapshot exposure.

## 10. Agent Notes

### 2026-07-09 — @kimi
- **Decision:** Hitbox/visual parity is a P0 gate; deep simulation determinism is tested before milestone advance.
- **Rationale:** User canon amendment: For Honor fidelity with perfect hitboxes and no ghost hits.
- **Blocker:** Automated parity tooling must be built; deep solvers must be deterministic.
- **Status:** ACTIVE.
- **Next:** Create a hitbox/visual overlay tool and parity test for one action before scaling to the full action set.
