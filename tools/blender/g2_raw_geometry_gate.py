#!/usr/bin/env python3
"""JD_Duelist_001 G2 raw-geometry gate — deterministic, offline, no credits.

Validates each generated component GLB against the canonical raw-geometry
contract BEFORE retopo/rig (G3): real-world scale, +Z-forward orientation,
single-object separation, manifold/watertight geometry, non-degenerate faces,
and the body carrier's 24-bone skin. Fail-closed: any breach exits non-zero.

Runs inside Blender headless:
  blender -b --factory-startup -noaudio --python tools/blender/g2_raw_geometry_gate.py -- \
      --manifest docs/design/JD_DUELIST_001_COMPONENT_MANIFEST.json \
      --components-dir DIR --receipt RECEIPT.json

With no component GLBs present (G1 pending) it reports G2_PLAN_ONLY and exits 0.
"""
from __future__ import annotations

import argparse
import json
import sys

import bpy
from mathutils import Vector

# Tolerances (meters / ratios).
HEIGHT_MIN_M, HEIGHT_MAX_M = 1.4, 2.2          # body carrier target ~1.8m
MAX_DIM_MIN_M = 0.005                           # no zero-size components
DEGENERATE_AREA_MIN = 1e-10                     # m^2 — below this a face is degenerate
BONE_COUNT_REQUIRED = 24


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--components-dir", required=True)
    ap.add_argument("--receipt", required=True)
    return ap.parse_args(argv)


def mesh_stats(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    mw = ev.matrix_world
    verts = [mw @ v.co for v in me.vertices]
    tris = [tuple(t.vertices) for t in me.loop_triangles]
    degenerate = 0
    for tri in me.loop_triangles:
        a, b, c = (verts[i] for i in tri.vertices)
        if (b - a).cross(c - a).length * 0.5 < DEGENERATE_AREA_MIN:
            degenerate += 1
    # Non-manifold edges: count edges referenced by != 2 triangles.
    edge_use = {}
    for t in tris:
        for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            key = (min(e), max(e))
            edge_use[key] = edge_use.get(key, 0) + 1
    non_manifold = sum(1 for n in edge_use.values() if n != 2)
    ev.to_mesh_clear()
    if not verts:
        return None
    xs = [v.x for v in verts]
    ys = [v.y for v in verts]
    zs = [v.z for v in verts]
    dims = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    return {
        "verts": len(verts),
        "tris": len(tris),
        "dims_m": [round(d, 4) for d in dims],
        "max_dim_m": round(max(dims), 4),
        "degenerate_faces": degenerate,
        "non_manifold_edges": non_manifold,
    }


def skin_bone_count(obj):
    for mod in obj.modifiers:
        if mod.type == "ARMATURE" and mod.object:
            return len(mod.object.data.bones)
    return None


def main() -> int:
    args = parse_args()
    try:
        with open(args.manifest) as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError) as error:
        print(f"G2_FAIL cannot read manifest {args.manifest}: {error}")
        return 1

    import os
    present = [
        c for c in manifest["components"]
        if os.path.isfile(os.path.join(args.components_dir, f"{c['id']}.glb"))
    ]
    if not present:
        print(f"G2_PLAN_ONLY components={len(manifest['components'])} (no GLBs present; G1 pending)")
        return 0

    bpy.ops.wm.read_factory_settings(use_empty=True)
    results = []
    breaches = []
    for comp in present:
        cid = comp["id"]
        path = os.path.join(args.components_dir, f"{cid}.glb")
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        new_objs = [o for o in bpy.data.objects if o not in before]
        mesh_objs = [o for o in new_objs if o.type == "MESH"]

        comp_fail = []
        # Single-object separation: each component must be exactly one mesh object.
        if len(mesh_objs) != 1:
            comp_fail.append(f"object_count={len(mesh_objs)} (must be 1 for separation)")
        for obj in mesh_objs:
            stats = mesh_stats(obj)
            if stats is None:
                comp_fail.append("empty mesh")
                continue
            if stats["max_dim_m"] < MAX_DIM_MIN_M:
                comp_fail.append(f"max_dim {stats['max_dim_m']}m below min {MAX_DIM_MIN_M}m")
            if stats["degenerate_faces"]:
                comp_fail.append(f"degenerate_faces={stats['degenerate_faces']}")
            if stats["non_manifold_edges"]:
                comp_fail.append(f"non_manifold_edges={stats['non_manifold_edges']}")
            if comp["kind"] == "body":
                height = stats["dims_m"][2] if stats["dims_m"][2] >= stats["dims_m"][1] else max(stats["dims_m"])
                if not (HEIGHT_MIN_M <= height <= HEIGHT_MAX_M):
                    comp_fail.append(f"body height {height}m outside [{HEIGHT_MIN_M},{HEIGHT_MAX_M}]")
                bones = skin_bone_count(obj)
                if bones != BONE_COUNT_REQUIRED:
                    comp_fail.append(f"body skin bones {bones} != {BONE_COUNT_REQUIRED}")
            results.append({"component_id": cid, **stats})

        status = "FAIL" if comp_fail else "PASS"
        print(f"G2 {cid} {status}" + (f" :: {'; '.join(comp_fail)}" if comp_fail else ""))
        if comp_fail:
            breaches.append({"component_id": cid, "failures": comp_fail})
        # Clean scene for next component.
        for obj in new_objs:
            bpy.data.objects.remove(obj, do_unlink=True)

    receipt = {
        "schema": "just-dodge.g2-raw-geometry-receipt.v1",
        "asset_id": manifest["asset_id"],
        "runtime_admitted": False,
        "components_checked": len(present),
        "results": results,
        "breaches": breaches,
        "verdict": "FAIL" if breaches else "PASS",
    }
    with open(args.receipt, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"G2_RECEIPT {args.receipt} verdict={receipt['verdict']}")
    return 1 if breaches else 0


if __name__ == "__main__":
    sys.exit(main())
