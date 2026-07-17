#!/usr/bin/env python3
"""Re-pose Grab-07's two debug mannequins and run real triangle pair detection.

The runtime capture owns the pose.  This worker consumes its deterministic
``worst_substep_pose.json`` rather than reimplementing animation/retargeting in
Blender: each source vertex is CPU-skinned with the exported row-major
``world_skin_matrices`` and then passed through the same BVH/narrow-phase logic
as ``mesh_doctor_pair_detect.py``.

The pair is deliberately Player hand triangles (dominant LeftHand/RightHand
weights) against the complete Opponent body.  This makes the result an actual
hand-to-body triangle test rather than a whole-character OBB proxy result.

Run headless from the repository root:
  blender -b --factory-startup -noaudio --python tools/blender/grab07_pose_and_detect.py -- \
    --pose qa_runs/grab07_meshdoctor_pose/worst_substep_pose.json \
    --source-skin assets/source/meshy/c0_base_fighter/rigged_001/cooked/c0_skin8.bin \
    --cameras qa_runs/grab07_meshdoctor_pose/cameras.json \
    --out-dir qa_runs/grab07_meshdoctor_pose/posed_mesh_doctor

The optional repair is a snapshot-only, non-destructive candidate.  It never
modifies the cooked SKM1, runtime data, or capture artifacts, and is marked
``promoted: false`` even when its local efficacy probe improves the finding.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
HAND_BONE_NAMES = {"LeftHand", "RightHand"}
EPS = 1.0e-9
RENDER_WIDTH = 1280
RENDER_HEIGHT = 720


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def matrix_from_row_major(values: list[float]) -> Matrix:
    if not isinstance(values, list) or len(values) != 16:
        raise ValueError("expected 16 row-major matrix values")
    return Matrix(tuple(tuple(float(values[row * 4 + col]) for col in range(4)) for row in range(4)))


def parse_skm1(path: Path) -> dict:
    """Read the runtime's cooked SKM1 format, including its exact top-8 weights."""
    data = path.read_bytes()
    if data[:4] != b"SKM1":
        raise ValueError(f"{path}: expected SKM1")
    offset = 4
    vertex_count, index_count, bone_count = struct.unpack_from("<III", data, offset)
    offset += 12
    positions: list[tuple[float, float, float]] = []
    for _ in range(vertex_count):
        positions.append(struct.unpack_from("<3f", data, offset))
        offset += 32  # position[3], normal[3], uv[2]
    indices = list(struct.unpack_from(f"<{index_count}I", data, offset))
    offset += index_count * 4
    bones = []
    for _ in range(bone_count):
        (name_size,) = struct.unpack_from("<H", data, offset)
        offset += 2
        name = data[offset:offset + name_size].decode("utf-8")
        offset += name_size
        (parent_index,) = struct.unpack_from("<i", data, offset)
        offset += 4
        rest_local = list(struct.unpack_from("<16f", data, offset))
        offset += 64
        inverse_bind = list(struct.unpack_from("<16f", data, offset))
        offset += 64
        bones.append({"name": name, "parent_index": parent_index, "rest_local": rest_local, "inverse_bind": inverse_bind})
    influences: list[list[tuple[int, float]]] = []
    for _ in range(vertex_count):
        (count,) = struct.unpack_from("<B", data, offset)
        offset += 1
        vertex_influences = []
        for _ in range(count):
            joint_index, weight = struct.unpack_from("<If", data, offset)
            offset += 8
            if weight > 0.0:
                vertex_influences.append((joint_index, weight))
        influences.append(vertex_influences)
    if offset != len(data):
        raise ValueError(f"{path}: trailing SKM1 bytes={len(data) - offset}")
    if index_count % 3:
        raise ValueError(f"{path}: non-triangle index count={index_count}")
    return {
        "positions": positions,
        "indices": indices,
        "triangles": [tuple(indices[index:index + 3]) for index in range(0, index_count, 3)],
        "bones": bones,
        "influences": influences,
    }


def validate_pose(pose: dict, skin: dict, skin_sha256: str) -> tuple[dict, dict]:
    if pose.get("schema") != "grab07-worst-substep-pose-v1":
        raise ValueError("unsupported pose schema")
    if pose.get("matrix_layout") != "row_major":
        raise ValueError("only explicit row-major pose matrices are accepted")
    fighters = pose.get("fighters")
    if not isinstance(fighters, list) or len(fighters) != 2:
        raise ValueError("pose must contain exactly player and opponent")
    by_role = {fighter.get("role"): fighter for fighter in fighters}
    if set(by_role) != {"player", "opponent"}:
        raise ValueError("pose fighters must be player and opponent")
    if pose.get("source_skin_sha256") != skin_sha256:
        raise ValueError("source SKM1 hash does not match captured pose provenance")
    for role, fighter in by_role.items():
        matrices = fighter.get("world_skin_matrices_row_major")
        if not isinstance(matrices, list) or len(matrices) != len(skin["bones"]):
            raise ValueError(f"{role}: expected {len(skin['bones'])} world skin matrices")
        captured_bones = fighter.get("bones")
        if not isinstance(captured_bones, list) or len(captured_bones) != len(skin["bones"]):
            raise ValueError(f"{role}: missing captured inverse-bind/rest hierarchy")
        for index, (captured, cooked) in enumerate(zip(captured_bones, skin["bones"])):
            if captured.get("index") != index or captured.get("name") != cooked["name"]:
                raise ValueError(f"{role}: bone hierarchy drift at index={index}")
    return by_role["player"], by_role["opponent"]


def pose_vertices(source: dict, fighter: dict) -> list[Vector]:
    matrices = [matrix_from_row_major(values) for values in fighter["world_skin_matrices_row_major"]]
    result: list[Vector] = []
    for position, influences in zip(source["positions"], source["influences"]):
        if not influences:
            raise ValueError("SKM1 vertex lacks skin influences")
        point = Vector((position[0], position[1], position[2], 1.0))
        skinned = Vector((0.0, 0.0, 0.0, 0.0))
        for joint_index, weight in influences:
            if joint_index >= len(matrices):
                raise ValueError(f"joint index {joint_index} exceeds captured skin matrices")
            skinned += (matrices[joint_index] @ point) * weight
        if abs(skinned.w) <= EPS:
            result.append(Vector((skinned.x, skinned.y, skinned.z)))
        else:
            result.append(Vector((skinned.x / skinned.w, skinned.y / skinned.w, skinned.z / skinned.w)))
    return result


def dominant_bone_by_vertex(source: dict) -> list[int]:
    return [max(influences, key=lambda item: (item[1], -item[0]))[0] for influences in source["influences"]]


def hand_triangle_indices(source: dict) -> list[int]:
    bone_names = [bone["name"] for bone in source["bones"]]
    dominant = dominant_bone_by_vertex(source)
    selected = []
    for triangle_index, triangle in enumerate(source["triangles"]):
        names = {bone_names[dominant[vertex_index]] for vertex_index in triangle}
        if names & HAND_BONE_NAMES:
            selected.append(triangle_index)
    if not selected:
        raise ValueError("no dominant LeftHand/RightHand source triangles found")
    return selected


def pair_detector_module():
    path = Path(__file__).with_name("mesh_doctor_pair_detect.py")
    spec = importlib.util.spec_from_file_location("grab07_mesh_doctor_pair", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load pair detector {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_pair_detect(pair_module, player_vertices: list[Vector], opponent_vertices: list[Vector], source: dict, player_hand_ids: list[int], min_depth_m: float) -> list[dict]:
    hand_triangles = [source["triangles"][index] for index in player_hand_ids]
    crossings = pair_module.pair_crossings(player_vertices, hand_triangles, opponent_vertices, source["triangles"], min_depth_m)
    findings = []
    for crossing in crossings:
        depth = float(crossing["depth"])
        findings.append({
            "triangle_ids": [player_hand_ids[int(crossing["tri_a"])], int(crossing["tri_b"])],
            "barycentric": [round(float(value), 9) for value in crossing["bary"]],
            "world_point": [round(float(crossing["point"].x), 9), round(float(crossing["point"].y), 9), round(float(crossing["point"].z), 9)],
            "normal": [round(float(crossing["normal"].x), 9), round(float(crossing["normal"].y), 9), round(float(crossing["normal"].z), 9)],
            "signed_depth_m": round(-depth, 9),
        })
    findings.sort(key=lambda finding: (finding["signed_depth_m"], finding["triangle_ids"][0], finding["triangle_ids"][1], finding["world_point"]))
    return findings


def metrics(findings: list[dict]) -> dict:
    magnitudes = [abs(float(finding["signed_depth_m"])) for finding in findings]
    maximum = max(magnitudes, default=0.0)
    rms = math.sqrt(sum(value * value for value in magnitudes) / len(magnitudes)) if magnitudes else 0.0
    return {
        "findings_count": len(findings),
        "max_penetration_mm": round(maximum * 1000.0, 6),
        "rms_penetration_mm": round(rms * 1000.0, 6),
        "max_signed_penetration_mm": round(-maximum * 1000.0, 6) if magnitudes else 0.0,
        "rms_signed_penetration_mm": round(-rms * 1000.0, 6) if magnitudes else 0.0,
    }


def visible_surface_clearance_m(player_vertices: list[Vector], player_hand_ids: list[int], opponent_vertices: list[Vector], triangles: list[tuple[int, int, int]]) -> float:
    """Minimum hand-vertex to opponent-body-surface distance (m). This is the
    visible surface clearance: positive when the hand does not touch the body.
    Uses a BVH nearest-point query per hand vertex against the opponent mesh.
    """
    from mathutils.bvhtree import BVHTree

    bvh = BVHTree.FromPolygons([tuple(v) for v in opponent_vertices], [tuple(t) for t in triangles])
    hand_vertex_ids = sorted({index for tri in player_hand_ids for index in triangles[tri]})
    best = math.inf
    for vertex_index in hand_vertex_ids:
        _location, _normal, _face_index, distance = bvh.find_nearest(player_vertices[vertex_index])
        if distance is not None and distance < best:
            best = distance
    return 0.0 if best is math.inf else round(best, 9)


def make_mesh(name: str, vertices: list[Vector], triangles: list[tuple[int, int, int]], color: tuple[float, float, float, float]) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata([tuple(vertex) for vertex in vertices], [], triangles)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    material = bpy.data.materials.new(name + "Material")
    material.diffuse_color = color
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = color
    material.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.68
    obj.data.materials.append(material)
    return obj


def game_to_blender() -> Matrix:
    # Runtime/game is X-right, Y-up, Z-forward; Blender is X-right, Z-up, -Y-forward.
    return Matrix.Rotation(math.pi / 2.0, 4, "X")


def transform_object_for_render(obj: bpy.types.Object) -> None:
    obj.matrix_world = game_to_blender()


def marker(name: str, game_position: list[float]) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.024, location=game_to_blender() @ Vector(game_position))
    obj = bpy.context.object
    obj.name = name
    material = bpy.data.materials.new(name + "Material")
    material.diffuse_color = (1.0, 0.03, 0.02, 1.0)
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1.0, 0.03, 0.02, 1.0)
    material.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1.0, 0.0, 0.0, 1.0)
    material.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 2.0
    obj.data.materials.append(material)
    return obj


def setup_render() -> None:
    scene = bpy.context.scene
    # Blender 5 exposes the Eevee Next renderer under its stable enum name.
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = RENDER_WIDTH
    scene.render.resolution_y = RENDER_HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"
    scene.world = bpy.data.worlds.new("Grab07World")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.018, 0.025, 0.045, 1.0)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.35
    light_data = bpy.data.lights.new("Grab07Key", "AREA")
    light_data.energy = 950.0
    light_data.shape = "DISK"
    light_data.size = 4.0
    light = bpy.data.objects.new("Grab07Key", light_data)
    light.location = Vector((2.5, -3.0, 5.0))
    bpy.context.scene.collection.objects.link(light)
    light.rotation_euler = (0.45, 0.0, 0.7)


def render_views(cameras: list[dict], image_dir: Path, suffix: str) -> list[str]:
    image_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    rendered = []
    for camera_spec in cameras:
        camera_data = bpy.data.cameras.new("Grab07Camera_" + camera_spec["name"])
        camera = bpy.data.objects.new("Grab07Camera_" + camera_spec["name"], camera_data)
        bpy.context.scene.collection.objects.link(camera)
        eye = game_to_blender() @ Vector(camera_spec["eye_m"])
        target = game_to_blender() @ Vector(camera_spec["target_m"])
        up = game_to_blender().to_3x3() @ Vector(camera_spec["up"])
        camera.location = eye
        # Build the camera basis directly so the registered top-view up vector
        # is respected too; bpy's to_track_quat accepts only axis names.
        forward = (target - eye).normalized()
        right = forward.cross(up).normalized()
        corrected_up = right.cross(forward).normalized()
        camera.matrix_world = Matrix((
            (right.x, corrected_up.x, -forward.x, eye.x),
            (right.y, corrected_up.y, -forward.y, eye.y),
            (right.z, corrected_up.z, -forward.z, eye.z),
            (0.0, 0.0, 0.0, 1.0),
        ))
        camera_data.type = "PERSP"
        camera_data.sensor_fit = "VERTICAL"
        camera_data.angle_y = math.radians(float(camera_spec["fov_deg"]))
        scene.camera = camera
        path = image_dir / f"{camera_spec['name']}_{suffix}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        rendered.append(str(path))
        bpy.data.objects.remove(camera, do_unlink=True)
    return rendered


def render_ab_diff(before_path: Path, after_path: Path, out_path: Path) -> None:
    before = bpy.data.images.load(str(before_path), check_existing=False)
    after = bpy.data.images.load(str(after_path), check_existing=False)
    if before.size[:] != after.size[:]:
        raise ValueError("before/after resolution mismatch")
    result = bpy.data.images.new("Grab07ABDiff", width=before.size[0], height=before.size[1], alpha=False)
    before_pixels = list(before.pixels[:])
    after_pixels = list(after.pixels[:])
    pixels = []
    for index in range(0, len(before_pixels), 4):
        pixels.extend((abs(before_pixels[index] - after_pixels[index]), abs(before_pixels[index + 1] - after_pixels[index + 1]), abs(before_pixels[index + 2] - after_pixels[index + 2]), 1.0))
    result.pixels.foreach_set(pixels)
    result.filepath_raw = str(out_path)
    result.file_format = "PNG"
    result.save()
    bpy.data.images.remove(before, do_unlink=True)
    bpy.data.images.remove(after, do_unlink=True)
    bpy.data.images.remove(result, do_unlink=True)


def candidate_vertices(player_vertices: list[Vector], opponent_vertices: list[Vector], source: dict, findings: list[dict]) -> tuple[list[Vector], list[int]]:
    """Produce a deliberately local snapshot-only hand push for an efficacy probe."""
    accumulated: dict[int, Vector] = {}
    maximum_push: dict[int, float] = {}
    for finding in findings:
        player_triangle = source["triangles"][finding["triangle_ids"][0]]
        opponent_triangle = source["triangles"][finding["triangle_ids"][1]]
        player_center = sum((player_vertices[index] for index in player_triangle), Vector()) / 3.0
        opponent_center = sum((opponent_vertices[index] for index in opponent_triangle), Vector()) / 3.0
        direction = player_center - opponent_center
        if direction.length <= EPS:
            direction = Vector(finding["normal"])
        if direction.length <= EPS:
            continue
        direction.normalize()
        push = abs(float(finding["signed_depth_m"])) + 0.0005
        for vertex_index in player_triangle:
            accumulated[vertex_index] = accumulated.get(vertex_index, Vector()) + direction * push
            maximum_push[vertex_index] = max(maximum_push.get(vertex_index, 0.0), push)
    candidate = list(player_vertices)
    for vertex_index, delta in accumulated.items():
        direction = delta.normalized() if delta.length > EPS else Vector()
        candidate[vertex_index] = candidate[vertex_index] + direction * maximum_push[vertex_index]
    return candidate, sorted(accumulated)


def export_preview(candidate: bpy.types.Object, opponent: bpy.types.Object, path: Path) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    candidate.select_set(True)
    opponent.select_set(True)
    bpy.context.view_layer.objects.active = candidate
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_apply=True, export_animations=False)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pose", required=True, type=Path)
    parser.add_argument("--source-skin", type=Path, default=ROOT / "assets/source/meshy/c0_base_fighter/rigged_001/cooked/c0_skin8.bin")
    parser.add_argument("--cameras", type=Path, default=None)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--min-depth-m", type=float, default=0.0001)
    args = parser.parse_args(argv)

    pose = json.loads(args.pose.read_text(encoding="utf-8"))
    source_sha256 = sha256_file(args.source_skin)
    source = parse_skm1(args.source_skin)
    player_pose, opponent_pose = validate_pose(pose, source, source_sha256)
    cameras_path = args.cameras or (args.pose.parent / "cameras.json")
    camera_document = json.loads(cameras_path.read_text(encoding="utf-8"))
    cameras = camera_document.get("cameras", camera_document)
    if not isinstance(cameras, list) or not cameras:
        raise ValueError("camera document has no registered cameras")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.report or (args.out_dir / "findings_pose.json")
    image_dir = args.out_dir / "images"

    player_vertices = pose_vertices(source, player_pose)
    opponent_vertices = pose_vertices(source, opponent_pose)
    player_hand_ids = hand_triangle_indices(source)
    pair_module = pair_detector_module()
    findings = run_pair_detect(pair_module, player_vertices, opponent_vertices, source, player_hand_ids, args.min_depth_m)
    before_metrics = metrics(findings)
    clearance_m = visible_surface_clearance_m(player_vertices, player_hand_ids, opponent_vertices, source["triangles"])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    player_object = make_mesh("PlayerMannequin", player_vertices, source["triangles"], (0.23, 0.52, 0.92, 1.0))
    opponent_object = make_mesh("OpponentMannequin", opponent_vertices, source["triangles"], (0.94, 0.39, 0.20, 1.0))
    transform_object_for_render(player_object)
    transform_object_for_render(opponent_object)
    setup_render()
    before_views = render_views(cameras, image_dir, "BEFORE")

    markers = [marker(f"Detected_{index:03d}", finding["world_point"]) for index, finding in enumerate(findings[:20])]
    detected_views = render_views(cameras, image_dir, "DETECTED")
    for item in markers:
        bpy.data.objects.remove(item, do_unlink=True)

    repair_preview: dict = {
        "status": "not_attempted" if not findings else "rejected",
        "tractable": False,
        "promoted": False,
        "runtime_admitted": False,
        "candidate_glb": None,
        "receipt": None,
        "after_metrics": None,
        "after_views": [],
        "ab_diff_views": [],
        "reason": "no triangle-level hand-to-body penetration at the captured worst OBB substep" if not findings else "candidate efficacy pending",
    }
    if findings:
        candidate, moved_vertex_ids = candidate_vertices(player_vertices, opponent_vertices, source, findings)
        candidate_findings = run_pair_detect(pair_module, candidate, opponent_vertices, source, player_hand_ids, args.min_depth_m)
        after_metrics = metrics(candidate_findings)
        # A preview is tractable only when it monotonically improves the same real metric.
        before_key = (before_metrics["findings_count"], before_metrics["max_penetration_mm"])
        after_key = (after_metrics["findings_count"], after_metrics["max_penetration_mm"])
        tractable = after_key < before_key
        repair_preview["after_metrics"] = after_metrics
        repair_preview["moved_vertex_ids"] = moved_vertex_ids
        repair_preview["max_displacement_mm"] = round(max((candidate[index] - player_vertices[index]).length for index in moved_vertex_ids) * 1000.0, 6) if moved_vertex_ids else 0.0
        if tractable:
            candidate_object = make_mesh("PlayerMannequin_RepairPreview", candidate, source["triangles"], (0.20, 0.90, 0.38, 1.0))
            transform_object_for_render(candidate_object)
            player_object.hide_render = True
            player_object.hide_viewport = True
            for index, finding in enumerate(candidate_findings[:20]):
                markers.append(marker(f"AfterDetected_{index:03d}", finding["world_point"]))
            after_views = render_views(cameras, image_dir, "AFTER_REPAIR_PREVIEW")
            for item in markers:
                if item.name in bpy.data.objects:
                    bpy.data.objects.remove(item, do_unlink=True)
            diff_views = []
            for camera in cameras:
                name = camera["name"]
                diff_path = image_dir / f"{name}_AB_DIFF_REPAIR_PREVIEW.png"
                render_ab_diff(image_dir / f"{name}_BEFORE.png", image_dir / f"{name}_AFTER_REPAIR_PREVIEW.png", diff_path)
                diff_views.append(str(diff_path))
            candidate_path = args.out_dir / "repair_preview_candidate.glb"
            export_preview(candidate_object, opponent_object, candidate_path)
            receipt_path = args.out_dir / "repair_preview_receipt.json"
            receipt = {
                "schema": "grab07-repair-preview-v1",
                "runtime_admitted": False,
                "promoted": False,
                "non_destructive": True,
                "source_skin_sha256": source_sha256,
                "pose_sha256": sha256_file(args.pose),
                "candidate_glb": str(candidate_path),
                "candidate_sha256": sha256_file(candidate_path),
                "moved_vertex_ids": moved_vertex_ids,
                "before": before_metrics,
                "after": after_metrics,
                "note": "posed snapshot-only local hand correction; preview only, never auto-applied to cooked source or runtime",
            }
            receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            repair_preview.update({
                "status": "candidate_emitted",
                "tractable": True,
                "candidate_glb": str(candidate_path),
                "receipt": str(receipt_path),
                "after_views": after_views,
                "ab_diff_views": diff_views,
                "reason": "local snapshot candidate monotonically reduced the same hand-to-body pair metric",
            })
        else:
            repair_preview["reason"] = "local hand-only snapshot push did not monotonically improve the complete triangle-pair metric; no candidate emitted"

    report = {
        "schema": "grab07-posed-pair-detect-v1",
        "runtime_admitted": False,
        "promoted": False,
        "physics_tick": pose["physics_tick"],
        "render_frame": pose["render_frame"],
        "pose_path": str(args.pose),
        "pose_sha256": sha256_file(args.pose),
        "source_skin": str(args.source_skin),
        "source_skin_sha256": source_sha256,
        "matrix_layout": pose["matrix_layout"],
        "object_pair": ["PlayerMannequin.hand", "OpponentMannequin.body"],
        "triangle_id_space": "SKM1 index-order triangle id (indices[3*i:3*i+3])",
        "hand_bones": sorted(HAND_BONE_NAMES),
        "source_triangles": len(source["triangles"]),
        "player_hand_triangles": len(player_hand_ids),
        "min_depth_m": args.min_depth_m,
        "metrics": before_metrics,
        "visible_surface_clearance_m": clearance_m,
        "offending_triangle_pair": findings[0]["triangle_ids"] if findings else None,
        "findings_sha256": canonical_sha256(findings),
        "findings": findings[:200],
        "views": {"before": before_views, "detected": detected_views},
        "repair_preview": repair_preview,
        "verdict": "triangle-level penetration found; debug mesh repair remains preview-only" if findings else "OBB proxy overlap was not corroborated by hand-to-body triangle penetration at this posed substep; a coarse debug mannequin cannot establish the <=0.5 mm repair gate for a production asset",
    }
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(
        "GRAB07_POSE_DETECT=PASS "
        f"tick={pose['physics_tick']} findings={before_metrics['findings_count']} "
        f"max_mm={before_metrics['max_penetration_mm']:.6f} "
        f"rms_mm={before_metrics['rms_penetration_mm']:.6f} report={report_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
