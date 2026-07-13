#!/usr/bin/env python3
"""Cook the accepted W0 sword FBX into Just Dodge's rigid-mesh binary format.

Usage:
  blender --background --python tools/cook_w0_sword.py -- <source.fbx> <output.bin>

The source asset is a nine-component Blender assembly. This cooker preserves all
components in assembly-local coordinates; the runtime supplies its visual-only
first-person transform.
"""

from __future__ import annotations

from array import array
import hashlib
from pathlib import Path
import struct
import sys

import bpy

EXPECTED_FBX_SHA256 = "01705aabb18c55686e701eeb0d57db30aba3021a8d05514834993a5fef723cba"
EXPECTED_COMPONENTS = 9
EXPECTED_MIN = (-0.1400000006, -0.0250000004, -0.3519999981)
EXPECTED_MAX = (0.1400000006, 0.0250000004, 1.1978248358)
BOUNDS_TOLERANCE_M = 2.0e-4


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_close_vector(label: str, actual: tuple[float, float, float], expected: tuple[float, float, float]) -> None:
    if any(abs(actual[index] - expected[index]) > BOUNDS_TOLERANCE_M for index in range(3)):
        raise RuntimeError(f"{label}: expected {expected}, got {actual}")


def main() -> None:
    if "--" not in sys.argv:
        raise RuntimeError("missing -- separator")
    args = sys.argv[sys.argv.index("--") + 1 :]
    if len(args) != 2:
        raise RuntimeError("expected <source.fbx> <output.bin>")

    source_path = Path(args[0]).resolve()
    output_path = Path(args[1]).resolve()
    if sys.byteorder != "little":
        raise RuntimeError("W0 rigid-mesh format is little-endian")
    if sha256(source_path) != EXPECTED_FBX_SHA256:
        raise RuntimeError(f"unexpected W0 source hash for {source_path}")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=str(source_path))
    meshes = sorted((obj for obj in bpy.context.scene.objects if obj.type == "MESH"), key=lambda obj: obj.name)
    if len(meshes) != EXPECTED_COMPONENTS:
        raise RuntimeError(f"expected {EXPECTED_COMPONENTS} W0 mesh components, got {len(meshes)}")

    positions = array("f")
    normals = array("f")
    uvs = array("f")
    indices = array("I")
    low = [float("inf")] * 3
    high = [float("-inf")] * 3

    for obj in meshes:
        mesh = obj.data
        mesh.calc_loop_triangles()
        active_uv = mesh.uv_layers.active
        normal_matrix = obj.matrix_world.to_3x3().inverted_safe().transposed()
        for triangle in mesh.loop_triangles:
            for loop_index in triangle.loops:
                loop = mesh.loops[loop_index]
                vertex = mesh.vertices[loop.vertex_index]
                position = obj.matrix_world @ vertex.co
                normal = (normal_matrix @ loop.normal).normalized()
                uv = active_uv.data[loop_index].uv if active_uv else (0.0, 0.0)
                index = len(positions) // 3
                positions.extend((position.x, position.y, position.z))
                normals.extend((normal.x, normal.y, normal.z))
                uvs.extend((uv[0], uv[1]))
                indices.append(index)
                for axis, value in enumerate(position):
                    low[axis] = min(low[axis], value)
                    high[axis] = max(high[axis], value)

    actual_min = tuple(low)
    actual_max = tuple(high)
    assert_close_vector("W0 minimum bounds", actual_min, EXPECTED_MIN)
    assert_close_vector("W0 maximum bounds", actual_max, EXPECTED_MAX)
    if not positions or len(indices) % 3:
        raise RuntimeError("W0 cooker produced no complete triangles")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as output:
        output.write(struct.pack("<II", len(positions) // 3, len(indices)))
        # `asset::load_binary` defines this exact serialized order.
        positions.tofile(output)
        normals.tofile(output)
        indices.tofile(output)
        uvs.tofile(output)

    print(
        "W0_COOK_OK"
        f" source_sha256={EXPECTED_FBX_SHA256}"
        f" components={len(meshes)}"
        f" vertices={len(positions) // 3}"
        f" triangles={len(indices) // 3}"
        f" bounds_min={actual_min}"
        f" bounds_max={actual_max}"
        f" output={output_path}"
    )


if __name__ == "__main__":
    main()
