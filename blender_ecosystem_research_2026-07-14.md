# Blender Ecosystem Recommendations for High-Fidelity Game Assets
**Research date:** 2026-07-14 | **Scope:** stable/LTS, Cycles/OptiX + RTX 5090, glTF/FBX/USD, texture baking, color management, headless/CLI
**Convention:** "FACT" = stated in official primary source; "INFERRED" = best practice derived from official facts, not a direct quote.

---

## 1. Stable / LTS Version  **[FACT]**
- **Current stable = Blender 5.2 LTS**, released **July 14, 2026**, maintained until **July 2028** (2-year LTS).
- Prior active LTS: 4.5 LTS (Jul 15, 2025 – Jul 2027); 4.2 LTS (Jul 16, 2024 – Jul 2026, ending ~now).
- Blender cadence: stable release ~every 4 months; one LTS per year, supported 2 years.
- Official guidance: *"for general use and production, it's recommended to always use the latest stable release."*
- **Sources:**
  - https://www.blender.org/download/releases/5-2-lts/ ("Released July 14th, 2026")
  - https://developer.blender.org/docs/release_notes/5.2/ ("Blender 5.2 LTS was released on July 14, 2026 … maintained until July 2028")
  - https://developer.blender.org/docs/release_notes/ (version/date table, LTS policy)
  - https://www.blender.org/download/lts/ (LTS support windows)

## 2. Cycles / OptiX + RTX 5090  **[FACT + INFERRED]**
- **OptiX backend FACTS (Blender 5.2 Manual, GPU Rendering):**
  - OptiX supported on **Windows and Linux**; requires **NVIDIA GPU compute capability 5.0 or higher** and **driver version ≥ 535**.
  - *"OptiX takes advantage of hardware ray-tracing acceleration in RTX graphics cards, for improved performance."*
  - CUDA backend also supported on Win/Linux, compute capability ≥ 5.0.
- **RTX 5090 (Blackwell) support:**
  - **FACT:** RTX 5090 is NVIDIA compute capability **sm_120** (verified by independent NVIDIA/PyTorch sources dated 2025–2026). sm_120 >> 5.0 minimum, so it satisfies Blender's stated OptiX requirement.
  - **INFERRED (not a direct Blender quote):** Because Blender ships precompiled Cycles kernels and lists only "compute capability 5.0+ and driver ≥535" as the OptiX gate, an RTX 5090 on current drivers is expected to work under OptiX. The manual does NOT publish a per-card allowlist, and there is no Blackwell/sm_120 exclusion stated. (Early-2025 Reddit "5090 Cycles crashing" reports predate current drivers/manual and reflect driver maturity, not a documented Blender limitation.)
  - Driver recommendation: **NVIDIA Studio/Game Ready driver ≥ 535** (manual says use manufacturer/OEM drivers, not outdated OEM builds).
- **Sources:**
  - https://docs.blender.org/manual/en/5.2/render/cycles/gpu_rendering.html (OptiX section: "compute capability 5.0 and higher and a driver version of at least 535"; "Last updated on 2026-07-14")
  - https://forums.developer.nvidia.com/t/rtx-5090-not-working-with-pytorch-and-stable-diffusion-sm_120-unsupported/338015 (RTX 5090 = sm_120, dated Jul 2025)

## 3. Interchange Formats: glTF / FBX / USD  **[FACT]**
- **glTF 2.0** — Khronos importer/exporter, bundled & enabled by default (add-on "glTF 2.0"). Supports .glb, .gltf (separate/embedded), Draco/Meshopt compression, full PBR (BaseColor, MetallicRoughness, AO, Normal, Emissive, Clearcoat, Sheen, Specular, Anisotropy, Transmission, IOR, Volume, Iridescence), variants, UDIM. **Recommended format for game engines.** Dev: github.com/KhronosGroup/glTF-Blender-IO.
  - https://docs.blender.org/manual/en/5.2/addons/scene_gltf2.html
  - **Khronos primary spec:** https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html | Registry: https://registry.khronos.org/glTF/
- **FBX** — labeled **"FBX (Legacy)"** in 5.2; importer is a newer addition (binary FBX 7.1+, lacks many exporter features). Exporter supports smoothing groups, custom normals, armatures, baked animation. Use only when a target engine requires FBX; glTF preferred otherwise.
  - https://docs.blender.org/manual/en/5.2/files/import_export/fbx_legacy.html
- **USD (Universal Scene Description)** — full import **and** export add-on (in `files/import_export/usd.html`). Handles prim hierarchies, PointInstancer, materials, textures, rigging, UsdUIAccessibilityAPI; USDZ export supported (UDIM-in-USDZ known limitation per USD lib). Good for DCC interchange / Unreal pipelines.
  - https://docs.blender.org/manual/en/5.2/files/import_export/usd.html
- **Sources index:** https://docs.blender.org/manual/en/5.2/files/import_export/index.html ("Popular formats are enabled by default, other formats … enabled in the Preferences through … Add-ons")

## 4. Texture Baking  **[FACT]**
- Cycles **Render Baking** workflow documented in 5.2 Manual: Bake panel with Influence, **Selected to Active** (low→high, cage/extrusion, Max Ray Distance), Output to **Image Textures** or **Active Color Attribute**, and **Margin** (Extend / Adjacent Faces, pixel size) to avoid UV-seam discontinuities.
- Standard game-asset bake set: Normal (tangent space default), Diffuse/AO/Diffuse, Emission, etc. Bake targets an active Image Texture node per material.
  - https://docs.blender.org/manual/en/5.2/render/cycles/baking.html ("Last updated on 2026-07-14")

## 5. Color Management  **[FACT]**
- Blender uses **OpenColorIO (OCIO)**. Since **Blender 4.0**, the **AgX view transform is the default** in new files (replaced Filmic). AgX handles over-exposed highlights better (bright colors roll to white, like real cameras).
- 5.2 adds more input color spaces (camera logs, Adobe RGB, wide-gamut textures) and **Wide Gamut / HDR** enabling options.
- Working space is linear; images carry Non-Color vs Color roles; `BLENDER_OCIO` env var can override the OCIO config.
- For game textures: keep data maps (normal/roughness/metal/AO) in **Non-Color**; only albedo/emissive as Color. **INFERRED best practice**, consistent with manual's color-space role guidance.
- **Sources:**
  - https://docs.blender.org/manual/en/5.2/render/color_management/index.html ("Last updated on 2026-07-14")
  - https://developer.blender.org/docs/release_notes/4.0/color_management/ ("AgX view transform has been added, and replaces Filmic as the default in new files")
  - https://docs.blender.org/manual/en/5.2/render/color_management/opencolorio.html

## 6. Command-Line / Headless Operation  **[FACT]**
- **`-b` / `--background`**: run without UI (UI-less rendering), audio disabled by default. Enables remote/SSH rendering, no X server needed on Linux.
- Single frame: `blender -b file.blend -f 10`
- Animation: `blender -b file.blend -a` ; with engine/range/threads: `blender -b file.blend -E CYCLES -s 10 -e 500 -t 2 -a`
- Format override: `-o <path> -F OPEN_EXR -f <n>` ; arguments are order-sensitive (put `-f`/`-a` last).
- `--command` / `-c` implies background; `-P <script.py>` runs Python; `-E CYCLES` selects engine; `--debug-cycles` for logs.
- New in 5.2 Python API: `gpu.init()` to use GPU in background mode; `BLENDER_USER_*` / `BLENDER_SYSTEM_*` env vars for resource/script paths.
- **Sources:**
  - https://docs.blender.org/manual/en/5.2/advanced/command_line/render.html ("Last updated on 2026-07-14")
  - https://docs.blender.org/manual/en/5.2/advanced/command_line/arguments.html (`-b, --background`; GPU/Python/env-var options)

---

## Summary Table
| Topic | Recommendation (2026-07-14) | Confidence |
|---|---|---|
| Stable/LTS | **Blender 5.2 LTS** (Jul 14 2026 → Jul 2028) | FACT |
| RTX 5090 / OptiX | Supported via OptiX (sm_120 ≥ 5.0 req, driver ≥535) | FACT req + INFERRED support |
| Export to engine | **glTF 2.0 (.glb)** primary; FBX only if required (Legacy) | FACT |
| DCC interchange | **USD** import+export add-on | FACT |
| Baking | Cycles Render Baking (Selected-to-Active, Margin) | FACT |
| Color mgmt | **AgX** default (since 4.0), OCIO; Non-Color for data maps | FACT |
| Headless | `blender -b ... -E CYCLES -f/-a` ; no display needed | FACT |

*All manual pages cited are the Blender 5.2 LTS Manual, "Last updated on 2026-07-14".*
