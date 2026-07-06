#!/usr/bin/env python3
"""
Extract mesh data from an FBX file using Blender's Python API.
Usage: blender --background --python tools/extract_fbx_mesh.py -- input.fbx output.bin
Deduplicates shared vertices for compact .bin output.
"""
import bpy, struct, sys

argv = sys.argv[sys.argv.index('--') + 1:]
input_fbx, output_bin = argv[0], argv[1]

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Import FBX
bpy.ops.import_scene.fbx(filepath=input_fbx)

# Find first mesh
mesh_obj = None
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        mesh_obj = obj
        break
if not mesh_obj:
    print("No mesh found")
    sys.exit(1)

mesh = mesh_obj.data

# Triangulate
import bmesh
bm = bmesh.new()
bm.from_mesh(mesh)
bmesh.ops.triangulate(bm, faces=bm.faces)
bm.to_mesh(mesh)
bm.free()

mesh.calc_loop_triangles()
uv_layer = mesh.uv_layers.active

# Collect all vertex data per loop (triangle corner)
vert_data = []  # (x, y, z, nx, ny, nz, u, v) per loop
for tri in mesh.loop_triangles:
    for loop_idx in tri.loops:
        v = mesh.vertices[mesh.loops[loop_idx].vertex_index]
        if uv_layer:
            uv = uv_layer.data[loop_idx].uv
        else:
            uv = (0.0, 0.0)
        vert_data.append((v.co.x, v.co.y, v.co.z,
                          v.normal.x, v.normal.y, v.normal.z,
                          uv.x, uv.y))

# Deduplicate: same position = same vertex
unique = {}
new_verts = []
new_norms = []
new_uvs = []
new_idx = []
for vd in vert_data:
    key = (round(vd[0], 6), round(vd[1], 6), round(vd[2], 6))
    if key not in unique:
        unique[key] = len(new_verts)
        new_verts.extend([vd[0], vd[1], vd[2]])
        new_norms.extend([vd[3], vd[4], vd[5]])
        new_uvs.extend([vd[6], vd[7]])
    new_idx.append(unique[key])

vc = len(new_verts) // 3
ic = len(new_idx)
ratio = len(vert_data) // 3 / (vc / 3) if vc > 0 else 1
print(f"Raw tris: {len(vert_data)//3}, Unique verts: {vc}, Dedup ratio: {ratio:.1f}x")

with open(output_bin, 'wb') as f:
    f.write(struct.pack('<II', vc, ic))
    f.write(struct.pack(f'<{vc * 3}f', *new_verts))
    f.write(struct.pack(f'<{vc * 3}f', *new_norms))
    f.write(struct.pack(f'<{vc * 2}f', *new_uvs))
    f.write(struct.pack(f'<{ic}I', *new_idx))

print(f"Extracted {vc} verts, {ic} idxs → {output_bin} ({len(open.name)} bytes)")
