#!/usr/bin/env python3
"""Reconstruct the Meshy E0 gateway as deterministic closed components."""

from __future__ import annotations

import bmesh
import bpy
import hashlib
import json
import math
import sys
from pathlib import Path

from mathutils import Matrix

SOURCE_SHA256 = "3e6f6bd1b5aae18096031a32d9b319c02f5753a16f13c079ac533beb4f5ec888"
SOURCE_BOUNDS = (1.6839590073, 0.4004139900, 1.8995270729)
REFERENCE_TARGET_BOUNDS = (3.62, 0.66, 3.00)


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
    for collection in list(bpy.data.collections):
        if collection.name != "Collection":
            bpy.data.collections.remove(collection)


def bounds(obj: bpy.types.Object) -> tuple[list[float], list[float], list[float]]:
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    low = [float(min(point[axis] for point in points)) for axis in range(3)]
    high = [float(max(point[axis] for point in points)) for axis in range(3)]
    return low, high, [high[axis] - low[axis] for axis in range(3)]


def import_reference(path: Path) -> bpy.types.Object:
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(path))
    meshes = [obj for obj in bpy.context.scene.objects if obj not in before and obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(f"expected one Meshy reference mesh, got {len(meshes)}")
    obj = meshes[0]
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    low, high, size = bounds(obj)
    if any(abs(size[index] - SOURCE_BOUNDS[index]) > 2.0e-5 for index in range(3)):
        raise RuntimeError(f"reference bounds drift: {size}")
    center = [(low[index] + high[index]) * 0.5 for index in range(3)]
    scales = [REFERENCE_TARGET_BOUNDS[index] / size[index] for index in range(3)]
    for vertex in obj.data.vertices:
        vertex.co.x = (vertex.co.x - center[0]) * scales[0]
        vertex.co.y = (vertex.co.y - center[1]) * scales[1]
        vertex.co.z = (vertex.co.z - center[2]) * scales[2] + 1.5
    obj.name = "E0_MeshyReference_HIDDEN"
    obj.hide_render = True
    obj.hide_set(True)
    obj["source_sha256"] = SOURCE_SHA256
    return obj


def material(name: str, color: tuple[float, float, float, float], metallic: float, roughness: float) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def assign(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def tag(
    obj: bpy.types.Object,
    component_id: str,
    material_family: str,
    density: float,
    fracture: bool,
    replaceable: bool,
    collision_role: str,
) -> None:
    obj["component_id"] = component_id
    obj["material_family"] = material_family
    obj["density_kg_m3"] = density
    obj["fracture_enabled"] = fracture
    obj["replaceable"] = replaceable
    obj["collision_role"] = collision_role
    obj["source"] = "meshy_derived:E0:019f4a33-b425-7dc6-94c7-80ad8493004f"


def bevel(obj: bpy.types.Object, width: float = 0.018, segments: int = 2) -> None:
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    modifier = obj.modifiers.new(name="ManufacturedEdge", type="BEVEL")
    modifier.width = width
    modifier.segments = segments
    modifier.limit_method = "ANGLE"
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.select_set(False)


def box(name: str, dimensions: tuple[float, float, float], center: tuple[float, float, float], bevel_width: float = 0.018) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}_Mesh"
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if bevel_width > 0.0:
        bevel(obj, bevel_width)
    return obj


def tapered_base(name: str, center_x: float) -> bpy.types.Object:
    bottom_x, bottom_y = 0.72, 0.66
    top_x, top_y = 0.56, 0.54
    z0, z1 = 0.0, 0.35
    vertices = []
    for z, width, depth in ((z0, bottom_x, bottom_y), (z1, top_x, top_y)):
        vertices.extend([
            (center_x - width * 0.5, -depth * 0.5, z),
            (center_x + width * 0.5, -depth * 0.5, z),
            (center_x + width * 0.5, depth * 0.5, z),
            (center_x - width * 0.5, depth * 0.5, z),
        ])
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bevel(obj, 0.022)
    return obj


def triangular_brace(name: str, side: str) -> bpy.types.Object:
    if side == "left":
        triangle = [(-1.20, 2.47), (-0.88, 2.47), (-1.20, 2.13)]
    else:
        triangle = [(1.20, 2.47), (1.20, 2.13), (0.88, 2.47)]
    depth = 0.36
    vertices = [(x, -depth * 0.5, z) for x, z in triangle] + [(x, depth * 0.5, z) for x, z in triangle]
    faces = [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)]
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bevel(obj, 0.012)
    return obj


def socket(name: str, x: float, z: float) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.105, depth=0.16, location=(x, 0.0, z), rotation=(0.0, math.pi * 0.5, 0.0))
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}_Mesh"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bevel(obj, 0.008)
    return obj


def bolt(name: str, x: float, y: float, z: float, radius: float = 0.018) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=24,
        radius=radius,
        depth=0.024,
        location=(x, y, z),
        rotation=(math.pi * 0.5, 0.0, 0.0),
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}_Mesh"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bevel(obj, 0.003, 1)
    return obj


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


def validate(obj: bpy.types.Object) -> dict:
    stats = topology(obj)
    if stats["boundary_edges"] or stats["nonmanifold_edges"] or stats["connected_components"] != 1:
        raise RuntimeError(f"{obj.name}: {stats}")
    return stats


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) != 2:
        raise SystemExit("expected <repo-root> <output-dir>")
    root = Path(args[0]).resolve()
    output = Path(args[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = root / "assets/source/meshy/e0_arena_threshold/candidate_001/model.fbx"
    if sha256(source) != SOURCE_SHA256:
        raise RuntimeError("E0 source drift")

    clear_scene()
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    reference = import_reference(source)

    concrete = material("StructuralConcrete", (0.105, 0.115, 0.12, 1.0), 0.0, 0.82)
    steel = material("StructuralSteel", (0.11, 0.14, 0.16, 1.0), 0.88, 0.38)
    panel_steel = material("ImpactPanelSteel", (0.20, 0.23, 0.25, 1.0), 0.82, 0.46)
    socket_steel = material("SocketSteel", (0.08, 0.10, 0.12, 1.0), 0.92, 0.30)

    components: list[bpy.types.Object] = []
    for side, x in (("left", -1.45), ("right", 1.45)):
        foot = tapered_base(f"Foot_{side.title()}", x)
        assign(foot, concrete)
        tag(foot, f"e0.foot.{side}", "reinforced_concrete", 2400.0, True, False, "foundation")
        components.append(foot)

        core = box(f"PylonCore_{side.title()}", (0.55, 0.52, 2.30), (x, 0.0, 1.35), 0.026)
        assign(core, concrete)
        tag(core, f"e0.pylon.{side}", "reinforced_concrete", 2400.0, True, False, "structural")
        components.append(core)

        cap = box(f"PylonCap_{side.title()}", (0.60, 0.58, 0.60), (x, 0.0, 2.70), 0.025)
        assign(cap, concrete)
        tag(cap, f"e0.cap.{side}", "reinforced_concrete", 2400.0, True, False, "structural")
        components.append(cap)

        for face, y in (("front", -0.302), ("back", 0.302)):
            for bolt_x in (x - 0.20, x + 0.20):
                for bolt_z in (2.52, 2.88):
                    fastener = bolt(f"CapBolt_{side.title()}_{face.title()}_{bolt_x:+.2f}_{bolt_z:.2f}", bolt_x, y, bolt_z)
                    assign(fastener, socket_steel)
                    tag(fastener, f"e0.fastener.cap.{side}.{face}.{bolt_x:+.2f}.{bolt_z:.2f}", "hardened_fastener_steel", 7850.0, False, True, "visual_fastener")
                    components.append(fastener)

        for row, z in enumerate((0.72, 1.35, 1.98), start=1):
            for face, y in (("front", -0.285), ("back", 0.285)):
                panel = box(f"ImpactPanel_{side.title()}_{face.title()}_{row}", (0.38, 0.05, 0.42), (x, y, z), 0.014)
                assign(panel, panel_steel)
                tag(panel, f"e0.panel.{side}.{face}.{row}", "replaceable_impact_steel", 7850.0, True, True, "impact")
                components.append(panel)
                outer_y = -0.322 if face == "front" else 0.322
                for bolt_x in (x - 0.14, x + 0.14):
                    for bolt_z in (z - 0.15, z + 0.15):
                        fastener = bolt(f"PanelBolt_{side.title()}_{face.title()}_{row}_{bolt_x:+.2f}_{bolt_z:.2f}", bolt_x, outer_y, bolt_z)
                        assign(fastener, socket_steel)
                        tag(fastener, f"e0.fastener.panel.{side}.{face}.{row}.{bolt_x:+.2f}.{bolt_z:.2f}", "hardened_fastener_steel", 7850.0, False, True, "visual_fastener")
                        components.append(fastener)

            outer_x = -1.73 if side == "left" else 1.73
            plate = box(f"SocketPlate_{side.title()}_{row}", (0.05, 0.34, 0.26), (outer_x, 0.0, z), 0.010)
            assign(plate, steel)
            tag(plate, f"e0.socket_plate.{side}.{row}", "structural_steel", 7850.0, True, True, "attachment")
            components.append(plate)
            module = socket(f"Socket_{side.title()}_{row}", outer_x, z)
            assign(module, socket_steel)
            tag(module, f"e0.socket.{side}.{row}", "hardened_socket_steel", 7850.0, True, True, "attachment")
            components.append(module)

    beam = box("TopBeamCore", (2.50, 0.50, 0.34), (0.0, 0.0, 2.65), 0.024)
    assign(beam, concrete)
    tag(beam, "e0.beam.core", "reinforced_concrete", 2400.0, True, False, "structural")
    components.append(beam)

    for face, y in (("front", -0.275), ("back", 0.275)):
        plate = box(f"BeamPlate_{face.title()}", (2.30, 0.05, 0.24), (0.0, y, 2.65), 0.012)
        assign(plate, steel)
        tag(plate, f"e0.beam.plate.{face}", "structural_steel", 7850.0, True, True, "impact")
        components.append(plate)
        outer_y = -0.312 if face == "front" else 0.312
        for bolt_x in (-1.05, -0.90, 0.90, 1.05):
            for bolt_z in (2.59, 2.71):
                fastener = bolt(f"BeamBolt_{face.title()}_{bolt_x:+.2f}_{bolt_z:.2f}", bolt_x, outer_y, bolt_z)
                assign(fastener, socket_steel)
                tag(fastener, f"e0.fastener.beam.{face}.{bolt_x:+.2f}.{bolt_z:.2f}", "hardened_fastener_steel", 7850.0, False, True, "visual_fastener")
                components.append(fastener)

    for side in ("left", "right"):
        brace = triangular_brace(f"Brace_{side.title()}", side)
        assign(brace, steel)
        tag(brace, f"e0.brace.{side}", "structural_steel", 7850.0, True, True, "support")
        components.append(brace)

    stats = {obj.name: validate(obj) for obj in sorted(components, key=lambda item: item.name)}
    low = [min(entry["min"][axis] for entry in stats.values()) for axis in range(3)]
    high = [max(entry["max"][axis] for entry in stats.values()) for axis in range(3)]
    size = [high[axis] - low[axis] for axis in range(3)]
    if not (3.60 <= size[0] <= 3.70 and 0.64 <= size[1] <= 0.68 and 2.99 <= size[2] <= 3.01):
        raise RuntimeError(f"E0 dimensions: {size}")
    opening_width = 2.0 * (1.45 - 0.55 * 0.5)
    opening_height = 2.48
    if opening_width < 2.30 or opening_height < 2.40:
        raise RuntimeError("clearance gate")

    scene["asset_id"] = "e0_arena_threshold_assembled_001"
    scene["units"] = "meters"
    scene["opening_width_m"] = opening_width
    scene["opening_height_m"] = opening_height
    scene["source_sha256"] = SOURCE_SHA256

    blend_path = output / "e0_threshold_assembled.blend"
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
        "asset_id": "e0_arena_threshold_assembled_001",
        "source_sha256": SOURCE_SHA256,
        "dimensions_m": {"min": low, "max": high, "size": size},
        "clearance_m": {"width": opening_width, "height": opening_height},
        "component_count": len(components),
        "components": stats,
        "artifacts": {"blend": file_record(blend_path), "fbx": file_record(fbx_path), "glb": file_record(glb_path)},
    }
    report_path = output / "assembly_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "report": str(report_path), "components": len(components), "dimensions_m": size, "clearance_m": report["clearance_m"]}))


if __name__ == "__main__":
    main()
