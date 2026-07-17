#!/usr/bin/env python3
"""Fail-closed structural verifier for the R6K ForgeLens Motion Lab payload."""
import hashlib, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asset_review

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("assets/qa/pvp005_r6k_motion_lab.json")
raw = path.read_bytes()
data = asset_review.validate_motion_lab(json.loads(raw))
assert data["motionLabId"] == "pvp005-r6k-hero-strike-r2"
assert data["frameCount"] == 64 and data["fps"] == 30
assert [view["id"] for view in data["views"]] == ["kimodo-teacher", "ardy-proposal", "motionbricks-target", "physics-execution"]
assert [len(view["jointNames"]) for view in data["views"]] == [77, 27, 34, 24]
assert all(len(view["frames"]) == 64 and all(len(frame["joints"]) == len(view["jointNames"]) for frame in view["frames"]) for view in data["views"])
assert len(data["tracks"]["text"]) == 5
assert len(data["tracks"]["fullBody"]) == 5
assert len(data["tracks"]["root"]) == 16
assert len(data["tracks"]["endEffectors"]) == 32
assert len(data["tracks"]["contacts"]) == 32
assert all(len(metric["series"]) == 64 and all(math.isfinite(value) for value in metric["series"]) for metric in data["metrics"].values())
foot_drift_max = max(data["metrics"]["footDrift"]["series"])
grip_error_max = max(abs(value - 0.160) for value in data["metrics"]["grip"]["series"])
assert math.isfinite(foot_drift_max) and math.isfinite(grip_error_max)
assert set(data["lineage"]) == {"kimodoSha256", "ardySha256", "motionBricksSha256", "physicsSha256"}
print(json.dumps({"status": "PASS", "sha256": hashlib.sha256(raw).hexdigest(), "views": [view["id"] for view in data["views"]], "frames": data["frameCount"], "observedFootDriftMaxM": foot_drift_max, "observedGripErrorMaxM": grip_error_max}, sort_keys=True))
