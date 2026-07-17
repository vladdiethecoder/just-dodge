# Atomic Task Ledger

## Global Context
**Global Goal:** Build PVP005-GRAB07-G5-REALTIME-001 as a deterministic autonomous headless capture that renders the real retargeted `grab_07`, emits validated video/telemetry/contact evidence, and packages a human-pending ForgeLens review bundle.
**Assumptions:**
- Current repository HEAD is `e7f18ca51225c95e0b5fe15eaf9e155c01d4dcd9`.
- Existing uncommitted `tools/qa/grab07_*` files are prior workspace work and will be inspected but not overwritten blindly.
- Presentation retargeting must remain separate from deterministic truth/contact authority.
**Unresolved Risks:**
- Existing mannequin/retarget geometry may not physically reach the 15 mm visual-surface threshold without mesh penetration.
- Headless GPU/ffmpeg/Blender availability may constrain full media/mesh QA.

---

## Active Unit
**Unit ID:** GRAB07-G5-002
**Mode:** Implementation
**Goal:** Replace Grab/Clinch placeholder presentation with deterministic retargeted immutable `grab_07` skins and add a real-time artifact path without touching truth authority.
**Expected Behavior:** Renderer skin selection for Grab/Clinch uses `motion::load_g1_frames` + `motion_retarget::retarget_g1_frame_to_armored_skin`; output remains deterministic.
**Expected Files Changed:** `src/bin/grab07_capture.rs`, `src/bin/grab07_hand_probe.rs`, G5 artifact helper(s), `.hermes/atomic_ledger.md`.
**Exact Validation Command:** `cargo fmt --check && RUSTFLAGS='-Dwarnings' cargo check --locked --bin grab07_capture --bin grab07_hand_probe`; headless capture plus Blender triangle clearance.
**Baseline Result:** Current capture retarget was absent and used `placeholder_skin`; after the narrow core change the retargeted secure pose has 0 triangle penetration but 0.220935121 m visible hand-to-body clearance, so the 15 mm acquisition target is presently unproven/unmet.
**Strike Count:** 0
**Rollback Plan:** `git checkout -- src/bin/grab07_capture.rs`; remove `src/bin/grab07_hand_probe.rs`; leave prior workspace files untouched.
**Current Status:** In Progress

---

## Pending Units
- GRAB07-G5-002: Implement narrowly scoped retargeted capture and artifact emission.
- GRAB07-G5-003: Execute two headless captures; validate deterministic G5 evidence and visual artifacts.
- GRAB07-G5-004: Package validated evidence into ForgeLens with human-only pending gates.

---

## Blocked / Failed Units
- None.

---

## Recently Completed (Max 10)
- None.
