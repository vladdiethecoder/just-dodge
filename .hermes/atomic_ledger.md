# Atomic Task Ledger

## Global Context
**Global Goal:** Complete JD-NORTHSTAR-FULL-GAME-001 in strict SG order. The active implementation wave is SG02 cross-platform deterministic replay parity; SG03+ remain unstarted implementation work.
**Assumptions:**
- The Linux golden replay suite at `b2266e5` is the current deterministic baseline.
- Windows parity can be evaluated with a GitHub-hosted Windows runner after the branch is pushed.
- Steam Deck parity requires a real Deck or an explicitly configured self-hosted Deck runner; cross-compilation is not a platform-execution substitute.
**Unresolved Risks:**
- No authorized Steam Deck execution surface has yet been evidenced. GitHub's runner query returned `total_count=0` for this repository.

**Status Reconciliation (required by tools/verify_pvp005_revision_baseline.py):**
- Published feature baseline: `4e481ccd59602c1cb4eda97183c32dec48f9a801`
- Published branch: `pvp-005-readable-live-motion`
- This ledger tracks work on `grab07-650mm-closure`, which descends from that published baseline history.

---

## Active Unit
**Unit ID:** SG02-CROSS-PLATFORM-PARITY-001
**Mode:** Implementation
**Goal:** Add a portable, fail-closed golden-hash receipt path for Linux and Windows CI, and define a real-Steam-Deck execution receipt without treating cross-compilation as parity evidence.
**Expected Behavior:** Every participating platform independently runs the same no-default-features golden suite, validates the exact seven scenario hashes, emits a signed-by-content receipt, and a reducer rejects missing/mismatched platform receipts.
**Expected Files Changed:** .github/workflows/ci.yml, .github/workflows/sg02-cross-platform.yml, tools/qa/sg02_cross_platform_receipt.py, tools/qa/sg02_cross_platform_reduce.py, tools/qa/test_sg02_cross_platform_parity.py, tools/qa/sg02_golden_hashes.json, Cargo.toml, src/motion_service_async.rs, docs/reports/SG02_CROSS_PLATFORM_LINUX_RECEIPT.json, docs/reports/SG02_CROSS_PLATFORM_PARITY_STATUS.json, .hermes/atomic_ledger.md.
**Exact Validation Command:** cargo fmt --check && cargo clippy --locked --all-targets -- -D warnings && cargo test --locked && python3 tools/qa/sg02_cross_platform_receipt.py --help
**Baseline Result:** Linux golden replay: 7 scenarios × 100 runs bit-exact; no Windows or Steam Deck receipt exists.
**Strike Count:** 0
**Rollback Plan:** `git checkout -- .github/workflows/ci.yml .github/workflows/sg02-cross-platform.yml tools/qa/sg02_cross_platform_receipt.py tools/qa/sg02_cross_platform_reduce.py tools/qa/test_sg02_cross_platform_parity.py tools/qa/sg02_golden_hashes.json Cargo.toml src/motion_service_async.rs docs/reports/SG02_CROSS_PLATFORM_LINUX_RECEIPT.json docs/reports/SG02_CROSS_PLATFORM_PARITY_STATUS.json .hermes/atomic_ledger.md`.
**Current Status:** Blocked — the local infrastructure unit is committed at `a4775aba347dc1f48f1ddb68bda61a1845ec9920`; real Windows and Steam Deck receipts require the owner-controlled GitHub runner/push surfaces.

---

## Pending Units
- SG02-CROSS-PLATFORM-PARITY-001-DECK: Execute the generated Deck receipt workflow on a real Steam Deck and archive the immutable receipt. This remains externally owned until a Deck runner is available.
- SG02-NO-BAKED-RUNTIME-BOUNDARY-001: The legacy `BakedClipProvider` remains publicly compiled because integration tests import it. Isolate it to test-only compilation and prove no production binary exports or constructs it before any SG03 promotion.
- SG03-THREE-ACTION-NEURAL-PHYSICAL-SLICE: Do not implement until SG02 has real Windows and Steam Deck receipts and the strict gate is promoted.

---

## Blocked / Failed Units
- UNIT-2 v7 PASS: INVALID_EVIDENCE. The augmented training data was synthetic (scaled to 650mm), not real 650mm reach data. The model learned from augmented data, not real 650mm reach data. The gate was passed by manufacturing data, not by genuine learned interaction conditioning.

---

## Recently Completed (Max 10)
- SG02-CROSS-PLATFORM-PARITY-001-LOCAL-INFRA: Committed receipt/reducer/workflow infrastructure at `a4775aba347dc1f48f1ddb68bda61a1845ec9920`.
  - *Validation Executed:* Clean checkout at that exact commit: fmt, clippy `-D warnings`, `cargo test --locked --all-targets` (236 lib + 159 main + 2 bin + 3 integration; 0 failed), Linux 7-scenario × 100-run receipt `c0fbef31e916e7efd01f9bbf49f3f92070ad10747646179b5d37d6c0ba4e3a2f`, and fail-closed missing-Windows reduction. Durable evidence: `docs/reports/SG02_CROSS_PLATFORM_LINUX_RECEIPT.json`, `docs/reports/SG02_CROSS_PLATFORM_PARITY_STATUS.json`.
- PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001-QUARANTINE: Quarantined 11 INVALID_EVIDENCE files (101KB) with SHA-256 preservation.
  - *Validation Executed:* Yes — all 11 files copied to docs/evidence_quarantine/PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001/ with SHA-256 hashes. Manifest created with reason, G4/G5 status, and promotion BLOCKED.
- GRAB07-SEQ-CONCAT-002: Train v6 concatenation conditioner on the combined corpus and record the strict full-distribution verdict.
  - *Validation Executed:* Yes — fresh `/tmp/hermes-verify-grab07-concat-_41nt3u3.py` ad-hoc focused verification re-ran `python3 tools/qa/train_grab07_seq_conditioner.py --steps 15000`, structural concat assertions, syntax checking, and receipt assertions. It passed with the expected strict trainer exit 1 / `FAIL` (median 365.10 mm > 15 mm), early stopping at `9.242739179171622e-05`, both training corpora, all 12 paired held-out rows, and median-derived ablation delta 15.77 mm. Temp script cleanup was explicitly verified; evidence log SHA-256 `b45a655ab8d43340914ce671a72ad31efa8a1b561ed39a33ba786bbf59370fa9`.
- GRAB07-SEQ-CONCAT-001: Implement concatenation conditioner, source-aware combined-corpus split, strict median gate, early stop, and distribution receipt.
  - *Validation Executed:* Yes — `python3 -m py_compile ...` and structural forward/Conv/dropout assertions printed `STRUCTURAL_CONCAT_SMOKE=PASS`; one-step live trainer smoke completed with the expected non-pass exit.
