# Changelog

## Unreleased — M3 packet truth and armored-duelist integration

Source revision: `9691ecb9bc523ac9d0edb0c9950cf947aa2a2146`.

### Added
- `PhysicalContactBatch` replay v2 and a 120 Hz cleanbox-to-60 Hz M3 adapter; body, guard, and explicit whiff outcomes are contact-role driven.
- Headless M3 autoplay/replay verification through the same packet-driven path as runtime integration.
- `c0_armored_duelist_001`: tracked GLB/FBX/SKM1 source chain, 24-bone cooked character, hashes, Meshy task IDs, and conversion manifest.
- `docs/reports/DEVELOPMENT_TASKLIST.md`, the dependency-gated implementation plan.

### Changed
- Runtime C0 loading now uses the armored duelist rather than the old nude carrier.
- Default static armor material is a light bronze readability fallback. Raw generated PBR maps are not yet used because the renderer has no complete PBR pipeline.
- Local timestamped QA output is ignored; canonical reviewed media must be promoted explicitly under `docs/media/latest/`.

### Verified
- Warning-denying all-target compile passed.
- Repeated all-target test pass: 79 library + 93 game-binary + 1 official-motion + 6 motion-service tests.
- M3 autoplay/replay: Player terminal at frame 342, truth hash `d1a3cc1bfb9c2f67`.

### Boundaries
- MotionBricks is not yet action-conditioned in the runtime; bind pose remains active.
- Five human packaged matches, canonical gameplay media, PBR material support, and distribution-rights closure remain open work.
