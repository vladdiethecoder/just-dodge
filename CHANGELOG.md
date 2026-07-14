# Changelog

## Unreleased — PLAYABLE-PROOF reconciliation baseline

Source revision: `2677b4a7dd050e7f4c5ee03881aa16035e413a8b`.

### Added
- `PhysicalContactBatch` replay v2 and a 120 Hz cleanbox-to-60 Hz M3 adapter; body, guard, and explicit whiff outcomes are contact-role driven.
- Headless M3 autoplay/replay verification through the same packet-driven path as runtime integration.
- `c0_armored_duelist_001`: tracked GLB/FBX/SKM1 source chain, 24-bone cooked character, hashes, Meshy task IDs, and conversion manifest.
- Isolated post-Reveal ARDY service, quantized motion-plan/replan schema, replay receipts, active-ragdoll tracking core, official G1 articulation model, and deterministic hinge projection.
- Tracked `Cargo.lock`, a 13-file MotionBricks runtime checksum manifest, and a fail-closed clean-checkout artifact hydrator.

### Changed
- Runtime C0 loading now uses the armored duelist rather than the old nude carrier.
- Default static armor material is a light bronze readability fallback. Raw generated PBR maps are not yet used because the renderer has no complete PBR pipeline.
- Local timestamped QA output is ignored; canonical reviewed media must be promoted explicitly under `docs/media/latest/`.
- PLAYABLE-PROOF work now advances the single live M3 path before 13-action, multiplayer, anatomy/FEM, world, roster, store, or Supabase scope.

### Verified
- Warning-denying all-target compile passed.
- Fresh all-target test pass: 116 library + 115 game-binary + 1 official-motion + 1 serialized motion-service test (233 total).
- M3 autoplay/replay: Player terminal at frame 342, truth hash `d1a3cc1bfb9c2f67`.
- Release `just-dodge` launched, initialized the Vulkan renderer/UI, reached terminal state under deterministic autoplay, saved a replay, and the replay independently reconstructed the same hash.
- Fmt, warning-denying clippy/check, shell validation, runtime-bundle hashes, and 233 all-target tests pass; the same 233 tests pass in an isolated checkout after exact artifact hydration.

### Boundaries
- `App::current_pose()` still returns bind matrices; ARDY/MotionBricks/active-ragdoll foundations are not wired into live gameplay.
- The M3 adapter measures action-authored cleanbox targets, not proxies derived from rendered/solved poses; full physics-derived-contact evidence is absent.
- Package/repo verifiers, five human packaged matches, canonical gameplay media, PBR material support, and distribution-rights closure remain open. A durable remote home for the pinned large-model bundle is still a release operation; the local hydrator requires an explicitly supplied trusted cache.
