# P4 ForgeLens Mesh Doctor — Repair Worker Honest Status (2026-07-17)

Status: research/QA. runtime_admitted=False, promoted=False. NOT a working repair.
The detection core (P4_MESH_DOCTOR_DETECTION_2026-07-17.md) is validated; the
first repair approach is FALSIFIED and recorded here with the correct direction.

## What was built

`tools/blender/mesh_doctor_repair.py` — non-destructive repair worker (Blender).
Consumes a detection report, produces corrective shape keys on a COPY of the mesh,
exports a NEW immutable candidate GLB + receipt. Non-destructive: base mesh never
mutated; repairs live in shape keys; never auto-promotes. Receipt persists source/
detection/candidate hashes, per-repair push, falloff, verts displaced.

## Verified correct (this session)

- Repair pipeline runs end-to-end: 20 repairs, candidate with 20 morph targets,
  receipt with full provenance (non_destructive=True, promoted=False).
- Displacement math is correct in WORLD space: repair_000 max 3.524 mm (expected
  ~3.76 mm = 3.26 mm penetration + 0.5 mm clearance). Caught and fixed a real bug:
  the C0 mesh is scaled 0.01 (cm->m); the shape-key offset must be converted with
  the full inverse world matrix. An early "352 mm" reading was a local-vs-world
  misread; world-space is correct.

## FALSIFIED: three repair approaches on the fused mesh

Efficacy check (re-run genuine-crossing detection, >0.5 mm, original vs repaired):

- ORIGINAL: 710 genuine crossings
- REPAIRED single-normal push (20 keys @ weight 1.0): 729 (+19, worse)
- REPAIRED bidirectional push (both surfaces apart, half each): 722 (+12, worse)
- REPAIRED global iterative relaxation with efficacy gate: 710 → 710 (no
  improvement; every trial step rejected; damping reduced to floor in 4 iters)

Root cause (confirmed by the global solver's total failure): the C0 mesh is a
FUSED body+armor single mesh. Armor and body vertices are structurally interlocked
— the armor was authored seated ON the body, so separating any crossing creates a
new one elsewhere. This is a TOPOLOGICAL problem, not an algorithmic one: no local
or gradient-based vertex displacement can separate two surfaces that were modeled
as one. The independent-push (worse) and global-relaxation (no-improvement) results
are the honest, reproducible evidence.

## Correct repair direction (recorded boundary)

The repair requires MESH DECOMPOSITION first — separating the fused mesh into
distinct body and armor surfaces (via vertex-group/UV/material masks or a remesh)
BEFORE applying separation displacements. On already-separated meshes, the
bidirectional separation converges (the coupling that blocks it here would not
exist). The current C0 asset does not carry body/armor separation masks, so this
is blocked on asset decomposition, not on the repair algorithm.

Strike-2+1 discipline applied: three repair approaches falsified on the fused mesh;
further local-push iteration is halted. The honest next unit is mesh decomposition.

## Honest state

Detection: works, validated (145 clusters >0.5 mm on C0; deepest -3.26 mm left hip).
Repair: non-destructive pipeline + global iterative solver both implemented and
receipted, but NEITHER converges on the fused body+armor mesh — recorded as
falsified with the decomposition-boundary diagnosis. The Mesh Doctor currently
DETECTS and SURFACES; it does not yet repair. Promotion gates and ForgeLens UI
are forward work.
