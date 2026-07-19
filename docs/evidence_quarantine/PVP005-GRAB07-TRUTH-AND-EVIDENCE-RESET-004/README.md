# PVP005-GRAB07-TRUTH-AND-EVIDENCE-RESET-004 — INVALID EVIDENCE REVOCATION

Date: 2026-07-19. Branch: grab07-650mm-closure. Manifest: quarantine_manifest.json (SHA-256 preserved).

## Revoked

- UNIT2_RECEIPT_V11_HARMONY4D_PASS.json — INVALID_EVIDENCE, MACHINE_ELIGIBLE REVOKED.
- UNIT2_RECEIPT_V13_HARMONY4D_TRAINED_PASS.json — INVALID_EVIDENCE, MACHINE_ELIGIBLE REVOKED.
  - v13's model is `DistanceGrabModel (MLP: 400 distance features -> 256 -> 128 -> 1)`: a scalar
    distance predictor whose inputs ARE distance features — target leakage by construction, and
    not a motion model. Its "PASS" cannot stand.
  - v11/v13 gate reports are median-only; RESET-004 requires every admitted case <=15mm
    continuously >=100ms, worst/p95/median reported, penetration <=0.5mm, causal opponent
    response, foot sliding, invalid rotations, replay parity.
  - No 120Hz runtime-truth emission backs either claim.
  - Not reproducible from a clean checkout (receipts/training data untracked; no checkpoint,
    config, seeds, optimizer state, or hashes saved).

## Quarantined as DEBUG_RENDER_SMOKE only

12 stills at qa_runs/game_loop_grab_visual_{200,500,1000,2000,5000,10000}/ (observer +
first_person). These are placeholder/procedural render smoke, never runtime-truth evidence.

## Missing / stale record

- v12 receipt: failing experiment (median 229.71mm, best 43.74mm vs 15mm gate), untracked.
- v13 training_data.json: exists locally, untracked — absent from a clean checkout.
- No committed checkpoint/config/seeds/hashes for any v11-v13 claim.
- PR #2 body candidate SHA 30d49b66 is stale (PR head 3b4be51, local head at reset: 1520854).
- CI: 4 consecutive failures on this branch (2026-07-19).

## Preserved

GRAB_ACQUIRE_RANGE_MM=650 (src/intent/grab_state.rs:14) — opportunity/acquisition boundary
ONLY. It is never an absolute hand-coordinate training target.

## Stop state

UNIT2=NOT_MACHINE_EVIDENCE_READY. G4=PENDING_HUMAN. G5=PENDING_HUMAN.
HUMAN_DECISION=PENDING. PROMOTION=BLOCKED.
