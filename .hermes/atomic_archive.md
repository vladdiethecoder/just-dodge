# Atomic Unit Archive

Completed units moved from `.hermes/atomic_ledger.md` when the active ledger exceeded ten completed entries.

## Archived Completed Units
- O1 partial: named decoder inputs + `encode_to_vec` helper (`7bc5b3f`).
  - *Validation Executed:* Partial — encoder works, decoder reshape error persists.
- r1: Skinning revert (`retarget::g1_to_skin` → `asset::compute_skin_matrices`) (`cc438f5`).
  - *Validation Executed:* Mechanically yes (11/11 non-ONNX tests, shot harness 0 bad weights), but current live visual evidence has now falsified visual correctness.
- r5: Retargeting plan (`b7c05a2`).
  - *Validation Executed:* N/A — documentation artifact.
