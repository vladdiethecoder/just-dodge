#!/usr/bin/env python3
"""
extract_fbx_skinned.py — Export a rigged FBX to a skinned mesh + baked animation.

Usage (Blender headless):
    blender --background --python tools/extract_fbx_skinned.py -- \
        input.fbx output.bin [--anim-out clip.anim] [--no-bake]

What is preserved (nothing thrown away):
  - Triangulated vertex positions, normals, UVs, indices   (mesh)
  - Full bone hierarchy: name, parent index, rest-local matrix, inverse-bind matrix
  - Per-vertex skin weights: top-4 joints by magnitude, renormalized
  - Baked skeletal animation (optional): per-frame, per-bone parent-relative local matrix

Coordinate handling (so the game sees a sane model):
  - Everything is converted into MESH-LOCAL space first (matches the old exporter's
    vertex space, so the static mesh looks identical to before).
  - A global transform G = R * Scale(s) is applied uniformly to vertices, normals,
    bone matrices and animation matrices:
        R : Blender Z-up / -Y-forward  ->  game Y-up / +Z-forward (rotation -90deg about X)
        s : auto-detected cm->m scale (1.0 if model is already meter-scale)
  - Skinning stays self-consistent because G is applied to vertices AND bones AND anim.

Output format (magic "SKM1"):
  b"SKM1"                         (4 bytes)
  u32 vert_count
  u32 index_count
  u32 bone_count
  -- vertices: vert_count * (pos[3] f32, normal[3] f32, uv[2] f32)
  -- indices : index_count * u32
  -- bones   : bone_count * (
        u16 name_len; name (utf8 bytes)
        i32 parent_index            (-1 = root)
        f32[16] rest_local          (parent-relative rest matrix, game space)
        f32[16] inverse_bind        (game space)
  )
  -- skin    : vert_count * (
        u8 count (1..4)
        count * (u32 joint_index, f32 weight)
  )

Animation format (magic "ANM1"):
  b"ANM1"                         (4 bytes)
  u32 bone_count
  u16 fps
  u32 frame_count
  -- per frame f: for each bone b: f32[16] local_matrix (parent-relative, game space)
"""

import bpy
import sys
import struct
import mathutils


# ---------------------------------------------------------------------------
# Blender Z-up/-Y-forward  ->  game Y-up/+Z-forward
# Equivalent to rotation -90deg about X: (x, y, z) -> (x, z, -y)
# ---------------------------------------------------------------------------
def axis_rotation():
    # column-major mathutils.Matrix; R @ v maps (x,y,z,1)->(x,z,-y,1)
    return mathutils.Matrix((
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))


def mat_to_list(m):
    # row-major flat list of 16 floats (what we serialize)
    return [float(v) for row in m.row for v in row]


def apply_global(m, G):
    # G @ m @ G^{-1}  (G orthonormal up to uniform scale)
    Ginv = G.inverted()
    return G @ m @ Ginv


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    if len(argv) < 2:
        print("Usage: blender --background --python extract_fbx_skinned.py -- "
              "input.fbx output.bin [--anim-out clip.anim] [--no-bake]")
        sys.exit(1)

    input_fbx = argv[0]
    out_bin = argv[1]
    anim_out = None
    bake = True
    if "--anim-out" in argv:
        anim_out = argv[argv.index("--anim-out") + 1]
    if "--no-bake" in argv:
        bake = False

    # Fresh scene
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=input_fbx)

    armature = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    mesh_obj = next((o for o in bpy.data.objects if o.type == "MESH"), None)
    if armature is None or mesh_obj is None:
        print("ERROR: FBX must contain an ARMATURE and a MESH")
        sys.exit(1)

    R = axis_rotation()

    # ---- Bone rest matrices in MESH-LOCAL space -------------------------
    # M_i (mesh-local rest world) = mesh_world^{-1} * arm_world * bone.matrix_local
    mesh_world_inv = mesh_obj.matrix_world.inverted()
    arm_world = armature.matrix_world

    bones = list(armature.data.bones)
    bone_index = {b.name: i for i, b in enumerate(bones)}
    bone_count = len(bones)

    M_rest = []  # mesh-local rest-world matrices
    for b in bones:
        m = mesh_world_inv @ arm_world @ b.matrix_local
        M_rest.append(m)

    # auto-detect scale from the MESH bounding box (authoritative: that's what
    # renders). Blender's FBX importer brings Meshy models in at ~100x (cm); a
    # humanoid should end up ~1.5-1.8 game units tall. If the bbox height is
    # clearly not already meters (> 5 units), rescale to ~1.6 units.
    ys = [v.co.z for v in mesh_obj.data.vertices]  # Blender Z-up pre-bake
    bbox_h = (max(ys) - min(ys)) if ys else 0.0
    s = 0.05 if bbox_h > 5.0 else 1.0
    G = mathutils.Matrix.Scale(s, 4) @ R  # uniform scale then rotation

    # ---- Mesh vertices (mesh-local, then G applied) ---------------------
    mesh = mesh_obj.data
    mesh.calc_loop_triangles()
    uv_layer = mesh.uv_layers.active

    # Build per-loop vertex list with full attribute tuple (so skin seams are
    # NOT merged). Dedupe only on the complete tuple.
    def skin_key(groups):
        # stable key of (joint_index, weight) sorted
        return tuple(sorted((gi, round(w, 4)) for gi, w in groups))

    unique = {}
    new_pos, new_nrm, new_uv = [], [], []
    new_idx, new_skin = [], []
    vg_map = {g.index: g.name for g in mesh_obj.vertex_groups}

    for tri in mesh.loop_triangles:
        for loop_idx in tri.loops:
            li = mesh.loops[loop_idx]
            v = mesh.vertices[li.vertex_index]
            co = v.co
            no = v.normal
            uv = uv_layer.data[loop_idx].uv if uv_layer else (0.0, 0.0)

            # skin weights -> bone indices
            groups = []
            for g in v.groups:
                gname = vg_map.get(g.group)
                if gname in bone_index and g.weight > 0.0:
                    groups.append((bone_index[gname], g.weight))
            groups.sort(key=lambda t: t[1], reverse=True)
            top = groups[:4]
            wsum = sum(w for _, w in top) or 1.0
            top = [(ji, w / wsum) for ji, w in top]

            key = (round(co.x, 5), round(co.y, 5), round(co.z, 5),
                   round(no.x, 4), round(no.y, 4), round(no.z, 4),
                   round(uv[0], 5), round(uv[1], 5), skin_key(top))
            if key not in unique:
                # apply global transform to point + normal
                gp = G @ co.to_4d()
                gn = (R @ no.normalized().to_4d())  # rotation only
                unique[key] = len(new_pos) // 3  # VERTEX index, not float count
                new_pos.extend([gp.x, gp.y, gp.z])
                new_nrm.extend([gn.x, gn.y, gn.z])
                new_uv.extend([uv[0], uv[1]])
                new_skin.append(top)
            new_idx.append(unique[key])

    vert_count = len(new_pos) // 3
    index_count = len(new_idx)
    print(f"Mesh: {vert_count} verts, {index_count} idxs (dedup from loops)")
    print(f"Scale factor s={s} (pre-bake mesh bbox height={bbox_h:.2f})")

    # ---- Bone serialization ---------------------------------------------
    rest_local = []  # parent-relative rest (game space)
    inv_bind = []
    parent_indices = []
    bone_names = []
    for i, b in enumerate(bones):
        p = b.parent
        pi = bone_index[p.name] if p is not None else -1
        parent_indices.append(pi)
        Mp_inv = M_rest[pi].inverted() if pi >= 0 else mathutils.Matrix.Identity(4)
        rl = Mp_inv @ M_rest[i]                  # parent-relative rest (mesh-local)
        rl_g = apply_global(rl, G)
        ib = (M_rest[i]).inverted()             # mesh-local inverse bind
        ib_g = apply_global(ib, G)
        rest_local.append(rl_g)
        inv_bind.append(ib_g)
        bone_names.append(b.name)

    # ---- Write .bin ------------------------------------------------------
    with open(out_bin, "wb") as f:
        f.write(b"SKM1")
        f.write(struct.pack("<III", vert_count, index_count, bone_count))
        # vertices
        for i in range(vert_count):
            f.write(struct.pack("<3f", new_pos[3*i], new_pos[3*i+1], new_pos[3*i+2]))
            f.write(struct.pack("<3f", new_nrm[3*i], new_nrm[3*i+1], new_nrm[3*i+2]))
            f.write(struct.pack("<2f", new_uv[2*i], new_uv[2*i+1]))
        # indices
        f.write(struct.pack("<%dI" % index_count, *new_idx))
        # bones
        for i in range(bone_count):
            nb = bone_names[i].encode("utf-8")
            f.write(struct.pack("<H", len(nb)))
            f.write(nb)
            f.write(struct.pack("<i", parent_indices[i]))
            f.write(struct.pack("<16f", *mat_to_list(rest_local[i])))
            f.write(struct.pack("<16f", *mat_to_list(inv_bind[i])))
        # skin
        for i in range(vert_count):
            top = new_skin[i]
            cnt = len(top)
            f.write(struct.pack("<B", cnt))
            for ji, w in top:
                f.write(struct.pack("<If", ji, w))
    print(f"Wrote {out_bin}: {bone_count} bones, {vert_count} skinned verts")

    # ---- Bake animation (optional) --------------------------------------
    if anim_out and bake:
        ad = armature.animation_data
        if ad and ad.action:
            act = ad.action
            fs, fe = act.frame_range
            fps = getattr(act, "fps", bpy.context.scene.render.fps) or 30
            frames = list(range(int(fs), int(fe) + 1))
            # ensure pose mode
            bpy.context.view_layer.objects.active = armature
            with open(anim_out, "wb") as f:
                f.write(b"ANM1")
                f.write(struct.pack("<IHI", bone_count, int(round(fps)), len(frames)))
                for fr in frames:
                    bpy.context.scene.frame_set(fr)
                    bpy.context.view_layer.update()
                    for i, b in enumerate(bones):
                        # pose.bones[i].matrix is parent-relative in armature-local
                        pm = mesh_world_inv @ arm_world @ armature.pose.bones[i].matrix
                        pm_g = apply_global(pm, G)
                        f.write(struct.pack("<16f", *mat_to_list(pm_g)))
            print(f"Wrote {anim_out}: {len(frames)} frames @ {fps}fps, {bone_count} bones")
        else:
            print("No armature animation found; skipping .anim")


if __name__ == "__main__":
    main()
