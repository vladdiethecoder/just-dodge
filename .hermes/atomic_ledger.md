# Atomic Task Ledger

## Global Context
**Global Goal:** Fix ONNX ort bridge so MotionBricks produces G1(34) → rich(103) → skin(24) animation frames for a playable combat vertical slice.
**Assumptions:**
- Python pipeline proves encoder+decoder work with identical data
- ORT_DYLIB_PATH set to onnxruntime 1.27.0
- `asset::compute_skin_matrices` is proven correct (11/11 tests)
- Local-space retargeting plan is ready (`docs/RETARGETING-PLAN.md`)
**Unresolved Risks:**
- ort v2 Tensor→ndarray→Tensor round-trip may corrupt data layout despite correct shapes

---

## Active Unit
**Unit ID:** None — O1 blocked, awaiting new approach

---

## Pending Units
- O1: Fix ort bridge (blocked — see below)
- R0: Implement local-space retargeting G1→103→24 per docs/RETARGETING-PLAN.md
- A0: Visual proof no morphing on 103-bone skeleton
- A1-A4: Animation clips via MB (idle, strike, dodge, clip selector)
- C1-C5: Combat loop on 103-bone skeleton
- R1-R3: Readability/polish

---

## Blocked / Failed Units
- O1: ort bridge — reshape error `{1,1024,2} → {1,10,-1}` in decoder.run()
  - Python works: encoder→decoder produces (1,40,413) with identical input data
  - Tried: named decoder inputs, owned-data extraction, direct encoder pass-through
  - Next: save Python encoder output to file, load in Rust, test decoder directly
  - Commit: 7bc5b3f (partial fix applied)

---

## Recently Completed (Max 10)
- O1 partial: named decoder inputs + encode_to_vec helper (7bc5b3f)
  - *Validation Executed:* Partial — encoder works, decoder reshape error persists
- r1: Skinning revert (retarget::g1_to_skin → asset::compute_skin_matrices) (cc438f5)
  - *Validation Executed:* Yes — 11/11 non-ONNX tests pass, shot harness 0 bad weights
- r5: Retargeting plan (b7c05a2)
  - *Validation Executed:* N/A — documentation artifact