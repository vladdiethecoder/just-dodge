# Historical State Audit — PLAYABLE-PROOF Baseline

> Superseded as current authority on 2026-07-21. This file preserves the
> revision-scoped 2026-07-14 PVP-005 observation below. Current status authority:
> `docs/evidence_quarantine/SG01-EVIDENCE-CANON-RESET-002/clean_checkout_receipt.json`.
> Subject `3caa1ec680d181b244affb25ff1826a74ea6cc3b` passed local clean-checkout gates; SG01 remains blocked on same-commit remote CI and SG02+ implementation is parked.

- Audit baseline revision: published PVP-005 feature baseline `4e481ccd59602c1cb4eda97183c32dec48f9a801`
- Audit UTC: 2026-07-14
- Branch: `pvp-005-readable-live-motion`; historical PVP-003/PVP-004 reports retain their evaluated ancestor revisions
- Worktrees: one (`/run/media/vdubrov/NVMe-Storage1/Just Dodge`)

## Selected executable path

1. `src/main.rs` owns `milestone3::Session`, `M3CleanboxWorld`, deterministic AI, renderer, UI, input, telemetry, and the 60 Hz wall-time accumulator.
2. `src/milestone3.rs` owns authoritative phase/input/injury/result state, exact contact admission, RON replay, and canonical truth hashes.
3. `src/m3_cleanbox.rs` maps revealed M3 actions into `cleanbox::step_actions`, advances exactly two 120 Hz substeps, and adapts the reduced packet back into M3.
4. `src/cleanbox.rs`, `src/duel_world.rs`, `src/duel_physics.rs`, and `src/hitbox.rs` remain supporting live dependencies; they are not quarantine candidates yet.
5. Renderer/UI/camera consume cloned immutable M3 snapshots. `App::current_pose()` returns static reference skin matrices, and the first-person sword uses a separate presentation transform.
6. `src/bin/m3_match.rs` exercises the same M3 session/cleanbox path without rendering.

## Evidence classification

| Subsystem | Classification | Current evidence boundary |
|---|---|---|
| M3 intent/phase/injury/result truth | Live, verified mechanically | Warning-denying check; M3 tests; terminal frame 342 |
| M3 replay/hash | Live, verified mechanically | 100 reconstructions; final hash `d1a3cc1bfb9c2f67` |
| 120 Hz → 60 Hz adapter | Live, verified for authored cleanbox targets | Exactly two substeps; exact packet admission |
| Physical outcome claim | Partial | Labels derive from packets, but the target geometry is action-authored rather than derived from solved/rendered poses |
| Armored C0 import | Live presentation, static integrity only | 82,928 vertices; 309,864 indices; 24 bones; cooked verifier passes |
| ARDY/MotionBricks plan packets | Isolated foundation | Provenance/quantization/replay tests exist; no live `App` consumer |
| Active-ragdoll/G1 articulation | Isolated foundation | Independent-joint tracking and hinge projection tests; no coupled articulated world |
| Player flow | Live, verified mechanically | Menu → Establishing → duel phases → Result → validated Replay; rematch/menu/quit and duel-only cursor capture are implemented. Real keyboard/mouse package evidence remains open |
| Package/evidence | Local technical package verified | Two byte-identical assemblies, complete SHA-256 coverage, packaged replay reconstruction, `/tmp` launch, and OS-level input cadence pass. Human matches and canonical video remain absent |

## Fresh baseline gates

- PASS: warning-denying all-target check.
- PASS: 237 all-target tests (119 library, 116 main, two integrations).
- PASS: release `just-dodge`/`m3_match` build and release launch through renderer/UI initialization and replay save.
- PASS: armored cooked-mesh verifier.
- PASS: `cargo fmt --check` and warning-denying clippy/check.
- PASS: tracked `Cargo.lock` and locked compilation from an isolated checkout.
- PASS: the isolated checkout hydrates and verifies all 13 pinned MotionBricks runtime files from an explicit trusted cache, then passes all 233 tests.
- PASS: runtime-flow truth-isolation and replay tests; release Menu and Result captures; cursor capture/release logs.
- FAIL: canonical-media verifier (rendering overview, gameplay video, and manifest absent).
- PASS: two byte-identical 184,144,387-byte local package assemblies; complete manifest coverage; packaged replay reconstruction; launch from `/tmp`; OS-level Start → Plan/confirm → Result → Replay → Rematch → Menu → Quit cadence.
- FAIL: five human packaged matches remain absent. The Replay capture also exposes overlapping footer/Plan instructions, so presentation acceptance remains fail-closed.

## Historical documents

`M3_MOTION_GATE_20260713.md`, `TERRA_AGENTIC_BUILD.md`, and `ASSET_PROVENANCE_M3.md` are immutable evidence snapshots for older revisions. Their former Kimodo authorization blocker and test counts are historical, not current project status.

## Ordered PLAYABLE-PROOF path

`PVP-001 reconcile active path` → `PVP-002 clean-checkout gates` (passed) → `PVP-003 complete runtime flow` (passed mechanically) → `PVP-004 packaged interaction/cadence proof` (passed for local automated input path) → `PVP-005 admitted plan packets/motion` → coupled articulated physics → pose/socket-derived contact → camera/readability → truth-driven presentation → packaged human matches and canonical evidence.

No 13-action, multiplayer, roster, anatomy/FEM, world, store, Supabase, or nonessential asset expansion is admitted before that chain passes.
