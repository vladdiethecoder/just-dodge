# Kimodo/BONES-SEED Motion Primitive Integration Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Generate a production-quality, MotionBricks-compatible primitive library for six combat actions using NVIDIA Kimodo-G1-SEED-v1, replacing the current CMU-only Strike/Idle primitives.

**Architecture:** Kimodo generates Unitree G1 skeleton motions from text prompts; a new Python converter maps Kimodo NPZ output to the same `[T, 414]` feature space used by CMU retargeting; the existing `encode_primitives.py` normalizes and writes `assets/data/primitives.ron`; visual QA verifies each primitive.

**Tech Stack:** Kimodo (PyTorch, diffusers-style inference), NumPy, MotionBricks `GlobalRootGlobalJoints`, existing `encode_primitives.py`, existing Rust integration tests.

---

## Current Context / Assumptions

- GPU: NVIDIA RTX 5090 with 32 GB VRAM, CUDA 13.0, PyTorch 2.11.0+cu130 already installed.
- MotionBrains service and Rust tests pass for the current CMU Strike/Idle primitives.
- Feature format expected by the runtime: `[T, 414]` composed of root_pos (3) + root_heading_cos/sin (2) + root-relative joint positions for joints 1..33 (99) + 34×6D rotations (204) + zero local_vel (102) + zero foot_contacts (4).
- `tools/extract_motion_features.py` already produces this format from `joint_positions [T,34,3]` and `joint_rotations [T,34,3,3]`.
- Kimodo-G1-SEED-v1 outputs NPZ with at least `posed_joints [T,J,3]`, `local_rot_mats [T,J,3,3]`, `root_positions [T,3]`, `global_root_heading [T,2]`.

---

### Task 1: Install Kimodo and download Kimodo-G1-SEED-v1

**Objective:** Make `kimodo_gen` callable and verify the G1 model downloads.

**Files:**
- Modify: `motionbricks_service/requirements.txt`
- Modify: `README.md` (add Kimodo setup notes)

**Step 1: Add Kimodo dependency**

In `motionbricks_service/requirements.txt`, append:

```text
kimodo @ git+https://github.com/nv-tlabs/kimodo.git
```

**Step 2: Install in the project environment**

Run:

```bash
python3 -m pip install -r motionbricks_service/requirements.txt
```

Expected: installs `kimodo` package and dependencies.

**Step 3: Smoke-test Kimodo CLI and download G1 model**

Run:

```bash
kimodo_gen "a person stands still" \
  --model Kimodo-G1-SEED-v1 \
  --duration 1.0 \
  --num_samples 1 \
  --seed 42 \
  --output /tmp/kimodo_smoke
```

Expected: creates `/tmp/kimodo_smoke.npz` (and possibly `/tmp/kimodo_smoke.csv`). First run downloads the model checkpoint (~2-4 GB).

**Step 4: Verify NPZ keys**

Run:

```bash
python3 - <<'PY'
import numpy as np
data = np.load('/tmp/kimodo_smoke.npz', allow_pickle=True)
print('keys:', list(data.keys()))
for k in data.keys():
    print(k, data[k].shape)
PY
```

Expected output shape for `posed_joints` is `[T, J, 3]` where J is the G1 joint count (likely 34 or 51). Record this for Task 3.

**Step 5: Commit**

```bash
git add motionbricks_service/requirements.txt README.md
git commit -m "deps: add Kimodo and document setup"
```

---

### Task 2: Create prompt catalog for six actions

**Objective:** Store text prompts and generation settings under version control.

**Files:**
- Create: `tools/data/kimodo_prompts.json`

**Step 1: Write prompt catalog**

```json
{
  "version": "2026-07-09",
  "model": "Kimodo-G1-SEED-v1",
  "duration": 1.2,
  "num_samples": 4,
  "seed": 20260709,
  "actions": {
    "Strike": {
      "prompts": [
        "two handed overhead longsword strike downward, planted feet",
        "powerful downward sword cut with longsword, two hands"
      ]
    },
    "Block": {
      "prompts": [
        "high sword block with longsword, two handed guard, brace",
        "parry an overhead strike, longsword raised"
      ]
    },
    "Thrust": {
      "prompts": [
        "forward longsword thrust, two handed, lunge step",
        "sword stab straight ahead with longsword"
      ]
    },
    "Grab": {
      "prompts": [
        "close quarters grapple, step in and grab torso",
        "unarmed tackle entry, arms wrapping around"
      ]
    },
    "Dodge": {
      "prompts": [
        "side step evasion, sword guard, lean away from attack",
        "dodge backward while holding longsword"
      ]
    },
    "Idle": {
      "prompts": [
        "standing guard with longsword, relaxed ready pose, breathing",
        "calm idle holding a longsword in both hands"
      ]
    }
  }
}
```

**Step 2: Validate JSON**

Run:

```bash
python3 -m json.tool tools/data/kimodo_prompts.json > /dev/null
```

Expected: no output (valid JSON).

**Step 3: Commit**

```bash
git add tools/data/kimodo_prompts.json
git commit -m "data: add Kimodo prompt catalog for six combat actions"
```

---

### Task 3: Implement Kimodo-to-MotionBricks converter

**Objective:** Convert Kimodo-G1 NPZ output into the `[T, 414]` feature array the runtime expects.

**Files:**
- Create: `tools/kimodo_to_motionbricks.py`

**Step 1: Write converter skeleton**

```python
#!/usr/bin/env python3
"""Convert Kimodo-G1 NPZ output to MotionBricks [T, 414] feature arrays."""
import argparse
import json
import numpy as np


def _g1_kimodo_to_skeleton34_indices() -> list[int]:
    """Map Kimodo-G1 joint order to G1Skeleton34 joint order.

    This is filled after inspecting the Kimodo NPZ joint names.
    Default identity mapping; update once names are known.
    """
    return list(range(34))


def _global_rot_mats_from_local(local_rot_mats: np.ndarray) -> np.ndarray:
    """Compute global rotation matrices from local (parent-relative) rotations."""
    T, J = local_rot_mats.shape[:2]
    global_rot = np.zeros((T, J, 3, 3), dtype=local_rot_mats.dtype)
    # Parent indices for G1Skeleton34. Verify against actual skeleton.
    parents = [
        -1, 0, 1, 2, 3, 0, 5, 6, 7, 0,
        9, 10, 11, 12, 13, 14, 11, 16, 17, 18,
        19, 11, 21, 22, 23, 11, 25, 26, 27, 28,
        11, 30, 31, 32,
    ]
    for t in range(T):
        for j in range(J):
            if parents[j] < 0:
                global_rot[t, j] = local_rot_mats[t, j]
            else:
                global_rot[t, j] = global_rot[t, parents[j]] @ local_rot_mats[t, j]
    return global_rot


def convert(npz_path: str, out_path: str):
    data = np.load(npz_path, allow_pickle=True)
    posed_joints = data["posed_joints"]      # [T, J, 3]
    local_rot_mats = data["local_rot_mats"]  # [T, J, 3, 3]

    # Map to G1Skeleton34 ordering.
    idx_map = _g1_kimodo_to_skeleton34_indices()
    posed_joints = posed_joints[:, idx_map, :]
    local_rot_mats = local_rot_mats[:, idx_map, :, :]

    global_rot_mats = _global_rot_mats_from_local(local_rot_mats)

    from tools.extract_motion_features import extract_features
    features = extract_features(posed_joints, global_rot_mats, fps=30)

    # Root-lock: remove root translation drift so VQVAE does not extrapolate.
    features[:, :2] = 0.0  # x, z root position
    features[:, 3:5] = 0.0  # cos/sin heading

    np.save(out_path, features.astype(np.float32))
    print(f"[kimodo_to_motionbricks] wrote {out_path} shape={features.shape}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("npz", help="Kimodo output NPZ")
    parser.add_argument("--out", required=True, help="Output .npy path")
    args = parser.parse_args()
    convert(args.npz, args.out)


if __name__ == "__main__":
    main()
```

**Step 2: Test on smoke output**

Run:

```bash
python3 tools/kimodo_to_motionbricks.py /tmp/kimodo_smoke.npz --out /tmp/kimodo_smoke_features.npy
```

Expected: prints shape `[T, 414]`.

**Step 3: Run shape assertion smoke test**

Run:

```bash
python3 - <<'PY'
import numpy as np
f = np.load('/tmp/kimodo_smoke_features.npy')
assert f.shape[1] == 414, f.shape
assert f.shape[0] % 4 == 0 or f.shape[0] >= 4, f.shape
print('OK', f.shape)
PY
```

Expected: `OK (T, 414)`.

**Step 4: Commit**

```bash
git add tools/kimodo_to_motionbricks.py
git commit -m "feat: add Kimodo-G1 to MotionBricks feature converter"
```

---

### Task 4: Implement batch Kimodo generator

**Objective:** Generate all prompts for all actions in one script, producing NPZs ready for conversion.

**Files:**
- Create: `tools/kimodo_generate.py`

**Step 1: Write batch generator**

```python
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
```

**Step 2: Dry-run to verify catalog parsing**

Run:

```bash
python3 tools/kimodo_generate.py --dry-run
```

Expected: prints 12 generation commands (2 prompts × 6 actions).

**Step 3: Commit**

```bash
git add tools/kimodo_generate.py
git commit -m "feat: add batch Kimodo motion generator"
```

---

### Task 5: Generate and convert all candidate motions

**Objective:** Produce `[T, 414]` `.npy` feature files for every prompt.

**Files:**
- Creates: `data/kimodo/*.npz`, `data/kimodo/*.npy`

**Step 1: Run batch generator (long-running)**

Run:

```bash
python3 tools/kimodo_generate.py --out-dir data/kimodo
```

Expected: creates `data/kimodo/strike_00.npz`, `data/kimodo/strike_01.npz`, etc., with `_00`, `_01` samples inside each folder. This may take 10-30 minutes depending on diffusion steps and sample count.

**Step 2: Convert each NPZ to features**

Run:

```bash
for npz in data/kimodo/*/*.npz data/kimodo/*.npz; do
  [ -f "$npz" ] || continue
  out="${npz%.npz}_features.npy"
  python3 tools/kimodo_to_motionbricks.py "$npz" --out "$out"
done
```

Expected: produces matching `_features.npy` files.

**Step 3: Commit generated artifacts (optional)**

If the generated files are small enough and redistributable:

```bash
git add data/kimodo/
git commit -m "data: generate Kimodo candidate motions and features"
```

If too large, add `data/kimodo/` to `.gitignore` and commit a README describing regeneration instead.

---

### Task 6: Extend encode_primitives.py for Kimodo features

**Objective:** Allow `encode_primitives.py` to read Kimodo `.npy` files and update the library.

**Files:**
- Modify: `tools/encode_primitives.py`

**Step 1: Add Kimodo batch mode**

Add a new CLI entry path in `main()`:

```python
    parser.add_argument("--kimodo-dir", help="Directory of Kimodo *_features.npy files to batch encode")
    parser.add_argument("--peak", type=int, default=15, help="Frame index of the peak 4-frame window")
```

After the existing smoke-test/encode branch, add:

```python
    if args.kimodo_dir:
        import glob
        features_files = sorted(glob.glob(os.path.join(args.kimodo_dir, "*_features.npy")))
        if not features_files:
            parser.error(f"no *_features.npy found in {args.kimodo_dir}")
        for feat_path in features_files:
            stem = os.path.basename(feat_path).replace("_features.npy", "")
            # Parse action from stem, e.g. "strike_00" -> action Strike.
            action_name = stem.split("_")[0].capitalize()
            # Validate action exists in our Action enum mapping.
            valid = {"Strike", "Block", "Thrust", "Grab", "Dodge", "Idle"}
            if action_name not in valid:
                print(f"[encode] skipping unrecognized stem {stem}")
                continue
            features = np.load(feat_path)
            if features.ndim != 2 or features.shape[1] != 414:
                print(f"[encode] skipping bad shape {features.shape} for {stem}")
                continue
            motion_rep = build_motion_rep()
            features_t = torch.from_numpy(features)
            features_norm = motion_rep.normalize(features_t).numpy()
            # Choose peak near middle of clip.
            peak = min(args.peak, features_norm.shape[0] - 4)
            primitive = encode_primitive(
                action_name, args.weapon or "Longsword", args.stance or "Top",
                f"kimodo_{stem}", features_norm, peak,
            )
            if os.path.exists(args.out):
                update_library(primitive, args.out, action_name, args.weapon or "Longsword", args.stance or "Top")
            else:
                create_library(primitive, args.out)
            print(f"[encode] added {action_name} from {stem}")
        return
```

Also add `--weapon` and `--stance` defaults in argparse if not already present.

**Step 2: Dry-run smoke test**

Run:

```bash
python3 tools/encode_primitives.py --smoke-test
```

Expected: prints a dummy primitive RON block.

**Step 3: Commit**

```bash
git add tools/encode_primitives.py
git commit -m "feat: batch-encode Kimodo features into primitives.ron"
```

---

### Task 7: Encode selected primitives into primitives.ron

**Objective:** Replace CMU Strike/Idle with Kimodo-backed versions and add new actions.

**Files:**
- Modify: `assets/data/primitives.ron`

**Step 1: Backup existing library**

```bash
cp assets/data/primitives.ron assets/data/primitives.ron.cmu_backup
```

**Step 2: Encode Kimodo features**

```bash
python3 tools/encode_primitives.py \
  --kimodo-dir data/kimodo \
  --weapon Longsword --stance Top \
  --out assets/data/primitives.ron
```

Expected: updates or appends one primitive per `_features.npy` file.

**Step 3: Inspect generated RON**

```bash
head -30 assets/data/primitives.ron
```

Expected: contains Kimodo `source_id` entries and 414-dim feature windows.

**Step 4: Commit**

```bash
git add assets/data/primitives.ron
git commit -m "data: replace primitive library with Kimodo-backed six-action set"
```

---

### Task 8: Run integration tests and visual QA

**Objective:** Verify the new primitives decode correctly in Rust and look reasonable as stick figures.

**Files:**
- Test: `tests/motion_service_integration.rs`
- QA: `tools/qa/visual_verify_primitives.py`

**Step 1: Run Rust integration tests**

```bash
cargo test --test motion_service_integration -- --nocapture
```

Expected: `2 passed; 0 failed`. If Strike test fails because source_id changed, update the test to use a Kimodo source_id or add an Idle test.

**Step 2: Run visual QA**

```bash
python3 tools/qa/visual_verify_primitives.py
```

Expected: generates `qa_runs/visual_primitives_*/` with readable stick figures. All actions should show root_path ≈ 0.0 m.

**Step 3: Inspect QA report**

```bash
cat qa_runs/visual_primitives_*/report.json
```

Expected: every action has finite frames, root_path 0.0, max velocity in reasonable range.

**Step 4: If tests fail, debug**

- If VQVAE decode explodes: pick a different `--peak` or normalize root-locking more aggressively.
- If stick figure is unreadable: regenerate with tighter prompts or select a different sample index.
- If Rust tests fail on deterministic length: adjust seed or check that `motion_service.py` still maps source_id correctly.

**Step 5: Commit fixes**

```bash
git add -A
git commit -m "test: verify Kimodo primitives pass integration and visual QA"
```

---

### Task 9: Update mocap manifest and documentation

**Objective:** Record provenance and license for the new Kimodo-generated primitives.

**Files:**
- Modify: `tools/data/mocap_manifest.json`
- Modify: `docs/MOTIONBRICKS-RETARGETING.md` (or create `docs/KIMODO-PRIMITIVES.md`)

**Step 1: Add Kimodo source entry to manifest**

```json
{
  "id": "kimodo_g1_seed",
  "name": "NVIDIA Kimodo G1 SEED v1",
  "url": "https://github.com/nv-tlabs/kimodo",
  "license": "NVIDIA Open Model License",
  "license_url": "https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/",
  "redistributable": true,
  "raw_format": "npz",
  "local_path": "data/kimodo",
  "actions": ["Strike", "Block", "Thrust", "Grab", "Dodge", "Idle"],
  "weapons": ["Longsword"],
  "retargeted": false,
  "retargeted_path": "",
  "provenance": {
    "model": "Kimodo-G1-SEED-v1",
    "training_data": "BONES-SEED",
    "dataset_license": "CC BY 4.0",
    "generated_with": "tools/kimodo_generate.py",
    "converted_with": "tools/kimodo_to_motionbricks.py"
  },
  "rationale": "Text-conditioned kinematic motion diffusion on the Unitree G1 skeleton. Generates diverse combat primitives without hunting for specific mocap clips. Deterministic seeds keep the build reproducible.",
  "clips": []
}
```

**Step 2: Document the pipeline**

Create `docs/KIMODO-PRIMITIVES.md`:

```markdown
# Kimodo Primitive Pipeline

## Quick regenerate

```bash
python3 -m pip install -r motionbricks_service/requirements.txt
python3 tools/kimodo_generate.py --out-dir data/kimodo
python3 tools/kimodo_to_motionbricks_all.py  # or shell loop
python3 tools/encode_primitives.py --kimodo-dir data/kimodo --weapon Longsword --stance Top
python3 tools/qa/visual_verify_primitives.py
```

## License

- Kimodo code: Apache-2.0
- Kimodo-G1-SEED-v1 checkpoint: NVIDIA Open Model License
- BONES-SEED dataset annotations: CC BY 4.0
```

**Step 3: Commit**

```bash
git add tools/data/mocap_manifest.json docs/KIMODO-PRIMITIVES.md
git commit -m "docs: document Kimodo primitive provenance and regeneration"
```

---

### Task 10: Final verification

**Objective:** Confirm the milestone gates are met.

**Commands:**

```bash
cargo test --test motion_service_integration -- --nocapture
python3 tools/qa/visual_verify_primitives.py
```

**Expected:**
- Rust: `2 passed; 0 failed`
- QA: all six actions produce readable keyframes with `root_path = 0.0 m`

**Success criteria checklist:**
- [ ] `assets/data/primitives.ron` contains six distinct Kimodo-backed actions.
- [ ] No procedural fallbacks are used.
- [ ] Integration tests pass.
- [ ] Visual QA passes.
- [ ] `tools/data/mocap_manifest.json` records Kimodo provenance.

**Step: Final commit**

```bash
git add -A
git commit -m "feat: complete Kimodo/BONES-SEED primitive integration milestone"
```

---

## Notes for Implementers

- If Kimodo-G1 joint ordering differs from G1Skeleton34, update `_g1_kimodo_to_skeleton34_indices()` in Task 3 before encoding.
- If generation is slow, reduce `--num_samples` to 2 in `kimodo_prompts.json` during development, then raise to 4 for final selection.
- Keep the CMU backup (`assets/data/primitives.ron.cmu_backup`) until QA passes; delete it in Task 10 if everything is green.
