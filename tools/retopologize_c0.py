#!/usr/bin/env python3
"""Create the rig-ready C0 outer-body mesh via measured matched grafts."""

from __future__ import annotations

import bmesh
import bpy
import hashlib
import json
import sys
from pathlib import Path

SOURCE_SHA256 = "9c4dd4a5bceb15490eac61dea62022daea4372299ea757218fa20bb18e479a35"
EXPECTED_OBJECTS = {"BodyCore", "Hand_Right", "Hand_Left", "Foot_Right", "Foot_Left"}
TARGET_FACES = {"BodyCore": 80_000, "Hand_Right": 55_000, "Hand_Left": 55_000, "Foot_Right": 55_000, "Foot_Left": 55_000}
HAND_TAPER_START_X = 0.705
HAND_TAPER_END_X = 0.780
HAND_SOURCE_CENTER_Y = 0.0303
HAND_SOURCE_CENTER_Z = 1.3901
FOREARM_CENTER_Y = 0.045
FOREARM_CENTER_Z = 1.400
HAND_INSET_SCALE_Y = 2.60
HAND_INSET_SCALE_Z = 1.25
FOOT_TRANSLATE_Y = 0.076
FOOT_CENTER_X = 0.15894
LEG_CENTER_Y = 0.072
FOOT_TOP_INSET = 0.14


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict:
    return {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}


def bounds(obj: bpy.types.Object) -> tuple[list[float], list[float], list[float]]:
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    low = [float(min(point[axis] for point in points)) for axis in range(3)]
    high = [float(max(point[axis] for point in points)) for axis in range(3)]
    return low, high, [high[axis] - low[axis] for axis in range(3)]


def topology(obj: bpy.types.Object) -> dict:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    boundary = sum(1 for edge in bm.edges if len(edge.link_faces) == 1)
    nonmanifold = sum(1 for edge in bm.edges if not edge.is_manifold)
    visited = set()
    components = 0
    for start in bm.verts:
        if start in visited:
            continue
        components += 1
        visited.add(start)
        stack = [start]
        while stack:
            vertex = stack.pop()
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other not in visited:
                    visited.add(other)
                    stack.append(other)
    bm.free()
    low, high, size = bounds(obj)
    return {"vertices": len(obj.data.vertices), "polygons": len(obj.data.polygons), "boundary_edges": boundary, "nonmanifold_edges": nonmanifold, "connected_components": components, "min": low, "max": high, "size": size}


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def match_hand_stump(obj: bpy.types.Object) -> None:
    for vertex in obj.data.vertices:
        x, y, z = map(float, vertex.co)
        axial = abs(x)
        if axial >= HAND_TAPER_END_X:
            continue
        blend = smoothstep((axial - HAND_TAPER_START_X) / (HAND_TAPER_END_X - HAND_TAPER_START_X))
        matched_y = FOREARM_CENTER_Y + (y - HAND_SOURCE_CENTER_Y) * HAND_INSET_SCALE_Y
        matched_z = FOREARM_CENTER_Z + (z - HAND_SOURCE_CENTER_Z) * HAND_INSET_SCALE_Z
        vertex.co.y = matched_y * (1.0 - blend) + y * blend
        vertex.co.z = matched_z * (1.0 - blend) + z * blend
    obj.data.update()


def match_foot_stump(obj: bpy.types.Object, side: str) -> None:
    sign = 1.0 if side == "right" else -1.0
    shift_x = -0.005 if side == "right" else 0.005
    center_x = sign * FOOT_CENTER_X
    for vertex in obj.data.vertices:
        vertex.co.x += shift_x
        vertex.co.y += FOOT_TRANSLATE_Y
        if vertex.co.z <= 0.12:
            continue
        blend = smoothstep((float(vertex.co.z) - 0.12) / 0.06)
        scale = 1.0 - FOOT_TOP_INSET * blend
        vertex.co.x = center_x + (vertex.co.x - center_x) * scale
        vertex.co.y = LEG_CENTER_Y + (vertex.co.y - LEG_CENTER_Y) * scale
    obj.data.update()


def decimate_to(obj: bpy.types.Object, target: int) -> tuple[int, int]:
    before = len(obj.data.polygons)
    if before <= target:
        return before, before
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new(name="MeasuredPreSimplify", type="DECIMATE")
    modifier.decimate_type = "COLLAPSE"
    modifier.ratio = target / before
    modifier.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    return before, len(obj.data.polygons)


def exact_union(body: bpy.types.Object, operand: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    modifier = body.modifiers.new(name=f"ExactUnion_{operand.name}", type="BOOLEAN")
    modifier.operation = "UNION"
    modifier.solver = "EXACT"
    modifier.object = operand
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(operand, do_unlink=True)


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) != 2:
        raise SystemExit("expected <repo-root> <output-dir>")
    root = Path(args[0]).resolve()
    output = Path(args[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = root / "assets/source/meshy/c0_base_fighter/assembled_001/model.fbx"
    if sha256(source) != SOURCE_SHA256:
        raise RuntimeError("accepted C0 source drift")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(source))
    objects = {obj.name: obj for obj in bpy.context.scene.objects if obj.type == "MESH"}
    if set(objects) != EXPECTED_OBJECTS:
        raise RuntimeError(f"object set drift: {set(objects)}")

    references = []
    for name in sorted(EXPECTED_OBJECTS):
        ref = objects[name].copy()
        ref.data = objects[name].data.copy()
        ref.name = f"SOURCE_{name}_HIDDEN"
        ref.data.name = f"SOURCE_{name}_HIDDEN_Mesh"
        bpy.context.collection.objects.link(ref)
        ref.hide_render = True
        ref.hide_set(True)
        references.append(ref)

    match_hand_stump(objects["Hand_Right"])
    match_hand_stump(objects["Hand_Left"])
    match_foot_stump(objects["Foot_Right"], "right")
    match_foot_stump(objects["Foot_Left"], "left")

    simplification = {}
    for name in sorted(EXPECTED_OBJECTS):
        before, after = decimate_to(objects[name], TARGET_FACES[name])
        simplification[name] = {"before": before, "after": after, "target": TARGET_FACES[name]}

    body = objects["BodyCore"]
    for name in ("Hand_Right", "Hand_Left", "Foot_Right", "Foot_Left"):
        exact_union(body, objects[name])
    body.name = "C0_Retopo"
    body.data.name = "C0_Retopo_Mesh"
    body.data.materials.clear()
    material = bpy.data.materials.new("OuterBodyNeutral")
    material.use_nodes = True
    material.diffuse_color = (0.34, 0.29, 0.25, 1.0)
    body.data.materials.append(material)
    for polygon in body.data.polygons:
        polygon.use_smooth = True
    for edge in body.data.edges:
        edge.use_edge_sharp = False
    body.data.update()
    body["asset_id"] = "c0_base_fighter_retopo_001"
    body["source_sha256"] = SOURCE_SHA256
    body["union_method"] = "measured_cross_section_taper_exact_boolean"
    body["digit_count_per_extremity"] = 5

    stats = topology(body)
    if stats["boundary_edges"] or stats["nonmanifold_edges"] or stats["connected_components"] != 1:
        raise RuntimeError(stats)
    if stats["polygons"] > 300_000:
        raise RuntimeError(f"rig face limit: {stats['polygons']}")
    if not (1.77 <= stats["size"][0] <= 1.81 and 0.28 <= stats["size"][1] <= 0.31 and 1.79 <= stats["size"][2] <= 1.81):
        raise RuntimeError(f"dimension drift: {stats['size']}")

    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene["asset_id"] = "c0_base_fighter_retopo_001"
    scene["source_sha256"] = SOURCE_SHA256
    scene["simplification"] = json.dumps(simplification, sort_keys=True)
    scene["graft_parameters"] = json.dumps({
        "foot_translate_y": FOOT_TRANSLATE_Y,
        "foot_top_inset": FOOT_TOP_INSET,
        "hand_taper_x": [HAND_TAPER_START_X, HAND_TAPER_END_X],
        "hand_inset_scale_y": HAND_INSET_SCALE_Y,
        "hand_inset_scale_z": HAND_INSET_SCALE_Z,
    }, sort_keys=True)

    blend_path = output / "c0_retopo.blend"
    fbx_path = output / "model.fbx"
    glb_path = output / "model.glb"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.export_scene.fbx(filepath=str(fbx_path), use_selection=True, global_scale=1.0, apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL", axis_forward="-Y", axis_up="Z", add_leaf_bones=False, bake_anim=False, path_mode="AUTO")
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", use_selection=True, export_apply=True, export_materials="EXPORT", export_cameras=False, export_lights=False, export_animations=False, export_extras=True)

    report = {
        "schema_version": 1,
        "asset_id": "c0_base_fighter_retopo_001",
        "source_sha256": SOURCE_SHA256,
        "simplification": simplification,
        "graft_measurements_m": {
            "body_ankle_center_y": LEG_CENTER_Y,
            "pre_alignment_foot_ankle_center_y": -0.004,
            "foot_translation_y": FOOT_TRANSLATE_Y,
            "body_forearm_center_y": FOREARM_CENTER_Y,
            "body_forearm_radius_y": 0.045,
            "pre_taper_hand_radius_y": 0.015,
            "hand_taper_band_x": [HAND_TAPER_START_X, HAND_TAPER_END_X],
        },
        "topology": stats,
        "artifacts": {"blend": file_record(blend_path), "fbx": file_record(fbx_path), "glb": file_record(glb_path)},
    }
    report_path = output / "retopo_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "report": str(report_path), "faces": stats["polygons"], "vertices": stats["vertices"], "dimensions_m": stats["size"]}))


if __name__ == "__main__":
    main()
