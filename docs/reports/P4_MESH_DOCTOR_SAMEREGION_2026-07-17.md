# P4 ForgeLens Mesh Doctor — Same-Region Repair Convergence (2026-07-17)

Status: research/QA. runtime_admitted=False, promoted=False. NOT a promotion.

## Breakthrough: region classification unlocks repair convergence

The earlier falsification (P4_MESH_DOCTOR_REPAIR) showed global repair cannot
converge on the C0 fused mesh because it treats all crossings as one coupled
problem. Region analysis (this session) decomposed the defects by bone-group
membership:

- 108 same-region clusters (both triangles dominated by one bone group) — armor
  plates folding onto THEMSELVES within one anatomical region (self-colliding
  cloth/armor). The deepest defects are same-region (RightUpLeg↔RightUpLeg,
  LeftUpLeg↔LeftUpLeg).
- 92 cross-region/unknown — these retain the body<->armor coupling and need mesh
  decomposition.

`tools/blender/mesh_doctor_sameregion_repair.py` targets ONLY the same-region class:
unfold each fold along its normal (symmetric bidirectional, narrow falloff), with a
per-iteration efficacy gate that accepts only strictly-reducing steps. Cross-region
count is reported but not targeted.

## Validated result (measured, this session)

Ran on C0 armored duelist (revision 597c48f). Receipt:
`qa_runs/p4_mesh_doctor/c0_sameregion_receipt.json` (gitignored).

- same_region_history (6 iters): 447 -> 423 -> 422 -> 420 (monotone, converged=True)
- same_region_history (20 iters): 447 -> 423 -> 422 -> 420 -> 411 (continues to
  decrease; converges toward a floor as remaining folds are deeper/tighter)
- cross_region_history: 263 -> 262 (untargeted, stable — no new penetrations)
- Non-destructive: corrective shape key `meshdoctor_sameregion_repair` on a copy;
  new immutable candidate + receipt. promoted=False.

This is the FIRST repair convergence in the Mesh Doctor. The key insight: region
classification separates the tractable self-collision class from the coupled
body<->armor class. Same-region unfolds converge; cross-region does not (as
diagnosed).

## Honest gaps (not claimed)

- Convergence is PARTIAL and slow: 447 -> 420 same-region in 3 accepted steps, not
  to zero. It plateaus; full resolution needs more iterations and/or a stronger
  per-fold solve (larger search over unfold direction/magnitude).
- Cross-region crossings (263) are NOT repaired — they need body/armor mesh
  decomposition (the fused mesh has no body/armor separation signal; vertex groups
  are purely anatomical).
- No promotion-gate or ForgeLens-UI integration yet.
- WO §5 gates (zero self-intersection, ≤0.5 mm) are NOT met — this is a converging
  repair, not a resolved one.

## Reproduce

```
blender --background --python tools/blender/mesh_doctor_sameregion_repair.py -- \
  --glb assets/source/meshy/c0_armored_duelist_001/model.glb \
  --out-glb qa_runs/p4_mesh_doctor/c0_sameregion_candidate.glb \
  --out-receipt qa_runs/p4_mesh_doctor/c0_sameregion_receipt.json --iters 6
```
