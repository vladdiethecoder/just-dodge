#!/usr/bin/env python3
"""ForgeLens Mesh Doctor — cross-object pair penetration detection (Blender).

Extends the single-mesh self-intersection detector to PAIRS of distinct objects
(cloth<->body, armor<->body, weapon<->body, weapon<->weapon). Uses BVH broad
phase between two objects' triangle sets, then triangle-level narrow phase for
genuine crossings (one triangle's vertices straddling the other's plane, crossing
point inside the other triangle, depth above the tolerance).

Each finding persists: artifact hash, revision, clip, frame/subframe, LOD,
object pair, triangle IDs (per-object), barycentric, world point, normal, depth.

This is the WO §4 pair-penetration detection. On separated meshes (unlike the
fused C0 body+armor), pair detection is meaningful and repair is tractable.
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


def world_tris(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    mw = ev.matrix_world
    verts = [mw @ v.co for v in me.vertices]
    tris = [tuple(t.vertices) for t in me.loop_triangles]
    ev.to_mesh_clear()
    return verts, tris


def tri_normal(verts, t):
    e1 = verts[t[1]] - verts[t[0]]
    e2 = verts[t[2]] - verts[t[0]]
    n = e1.cross(e2)
    return n.normalized() if n.length > 1e-12 else Vector((0, 0, 1))


def point_in_tri_bary(p, a, b, c):
    v0, v1, v2 = c - a, b - a, p - a
    d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
    d20, d21 = v2.dot(v0), v2.dot(v1)
    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-12:
        return (0.0, 0.0, 1.0), False
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w
    eps = 1e-6
    return (u, v, w), (u >= -eps and v >= -eps and w >= -eps)


def pair_crossings(verts_a, tris_a, verts_b, tris_b, min_depth):
    """Genuine crossings between two meshes' triangle sets."""
    bvh_a = BVHTree.FromPolygons(verts_a, tris_a, all_triangles=True, epsilon=0.0)
    bvh_b = BVHTree.FromPolygons(verts_b, tris_b, all_triangles=True, epsilon=0.0)
    overlaps = bvh_a.overlap(bvh_b)
    out = []
    for ai, bi in overlaps:
        ta, tb = tris_a[ai], tris_b[bi]
        # test ta crossing tb plane
        a, b, c = verts_b[tb[0]], verts_b[tb[1]], verts_b[tb[2]]
        n = tri_normal(verts_b, tb)
        d = [(verts_a[ta[k]] - a).dot(n) for k in range(3)]
        if max(d) > 1e-6 and min(d) < -1e-6:
            depth = max(abs(x) for x in d)
            if depth > min_depth:
                k = min(range(3), key=lambda k: abs(d[k]))
                p = verts_a[ta[k]]
                (u, v, w), inside = point_in_tri_bary(p, a, b, c)
                if inside:
                    out.append({"tri_a": ai, "tri_b": bi, "depth": depth,
                                "point": u*a+v*b+w*c, "normal": n, "bary": (u,v,w)})
        # also test tb crossing ta plane
        a, b, c = verts_a[ta[0]], verts_a[ta[1]], verts_a[ta[2]]
        n = tri_normal(verts_a, ta)
        d = [(verts_b[tb[k]] - a).dot(n) for k in range(3)]
        if max(d) > 1e-6 and min(d) < -1e-6:
            depth = max(abs(x) for x in d)
            if depth > min_depth:
                k = min(range(3), key=lambda k: abs(d[k]))
                p = verts_b[tb[k]]
                (u, v, w), inside = point_in_tri_bary(p, a, b, c)
                if inside:
                    out.append({"tri_a": ai, "tri_b": bi, "depth": depth,
                                "point": u*a+v*b+w*c, "normal": n, "bary": (u,v,w)})
    return out


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--glb", required=True)
    ap.add_argument("--object-a", required=True)
    ap.add_argument("--object-b", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--revision", default="unknown")
    ap.add_argument("--clip", default="bind")
    ap.add_argument("--min-depth-m", type=float, default=0.0001)
    ap.add_argument("--lod", default="LOD0")
    args = ap.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args.glb)
    obj_a = bpy.data.objects.get(args.object_a)
    obj_b = bpy.data.objects.get(args.object_b)
    if not obj_a or not obj_b:
        print(f"ERROR: object(s) not found: {args.object_a}, {args.object_b}")
        return 1

    verts_a, tris_a = world_tris(obj_a)
    verts_b, tris_b = world_tris(obj_b)
    crossings = pair_crossings(verts_a, tris_a, verts_b, tris_b, args.min_depth_m)

    findings = []
    for c in crossings:
        findings.append({
            "artifact_sha256": sha256_file(args.glb),
            "revision": args.revision, "clip": args.clip, "frame": 0, "lod": args.lod,
            "object_pair": [args.object_a, args.object_b],
            "triangle_ids": [c["tri_a"], c["tri_b"]],
            "barycentric": [round(x, 6) for x in c["bary"]],
            "world_point": [round(c["point"].x, 6), round(c["point"].y, 6), round(c["point"].z, 6)],
            "normal": [round(c["normal"].x, 4), round(c["normal"].y, 4), round(c["normal"].z, 4)],
            "signed_depth_m": round(-c["depth"], 6),
        })
    findings.sort(key=lambda f: f["signed_depth_m"])
    report = {
        "schema": "just-dodge-forgelens-mesh-doctor-pair-v1",
        "runtime_admitted": False,
        "glb": args.glb,
        "object_pair": [args.object_a, args.object_b],
        "tris_a": len(tris_a), "tris_b": len(tris_b),
        "findings_count": len(findings),
        "findings": findings[:200],
    }
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"MESH_DOCTOR_PAIR pair=[{args.object_a},{args.object_b}] findings={len(findings)} report={args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
