#!/usr/bin/env python3
"""ForgeLens Mesh Doctor — global iterative penetration repair (Blender worker).

Corrects the falsified independent per-cluster push (P4_MESH_DOCTOR_REPAIR):
on a FUSED single mesh, repairing clusters independently drives the region into
adjacent penetrations. This worker instead performs a GLOBAL, ITERATIVE relaxation:

  1. Each iteration detects all genuine crossings, accumulates a coupled
     separation displacement over the whole mesh (each crossing contributes a
     bidirectional separation weighted toward the deepest local regions), and
     applies a damped step.
  2. EFFICACY GATE: after each step the total genuine-crossing count is
     re-measured. A step that does not strictly reduce it is rolled back and the
     damping is reduced. Iteration stops on no-improvement or convergence.
  3. The converged total displacement is written as ONE corrective shape key on a
     COPY (non-destructive), exported as a new immutable candidate GLB + receipt.
     Never mutates or promotes the reviewed artifact.

runtime_admitted=False, promoted=False.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def world_geometry(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    mw = ev.matrix_world
    verts = [mw @ v.co for v in me.vertices]
    tris = [tuple(t.vertices) for t in me.loop_triangles]
    ev.to_mesh_clear()
    return verts, tris, mw


def genuine_crossings(verts, tris, min_depth=0.0005):
    """Return list of (t1i, t2i, depth, point, normal) genuine crossings."""
    bvh = BVHTree.FromPolygons(verts, tris, all_triangles=True, epsilon=0.0)
    ov = bvh.overlap(bvh)
    out = []
    for t1i, t2i in ov:
        if t1i >= t2i:
            continue
        t1, t2 = tris[t1i], tris[t2i]
        if set(t1) & set(t2):
            continue
        a, b, c = verts[t2[0]], verts[t2[1]], verts[t2[2]]
        n = (b - a).cross(c - a)
        if n.length < 1e-12:
            continue
        n = n.normalized()
        d = [(verts[t1[k]] - a).dot(n) for k in range(3)]
        if max(d) > 1e-6 and min(d) < -1e-6:
            depth = max(abs(x) for x in d)
            if depth > min_depth:
                k = min(range(3), key=lambda k: abs(d[k]))
                out.append((t1i, t2i, depth, verts[t1[k]], n, t1, t2, d))
    return out


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--glb", required=True)
    ap.add_argument("--out-glb", required=True)
    ap.add_argument("--out-receipt", required=True)
    ap.add_argument("--object", default=None)
    ap.add_argument("--iters", type=int, default=8)
    ap.add_argument("--min-depth-m", type=float, default=0.0005)
    ap.add_argument("--step", type=float, default=0.6, help="separation step scale")
    args = ap.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args.glb)
    src = None
    for ob in bpy.data.objects:
        if ob.type == "MESH" and (args.object is None or ob.name == args.object):
            if ob.find_armature() is not None or args.object is not None:
                src = ob
                break
    if src is None:
        src = max([o for o in bpy.data.objects if o.type == "MESH"], key=lambda o: len(o.data.vertices))

    dup = src.copy()
    dup.data = src.data.copy()
    bpy.context.collection.objects.link(dup)
    dup.name = src.name + "_meshdoctor_candidate"
    n = len(dup.data.vertices)
    mw_inv3 = dup.matrix_world.inverted().to_3x3()

    # Work in LOCAL space (shape-key space). Convert world crossings to local.
    # cumulative local displacement per vertex
    disp = [Vector((0, 0, 0)) for _ in range(n)]
    history = []
    base_verts, base_tris, _ = world_geometry(dup)
    prev_count = len(genuine_crossings(base_verts, base_tris, args.min_depth_m))
    history.append(prev_count)

    damping = args.step
    for it in range(args.iters):
        verts, tris, _ = world_geometry(dup)
        crossings = genuine_crossings(verts, tris, args.min_depth_m)
        if not crossings:
            break
        # accumulate local separation displacement
        step_disp = [Vector((0, 0, 0)) for _ in range(n)]
        weight = [0.0] * n
        for (t1i, t2i, depth, point, normal, t1, t2, d) in crossings:
            half = 0.5 * (depth + 0.0005) * damping
            off_local = mw_inv3 @ (normal * half)
            for vi in t1:
                step_disp[vi] -= off_local
                weight[vi] += 1
            for vi in t2:
                step_disp[vi] += off_local
                weight[vi] += 1
        # apply (this mutates the candidate's BASIS for the iteration; we fold into
        # cumulative disp and reset basis from src each time to stay non-destructive)
        for vi in range(n):
            if weight[vi] > 0:
                step_disp[vi] /= weight[vi]
        # trial: compute new count with step applied
        trial = [Vector(dup.data.vertices[vi].co) + step_disp[vi] for vi in range(n)]
        mw = dup.matrix_world
        trial_world = [mw @ trial[vi] for vi in range(n)]
        new_count = len(genuine_crossings(trial_world, tris, args.min_depth_m))
        if new_count < prev_count:
            for vi in range(n):
                disp[vi] += step_disp[vi]
                dup.data.vertices[vi].co = trial[vi]
            dup.data.update()
            history.append(new_count)
            prev_count = new_count
        else:
            damping *= 0.5  # reject step, reduce damping
            history.append(prev_count)
            if damping < 0.05:
                break

    # Restore non-destructive: reset basis from source, then write cumulative
    # displacement into ONE shape key.
    for vi in range(n):
        dup.data.vertices[vi].co = src.data.vertices[vi].co
    dup.data.update()
    dup.shape_key_add(name="Basis", from_mix=False)
    key = dup.shape_key_add(name="meshdoctor_global_repair", from_mix=False)
    for vi in range(n):
        key.data[vi].co = src.data.vertices[vi].co + disp[vi]

    bpy.ops.object.select_all(action="DESELECT")
    dup.select_set(True)
    bpy.ops.export_scene.gltf(filepath=args.out_glb, export_format="GLB",
                              use_selection=True, export_morph=True, export_apply=False)

    receipt = {
        "schema": "just-dodge-forgelens-mesh-doctor-global-repair-v1",
        "runtime_admitted": False, "promoted": False, "non_destructive": True,
        "method": "global iterative relaxation with efficacy gate (monotone or rolled back)",
        "source_glb": args.glb, "source_sha256": sha256_file(args.glb),
        "candidate_glb": args.out_glb, "candidate_sha256": sha256_file(args.out_glb),
        "crossing_history": history,
        "initial_crossings": history[0], "final_crossings": history[-1],
        "iterations_run": len(history) - 1,
        "converged": history[-1] < history[0],
    }
    receipt["receipt_sha256"] = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()
    with open(args.out_receipt, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"MESH_DOCTOR_GLOBAL_REPAIR crossings {history[0]}->{history[-1]} converged={history[-1]<history[0]} candidate={args.out_glb}")
    return 0


main()
