#!/usr/bin/env python3
"""Encode retargeted G1 clips into the primitive library."""
import json
import numpy as np


def encode_primitive(action, weapon, stance, source_id, features: np.ndarray, peak_idx: int):
    """Extract 4-frame peak window from features and emit RON snippet."""
    assert features.shape[1] == 414, features.shape
    window = features[peak_idx:peak_idx + 4]
    assert window.shape[0] == 4
    root = window[-1, :3]
    heading = np.arctan2(window[-1, 5], window[-1, 4])
    ron = f"""(
    action: {action},
    weapon: {weapon},
    stance: {stance},
    source_id: "{source_id}",
    feature_window: {json.dumps(window.tolist())},
    root_target: (position: [{root[0]:.6f}, {root[1]:.6f}, {root[2]:.6f}], heading: {heading:.6f}),
),"""
    return ron


if __name__ == "__main__":
    dummy = np.zeros((30, 414), dtype=np.float32)
    print(encode_primitive("Strike", "Longsword", "Top", "test", dummy, 10))
