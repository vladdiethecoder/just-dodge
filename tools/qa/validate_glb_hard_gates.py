#!/usr/bin/env python3
"""
Post-Download GLB Hard Gate Validator
=====================================
Auto-rejects Meshy GLB downloads that fail any hard numeric gate.
Must be run before any Blender inspection or engine cooking.

Hard gates from 500-defect audit:
  - Vertices ≤ 25,000
  - Triangles ≤ 50,000
  - Boundary edges = 0
  - Bones ≥ 24
  - Materials ≥ 2
  - Arm span:height ≥ 0.95
  - Watertight = Yes
  - Face budget for rigging ≤ 300,000

Usage: python3 tools/qa/validate_glb_hard_gates.py <model.glb>
"""
import sys, json, hashlib, struct, os, subprocess
from pathlib import Path
from datetime import datetime

def parse_glb_basic(path: Path) -> dict:
    """Parse GLB header and JSON chunk to get basic info."""
    with open(path, 'rb') as f:
        header = f.read(12)
        if header[:4] != b'glTF':
            return {'error': 'Not a valid GLB file'}
        
        # Read JSON chunk
        chunk_len = struct.unpack('<I', f.read(4))[0]
        chunk_type = struct.unpack('<I', f.read(4))[0]
        if chunk_type != 0x4E4F534A:  # 'JSON'
            return {'error': 'First chunk is not JSON'}
        
        json_data = json.loads(f.read(chunk_len))
    
    info = {'file_size': os.path.getsize(path)}
    
    # Meshes
    if 'meshes' in json_data:
        total_verts = 0
        total_tris = 0
        for mesh in json_data['meshes']:
            for prim in mesh.get('primitives', []):
                if 'attributes' in prim and 'POSITION' in prim['attributes']:
                    pos_acc = prim['attributes']['POSITION']
                    if 'accessors' in json_data:
                        acc = json_data['accessors'][pos_acc]
                        total_verts += acc.get('count', 0)
                if 'indices' in prim:
                    idx_acc = prim['indices']
                    if 'accessors' in json_data:
                        acc = json_data['accessors'][idx_acc]
                        total_tris += acc.get('count', 0) // 3
    
    info['vertices'] = total_verts
    info['triangles'] = total_tris
    
    # Bones (from skins or nodes)
    bones = 0
    if 'nodes' in json_data:
        for node in json_data['nodes']:
            if 'mesh' in node and 'skin' in node:
                if 'skins' in json_data:
                    skin = json_data['skins'][node['skin']]
                    bones = max(bones, len(skin.get('joints', [])))
    info['bones'] = bones
    
    # Materials
    info['materials'] = len(json_data.get('materials', []))
    
    # Bounds from accessor min/max
    if 'accessors' in json_data:
        for acc in json_data['accessors']:
            if acc.get('type') == 'VEC3' and 'max' in acc and 'min' in acc:
                mx, mn = acc['max'], acc['min']
                if abs(mx[0] - mn[0]) > 1.0:  # plausible width
                    info['bounds'] = {'min': mn, 'max': mx}
                    info['width'] = mx[0] - mn[0]
                    info['height'] = mx[1] - mn[1] if mx[1] > mx[2] else mx[2] - mn[2]
                    info['arm_span_to_height'] = round(info['width'] / info['height'], 4)
                    break
    
    return info

def check_watertight(path: Path) -> tuple[bool, int]:
    """Check watertightness via Blender headless."""
    try:
        script = f"""
import bpy, json
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath='{path}')
boundary = 0
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        boundary = sum(1 for e in bm.edges if e.is_boundary)
        bm.free()
print(json.dumps({{'boundary_edges': boundary}}))
"""
        result = subprocess.run(
            ['blender', '--background', '--python-expr', script],
            capture_output=True, text=True, timeout=60
        )
        for line in result.stdout.split('\n'):
            if 'boundary_edges' in line:
                data = json.loads(line.strip())
                return data['boundary_edges'] == 0, data['boundary_edges']
    except Exception as e:
        return False, -1
    
    return False, -1

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/qa/validate_glb_hard_gates.py <model.glb>")
        sys.exit(1)
    
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"ERROR: {path} not found")
        sys.exit(1)
    
    # SHA-256
    with open(path, 'rb') as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    
    info = parse_glb_basic(path)
    
    # Hard gates
    gates = [
        ('vertices_ok', info.get('vertices', 0) <= 25000, f"{info.get('vertices', 0)} (≤25,000)"),
        ('triangles_ok', info.get('triangles', 0) <= 50000, f"{info.get('triangles', 0)} (≤50,000)"),
        ('bones_ok', info.get('bones', 0) >= 24, f"{info.get('bones', 0)} (≥24)"),
        ('materials_ok', info.get('materials', 0) >= 2, f"{info.get('materials', 0)} (≥2)"),
        ('arm_span_ok', info.get('arm_span_to_height', 0) >= 0.95, f"{info.get('arm_span_to_height', 0)} (≥0.95)"),
        ('rigging_budget_ok', info.get('triangles', 0) <= 300000, f"{info.get('triangles', 0)} (≤300,000 for rigging)"),
    ]
    
    # Watertight (slow — only if Blender available and basic gates pass)
    all_basic_pass = all(g[1] for g in gates)
    if all_basic_pass:
        wt, boundary = check_watertight(path)
        gates.append(('watertight_ok', wt, f"{boundary} boundary edges (0 required)"))
    else:
        gates.append(('watertight_ok', None, 'skipped (basic gates failed)'))
    
    passed = sum(1 for g in gates if g[1] is True)
    failed = sum(1 for g in gates if g[1] is False)
    skipped = sum(1 for g in gates if g[1] is None)
    
    verdict = 'PASS' if failed == 0 and skipped == 0 else 'REJECT'
    
    report = {
        'tool': 'validate_glb_hard_gates',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'model_path': str(path),
        'sha256': sha,
        'file_size': info.get('file_size', 0),
        'glb_info': info,
        'gates': [{'name': g[0], 'pass': g[1], 'detail': g[2]} for g in gates],
        'passed': passed,
        'failed': failed,
        'skipped': skipped,
        'verdict': verdict,
    }
    
    # Write receipt
    receipt_path = path.parent / f'{path.stem}_hard_gate_receipt.json'
    with open(receipt_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"GLB HARD GATE VALIDATION: {verdict}")
    print(f"{'='*60}")
    print(f"  Model: {path}")
    print(f"  SHA-256: {sha[:32]}...")
    print(f"  Verts: {info.get('vertices', '?')}, Tris: {info.get('triangles', '?')}")
    print(f"  Bones: {info.get('bones', '?')}, Materials: {info.get('materials', '?')}")
    print(f"  Span:Height: {info.get('arm_span_to_height', '?')}")
    for g in gates:
        if g[1] is True:
            print(f"  ✓ {g[0]}: {g[2]}")
        elif g[1] is False:
            print(f"  ✗ {g[0]}: {g[2]}")
        else:
            print(f"  ? {g[0]}: {g[2]}")
    print(f"\n  Receipt: {receipt_path}")
    
    if verdict == 'REJECT':
        print(f"\n  ⛔ REJECTED. Do NOT download. Do NOT inspect further.")
        print(f"     Fix reference images and regenerate.")
    
    sys.exit(0 if verdict == 'PASS' else 1)

if __name__ == '__main__':
    main()
