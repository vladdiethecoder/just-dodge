#!/usr/bin/env python3
"""Ad-hoc Mesh Doctor before/after evidence renderer.

Renders the C0 armored duelist source GLB and the same-region repair candidate
side-by-side (front + three-quarter views) so the repair's effect is visually
inspectable. Pure bpy; deterministic camera/light; no labels baked over mesh.
Output: 2 PNGs (front, three-quarter), each showing SOURCE | REPAIRED.

Honest-evidence notes:
  - Renders the ACTUAL candidate GLB produced by mesh_doctor_sameregion_repair
    (qa_runs/p4_mesh_doctor/c0_sr20_candidate.glb), not a mock.
  - Does NOT claim penetration resolution; the receipt already states partial
    convergence (447->411 same-region). This is a visual aid, not a pass gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "assets/source/meshy/c0_armored_duelist_001/model.glb"
CANDIDATE = ROOT / "qa_runs/p4_mesh_doctor/c0_sr20_candidate.glb"
OUT_DIR = ROOT / "qa_runs/p4_mesh_doctor/visual_evidence"


def look_at(cam: bpy.types.Object, target: Vector) -> None:
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()


def clean_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_glb(path: Path, x_offset: float) -> list:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new_objs = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new_objs if o.type == "MESH"]
    # shift the whole imported hierarchy
    roots = [o for o in new_objs if o.parent is None]
    for r in roots:
        r.location.x += x_offset
    return meshes


def bounds(meshes):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in meshes:
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    return lo, hi


def render_view(
    name: str,
    cam_loc: Vector,
    target: Vector,
    lo: Vector,
    hi: Vector,
    res: int = 900,
    margin: float = 1.08,
) -> None:
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cam_data)
    scene.collection.objects.link(cam)
    cam.location = cam_loc
    look_at(cam, target)
    cam_data.type = "ORTHO"
    scene.camera = cam

    # Fit the ortho frustum to the ACTUAL combined bounds in camera space.
    # Fixed ortho scales cropped full bodies before (2:1 render: vertical span
    # is ortho_scale/aspect). Compute extents of all 8 bound corners after
    # transforming into the camera's local frame (-Z forward, Y up).
    bpy.context.view_layer.update()
    cam_inv = cam.matrix_world.inverted()
    corners = [
        Vector((x, y, z))
        for x in (lo.x, hi.x)
        for y in (lo.y, hi.y)
        for z in (lo.z, hi.z)
    ]
    local = [cam_inv @ c for c in corners]
    cx = (min(v.x for v in local) + max(v.x for v in local)) / 2
    cy = (min(v.y for v in local) + max(v.y for v in local)) / 2
    half_w = max(abs(v.x - cx) for v in local)
    half_h = max(abs(v.y - cy) for v in local)
    # Recenter the camera on the bound center within the view plane so both
    # figures are symmetric in frame.
    cam.location = cam.location + (cam.matrix_world.to_quaternion() @ Vector((cx, cy, 0.0)))
    aspect = (res * 2) / res  # resolution_x : resolution_y
    cam_data.ortho_scale = max(2 * half_w, 2 * half_h * aspect) * margin
    print(
        f"[frame-fit] {name}: half_w={half_w:.3f} half_h={half_h:.3f} "
        f"ortho_scale={cam_data.ortho_scale:.3f}"
    )

    # key light
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.rotation_euler = (0.9, 0.2, 0.6)
    sun.data.energy = 3.0
    scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.05, 0.05, 0.07, 1.0)
    bg.inputs[1].default_value = 0.6
    scene.world = world

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = res * 2
    scene.render.resolution_y = res
    scene.render.filepath = str(OUT_DIR / f"meshdoctor_beforeafter_{name}.png")
    bpy.ops.render.render(write_still=True)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    clean_scene()

    src_meshes = import_glb(SOURCE, x_offset=-1.1)
    rep_meshes = import_glb(CANDIDATE, x_offset=+1.1)
    all_m = src_meshes + rep_meshes
    lo, hi = bounds(all_m)
    center = (lo + hi) / 2

    # front view (camera on -Y, looking +Y at center)
    render_view("front", Vector((center.x, lo.y - 6.0, center.z)), center, lo, hi)
    # three-quarter
    render_view(
        "threequarter",
        Vector((center.x + 3.2, lo.y - 4.5, center.z + 2.2)),
        center,
        lo,
        hi,
    )
    print(f"wrote evidence to {OUT_DIR}")


if __name__ == "__main__":
    main()
