# Changelog

## Unreleased — Milestone 3 engineering candidate

### Added
- Renderer-independent deterministic three-action duel session with replay reconstruction and canonical truth hashes.
- Headless `m3_match` runner for deterministic match and replay verification.
- Warning-denying all-target CI gate and canonical-media verifier.
- Current-state, build-attribution, and packaged-asset provenance reports.

### Changed
- The Rust/wgpu presentation path consumes immutable Milestone 3 snapshots for input, phase, action, consequence, result, and restart display.
- Runtime/package documentation now distinguishes verified engineering evidence from unproven live-input, video, and asset-distribution claims.

### Known boundaries
- Canonical live gameplay media is intentionally absent until the Wayland automation environment can focus and capture the packaged winit window.
- The supplied runtime package is engineering-only: included Meshy-derived and arena assets do not yet have complete redistribution-rights records.
