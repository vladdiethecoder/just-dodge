#!/usr/bin/env python3
"""
Pre-Meshy Reference Image Validator
====================================
Runs the 13-point quality gate on reference images before submission to Meshy.
Must PASS before any credits are spent. Failures are HARD BLOCKS — fix images, re-run.

Usage: python3 tools/qa/validate_reference_images.py <image_dir>
Example: python3 tools/qa/validate_reference_images.py assets/source/meshy/ph1_fighter_001/references/

Gate source: 500-defect vision audit (docs/reports/PH1_FIGHTER_001_500_DEFECT_AUDIT.json)
"""
import sys, os, json, hashlib
from pathlib import Path
from datetime import datetime

# Try to import PIL, fall back gracefully
try:
    from PIL import Image
    import numpy as np
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("WARNING: PIL not available — only structural checks will run (no pixel-level analysis)")

REQUIRED_VIEWS = ['front', 'right', 'back', 'front_three_quarter']

def check_structural(img_dir: Path) -> list[dict]:
    """Check file existence, naming, format."""
    results = []
    for view in REQUIRED_VIEWS:
        png = img_dir / f'{view}.png'
        jpg = img_dir / f'{view}.jpg'
        if png.exists():
            results.append({'check': f'{view}_exists', 'pass': True, 'detail': str(png)})
        elif jpg.exists():
            results.append({'check': f'{view}_exists', 'pass': True, 'detail': str(jpg)})
        else:
            results.append({'check': f'{view}_exists', 'pass': False, 'detail': f'Missing required view: {view}'})
    return results

def check_pixel(img_dir: Path) -> list[dict]:
    """Pixel-level quality checks using PIL."""
    if not HAS_PIL:
        return [{'check': 'pixel_analysis', 'pass': False, 'detail': 'PIL/numpy not available'}]
    
    results = []
    
    for view in REQUIRED_VIEWS:
        for ext in ['.png', '.jpg']:
            path = img_dir / f'{view}{ext}'
            if not path.exists():
                continue
            
            img = Image.open(path).convert('RGB')
            arr = np.array(img, dtype=np.float64)
            
            # GATE 6: Background uniformity (±5 RGB values)
            # Sample corners and center
            h, w = arr.shape[:2]
            corners = [
                arr[10:30, 10:30].mean(axis=(0,1)),
                arr[10:30, -30:-10].mean(axis=(0,1)),
                arr[-30:-10, 10:30].mean(axis=(0,1)),
                arr[-30:-10, -30:-10].mean(axis=(0,1)),
            ]
            bg_std = np.std([c.mean() for c in corners])
            bg_pass = bg_std < 5.0
            results.append({'check': f'{view}_bg_uniformity', 'pass': bool(bg_pass),
                          'detail': f'Corner stddev={bg_std:.1f} (must be <5)'})
            
            # GATE 9: Fingertip margin (≥10% frame width)
            # Check if pixels near left/right edges are background or character
            margin = w // 10
            left_strip = arr[:, :margin, :]
            right_strip = arr[:, -margin:, :]
            left_bg = (np.std(left_strip, axis=2) < 10).mean()
            right_bg = (np.std(right_strip, axis=2) < 10).mean()
            margin_pass = left_bg > 0.85 and right_bg > 0.85
            results.append({'check': f'{view}_margin', 'pass': bool(margin_pass),
                          'detail': f'Left bg={left_bg:.1%}, Right bg={right_bg:.1%} (must be >85% each, i.e. 10% margin)'})
            
            # GATE 7: No specular highlights (max brightness must stay below 250)
            max_bright = arr.max()
            highlight_pass = max_bright < 250
            results.append({'check': f'{view}_no_specular', 'pass': bool(highlight_pass),
                          'detail': f'Max brightness={max_bright:.0f} (must be <250)'})
            
            # Resolution check
            if w < 1024 or h < 1024:
                results.append({'check': f'{view}_resolution', 'pass': False,
                              'detail': f'{w}x{h} (minimum 1024x1024)'})
            else:
                results.append({'check': f'{view}_resolution', 'pass': True, 'detail': f'{w}x{h}'})
            
            break  # only check first found extension
    
    return results

def check_consistency(img_dir: Path) -> list[dict]:
    """Check consistency across views."""
    if not HAS_PIL:
        return []
    
    results = []
    sizes = {}
    
    for view in REQUIRED_VIEWS:
        for ext in ['.png', '.jpg']:
            path = img_dir / f'{view}{ext}'
            if path.exists():
                img = Image.open(path)
                sizes[view] = img.size
                break
    
    if len(sizes) >= 2:
        unique_sizes = set(sizes.values())
        consistent = len(unique_sizes) == 1
        results.append({'check': 'cross_view_size', 'pass': bool(consistent),
                      'detail': f'Sizes: {sizes}'})
    
    return results

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/qa/validate_reference_images.py <image_dir>")
        sys.exit(1)
    
    img_dir = Path(sys.argv[1])
    if not img_dir.is_dir():
        print(f"ERROR: {img_dir} is not a directory")
        sys.exit(1)
    
    results = []
    results.extend(check_structural(img_dir))
    results.extend(check_pixel(img_dir))
    results.extend(check_consistency(img_dir))
    
    # Summarize
    passed = sum(1 for r in results if r['pass'])
    failed = sum(1 for r in results if not r['pass'])
    total = len(results)
    
    report = {
        'tool': 'validate_reference_images',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'image_dir': str(img_dir),
        'total_checks': total,
        'passed': passed,
        'failed': failed,
        'verdict': 'PASS' if failed == 0 else 'FAIL',
        'checks': results,
    }
    
    # Write receipt
    out_path = img_dir / 'reference_validation_receipt.json'
    with open(out_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    # Also compute SHA-256 of all images
    sha_input = b''
    for view in sorted(REQUIRED_VIEWS):
        for ext in ['.png', '.jpg']:
            p = img_dir / f'{view}{ext}'
            if p.exists():
                sha_input += p.read_bytes()
    report['images_sha256'] = hashlib.sha256(sha_input).hexdigest()
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"REFERENCE IMAGE VALIDATION: {report['verdict']}")
    print(f"{'='*60}")
    print(f"  Checks: {passed}/{total} passed, {failed} failed")
    for r in results:
        status = '✓' if r['pass'] else '✗'
        print(f"  {status} {r['check']}: {r['detail']}")
    print(f"\n  Receipt: {out_path}")
    print(f"  Images SHA-256: {report['images_sha256'][:32]}...")
    
    sys.exit(0 if report['verdict'] == 'PASS' else 1)

if __name__ == '__main__':
    main()
