# Adversarial Visual Contract

Status: permanent, fail closed. Threshold authority: `ADVERSARIAL_VISUAL_THRESHOLDS.v1.json`.

## Inheritance and change control

Every `/goal` or `TASK` that can change an asset, motion, renderer, camera, VFX, damage presentation, collision proxy, or arena inherits this contract. Its acceptance packet must name the threshold version and the reachable Git commit used for every render, metric, judgment, and verdict. Evidence from different commits may not be combined.

Feature work may preserve or strengthen this contract. Removing a view, frame, AOV, scope, lighting stress, or CI check; increasing a maximum; decreasing a minimum; or replacing a baseline requires a reviewed ADR that states the reason, impact, replacement evidence, and newly signed acceptance packet. A capture, thumbnail, contact sheet, or attractive gameplay video is diagnostic evidence only and never closes a task.

The four required GitHub checks are `adversarial-visual-gate`, `blender-asset-gate`, `motion-readability-gate`, and `provenance-hash-gate`. Missing checks or artifacts fail promotion.

## Revision and provenance boundary

Each run records one reachable Git SHA, dirty-worktree state, threshold/config hashes, tool and script hashes, renderer/device versions, source lineage, licenses, and content hashes. Raw source, DCC source, generated intermediates, cooked assets, frozen motion packets, runtime assets, and evidence remain distinct. Any source or hash change invalidates approval automatically.

Git stores canonical manifests and small evidence. Large artifacts use content-addressed CI or release storage. An optional Supabase mirror must use private buckets, RLS, short-lived signed URLs, and no public or service-role client access. It is never gameplay authority and paid infrastructure may not be revived without approval.

## Required stages and poses

Run the harness for every raw candidate, Blender revision, cooked asset, and live-runtime revision. Asset stages render neutral plus declared stress poses. Motion stages render first, anticipation, contact, and recovery poses and the first eight player-visible Reveal frames. Missing one stage, pose, angle, frame, pass, receipt, or hash fails the run.

For each required pose/frame, render 16 lossless 2048 by 2048 views with azimuth `22.5 degrees * i`, `i=0..15`, and fixed radius, height, lens, crop, aim point, scale, lighting, exposure, color management, renderer, camera matrices, and frame index. Assemble a 4096 by 4096 4 by 4 structure sheet, preserve each 1:1 view, emit defect crops, and emit an eight-frame strip from the actual first-person duel camera. Review copies label action, stage, view, frame, timestamps, AOV, and revision. Blind copies remove action labels.

Run neutral, grazing, and gameplay lighting at -1, 0, and +1 EV, both approved FOV extremes, mirrored presentation, and near, duel, and far LOD. Fog, depth of field, bloom, grain, motion blur, and auto-exposure are disabled.

## Background and edge contract

Use a flat, textureless, color-managed matte selected from the fixed versioned palette. An object-ID prepass samples actor and complete weapon colors. Selection maximizes the minimum OKLab distance and luminance contrast against both. Lock the result for the complete action or asset set. At least 95 percent of actor-edge pixels and 95 percent of weapon-edge pixels must each meet 4.5:1 luminance contrast. If no single palette color passes both, emit paired complementary light and dark variants. Lost edges, clipping, camouflage, exposure drift, or a missing complete weapon fail.

## Required AOVs and overlays

Every required view emits beauty and clay, silhouette, polygon wireframe/topology, normals and face orientation, depth and position, curvature and thickness, object/material ID or Cryptomatte, base color, roughness, metallic, normal, UV and texel density, weights, skeleton/socket, accumulated weapon path, collision/damage proxies, and shadows. The output index binds every image hash to its exact configuration.

Adversarial review actively seeks clipping, fused, floating, or thin parts, weak bevels, bad normals or UVs, repetition, baked lighting, false PBR, deformation collapse, foot slide, socket drift, weapon loss, silhouette confusion, and proxy mismatch. Every finding records view, frame, AOV, region, severity, disposition, and closure evidence or explicit deferral.

## Blender and Meshy boundary

Blender 5.1.2 build `ec6e62d40fa9` is the pinned DCC repair and validation authority. Headless, versioned scripts own FBX/GLB import, units, orientation, origin, bmesh/manifold and dimensions, retopology, component boundaries, UVs, bakes and PBR inputs, LOD, weights and stress poses, sockets, collision/fracture parts, AOV sheets, and deterministic export. Preserve raw source, `.blend`, scripts, logs, exports, and SHA-256 values. Untracked manual edits cannot be promoted.

Meshy 6 is an offline component-candidate source only. A valid geometry request is component-first, uses coherent multi-view references, sets `should_texture:false` and `should_remesh:false`, and separates anatomy, equipment, weapon mechanisms, and breakables. Geometry must pass Blender before PBR retexture and local physical-material correction. One-shot thumbnail acceptance is forbidden. Record endpoint, payload, task lineage, model, returned seed when available, credits, license, artifacts, and SHA-256; download expiring outputs. Meshy animation is rig diagnostics only.

If pinned Blender, Meshy access, or provenance/license inputs are unavailable, stop with the exact blocker. Do not substitute screenshots, placeholders, another generator, or untracked manual edits.

## Motion and live-runtime boundary

The required architecture is a live asynchronous neural stack, not three frozen authored clips. Pinned official ARDY is the interactive autoregressive diffusion planner. It consumes action-specific root, stance, both-hand, weapon-orientation, tell, opponent, and evolving kinematic constraints and continuously proposes a longer-horizon plan into a versioned asynchronous buffer. Fixed seeds and complete condition payloads make each proposal reproducible. ARDY does not own combat, collision, damage, or outcome.

An admitted MotionBricks checkpoint may provide the high-frequency transition and physics-feedback layer only when its exact source, checkpoint, rig, license, input channels, latency distribution, and feedback semantics are proven. A checkpoint that exposes only context and final-target boundary conditioning cannot be relabelled as an interaction-conditioned solver. Such a checkpoint remains a falsified A/B transition candidate until a compatible trained interaction-conditioning extension is admitted. MotionBricks does not own combat, collision, damage, or outcome.

The handoff unit is a canonical `NeuralPlanPacket`, never an unversioned tensor or request-envelope hash. It contains schema and model versions; source/checkpoint/license/rig/retarget/exporter hashes; seed; complete normalized constraints; input truth frame and truth-state hash; canonical quantized pose/proxy samples; validity interval; planner and feedback timing; and a canonical payload SHA-256 computed over the decoded match-relevant payload. A single-producer/single-consumer asynchronous ring buffer publishes only fully validated packets. Sequence gaps, stale truth inputs, mismatched hashes, non-finite values, latency-budget breaches, or buffer underruns abort before or during the match with a useful fail-closed error.

Live play consumes already-published packet samples; it does not synchronously wait for a neural model inside the 60 Hz truth tick. Physics contact and outcome feed the next planning condition at 120 Hz through a declared, hash-bound feedback schema. If the pose or pose-derived proxy affects truth, the packet payload hash, model stack version, and feedback-schema version are match/replay truth inputs. Replay and rollback consume recorded canonical packets byte-for-byte and never rerun ARDY or MotionBricks. Presentation-only interpolation may vary render cadence but cannot change truth bytes or result hashes.

One evaluated packet sample is the sole pose source for the rendered mesh, right-hand sword socket, weapon path, body/weapon/guard/damage proxies, and every corresponding AOV. Player mode has no bind-pose, reference-matrix, independent-sword, stale-packet, or alternate-generator fallback. Missing or mismatched assets, packets, checkpoints, or provenance abort before match start.

Admission is distributional. Each action covers the versioned stance, side, opponent-state, camera-FOV, distance, and fixed-seed matrix in the threshold file; a cherry-picked seed cannot admit a model stack. Report cold, hot, p50, p95, and worst ARDY planning, MotionBricks feedback, packet validation/decode, retarget, proxy evaluation, and end-to-end buffer age separately. The permanent thresholds govern p95 and worst latency, and zero underruns are allowed.

## Automated and human gates

Automated gates require zero NaN/Inf, missing bone, joint-limit violation, frame discontinuity, or crop; full body and complete weapon in all views; planted-foot drift at most 20 mm; penetration at most 10 mm; socket error at most 10 mm and 3 degrees; and frozen packet evaluation at most 16 ms. Record root drift, joint velocity and jerk, self/body-weapon penetration, proxy error, dimensions, components, silhouette and socket deltas across raw, Blender, cooked, and runtime stages.

Emit pairwise first-six-frame silhouette, optical-flow, and confusion heatmaps. Exact pixels and hashes are authoritative on the pinned GPU. Other approved GPUs use declared masked perceptual and SSIM tolerances. Baselines are immutable except through the ADR process above.

Human review uses randomized HUD-free, audio-free, action-unlabelled first-six-frame clips from the actual first-person camera. Server-side counterbalanced A/B/C mappings remain hidden from reviewers. Archive the mapping, pseudonymous response, latency, and exact clip hash. Each action needs at least 20 independent judgments, at least 80 percent accuracy, and no pairwise confusion above 20 percent.

## Acceptance packet and fidelity review

The packet includes reachable commit SHA; threshold/config hashes; source/model/checkpoint/license/skeleton/seed/retarget/exporter hashes; canonical motion-payload hashes; tests and timings; visual/physical metric JSON; cameras/background/renderer configuration; all structure sheets, views, AOVs, crops, and first-person strips; raw blind responses and confusion matrix; before/after truth fixtures; continuous packaged gameplay video; findings ledger; and redistribution status.

Craft benchmarks are diagnostic, never design-copy authority: For Honor for combat silhouette, armor layering, weapon and material readability; Elden Ring for authored silhouette, surface history, and environmental storytelling; and Dark Souls III for value hierarchy, wear/damage, and monumental atmosphere. Each milestone records and closes or explicitly defers its three largest visible gaps, proven in-engine.

Every verdict ends gate by gate with exact blockers and one next atomic unit. `PLAYABLE-PROOF` remains false until its later independent gates pass. Coupled ragdoll, final contact/damage, PBR arena polish, roster, and networking remain out of scope until PVP-005 passes.
