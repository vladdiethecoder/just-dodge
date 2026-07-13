"""Transfer bounded Meshy hand/foot surface displacement onto MPFB topology.

Blender 4.3 usage:
  blender --background --python tools/transfer_mpfb_extremity_detail.py -- \
    <repo-root> <mpfb-top8.blend> <output.blend>
"""
import bpy
import json
import sys
from pathlib import Path
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

repo = Path(sys.argv[sys.argv.index("--") + 1])
source = Path(sys.argv[sys.argv.index("--") + 2])
output = Path(sys.argv[sys.argv.index("--") + 3])
bpy.ops.wm.open_mainfile(filepath=str(source))
human = bpy.data.objects["Human_clean"]


def load_target(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(path))
    obj = next(
        item
        for item in bpy.context.scene.objects
        if item not in before and item.type == "MESH"
    )
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    return obj


def target_tree(obj, kind, local_bounds):
    points = [vertex.co.copy() for vertex in obj.data.vertices]
    lower = [min(point[i] for point in points) for i in range(3)]
    upper = [max(point[i] for point in points) for i in range(3)]
    minimum, maximum = local_bounds
    vertices = []
    for point in points:
        x = minimum.x + (point.x - lower[0]) / (upper[0] - lower[0]) * (
            maximum.x - minimum.x
        )
        if kind == "hand":
            y = minimum.y + (point.y - lower[1]) / (upper[1] - lower[1]) * (
                maximum.y - minimum.y
            )
            z = minimum.z + (point.z - lower[2]) / (upper[2] - lower[2]) * (
                maximum.z - minimum.z
            )
        else:
            y = maximum.y - (point.y - lower[1]) / (upper[1] - lower[1]) * (
                maximum.y - minimum.y
            )
            z = minimum.z + (point.z - lower[2]) / (upper[2] - lower[2]) * (
                maximum.z - minimum.z
            )
        vertices.append(Vector((x, y, z)))
    faces = [tuple(face.vertices) for face in obj.data.polygons]
    return BVHTree.FromPolygons(vertices, faces, all_triangles=False)


def bounded_delta(tree, point, blend):
    nearest = tree.find_nearest(point)
    if not nearest:
        return Vector()
    delta = nearest[0] - point
    limit = 0.004 * max(0.0, min(1.0, blend))
    magnitude = delta.length
    if magnitude > limit and magnitude > 0.0:
        delta *= limit / magnitude
    return delta


def transfer_hand(side, target):
    wrist_x = 0.453 * side
    wrist_y = -0.183
    wrist_z = 1.016
    indexes = []
    local_points = []
    for vertex in human.data.vertices:
        point = vertex.co
        if (
            side * point.x > 0.39
            and point.y < wrist_y + 0.015
            and wrist_z - 0.09 < point.z < wrist_z + 0.09
        ):
            local = Vector(
                (side * (point.x - wrist_x), point.z - wrist_z, -(point.y - wrist_y))
            )
            if local.z > -0.005:
                indexes.append(vertex.index)
                local_points.append(local)
    minimum = Vector(
        (min(p.x for p in local_points), min(p.y for p in local_points), 0.0)
    )
    maximum = Vector(
        (
            max(p.x for p in local_points),
            max(p.y for p in local_points),
            max(p.z for p in local_points),
        )
    )
    tree = target_tree(target, "hand", (minimum, maximum))
    lengths = []
    for index, local in zip(indexes, local_points):
        delta = bounded_delta(tree, local, local.z / 0.025)
        vertex = human.data.vertices[index]
        vertex.co.x += side * delta.x
        vertex.co.z += delta.y
        vertex.co.y -= delta.z
        lengths.append(delta.length)
    return lengths


def transfer_foot(side, target):
    center_x = 0.18 * side
    indexes = []
    local_points = []
    for vertex in human.data.vertices:
        point = vertex.co
        if side * point.x > 0.08 and point.z < 0.13 and point.y < 0.07:
            indexes.append(vertex.index)
            local_points.append(Vector((side * (point.x - center_x), -point.y, point.z)))
    minimum = Vector(tuple(min(p[i] for p in local_points) for i in range(3)))
    maximum = Vector(tuple(max(p[i] for p in local_points) for i in range(3)))
    tree = target_tree(target, "foot", (minimum, maximum))
    lengths = []
    for index, local in zip(indexes, local_points):
        delta = bounded_delta(tree, local, (local.y - minimum.y) / 0.04)
        vertex = human.data.vertices[index]
        vertex.co.x += side * delta.x
        vertex.co.y -= delta.y
        vertex.co.z += delta.z
        lengths.append(delta.length)
    return lengths


hand_target = load_target(
    repo / "assets/source/meshy/c0_base_fighter/hand_candidate_001/model.fbx"
)
foot_target = load_target(
    repo / "assets/source/meshy/c0_base_fighter/foot_candidate_002/model.fbx"
)
measurements = {
    "hand_L": transfer_hand(1, hand_target),
    "hand_R": transfer_hand(-1, hand_target),
    "foot_L": transfer_foot(1, foot_target),
    "foot_R": transfer_foot(-1, foot_target),
}
bpy.data.objects.remove(hand_target, do_unlink=True)
bpy.data.objects.remove(foot_target, do_unlink=True)
bpy.ops.wm.save_as_mainfile(filepath=str(output))
print(
    json.dumps(
        {
            key: {
                "vertices": len(values),
                "max_m": max(values),
                "mean_m": sum(values) / len(values),
            }
            for key, values in measurements.items()
        }
    )
)
