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

Other helper ONNX files (`motionbricks_root_conv.onnx`, `motionbricks_root_token.onnx`, `motionbricks_root_shared.onnx`, `motionbricks_pose_transformer.onnx`, etc.) may also be present; they are experimental component-level exports and are not required by the current runtime.

The `.onnx` files are small ONNX graph wrappers; the actual parameters live in the sibling `.onnx.data` files. ONNX external-data format is used because the full weights are too large for Git.

## Relationship to the current runtime

The active Rust runtime currently loads the MotionBricks networks via **PyO3 + PyTorch checkpoints**, not these ONNX files. The ONNX exports are **optional, future artifacts** intended for a pure-Rust ONNX inference path. They are not built, loaded, or required by `cargo build`/`cargo run` today.

## Git tracking policy

- `*.onnx.data` files are **not tracked** in Git (ignored by `.gitignore`). The pose + root backbone `.data` files alone total roughly **650 MB**.
- The small `.onnx` wrapper files are also ignored by `.gitignore` (`motionbricks_*.onnx`) and are **not tracked**, because a wrapper without its `.onnx.data` file is useless on a fresh clone and would only cause confusion.
- The export script (`tools/export_motionbricks_onnx.py`) and this document **are tracked**, so anyone with the source checkpoints can regenerate the ONNX artifacts locally.

## Regenerating the ONNX artifacts

Set `MOTIONBRICKS_DIR` to the root of the MotionBricks training checkout and activate the Python environment that contains the MotionBricks dependencies and PyTorch, then run:

```bash
export MOTIONBRICKS_DIR=/run/media/vdubrov/Bulk-SSD/gr00t/motionbricks
source /run/media/vdubrov/Bulk-SSD/mb_venv/bin/activate
python3 tools/export_motionbricks_onnx.py
```

The script reads the trained checkpoints from `$MOTIONBRICKS_DIR/out` and writes the `.onnx` / `.onnx.data` pairs into `assets/`.

## Verifying the ONNX artifacts

Once generated, run:

```bash
python3 tools/verify_onnx.py
```

This performs a quick ONNX Runtime inference smoke test on `motionbricks_pose_backbone.onnx` and `motionbricks_root_backbone.onnx`. `verify_onnx.py` also warns if the matching `.onnx.data` external-data file is missing, which is the most common failure mode on a fresh clone before regeneration.
