#!/usr/bin/env python3
"""Corrected C0 human visual gate render for lateral dodge QA.

Fixes present in the root render_c0_calibration_sheet.py:
  - Per-OBJ Y-centering that strips lateral (engine Z → Blender Y) displacement.
  - Front-facing camera that compresses the diagnostic lateral axis.
  - Duplicate reference.obj + frame_0000.obj showing same source frame twice.

This script:
  - Reads reference.obj ONCE as the Y-anchor and neutral reference.
  - Skips frame_0000.obj (same source frame 0 as reference.obj).
  - Preserves internal lateral (Y) offsets anchored to the reference centroid.
  - Lays out figures along X for timeline ordering.
  - Renders one isometric/oblique orthographic sheet with all 5 figures in frame.
  - Adds per-figure labels (reference, onset f30, peak f143, recovery f280, terminal f362).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def look_at(cam: bpy.types.Object, target: Vector) -> None:
    cam.rotation_euler = ((target - cam.location).to_track_quat("-Z", "Y").to_euler())


def object_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return (
        Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))),
        Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(
        sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    )

    input_dir = args.input_dir.resolve()

    # Collect only the 5 distinct samples: reference.obj + frame_0001..frame_0004.
    # frame_0000.obj is a duplicate of reference.obj (both = source frame 0) — skip it.
    ref_path = input_dir / "reference.obj"
    frame_paths = sorted(input_dir.glob("frame_*.obj"))
    # Drop frame_0000 (duplicate source 0)
    frame_paths = [p for p in frame_paths if p.name != "frame_0000.obj"]

    if not ref_path.is_file():
        raise SystemExit(f"missing reference.obj in {input_dir}")
    if len(frame_paths) != 4:
        raise SystemExit(f"expected 4 motion frame OBJs (0001..0004), got {len(frame_paths)}: {[p.name for p in frame_paths]}")

    source_labels = ["reference f0", "onset f30", "peak f143", "recovery f280", "terminal f362"]
    paths = [ref_path] + frame_paths

    # --- Setup scene ---
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    material = bpy.data.materials.new("C0 gate mat")
    material.diffuse_color = (0.38, 0.55, 0.82, 1.0)

    imported: list[bpy.types.Object] = []
    spacing = 2.8
    anchor_y: float | None = None
    anchor_z: float | None = None
    fig_bboxes: list[tuple[Vector, Vector]] = []

    for index, path in enumerate(paths):
        bpy.ops.wm.obj_import(filepath=str(path), forward_axis="Y", up_axis="Z")
        obj = bpy.context.selected_objects[0]
        obj.name = source_labels[index]
        obj.data.materials.append(material)
        for poly in obj.data.polygons:
            poly.use_smooth = True

        lo, hi = object_bounds(obj)

        if index == 0:  # reference — establish anchors
            anchor_y = (lo.y + hi.y) * 0.5
            anchor_z = lo.z

        # Layout along X, preserve internal Y (lateral) offset anchored to reference centroid
        obj.location += Vector((
            index * spacing - (lo.x + hi.x) * 0.5,
            -(anchor_y or 0.0),
            -(anchor_z or 0.0),
        ))
        imported.append(obj)
        # Re-fetch bounds after placement
        lo2, hi2 = object_bounds(obj)
        fig_bboxes.append((lo2, hi2))

    # --- Ground plane ---
    scene_center_x = (len(paths) - 1) * spacing / 2.0
    scene_center_y = anchor_y or 0.0
    bpy.ops.mesh.primitive_plane_add(size=40, location=(scene_center_x, scene_center_y, -0.01))
    plane = bpy.context.object
    pm = bpy.data.materials.new("ground")
    pm.diffuse_color = (0.055, 0.065, 0.08, 1.0)
    plane.data.materials.append(pm)

    # --- Lights ---
    bpy.ops.object.light_add(type="AREA", location=(scene_center_x, scene_center_y - 6.0, 8.0))
    bpy.context.object.data.energy = 1600
    bpy.context.object.data.shape = "DISK"
    bpy.context.object.data.size = 7.0
    bpy.ops.object.light_add(type="AREA", location=(scene_center_x, scene_center_y + 5.0, 5.0))
    bpy.context.object.data.energy = 900
    bpy.context.object.data.size = 5.0

    # --- Compute full scene AABB from all figure+label bboxes ---
    all_lo = Vector((min(b[0].x for b in fig_bboxes), min(b[0].y for b in fig_bboxes), min(b[0].z for b in fig_bboxes)))
    all_hi = Vector((max(b[1].x for b in fig_bboxes), max(b[1].y for b in fig_bboxes), max(b[1].z for b in fig_bboxes)))
    aabb_center = (all_lo + all_hi) * 0.5
    aabb_size = all_hi - all_lo

    # --- ISO camera — orthographic, auto-fit from AABB ---
    # Safe multiplier avoids crop from oblique projection of depth (Z)
    iso_dist = max(aabb_size.x, aabb_size.y, aabb_size.z) * 2.0 + 4.0
    iso_loc = aabb_center + Vector((iso_dist * 0.65, -iso_dist * 0.50, iso_dist * 0.35))
    bpy.ops.object.camera_add(location=iso_loc)
    camera = bpy.context.object
    camera.name = "CAM_ISO"
    look_at(camera, aabb_center)
    camera.data.type = "ORTHO"
    # Use AABB diagonal to guarantee no ISO crop regardless of projection angle
    aabb_diag = (aabb_size.x**2 + aabb_size.y**2 + aabb_size.z**2) ** 0.5
    camera.data.ortho_scale = aabb_diag * 1.20
    bpy.context.scene.camera = camera

    # --- Labels ---
    text_mat = bpy.data.materials.new("label_mat")
    text_mat.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    for idx, obj in enumerate(imported):
        bpy.ops.object.text_add()
        text_obj = bpy.context.object
        text_obj.name = f"LABEL_{idx}"
        text_obj.data.body = source_labels[idx]
        text_obj.data.size = 0.18
        text_obj.data.align_x = "CENTER"
        text_obj.data.materials.append(text_mat)
        lo, hi = fig_bboxes[idx]
        pos_x = (lo.x + hi.x) * 0.5
        pos_y = (lo.y + hi.y) * 0.5
        text_obj.location = Vector((pos_x, pos_y, hi.z + 0.35))
        text_obj.rotation_euler = camera.rotation_euler

    # --- Render ---
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
