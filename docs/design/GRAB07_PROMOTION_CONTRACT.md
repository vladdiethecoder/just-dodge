# JD-RC0-MESHDOCTOR-GRAB07-PROMOTION-003 — Shared Contract v1

Single source of truth for all agents. Do not deviate; extend only by appending
optional fields. Every artifact must be reproducible from the pinned executable
revision. Status is BLOCKED until all gates in the work order pass. No agent may
claim acceptance or promotion — only the human owner may approve/promote.

## 0. Pinned provenance (must appear in every receipt)

- `executable_revision`: `git rev-parse HEAD` at capture time (record exact value).
- `motion`: `assets/motion/pvp005_candidates/grab/grab_07.413.f32`
  sha256 `df134b66d5d239ac119ba48cd7dda4acd041db6521feaf0548ae8c2b9ec61444`
  (90 frames @ 25 fps, G1 34-joint Mat4 stream, prompt = two-handed torso grab).
- `mesh`: C0 armored duelist cooked bin + source GLB (record sha256 of each).
- `physics_hz`: 120 (`duel_physics::PHYSICS_TICKS_PER_SECOND`).
- `render_fps`: 60. Every render frame maps to exactly 2 physics substeps.
- Blender `5.1.2`; Python `3.14.6`; node `v24.3.0`; rustc `1.96.0`.

## 1. Actors

Two C0 armored duelists staged by the ENGINE, not hand-placed. The engine
autonomously stages fighters via `cleanbox.rs` (PLAYER_ROOT `+1Z`,
OPPONENT_ROOT `-1Z`, facing; Player forward `-Z`, Opponent `+Z`) and resolves
contact via `DuelWorld` (src/duel_world.rs) consuming shared-physics proxies +
`swept_contacts` CCD at 120 Hz, reduced by `duel_physics::physical_contact_batch`.

AUTHORITATIVE CONSTRAINT (measured, do not bypass): animation-skinned body
proxies fed into static `hitbox::contact` produce ZERO contact for the grab
across 0.10–0.50 m separations even at 2.88 cm hand-to-spine distance. This
matches the engine contract that "renderer skinning matrices and
sampled/generated animation poses are not valid substitutes" for shared-physics
proxies. Therefore the capture MUST drive the runtime's own match/truth loop
(DuelWorld) so the grab contact is measured by the engine's swept-CCD truth
path, not by a hand-built static scene. No hand-authored actor offsets.

Measured grab reach (retargeted grab_07, grabber at IDENTITY): hand envelope
x[-0.136,0.223] y[1.003,1.659] z[0.083,0.493]; grab reaches +Z at chest height.
Opponent is the receiving body; the engine's staged 2 m separation + reach
governs contact, not a swept constant.

- `grabber` (attacker): plays grab_07 forward from frame 0.
- `opponent` (defender): the receiving body, engine-staged facing the grabber.
  Record the exact opponent root transform the engine assigns in the receipt.

The grab is unmistakable only if hands meet torso; verify by the engine's
measured `PhysicalContactBatch` contact events, not by eye.

## 2. Phase segmentation (7 named spans, by physics_tick)

`tell, approach, first_contact, secure_grab, consequence, release, recovery`.
Assign each physics_tick a phase label. `first_contact` = first tick with a
grabber-hand↔opponent-body contact. Spans are contiguous and cover the whole
clip. Persist `{phase, start_physics_tick, end_physics_tick}` to `phases.json`.

## 3. Substep identifier (stable key used everywhere)

`substep_id = physics_tick` (integer, 0-based, monotonic, from
`SharedPhysicsStep.physics_tick`). `render_frame = physics_tick / 2`,
`substep_within_frame = physics_tick % 2`. All captures, findings, renders,
receipt rows, and ForgeLens scrub positions are keyed by `physics_tick`.

## 4. Registered cameras (5, fixed for the whole clip, identical across A/B)

`first_person, front, side, top, three_quarter`. Each camera stores
`{name, eye_m, target_m, up, fov_deg OR ortho_scale}`. The SAME 5 camera
definitions are used for BEFORE / DETECTED / REPAIR_PREVIEW / AFTER /
AB_DIFFERENCE so those 5 state-images are pixel-registered (diffable). Every
view must frame BOTH actors and all interacting hands/weapons. Camera rig goes
in `qa_runs/grab07_promotion/cameras.json` and is hashed into the receipt.

## 5. Per-substep capture record (JSONL, one line per physics_tick)

File `qa_runs/grab07_promotion/capture.jsonl`:
```
{ "schema":"grab07-capture-v1", "physics_tick":int, "render_frame":int,
  "substep_within_frame":int, "phase":str,
  "contacts":[ {"attacker":str,"defender":str,"attacker_proxy":int,
    "defender_proxy":int,"point_m":[f;3],"normal":[f;3],"depth_m":f,
    "time_of_impact":f,"mesh_pair":str } ],
  "max_penetration_depth_m":f, "rms_penetration_depth_m":f,
  "grabber_root":"sha256-of-pose", "opponent_root":"sha256-of-pose" }
```
`mesh_pair` is a stable string id, e.g. `"grabber:RightHand<->opponent:Spine2"`.
Pose hashes let the deterministic rerun prove identical inputs.

## 6. Penetration findings (Mesh Doctor, posed @120Hz)

Extend detection from bind pose to the POSED evaluated depsgraph at each
physics_tick. Each finding (see mesh-geometry-qa §3) persists:
`{artifact_sha256, revision, clip:"grab07", physics_tick, subframe, lod,
object_pair, mesh_pair, triangle_ids:[a,b], barycentric:[u,v,w],
world_point:[f;3], local_point:[f;3], normal:[f;3], signed_depth_m:f,
area_m2:f, duration_ticks:int}`. Write `findings.jsonl`. Identify
`worst_substep` = physics_tick of the single deepest signed penetration.

## 7. A/B/DIFF registered image set (at worst_substep)

For each of the 5 cameras, render 5 registered images:
`{view}_{BEFORE|DETECTED|REPAIR_PREVIEW|AFTER|AB_DIFFERENCE}.png`
- BEFORE: original posed meshes.
- DETECTED: penetration heatmap + contact points/normals overlaid.
- REPAIR_PREVIEW: corrective shape-key preview (non-destructive).
- AFTER: repaired candidate applied.
- AB_DIFFERENCE: per-pixel |AFTER-BEFORE| amplified, same framing.
Same camera, same lighting, same resolution → pixel-registered.

## 8. Diagnostic passes (12, at worst_substep + scrub-able in ForgeLens)

`beauty, wireframe, skeleton, object_id, material_id, normals, depth,
collision_proxies, penetration_heatmap, contact_points_normals,
allowed_contact_masks, trajectories` (weapon + per-hand world paths).
Each is a separate toggleable layer/file, named `{view}_{pass}.png` (or `.exr`
for depth). Trajectories may be overlays on beauty.

## 9. Strict receipt (receipt.json)

```
{ "schema":"grab07-promotion-receipt-v1",
  "executable_revision":str, "executable_sha256":str,
  "build": {"rustc":"1.96.0","blender":"5.1.2","python":"3.14.6","node":"v24.3.0"},
  "inputs": {"motion_sha256":str,"mesh_sha256":str,"cameras_sha256":str,
             "opponent_root_offset":[f;16]},
  "worst_substep":{"physics_tick":int,"render_frame":int},
  "mesh_pairs":[str],
  "before":{"max_penetration_m":f,"rms_penetration_m":f,"affected_area_m2":f,
            "duration_ticks":int,"min_clearance_m":f},
  "after":{ ...same fields... },
  "repair":{"moved_vertex_ids":[int],"moved_vertex_count":int,
            "max_displacement_m":f,"rms_displacement_m":f},
  "source_sha256":str,"output_sha256":str,
  "tool_version":str, "deterministic_rerun_sha256":str,
  "gates":{...}, "human_decision":"pending" }
```

## 10. Gates (fail-closed; record pass/fail + measured value each)

G1 zero prohibited body/cloth/armor intersections across clip.
G2 after-repair max signed penetration ≤ 0.5 mm.
G3 intended hand/body grab contacts present + drive truth (contact events exist
   in secure_grab span and appear in SharedDuelPhysics contacts).
G4 no texture holes / blacked-out / placeholder weapon material in beauty.
G5 grab unmistakable from first_person AND silhouette views.
G6 deterministic rerun reproduces every metric + hash exactly.
Only a human may set `human_decision` to approved/rejected. Automatic vision may
prioritize but never approve.

## 11. ForgeLens (tools/asset_review.*, plain JS + WebGL2 + Python stdlib)

Human can: scrub by physics_tick; toggle each of the 12 passes; pin the
offending triangle/contact (triangle + barycentric, not just screen px);
compare registered A/B states (side-by-side + flicker); comment; reject; approve.
Queue Blender repair creates a NEW immutable candidate + receipt; never mutates
or auto-promotes. No React/Vite/FastAPI/new framework.

## 12. Output layout (all under qa_runs/grab07_promotion/)

`capture.jsonl findings.jsonl phases.json cameras.json receipt.json
images/ (A/B/DIFF + passes) clip/ (60fps frames) repair_candidate.glb
repair_receipt.json DETERMINISM.md`
