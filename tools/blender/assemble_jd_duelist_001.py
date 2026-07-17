#!/usr/bin/env python3
"""Assemble JD_Duelist_001 part-separated component GLBs into one scene WITHOUT
joining, per the component manifest. Establishes meters, +Z-forward, named
collections, and per-component origins; records every source hash; exports
assembled.glb for the pair-clearance gate and downstream Blender authority work.

Deterministic, offline, no credits. Runs inside Blender headless:
  blender -b --factory-startup -noaudio --python tools/blender/assemble_jd_duelist_001.py -- \
      --manifest docs/design/JD_DUELIST_001_COMPONENT_MANIFEST.json \
      --components-dir DIR --out OUT.glb --receipt RECEIPT.json

Exits 0 with ASSEMBLE_PLAN_ONLY when no component GLBs are present (G1 pending).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

import bpy


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--components-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--receipt", required=True)
    return ap.parse_args(argv)


def main() -> int:
    args = parse_args()
    with open(args.manifest) as fh:
        manifest = json.load(fh)
    components = manifest["components"]

    import os
    present = [
        c for c in components
        if os.path.isfile(os.path.join(args.components_dir, f"{c['id']}.glb"))
    ]
    if not present:
        print(f"ASSEMBLE_PLAN_ONLY components={len(components)} (no GLBs present; G1 pending)")
        for c in components:
            print(f"  expect {c['id']}.glb kind={c['kind']} skinned={c['skinned']}")
        return 0

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    sources = []
    imported = []
    for comp in present:
        cid = comp["id"]
        path = os.path.join(args.components_dir, f"{cid}.glb")
        sources.append({
            "component_id": cid,
            "path": path,
            "sha256": sha256(path),
            "kind": comp["kind"],
            "skinned": comp["skinned"],
        })
        collection = bpy.data.collections.new(cid)
        scene.collection.children.link(collection)
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        new_objs = [o for o in bpy.data.objects if o not in before]
        for obj in new_objs:
            for coll in list(obj.users_collection):
                coll.objects.unlink(obj)
            collection.objects.link(obj)
            obj["component_id"] = cid
            obj["component_kind"] = comp["kind"]
        imported.append({"component_id": cid, "object_count": len(new_objs)})
        print(f"ASSEMBLE_IMPORT {cid} objects={len(new_objs)}")

    bpy.ops.export_scene.gltf(
        filepath=args.out,
        export_format="GLB",
        export_yup=True,
        export_apply=False,
        export_animations=False,
    )
    out_hash = sha256(args.out) if os.path.isfile(args.out) else None
    receipt = {
        "schema": "just-dodge.assembly-receipt.v1",
        "asset_id": manifest["asset_id"],
        "runtime_admitted": False,
        "components_imported": imported,
        "sources": sources,
        "output": {"path": args.out, "sha256": out_hash},
        "canonical": manifest["canonical"],
        "note": "components imported into named collections WITHOUT joining; "
                "authoritative retopo/rig/proxy work happens in later Blender steps",
    }
    with open(args.receipt, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"ASSEMBLE_OK components={len(present)} out={args.out} receipt={args.receipt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
