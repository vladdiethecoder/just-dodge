#!/usr/bin/env python3
"""Encode six root-locked CMU segments into the primitive library."""
import os
import sys

import numpy as np
import pyron
import torch

# Make tools/ importable so we can reuse encode_primitives helpers.
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from encode_primitives import build_motion_rep, encode_primitive, format_library


SEGMENTS = [
    ("data/cmu_segments/113_21_30_150_idle_features.npy", "Idle", "cmu_113_21_30_150", 58),
    ("data/cmu_segments/02_07_80_105_strike_features.npy", "Strike", "cmu_02_07_80_105", 12),
    ("data/cmu_segments/02_07_190_215_block_features.npy", "Block", "cmu_02_07_190_215", 12),
    ("data/cmu_segments/14_01_530_545_thrust_features.npy", "Thrust", "cmu_14_01_530_545", 7),
    ("data/cmu_segments/14_01_1200_1235_grab_features.npy", "Grab", "cmu_14_01_1200_1235", 17),
    ("data/cmu_segments/14_02_130_160_dodge_features.npy", "Dodge", "cmu_14_02_130_160", 13),
]

WEAPON = "Longsword"
STANCE = "Top"
OUT_PATH = "assets/data/primitives.ron"


def _normalize_identifier(value) -> str:
    """Return a plain lower-case string for a RON identifier or string value."""
    name = str(value).strip()
    if name.endswith("()"):
        name = name[:-2]
    return name.lower()


def _load_existing_primitives(out_path: str) -> list[dict]:
    """Load existing primitives from a RON library file, if one exists."""
    if not os.path.exists(out_path):
        return []
    with open(out_path, "r", encoding="utf-8") as f:
        data = pyron.loads(f.read(), preserve_structs=True)
    primitives = list(data.get("primitives", []))
    # Normalize pyron identifier objects back to plain strings.
    for p in primitives:
        for key in ("action", "weapon", "stance"):
            if key in p:
                p[key] = str(p[key]).rstrip("()")
    return primitives


def main():
    """Encode the six CMU segments and merge them into the primitive library."""
    project_root = os.path.dirname(_TOOLS_DIR)
    out_path = os.path.join(project_root, OUT_PATH)
    motion_rep = build_motion_rep()

    new_primitives = []
    for rel_path, action, source_id, peak in SEGMENTS:
        feature_path = os.path.join(project_root, rel_path)
        if not os.path.exists(feature_path):
            raise FileNotFoundError(
                f"Segment file not found: {feature_path} (referenced as {rel_path})"
            )

        features = np.load(feature_path, allow_pickle=False)
        if features.ndim != 2 or features.shape[1] != 414:
            raise ValueError(f"{rel_path}: expected shape [T, 414], got {features.shape}")
        if peak < 0 or peak + 4 > features.shape[0]:
            raise ValueError(
                f"{rel_path}: peak window [{peak}, {peak + 4}) exceeds bounds (T={features.shape[0]})"
            )

        features_t = torch.from_numpy(features)
        features_norm = motion_rep.normalize(features_t).numpy()

        primitive = encode_primitive(
            action, WEAPON, STANCE, source_id, features_norm, peak
        )
        new_primitives.append(primitive)
        print(f"[encode] {action:6s} from {source_id} (peak={peak})")

    # Merge the six new primitives into the existing library (if any) by key.
    primitives = _load_existing_primitives(out_path)
    new_keys = {
        (p["action"].lower(), p["weapon"].lower(), p["stance"].lower())
        for p in new_primitives
    }

    merged = list(new_primitives)
    for existing in primitives:
        key = (
            _normalize_identifier(existing["action"]),
            _normalize_identifier(existing["weapon"]),
            _normalize_identifier(existing["stance"]),
        )
        if key not in new_keys:
            merged.append(existing)

    library_text = format_library(
        merged,
        generator_name="tools/encode_cmu_segments.py",
    )
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(library_text)

    # Verify the generated library.
    data = pyron.loads(library_text, preserve_structs=True)
    loaded_primitives = list(data.get("primitives", []))
    expected_actions = {action for _, action, _, _ in SEGMENTS}
    loaded_actions = {str(p["action"]).rstrip("()") for p in loaded_primitives}

    if len(loaded_primitives) != 6:
        raise RuntimeError(f"Expected 6 primitives, got {len(loaded_primitives)}")
    if loaded_actions != expected_actions:
        raise RuntimeError(
            f"Primitive actions mismatch: expected {expected_actions}, got {loaded_actions}"
        )
    for p in loaded_primitives:
        window = p["feature_window"]
        if len(window) != 4 or len(window[0]) != 414:
            first_row_len = len(window[0]) if window else 0
            raise RuntimeError(
                f"feature_window for {p['action']} has shape "
                f"[{len(window)}, {first_row_len}], expected [4, 414]"
            )

    print(f"[encode] wrote {len(merged)} primitives to {out_path}")


if __name__ == "__main__":
    main()
