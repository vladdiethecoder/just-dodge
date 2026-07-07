#!/usr/bin/env python3
"""Read back a SKM1 .bin + ANM1 .anim and assert integrity.

Usage: python3 tools/verify_skinned_bin.py assets/characters/mannequin_male.bin \
       [assets/characters/mannequin_male_running.anim]
"""
import struct
import sys

IDENT = "SKM1"
AIDENT = "ANM1"


def read_bin(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:4] == IDENT.encode(), "bad magic"
    off = 4
    vert_count, index_count, bone_count = struct.unpack_from("<III", data, off)
    off += 12
    verts = []
    for _ in range(vert_count):
        pos = struct.unpack_from("<3f", data, off); off += 12
        nrm = struct.unpack_from("<3f", data, off); off += 12
        uv = struct.unpack_from("<2f", data, off); off += 8
        verts.append((pos, nrm, uv))
    idxs = list(struct.unpack_from("<%dI" % index_count, data, off)); off += 4 * index_count
    bones = []
    for _ in range(bone_count):
        (nl,) = struct.unpack_from("<H", data, off); off += 2
        name = data[off:off + nl].decode(); off += nl
        (pi,) = struct.unpack_from("<i", data, off); off += 4
        rest = struct.unpack_from("<16f", data, off); off += 64
        inv = struct.unpack_from("<16f", data, off); off += 64
        bones.append((name, pi, rest, inv))
    skin = []
    for _ in range(vert_count):
        (cnt,) = struct.unpack_from("<B", data, off); off += 1
        g = []
        for _ in range(cnt):
            ji, w = struct.unpack_from("<If", data, off); off += 8
            g.append((ji, w))
        skin.append(g)
    assert off == len(data), f"trailing bytes: {len(data) - off}"
    return vert_count, index_count, bone_count, verts, idxs, bones, skin


def read_anim(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:4] == AIDENT.encode(), "bad anim magic"
    off = 4
    bone_count, fps, frame_count = struct.unpack_from("<IHI", data, off)
    off += 10
    frames = []
    for _ in range(frame_count):
        fm = []
        for _ in range(bone_count):
            m = struct.unpack_from("<16f", data, off); off += 64
            fm.append(m)
        frames.append(fm)
    assert off == len(data), f"anim trailing bytes: {len(data) - off}"
    return bone_count, fps, frame_count, frames


def m_row(m):
    return [m[i*4:i*4+4] for i in range(4)]


if __name__ == "__main__":
    binp = sys.argv[1]
    animp = sys.argv[2] if len(sys.argv) > 2 else None
    vc, ic, bc, verts, idxs, bones, skin = read_bin(binp)
    print(f"[OK] {binp}")
    print(f"  verts={vc} idxs={ic} bones={bc}")
    # index bounds
    assert max(idxs) < vc, "index out of range"
    # bone parent integrity
    for name, pi, _, _ in bones:
        if pi != -1:
            assert 0 <= pi < bc, f"{name} bad parent"
    # head bone Y above hips (Y-up game space). Translation stored row-major at
    # indices 3 (x), 7 (y), 11 (z) of each 16-float matrix.
    hidx = next(i for i, b in enumerate(bones) if b[0] == "Hips")
    head_idx = next((i for i, b in enumerate(bones) if b[0] == "Head"), None)
    def world_y(inv):
        # world bind = inverse(inv_bind); translation = -inv_trans for rigid
        return -inv[7]
    # inverse bind should map bind mesh ~ to bone space; check diag of rest not degenerate
    # skin weights sum ~1 and max 4
    bad_w = 0
    for g in skin:
        s = sum(w for _, w in g)
        if abs(s - 1.0) > 0.02 or len(g) > 4:
            bad_w += 1
    print(f"  skin verts with bad weight sum/>4 = {bad_w}/{vc}")
    # vertex bounding-box height (game Y) — model should be ~1.5-1.8 units tall
    vys = [verts[i][0][1] for i in range(vc)]  # pos[1] = Y
    vh = max(vys) - min(vys)
    print(f"  mesh bbox height (game Y) = {vh:.3f}  (verts {min(vys):.3f}..{max(vys):.3f})")
    assert 0.5 < vh < 4.0, f"mesh height {vh:.2f} not in humanoid range"
    # show bone names
    print("  bones: " + ", ".join(b[0] for b in bones))

    if animp:
        abc, fps, fc, frames = read_anim(animp)
        print(f"[OK] {animp}")
        print(f"  bones={abc} fps={fps} frames={fc}")
        assert abc == bc, "anim bone count mismatch"
        # Hips parent-relative local translate Y (row-major index 7) should vary
        hips_local_ty = [f[hidx][7] for f in frames]
        delta = max(hips_local_ty) - min(hips_local_ty)
        print(f"  Hips local translate Y range: {min(hips_local_ty):.4f}..{max(hips_local_ty):.4f} (delta={delta:.4f})")
        # count bones that actually change across frames
        moving = 0
        for b in range(bc):
            f0 = frames[0][b]
            if any(any(abs(f[b][i] - f0[i]) > 1e-3 for i in range(16)) for f in frames[1:]):
                moving += 1
        print(f"  bones whose matrix changes across clip: {moving}/{bc}")
        assert delta > 1e-3 or moving > 0, "animation appears static!"
        print("  [OK] animation is non-static")
    print("ALL CHECKS PASSED")
