# gpt-5.6-terra Agentic Build Record — Just Dodge Milestone 3

## Identity and scope

- Acting implementation model: `gpt-5.6-terra` via `openai-codex`.
- Session goal: verified independently playable Just Dodge Milestone 3 First Playable candidate.
- Implementation-author rule: this record covers implementation authored only by gpt-5.6-terra. No auxiliary model has written code or patches for this goal.
- Starting SHA: `c47256bfbb87d38d5d837e53c54816fc3a5d7ca3`.
- Dedicated reversible branch: `milestone3-first-playable-terra`, created from the starting SHA. Public history was not rewritten.

## Baseline evidence

| UTC | Command / action | Observed result |
|---|---|---|
| 2026-07-12 | `cargo fmt --check` | PASS before this implementation unit. |
| 2026-07-12 | `cargo test --all-targets --locked` | PASS: 77 tests before this implementation unit. |
| 2026-07-12 | `cargo build --locked` | PASS before this implementation unit. |
| 2026-07-12 | `./target/debug/just-dodge --telemetry` | winit window, Vulkan surface, clear frame, arena assets, and telemetry were live. The legacy route did not prove a player-controlled complete match. |
| 2026-07-12 | CUA/X11/AT-SPI discovery | No discoverable game window despite live Wayland process. This is a capture limitation, not gameplay proof. |

## Milestone units

### M3-AUDIT-001 — Current-state audit

- Files authored: `docs/reports/CURRENT_STATE_AUDIT.md`, this build record.
- Acceptance: baseline compile/test/runtime reproduced; observed and inferred status separated; smallest executable path identified.
- Status: PASS.

### M3-SIM-001 — Canonical deterministic three-action core

- Files authored: `src/milestone3.rs`, `src/bin/m3_match.rs`; `src/lib.rs` exports the core.
- Contract: a single `milestone3::Action` drives terminal input, seeded AI, an exhaustive data-defined 3×3 resolver, replay events, canonical hash, and snapshot presentation boundary.
- Safety: reveal requires both commits; opponent AI is called from public exchange state only; restart is accepted only from `MatchResult`.
- State: 60 Hz phases `Observe → Plan → Commit → Reveal → Resolve → Consequence`; terminal localized head/torso injury; explicit winner.
- Replay: RON serialized event stream plus one canonical hash per initial/ticked state; `replay()` independently reconstructs and rejects hash mismatch.
- Focused verification: `cargo test --locked milestone3 -- --nocapture` passed 5/5 tests. Log: `qa_runs/milestone3_sim_001/focused_tests_after_presentation.log`.
- Five replay reconstructions: `cargo run --locked --bin m3_match -- --autoplay 5 qa_runs/milestone3_sim_001/replays` passed. Final hashes:
  - `c52988e98614420e`
  - `fd263c569179e7e7`
  - `6d66b13377e82d52`
  - `28955fa576102879`
  - `460720a18a53b8b6`

### M3-PRESENT-001 — Existing wgpu renderer bridge

- Files changed: `src/main.rs`, `src/input.rs`, `src/ui.rs`.
- Runtime path: window input maps `1/2/3` to canonical `Strike/Block/Grab`, then `Space/Enter` commits through `Session::apply`; seeded AI commits through the same method; the renderer consumes only the resulting read-only snapshot.
- UI: lists exactly Strike/Block/Grab, shows phase, action reveal, localized injury, and terminal overlay. `R` from `MatchResult` calls canonical restart.
- Visual response: canonical action/phase snapshots drive a visual-only first-person W0 longsword transform. It cannot mutate combat state, replay, or hash.
- Compile: `cargo check --locked --bin just-dodge` passed. Logs: `qa_runs/milestone3_sim_001/presentation_check_attempt_2.log` and `qa_runs/milestone3_sim_001/presentation_check_autoplay.log`.
- Runtime: `cargo run --locked --bin just-dodge -- --telemetry --autoplay` loaded arena + C0 + W0, completed a match at frame 142, and saved `/tmp/just_dodge_m3_replay_1783906109.ron`.
- Runtime replay verification: `m3_match --verify` independently reproduced the saved renderer-run replay: 143 hash states, `winner=Some(Player)`, final hash `c52988e98614420e`. Log: `qa_runs/milestone3_sim_001/live_renderer_replay_verify.log`.

## Failures, exact causes, and corrections

1. `m3_match --autoplay` initially failed with `AlreadyCommitted`. Cause: the runner returned at Plan after both fighters committed, then tried to select another player action. Correction: tick fully committed Plan into Commit before accepting new input. The five-replay rerun passed.
2. Initial renderer-bridge compile exposed stale legacy UI types (`Thrust`, `Dodge`, stance fields) after the canonical input type changed. Correction: UI now consumes only `milestone3::Snapshot` and canonical action labels. `cargo check --bin just-dodge` passed.
3. Current Linux Wayland CUA cannot enumerate or screenshot the game window. Evidence: no window returned for the live PID; desktop capture reports no `$DISPLAY`/`$WAYLAND_DISPLAY` in the driver environment. No fabricated visual capture is used.

## Known limitations retained honestly

- The opponent still uses the accepted C0 carrier reference pose; the player is intentionally omitted from first-person body rendering to avoid self-occlusion. The W0 longsword now has action-specific presentation response, but full-body authored motion clips and sound effects are still separate work.
- Legacy `truth`, cleanbox, and MotionBricks modules remain compiled for their existing test evidence but are no longer the gameplay authority in `src/main.rs`; the new M3 route is `milestone3::Session`.
- QA-only `--autoplay` is not the default launch path. It is a deterministic integration driver used because the Wayland background automation backend cannot target this winit window.

## Package evidence

- Archive: `dist/just-dodge-m3-first-playable.tar.zst` (109 MiB), SHA-256 `08b6a82ae25b9b806a458aab73e84a86379acabb7b30561ae166f8ac7bdab3ae`.
- Clean extraction root: `/tmp/just-dodge-m3-package-verify/just-dodge-m3-first-playable`.
- Manifest: all 13 packaged payload entries verified with `sha256sum -c SHA256SUMS`.
- The extracted `./bin/m3_match --autoplay 5 replays` completed five matches at frame 142 and wrote five replay files.
- The extracted `./run.sh --telemetry --autoplay` created the winit window/Vulkan surface, initialized arena + C0 + W0, and saved a replay. The QA timeout returned 124 because the interactive window intentionally stays open; its replay had already been saved and independently verified.
- `cargo test --all-targets --locked`: PASS. This suite includes 18 library, 93 game-binary, 11 screenshot-harness, 7/13 probes, 1 official MotionBricks, and 6 motion-service tests. Existing warnings remain in legacy motion/probe code; this unit did not add warning diagnostics.

## Remaining evidence boundary

- Current visual media from a display-capable capture environment remains unavailable: the active Wayland CUA driver environment has neither `$DISPLAY` nor `$WAYLAND_DISPLAY`, cannot enumerate the winit surface, and cannot capture it. This does not invalidate the package launch / renderer initialization / replay evidence above; it prevents an honest screenshot claim.
- Local and remote commit SHA(s) follow after a scoped working-tree ownership check.
