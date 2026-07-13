"""Create a direction-only C0 reference action without changing MPFB bind data."""
import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Matrix, Vector

repo = Path(sys.argv[sys.argv.index("--") + 1])
source = Path(sys.argv[sys.argv.index("--") + 2])
output = Path(sys.argv[sys.argv.index("--") + 3])
bpy.ops.wm.open_mainfile(filepath=str(source))
human = bpy.data.objects["Human_clean"]
rig = bpy.data.objects["Human.rig_clean"]
before = set(bpy.context.scene.objects)
bpy.ops.import_scene.fbx(
    filepath=str(repo / "assets/source/meshy/c0_base_fighter/rigged_001/model.fbx")
)
target = next(
    obj
    for obj in bpy.context.scene.objects
    if obj not in before and obj.type == "ARMATURE"
)
target_bones = {
    bone.name: (
        target.matrix_world @ bone.head_local,
        target.matrix_world @ bone.tail_local,
    )
    for bone in target.data.bones
}


def direction(start, end):
    return (end - start).normalized()


def target_direction(name):
    return direction(*target_bones[name])


directions = {}
for side in ["L", "R"]:
    target_side = "Left" if side == "L" else "Right"
    shoulder = direction(
        target_bones[target_side + "Shoulder"][0],
        target_bones[target_side + "Arm"][0],
    )
    arm = direction(
        target_bones[target_side + "Arm"][0],
        target_bones[target_side + "ForeArm"][0],
    )
    forearm = direction(
        target_bones[target_side + "ForeArm"][0],
        target_bones[target_side + "Hand"][0],
    )
    leg = direction(
        target_bones[target_side + "UpLeg"][0],
        target_bones[target_side + "Leg"][0],
    )
    shin = direction(
        target_bones[target_side + "Leg"][0],
        target_bones[target_side + "Foot"][0],
    )
    for name in [f"clavicle.{side}", f"shoulder01.{side}"]:
        directions[name] = shoulder
    for name in [f"upperarm01.{side}", f"upperarm02.{side}"]:
        directions[name] = arm
    for name in [f"lowerarm01.{side}", f"lowerarm02.{side}"]:
        directions[name] = forearm
    directions[f"wrist.{side}"] = target_direction(target_side + "Hand")
    for name in [f"upperleg01.{side}", f"upperleg02.{side}"]:
        directions[name] = leg
    for name in [f"lowerleg01.{side}", f"lowerleg02.{side}"]:
        directions[name] = shin
    directions[f"foot.{side}"] = direction(
        target_bones[target_side + "Foot"][0],
        target_bones[target_side + "ToeBase"][0],
    )
for name in ["spine05", "spine04", "spine03", "spine02", "spine01"]:
    directions[name] = Vector((0, 0, 1))
for name in ["neck01", "neck02", "neck03", "head"]:
    directions[name] = Vector((0, 0, 1))


def depth(pose_bone):
    result = 0
    parent = pose_bone.parent
    while parent:
        result += 1
        parent = parent.parent
    return result


for pose_bone in sorted(
    [rig.pose.bones[name] for name in directions], key=depth
):
    bpy.context.view_layer.update()
    head = pose_bone.head.copy()
    current = (pose_bone.tail - pose_bone.head).normalized()
    rotation = current.rotation_difference(directions[pose_bone.name])
    pose_bone.matrix = (
        Matrix.Translation(head)
        @ rotation.to_matrix().to_4x4()
        @ Matrix.Translation(-head)
        @ pose_bone.matrix
    )
bpy.context.view_layer.update()
rig.animation_data_create()
action = bpy.data.actions.new("C0_REFERENCE_POSE")
rig.animation_data.action = action
for pose_bone in rig.pose.bones:
    pose_bone.rotation_mode = "QUATERNION"
    pose_bone.keyframe_insert("location", frame=1)
    pose_bone.keyframe_insert("rotation_quaternion", frame=1)
    pose_bone.keyframe_insert("scale", frame=1)
for obj in list(bpy.context.scene.objects):
    if obj not in before:
        bpy.data.objects.remove(obj, do_unlink=True)
bpy.context.scene.frame_set(1)
bpy.context.view_layer.update()
evaluated = human.evaluated_get(bpy.context.evaluated_depsgraph_get())
points = [evaluated.matrix_world @ vertex.co for vertex in evaluated.data.vertices]
height = max(point.z for point in points) - min(point.z for point in points)
errors = {
    name: math.degrees(
        (rig.pose.bones[name].tail - rig.pose.bones[name].head)
        .normalized()
        .angle(expected)
    )
    for name, expected in directions.items()
}
bpy.ops.wm.save_as_mainfile(filepath=str(output))
print(
    json.dumps(
        {
            "action": action.name,
            "mapped_directions": len(directions),
            "max_direction_error_deg": max(errors.values()),
            "mean_direction_error_deg": sum(errors.values()) / len(errors),
            "reference_height_m": height,
            "uniform_runtime_scale": 1.8 / height,
        }
    )
)
