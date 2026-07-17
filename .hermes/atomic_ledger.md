# Atomic Task Ledger

## Global Context
**Global Goal:** Achieve live/QA runtime truth parity for Strike presentation and replay verification.
**Assumptions:**
- `milestone3::Session` remains the authoritative deterministic truth owner.
- The existing R6 Hero Strike asset is the admitted shared presentation source.
- Rendering and collision consume presentation only; neither can write truth except through the existing measured-contact boundary.
**Unresolved Risks:**
- The live window is environment-dependent; headless Rust tests and replay verification are the primary closure evidence.

---

## Active Unit
**Unit ID:** RTP-001
**Mode:** Implementation
**Goal:** Admit the R6 Strike presentation to the normal runtime and make live render/cleanbox selection consume its same pose, weapon, and body-proxy sample.
**Expected Behavior:** Normal live Strike selection no longer depends on a QA command flag or panics; Resolve collision targets use the same R6 sample as the renderer.
**Expected Files Changed:** `src/main.rs`, `src/hero_strike.rs` (if shared sampling needs an API), `src/m3_cleanbox.rs` (only if target plumbing needs it).
**Exact Validation Command:** `cargo test --bin just-dodge runtime_strike -- --nocapture` plus focused library tests and `cargo check`.
**Baseline Result:** `cargo check` passed. `cargo test --no-run` passed. A combined filtered-test invocation was malformed (Cargo accepts one filter) and will be replaced with individual focused tests.
**Strike Count:** 0
**Rollback Plan:** Revert the RTP-001 diff from the named source files, leaving the pre-existing QA-only presentation path intact.
**Current Status:** In Progress

---

## Pending Units
- RTP-002: Persist and independently replay-verify the saved live M3 hash trace, with regression coverage for corruption.
- RTP-003: Run current-source focused and broad verification; record parity evidence and close the ledger.

---

## Blocked / Failed Units
- None.

---

## Recently Completed (Max 10)
- None.
