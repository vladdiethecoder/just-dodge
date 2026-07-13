# gpt-5.6-terra Build Record — Just Dodge M3

## Scope

- Branch: `milestone3-first-playable-terra`
- Starting revision: `c47256bfbb87d38d5d837e53c54816fc3a5d7ca3`
- Current implementation revision: `0e5a29a0cc99b7e29e259a4192ef6be3e8c8eb60`
- Authored implementation: deterministic M3 truth integration, cleanbox adapter, armored-duelist import, public motion requests, fail-closed MotionBricks source cache, 24-bone retarget QA bridge, renderer bridge, headless verification, and status/evidence documents.

## Current verified mechanics

| Capability | Evidence | Result |
|---|---|---|
| 60 Hz M3 phases and hidden simultaneous commitment | `milestone3::tests::reveal_requires_both_commits_and_ai_cannot_read_hidden_player_action` | Pass |
| Resolve waits for measured geometry | `milestone3::tests::resolve_holds_without_a_measured_packet` | Pass |
| 120 Hz cleanbox → one 60 Hz packet | `m3_cleanbox::tests::resolve_submission_advances_exactly_two_physics_substeps` | Pass |
| Body/guard/whiff consequences | `milestone3::tests::body_packet_overrides_action_labels_and_guard_packet_causes_no_injury` | Pass |
| Replay reconstruction | `m3_match --autoplay 1` then `m3_match --verify` | Frame 342, `Player`, hash `d1a3cc1bfb9c2f67` |
| Warning-clean project | `RUSTFLAGS='-Dwarnings' cargo check --locked --all-targets` | Pass |
| Full test surface | `RUSTFLAGS='-Dwarnings' cargo test --locked --all-targets` at `0e5a29a` | 85 library + 93 game-binary + 1 official-motion + 1 serialized motion-service test passed |

## Runtime asset integration

- Runtime now loads `assets/source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin`, not the old nude C0 carrier.
- The cooked asset has 82,928 vertices, 309,864 indices, and 24 bones; `tools/verify_skinned_bin.py` passed.
- `assets/source/meshy/c0_armored_duelist_001/manifest.json` records source Meshy task IDs, conversion chain, tool version, and SHA-256 identities.
- Current renderer uses a deliberately light bronze fallback rather than the raw generated base-color map, because metallic/roughness/normal maps are not yet supported. This preserved silhouette readability in current bind and first-person QA frames; it is not a PBR implementation.
- Fresh visual evidence is local/ignored: front `0159157db730b19e35fb37ed12240b76c7d4aa9f413e6d56e59b708496917a72`, first-person `159aad28e5e85ed1794f942270c33ae9f0a056a8917d01fcc0d591cf0f05dd0b`.

## Truth/presentation boundary

- `milestone3::Session` owns inputs, phase advancement, physical contact admission, injury, replay, and truth hashes.
- `M3CleanboxWorld` supplies measured packets from two physics substeps; it does not choose outcomes from action labels.
- Renderer, camera, and weapon response consume snapshots after truth advancement. They do not mutate M3 state.
- `App::current_pose()` still returns bind matrices by gate, not absence: public motion requests, artifact validation/cache loading, and retarget transport exist. Current four-frame source clips fail the player-visible semantic tell gate, so no retargeted pose is promoted into the app. See `M3_MOTION_GATE_20260713.md`.

## Boundaries retained

- Five human packaged matches and canonical gameplay media are not demonstrated.
- Current Wayland automation/capture evidence is insufficient for a real-match video claim. X11 probing showed injected input can reach the app, but it is not a five-match human-playtest substitute.
- The new armored-duelist manifest records technical provenance only; redistribution rights remain unverified. The build must not be described as distributable.
- The motion-service integration suite is now a single serialized contract test; it passed 10 consecutive isolated runs and the current all-target suite. This fixes test-harness concurrency without weakening any primitive assertions.
- Neural source generation through the repository's Kimodo path is blocked by owner-side Hugging Face authorization for `meta-llama/Meta-Llama-3-8B-Instruct`; the exact reproducer and no-fallback policy are in `M3_MOTION_GATE_20260713.md`.
