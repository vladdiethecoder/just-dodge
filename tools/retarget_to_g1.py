#!/usr/bin/env python3
"""Retarget a source FBX/BVH clip to G1Skeleton34 and export numpy features."""
import json
import numpy as np


def load_retarget_map():
    with open("tools/data/g1_retarget_map.json") as f:
        return json.load(f)


def retarget(source_path: str, source_format: str, out_path: str):
    """TODO: implement with pymuscle/bvh parser + FK retargeting."""
    raise NotImplementedError("retargeting implementation follows mocap acquisition")


if __name__ == "__main__":
    print("Retarget map loaded:", load_retarget_map()["g1_skeleton"]["joint_count"], "joints")
