# Historical Milestone 3 PLAYABLE-PROOF Report

> Superseded as current authority on 2026-07-21. The revision-scoped evidence
> below remains historical. Current authority is
> `docs/evidence_quarantine/SG01-EVIDENCE-CANON-RESET-002/clean_checkout_receipt.json`.
> Local clean-checkout gates pass at `3caa1ec680d181b244affb25ff1826a74ea6cc3b`; SG01 remains blocked on same-commit remote CI and PLAYABLE-PROOF is not passed.

- PLAYABLE-PROOF gate: **NOT PASSED**
- Current audit baseline: published PVP-005 feature baseline `4e481ccd59602c1cb4eda97183c32dec48f9a801`; historical evidence remains bound to its recorded ancestor revisions
- Branch: `pvp-005-readable-live-motion`; one worktree
- Evaluation date: 2026-07-14

## Verified engineering evidence

| Requirement | Evidence | Result |
|---|---|---|
| Canonical Strike/Block/Grab truth state | `src/milestone3.rs`; focused M3 tests | Pass |
| Hidden intent stays hidden until Reveal | M3 hidden-intent regression | Pass |
| Resolve requires a physical packet | `resolve_holds_without_a_measured_packet` | Pass |
| Two physics substeps reduce to one Resolve packet | `m3_cleanbox` regression | Pass |
| Guard/body/whiff semantics derive from contact role | M3 body/guard regression | Pass |
| Replay reconstruction | Fresh autoplay receipt hashes to `d1a3cc1bfb9c2f67`; verifier reproduces 343 states | Pass |
| Warning-denying check | `RUSTFLAGS='-Dwarnings' cargo check --locked --all-targets` | Pass |
| Test coverage | `RUSTFLAGS='-Dwarnings' cargo test --locked --all-targets` | 237 tests passed |
| Release launch | Release binary created Vulkan surface, initialized renderer/UI, reached terminal autoplay, and saved a replay | Pass for launch/automated path only |
| Runtime C0 asset | 24-bone armored duelist, 82,928 vertices, 309,864 indices; cooked-mesh verifier and fresh offscreen bind frames | Pass for static asset integrity |
| Clean-checkout gates | Tracked lockfile; fmt/warning-denying clippy/check; exact 13-file artifact hydration; 233 tests in isolated mirror | Pass |
| Complete mechanical player flow | Menu, Establishing, duel stages, Result, validated Replay, rematch/menu/quit, and cursor ownership; truth-isolation regressions | Pass mechanically; package/human input proof remains open |
| Local technical package | Two byte-identical assemblies; SHA-256 coverage of all 13 payloads; packaged replay reconstruction; launch from `/tmp` | Pass locally; public redistribution is not cleared |
| Automated OS input path | uinput Start → select/confirm → Result → Replay → Rematch → Menu → Quit; clean process exit | Pass for real event path, not human-play acceptance |

## Evidence still required

| Required evidence | Current state | Consequence |
|---|---|---|
| Admitted runtime poses | `App::current_pose()` remains bind-pose matrices; ARDY/MotionBricks/active-ragdoll foundations are isolated | No motion-readable action proof |
| Coupled articulated physics | Current tracker advances independent joints/root and explicitly excludes coupling, gravity, limits, balance, ground, and contacts | Physical response target is unproven |
| Pose-derived contact/socket parity | M3 uses action-authored cleanbox targets; first-person sword has an independent transform | Physics-derived visible contact is unproven |
| Five real packaged keyboard/mouse matches | Not recorded | Player-loop criterion is unproven |
| Continuous packaged gameplay video | Missing by design; canonical media verifier remains fail-closed | No gameplay-media claim |
| Distribution rights for all package payloads | C0 and W0 technical provenance exists; complete redistribution grants remain incomplete | Blocks redistribution claims, not technical work |
| Full PBR/lighting contract | Light-bronze fallback is structural/readability mitigation only | Generated PBR maps are not runtime-integrated |
| Replay presentation | Replay is mechanically correct, but the captured Replay footer overlaps stale Plan instructions | Presentation acceptance remains fail-closed |

## Decision

The live M3 core requires a typed packet, hashes every tick, and replays deterministically. That packet is currently generated from action-authored cleanbox targets rather than solved/rendered poses; both actors render bind matrices and the first-person sword is independent. Compilation, autoplay, replay, and static frames therefore do not establish the requested packaged human-play slice.

Advance only through the PVP chain in `docs/reports/DEVELOPMENT_TASKLIST.md`. Clean-checkout, mechanical runtime flow, local package, and automated OS input-path gates passed. Admitted action motion is now active; contact/socket, camera, presentation, and human-evidence units remain downstream.
