#!/usr/bin/env python3
"""Assemble C0 from a Meshy body core and validated extremity components."""

from __future__ import annotations

import bmesh
import bpy
import hashlib
import json
import statistics
import sys
from pathlib import Path

from mathutils import Matrix

SOURCE_HASHES = {
    "body": "00340dac5eeb68b73c61018c8bcebbdf8ad5efa0523cae6787a50739a1ed9a18",
    "hand": "61c91cac4d156496dc13028c67af0032674c1324db674bd70f0d5c9028529123",
    "foot": "c179062eb3a0b722a8cd898216c39a009e983027826af744df35e7c573fa96ef",
}
SOURCE_BOUNDS = {
    "body": (1.8269569874, 0.3141470551, 1.8989849091),
    "hand": (1.2718970776, 0.4523750544, 1.8993500471),
    "foot": (0.7162610292, 1.8994350433, 1.8113529682),
}
BODY_HEIGHT = 1.80
WRIST_CUT_X = 0.72
ANKLE_CUT_Z = 0.12


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict:
    return {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def world_bounds(obj: bpy.types.Object) -> tuple[list[float], list[float], list[float]]:
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    low = [float(min(point[axis] for point in points)) for axis in range(3)]
    high = [float(max(point[axis] for point in points)) for axis in range(3)]
    return low, high, [high[axis] - low[axis] for axis in range(3)]


def import_baked(path: Path, name: str, expected_bounds: tuple[float, float, float]) -> bpy.types.Object:
    bpy.ops.object.select_all(action="DESELECT")
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(path))
    meshes = [obj for obj in bpy.context.scene.objects if obj not in before and obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(f"{name}: expected one source mesh, got {len(meshes)}")
    obj = meshes[0]
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    obj.name = name
    obj.data.name = f"{name}_Mesh"
    _, _, size = world_bounds(obj)
    if any(abs(size[index] - expected_bounds[index]) > 2.0e-5 for index in range(3)):
        raise RuntimeError(f"{name}: source bounds drift {size}")
    return obj


def normalize_body(obj: bpy.types.Object) -> None:
    low, high, size = world_bounds(obj)
    scale = BODY_HEIGHT / size[2]
    center_x = (low[0] + high[0]) * 0.5
    center_y = (low[1] + high[1]) * 0.5
    for vertex in obj.data.vertices:
        vertex.co.x = (vertex.co.x - center_x) * scale
        vertex.co.y = (vertex.co.y - center_y) * scale
        vertex.co.z = (vertex.co.z - low[2]) * scale
    obj.data.update()
    _, _, result = world_bounds(obj)
    if abs(result[2] - BODY_HEIGHT) > 2.0e-5:
        raise RuntimeError(result)


def cube(name: str, dimensions: tuple[float, float, float], center: tuple[float, float, float]) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}_Mesh"
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def boolean_intersect(obj: bpy.types.Object, name: str, dimensions: tuple[float, float, float], center: tuple[float, float, float]) -> None:
    cutter = cube(f"{name}_Cutter", dimensions, center)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new(name=name, type="BOOLEAN")
    modifier.operation = "INTERSECT"
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Roughness"].default_value = 0.72
    return mat


def assign(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def tag(obj: bpy.types.Object, component_id: str, source: str, side: str, digit_count: int | None, graft: str) -> None:
    obj["component_id"] = component_id
    obj["source"] = source
    obj["side"] = side
    obj["graft_interface"] = graft
    obj["material_family"] = "outer_body_neutral"
    if digit_count is not None:
        obj["digit_count"] = digit_count


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
    low, high, size = world_bounds(obj)
    return {"vertices": len(obj.data.vertices), "polygons": len(obj.data.polygons), "boundary_edges": boundary, "nonmanifold_edges": nonmanifold, "connected_components": components, "min": low, "max": high, "size": size}


def validate(obj: bpy.types.Object) -> dict:
    stats = topology(obj)
    if stats["boundary_edges"] or stats["nonmanifold_edges"] or stats["connected_components"] != 1:
        raise RuntimeError(f"{obj.name}: {stats}")
    return stats


def sample_body_interfaces(obj: bpy.types.Object) -> dict:
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    wrist_points = [point for point in points if abs(abs(point.x) - WRIST_CUT_X) < 0.035 and point.z > 1.15]
    ankle_right = [point for point in points if 0.11 < point.z < 0.24 and point.x > 0.0]
    if not wrist_points or not ankle_right:
        raise RuntimeError("failed to sample body graft interfaces")
    return {
        "wrist_y": float(statistics.median(point.y for point in wrist_points)),
        "wrist_z": float(statistics.median(point.z for point in wrist_points)),
        "ankle_x": float(statistics.median(point.x for point in ankle_right)),
    }


def normalize_hand_local(obj: bpy.types.Object) -> None:
    low, high, size = world_bounds(obj)
    center_x = (low[0] + high[0]) * 0.5
    center_y = (low[1] + high[1]) * 0.5
    for vertex in obj.data.vertices:
        vertex.co.x = (vertex.co.x - center_x) * (0.090 / size[0])
        vertex.co.y = (vertex.co.y - center_y) * (0.035 / size[1])
        vertex.co.z = (vertex.co.z - low[2]) * (0.190 / size[2])
    obj.data.update()


def place_right_hand(obj: bpy.types.Object, wrist_y: float, wrist_z: float) -> None:
    for vertex in obj.data.vertices:
        local_x, local_y, local_z = float(vertex.co.x), float(vertex.co.y), float(vertex.co.z)
        vertex.co.x = WRIST_CUT_X - 0.015 + local_z
        vertex.co.y = wrist_y + local_y
        vertex.co.z = wrist_z - local_x
    obj.data.update()


def mirror_x(source: bpy.types.Object, name: str) -> bpy.types.Object:
    obj = source.copy()
    obj.data = source.data.copy()
    obj.name = name
    obj.data.name = f"{name}_Mesh"
    bpy.context.collection.objects.link(obj)
    for vertex in obj.data.vertices:
        vertex.co.x = -vertex.co.x
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    bm.normal_update()
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return obj


def normalize_foot(obj: bpy.types.Object, ankle_x: float) -> None:
    low, high, size = world_bounds(obj)
    center_x = (low[0] + high[0]) * 0.5
    center_y = (low[1] + high[1]) * 0.5
    for vertex in obj.data.vertices:
        vertex.co.x = ankle_x + (vertex.co.x - center_x) * (0.100 / size[0])
        vertex.co.y = -0.055 + (vertex.co.y - center_y) * (0.270 / size[1])
        vertex.co.z = (vertex.co.z - low[2]) * (0.200 / size[2])
    obj.data.update()
    boolean_intersect(obj, "FlatAnkleGraft", (0.16, 0.36, 0.19), (ankle_x, -0.055, 0.085))


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) != 2:
        raise SystemExit("expected <repo-root> <output-dir>")
    root = Path(args[0]).resolve()
    output = Path(args[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    sources = {
        "body": root / "assets/source/meshy/c0_base_fighter/candidate_003/model.fbx",
        "hand": root / "assets/source/meshy/c0_base_fighter/hand_candidate_001/model.fbx",
        "foot": root / "assets/source/meshy/c0_base_fighter/foot_candidate_002/model.fbx",
    }
    for key, path in sources.items():
        if sha256(path) != SOURCE_HASHES[key]:
            raise RuntimeError(f"{key} source drift: {sha256(path)}")

    clear_scene()
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    skin = material("OuterBodyNeutral", (0.34, 0.29, 0.25, 1.0))

    body = import_baked(sources["body"], "BodyCore", SOURCE_BOUNDS["body"])
    normalize_body(body)
    interfaces = sample_body_interfaces(body)
    reference = body.copy()
    reference.data = body.data.copy()
    reference.name = "C0_BodyCandidate003_HIDDEN"
    reference.data.name = "C0_BodyCandidate003_HIDDEN_Mesh"
    bpy.context.collection.objects.link(reference)
    reference.hide_render = True
    reference.hide_set(True)
    boolean_intersect(body, "BodyExtremityCuts", (WRIST_CUT_X * 2.0, 1.0, 2.0), (0.0, 0.0, 1.12))
    assign(body, skin)
    tag(body, "c0.body_core", "meshy:019f4a0d-7b8e-75a9-939a-a575cae48168", "center", None, "closed wrist x=±0.72; closed ankle z=0.12")
    validate(body)

    hand_right = import_baked(sources["hand"], "Hand_Right", SOURCE_BOUNDS["hand"])
    normalize_hand_local(hand_right)
    place_right_hand(hand_right, interfaces["wrist_y"], interfaces["wrist_z"])
    assign(hand_right, skin)
    tag(hand_right, "c0.hand.right", "meshy:019f4a19-7e38-7ff2-ada0-c4e64a65c187", "right", 5, "15mm overlap at x=+0.72")
    validate(hand_right)

    hand_left = mirror_x(hand_right, "Hand_Left")
    assign(hand_left, skin)
    tag(hand_left, "c0.hand.left", "mirrored:meshy:019f4a19-7e38-7ff2-ada0-c4e64a65c187", "left", 5, "15mm overlap at x=-0.72")
    validate(hand_left)

    foot_right = import_baked(sources["foot"], "Foot_Right", SOURCE_BOUNDS["foot"])
    normalize_foot(foot_right, interfaces["ankle_x"])
    assign(foot_right, skin)
    tag(foot_right, "c0.foot.right", "meshy:019f4bef-03fa-7e89-beb5-747f41519a96", "right", 5, "60mm overlap above z=0.12")
    validate(foot_right)

    foot_left = mirror_x(foot_right, "Foot_Left")
    assign(foot_left, skin)
    tag(foot_left, "c0.foot.left", "mirrored:meshy:019f4bef-03fa-7e89-beb5-747f41519a96", "left", 5, "60mm overlap above z=0.12")
    validate(foot_left)

    components = [body, hand_right, hand_left, foot_right, foot_left]
    stats = {obj.name: validate(obj) for obj in components}
    low = [min(entry["min"][axis] for entry in stats.values()) for axis in range(3)]
    high = [max(entry["max"][axis] for entry in stats.values()) for axis in range(3)]
    size = [high[axis] - low[axis] for axis in range(3)]
    if not (1.76 <= size[0] <= 1.84 and 0.32 <= size[1] <= 0.38 and abs(size[2] - BODY_HEIGHT) <= 2.0e-5):
        raise RuntimeError(f"assembled dimensions: {size}")
    if abs(stats["Hand_Right"]["size"][0] - 0.190) > 2.0e-5 or abs(stats["Foot_Right"]["size"][1] - 0.270) > 2.0e-5:
        raise RuntimeError("extremity metric gate")

    scene["asset_id"] = "c0_base_fighter_assembled_001"
    scene["units"] = "meters"
    scene["pose"] = "symmetric_t_pose"
    scene["source_hashes"] = json.dumps(SOURCE_HASHES, sort_keys=True)
    scene["graft_interfaces"] = json.dumps(interfaces, sort_keys=True)

    blend_path = output / "c0_fighter_assembled.blend"
    fbx_path = output / "model.fbx"
    glb_path = output / "model.glb"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in components:
        obj.select_set(True)
    reference.select_set(False)
    bpy.ops.export_scene.fbx(filepath=str(fbx_path), use_selection=True, global_scale=1.0, apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL", axis_forward="-Y", axis_up="Z", add_leaf_bones=False, bake_anim=False, path_mode="AUTO")
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", use_selection=True, export_apply=True, export_materials="EXPORT", export_cameras=False, export_lights=False, export_animations=False, export_extras=True)

    report = {
        "schema_version": 1,
        "asset_id": "c0_base_fighter_assembled_001",
        "source_hashes": SOURCE_HASHES,
        "interfaces": interfaces,
        "dimensions_m": {"min": low, "max": high, "size": size},
        "components": stats,
        "artifacts": {"blend": file_record(blend_path), "fbx": file_record(fbx_path), "glb": file_record(glb_path)},
    }
    report_path = output / "assembly_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "report": str(report_path), "dimensions_m": size, "interfaces": interfaces}))


if __name__ == "__main__":
    main()
