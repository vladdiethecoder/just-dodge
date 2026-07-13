#!/usr/bin/env python3
"""Find candidate peak frames for primitive encoding."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retarget_to_g1 import _parse_bvh, _forward_kinematics


def find_peak(bvh_path: str):
    text = Path(bvh_path).read_text()
    root, motion, frame_time = _parse_bvh(text)
    positions, rotations = _forward_kinematics(root, motion)
    T = motion.shape[0]

    # Find hand joints
    hand_names = [n for n in positions if 'hand' in n.lower()]
    if not hand_names:
        hand_names = [n for n in positions if 'wrist' in n.lower()]

    # Compute mean hand height per frame
    hand_y = np.mean(np.stack([positions[n][:, 1] for n in hand_names]), axis=0)
    max_frame = int(np.argmax(hand_y))
    min_frame = int(np.argmin(hand_y))

    # Also compute hand speed (norm of velocity)
    hand_pos = np.mean(np.stack([positions[n] for n in hand_names]), axis=0)
    hand_speed = np.linalg.norm(np.diff(hand_pos, axis=0), axis=1)
    max_speed_frame = int(np.argmax(hand_speed)) + 1

    print(f"{bvh_path}: T={T}")
    print(f"  max hand height frame={max_frame} y={hand_y[max_frame]:.3f}")
    print(f"  min hand height frame={min_frame} y={hand_y[min_frame]:.3f}")
    print(f"  max hand speed frame={max_speed_frame} speed={hand_speed[max_speed_frame-1]:.3f}")
    print(f"  hand_y range: {hand_y.min():.3f} - {hand_y.max():.3f}")


if __name__ == "__main__":
    for f in sys.argv[1:]:
        find_peak(f)
