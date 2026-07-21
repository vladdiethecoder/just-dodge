#!/usr/bin/env python3
"""Validate the pinned PVP-005 visual contract and background selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "assets/qa/pvp005_visual_harness_v1.json"


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def srgb_channel_to_linear(value: int) -> float:
    encoded = value / 255.0
    if encoded <= 0.04045:
        return encoded / 12.92
    return ((encoded + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: list[int] | tuple[int, int, int]) -> float:
    red, green, blue = (srgb_channel_to_linear(value) for value in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(
    left: list[int] | tuple[int, int, int],
    right: list[int] | tuple[int, int, int],
) -> float:
    high, low = sorted((relative_luminance(left), relative_luminance(right)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def linear_rgb_to_oklab(rgb: list[int] | tuple[int, int, int]) -> tuple[float, float, float]:
    red, green, blue = (srgb_channel_to_linear(value) for value in rgb)
    l_value = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    m_value = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    s_value = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    l_root = math.copysign(abs(l_value) ** (1.0 / 3.0), l_value)
    m_root = math.copysign(abs(m_value) ** (1.0 / 3.0), m_value)
    s_root = math.copysign(abs(s_value) ** (1.0 / 3.0), s_value)
    return (
        0.2104542553 * l_root + 0.7936177850 * m_root - 0.0040720468 * s_root,
        1.9779984951 * l_root - 2.4285922050 * m_root + 0.4505937099 * s_root,
        0.0259040371 * l_root + 0.7827717662 * m_root - 0.8086757660 * s_root,
    )


def oklab_distance(
    left: list[int] | tuple[int, int, int],
    right: list[int] | tuple[int, int, int],
) -> float:
    a = linear_rgb_to_oklab(left)
    b = linear_rgb_to_oklab(right)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


def select_backgrounds(config: dict[str, object]) -> dict[str, object]:
    background = config["background"]
    palette = background["palette_srgb8"]
    samples = background["declared_prepass_samples_srgb8"]
    minimum = float(background["minimum_edge_contrast_ratio"])
    scored = []
    for name, rgb in palette.items():
        contrasts = {subject: contrast_ratio(rgb, value) for subject, value in samples.items()}
        distances = {subject: oklab_distance(rgb, value) for subject, value in samples.items()}
        scored.append(
            {
                "name": name,
                "rgb": rgb,
                "luminance": relative_luminance(rgb),
                "contrasts": contrasts,
                "oklab_distances": distances,
                "min_contrast": min(contrasts.values()),
                "min_oklab_distance": min(distances.values()),
            }
        )
    single = [entry for entry in scored if entry["min_contrast"] >= minimum]
    if single:
        selected = max(single, key=lambda entry: (entry["min_oklab_distance"], entry["min_contrast"]))
        return {"mode": "single", "single": selected["name"], "scores": scored}

    sample_luminances = [relative_luminance(value) for value in samples.values()]
    dark = [
        entry
        for entry in scored
        if entry["luminance"] < min(sample_luminances)
        and entry["contrasts"]["actor"] >= minimum
    ]
    light = [
        entry
        for entry in scored
        if entry["luminance"] > max(sample_luminances)
        and entry["contrasts"]["weapon"] >= minimum
    ]
    if not dark or not light:
        raise SystemExit("palette cannot supply required complementary dark/light backgrounds")
    dark_choice = max(dark, key=lambda entry: (entry["min_oklab_distance"], entry["contrasts"]["actor"]))
    light_choice = max(light, key=lambda entry: (entry["min_oklab_distance"], entry["contrasts"]["weapon"]))
    return {
        "mode": "paired",
        "dark": dark_choice["name"],
        "light": light_choice["name"],
        "scores": scored,
    }


def validate_config(config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text())
    if config.get("schema") != "just-dodge-pvp005-visual-harness-v1":
        raise SystemExit("unsupported PVP-005 visual harness schema")
    orbit = config["orbit"]
    if orbit["sheet_width_px"] != 2048 or orbit["sheet_height_px"] != 2048:
        raise SystemExit("orbit sheets must be exactly 2048x2048")
    if orbit["grid_columns"] != 4 or orbit["grid_rows"] != 4:
        raise SystemExit("orbit sheets must use a 4x4 grid")
    if orbit["tile_width_px"] * 4 != 2048 or orbit["tile_height_px"] * 4 != 2048:
        raise SystemExit("orbit tiles do not exactly fill the sheet")
    expected_angles = [index * 22.5 for index in range(16)]
    if orbit["azimuth_degrees"] != expected_angles:
        raise SystemExit("orbit azimuths must be exact 22.5-degree increments")
    if config["cadence"]["reveal_frame_indices"] != list(range(8)):
        raise SystemExit("visual harness must render the first eight Reveal frames")
    if config["cadence"]["human_gate_frame_indices"] != list(range(6)):
        raise SystemExit("human gate must use the first six Reveal frames")
    required_layers = {
        "beauty",
        "silhouette",
        "object_id",
        "normals",
        "depth",
        "wireframe",
        "skeleton",
        "hand_socket_alignment",
        "accumulated_weapon_path",
        "collision_proxy_overlay",
    }
    if set(config["layers"]) != required_layers:
        raise SystemExit("visual layer contract is incomplete or contains an undeclared layer")
    if config["required_scopes"] != ["candidate", "admitted", "live_runtime"]:
        raise SystemExit("candidate/admitted/live scopes must all be required")
    retired = config.get("status") == "retired_not_current_evidence"
    if retired:
        if config.get("runtime_admissible") is not False:
            raise SystemExit("retired visual contract cannot be runtime-admissible")
        retirement_path = ROOT / config["retirement_manifest"]
        retirement = json.loads(retirement_path.read_text())
        if retirement.get("runtime_admissible") is not False:
            raise SystemExit("visual-contract retirement manifest became runtime-admissible")
        retired_inputs = {entry["path"]: entry["sha256"] for entry in retirement["files"]}
    else:
        retired_inputs = {}
    retired_bound_inputs = []
    for name, receipt in config["bound_inputs"].items():
        path = ROOT / receipt["path"]
        if not path.is_file():
            if retired_inputs.get(receipt["path"]) == receipt["sha256"]:
                retired_bound_inputs.append(name)
                continue
            raise SystemExit(f"missing unretired bound visual input {name}: {receipt['path']}")
        if sha256(path) != receipt["sha256"]:
            raise SystemExit(f"bound visual input drift: {name}")
    selection = select_backgrounds(config)
    expected = config["background"]["expected_selection"]
    observed = {key: selection[key] for key in expected}
    if observed != expected:
        raise SystemExit(f"background selection drift: {observed} != {expected}")
    return {
        "config": config,
        "background_selection": selection,
        "retired": retired,
        "retired_bound_inputs": retired_bound_inputs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_config(args.config.resolve())
    if args.output:
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite visual contract report: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"PVP005_VISUAL_CONTRACT_SHA256={sha256(args.config.resolve())}")
    selection = result["background_selection"]
    print(
        "PVP005_BACKGROUND_SELECTION="
        + (selection["single"] if selection["mode"] == "single" else f"{selection['dark']}+{selection['light']}")
    )
    if result["retired"]:
        print(f"PVP005_RETIRED_BOUND_INPUTS={len(result['retired_bound_inputs'])}")
        print("PVP005_VISUAL_CONTRACT=PASS_RETIRED_BLOCKED")
        print("RUNTIME_ADMISSIBLE=false")
    else:
        print("PVP005_VISUAL_CONTRACT=PASS_CONFIG_ONLY")


if __name__ == "__main__":
    main()
