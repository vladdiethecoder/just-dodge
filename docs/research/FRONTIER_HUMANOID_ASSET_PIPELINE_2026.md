# Frontier Humanoid Asset Authority Survey — 2026-07-20

Status: active canary research for Just Dodge asset foundation v2. This document distinguishes a character body authority from a general 3D candidate producer.

## Observed local result that triggered the survey

Two paid Meshy 6 body-carrier runs failed the same anatomy class:

- `meshy6_001` (multi-image): 67,852 vertices, 135,728 triangles, no UVs; both hands visibly collapsed into approximately two fused blade-like masses.
- `meshy6_002` (single-front image): 109,423 vertices, 218,902 triangles, no UVs; the same fused/missing-digit failure reproduced.
- Both meshes were manifold and had zero measured degenerate faces. This proves manifoldness is not character viability.
- Evidence: `assets/foundation/v2/fighters/f0_body_carrier/candidates/*/asset_authority.json` and their Blender QC renders.

Under strike-two discipline, Meshy remains eligible for isolated armor, weapons, props and environment components, but is no longer the active body-authority producer.

## Frontier paths

| Path | Current evidence | License/release issue | Body-authority disposition |
|---|---|---|---|
| CharacterGen + UniRig | SIGGRAPH/TOG 2024 character-specific single-image pipeline with multi-view pose calibration; official repo publishes 2D/3D inference, Blender/VRM route and points to UniRig. Local repo code is Apache-2.0; model card is Apache-2.0. | Training/evaluation data is anime VRM; repository says raw VRM data cannot be redistributed. Input/output source rights still require a receipt. Stack is old (Python 3.9, diffusers 0.24) and needs a modern CUDA canary. | Active local canary. Best open character-specific falsifier for Meshy's general-object failure. Still candidate-only until digits, topology, UV, rig and Blender gates pass. |
| TRELLIS.2 | Microsoft 4B image-to-3D model, up to 1536^3, PBR, arbitrary topology and MIT repository code. | Project page labels materials research-only/not intended for commercial exploitation despite MIT code; model/data terms must be resolved before shipping. General-object model has no deformation topology or rig guarantee. | Research canary only unless terms are reconciled. Not a body authority by itself. |
| Hunyuan3D 2.1/2.5/2mv | Local shape/texture pipeline, multiview model, Blender add-on/API; official docs state ~6 GB shape and ~16 GB shape+texture VRAM. | Tencent community license excludes EU, UK and South Korea; distribution carries notice/use obligations and >1M MAU terms. Global Steam distribution conflicts without a separate license. | Technically viable candidate producer; blocked as global release lineage under current terms. |
| Character Creator 5 | Official CC5 system provides HD body/face rigs, T-pose, skin weights, Blender tools, FBX/OBJ export, 70K HD mesh, 20K CC3+ and 10K Game Base. It includes clothing conformation, LOD/remesh and material tooling. | Proprietary paid tool/content licenses. Official page lists USD 299 Standard / USD 479 Deluxe before content or plugins. Exact export/content license needs owner acceptance. | Strongest turnkey production body topology route if proprietary licensing is acceptable. |
| SMPL-X / Meshcapade | Semantically stable body, hands and face model with Blender integration and commercial licensing path. | Public SMPL-X terms are non-commercial research only; commercial use requires Meshcapade/Max Planck licensing. | Strong mechanics/anatomy carrier after commercial license; identity/hair/material art remains ours. |
| MetaHuman | High-fidelity digital-human topology, hands/face and rig under the Unreal/MetaHuman license; current vendor positioning supports deployment through varied rendering environments. | Epic license/toolchain obligations, revenue terms and export/runtime constraints need owner review; adds Unreal tooling to a custom-engine pipeline. | High-fidelity option, but excessive licensing/toolchain coupling unless chosen deliberately. |
| Didimo Popul8 | Engine-agnostic character generation positioned for games and enterprise integration. | Enterprise terms/pricing and source ownership are not sufficiently public for immediate admission. | Vendor evaluation candidate only. |
| Rodin Gen-2.5 / Tripo 3.1 | Current cloud challenger generation systems with character/rigging claims and standard exports. | Paid, marketing-heavy, and no evidence yet that either solves exact fingers/deformation topology on this brief. | A blind paid bake-off can falsify them, but they remain candidate producers rather than authority. |
| MakeHuman/MPFB | Parametric Blender-native human base; official license says core assets and qualifying GUI exports can be CC0. | The CC0 exception has conditions; third-party plugin output and linked-library use can fall under AGPL. The exact MPFB/export path must be recorded. | Lowest-friction deterministic fallback authority, but less visually frontier than CC5/SMPL-X and needs authored identity/lookdev. |

## Real production signal

World Labs' 2026 AI-native pipeline case study is consistent with the foundation architecture: Claude Code orchestrates Marble, fal, Hunyuan3D, cleanup and audio; generated environments are split into editable meshes/physics objects and then handed to Blender/Unreal. It explicitly treats AI output as editable pipeline input rather than final authority. This supports the component-first DCC-authority approach and does not support one-shot hero-character generation.

CC5's official feature matrix is another strong signal: production character value comes from a stable parametric base, skin weights, conformation, rig profiles, LOD/remesh, materials and export integration—not from a one-shot mesh alone.

## Current decision

Proceed with the local CharacterGen canary because it is character-specific, open, reproducible on the RTX 5090 and directly falsifies the general-generator root cause without another paid request. The canary is pinned to:

- Repository commit `f329a835dbd5003060a5653eafd83d4d8868b043`
- Model repository revision `5b733f0e90d9fe51a126c8462ea33d49ae3bdabe`
- Python 3.10.19 (the documented Python 3.9 path could not pair with a CUDA 13 / sm_120 PyTorch wheel)
- PyTorch 2.9.1 + CUDA 13.0; nvdiffrast 0.4.0 built from commit `253ac4fcea7de5f396371124af597e6cc957bfae` with CUDA 13.1, GCC 15 and sm_120
- Seed 2333, 40 multi-view diffusion steps

Admission requires five distinct fingers per hand, no anatomy collapse, full-source hashes, Blender import, strict mesh metrics, UV evidence, neutral-view renders, and then UniRig stress-pose validation. A canary failure does not trigger prompt retries; it promotes the decision to a parametric body authority (CC5, commercially licensed SMPL-X, or conditional CC0 MakeHuman/MPFB).

## Primary sources retrieved 2026-07-20

- CharacterGen project and paper: https://charactergen.github.io/
- CharacterGen repository and Apache-2.0 license: https://github.com/zjp-shadow/CharacterGen
- CharacterGen model card/revision: https://huggingface.co/zjpshadow/CharacterGen
- TRELLIS.2 project: https://microsoft.github.io/TRELLIS.2/
- TRELLIS.2 repository MIT license: https://github.com/microsoft/TRELLIS.2
- Hunyuan3D-2 repository, model matrix, VRAM and Blender/API docs: https://github.com/Tencent-Hunyuan/Hunyuan3D-2
- Hunyuan3D 2.0 community license: https://raw.githubusercontent.com/Tencent-Hunyuan/Hunyuan3D-2/main/LICENSE
- Character Creator 5 features/pricing: https://www.reallusion.com/character-creator/
- SMPL-X license: https://smpl-x.is.tue.mpg.de/modellicense.html
- MakeHuman/MPFB license: https://static.makehumancommunity.org/about/license.html
- World Labs AI-native 3D pipeline case study: https://www.worldlabs.ai/labs/showcase/ai-native-3d-pipelines
