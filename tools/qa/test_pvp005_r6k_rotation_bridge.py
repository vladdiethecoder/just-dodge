#!/usr/bin/env python3
"""Golden verifier for the unpromoted PVP005-R6K rotation bridge."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEACHER = ROOT / "assets/motion/pvp005_r6k/teacher/kimodo_teacher_strike.refined.soma77.npz"
BRIDGE = ROOT / "assets/motion/pvp005_r6k/bridge/kimodo_to_ardy_core27_to_c0.bridge.npz"
REPORT = ROOT / "assets/qa/pvp005_r6k_rotation_bridge_report.json"
C0 = ROOT / "assets/qa/pvp005_r6k_c0_skeleton.json"
SCRIPT = ROOT / "tools/qa/pvp005_r6k_rotation_bridge.py"
EXPECTED = {
    TEACHER: "c3412394684264381c8c3b5828f607c69878100d52cba0648cbb84aa75202ece",
    BRIDGE: "f519764263e87796323c421bb2d7b2df0674d9f9638c763f6a50076ba3d72c72",
    REPORT: "7e8f71deb52ead74d84983db5882d68b734457a58e4212ae7e7acc1de57b3e43",
    C0: "be6dd0fc3d5465d58ceb0e8deb4471c9d92ed20880de7ef508e68361d1b6e6db",
}
REQUIRED_ARRAYS = {
    "c0_local_col_major.npy",
    "c0_local_quat_xyzw.npy",
    "c0_world_col_major.npy",
    "core27_global.npy",
    "core27_joints_m.npy",
    "core27_local.npy",
    "core27_local_quat_xyzw.npy",
    "foot_contacts.npy",
    "global_root_heading_xz.npy",
    "root_positions_m.npy",
    "scaled_constraint_targets_m.npy",
    "soma30_global.npy",
    "soma30_joints_m.npy",
    "soma30_local.npy",
    "soma30_local_quat_xyzw.npy",
}


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1 << 20):
            result.update(block)
    return result.hexdigest()


def verify_static() -> None:
    for path, expected in EXPECTED.items():
        observed = digest(path)
        if observed != expected:
            raise AssertionError(f"{path}: {observed} != {expected}")
    report = json.loads(REPORT.read_text())
    assert report["status"] == "pass"
    assert report["teacher_sha256"] == EXPECTED[TEACHER]
    assert report["bridge_sha256"] == EXPECTED[BRIDGE]
    assert report["report_sha256"] == "e086457afe7e5899508d0226c448c1317585e05d59c698efc691ce7f0f1be77e"
    assert report["roundtrip_fk_endpoint_error_max_m"] < 0.010
    assert report["c0_hand_position_error_max_m"] < 0.010
    assert report["c0_grip_span_error_max_m"] < 0.010
    assert max(report["c0_hand_rotation_error_deg"].values()) <= 3.0
    assert max(report["c0_planted_foot_drift_m"].values()) < 0.010
    assert report["finite"] is True
    assert report["rotation_determinants"]["min"] > 0.999
    assert report["rotation_determinants"]["max"] < 1.001
    assert report["joint_limit_violations"] == []
    assert report["ardy_generation_authorized"] is False
    assert report["runtime_admitted"] is False
    assert report["promoted"] is False
    for item in report["quaternion_continuity"].values():
        assert item["postcanonical_min_consecutive_dot"] >= 0.0
    with zipfile.ZipFile(BRIDGE) as archive:
        assert set(archive.namelist()) == REQUIRED_ARRAYS


def recompute(python: Path, ardy_root: Path) -> None:
    outputs: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="pvp005-r6k-golden-") as temporary:
        temp = Path(temporary)
        for index in range(2):
            output = temp / str(index)
            subprocess.run(
                [
                    str(python),
                    str(SCRIPT),
                    "--teacher",
                    str(TEACHER),
                    "--c0",
                    str(C0),
                    "--ardy-root",
                    str(ardy_root),
                    "--output",
                    str(output),
                ],
                check=True,
                cwd=ROOT,
            )
            outputs.append(output)
        for name, golden in (
            ("kimodo_to_ardy_core27_to_c0.bridge.npz", BRIDGE),
            ("rotation_bridge_report.json", REPORT),
        ):
            first = outputs[0] / name
            second = outputs[1] / name
            assert first.read_bytes() == second.read_bytes(), f"non-deterministic {name}"
            assert first.read_bytes() == golden.read_bytes(), f"golden drift in {name}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument("--python", type=Path, default=Path("/home/vdubrov/Projects/kimodo-r6k-worker/.venv/bin/python"))
    parser.add_argument("--ardy-root", type=Path, default=Path("/home/vdubrov/Projects/ardy-r6k-693f74d"))
    args = parser.parse_args()
    verify_static()
    if args.recompute:
        recompute(args.python, args.ardy_root)
    print("PVP005_R6K_ROTATION_BRIDGE_GOLDEN_PASS")


if __name__ == "__main__":
    main()
