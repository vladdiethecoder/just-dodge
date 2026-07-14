# MotionBricks ONNX Artifacts

This document describes the ONNX exports produced by `tools/export_motionbricks_onnx.py` and how they relate to the current runtime.

## What exists

The export script writes the following files under `assets/`:

| File | Purpose | Typical size |
|------|---------|--------------|
| `motionbricks_pose_backbone.onnx` | Wrapper graph for the pose token transformer. | ~150 KB |
| `motionbricks_pose_backbone.onnx.data` | External weights for the pose backbone. | ~520 MB |
| `motionbricks_root_backbone.onnx` | Wrapper graph for the root trajectory backbone. | ~1 MB |
| `motionbricks_root_backbone.onnx.data` | External weights for the root backbone. | ~130 MB |
| `motionbricks_vqvae_encoder.onnx` | VQVAE encoder + vector-quantization wrapper. | ~30 KB |
| `motionbricks_vqvae_encoder.onnx.data` | External weights for the encoder. | ~45 MB |
| `motionbricks_vqvae_decoder.onnx` | VQVAE decoder wrapper. | ~135 KB |
| `motionbricks_vqvae_decoder.onnx.data` | External weights for the decoder. | ~50 MB |
| `motionbricks_codebook.npy` | Quantization codebook extracted from the VQVAE. | small |

The current runtime bundle also requires `motionbricks_vqvae_decoder.fixed.onnx`, `motionbricks_pose_transformer.onnx`, `motionbricks_root_shared.onnx`, `motionbricks_root_conv.onnx`, their external-data siblings, and `motionbricks_codebook.npy`. `motionbricks_root_token.onnx` is loaded when present and is pinned in the same bundle.

The `.onnx` files are small ONNX graph wrappers; the actual parameters live in the sibling `.onnx.data` files. ONNX external-data format is used because the full weights are too large for Git.

## Relationship to the current runtime

The active Rust runtime validates and loads this ONNX/NPY bundle before it creates the M3 motion cache. Missing or hash-mismatched artifacts must block live match startup; there is no bind-pose fallback. Compilation itself does not embed the large files.

## Git tracking policy

- `*.onnx.data` files are **not tracked** in Git (ignored by `.gitignore`). The pose + root backbone `.data` files alone total roughly **650 MB**.
- The small `.onnx` wrapper files are also ignored by `.gitignore` (`motionbricks_*.onnx`) and are **not tracked**, because a wrapper without its `.onnx.data` file is useless on a fresh clone and would only cause confusion.
- The export script (`tools/export_motionbricks_onnx.py`) and this document **are tracked**, so anyone with the source checkpoints can regenerate the ONNX artifacts locally.
- `assets/motionbricks_runtime.sha256` is tracked and pins every byte required by the live runtime bundle.

## Hydrating a clean checkout

Point the fail-closed hydrator at an already trusted bundle directory. It verifies every source byte before copying, stages each file atomically, and verifies the destination again:

```bash
tools/hydrate_motionbricks_runtime.sh /path/to/trusted/motionbricks-assets
```

For an isolated checkout on the same workstation, the warm checkout can be the source:

```bash
MOTIONBRICKS_ARTIFACT_SOURCE=/path/to/warm-checkout/assets \
  tools/hydrate_motionbricks_runtime.sh
```

The hydrator never downloads an unpinned artifact and never accepts a partial bundle. Distribution packages must carry the verified bundle; publishing a durable remote cache is a separate release operation.

## Regenerating the ONNX artifacts

Set `MOTIONBRICKS_DIR` to the root of the MotionBricks training checkout and activate the Python environment that contains the MotionBricks dependencies and PyTorch, then run:

```bash
export MOTIONBRICKS_DIR=/run/media/vdubrov/Bulk-SSD/gr00t/motionbricks
source /run/media/vdubrov/Bulk-SSD/mb_venv/bin/activate
python3 tools/export_motionbricks_onnx.py
```

The script reads the trained checkpoints from `$MOTIONBRICKS_DIR/out` and writes the `.onnx` / `.onnx.data` pairs into `assets/`.

## Verifying the ONNX artifacts

Once generated, first verify the exact runtime bundle and then run the broader ONNX smoke test:

```bash
(cd assets && sha256sum --check motionbricks_runtime.sha256)
python3 tools/verify_onnx.py
```

This performs a quick ONNX Runtime inference smoke test on `motionbricks_pose_backbone.onnx` and `motionbricks_root_backbone.onnx`. `verify_onnx.py` also warns if the matching `.onnx.data` external-data file is missing, which is the most common failure mode on a fresh clone before regeneration.
