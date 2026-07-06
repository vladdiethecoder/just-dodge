#!/usr/bin/env python3
"""
Extract vertex data and embedded textures from a GLB file.
Usage: python3 tools/extract_mesh.py input.glb output_base_path

Output files:
  output_base_path.bin       - vertex positions, normals, UVs, indices
  output_base_path_0.jpg     - base color texture
  output_base_path_1.jpg     - metallic-roughness texture
  output_base_path_2.jpg     - normal map texture
  output_base_path_3.jpg     - emissive texture
"""
import struct, json, sys, os

def extract_glb(glb_path):
    with open(glb_path, 'rb') as f:
        f.read(12)
        chunks = []
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            chunk_len = struct.unpack('<I', hdr[:4])[0]
            chunk_type = struct.unpack('<I', hdr[4:8])[0]
            d = f.read(chunk_len)
            if len(d) < chunk_len:
                break
            chunks.append((chunk_type, d))
    j = d2 = None
    for t, d in chunks:
        if t == 0x4E4F534A:
            j = json.loads(d.decode('utf-8'))
        elif t == 0x004E4942:
            d2 = d
    return j, d2

def read_attr(bin_data, gltf, acc_idx, comp_size):
    if acc_idx is None:
        return None
    acc = gltf['accessors'][acc_idx]
    bv = gltf['bufferViews'][acc['bufferView']]
    cnt = acc['count']
    stride = bv.get('byteStride', comp_size)
    off = bv['byteOffset'] + acc.get('byteOffset', 0)
    raw = bytearray()
    for i in range(cnt):
        raw.extend(bin_data[off + i * stride:off + i * stride + comp_size])
    return list(struct.unpack(f'<{cnt * (comp_size // 4)}f', raw))

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 tools/extract_mesh.py input.glb output_base")
        sys.exit(1)

    glb_path, base_path = sys.argv[1], sys.argv[2]
    gltf, bin_data = extract_glb(glb_path)

    if gltf is None or bin_data is None:
        print("Error: invalid GLB file")
        sys.exit(1)

    # Extract images
    img_count = 0
    for i, img in enumerate(gltf.get('images', [])):
        bv_idx = img['bufferView']
        bv = gltf['bufferViews'][bv_idx]
        img_data = bin_data[bv['byteOffset']:bv['byteOffset'] + bv['byteLength']]
        ext = 'png' if img['mimeType'] == 'image/png' else 'jpg'
        out_img = f"{base_path}_{i}.{ext}"
        with open(out_img, 'wb') as f:
            f.write(img_data)
        print(f"Extracted image {i}: {len(img_data)} bytes → {out_img}")
        img_count += 1

    # Extract mesh data
    for mesh in gltf.get('meshes', []):
        for prim in mesh['primitives']:
            p_idx = prim['attributes'].get('POSITION')
            n_idx = prim['attributes'].get('NORMAL')
            u_idx = prim['attributes'].get('TEXCOORD_0')
            i_idx = prim.get('indices')
            if p_idx is None or i_idx is None:
                continue

            vc = gltf['accessors'][p_idx]['count']
            ic = gltf['accessors'][i_idx]['count']

            pos = read_attr(bin_data, gltf, p_idx, 12)
            nrm = read_attr(bin_data, gltf, n_idx, 12) or [0.0] * (vc * 3)
            uvs = read_attr(bin_data, gltf, u_idx, 8) or [0.0] * (vc * 2)

            i_acc = gltf['accessors'][i_idx]
            i_bv = gltf['bufferViews'][i_acc['bufferView']]
            ctype = i_acc.get('componentType')
            i_off = i_bv['byteOffset'] + i_acc.get('byteOffset', 0)
            i_len = ic * (2 if ctype == 5123 else 4)
            if ctype == 5123:
                idx = list(struct.unpack(f'<{ic}H', bin_data[i_off:i_off + i_len]))
            elif ctype == 5125:
                idx = list(struct.unpack(f'<{ic}I', bin_data[i_off:i_off + i_len]))
            else:
                print(f"Unsupported index type {ctype}")
                sys.exit(1)

            out_bin = base_path + '.bin'
            with open(out_bin, 'wb') as f:
                f.write(struct.pack('<II', vc, ic))
                f.write(struct.pack(f'<{vc * 3}f', *pos))
                f.write(struct.pack(f'<{vc * 3}f', *nrm))
                f.write(struct.pack(f'<{vc * 2}f', *uvs))
                f.write(struct.pack(f'<{ic}I', *idx))

            print(f"{vc} verts, {ic} idxs → {out_bin}")
            return

    print("No mesh primitives found")

if __name__ == '__main__':
    main()
