#!/usr/bin/env python3
"""Render ordered CPU-skinned OBJ calibration samples as one Blender contact sheet."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def look_at(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def bounds(object_: bpy.types.Object) -> tuple[Vector, Vector]:
    points = [object_.matrix_world @ Vector(corner) for corner in object_.bound_box]
    return (
        Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points))),
        Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points))),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    args = parser.parse_args(arguments)
    input_dir = args.input_dir.resolve()
    paths = [input_dir / "reference.obj", *sorted(input_dir.glob("frame_*.obj"))]
    if any(not path.is_file() for path in paths) or len(paths) != 6:
        missing = [str(path) for path in paths if not path.is_file()]
        raise SystemExit(f"expected reference plus five frame OBJ files; missing={missing}")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    material = bpy.data.materials.new("C0 skin QA material")
    material.diffuse_color = (0.38, 0.55, 0.82, 1.0)
    imported = []
    spacing = 2.35
    for index, path in enumerate(paths):
        # OBJ is already written as engine (X,Y,Z) → Blender (X,-Z,Y), so
        # disable the importer's default Y-up conversion.
        bpy.ops.wm.obj_import(filepath=str(path), forward_axis="Y", up_axis="Z")
        object_ = bpy.context.selected_objects[0]
        object_.name = path.stem
        object_.data.materials.append(material)
        for polygon in object_.data.polygons:
            polygon.use_smooth = True
        lo, hi = bounds(object_)
        object_.location += Vector((index * spacing - (lo.x + hi.x) * 0.5, -(lo.y + hi.y) * 0.5, -lo.z))
        imported.append(object_)

    bpy.ops.mesh.primitive_plane_add(size=30, location=(spacing * 2.5, 0.0, -0.01))
    plane = bpy.context.object
    plane_material = bpy.data.materials.new("ground")
    plane_material.diffuse_color = (0.055, 0.065, 0.08, 1.0)
    plane.data.materials.append(plane_material)

    bpy.ops.object.light_add(type="AREA", location=(spacing * 2.5, -5.0, 7.0))
    bpy.context.object.data.energy = 1400
    bpy.context.object.data.shape = "DISK"
    bpy.context.object.data.size = 6.0
    bpy.ops.object.light_add(type="AREA", location=(spacing * 2.5, 4.0, 4.0))
    bpy.context.object.data.energy = 800
    bpy.context.object.data.size = 4.0

    bpy.ops.object.camera_add(location=(spacing * 2.5, -20.0, 5.0))
    camera = bpy.context.object
    look_at(camera, Vector((spacing * 2.5, 0.0, 0.9)))
    bpy.context.scene.camera = camera
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(args.output.resolve())
    scene.world.color = (0.025, 0.03, 0.04)
    scene.render.film_transparent = False
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
