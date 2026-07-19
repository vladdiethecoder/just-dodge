# Atomic Task Ledger

## Global Context
**Global Goal:** Repair the GRAB07 UNIT-2 temporal CNN so it uses genuine concatenation-based exogenous conditioning, retains the strict 650 mm / 15 mm two-sided reach gate, and reports a distribution-wide condition-ablation verdict.
**Assumptions:**
- The corpus manifests under `qa_runs/grab07_combat_corpus/` are the intended combined CMU + Kungfu corpus.
- The train script is the isolated source of truth for this trainer and its machine receipt.
**Unresolved Risks:**
- The requested concat architecture genuinely improves the median ablation signal, but does not meet the strict 15 mm median reach gate. It remains runtime-inadmissible.

**Status Reconciliation (required by tools/verify_pvp005_revision_baseline.py):**
- Published feature baseline: `4e481ccd59602c1cb4eda97183c32dec48f9a801`
- Published branch: `pvp-005-readable-live-motion`
- This ledger tracks work on `grab07-650mm-closure`, which descends from that published baseline history.

---

## Active Unit
**Unit ID:** PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001
**Mode:** Implementation
**Goal:** Quarantine INVALID_EVIDENCE, rebuild corpus lineage, repair retargeting, replace leaking model path, and restore trustworthy machine evaluation.
**Expected Behavior:** All prior UNIT-2 v7 PASS evidence is quarantined as INVALID. New evidence is built from properly licensed, lineage-disjoint positive Grab data with genuine contact conditioning.
**Expected Files Changed:** docs/evidence_quarantine/PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001/, .hermes/atomic_ledger.md, tools/qa/train_grab07_seq_conditioner.py, src/intent/grab_state.rs, src/intent/grab_closing.rs, src/intent/plan_phase.rs.
**Exact Validation Command:** cargo fmt --check && cargo clippy --locked --all-targets -- -D warnings && cargo test --locked
**Baseline Result:** INVALID_EVIDENCE quarantined (11 files, 101KB).
**Strike Count:** 0
**Rollback Plan:** `git checkout -- .hermes/atomic_ledger.md` if the ledger needs to be restored.
**Current Status:** In Progress

---

## Pending Units
- PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001-LINEAGE: Rebuild corpus lineage with source URI, license, raw SHA, actor, session, clip, action, root-lineage ID, conversion SHA, retarget SHA, window SHA, augmentation parent, split.
- PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001-RETARGET: Repair retargeting with framewise marker validity, anatomically declared mappings, no numeric joint copying.
- PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001-MODEL: Replace leaking model path with real MotionBricks or CHECKPOINT/PROVIDER_UNAVAILABLE.
- PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001-EVAL: Action-specific evaluation (Grab: 15mm+100ms+0.5mm+overlap+causal+rotations+stable feet; Kick: foot-to-target contact+timing+velocity+balance+recovery).
- PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001-RUNTIME: Runtime proof (measured runtime contact, no manual admission booleans, synchronized views, executable hashes).

---

## Blocked / Failed Units
- UNIT-2 v7 PASS: INVALID_EVIDENCE. The augmented training data was synthetic (scaled to 650mm), not real 650mm reach data. The model learned from augmented data, not real 650mm reach data. The gate was passed by manufacturing data, not by genuine learned interaction conditioning.

---

## Recently Completed (Max 10)
- PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001-QUARANTINE: Quarantined 11 INVALID_EVIDENCE files (101KB) with SHA-256 preservation.
  - *Validation Executed:* Yes — all 11 files copied to docs/evidence_quarantine/PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001/ with SHA-256 hashes. Manifest created with reason, G4/G5 status, and promotion BLOCKED.
- GRAB07-SEQ-CONCAT-002: Train v6 concatenation conditioner on the combined corpus and record the strict full-distribution verdict.
  - *Validation Executed:* Yes — fresh `/tmp/hermes-verify-grab07-concat-_41nt3u3.py` ad-hoc focused verification re-ran `python3 tools/qa/train_grab07_seq_conditioner.py --steps 15000`, structural concat assertions, syntax checking, and receipt assertions. It passed with the expected strict trainer exit 1 / `FAIL` (median 365.10 mm > 15 mm), early stopping at `9.242739179171622e-05`, both training corpora, all 12 paired held-out rows, and median-derived ablation delta 15.77 mm. Temp script cleanup was explicitly verified; evidence log SHA-256 `b45a655ab8d43340914ce671a72ad31efa8a1b561ed39a33ba786bbf59370fa9`.
- GRAB07-SEQ-CONCAT-001: Implement concatenation conditioner, source-aware combined-corpus split, strict median gate, early stop, and distribution receipt.
  - *Validation Executed:* Yes — `python3 -m py_compile ...` and structural forward/Conv/dropout assertions printed `STRUCTURAL_CONCAT_SMOKE=PASS`; one-step live trainer smoke completed with the expected non-pass exit.
