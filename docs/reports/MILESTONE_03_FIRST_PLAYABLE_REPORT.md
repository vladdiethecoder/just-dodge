# Milestone 3 First Playable Report

- Decision: **BLOCKED**
- Evaluated revision: `9691ecb9bc523ac9d0edb0c9950cf947aa2a2146`
- Starting revision: `c47256bfbb87d38d5d837e53c54816fc3a5d7ca3`
- Branch: `milestone3-first-playable-terra`

## Verified engineering evidence

| Requirement | Evidence | Result |
|---|---|---|
| Canonical Strike/Block/Grab truth state | `src/milestone3.rs` with 79 library tests | Pass |
| Hidden intent stays hidden until Reveal | M3 hidden-intent regression | Pass |
| Resolve requires a physical packet | `resolve_holds_without_a_measured_packet` | Pass |
| Two physics substeps reduce to one Resolve packet | `m3_cleanbox` regression | Pass |
| Guard/body/whiff semantics derive from contact role | M3 body/guard regression | Pass |
| Replay reconstruction | Fresh autoplay receipt hashes to `d1a3cc1bfb9c2f67`; verifier reproduces 343 states | Pass |
| Warning-clean source | `RUSTFLAGS='-Dwarnings' cargo check --locked --all-targets` | Pass |
| Test coverage | repeated `RUSTFLAGS='-Dwarnings' cargo test --locked --all-targets` | 179 Rust unit/integration tests passed |
| Runtime C0 asset | 24-bone armored duelist, 82,928 vertices, 309,864 indices; cooked-mesh verifier and fresh offscreen bind frames | Pass for static asset integrity |

## Evidence still required

| Required evidence | Current state | Consequence |
|---|---|---|
| Action-conditioned MotionBricks runtime poses | `App::current_pose()` remains bind-pose matrices | No motion-readable action proof; pose-contact parity is not established |
| Five real packaged keyboard/mouse matches | Not recorded | Player-loop criterion is unproven |
| Continuous packaged gameplay video | Missing by design; canonical media verifier remains fail-closed | No gameplay-media claim |
| Distribution rights for all package payloads | New C0 task/hash record is technical provenance only; legacy arena/weapon records also remain incomplete | No distributable-build claim |
| Full PBR/lighting contract | Light-bronze fallback is structural/readability mitigation only | Generated PBR maps are not runtime-integrated |

## Decision

The committed M3 core is mechanically stronger than the former action-table path: outcomes require a typed physical packet and the packet is replayed and hashed. The armored runtime opponent is now structurally valid and visible in static QA frames. These facts do not prove an independently playable, action-readable, distributable first playable.

Do not advance Milestone 3. Execute the dependency chain in `docs/reports/DEVELOPMENT_TASKLIST.md`, beginning with `B.1.1` (public deterministic motion request contract), then use real player matches and canonical media as the final M3 evidence gate.
