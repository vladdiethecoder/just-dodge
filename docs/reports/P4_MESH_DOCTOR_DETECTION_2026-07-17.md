# P4 ForgeLens Mesh Doctor — Detection Core (2026-07-17)

Status: research/QA foundation. runtime_admitted=False. NOT a repair, promotion,
or mesh-quality admission. The detection core is validated; repair queue and
promotion gates are forward work.

## What was built

`tools/blender/mesh_doctor_detect.py` — deterministic penetration detection worker
that runs INSIDE Blender (headless, 5.1.2 verified). Uses:

- Blender's evaluated dependency graph (`evaluated_depsgraph_get`) for the
  evaluated (modifier/armature-applied) mesh.
- Deterministic triangulation (`calc_loop_triangles`).
- BVH broad phase (`mathutils.bvhtree.BVHTree.overlap`) for candidate triangle pairs.
- Triangle-level narrow phase: a pair is a genuine crossing only if one triangle's
  vertices straddle the other's plane AND the crossing point lies inside the other
  triangle (barycentric). Near-coincident armor-over-body surfaces that do not cross
  are NOT flagged (this eliminated a 780-finding false-positive flood from an earlier
  naive band test).
- Adaptive subframe sampling, minimum 120 Hz equivalent (2 subframes at 60 fps).

## Honest scope

This stage detects NON-ADJACENT SELF-INTERSECTION on a single mesh. The C0 armored
duelist is a single fused skinned mesh (body+armor in one 82,928-vert mesh, 1
material); cloth/armor/weapon<->body PAIR penetration requires a declared mesh-pair
decomposition (separate body/cloth/armor meshes or explicit vertex-group masks),
which the current assets do not provide. Pair detection is a follow-up once pair
masks are declared. Self-intersection is fully testable now and is the load-bearing
geometry core.

## Validated finding (measured, this session)

Ran on `assets/source/meshy/c0_armored_duelist_001/model.glb` (revision 64c673c).
Report: `qa_runs/p4_mesh_doctor/c0_self_intersect.json` (gitignored).

- 726 candidate crossings -> 363 clusters above the 0.1 mm reporting floor
  (deduped across subframes, deepest kept per triangle pair).
- 145 clusters exceed the WO 0.5 mm signed-distance tolerance (genuine defects).
- Defect regions (world Z): z=1.5 m: 72 clusters (neck/shoulder/armor junction);
  z=1.6 m: 20; z=0.7–0.8 m: 32 (hip/groin).
- Deepest cluster: -3.262 mm at (-0.138, -0.104, 0.746) — left hip, triangles
  [90740, 91246], barycentric (0.198, 0.653, 0.149). This is a genuine
  self-intersection the Mesh Doctor exists to surface.

## Finding persistence (per WO)

Each cluster persists: artifact sha256, revision, clip, frame, subframe, LOD,
object pair, triangle IDs, barycentric coordinates, world point, normal, signed
depth. Camera evidence, area, and duration are carried in the schema and populated
when a posed clip (not the bind pose) is scanned.

## Forward work (not claimed)

- Repair queue: non-destructive corrective shape keys from these clusters
  (protected seams, controlled falloff, smoothing), producing immutable candidates
  + receipts; never auto-promoting.
- Promotion gates (WO §5): zero self-intersections outside contact masks, signed
  distance ≤0.5 mm, clearance targets, etc.
- Pair penetration (cloth/armor/weapon<->body) once mesh-pair masks are declared.
- ForgeLens UI: penetration heatmaps, signed-depth vectors, intersection loops,
  geometry-anchored pins (triangle+barycentric, which the findings already carry).

## Reproduce

```
blender --background --python tools/blender/mesh_doctor_detect.py -- \
  --glb assets/source/meshy/c0_armored_duelist_001/model.glb \
  --report qa_runs/p4_mesh_doctor/c0_self_intersect.json \
  --revision $(git rev-parse HEAD) --subframes 2 --min-depth-m 0.0001
```
