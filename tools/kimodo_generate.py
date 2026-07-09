#!/usr/bin/env python3
"""Batch-generate Kimodo motions from tools/data/kimodo_prompts.json."""
import argparse
import json
import os
import subprocess
import sys


def run_kimodo(prompt: str, output: str, model: str, duration: float, num_samples: int, seed: int):
    cmd = [
        "kimodo_gen", prompt,
        "--model", model,
        "--duration", str(duration),
        "--num_samples", str(num_samples),
        "--seed", str(seed),
        "--output", output,
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", default="tools/data/kimodo_prompts.json")
    parser.add_argument("--out-dir", default="data/kimodo")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(args.prompts) as f:
        cfg = json.load(f)

    os.makedirs(args.out_dir, exist_ok=True)

    for action, action_cfg in cfg["actions"].items():
        for pi, prompt in enumerate(action_cfg["prompts"]):
            out_stem = os.path.join(args.out_dir, f"{action.lower()}_{pi:02d}")
            if args.dry_run:
                print(f"would generate: {action} prompt {pi} -> {out_stem}")
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
