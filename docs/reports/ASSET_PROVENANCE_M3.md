# Milestone 3 Asset Provenance Audit

- Audit revision: `9691ecb9bc523ac9d0edb0c9950cf947aa2a2146`
- Audit UTC: 2026-07-13
- Decision: **technical provenance recorded; distribution rights remain unverified.**

## Runtime armored duelist

| Field | Value |
|---|---|
| Runtime source | `assets/source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin` |
| Geometry | 82,928 vertices; 309,864 indices; 24 bones |
| Cooked SHA-256 | `36a9c4e41f7e33ff58d68c10aa59a6b6cdbfb7e0384e0402e520801c205a1c7e` |
| GLB SHA-256 | `1508020c842b80980df3bb1cb7103f5edb9cb8adc1249fe1e757c741957b0ecb` |
| FBX SHA-256 | `354721c07ad407cc519fadda06f48d1a05051be77e7c03aab7f9df17f9501710` |
| Base color SHA-256 | `40a3a779d49090ccb249f9d218961d03df8eccac8b8dcbe8c15016e4a9068402` |
| Source chain | GPT Image 2 T-pose reference → Meshy 6 image-to-3D `019f5b5a-ab79-7acc-86f1-9867cf8ca851` → Meshy rig `019f5b61-5616-78ef-b659-09149eae24b2` |
| Conversion | Blender 4.3.2 GLB→FBX; `tools/extract_fbx_skinned.py` FBX→SKM1 |
| Immutable record | `assets/source/meshy/c0_armored_duelist_001/manifest.json` |
| Rights status | Unverified. Technical source identification is not a redistribution grant. |

`python3 tools/verify_skinned_bin.py` passed for the cooked mesh. Fresh engine frame dumps show a connected full-body armored silhouette with no static skinning explosion. They do not establish PBR material correctness or action animation.

## Existing package boundary

The previously described package is stale relative to the new armored-duelist runtime source and must not be treated as proof for this revision. Existing weapon and arena records still lack complete immutable redistribution-rights evidence. Therefore:

1. do not claim a distributable package;
2. keep asset generation/development active;
3. complete `E.6 QA-RIGHTS` before any distribution assertion; and
4. rebuild and verify the package only after the runtime asset set and rights records are closed.

## Required distribution closure

For every packaged payload, retain source identity, license/terms granting the intended redistribution, source hash, derivation chain, conversion-tool version, cooked hash, and a verifier that compares the package payload against those records.
