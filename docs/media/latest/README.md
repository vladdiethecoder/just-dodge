# Canonical review media

No valid canonical gameplay media is present.

`rendering-overview.png`, `gameplay-demo.mp4`, and `manifest.json` are deliberately absent rather than substituted with screenshots, autoplay, or an edited sequence. The current Wayland automation boundary cannot focus or capture the packaged winit surface; see `docs/reports/TERRA_AGENTIC_BUILD.md`.

`python3 tools/verify_latest_media.py` must fail until a real packaged-build capture and its provenance manifest are produced. Do not claim a visual or gameplay pass from this directory while that verifier fails.
