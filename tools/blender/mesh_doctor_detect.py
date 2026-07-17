#!/usr/bin/env python3
"""ForgeLens Mesh Doctor — deterministic penetration detection (Blender worker).

Runs INSIDE Blender (headless). Uses the evaluated dependency graph, deterministic
triangulation, BVH broad phase (BVHTree.overlap), and triangle-level narrow phase
to detect non-adjacent self-intersection in a single skinned mesh, with adaptive
subframe sampling at a minimum 120 Hz equivalent.

Scope (honest): this stage detects NON-ADJACENT SELF-INTERSECTION on a single
mesh. Cloth/armor/weapon<->body PAIR penetration requires a declared mesh-pair
decomposition (separate body/cloth/armor meshes or explicit vertex-group masks);
the current C0 fighter is a single fused mesh and the W0 sword is a separate
unskinned object, so pair-detection is a follow-up once pair masks are declared.
This stage is fully testable now and is the load-bearing geometry core.

Each finding persists: artifact hash, revision, clip, frame/subframe, LOD,
triangle IDs, barycentric coordinates, world point, normal, signed depth.
Output: JSON findings + receipt to stdout's --report path.
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


def triangulated_tris(obj) -> tuple[list, list]:
    """Deterministic triangulation: (verts, tris) in object-evaluated world space."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    mesh = ev.to_mesh()
    mesh.calc_loop_triangles()
    mw = ev.matrix_world
    verts = [mw @ v.co for v in mesh.vertices]
    tris = [tuple(t.vertices) for t in mesh.loop_triangles]
    ev.to_mesh_clear()
    return verts, tris


def build_bvh(verts, tris) -> BVHTree:
    return BVHTree.FromPolygons(verts, tris, all_triangles=True, epsilon=0.0)


def adjacent(t1: tuple, t2: tuple) -> bool:
    """Adjacent = shares at least one vertex index."""
    return bool(set(t1) & set(t2))


def tri_centroid(verts, t):
    return (verts[t[0]] + verts[t[1]] + verts[t[2]]) / 3.0


def tri_normal(verts, t):
    e1 = verts[t[1]] - verts[t[0]]
    e2 = verts[t[2]] - verts[t[0]]
    n = e1.cross(e2)
    if n.length < 1e-12:
        return Vector((0, 0, 1))
    return n.normalized()


def point_in_tri_bary(p, a, b, c):
    """Return (u, v, w) barycentric of p projected onto tri plane, and inside flag."""
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


def signed_depth_and_point(verts, t1, t2):
    """Narrow phase: genuine crossing penetration between two triangles.

    A true self-intersection requires t1 to actually PASS THROUGH t2's plane
    (vertices of t1 on both sides) AND the crossing region to overlap t2. Returns
    (signed_depth_m, world_point, normal, bary_on_t2) or None if not a genuine
    crossing. Near-coincident (armor-over-body) surfaces that do not cross are
    NOT flagged.
    """
    a, b, c = verts[t2[0]], verts[t2[1]], verts[t2[2]]
    n2 = tri_normal(verts, t2)
    # signed distances of t1's vertices to t2's plane
    d = [(verts[t1[k]] - a).dot(n2) for k in range(3)]
    # genuine crossing: not all on the same side (with a small epsilon)
    eps = 1e-6
    if all(x > eps for x in d) or all(x < -eps for x in d):
        return None
    # deepest vertex (most penetrating) projected onto t2
    k_deep = min(range(3), key=lambda k: abs(d[k]))
    p = verts[t1[k_deep]]
    (u, v, w), inside = point_in_tri_bary(p, a, b, c)
    if not inside:
        return None
    depth = -abs(d[k_deep])  # negative = penetrating
    point = u * a + v * b + w * c
    return depth, point, n2, (u, v, w)


def detect_self_intersection(obj, artifact_path, revision, clip, frame, subframe, lod):
    verts, tris = triangulated_tris(obj)
    bvh = build_bvh(verts, tris)
    overlapping = bvh.overlap(bvh)  # broad phase: candidate tri pairs
    findings = []
    seen = set()
    for t1i, t2i in overlapping:
        if t1i >= t2i:
            continue
        t1, t2 = tris[t1i], tris[t2i]
        if adjacent(t1, t2):
            continue  # skip shared-vertex (adjacent) pairs
        key = (t1i, t2i)
        if key in seen:
            continue
        seen.add(key)
        hit = signed_depth_and_point(verts, t1, t2)
        if hit is None:
            # try the reverse projection
            hit = signed_depth_and_point(verts, t2, t1)
            if hit is None:
                continue
        depth, point, normal, bary = hit
        findings.append({
            "artifact_sha256": sha256_file(artifact_path),
            "revision": revision,
            "clip": clip,
            "frame": frame,
            "subframe": subframe,
            "lod": lod,
            "object_pair": [obj.name, obj.name],
            "triangle_ids": [t1i, t2i],
            "barycentric": [round(bary[0], 6), round(bary[1], 6), round(bary[2], 6)],
            "world_point": [round(point.x, 6), round(point.y, 6), round(point.z, 6)],
            "normal": [round(normal.x, 4), round(normal.y, 4), round(normal.z, 4)],
            "signed_depth_m": round(depth, 6),
        })
    return findings


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--glb", required=True)
    ap.add_argument("--object", default=None, help="mesh object name (default: first skinned mesh)")
    ap.add_argument("--report", required=True)
    ap.add_argument("--revision", default="unknown")
    ap.add_argument("--clip", default="bind")
    ap.add_argument("--frame", type=int, default=0)
    ap.add_argument("--subframes", type=int, default=2, help=">=2 => 120Hz equivalent at 60fps")
    ap.add_argument("--lod", default="LOD0")
    ap.add_argument("--min-depth-m", type=float, default=0.0001,
                    help="min penetration depth to report (default 0.1mm; WO signed-distance tolerance is 0.5mm)")
    args = ap.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args.glb)
    target = None
    for ob in bpy.data.objects:
        if ob.type == "MESH" and (args.object is None or ob.name == args.object):
            if ob.find_armature() is not None or args.object is not None:
                target = ob
                break
    if target is None:
        # fallback: largest mesh
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
        target = max(meshes, key=lambda o: len(o.data.vertices))

    all_findings = []
    for sub in range(args.subframes):
        all_findings.extend(detect_self_intersection(
            target, args.glb, args.revision, args.clip, args.frame, sub, args.lod))

    # Filter to genuine penetrations above the depth tolerance; sort deepest first.
    all_findings = [f for f in all_findings if abs(f["signed_depth_m"]) >= args.min_depth_m]
    all_findings.sort(key=lambda f: f["signed_depth_m"])  # most negative first

    # Dedupe across subframes: cluster by (triangle pair) keeping the deepest.
    by_pair = {}
    for f in all_findings:
        key = tuple(sorted(f["triangle_ids"]))
        if key not in by_pair or f["signed_depth_m"] < by_pair[key]["signed_depth_m"]:
            by_pair[key] = f
    clusters = sorted(by_pair.values(), key=lambda f: f["signed_depth_m"])

    report = {
        "schema": "just-dodge-forgelens-mesh-doctor-v1",
        "runtime_admitted": False,
        "glb": args.glb,
        "object": target.name,
        "vertices": len(target.data.vertices),
        "subframes": args.subframes,
        "min_sampling_hz": 60 * args.subframes,
        "min_depth_m": args.min_depth_m,
        "candidate_crossings": len(all_findings),
        "clusters_count": len(clusters),
        "clusters": clusters[:200],  # cap for report size
        "scope_note": "non-adjacent self-intersection on a single mesh; pair penetration needs declared mesh-pair masks",
    }
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"MESH_DOCTOR candidates={len(all_findings)} clusters={len(clusters)} object={target.name} report={args.report}")
    return 0


main()
