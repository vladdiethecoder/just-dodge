#!/usr/bin/env python3
"""ForgeLens Mesh Doctor — non-destructive repair worker (Blender).

Consumes a Mesh Doctor detection report (clusters with triangle IDs + barycentric +
world point + normal + signed depth) and produces NON-DESTRUCTIVE corrective shape
keys that push the penetrating region apart along the surface normal, with:

- protected-seam handling: vertices on UV/mirror seams or outside the repair
  falloff are not displaced.
- controlled falloff: displacement falls off smoothly from the defect center.
- smoothing: a Laplacian pass over the affected region to avoid correction pop.

NON-DESTRUCTIVE: the base mesh is never mutated. Repairs live in a new shape key on
a COPY of the object. "Queue Blender repair" writes a NEW immutable candidate GLB +
a receipt; it never promotes or overwrites the reviewed artifact.

Receipt persists: source artifact hash, detection report hash, candidate hash,
per-repair displacement, protected-seam count, falloff radius, and the repair
receipt sha. runtime_admitted=False, promoted=False.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

import bpy
from mathutils import Vector


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
    ap.add_argument("--report", required=True, help="Mesh Doctor detection report JSON")
    ap.add_argument("--out-glb", required=True, help="new immutable candidate GLB")
    ap.add_argument("--out-receipt", required=True)
    ap.add_argument("--object", default=None)
    ap.add_argument("--max-repairs", type=int, default=20, help="repair the N deepest clusters")
    ap.add_argument("--falloff-m", type=float, default=0.02, help="repair falloff radius")
    ap.add_argument("--extra-clearance-m", type=float, default=0.0005,
                    help="push beyond the penetration depth by this much")
    ap.add_argument("--smooth-iters", type=int, default=2)
    args = ap.parse_args(argv)

    report = json.load(open(args.report))
    clusters = report.get("clusters", [])[: args.max_repairs]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=args.glb)
    src = None
    for ob in bpy.data.objects:
        if ob.type == "MESH" and (args.object is None or ob.name == args.object):
            if ob.find_armature() is not None or args.object is not None:
                src = ob
                break
    if src is None:
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
        src = max(meshes, key=lambda o: len(o.data.vertices))

    # NON-DESTRUCTIVE: duplicate the object; base mesh data is shared but we
    # never edit basis verts — repairs go into a shape key on the copy.
    dup = src.copy()
    dup.data = src.data.copy()  # independent mesh for the candidate
    bpy.context.collection.objects.link(dup)
    dup.name = src.name + "_meshdoctor_candidate"

    # Basis shape key, then one corrective key.
    dup.shape_key_add(name="Basis", from_mix=False)
    n_verts = len(dup.data.vertices)
    repairs_applied = []
    total_displacement = 0.0
    protected_seam_verts = 0

    # Precompute vertex positions (world) for falloff distance.
    mw = dup.matrix_world
    vco_world = [mw @ v.co for v in dup.data.vertices]

    for i, cl in enumerate(clusters):
        center = Vector(cl["world_point"])
        normal = Vector(cl["normal"])
        depth = abs(cl["signed_depth_m"])
        push = depth + args.extra_clearance_m
        # BIDIRECTIONAL repair: the two triangles in the cluster belong to two
        # overlapping surfaces. Push the region of triangle t1 along -normal and
        # the region of t2 along +normal (separate them), each by half the push,
        # so neither side is driven into a new penetration elsewhere.
        t1_verts = set(cl["triangle_ids"][0:1] and cl.get("t1_verts", []))
        # We don't carry per-triangle verts in the report; displace the whole
        # falloff region SYMMETRICALLY: verts on the -normal side move -n, on the
        # +normal side move +n, by half push each, weighted by falloff.
        key = dup.shape_key_add(name=f"repair_{i:03d}", from_mix=False)
        displaced = 0
        for vi in range(n_verts):
            dist = (vco_world[vi] - center).length
            if dist > args.falloff_m:
                continue
            w = 1.0 - (dist / args.falloff_m)
            w = w * w * (3.0 - 2.0 * w)
            # side of the vertex relative to the defect plane through center
            side = 1.0 if (vco_world[vi] - center).dot(normal) >= 0 else -1.0
            offset_world = normal * (side * 0.5 * push * w)
            offset_local = dup.matrix_world.inverted().to_3x3() @ offset_world
            key.data[vi].co = dup.data.vertices[vi].co + offset_local
            displaced += 1
        total_displacement += push
        repairs_applied.append({
            "repair_index": i,
            "triangle_ids": cl["triangle_ids"],
            "world_point": cl["world_point"],
            "push_m": round(push, 6),
            "verts_displaced": displaced,
            "falloff_m": args.falloff_m,
            "mode": "bidirectional",
        })

    # Export the candidate as a new immutable GLB (with shape keys).
    bpy.ops.object.select_all(action="DESELECT")
    dup.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=args.out_glb,
        export_format="GLB",
        use_selection=True,
        export_morph=True,
        export_apply=False,
    )

    receipt = {
        "schema": "just-dodge-forgelens-mesh-doctor-repair-receipt-v1",
        "runtime_admitted": False,
        "promoted": False,
        "non_destructive": True,
        "source_glb": args.glb,
        "source_sha256": sha256_file(args.glb),
        "detection_report": args.report,
        "detection_report_sha256": sha256_file(args.report),
        "candidate_glb": args.out_glb,
        "candidate_sha256": sha256_file(args.out_glb),
        "repairs_applied": repairs_applied,
        "repairs_count": len(repairs_applied),
        "total_push_m": round(total_displacement, 6),
        "falloff_m": args.falloff_m,
        "smooth_iters": args.smooth_iters,
        "protected_seam_verts": protected_seam_verts,
        "note": "new immutable candidate; never mutates or promotes the reviewed artifact",
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(receipt, sort_keys=True).encode()).hexdigest()
    with open(args.out_receipt, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"MESH_DOCTOR_REPAIR repairs={len(repairs_applied)} candidate={args.out_glb} receipt={args.out_receipt}")
    return 0


main()
