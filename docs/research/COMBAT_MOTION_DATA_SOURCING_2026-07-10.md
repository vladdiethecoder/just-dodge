# Combat Motion Data Sourcing — 2026-07-10

## Decision

Just Dodge will not use extracted proprietary game animation or gameplay footage as model-training or runtime motion input. Combat motion remains a provenance-gated asset class.

MotionBricks is a kinematic pose generator. The Rust 60 Hz simulation remains authoritative for swept weapon/body geometry, active windows, parry/whiff/hit, injury, force, and any ragdoll/physics handoff. Generated motion is presentation only.

## Primary-source findings

| Source | Evidence | Commercial status | Immediate role | Gate |
|---|---|---|---|---|
| Self-captured performances | Project-owned recordings with performer release and capture log | Green after release + provenance hash | Primary source for sword, stance, paired actions, reaction, grappling | Require written performer release, camera/capture metadata, action/phase/contact labels |
| Kyokushin Karate optical mocap | Figshare article `12315629`, DOI `10.6084/m9.figshare.12315629.v1`; 37 athletes, 1,411 recordings, 3,229 kicks/punches, C3D | Green: Figshare API reports CC0 1.0 | High-fidelity strike/kick primitive pretraining and phase-label baseline | Convert C3D markers to canonical skeleton; retain DOI/license/hash in manifest; not paired combat or weapon data |
| BONES-SEED | https://bones.studio/info/seed-license; 142,220 sequences documented at https://bones.studio/datasets/seed | Commercial license held per project owner, subject to its exact terms | MotionBricks-format base data; only 20 dataset entries are categorized martial arts | Keep data and audit manifests outside Git; record the internal commercial-license reference and accepted license hash before use |
| Mixamo | Adobe FAQ: https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html | Green for incorporation into commercial games; FAQ does not grant an explicit model-training/data-redistribution right | Runtime/reference motion only | Do not ingest into a training corpus absent written Adobe ML/data permission |
| Rokoko free motion assets | https://www.rokoko.com/free-resources lists 6 martial-arts and 13 fight clips, usable in commercial projects | Green for stated project use; ML-training grant not established | Runtime/reference motion only | Do not ingest into training corpus absent written vendor permission |
| Rokoko Vision self-capture | https://www.rokoko.com/products/vision documents webcam/video capture and FBX/BVH export | Tool output must be evaluated under current terms; own footage is the clean source input | Cheap capture/cleanup for self-filmed primitives | One performer per AI capture is documented; use simultaneous inertial capture or independently synchronized captures for paired interactions |
| ActorCore Hand-to-Hand Combat | Official listing states exports are royalty-free and FBX/BVH compatible: https://actorcore.reallusion.com/Motion?asset=studio-mocap-hand-to-hand-combat | Runtime use candidate; training right not established by public listing | Runtime/reference motion only | Purchase/EULA review and written ML-training permission before data ingestion |
| DuoBox / Ready-to-React | Official repo: https://github.com/zju3dv/ready_to_react; data requires a request form; repo has no discoverable top-level license | Unqualified for commercial ingestion | Research baseline only | Obtain a written commercial data license from authors before any download/training |

## Corrections to common assumptions

1. BONES-SEED is not unrestricted commercial "open data." Its published agreement grants a qualifying startup internal research/development/commercialization use below USD 1M annual revenue and requires a separate license outside that status.
2. A commercial game-animation license is not automatically a right to train/fine-tune a generative model, redistribute derived training data, or distribute a model whose weights may retain recoverable source content. Mixamo, Rokoko library assets, and ActorCore remain runtime/reference-only until the vendor grants that use in writing.
3. DuoBox is technically valuable for paired reactive boxing, but the official repository requires a data access form and does not expose a commercial data license. It must not enter the project corpus without written permission.

## BONES-SEED acquisition state

Project owner confirmed that Just Dodge holds a BONES-SEED commercial license. Hugging Face metadata remains access-gated until the owner enables approved account access; an unauthenticated metadata HEAD request returned HTTP `401` on 2026-07-10. `tools/audit_bones_seed.py` is ready to create an internal, non-redistributable candidate-selection audit after access is enabled. It accepts only an opaque internal license reference and writes the audit beside the licensed checkout, not into Git.

The public dataset card records 142,220 motions, approximately 288 hours at 120 Hz, SOMA and Unitree G1 representations, and temporal labels. It also records only 20 martial-arts entries, so BONES-SEED is the broad motion/tokenizer base corpus, not the complete paired, weapon-rich combat corpus.

## Data ABI required before training

Each imported sequence must become a provenance-locked record:

```text
sequence_id
source_id, source_url, license_id, license_url, acquisition_date, sha256
performer_release_id (required for self-capture)
skeleton_schema, fps, coordinate_system, unit_scale
self_root_world, opponent_root_in_self_frame
joint_positions, joint_rotations, joint_velocities
phase[neutral|guard|windup|strike|recover|hit|block|parry|grab|knockdown]
inter_agent_contact[self_anchor, opponent_anchor, state, confidence]
active_window_60hz, contact_frame_30hz
impact_direction, measured/estimated force label, target anatomy query
visual_qa, geometry_qa, rejection_reason
```

`CombatPrimitive` now contains the runtime-side immutable version of this interaction vocabulary. No field is fed into the released navigation checkpoint.

## Acquisition order

1. Import only the CC0 Kyokushin dataset metadata and a small sampled C3D conversion set. Prove marker-to-canonical-skeleton conversion, 30 Hz resampling, source visual QA, and phase/contact labeling before bulk ingestion.
2. Capture project-owned one-person sword and unarmed primitives with releases. Capture windup/contact/recovery separately and label semantic anchors.
3. Capture paired exchanges with synchronized cameras/inertial systems or a controlled dual-performer studio workflow. Produce shared contact-frame labels and opponent-relative-root trajectories.
4. If eligible under the recorded BONES-SEED agreement, use it only as the broad MotionBricks-compatible base corpus. Preserve raw-data isolation and license audit records.
5. Train/evaluate a new combat-conditioned tokenizer/root/pose checkpoint. The public G1 navigation checkpoint failed the raw-G1 gate under real target injection and is excluded from combat runtime use.
6. Only after raw source, generated G1, retarget, contact, latency, and two-fighter interruption gates pass may the new model enter the runtime request path.

## Primary sources

- NVIDIA MotionBricks project page, SIGGRAPH 2026: https://nvlabs.github.io/motionbricks/
- MotionBricks paper, arXiv:2604.24833v1, 2026-04-27: https://arxiv.org/html/2604.24833v1
- NVIDIA GR00T/MotionBricks repository and license: https://github.com/NVlabs/GR00T-WholeBodyControl
- BONES-SEED license: https://bones.studio/info/seed-license
- Kyokushin dataset publication: https://doi.org/10.1038/s41597-021-00801-5
- Kyokushin CC0 dataset: https://doi.org/10.6084/m9.figshare.12315629.v1
- Ready-to-React, ICLR 2025 / arXiv:2502.20370: https://arxiv.org/abs/2502.20370
- Adobe Mixamo FAQ: https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html
- Rokoko free resources: https://www.rokoko.com/free-resources
