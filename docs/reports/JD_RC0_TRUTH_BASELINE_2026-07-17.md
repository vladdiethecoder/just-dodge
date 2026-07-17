# JD-RC0-STEAM-VERTICAL-SLICE-MESH-DOCTOR-001 — Truth Baseline

Owned outcome: first honestly promotable, Steam-depot-ready Windows x64 vertical slice +
reusable ForgeLens Mesh Doctor. This document is the recorded executable truth baseline
required by Work Order §1 before any new quality claim is accepted. It records observed
facts only; it makes no promotion, readiness, or publication claim.

## 1. Source revision and dirty state

| Field | Value |
|---|---|
| Pinned baseline (work order) | `85d0b845f354996b39822efc05a49a683a4ae198` |
| Current HEAD | `76aec36391249c4cc9fe874da253a716e7f2bf19` |
| HEAD relative to baseline | baseline is ancestor of HEAD (`git merge-base --is-ancestor 85d0b84 HEAD` → true) |
| Delta baseline→HEAD | 1 commit `76aec36 fix: restore atomic ledger baseline reconciliation`; 1 file, 1 insertion, `.hermes/atomic_ledger.md` only. No source change. |
| Tracked dirty files | 0 (`git status --porcelain --untracked-files=no` → empty) |
| Untracked non-target files | 0 |
| Branch | `main` → `origin/main` (`git@github.com:vladdiethecoder/just-dodge.git`) |
| HEAD commit date | 2026-07-17 02:02:18 -0400 |

## 2. Toolchain and tool versions (recorded at baseline)

| Tool | Version |
|---|---|
| rustc | 1.96.0 (ac68faa20 2026-05-25) |
| cargo | 1.96.0 (30a34c682 2026-05-25) |
| CI rust toolchain | dtolnay/rust-toolchain@1.96.0 (matches local) |
| Rust targets installed | x86_64-pc-windows-gnu, x86_64-pc-windows-msvc, x86_64-unknown-linux-gnu, x86_64-unknown-linux-musl |
| Blender | 5.1.2 |
| Python | 3.14.6 |
| node | v24.3.0 (fnm) |
| Khronos glTF validator | gltf-validator@2.0.0-dev.3.10 (npm library, node runner) |
| mingw cross gcc | x86_64-w64-mingw32-gcc present (g++ NOT on PATH) |
| wine | wine + wine64 present; smoke test `int main(){return 42;}` → exit 42 (PE executes) |
| torch (baseline env) | 2.11.0+cu130, CUDA available |
| onnxruntime (python) | 1.26.0 |

## 3. Complete input/output hashes

Cooked runtime mesh inputs (sha256, observed):

```
36a9c4e41f7e33ff58d68c10aa59a6b6cdbfb7e0384e0402e520801c205a1c7e  assets/source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin
e1ba7788cafcb2a156ff2bcdcda4d24f1811c8d50fc2a9a7a5d18ac77919831d  assets/weapons/w0_sword_assembled.bin
d5de5def9d903c09b64b8ba73fc516737058bdb1bb222c8ee08e44e9272cc429  assets/arena_rock.bin
596633bda76d7fa3e663728f08d1f307eadbc34a5ace3d7198785ea2825c9d8f  assets/lintel_gate.bin
9889d31c3caa1158be2c3d184097e9653551db7a06a61f33a2a41cf54a8d117e  assets/rune_pillar.bin
```

MotionBricks ONNX runtime (13 pinned files): see `assets/motionbricks_runtime.sha256`.
`tools/hydrate_motionbricks_runtime.sh` verifies the full set against a trusted bundle
before hydration and re-verifies the hydrated destination. Interaction checkpoint present:
`assets/motion/pvp005_r6k/models/motionbricks_r6k_interaction.onnx` (+ `.verify.json`).

Deterministic truth reference (from `docs/reports/CURRENT_STATE_AUDIT.md`, prior revision):
100 replay reconstructions final truth hash `d1a3cc1bfb9c2f67`. Re-confirmed at HEAD by
the 100-replay test (PASS, below).

## 4. Current CI and release status (re-run at HEAD, observed)

| Gate | Command | Result |
|---|---|---|
| fmt | `cargo fmt --check` | PASS (exit 0) |
| clippy | `cargo clippy --locked --all-targets -- -D warnings` | PASS (exit 0) |
| check -Dwarnings | `RUSTFLAGS=-Dwarnings cargo check --locked --all-targets` | PASS (exit 0) |
| full test suite | `cargo test --locked --all-targets` | PASS — 144 lib + 156 integration + 2 doc + bin suites; 0 failed |
| determinism | `cargo test --locked --lib milestone3::tests::one_hundred_replay_reconstructions_keep_the_same_truth_hash` | PASS |
| glTF validation | node runner, gltf-validator@2.0.0-dev.3.10 | 5/5 GLB, **0 errors** (1 non-fatal NODE_SKINNED_MESH_NON_ROOT warning on c0_armored_duelist) |

GLB validation detail (errors/warnings/infos):
- c0_armored_duelist_001/model.glb: 0 err / 1 warn (skinned-mesh non-root) / 0 info
- c0_base_fighter/assembled_001/model.glb: 0 / 0 / 3
- c0_base_fighter/retopo_001/model.glb: 0 / 0 / 1
- e0_arena_threshold/assembled_001/model.glb: 0 / 0 / 111
- w0_sword/assembled_001/model.glb: 0 / 0 / 7

## 5. Quarantine status (Work Order §1)

- 162-example dynamic combat demo: **already quarantined** at baseline.
  - Notice: `docs/evidence_quarantine/DYNAMIC_COMBAT_DEMO_162_INVALID.md` (EXPLORATORY-ONLY, invalid for production admission).
  - Generator `tools/qa/dynamic_combat_demo.py` and `render_dynamic_combat_frames.py` carry QUARANTINED headers and write only to the ignored path `validation_evidence/quarantine/dynamic-combat-demo-162-invalid-exploratory-20260717/`.
  - Root cause of invalidity: synthetic in-process targets + hard-masked constraint values; zero foot/grip/hand errors are NOT independent forward-path conformance.
  - OPEN: quarantine is documentation + convention only. No CI gate yet rejects these artifacts as promotion evidence. Tracked under gate-repair work.

## 6. Known deficits carried forward (observed, not new claims)

1. **Live bind-pose fallback.** `App::current_pose()` (`src/main.rs:1131`) returns
   `c0_reference_skin` (static bind pose) for any action that is not Strike (hero_strike
   sample) or Move (c0_walk_skins). Confirmed by code and by
   `docs/reports/CURRENT_STATE_AUDIT.md` §Selected-path item 5. QA harness success does
   NOT imply live full-body animation.
2. **Python/PyO3 in the executable path.** `src/motion_service.rs` bridges to the Python
   `motionbricks_service` via PyO3 (`auto-initialize`). Cross-compile to Windows fails:
   `error: PYO3_CROSS_PYTHON_VERSION or an abi3-py3* feature must be specified when
   cross-compiling`. This violates the clean-directory constraint (no Python install) and
   "no generative model ships in the executable". Must be feature-gated out of the shipped
   binary; baked, validated motion ships instead.
3. **Windows packaging unverified.** Existing `tools/package_release.sh` is
   Linux-only (`x86_64-unknown-linux-gnu`). No Windows x64 depot package exists yet.
4. **Prior FAILs (from audit, still open):** canonical-media verifier absent; five human
   packaged matches absent; replay capture shows overlapping footer/Plan instructions
   (presentation acceptance fail-closed).

## 7. Honest scope note

This baseline records the verified starting state. The Windows x64 package, the
interaction-conditioned vertical Strike lane with actor/session/clip held-out split, the
ForgeLens Mesh Doctor, the CI gate-repair set, and the canonical release evidence are
forward work. The 1080p60 gameplay capture, 30-minute soak, and human owner approval are
hardware/HID/human-bound and cannot be produced by automated tooling alone; they are
tracked as external dependencies, not fabricated.

No artifact in this document is a promotion, readiness, or Steam-publication claim.
