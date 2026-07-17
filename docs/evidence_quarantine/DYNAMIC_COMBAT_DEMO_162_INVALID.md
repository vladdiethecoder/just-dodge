# INVALID EVIDENCE QUARANTINE — Dynamic Combat Demo (162 examples)

**Status: EXPLORATORY-ONLY. INVALID FOR PRODUCTION EVIDENCE.**

This notice quarantines the former 162-example dynamic-combat demo. It is **not** evidence for the typed interaction-conditioned MotionBricks forward path, and it must not be used for model/runtime admission, production-motion claims, promotion, deterministic truth, replay validation, or owner acceptance.

## Quarantined artifacts

The artifacts were moved from the external scratch location
`/home/vdubrov/Projects/r6k-dynamic-combat-demo/` to the ignored repository-local quarantine:

`validation_evidence/quarantine/dynamic-combat-demo-162-invalid-exploratory-20260717/`

The directory contains the original `demo_summary.json`, `rendered_poses.npy`,
`rendered_manifest.json`, and contact-sheet frames. Its summary records 162
examples (`6` moves × `27` variants per move).

## Why this evidence is invalid for production admission

1. The demo constructs synthetic targets in-process rather than consuming the
   production typed interaction-conditioned MotionBricks forward contract.
2. Its output combines the learned residual with **hard-masked constraint
   values**. The reported zero foot/grip/hand errors are consequently not an
   independent forward-path conformance result.
3. It has no held-out typed-forward test, no admitted runtime integration, and
   no deterministic truth or replay evidence.
4. Skeleton contact sheets and feature variance only establish exploratory
   variation in this toy setup; they do not establish valid combat-motion
   conditioning, production safety, or mechanical authority boundaries.

## Enforcement and permitted use

- `tools/qa/dynamic_combat_demo.py` and
  `tools/qa/render_dynamic_combat_frames.py` are prominently marked
  **QUARANTINED EXPLORATORY-ONLY** and write/read this quarantine location.
- The artifacts may be inspected only to design future falsifiable experiments.
- Any future admissible evidence must independently exercise the typed
  interaction-conditioned MotionBricks forward path and satisfy its separate
  runtime, truth, replay, and promotion gates.
