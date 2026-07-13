#!/usr/bin/env python3
"""CMU 14_02 retargeted G1 RAW SOURCE contact sheet for human visual gate.

This is a RAW G1 stick-figure inspection sheet, NOT a C0 render.
No combat truth, physics, or runtime wiring in scope.

Produces: context [100,220) with 24 ordered samples, side+top views,
highlighted [130,160) candidate region, root trajectory overlay.
"""

import sys
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.qa.visual_verify_primitives import parse_g1_frame, G1_NAMES

# --- Skeleton ---
G1_PARENTS = np.array([
    -1, 0, 1, 2, 3, 4, 5, 6, 0, 8, 9, 10, 11, 12, 13, 0, 15, 16, 17, 18,
    19, 20, 21, 22, 23, 24, 17, 26, 27, 28, 29, 30, 31, 32,
], dtype=np.int32)

BONE_COLOR = "#446688"
BONE_COLOR_HIGHLIGHT = "#CC4400"
TRAJECTORY_COLOR = "#334455"
TRAJECTORY_HIGHLIGHT = "#CC6600"
BG_COLOR = "#0a0c10"
TEXT_COLOR = "#ccddee"


def draw_skeleton(ax, positions, highlight=False):
    color = BONE_COLOR_HIGHLIGHT if highlight else BONE_COLOR
    lw = 1.8 if highlight else 1.0
    for i, p in enumerate(G1_PARENTS):
        if p >= 0:
            ax.plot(
                [positions[p, 0], positions[i, 0]],
                [positions[p, 1], positions[i, 1]],
                color=color, linewidth=lw, solid_capstyle="round",
            )


def draw_skeleton_top(ax, positions, highlight=False):
    color = BONE_COLOR_HIGHLIGHT if highlight else BONE_COLOR
    lw = 1.8 if highlight else 1.0
    for i, p in enumerate(G1_PARENTS):
        if p >= 0:
            ax.plot(
                [positions[p, 0], positions[i, 0]],
                [positions[p, 2], positions[i, 2]],
                color=color, linewidth=lw, solid_capstyle="round",
            )


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--carrier", required=True, type=Path, help="413.f32 context carrier")
    parser.add_argument("--output", required=True, type=Path, help="output PNG")
    parser.add_argument("--window-start", type=int, default=100, help="absolute start frame")
    parser.add_argument("--core-start", type=int, default=130, help="labeled candidate start")
    parser.add_argument("--core-end", type=int, default=160, help="labeled candidate end (exclusive)")
    parser.add_argument("--samples", type=int, default=24, help="number of samples to render")
    args = parser.parse_args()

    carrier_bytes = args.carrier.read_bytes()
    frames = np.frombuffer(carrier_bytes, dtype="<f4").reshape(-1, 413)
    N = frames.shape[0]
    assert N >= args.samples, f"carrier has {N} frames, need {args.samples}"

    # Parse all positions
    positions = np.stack([parse_g1_frame(f) for f in frames], axis=0)  # [N, 34, 3]
    root = positions[:, 0]  # [N, 3]

    # Sample evenly
    indices = np.linspace(0, N - 1, args.samples, dtype=int).tolist()
    abs_frames = [args.window_start + i for i in indices]

    # Compute global axis bounds
    x_min, x_max = root[:, 0].min(), root[:, 0].max()
    z_min, z_max = root[:, 2].min(), root[:, 2].max()
    y_min = min(positions[:, :, 1].min(), -0.15)
    y_max = max(positions[:, :, 1].max(), 0.05)
    x_margin = (x_max - x_min) * 0.15 + 0.3
    z_margin = (z_max - z_min) * 0.15 + 0.3
    y_margin = (y_max - y_min) * 0.1 + 0.15

    # Layout
    cols = 8
    rows = (args.samples + cols - 1) // cols
    fig_w = cols * 2.6
    fig_h = rows * 2.8

    fig, axes = plt.subplots(rows, cols, figsize=(fig_w, fig_h), facecolor=BG_COLOR)
    axes = axes.flatten() if hasattr(axes, "flatten") else [axes]

    for idx, (fi, af) in enumerate(zip(indices, abs_frames)):
        ax = axes[idx]
        ax.set_facecolor(BG_COLOR)
        is_core = args.core_start <= af < args.core_end

        # Side view (X-Y)
        draw_skeleton(ax, positions[fi], highlight=is_core)
        # Root dot
        ax.scatter(root[fi, 0], root[fi, 1], c=TRAJECTORY_HIGHLIGHT if is_core else TRAJECTORY_COLOR, s=12, zorder=3)
        ax.set_xlim(x_min - x_margin, x_max + x_margin)
        ax.set_ylim(y_min - y_margin, y_max + y_margin)
        ax.set_aspect("equal")
        ax.axis("off")

        # Frame label
        ax.set_title(f"f{af}", fontsize=7, color=TEXT_COLOR, pad=2)
        if is_core:
            ax.add_patch(Rectangle(
                (0, 0), 1, 1, transform=ax.transAxes,
                facecolor="#CC4400", alpha=0.10, zorder=0,
            ))

    # Hide unused axes
    for j in range(len(indices), len(axes)):
        axes[j].axis("off")

    # --- Second figure: top-down view with root trajectory ---
    fig2, ax_top = plt.subplots(figsize=(12, 10), facecolor=BG_COLOR)
    ax_top.set_facecolor(BG_COLOR)

    # Full root trajectory
    ax_top.plot(root[:, 0], root[:, 2], color=TRAJECTORY_COLOR, linewidth=0.8, alpha=0.7)

    # Core [130,160) highlighted
    core_rel_start = args.core_start - args.window_start
    core_rel_end = args.core_end - args.window_start
    if core_rel_start < N and core_rel_end <= N:
        ax_top.plot(
            root[core_rel_start:core_rel_end, 0],
            root[core_rel_start:core_rel_end, 2],
            color=TRAJECTORY_HIGHLIGHT, linewidth=2.0, alpha=0.9,
        )

    # Sample dots
    for fi, af in zip(indices, abs_frames):
        is_core = args.core_start <= af < args.core_end
        c = TRAJECTORY_HIGHLIGHT if is_core else TEXT_COLOR
        s = 30 if is_core else 15
        ax_top.scatter(root[fi, 0], root[fi, 2], c=c, s=s, zorder=3, edgecolors="none")
        ax_top.annotate(
            str(af), (root[fi, 0], root[fi, 2]),
            textcoords="offset points", xytext=(4, 4),
            fontsize=5, color=c, alpha=0.8,
        )

    # Start marker
    ax_top.scatter(root[0, 0], root[0, 2], c="#00CC66", s=50, marker="s", zorder=4, label="start")
    ax_top.annotate(f"f{args.window_start}", (root[0, 0], root[0, 2]),
                    textcoords="offset points", xytext=(6, -10), fontsize=7, color="#00CC66")

    ax_top.set_xlim(x_min - x_margin, x_max + x_margin)
    ax_top.set_ylim(z_min - z_margin, z_max + z_margin)
    ax_top.set_aspect("equal")
    max_disp = np.linalg.norm(root[:, [0, 2]] - root[0, [0, 2]], axis=1).max()
    ax_top.set_title(
        f"CMU 14_02 → G1 retargeted — context [{args.window_start},{args.window_start+N})  |  "
        f"core dodge [{args.core_start},{args.core_end})  |  "
        f"max XZ disp: {max_disp:.2f}m",
        fontsize=10, color=TEXT_COLOR, pad=10,
    )
    ax_top.set_facecolor(BG_COLOR)
    ax_top.tick_params(colors=TEXT_COLOR, labelsize=7)
    ax_top.grid(True, alpha=0.15, color=TEXT_COLOR)
    ax_top.set_xlabel("X (m)", fontsize=8, color=TEXT_COLOR)
    ax_top.set_ylabel("Z (m)", fontsize=8, color=TEXT_COLOR)

    fig.suptitle(
        f"CMU 14_02 → G1 retargeted inspection context [{args.window_start},{args.window_start+N})  "
        f"|  core dodge [{args.core_start},{args.core_end})  "
        f"|  {args.samples} ordered samples",
        fontsize=11, color=TEXT_COLOR, y=1.01,
    )
    fig.tight_layout()
    fig.savefig(args.output, dpi=150, facecolor=BG_COLOR, bbox_inches="tight")
    plt.close(fig)

    top_out = args.output.parent / f"{args.output.stem}_top.png"
    fig2.tight_layout()
    fig2.savefig(top_out, dpi=150, facecolor=BG_COLOR, bbox_inches="tight")
    plt.close(fig2)

    print(f"Side sheet: {args.output}")
    print(f"Top  sheet: {top_out}")


if __name__ == "__main__":
    main()
