# Current State Audit — Milestone 3 First Playable

- Audit UTC: 2026-07-12
- Starting commit: `c47256bfbb87d38d5d837e53c54816fc3a5d7ca3`
- Working branch: `milestone3-first-playable-terra`
- Scope: observed repository state and executable behavior before Milestone 3 implementation.

## Evidence gathered

- `cargo fmt --check`: PASS at baseline.
- `cargo test --all-targets --locked`: PASS at baseline; 77 test cases, 0 failures.
- `cargo build --locked`: PASS at baseline.
- `./target/debug/just-dodge --telemetry`: launched and remained live. Runtime logged window creation, surface configuration, first present, and static arena asset loading. A later 260-second telemetry sample showed the old fixed-timing shell cycling `Observe → Plan → Commit → Reveal → Resolve → Consequence`, with player intent permanently `Idle`; it repeatedly synthesized/defaulted the legacy `Block vs Thrust` result. The telemetry's `frame` field remained `0`, so it cannot serve as a verified truth-tick trace.
- The live window was not capturable by the installed Linux CUA backend: its Wayland accessibility/X11 window discovery returned zero visible windows while the process was live. This is a capture-tool limitation, not evidence that the program did not create its winit surface. It must be re-tested after the playable loop exists.

## Documentation reconciliation

| Claim/source | Observed implementation | Classification |
|---|---|---|
| README describes the project as code-empty / pre-production | Custom Rust 2024 + wgpu 30 + winit 0.30 executable, renderer, assets, input, combat, truth, replay, and AI source exist. | Stale / contradictory |
| `docs/MILESTONES.md` includes Godot language | No Godot project or dependency was found; the executable is custom Rust/wgpu. | Stale |
| `docs/ROADMAP.md` calls First Playable a future stage | The repository has partial components but no verified complete match. | Partly correct, but checklist must distinguish components from playable loop |
| `docs/FILE-INVENTORY-AUDIT.md` says skinned asset pipeline is verified | Existing source and previous asset evidence support salvageability, but this audit did not prove action-readable animated fighters. | Salvageable, unproven for Milestone 3 |
| MotionBricks materials imply a combat-motion runtime | Current source has MotionBricks plumbing but the active live match does not use it as authoritative gameplay. | Disconnected / non-critical |

## Observed subsystem state

### Renderer and assets

- The live executable initializes Vulkan/wgpu, creates a surface, presents, and loads `arena_rock.bin`, `lintel_gate.bin`, and `rune_pillar.bin`.
- `src/bin/shot.rs` can render offscreen C0 carrier inspection images and first-person weapon composition. It is a visual QA harness, not a live-match capture.
- Existing Meshy-derived arena, carrier, and weapon files have partial manifests. Distribution-right evidence is incomplete at this audit point; no distributable claim is admissible yet.
- Classification: renderer **verified for launch/static asset loading**; first-person carrier/weapon presentation **salvageable**; action animation/readability **unproven**.

### Combat and truth

- Existing code has `CombatTruth`, `Cleanbox`, `ActionMatrix`, `Injury`, and fixed-step/replay code.
- The active first-playable selector is `Thrust`, `Block`, `Dodge` (`src/combat.rs`), not the required `Strike`, `Block`, `Grab` triangle.
- Current action-matrix RON contains five actions and stance-dependent rules; it is not the required exhaustive data-driven 3×3 Milestone 3 resolver.
- The live shell cycles phases without a confirmed player choice and sometimes emits a legacy default `Block vs Thrust`; baseline execution did not reach a verifiable terminal match result or restart.
- Classification: deterministic foundations **salvageable**; required 3-action match **broken/incomplete**; deep injury/physics work **premature for this goal**.

### AI, replay, and input

- Seeded AI and binary replay structures exist and have unit coverage.
- Input maps current first-playable selection to Thrust/Block/Dodge, not the required canonical triangle.
- Existing replay code records truth-oriented state but baseline did not demonstrate a full independently playable match recording and replaying to a matching final hash.
- Classification: AI/replay/input **salvageable**, but not accepted as a complete playable loop.

### MotionBricks

- Existing MotionBricks/ONNX/Python boundaries and prior validation artifacts are useful research and presentation work.
- They do not establish action-conditioned combat semantics and must not determine authoritative resolution.
- Classification: **isolated, non-critical, unproven for match presentation**.

## Smallest complete path

1. Introduce one renderer-independent canonical `Action` (`Strike`, `Block`, `Grab`) and one deterministic 3×3 rule table shared by player input, AI, resolver, replay, CLI verification, and presentation snapshots.
2. Implement a fixed-frame exchange state machine: `Observe → Plan → Commit → Reveal → Resolve → Consequence → Observe`; allow `MatchResult` only after health/incapacitation.
3. Enforce simultaneous commitment: neither side may inspect the other side's planned action; AI receives only public snapshot state and historical revealed actions.
4. Apply minimal localized injury/health effects directly from resolution; implement terminal result and restart.
5. Record exact seeded inputs and per-tick canonical hashes. Prove replay reconstruction matches a full match.
6. Only after headless proof passes, replace live Thrust/Block/Dodge input wiring with the same canonical core, render immutable snapshots, and show phase/actions/consequence/result/restart in the existing wgpu shell.
7. Use procedural geometry for the packaged proof build if asset rights remain unproven. Keep MotionBricks presentation-only and optional.

## Audit decision

**CONTINUE.** The starting executable and renderer are real, but the requested First Playable is not present at the starting commit. The shortest truthful route is a small headless-first deterministic game core, then a narrow adapter into the existing renderer; no engine rewrite, 13-action expansion, neural-motion dependency, or deep-simulation work is required for this gate.
