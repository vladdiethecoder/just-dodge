#!/usr/bin/env python3
"""Validate the JD_Duelist_001 component manifest and any generated component GLBs
against the canonical contract (G0 brief / HIGH_FIDELITY_ASSET_PIPELINE.md).

Fail-closed: any schema violation or contract breach exits non-zero. This is
deterministic, offline, and spends no credits — it is the acceptance machinery
that consumes components once G0 is approved and they are generated.

Usage:
  python3 tools/qa/validate_component_manifest.py docs/design/JD_DUELIST_001_COMPONENT_MANIFEST.json \
      [--components-dir DIR]
"""
import argparse
import json
import struct
import sys

REQUIRED_CANONICAL = {
    "units": "meters",
    "forward_axis": "+Z",
    "bone_count": 24,
    "weapon_socket": "weapon_r",
}
REQUIRED_COMPONENT_KEYS = {"id", "kind", "skinned", "socket"}
VALID_KINDS = {"body", "armor", "weapon", "proxy"}


def fail(msg):
    print(f"MANIFEST_FAIL {msg}")
    sys.exit(1)


def validate_manifest(manifest):
    if manifest.get("schema") != "just-dodge.component-manifest.v1":
        fail(f"bad schema: {manifest.get('schema')!r}")
    if not manifest.get("asset_id"):
        fail("missing asset_id")
    canonical = manifest.get("canonical") or fail("missing canonical block")
    for key, want in REQUIRED_CANONICAL.items():
        got = canonical.get(key)
        if got != want:
            fail(f"canonical.{key}: want {want!r}, got {got!r}")
    components = manifest.get("components")
    if not isinstance(components, list) or not components:
        fail("components must be a non-empty list")
    ids = set()
    body = 0
    for comp in components:
        if not isinstance(comp, dict) or not REQUIRED_COMPONENT_KEYS.issubset(comp):
            fail(f"component missing required keys: {comp!r}")
        cid = comp["id"]
        if cid in ids:
            fail(f"duplicate component id: {cid}")
        ids.add(cid)
        if comp["kind"] not in VALID_KINDS:
            fail(f"{cid}: bad kind {comp['kind']!r}")
        if not isinstance(comp["skinned"], bool):
            fail(f"{cid}: skinned must be bool")
        if comp["kind"] == "body":
            body += 1
            if not comp["skinned"]:
                fail(f"{cid}: body carrier must be skinned")
        if comp["socket"] is not None and comp["socket"] != canonical["weapon_socket"]:
            fail(f"{cid}: socket {comp['socket']!r} != canonical {canonical['weapon_socket']!r}")
    if body != 1:
        fail(f"exactly one body carrier required, found {body}")
    return ids


def glb_bone_count(path):
    """Return the joint count of the first skin in a GLB, or None if unskinned.

    Parses the GLB JSON chunk only (stdlib); reads skins[0].joints length.
    """
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"glTF":
        fail(f"{path}: not a GLB (bad magic)")
    length = struct.unpack_from("<I", data, 8)[0]
    if length != len(data):
        fail(f"{path}: GLB length field {length} != file size {len(data)}")
    json_len, json_type = struct.unpack_from("<I4s", data, 12)
    if json_type != b"JSON":
        fail(f"{path}: first chunk is not JSON")
    doc = json.loads(data[20:20 + json_len])
    skins = doc.get("skins") or []
    if not skins:
        return None
    return len(skins[0].get("joints") or [])


def validate_components_dir(manifest, ids, directory, bone_count):
    import os
    found = 0
    for cid in sorted(ids):
        path = os.path.join(directory, f"{cid}.glb")
        if not os.path.isfile(path):
            continue  # components not yet generated are skipped, not failed
        found += 1
        comp = next(c for c in manifest["components"] if c["id"] == cid)
        joints = glb_bone_count(path)
        if comp["kind"] == "body":
            if joints != bone_count:
                fail(f"{cid}: body carrier joints {joints} != canonical {bone_count}")
        print(f"  component {cid}: glb present, joints={joints}")
    if found == 0:
        print("  no component GLBs present yet (G0 pending); schema-only validation")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--components-dir", default=None)
    args = ap.parse_args()
    with open(args.manifest) as f:
        manifest = json.load(f)
    ids = validate_manifest(manifest)
    print(f"MANIFEST_SCHEMA_OK components={len(ids)} asset_id={manifest['asset_id']}")
    if args.components_dir:
        validate_components_dir(
            manifest, ids, args.components_dir, manifest["canonical"]["bone_count"]
        )
    print("MANIFEST_VALIDATION_PASS")


if __name__ == "__main__":
    main()
