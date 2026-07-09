# Motion Capture Provenance

This document records the licenses and redistribution rules for every motion
capture source used by Just Dodge. MotionBricks is the sole animation engine;
all combat primitives are derived from retargeted mocap, not prebaked clips.

## Sources

See `tools/data/mocap_manifest.json` for the machine-readable manifest and
`tools/data/mocap_manifest_schema.json` for its schema.

| Source | License | Redistributable | Notes |
|--------|---------|-----------------|-------|
| CMU MoCap Boxing and Kicking | CC-BY-4.0 | **Yes** | Raw `.c3d` files may be kept in the repo with attribution. |
| Mixamo Sword/Shield Pack | Adobe Standard EULA | **No** | Embedded in-game use is permitted; raw FBX files must stay outside the repo. |
| MoCap Online Ninja Sword Pack | Commercial (purchased seat) | **No** | Raw and retargeted files must stay outside the repo; only the derived primitive metadata may be committed if the license allows. |

## Redistribution Policy

- Only **CMU** data can be stored in this repository in raw or retargeted form.
- Non-redistributable sources (Mixamo, MoCap Online) must be kept outside the
  repository. Any primitive derived from them must reference the source `id` and
  `license` fields so provenance is preserved.
- Every committed retargeted clip or primitive must include a `source_id` field
  that maps back to an entry in `tools/data/mocap_manifest.json`.
