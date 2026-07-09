# MotionBrains service for Just Dodge

This package wraps the GR00T MotionBricks pose/root/VQVAE models and exposes
`generate_clip(action, weapon, stance, context_frames, seed)` for the Rust
bridge.

## Environment variables

All paths default to a sibling `gr00t/motionbricks` checkout relative to the
project root:

| Variable | Default | Description |
|----------|---------|-------------|
| `MB_DIR` | `../gr00t/motionbricks` | GR00T MotionBricks checkout root |
| `CHECKPOINT_DIR` | `../gr00t/motionbricks/out` | Directory containing trained checkpoints |
| `SKELETON_XML` | `$MB_DIR/assets/skeletons/g1/g1.xml` | G1 skeleton description |
| `CLIP_CKPT` | `$CHECKPOINT_DIR/G1-clip.ckpt` | Clip-holder checkpoint |

Set these variables if your MotionBricks checkout lives elsewhere.

## Installing MotionBricks

`requirements.txt` does not pin an absolute path. Install MotionBricks from your
local checkout before running the service:

```bash
pip install /path/to/gr00t/motionbricks
```

## Quick check

```bash
python3 -c "from motionbricks_service.generate import init_service; print(init_service()['ready'])"
```
