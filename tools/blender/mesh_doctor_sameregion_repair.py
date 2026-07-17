#!/usr/bin/env python3
"""ForgeLens Mesh Doctor — targeted same-region armor-plate repair (Blender).

The C0 fused mesh's self-intersections split (measured): 108 same-region (armor
plates folding onto themselves within one bone group — self-colliding cloth/armor,
tractable) vs 92 cross-region/unknown. Same-region folds do NOT have the
body<->armor coupling that falsified global repair; they can be separated by a
local unfold along the fold normal without driving adjacent surfaces into new
penetrations.

This worker:
  1. Re-detects self-intersections, classifying each as same-region (both triangles
     dominated by one bone group) vs cross-region.
  2. Repairs ONLY the same-region clusters (unfold: push the fold apart along its
     normal, symmetric bidirectional, narrow falloff).
  3. Per-iteration efficacy gate: measure the SAME-REGION crossing count before/after;
     only accept repairs that strictly reduce it. Cross-region count is reported but
     not targeted (those need body/armor decomposition).
  4. Non-destructive: corrective shape key on a copy, new immutable candidate + receipt.

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


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--glb", required=True)
    ap.add_argument("--out-glb", required=True)
    ap.add_argument("--out-receipt", required=True)
    ap.add_argument("--min-depth-m", type=float, default=0.0005)
    ap.add_argument("--falloff-m", type=float, default=0.012)
    ap.add_argument("--iters", type=int, default=6)
    args = ap.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args.glb)
    src = [o for o in bpy.data.objects if o.find_armature()][0]
    vg = [g.name for g in src.vertex_groups]
    # dominant bone group per vertex
    dom = {}
    for v in src.data.vertices:
        if v.groups:
            best = max(v.groups, key=lambda g: g.weight)
            dom[v.index] = vg[best.group] if best.weight > 0.5 else "?"

    dup = src.copy()
    dup.data = src.data.copy()
    bpy.context.collection.objects.link(dup)
    dup.name = src.name + "_meshdoctor_sameregion_candidate"
    n = len(dup.data.vertices)
    mw_inv3 = dup.matrix_world.inverted().to_3x3()

    def geom(obj):
        dg = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(dg)
        me = ev.to_mesh(); me.calc_loop_triangles()
        mw = ev.matrix_world
        verts = [mw @ v.co for v in me.vertices]
        tris = [tuple(t.vertices) for t in me.loop_triangles]
        ev.to_mesh_clear()
        return verts, tris

    def tri_group(tid, tris):
        s = {dom.get(v, "?") for v in tris[tid]}
        return s.pop() if len(s) == 1 else "MIXED"

    def crossings(verts, tris):
        bvh = BVHTree.FromPolygons(verts, tris, all_triangles=True, epsilon=0.0)
        out_same, out_cross = [], []
        for ai, bi in bvh.overlap(bvh):
            if ai >= bi:
                continue
            t1, t2 = tris[ai], tris[bi]
            if set(t1) & set(t2):
                continue
            a, b, c = verts[t2[0]], verts[t2[1]], verts[t2[2]]
            nrm = (b - a).cross(c - a)
            if nrm.length < 1e-12:
                continue
            nrm = nrm.normalized()
            d = [(verts[t1[k]] - a).dot(nrm) for k in range(3)]
            if max(d) > 1e-6 and min(d) < -1e-6:
                depth = max(abs(x) for x in d)
                if depth > args.min_depth_m:
                    g1, g2 = tri_group(ai, tris), tri_group(bi, tris)
                    entry = (ai, bi, depth, nrm)
                    if g1 == g2 and g1 not in ("?", "MIXED"):
                        out_same.append(entry)
                    else:
                        out_cross.append(entry)
        return out_same, out_cross

    history = []
    disp = [Vector((0, 0, 0)) for _ in range(n)]
    verts, tris = geom(dup)
    same0, cross0 = crossings(verts, tris)
    prev = len(same0)
    history.append({"same": prev, "cross": len(cross0)})
    damping = 0.5
    for it in range(args.iters):
        verts, tris = geom(dup)
        same, cross = crossings(verts, tris)
        if not same:
            break
        step = [Vector((0, 0, 0)) for _ in range(n)]
        w = [0.0] * n
        vco = [dup.matrix_world @ dup.data.vertices[i].co for i in range(n)]
        for (ai, bi, depth, nrm) in same:
            # unfold: push each side away along the fold normal, falloff-weighted
            t1, t2 = tris[ai], tris[bi]
            cen = (vco[t1[0]] + vco[t1[1]] + vco[t1[2]]) / 3.0
            for vi in set(t1) | set(t2):
                # displace the fold region's verts
                for vj in range(n):
                    d = (vco[vj] - cen).length
                    if d > args.falloff_m:
                        continue
                    wgt = 1 - d / args.falloff_m
                    wgt = wgt * wgt * (3 - 2 * wgt)
                    side = 1.0 if (vco[vj] - cen).dot(nrm) >= 0 else -1.0
                    step[vj] += mw_inv3 @ (nrm * (side * 0.5 * depth * damping * wgt))
                    w[vj] += 1
        for vi in range(n):
            if w[vi] > 0:
                step[vi] /= w[vi]
        trial = [Vector(dup.data.vertices[i].co) + step[i] for i in range(n)]
        mw = dup.matrix_world
        trial_world = [mw @ trial[i] for i in range(n)]
        s2, c2 = crossings(trial_world, tris)
        if len(s2) < prev:
            for vi in range(n):
                disp[vi] += step[vi]
                dup.data.vertices[vi].co = trial[vi]
            dup.data.update()
            history.append({"same": len(s2), "cross": len(c2)})
            prev = len(s2)
        else:
            damping *= 0.5
            if damping < 0.05:
                break

    # fold into a non-destructive shape key
    for vi in range(n):
        dup.data.vertices[vi].co = src.data.vertices[vi].co
    dup.data.update()
    dup.shape_key_add(name="Basis", from_mix=False)
    key = dup.shape_key_add(name="meshdoctor_sameregion_repair", from_mix=False)
    for vi in range(n):
        key.data[vi].co = src.data.vertices[vi].co + disp[vi]

    bpy.ops.object.select_all(action="DESELECT")
    dup.select_set(True)
    bpy.ops.export_scene.gltf(filepath=args.out_glb, export_format="GLB",
                              use_selection=True, export_morph=True, export_apply=False)

    receipt = {
        "schema": "just-dodge-forgelens-mesh-doctor-sameregion-repair-v1",
        "runtime_admitted": False, "promoted": False, "non_destructive": True,
        "method": "same-region armor-plate unfold with efficacy gate (cross-region not targeted)",
        "source_glb": args.glb, "source_sha256": sha256_file(args.glb),
        "candidate_glb": args.out_glb, "candidate_sha256": sha256_file(args.out_glb),
        "same_region_history": [h["same"] for h in history],
        "cross_region_history": [h["cross"] for h in history],
        "same_converged": history[-1]["same"] < history[0]["same"],
    }
    receipt["receipt_sha256"] = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()
    with open(args.out_receipt, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"MESH_DOCTOR_SAMEREGION same {history[0]['same']}->{history[-1]['same']} cross {history[0]['cross']}->{history[-1]['cross']} converged={history[-1]['same']<history[0]['same']}")
    return 0


main()
