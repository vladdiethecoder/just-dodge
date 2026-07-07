# File Inventory Audit — Just Dodge

## Purpose

This document records the sequential repository review performed for the architecture/systems/planning documentation pass. It exists so later work can see what was inspected and what architectural facts were extracted.

No code changes were made for this audit. Binary/image/FBX files were inspected by file type/metadata and, where applicable, by custom verifier output. Text/source files were read directly.

## Review Commands / Methods

- Repository inventory: `git status --short`, `git ls-files`, `git ls-files --others --exclude-standard`.
- Text/source inspection: `read_file` per file.
- Binary/image/FBX inspection: `file <path>` per file.
- Static mesh header inspection: one-file-at-a-time Python header read.
- SKM1/ANM1 verification: `python3 tools/verify_skinned_bin.py ...` per character set.

## Global State Observed

At review time:

- Branch: `clean-master`.
- Existing modified code files before this documentation pass included `Cargo.toml`, `src/asset.rs`, `src/main.rs`, `src/motion.rs`, `src/renderer.rs`.
- Existing untracked files included `assets/characters/`, `docs/.temp4/`, `src/skin.wgsl`, `tools/extract_fbx_skinned.py`, `tools/verify_skinned_bin.py`.
- This pass only writes documentation files.

## Root Files

| File | Review Signal | Architecture/System Notes |
|---|---|---|
| `.gitignore` | read directly | Ignores `target`, generated ONNX/NPY MotionBricks artifacts, zips, `__pycache__`; generated runtime artifacts must be reproducible outside git. |
| `.hermes/plans/2026-07-06_201500-motionbricks-inference-pipeline.md` | read directly | Detailed prior MotionBricks ONNX/Rust integration plan; useful but partially stale against current code. |
| `Cargo.toml` | read directly | Rust 2024, winit 0.30, wgpu 30.0, ort 2.0.0-rc.12 CUDA/load-dynamic, ndarray/anyhow; confirms custom Rust/wgpu path. |
| `README.md` | read directly | Stale status says code-empty/pre-production even though repo now contains engine/render/motion code. |

## Static Runtime Assets in `assets/`

| File | Review Signal | Notes |
|---|---|---|
| `assets/arena_rock.bin` | `file`; header parsed | static binary mesh; 209,869 vertices, 1,259,202 indices, 11,752,624 bytes. |
| `assets/arena_rock_0.jpg` | `file` | JPEG 4096×4096 RGB. |
| `assets/arena_rock_0.png` | `file` | PNG 4096×4096 RGB. |
| `assets/arena_rock_1.jpg` | `file` | JPEG 2048×2048 RGB. |
| `assets/arena_rock_1.png` | `file` | PNG 2048×2048 grayscale. |
| `assets/arena_rock_2.jpg` | `file` | JPEG 4096×4096 RGB. |
| `assets/arena_rock_2.png` | `file` | PNG 4096×4096 RGB. |
| `assets/arena_rock_3.jpg` | `file` | JPEG 2048×2048 RGB. |
| `assets/lintel_gate.bin` | `file`; header parsed | static binary mesh; 116,218 vertices, 697,428 indices, 6,508,696 bytes. |
| `assets/lintel_gate_0.jpg` | `file` | JPEG 4096×4096 RGB. |
| `assets/lintel_gate_1.jpg` | `file` | JPEG 2048×2048 RGB. |
| `assets/lintel_gate_2.jpg` | `file` | JPEG 4096×4096 RGB. |
| `assets/lintel_gate_3.jpg` | `file` | JPEG 2048×2048 RGB. |
| `assets/mannequin_male.bin` | `file`; header parsed | static binary mesh; 40,654 vertices, 244,308 indices, 2,278,168 bytes. |
| `assets/mannequin_male_0.png` | `file` | PNG 4096×4096 RGBA. |
| `assets/rune_pillar.bin` | `file`; header parsed | static binary mesh; 184,033 vertices, 1,104,741 indices, 10,308,028 bytes. |
| `assets/rune_pillar_0.jpg` | `file` | JPEG 4096×4096 RGB. |
| `assets/rune_pillar_1.jpg` | `file` | JPEG 2048×2048 RGB. |
| `assets/rune_pillar_2.jpg` | `file` | JPEG 4096×4096 RGB. |
| `assets/rune_pillar_3.jpg` | `file` | JPEG 2048×2048 RGB. |

## Untracked Character Runtime Assets in `assets/characters/`

| File | Review Signal | Notes |
|---|---|---|
| `assets/characters/mannequin_female.bin` | `file`; verifier | SKM1 verified: 163,211 vertices, 871,596 indices, 24 bones, weight sums valid, 1.551 game-unit height. |
| `assets/characters/mannequin_female_dummy.bin` | `file`; verifier | SKM1 verified: 163,211 vertices, 871,596 indices, 24 bones, weight sums valid, 1.551 game-unit height. |
| `assets/characters/mannequin_female_merged.anim` | `file`; verifier with female bin | ANM1 verified: 24 bones, 30 fps, 39 frames, 24/24 moving bones. |
| `assets/characters/mannequin_male.bin` | `file`; verifier | SKM1 verified: 68,107 vertices, 244,308 indices, 24 bones, weight sums valid, 1.556 game-unit height. |
| `assets/characters/mannequin_male_dummy.bin` | `file`; verifier | SKM1 verified: 68,107 vertices, 244,308 indices, 24 bones, weight sums valid, 1.556 game-unit height. |
| `assets/characters/mannequin_male_running.anim` | `file`; verifier with male bin | ANM1 verified: 24 bones, 60 fps, 39 frames, 24/24 moving bones. |

## Raw Planning Fragments in `docs/.temp/`

| File | Review Signal | Notes |
|---|---|---|
| `docs/.temp/file.txt` | read directly | MotionBricks backend, retargeting, injury, physics, render layer diagram. |
| `docs/.temp/file(1).txt` | read directly | 29-joint MotionBricks to richer mannequin bone mapping. |
| `docs/.temp/file(2).txt` | read directly | Motion clip CSV/runtime export shape. |
| `docs/.temp/file(3).txt` | read directly | Per-frame motion output shape: rotations, root velocities, keypoints. |
| `docs/.temp/file.cpp` | read directly | Pseudocode for MotionBricks sidecar query and retargeting/injury loop. |

## Raw Armor Planning Fragments in `docs/.temp2/`

| File | Review Signal | Notes |
|---|---|---|
| `docs/.temp2/file(1).cpp` | read directly | Conceptual `ArmorPiece` schema. |
| `docs/.temp2/file(4).txt` | read directly | Armor slots/body regions/bones covered. |
| `docs/.temp2/file(5).txt` | read directly | Material resistance matrix. |
| `docs/.temp2/file(6).txt` | read directly | Weapon damage types. |
| `docs/.temp2/file(7).txt` | read directly | Integrity states and degradation triggers. |
| `docs/.temp2/file(8).txt` | read directly | Armor class weight/stamina/speed/ROM table. |
| `docs/.temp2/file(9).txt` | read directly | ROM restrictions by armor piece. |
| `docs/.temp2/file(10).txt` | read directly | Material noise/detection range. |
| `docs/.temp2/file(11).txt` | read directly | Critical hit zone consequences. |
| `docs/.temp2/file(12).txt` | read directly | Loadout class philosophy/simulation identity. |

## Raw Material/Armor Simulation Fragments in `docs/.temp3/`

| File | Review Signal | Notes |
|---|---|---|
| `docs/.temp3/file.txt` | read directly | Material strength/density/behavior table. |
| `docs/.temp3/file(1).txt` | read directly | Cloth/silk PBD behavior. |
| `docs/.temp3/file(2).txt` | read directly | Leather mass-spring/plasticity behavior. |
| `docs/.temp3/file(3).txt` | read directly | Chainmail rigid-body constraint network behavior. |
| `docs/.temp3/file(4).txt` | read directly | Plate FEM behavior. |
| `docs/.temp3/file(5).txt` | read directly | Rune-Marble brittle fracture/Voronoi behavior. |
| `docs/.temp3/file(6).txt` | read directly | Warden bone brittle organic behavior. |
| `docs/.temp3/file(7).txt` | read directly | Armor resolution pipeline. |
| `docs/.temp3/file(8).txt` | read directly | Recommended simulation stack. |
| `docs/.temp3/file(9).txt` | read directly | Material visual state progression. |

## Raw Persistent Armor Damage Fragments in `docs/.temp4/`

| File | Review Signal | Notes |
|---|---|---|
| `docs/.temp4/file.txt` | read directly earlier; unchanged on recheck | Armor spawns pristine then records combat events visually. |
| `docs/.temp4/file(1).txt` | read directly earlier; unchanged on recheck | Trigger/material/result table for physical armor damage. |
| `docs/.temp4/file(2).txt` | read directly earlier; unchanged on recheck | Shader/state writes for impacts, dents, blood, dirt, burns. |
| `docs/.temp4/file(3).txt` | read directly earlier; unchanged on recheck | Integrity/visual/physics behavior state bands. |
| `docs/.temp4/file(4).txt` | read directly earlier; unchanged on recheck | Persistent armor state arrays and implications. |

## Existing Documentation Files

| File | Review Signal | Notes |
|---|---|---|
| `docs/ARMOR-DAMAGE-SYSTEM.md` | read directly | Deep armor design with persistent damage state and material behavior. |
| `docs/CHECKLIST.md` | read directly | Master development checklist; now references persistent damage records. |
| `docs/COMBAT-SYSTEM.md` | read directly | 13-action intent, resolver outputs, injury, armor handoff, AI/replay/truth isolation. |
| `docs/ENGINE-SKELETON.md` | read directly | Minimal shape prototype engine plan; narrower than current source baseline. |
| `docs/GDD.md` | read directly | Core game design, 13 actions, localized injury, modes, armor identities. |
| `docs/LESSONS-FROM-OATHYARD.md` | read directly | Truth isolation, renderer-driven trap, player mode, AI, executable-first principles. |
| `docs/MILESTONES.md` | read directly | Milestones; includes stale Godot reference for Milestone 2. |
| `docs/MOTIONBRICKS-RETARGETING.md` | read directly | MotionBricks retargeting plan and truth isolation requirements. |
| `docs/PROTOTYPES.md` | read directly | Prototype sequence from paper triangle to network rollback. |
| `docs/RISK-REGISTER.md` | read directly | Active risks: scope, engine expansion, determinism, assets, camera, placeholder UI, MotionBricks, armor. |
| `docs/ROADMAP.md` | read directly | Stage roadmap to launch/live ops; needs expansion for current architecture and QA. |
| `docs/TECH-STACK.md` | read directly | Custom Rust/wgpu stack, architecture layers, deterministic contract, asset pipeline, tooling. |
| `docs/reports/PROTOTYPE_01_PAPER_YOMI_PLAN.md` | read directly | Paper prototype plan. |
| `docs/reports/PROTOTYPE_02_SHAPE_PROTOTYPE_PLAN.md` | read directly | Shape prototype plan. |

## Source Files

| File | Review Signal | Notes |
|---|---|---|
| `src/asset.rs` | read directly | Static mesh loader, SKM1/ANM1 loader, G1-to-mannequin retarget map, skin matrices. Potential static `.bin` layout mismatch with extraction scripts. |
| `src/combat.rs` | read directly | Strike/Block/Grab MotionBricks action profiles, local/global root constraints, replanning tests. Not yet full authoritative resolver. |
| `src/input.rs` | read directly | Z/X/C action mapping through winit logical keys. |
| `src/main.rs` | read directly | ApplicationHandler shell, Vulkan backend, orbital camera, render loop, MotionBricks clip generation and skin joint upload. |
| `src/motion.rs` | read directly | ort v2 sessions, codebook NPY loader, quantize/dequantize, VQVAE autoencode/decode, G1 frame parser, synthetic idle encoder input. |
| `src/renderer.rs` | read directly | Static mesh pipeline, skinned pipeline, checkerboard ground, object config, texture loading, skinned mannequin resource setup. |
| `src/shader.wgsl` | read directly | Static textured shader with MVP, UVs, simple directional light. |
| `src/skin.wgsl` | read directly | Skinned shader using 24 joint matrices; untracked but referenced by renderer. |

## Source Asset Files in `src/assets/Meshy_AI_Male_Combat_Mannequin_biped/`

| File | Review Signal | Notes |
|---|---|---|
| `..._Animation_Running_frame_rate_60.fbx` | `file` | Kaydara FBX v7400. |
| `..._Animation_Walking_frame_rate_60.fbx` | `file` | Kaydara FBX v7400. |
| `..._Character_output.fbx` | `file` | Kaydara FBX v7400. |
| `..._texture_0.png` | `file` | PNG 4096×4096 RGBA. |
| `..._texture_0_metallic.png` | `file` | PNG 2048×2048 grayscale. |
| `..._texture_0_roughness.png` | `file` | PNG 2048×2048 grayscale. |

## Source Arena Asset Files in `src/assets/extracted_assets/`

| File | Review Signal | Notes |
|---|---|---|
| Arena Scatter Rock `.fbx` | `file` | Kaydara FBX v7400. |
| Arena Scatter Rock base `.png` | `file` | PNG 4096×4096 RGB. |
| Arena Scatter Rock emission `.png` | `file` | PNG 2048×2048 RGB. |
| Arena Scatter Rock metallic `.png` | `file` | PNG 2048×2048 grayscale. |
| Arena Scatter Rock normal `.png` | `file` | PNG 4096×4096 RGB. |
| Arena Scatter Rock roughness `.png` | `file` | PNG 2048×2048 grayscale. |
| Lintel Gate `.fbx` | `file` | Kaydara FBX v7400. |
| Lintel Gate base `.png` | `file` | PNG 4096×4096 RGB. |
| Lintel Gate emission `.png` | `file` | PNG 2048×2048 RGB. |
| Lintel Gate metallic `.png` | `file` | PNG 2048×2048 grayscale. |
| Lintel Gate normal `.png` | `file` | PNG 4096×4096 RGB. |
| Lintel Gate roughness `.png` | `file` | PNG 2048×2048 grayscale. |
| Rune Monolith Pillar `.fbx` | `file` | Kaydara FBX v7400. |
| Rune Monolith Pillar base `.png` | `file` | PNG 4096×4096 RGB. |
| Rune Monolith Pillar emission `.png` | `file` | PNG 2048×2048 RGB. |
| Rune Monolith Pillar metallic `.png` | `file` | PNG 2048×2048 grayscale. |
| Rune Monolith Pillar normal `.png` | `file` | PNG 4096×4096 RGB. |
| Rune Monolith Pillar roughness `.png` | `file` | PNG 2048×2048 grayscale. |

## Tool Files

| File | Review Signal | Notes |
|---|---|---|
| `tools/export_backbones.py` | read directly | Exports MotionBricks transformer stacks and projection/embedding weights; saves metadata. |
| `tools/export_motionbricks_onnx.py` | read directly | Exports VQVAE encoder/decoder/codebook and pose/root backbones from MotionBricks checkpoints. |
| `tools/extract_fbx_mesh.py` | read directly | Blender FBX static mesh extractor; writes positions/normals/UVs/indices. |
| `tools/extract_mesh.py` | read directly | Raw GLB extractor for mesh data and embedded textures; writes positions/normals/UVs/indices. |
| `tools/extract_fbx_skinned.py` | read directly | Blender FBX rigged mesh/animation exporter to SKM1/ANM1 with coordinate conversion and top-4 weights. |
| `tools/verify_skinned_bin.py` | read directly; executed | SKM1/ANM1 verifier; checked male/female/dummy assets. |

## Architectural Findings

1. The game architecture is custom Rust/wgpu, not Godot and not code-empty.
2. Current implementation is renderer/motion/asset heavy relative to the verified playable loop.
3. The docs must steer the next phase back to playable 3-action loop and truth hash verification.
4. The skinned asset pipeline is materially useful and verified.
5. MotionBricks runtime path exists but remains a risk until action-driven motion and latency are proven.
6. Static asset binary format consistency must be locked before more extraction work.
7. Player/Developer/Presentation mode separation is not yet represented in the source architecture.
8. QA must include visual-agent capture audits, but final acceptance still needs human play/fun evidence.
