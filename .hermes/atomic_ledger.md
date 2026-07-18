# Atomic Task Ledger

## Global Context
**Global Goal:** Repair the GRAB07 UNIT-2 temporal CNN so it uses genuine concatenation-based exogenous conditioning, retains the strict 650 mm / 15 mm two-sided reach gate, and reports a distribution-wide condition-ablation verdict.
**Assumptions:**
- The corpus manifests under `qa_runs/grab07_combat_corpus/` are the intended combined CMU + Kungfu corpus.
- The train script is the isolated source of truth for this trainer and its machine receipt.
**Unresolved Risks:**
- The requested concat architecture genuinely improves the median ablation signal, but does not meet the strict 15 mm median reach gate. It remains runtime-inadmissible.

---

## Active Unit
**Unit ID:** None
**Mode:** Implementation
**Goal:** None.
**Expected Behavior:** None.
**Expected Files Changed:** None.
**Exact Validation Command:** None.
**Baseline Result:** N/A.
**Strike Count:** 0
**Rollback Plan:** `git checkout -- tools/qa/train_grab07_seq_conditioner.py` if the experiment needs to be discarded.
**Current Status:** Completed

---

## Pending Units
- None.

---

## Blocked / Failed Units
- None. The training experiment completed with an honest strict `FAIL`, rather than a blocked run.

---

## Recently Completed (Max 10)
- GRAB07-SEQ-CONCAT-002: Train v6 concatenation conditioner on the combined corpus and record the strict full-distribution verdict.
  - *Validation Executed:* Yes — fresh `/tmp/hermes-verify-grab07-concat-_41nt3u3.py` ad-hoc focused verification re-ran `python3 tools/qa/train_grab07_seq_conditioner.py --steps 15000`, structural concat assertions, syntax checking, and receipt assertions. It passed with the expected strict trainer exit 1 / `FAIL` (median 365.10 mm > 15 mm), early stopping at `9.242739179171622e-05`, both training corpora, all 12 paired held-out rows, and median-derived ablation delta 15.77 mm. Temp script cleanup was explicitly verified; evidence log SHA-256 `b45a655ab8d43340914ce671a72ad31efa8a1b561ed39a33ba786bbf59370fa9`.
- GRAB07-SEQ-CONCAT-001: Implement concatenation conditioner, source-aware combined-corpus split, strict median gate, early stop, and distribution receipt.
  - *Validation Executed:* Yes — `python3 -m py_compile ...` and structural forward/Conv/dropout assertions printed `STRUCTURAL_CONCAT_SMOKE=PASS`; one-step live trainer smoke completed with the expected non-pass exit.
