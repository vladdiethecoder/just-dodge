# Milestone 3 packaged-asset provenance audit

- Audit UTC: `2026-07-13T02:21:28Z`
- Scope: `dist/just-dodge-m3-first-playable/assets/`
- Conclusion: **BLOCKED — package is an engineering/runtime proof only, not a distributable asset bundle.**

## Evidence rule

A packaged asset is distributable only when this repository contains a source identity, a license or distribution-rights statement, and a content hash or other immutable source linkage. Generation metadata or successful geometry QA is not a license statement.

## Packaged payload inventory

| Runtime path | SHA-256 | Source evidence | Rights status | Distributable? |
|---|---|---|---|---|
| `assets/source/meshy/c0_base_fighter/pose_carrier_001/cooked/c0_pose_carrier.bin` | `24b84977b5d4b275af385484c68a4624e6580fe22b0c7db14f149fa896dddb99` | `pose_carrier_001/report.json`: MPFB2 base, commit `26c811d...`, CC0-1.0; Meshy hand/foot references are named but have no bundled distribution-rights evidence. | Mixed / incomplete | No |
| `assets/source/meshy/c0_base_fighter/pose_carrier_001/cooked/c0_reference.anim` | `f0ec0e4ab59b9a859fc3ce26773de4dc43701f76e7eb69b94fdd9adc4c40bb10` | Derived companion artifact; no standalone rights record. | Incomplete | No |
| `assets/weapons/w0_sword_assembled.bin` | `e1ba7788cafcb2a156ff2bcdcda4d24f1811c8d50fc2a9a7a5d18ac77919831d` | `w0_sword/assembled_001/manifest.json` records Meshy-6 task IDs and source hashes, but no rights grant. | Incomplete | No |
| `assets/arena_rock.bin` | `d5de5def9d903c09b64b8ba73fc516737058bdb1bb222c8ee08e44e9272cc429` | No source manifest or license found. | Unknown | No |
| `assets/arena_rock_0.png` | `ba4637635294173825246a3bda19c4cb2277145a53020c197e7e282e62198b19` | No source manifest or license found. | Unknown | No |
| `assets/lintel_gate.bin` | `596633bda76d7fa3e663728f08d1f307eadbc34a5ace3d7198785ea2825c9d8f` | No source manifest or license found. | Unknown | No |
| `assets/lintel_gate_0.jpg` | `64b324de153183b2502db3ebeeece664265762292640df85744c7cfa8c80e14c` | No source manifest or license found. | Unknown | No |
| `assets/rune_pillar.bin` | `9889d31c3caa1158be2c3d184097e9653551db7a06a61f33a2a41cf54a8d117e` | No source manifest or license found. | Unknown | No |
| `assets/rune_pillar_0.jpg` | `b8a3e749603edd5a1a7ff2976c26aa04c396ba8e8493544c98974c63f7609dc4` | No source manifest or license found. | Unknown | No |

## Positive provenance found

`assets/source/reference_humans/mpfb2_base_001/provenance.json` identifies MakeHuman Community MPFB2 2.0.17 at commit `26c811d307b57e2f9f3d743b92d69681b1704e85`, with CC0-1.0 bundled-asset terms and bundled license files. This supports the underlying MPFB2 base source only; it does not establish distribution rights for the Meshy-derived additions or the cooked runtime carrier.

## Required release gate

Before a distributable package is claimed, add immutable provenance records for every runtime asset above containing:

1. source artifact hash and source identity;
2. an explicit redistribution right or license;
3. derivation chain and tool version for cooked outputs; and
4. a verifier that checks packaged hashes against those records.

Until then, keep this package out of release/distribution claims. A separate proof build may use only repository-authored procedural geometry and assets with complete records.
