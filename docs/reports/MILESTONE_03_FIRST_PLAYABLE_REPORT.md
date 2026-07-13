# Milestone 3 First Playable Report

- Decision: **BLOCKED**
- Evaluated source commit: `0dd1e398a28d85654d46b3859a476b694d8272e2`
- Starting commit: `c47256bfbb87d38d5d837e53c54816fc3a5d7ca3`
- Branch: `milestone3-first-playable-terra`

## Verified engineering evidence

| Requirement | Evidence | Result |
|---|---|---|
| Deterministic Strike/Block/Grab resolver | `milestone3::tests::resolver_is_exhaustive_and_has_the_required_triangle` | Pass |
| Both actors commit before reveal and AI cannot inspect hidden intent | `milestone3::tests::reveal_requires_both_commits_and_ai_cannot_read_hidden_player_action` | Pass |
| Terminal injury and restart | `milestone3::tests::localized_injury_ends_match_and_restart_is_terminal_only` | Pass |
| Replay reconstruction | `m3_match --verify` reproduced 143 hash states, final `c52988e98614420e` | Pass |
| Determinism soak | `milestone3::tests::one_hundred_replay_reconstructions_keep_the_same_truth_hash` | Pass |
| Warning-clean project gates | `RUSTFLAGS='-Dwarnings' cargo check --locked --all-targets` and `RUSTFLAGS='-Dwarnings' cargo test --locked --all-targets` | Pass |
| Clean copied package launch | `/tmp/just-dodge-package-TYNqHo/package/run.sh --telemetry` created the winit surface, presented a frame, and initialized arena, C0, renderer, and UI | Pass |

## Non-advanceable requirements

| Required evidence | Observed result | Consequence |
|---|---|---|
| Five actual keyboard/mouse matches in the packaged build | CUA cannot target the KDE Wayland winit surface. `ydotoold` injection did not change telemetry; `xdotool search --pid 3621880` returned no X11 window. | Not demonstrated |
| Continuous packaged-gameplay video | Driver desktop capture cannot see the Wayland display/input surface. | `docs/media/latest/gameplay-demo.mp4` is correctly absent |
| Canonical media manifest and rendering overview | `python3 tools/verify_latest_media.py` fails closed: missing `rendering-overview.png`, `gameplay-demo.mp4`, and `manifest.json`. | Not demonstrated |
| Distribution rights for runtime assets | `docs/reports/ASSET_PROVENANCE_M3.md` identifies incomplete/unknown rights records for every shipped Meshy-derived/arena runtime payload. | Engineering package only, no distributable claim |

## Root cause and smallest recovery

`hermes computer-use doctor` confirms the installed `cua-driver 0.7.1` can inspect and capture X11. With `CUA_DRIVER_RS_ENABLE_WAYLAND=1`, it reports that KDE lacks a virtual-pointer protocol and the installed driver was built without `portal-libei`. A portal-enabled cua-driver build (or an equivalent Wayland input/capture backend) is required before real input/video evidence can be obtained.

## Decision

Do not advance Milestone 3. The deterministic simulation, replay, renderer bridge, package launch, and project gates are evidence-backed, but the required real interactive play/video and asset-rights gates remain unproven. This report is deliberately **BLOCKED**, not PASS, CONTINUE, or a distribution claim.
