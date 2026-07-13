#!/usr/bin/env python3
"""Deterministically assemble the W0 sword from validated Meshy components."""

from __future__ import annotations

import bmesh
import bpy
import hashlib
import json
import math
import sys
from pathlib import Path

from mathutils import Matrix, Vector

SOURCE_HASHES = {
    "blade": "54b982848c79c6a9a43d1cc5a125d66bf99d496ff012167a4f5feccfbe8825f2",
    "guard": "7f9b063789de67683fc29f8bc5fe1baa9852fc5342231f67c672b66de3800059",
    "pommel": "661f53c1092a94d7d3a19836f13e777a809cbf3b954b48bb59fc41576010487d",
}
SOURCE_BOUNDS = {
    "blade": (0.1174440011, 0.0563200004, 1.8989189863),
    "guard": (1.8995140195, 0.1984900013, 0.1164380051),
    "pommel": (1.0294950008, 0.7840690017, 1.8997290134),
}
TARGET_BOUNDS = {
    "blade": (0.052, 0.006, 1.475),
    "guard": (0.280, 0.030, 0.0175),
    "pommel": (0.070, 0.050, 0.060),
}
BLADE_SOURCE_SHOULDER_Z = -0.594
GRIP_TOP_Z = -0.025
GRIP_BOTTOM_Z = -0.270
POMMEL_CENTER_Z = -0.310


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict:
    return {"path": str(path), "sha256": file_hash(path), "bytes": path.stat().st_size}


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def world_bounds(obj: bpy.types.Object) -> tuple[list[float], list[float], list[float]]:
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    low = [float(min(point[axis] for point in points)) for axis in range(3)]
    high = [float(max(point[axis] for point in points)) for axis in range(3)]
    size = [high[axis] - low[axis] for axis in range(3)]
    return low, high, size


def assert_close_vector(actual: list[float], expected: tuple[float, float, float], tolerance: float, label: str) -> None:
    if any(abs(actual[index] - expected[index]) > tolerance for index in range(3)):
        raise RuntimeError(f"{label}: expected {expected}, got {actual}")


def import_baked(path: Path, name: str, expected_bounds: tuple[float, float, float]) -> bpy.types.Object:
    bpy.ops.object.select_all(action="DESELECT")
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(path))
    meshes = [obj for obj in bpy.context.scene.objects if obj not in before and obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(f"{path}: expected one mesh, got {len(meshes)}")
    obj = meshes[0]
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    obj.name = name
    obj.data.name = f"{name}_Mesh"
    _, _, size = world_bounds(obj)
    assert_close_vector(size, expected_bounds, 2.0e-5, f"{name} baked import bounds")
    return obj


def scale_geometry_to_bounds(
    obj: bpy.types.Object,
    target_size: tuple[float, float, float],
    target_center: tuple[float, float, float] | None = None,
    source_anchor_z: float | None = None,
    target_anchor_z: float | None = None,
) -> None:
    low, high, size = world_bounds(obj)
    center = [(low[axis] + high[axis]) * 0.5 for axis in range(3)]
    scale = [target_size[axis] / size[axis] for axis in range(3)]
    if target_center is None:
        target_center = (0.0, 0.0, 0.0)
    z_shift = target_center[2]
    if source_anchor_z is not None and target_anchor_z is not None:
        scaled_anchor_z = (source_anchor_z - center[2]) * scale[2]
        z_shift = target_anchor_z - scaled_anchor_z
    for vertex in obj.data.vertices:
        vertex.co.x = (vertex.co.x - center[0]) * scale[0] + target_center[0]
        vertex.co.y = (vertex.co.y - center[1]) * scale[1] + target_center[1]
        vertex.co.z = (vertex.co.z - center[2]) * scale[2] + z_shift
    obj.data.update()
    _, _, result_size = world_bounds(obj)
    assert_close_vector(result_size, target_size, 2.0e-5, f"{obj.name} target bounds")


def make_material(name: str, color: tuple[float, float, float, float], metallic: float, roughness: float) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def set_material(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def tag(obj: bpy.types.Object, component: str, material: str, mass: float, source: str, fracture: bool) -> None:
    obj["component_id"] = component
    obj["material_family"] = material
    obj["mass_kg_estimate"] = mass
    obj["source"] = source
    obj["fracture_enabled"] = fracture
    obj["assembly_origin"] = "guard_center"


def cube(name: str, dimensions: tuple[float, float, float], center: tuple[float, float, float]) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}_Mesh"
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def cylinder(name: str, radii: tuple[float, float], depth: float, center_z: float, vertices: int = 96) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=1.0, depth=depth, location=(0.0, 0.0, center_z))
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}_Mesh"
    obj.scale = (radii[0], radii[1], 1.0)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def subtract_channel(obj: bpy.types.Object, name: str, dimensions: tuple[float, float, float], center_z: float) -> None:
    cutter = cube(f"{name}_Cutter", dimensions, (0.0, 0.0, center_z))
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new(name=name, type="BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def make_wrap() -> bpy.types.Object:
    turns = 13.5
    path_count = int(turns * 48) + 1
    ring_count = 12
    radius = 0.00155
    centers: list[Vector] = []
    for index in range(path_count):
        t = index / (path_count - 1)
        angle = 2.0 * math.pi * turns * t
        centers.append(Vector((0.0223 * math.cos(angle), 0.0173 * math.sin(angle), GRIP_BOTTOM_Z + (GRIP_TOP_Z - GRIP_BOTTOM_Z) * t)))
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for index, center in enumerate(centers):
        tangent = (centers[min(path_count - 1, index + 1)] - centers[max(0, index - 1)]).normalized()
        angle = 2.0 * math.pi * turns * index / (path_count - 1)
        radial = Vector((math.cos(angle), math.sin(angle), 0.0))
        radial = (radial - tangent * radial.dot(tangent)).normalized()
        binormal = tangent.cross(radial).normalized()
        for ring in range(ring_count):
            around = 2.0 * math.pi * ring / ring_count
            point = center + radius * (math.cos(around) * radial + math.sin(around) * binormal)
            vertices.append((float(point.x), float(point.y), float(point.z)))
    for index in range(path_count - 1):
        first = index * ring_count
        second = (index + 1) * ring_count
        for ring in range(ring_count):
            nxt = (ring + 1) % ring_count
            faces.append((first + ring, first + nxt, second + nxt, second + ring))
    start_center = len(vertices)
    vertices.append((float(centers[0].x), float(centers[0].y), float(centers[0].z)))
    end_center = len(vertices)
    vertices.append((float(centers[-1].x), float(centers[-1].y), float(centers[-1].z)))
    last = (path_count - 1) * ring_count
    for ring in range(ring_count):
        nxt = (ring + 1) % ring_count
        faces.append((start_center, nxt, ring))
        faces.append((end_center, last + ring, last + nxt))
    mesh = bpy.data.meshes.new("GripWrap_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("GripWrap", mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def mesh_stats(obj: bpy.types.Object) -> dict:
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


def validate_component(obj: bpy.types.Object, expected_size: tuple[float, float, float] | None = None) -> dict:
    stats = mesh_stats(obj)
    if stats["boundary_edges"] or stats["nonmanifold_edges"] or stats["connected_components"] != 1:
        raise RuntimeError(f"{obj.name} topology: {stats}")
    if expected_size is not None:
        assert_close_vector(stats["size"], expected_size, 2.0e-5, f"{obj.name} validation")
    print(json.dumps({"validated_component": obj.name, "stats": stats}))
    return stats


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) != 2:
        raise SystemExit("expected <repo-root> <output-dir>")
    root = Path(args[0]).resolve()
    output = Path(args[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_paths = {
        "blade": root / "assets/source/meshy/w0_sword/blade_candidate_001/model.fbx",
        "guard": root / "assets/source/meshy/w0_sword/guard_candidate_001/model.fbx",
        "pommel": root / "assets/source/meshy/w0_sword/pommel_candidate_001/model.fbx",
    }
    for key, path in source_paths.items():
        if file_hash(path) != SOURCE_HASHES[key]:
            raise RuntimeError(f"source drift: {key}")

    clear_scene()
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    blade_mat = make_material("BladeSteel", (0.16, 0.19, 0.22, 1.0), 0.95, 0.28)
    guard_mat = make_material("GuardSteel", (0.10, 0.12, 0.14, 1.0), 0.90, 0.38)
    wood_mat = make_material("GripWood", (0.12, 0.045, 0.018, 1.0), 0.0, 0.72)
    leather_mat = make_material("GripLeather", (0.045, 0.012, 0.006, 1.0), 0.0, 0.62)
    pommel_mat = make_material("PommelSteel", (0.12, 0.15, 0.18, 1.0), 0.92, 0.34)

    blade = import_baked(source_paths["blade"], "BladeAndTang", SOURCE_BOUNDS["blade"])
    scale_geometry_to_bounds(blade, TARGET_BOUNDS["blade"], source_anchor_z=BLADE_SOURCE_SHOULDER_Z, target_anchor_z=0.0)
    set_material(blade, blade_mat)
    tag(blade, "w0.blade_tang", "quenched_tempered_steel", 1.05, "meshy:019f4a46-38c7-7949-82c9-c7d00993094a", True)
    validate_component(blade, TARGET_BOUNDS["blade"])

    guard = import_baked(source_paths["guard"], "Guard", SOURCE_BOUNDS["guard"])
    scale_geometry_to_bounds(guard, TARGET_BOUNDS["guard"], target_center=(0.0, 0.0, -0.006))
    subtract_channel(guard, "GuardTangSlot", (0.029, 0.008, 0.050), -0.006)
    set_material(guard, guard_mat)
    tag(guard, "w0.guard", "toughened_steel", 0.32, "meshy:019f4a4c-046a-7a38-8d93-c51896189157", True)
    validate_component(guard)
    validate_component(blade, TARGET_BOUNDS["blade"])

    grip_center = (GRIP_TOP_Z + GRIP_BOTTOM_Z) * 0.5
    grip = cylinder("GripCore", (0.021, 0.016), GRIP_TOP_Z - GRIP_BOTTOM_Z, grip_center)
    subtract_channel(grip, "GripTangChannel", (0.029, 0.008, 0.270), grip_center)
    set_material(grip, wood_mat)
    tag(grip, "w0.grip_core", "hardwood", 0.12, "local_repair:rejected_meshy_grip", True)
    validate_component(grip)

    wrap = make_wrap()
    set_material(wrap, leather_mat)
    tag(wrap, "w0.grip_wrap", "vegetable_tanned_leather", 0.05, "local_repair:continuous_helix", True)
    validate_component(wrap)

    # Collars deliberately overlap the adjacent parts by fractions of a
    # millimetre so the physical stack has no floating visual/mechanical gap.
    upper = cylinder("UpperCollar", (0.024, 0.019), 0.0105, -0.0199)
    lower = cylinder("LowerCollar", (0.024, 0.019), 0.0105, -0.275)
    for collar, center_z, suffix in ((upper, -0.020, "upper"), (lower, -0.275, "lower")):
        subtract_channel(collar, f"{suffix.title()}CollarTangSlot", (0.029, 0.008, 0.025), center_z)
        set_material(collar, guard_mat)
        tag(collar, f"w0.collar_{suffix}", "toughened_steel", 0.025, "local_mechanical_interface", False)
        validate_component(collar)

    pommel = import_baked(source_paths["pommel"], "Pommel", SOURCE_BOUNDS["pommel"])
    scale_geometry_to_bounds(pommel, TARGET_BOUNDS["pommel"], target_center=(0.0, 0.0, POMMEL_CENTER_Z))
    subtract_channel(pommel, "PommelTangChannel", (0.029, 0.008, 0.080), POMMEL_CENTER_Z)
    set_material(pommel, pommel_mat)
    tag(pommel, "w0.pommel", "toughened_steel", 0.42, "meshy_repair:019f4a4c-12e7-72fa-820d-1a085d29f74e", True)
    validate_component(pommel)
    validate_component(blade, TARGET_BOUNDS["blade"])

    tang = cube("TangExtension", (0.026, 0.006, 0.082), (0.0, 0.0, -0.307))
    set_material(tang, blade_mat)
    tag(tang, "w0.tang_extension", "quenched_tempered_steel", 0.035, "local_mechanical_interface", True)
    validate_component(tang)

    peen = cylinder("Peen", (0.007, 0.006), 0.010, -0.347, vertices=64)
    set_material(peen, blade_mat)
    tag(peen, "w0.peen", "quenched_tempered_steel", 0.012, "local_mechanical_interface", False)
    validate_component(peen)

    components = sorted((obj for obj in scene.objects if obj.type == "MESH"), key=lambda obj: obj.name)
    stats = {obj.name: validate_component(obj) for obj in components}
    mins = [min(item["min"][axis] for item in stats.values()) for axis in range(3)]
    maxs = [max(item["max"][axis] for item in stats.values()) for axis in range(3)]
    overall = [maxs[axis] - mins[axis] for axis in range(3)]
    if not (1.50 <= overall[2] <= 1.58 and 0.27 <= overall[0] <= 0.29):
        raise RuntimeError(f"assembly dimensions: {overall}")

    scene["asset_id"] = "w0_sword_assembled_001"
    scene["axis_convention"] = "+Z blade, +X guard, +Y thickness"
    scene["units"] = "meters"
    scene["target_mass_kg"] = 2.032

    blend_path = output / "w0_sword_assembled.blend"
    fbx_path = output / "model.fbx"
    glb_path = output / "model.glb"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in components:
        obj.select_set(True)
    bpy.ops.export_scene.fbx(filepath=str(fbx_path), use_selection=True, global_scale=1.0, apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL", axis_forward="-Y", axis_up="Z", add_leaf_bones=False, bake_anim=False, path_mode="AUTO")
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", use_selection=True, export_apply=True, export_materials="EXPORT", export_cameras=False, export_lights=False, export_animations=False)

    report = {
        "schema_version": 1,
        "asset_id": "w0_sword_assembled_001",
        "source_hashes": SOURCE_HASHES,
        "dimensions_m": {"min": mins, "max": maxs, "size": overall},
        "components": stats,
        "artifacts": {"blend": file_record(blend_path), "fbx": file_record(fbx_path), "glb": file_record(glb_path)},
    }
    report_path = output / "assembly_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "report": str(report_path), "components": len(components), "dimensions_m": overall}))


if __name__ == "__main__":
    main()
