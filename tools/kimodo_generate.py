#!/usr/bin/env python3
"""Batch-generate Kimodo motions from tools/data/kimodo_prompts.json.

Output path convention:
- The --output value passed to ``kimodo_gen`` is a stem without an extension.
- For a single sample (num_samples == 1), ``kimodo_gen`` writes ``<stem>.npz``.
- For multiple samples (num_samples > 1), ``kimodo_gen`` creates a directory
  ``<stem>/`` and writes files named ``<stem>_00.npz``, ``<stem>_01.npz``, etc.
"""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys


REQUIRED_CONFIG_KEYS = ("version", "model", "duration", "num_samples", "seed", "actions")


def run_kimodo(prompt: str, output: str, model: str, duration: float, num_samples: int, seed: int):
    cmd = [
        "kimodo_gen", prompt,
        "--model", model,
        "--duration", str(duration),
        "--num_samples", str(num_samples),
        "--seed", str(seed),
        "--output", output,
    ]
    print(shlex.join(cmd))
    subprocess.run(cmd, check=True)


def validate_config(cfg: dict, path: str):
    """Validate the configuration loaded from ``path``."""
    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in cfg]
    if missing:
        raise SystemExit(f"error: {path} is missing required key(s): {', '.join(missing)}")

    if not isinstance(cfg["actions"], dict):
        raise SystemExit(f"error: {path}: 'actions' must be an object")

    for action, action_cfg in cfg["actions"].items():
        if not isinstance(action_cfg, dict):
            raise SystemExit(f"error: {path}: action '{action}' must be an object")
        if "prompts" not in action_cfg:
            raise SystemExit(
                f"error: {path}: action '{action}' is missing required key 'prompts'"
            )
        if not isinstance(action_cfg["prompts"], list):
            raise SystemExit(f"error: {path}: action '{action}' prompts must be a list")


def main():
    parser = argparse.ArgumentParser(
        description="Batch-generate Kimodo motions from a JSON prompt config."
    )
    parser.add_argument(
        "--prompts",
        default="tools/data/kimodo_prompts.json",
        help="Path to the JSON prompt configuration file (default: %(default)s).",
    )
    parser.add_argument(
        "--out-dir",
        default="data/kimodo",
        help="Directory where generated motion stems will be written (default: %(default)s).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the stems that would be generated without invoking kimodo_gen.",
    )
    args = parser.parse_args()

    try:
        with open(args.prompts) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"error: prompt config not found: {args.prompts}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: failed to parse {args.prompts}: {exc}")

    validate_config(cfg, args.prompts)

    os.makedirs(args.out_dir, exist_ok=True)

    if not args.dry_run and shutil.which("kimodo_gen") is None:
        raise SystemExit(
            "error: 'kimodo_gen' was not found on PATH. "
            "Install or activate the Kimodo environment before running this script."
        )

    for action, action_cfg in cfg["actions"].items():
        for prompt_index, prompt in enumerate(action_cfg["prompts"]):
            out_stem = os.path.join(args.out_dir, f"{action.lower()}_{prompt_index:02d}")
            if args.dry_run:
                print(f"would generate: {action} prompt {prompt_index} -> {out_stem}")
                continue
            run_kimodo(
                prompt,
                out_stem,
                cfg["model"],
                cfg["duration"],
                cfg["num_samples"],
                cfg["seed"],
            )


if __name__ == "__main__":
    main()
