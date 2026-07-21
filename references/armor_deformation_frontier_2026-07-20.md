# Frontier armor deformation research and deterministic implementation route

**Project:** Just Dodge (Rust/wgpu, deterministic truth)
**Date:** 2026-07-20
**Scope:** contact-aware armor/clothing deformation, layered character simulation, neural corrective skinning, cage/SDF binding, and physically constrained hard-surface plate articulation. This is an implementation decision record, not a claim that any paper is production-ready.

## Executive outcome

Do **not** put a floating-point neural simulator in the authoritative combat/contact path. The best route for Just Dodge is a deterministic hybrid:

1. **Authoritative layer:** rigid armor plates as explicit links attached to the existing skeleton, with fixed-pivot hinge/spherical constraints, joint-range limits, and deterministic collision proxies. This is the only layer allowed to affect truth, contact, ROM, damage, or replay.
2. **Offline binding:** use a SkinCells-/robust-biharmonic-style binder to generate sparse, topology-tolerant weights and transfer them to the armor shells. Export at most four influences per vertex, then cook to the existing custom runtime format.
3. **Offline contact oracle:** use PhysDrape, NeuralClothSim, or a high-quality deterministic PBD/XPBD solver to generate pose/contact samples for straps, faulds, leather, chainmail, and other flexible secondary pieces. Do not use that solver as runtime truth.
4. **Baked corrective layer:** distill the offline samples into a small, quantized corrective basis (pose-space morphs or virtual-bone/node residuals). Runtime evaluates a deterministic fixed-point lookup/polynomial and ordinary skinning; it does not run a neural network.
5. **Optional presentation experiment:** PhySkin/PhysSkin-style neural node correctives may be evaluated as a shadow presentation path only after they beat the baked path and survive quantization. Their output must never write combat state or collision outcomes.

This route matches the current project boundary: `src/articulated_physics.rs` owns an integer fixed-step truth solver; `src/hinge_projection.rs` and `src/g1_hinge_adapter.rs` already project targets onto deterministic hinge axes/limits; `src/active_ragdoll.rs` is a bounded motor/presentation bridge; and `docs/ARMOR-DAMAGE-SYSTEM.md` explicitly makes armor damage a deterministic event-driven record.

## Existing Just Dodge anchors

- `docs/ARMOR-DAMAGE-SYSTEM.md`: armor pieces cover explicit regions (breastplate, pauldrons, couters, vambraces, poleyns, etc.); the system expects ROM clamps, mass/material properties, persistent damage events, and deterministic visual state. It distinguishes plate/lamellar/chainmail/leather behavior, which argues against one universal cloth model.
- `assets/foundation/v2/qa/sg02_lifecycle_kit_redo/evidence/path_b_mixamo_canary_manifest.json`: torso, vambraces, greaves, and boots already passed the quarantine transfer with zero unweighted vertices and `<=4` normalized influences. The full kit remains blocked at the hand/finger strike, so a global neural or cage rewrite would be the wrong next move.
- `src/hinge_projection.rs`: deterministic hinge-angle projection in integer units.
- `src/g1_hinge_adapter.rs`: representation conversion to pinned hinge targets; it uses microradians/milliradians and official limits rather than unconstrained transforms.
- `src/articulated_physics.rs`: fixed-step, canonical-order physics substrate; any armor solver must preserve its ordering and replay hash contract.
- `docs/reports/JD_RC0_TRUTH_BASELINE_2026-07-17.md`: current baseline reports 5/5 GLBs with zero glTF Validator errors, a passing 100-replay truth-hash determinism test, and the established glTF-to-cooked-runtime separation.

## Method matrix

### 1. Deterministic rigid plate graph — production baseline, ranked first

**Mechanism.** One rigid link per meaningful plate or plate cluster; an explicit pivot and local frame; hinge, slider, or bounded spherical joint; a low-poly convex/capsule contact proxy; a soft strap/connector only where a rigid link is insufficient. The visible hard surface is not skinned across a bend that should articulate as a plate.

**Offline cost.** Author pivots, rest transforms, overlap/clearance, mass/inertia, and limits. Generate proxy hulls and a body-to-plate clearance report. No training.

**Runtime cost.** A few fixed-point joint rows and proxy contacts per plate. Target `p99 <=0.25 ms` for one armored actor at 120 Hz and `p99 <=1.0 ms` for four actors on the release CPU, including plate constraints but excluding rendering.

**Determinism/packetization.** Ideal. Serialize only stable plate IDs, parent IDs, quantized local transforms, joint state, and solver version. Never serialize neural weights or optimizer state. Use stable plate/constraint/contact ordering.

**Export.** Each plate can be a glTF node or a separate mesh under the accepted skeleton. Put pivot/axis/limit/material metadata in a versioned `extras` block, then cook to the existing custom binary. glTF is interchange; the runtime should load cooked bytes.

**License/maturity.** No research dependency; this is the only path with full project ownership and predictable maintenance.

**Use.** Breastplate, pauldrons, couters, poleyns, vambraces, greaves, sabatons, rigid helm/gorget sections, and active-ragdoll-linked pieces.

### 2. SkinCells: sparse Voronoi weight fields — best binding candidate

**Primary source:** [SkinCells: Sparse Skinning using Voronoi Cells](https://arxiv.org/html/2506.14714), Eurographics/Computer Graphics Forum 2026; [author page](https://elrnv.com/projects/skincells/).

**Mechanism.** A continuous, parameterized Voronoi-like weight field around joints. Sparsity is explicit: with the field configured for `l`, each point has at most `l` non-zero influences. The authors optimize smoothness, skeleton-following location, and sparsity over sampled poses. The field can be evaluated on different mesh resolutions and similar meshes, making it useful for LOD and armor variants.

**Measured offline cost.** 1,500 optimization steps over 1,024 poses, batched at 16; tried examples converged within about one minute on an RTX A6000. The paper reports all 40 artist-created characters processed, versus bounded biharmonic baselines that failed on several meshes.

**Runtime cost.** Ordinary LBS after weights are baked; no neural inference and no extra runtime solve. The paper reports the field representation itself as 21 KB of single-precision parameters and up to four influences in experiments; the actual cooked vertex buffers still dominate memory.

**Determinism/packetization.** Excellent after bake. Store only sorted `JOINTS_0/WEIGHTS_0` or engine-native equivalent. Generate weights offline with a pinned tool/container; do not evaluate the continuous field in combat runtime.

**Export.** Directly compatible with glTF skin attributes after pruning/normalization. The field itself is not a glTF runtime requirement. For each armor asset, retain the field parameters as authoring provenance and bake final per-vertex weights into the custom cook.

**License/code maturity.** The paper and author page are public; no public implementation repository was located in the checked official sources. No code license was therefore established. Treat it as a method to reimplement or prototype, not as a shippable dependency.

**Limits.** The paper explicitly does not solve garment self-contact; canonical 3D proximity can confuse surfaces close together, and it recommends a separated A/T-pose. This is acceptable for armor binding only if pair-clearance and extreme-pose gates follow the bake.

**Verdict.** Use the idea first: optimize sparse weights for the Meshy armor on the real MPFB/Mixamo carrier, with `l=4`, then verify the same weights across LODs. Do not import an unlicensed research repository.

### 3. Robust Biharmonic Skinning Using Geometric Fields — binding fallback

**Primary source:** [Robust Biharmonic Skinning Using Geometric Fields](https://arxiv.org/html/2406.00238v2), ACM TOG 2025.

**Mechanism.** Mesh-free Lagrangian geometric fields optimize bounded-biharmonic-like weights without tetrahedralizing the volume. The method is designed for open surfaces, triangle soups, scans, and difficult geometry where FEM/tetrahedralization fails. It uses hardware-accelerated ray tracing for geometry-aware parameterization.

**Measured offline cost.** The paper reports a difficult case solved in 32.2 s versus 1.78 h when a boundary-respecting tetrahedralization path was used. This is authoring-time work, not runtime.

**Runtime cost.** None beyond ordinary baked skinning. The output is weights, not a neural runtime field.

**Determinism/packetization.** Good after bake. Pin the authoring result and serialize only the final sparse weights. Re-running a GPU ray-tracing optimizer need not be bit-identical; the cook receipt and resulting weights must be hash-bound before promotion.

**Export.** Same glTF `JOINTS_0/WEIGHTS_0` path; no direct glTF exporter was found in the official paper sources. The result still needs the existing glTF Validator and custom cook.

**License/code maturity.** No official code repository was located in the checked sources. The article is published research; do not infer a code license from the paper or copy an implementation without a separate license review.

**Verdict.** Keep as the fallback when SkinCells-style optimization or standard heat/biharmonic weights fail on Meshy shells, gauntlet topology, or armor with openings. It is especially valuable for irregular/open armor meshes, not as a runtime SDF.

### 4. PhySkin — strongest 2026 neural corrective design for a baked route

**Primary source:** [PhySkin: Physics-based Bone-driven Neural Garment Simulation](https://arxiv.org/html/2603.27013), submitted 2026-03-27.

**Mechanism.** Reduce a garment to sampled virtual nodes/handles, initialize them by LBS from the body pose, and learn pose/body-conditioned corrective transforms for those nodes. Training is self-supervised using stretch, bending, collision, and gravity energies. The runtime path then skins the garment from corrected handles.

**Measured offline cost.** Approximately 32 hours on one NVIDIA A100. It uses 128 nodes by default; the paper reports diminishing quality returns beyond 128. It does not require precomputed simulated ground truth, but it still requires substantial optimization and a target garment/body training setup.

**Measured runtime cost.** The custom C++ forward pass reports `12.5 us` for the node-deformer MLP plus `46.7 us` for the pose MLP, or 16,891 FPS for those two MLPs on one Threadripper PRO 7995WX core. The paper explicitly excludes skinning and the one-time body encoder, so this is not an end-to-end armor budget.

**Determinism/packetization.** The direct neural path is not acceptable as truth until a native Rust implementation, fixed-point/quantized weights, and a cross-run hash contract are demonstrated. The useful production transfer is to use PhySkin as an offline teacher, then export a low-rank corrective basis or a small deterministic lookup over joint-angle bins.

**Export.** The paper describes node transforms and LBS, not a glTF exporter. Export the corrected result as ordinary skinning weights plus pose-space correctives or bake representative clips to a custom vertex-animation asset. A custom engine packet is preferable to shipping Python/PyTorch.

**License/code maturity.** The arXiv paper is public; no official code repository was located in the checked sources. No code license was established.

**Limits.** The authors state that the method is quasi-static and future work is needed for dynamics. That makes it a candidate for fitted armor/strap pose correctives, not a substitute for active-ragdoll contact dynamics.

**Verdict.** Rank first among neural methods, but use it offline and distill. It has the right abstraction—virtual handles plus skinning—for a game asset pipeline.

### 5. PhysSkin — more general continuous neural skinning fields, but not integration-ready

**Primary source:** [PhysSkin project page](https://zju3dv.github.io/PhysSkin/), [arXiv:2603.23194](https://arxiv.org/abs/2603.23194), [repository](https://github.com/zju3dv/PhysSkin).

**Mechanism.** Learns continuous skinning fields as basis functions from handle transformations using a transformer encoder and cross-attention decoder. The self-supervised objective balances energy minimization, spatial smoothness, and orthogonality; the field is mesh/discretization-agnostic in the research formulation.

**Offline/runtime cost.** The public project page emphasizes real-time physics-based animation and generalization, but the checked README does not provide an end-to-end game runtime number suitable for budgeting.

**Determinism/packetization.** Research inference is floating-point and continuous. The practical transfer is to sample the field on the target armor vertices offline, normalize/prune to four influences or a low-rank residual basis, and throw away the network for runtime.

**Export.** No glTF exporter is supplied. Baked weights/correctives can use glTF; the neural field itself requires a custom engine implementation and is not a glTF primitive.

**License/code maturity.** The repository has 7 commits, 32 stars, 0 issues, and no published releases. Its README explicitly lists code release as unchecked (`[ ] Release codes`), and the checked `LICENSE` URL is 404. This is research code not yet released, not a production dependency.

**Verdict.** Useful as a research direction for future universal binders; lower immediate priority than PhySkin because it lacks released code and a concrete runtime/export path.

### 6. PhysDrape — explicit force + stretching solver + collision handler

**Primary source:** [PhysDrape](https://arxiv.org/html/2602.08020).

**Mechanism.** A force-driven GNN predicts per-node forces; a learnable stretching solver propagates them; an integrated collision handler projects vertices away from the body. The model is self-supervised with strain, bending, collision, and gravity energies, rather than supervised by draped meshes.

**Measured results.** On CLOTH3D, training used 600 top garments, 30 unseen test garments, 150,000 iterations on one V100, and `T=3` during training / `T=15` for evaluation. Reported B2G interpenetration is approximately `0.05%`; strain energy is `0.20` at T=3 and `0.15` at T=15; bending energy is `0.004`. Runtime is 29 ms per garment at T=3 and 91 ms at T=15 on one V100, averaged over 5,000 samples.

**Offline/runtime cost.** Strong offline contact-aware teacher, but the 29–91 ms result is already too expensive for a 120 Hz armor truth path, and it is a static drape method rather than an active dynamic solver.

**Determinism/packetization.** Treat outputs as offline reference meshes/contact samples. If used in a shadow presentation path, record the exact model/seed/input pose and quantize the resulting displacement before use. Never let its collision handler create gameplay contact events.

**Export.** It produces mesh positions, not glTF animation or a Rust/wgpu runtime. Distill to pose correctives, node deltas, or a contact-safe proxy; export the baked result through ordinary glTF/custom cook.

**License/code maturity.** The checked primary source is arXiv; no official code repository/license was located. Research maturity is high as a paper, integration maturity low.

**Limits.** The evaluation is upper-body soft garments on CLOTH3D and does not establish hard metal plate behavior, active ragdoll, or arbitrary MPFB/Meshy topology.

**Verdict.** Use for offline strap/fauld/underlayer fitting and as a collision oracle. Do not use for rigid plates or runtime truth.

### 7. ClothTransformer — frontier latent-space simulator, too large for first integration

**Primary source:** [ClothTransformer](https://arxiv.org/html/2605.27852v4), [project page](https://yucrazing.github.io/clothtransformer/), [dataset card](https://huggingface.co/datasets/YuCrazing1/ClothTransformer-dataset).

**Mechanism.** Compresses variable-resolution cloth and collider geometry into a fixed number of latent tokens, evolves dynamics autoregressively with a transformer, decodes to vertices, and uses differentiable continuous collision detection plus CCD post-processing. The dataset spans human garments, robotic manipulation, and diverse object collisions.

**Measured offline/runtime cost.** Training is reported as 160k pretraining + 40k fine-tuning steps, about 300 NVIDIA H200 GPU-hours, on 2,056 trajectories / 493,440 frames (~33.7 GB). With 1,024 latent tokens, inference is about 4.90 ms/frame in the paper’s ablation. However, the encoder/decoder remain mesh-dependent: at 40k vertices the paper reports 275.27 ms/frame on an RTX 4090. The method is therefore not resolution-free end-to-end.

**Contact quality.** On unseen human-garment tests, reported MVE is 6.92 cm, collision rate 14.12%, and self-collision rate 9.79% without the CCD-loss variant; the CCD-loss variant reports 6.53 cm MVE, 16.32% collision, and 9.12% self-collision in the table. These numbers are soft-cloth benchmark values and are not an armor acceptance target.

**Determinism/packetization.** Autoregressive neural rollout and CCD postprocessing are poor truth candidates. Use the model as an offline trajectory generator; packetize the distilled result as fixed-point basis coefficients or baked vertex frames, not transformer state.

**Export.** No glTF exporter is provided by the paper/project source. Output can be sampled to OBJ/glTF for authoring or compressed into a custom vertex-animation/corrective asset.

**License/code maturity.** The dataset is CC BY 4.0, but its underlying assets retain additional terms: SMPL CC BY 4.0, Make-It-Animatable Apache-2.0, 3D Garments CC BY 4.0, and Objaverse ODC-BY 1.0/per-object licenses. The checked paper/project sources did not establish a permissive code license. The dataset is useful but 33.7 GB and provenance-heavy.

**Verdict.** Keep for a later offline contact-data lane, not as the first runtime route.

### 8. NeuralClothSim — MIT authoring oracle for flexible pieces

**Primary source:** [NeuralClothSim](https://4dqv.mpi-inf.mpg.de/NeuralClothSim/), [repository](https://github.com/navamikairanda/neuralclothsim), NeurIPS 2024.

**Mechanism.** Represents a thin shell as a continuous neural deformation field and optimizes it with nonlinear Kirchhoff–Love shell energies, anisotropic materials, and hard boundary conditions. It can query arbitrary surface resolutions without retraining and supports material interpolation/editing.

**Offline/runtime cost.** It is a quasi-static neural-field solver/authoring tool, not a cheap per-frame game solver. Use it to create panel/strap reference states, material sweeps, or basis samples. It is especially appropriate for isolated flexible armor elements with explicit boundaries; it does not establish a complete body-contact pipeline for the MPFB armor stack.

**Determinism/packetization.** Keep checkpoints and optimization outside the game. Export sampled positions, normals, and a deterministic corrective basis. If a neural field is retained for offline regeneration, bind a container/version/hash receipt.

**Export.** README supports arbitrary-mesh input and extraction of simulated meshes, but no glTF/runtime exporter. Sample and cook through the project’s normal glTF validation path.

**License/code maturity.** 105-commit public repository, MIT `LICENSE` file, official reproduction instructions, and a Colab path. The README also says “freely for non-commercial use,” which conflicts with the MIT file; legal review should resolve the discrepancy before commercial reuse. Dependencies include PyTorch3D and CUDA 11.8-era packages.

**Verdict.** The most usable openly coded offline oracle in this list, but keep it out of runtime and resolve the README/license discrepancy.

### 9. Layered baselines: ISP, GAPS, and SNUG — useful references, not shipping dependencies

- **ISP: Multi-Layered Garment Draping with Implicit Sewing Patterns** ([paper/project](https://liren2515.github.io/page/isp/isp.html), [repo](https://github.com/liren2515/ISP), NeurIPS 2023) is directly relevant to layered clothing. The public repo has 18 commits, checkpoints, Python 3.8 / Torch 2.0.1 / CUDA 11.8 instructions, and explicit layering inference. It is image/SMPL/checkpoint-oriented, offline, and no `LICENSE` file was found. Use only as an offline layered-underlayer/garment generator after asset-license review.
- **GAPS: Geometry-Aware, Physics-Based, Self-Supervised Neural Garment Draping** ([paper](https://arxiv.org/html/2312.01490v2), [repo](https://github.com/Simonhfls/GAPS), 3DV 2024) adds geometry-aware collision/inextensibility and skinning. The public repo has 2 commits, TensorFlow 2.10 instructions, 22 stars, and no `LICENSE` file was found. It is a reasonable older contact baseline, not a hard-plate method.
- **SNUG: Self-Supervised Neural Dynamic Garments** ([paper](https://openaccess.thecvf.com/content/CVPR2022/html/Santesteban_SNUG_Self-Supervised_Neural_Dynamic_Garments_CVPR_2022_paper.html), [repo](https://github.com/isantesteban/snug)) has a public trained-model runner and 201 stars but only 4 commits. Its `LICENSE.md` permits non-commercial scientific research, education, or non-commercial artistic projects and explicitly prohibits commercial use. It must not enter a commercial Just Dodge build without a new license.

## Cage/SDF binding decision

Use a cage/SDF as **offline geometry and contact metadata**, not as a learned runtime authority:

- Build a body collision proxy and per-piece signed-distance/closest-surface samples in canonical pose.
- Use those samples to reject bad weights, train or fit correctives, and generate clearance-aware extreme poses.
- At runtime, use authored convex/capsule proxies and deterministic fixed-point contact/limit rows. Do not evaluate a dense neural SDF per vertex at 120 Hz.
- If a per-vertex SDF is needed for presentation, bake a low-resolution quantized grid or sparse local samples and use a fixed traversal/interpolation order. The SDF cannot create a gameplay hit by itself.
- A pure proximity/cage binder is insufficient around close canonical surfaces, armpits, fingers, layered plate gaps, and open armor shells. Pair-clearance and extreme-pose tests are mandatory.

## Physically constrained hard-surface plate articulation

Hard plates should not be treated as cloth triangles. Use a hierarchy such as:

```text
body bone / active-ragdoll link
  -> plate rigid link (pivot, inertia, collision proxy)
      -> optional compliant strap/connector
          -> adjacent plate rigid link
```

Recommended constraints:

- **Hinge:** shoulder/pauldron flap, couter, poleyn, sabaton flap; fixed axis and signed min/max angle.
- **Bounded spherical joint:** pauldron mounted to the shoulder ball where two-axis motion is required.
- **Slider/rail:** fauld/tasset or sliding knee/arm coverage; bounded travel, no unconstrained transform blending.
- **Compliant connector:** leather straps, chainmail links, or articulated gap covers; deterministic spring/damper or position constraint, not plate deformation.
- **Contact proxy:** convex hull/capsule/box per plate; body contact shapes remain the truth geometry. Use CCD for fast weapon/body sweeps, not for rendering mesh.

A plate may have a visual LBS skin only over a small transition region. If that LBS causes visible metal volume collapse, split the plate at the mechanical seam and add a rigid link instead. This preserves silhouette, mass, ROM, and contact semantics.

## Ranked implementation route

### R0 — Deterministic plate graph and offline sparse binding (implement first)

1. Keep each rigid Meshy plate as a separate source object.
2. Author stable plate IDs, parent joint, pivot, axis, rest transform, mass/inertia, clearance, and ROM limits.
3. Use the existing integer hinge projection/adapter path for targets.
4. Generate sparse armor weights with a SkinCells-style optimizer; fall back to robust biharmonic/geometric-field or current nearest-surface transfer where needed.
5. Prune/normalize to `<=4` influences, cook to the custom runtime format, and retain glTF only as interchange/review.

**Keep gate:** all R0 acceptance measurements below pass on the MPFB body, Meshy armor, Mixamo canary, and the existing hand/foot negative fixtures.

### R1 — Deterministic baked corrective basis

1. Create an offline pose corpus: the current proof poses plus a held-out set sampled within joint limits; include crouch, torso twist, shoulder elevation, elbow/knee flexion, forearm pronation, and plate-gap extremes.
2. Use a deterministic high-quality solver or PhysDrape/NeuralClothSim/PhySkin-inspired self-supervised teacher to produce body-clear, low-energy target states for flexible pieces.
3. Fit per-piece virtual-node or pose-space correctives; retain `K<=8` bases per piece and quantize deltas to signed 16-bit values with an explicit scale.
4. Runtime computes coefficients using a fixed-point piecewise-linear table or bounded polynomial over joint angles; it then performs ordinary LBS/rigid transforms.

**Why this is the recommended frontier transfer:** it captures the research benefit of neural/physics methods while keeping replay, rollback, contact, and glTF/custom cook deterministic.

### R2 — Offline contact-aware layered authoring

Use ISP for initial multi-layer geometry only if its dependencies and source assets are legally cleared. Use PhysDrape or NeuralClothSim to fit flexible underlayers/straps/faulds to extreme poses. Use ClothTransformer only if a later research lane needs broad collision trajectories and can afford its 33.7 GB dataset / 300 H200-hour training path.

**Do not:** use an ISP/GAPS/SNUG checkpoint to decide armor collision, injury, damage, or action success.

### R3 — Presentation-only neural shadow

Prototype PhySkin-style node correctives or PhysSkin continuous fields in a separate presentation module. Compare against R1 on held-out poses. Promotion requires a native Rust/wgpu or CPU implementation, fixed model/version hashes, deterministic quantization, and no authority-boundary imports. If it cannot beat R1 under the gates, delete the shadow path rather than making it a second deformation authority.

### R4 — Full runtime neural/cloth simulation

Defer. PhysDrape’s 29–91 ms per garment on a V100 and ClothTransformer’s mesh-dependent 4.9–275 ms figures show why a full runtime neural cloth stack is not the right first move for 120 Hz deterministic armor. It may become a non-authoritative cinematic/Photo Mode lane later.

## Proposed deterministic packetization

Use a versioned cooked artifact, separate from glTF:

```text
ArmorCookV1
  header:
    schema_version: u16
    armor_asset_hash: [u8; 32]
    skeleton_hash: [u8; 32]
    solver_version_hash: [u8; 32]
    plate_count: u16
    flexible_piece_count: u16

  plate[stable_id order]:
    parent_joint: u16
    pivot_mm: i32[3]
    axis_q30: i32[3]
    rest_rotation_q15: i16[4]
    limit_min_millirad: i32
    limit_max_millirad: i32
    max_velocity_millirad_s: i32
    clearance_um: u32
    proxy_id: u16

  flexible_piece:
    vertex_count: u32
    indices/positions: cooked mesh payload
    joints_0: u16[4] per vertex
    weights_0: u16[4] or q15 equivalent per vertex
    corrective_basis_count: u8   # hard cap 8
    basis_scale_um: i32
    basis_delta_i16: packed signed deltas
    coefficient_lut_hash: [u8; 32]
```

Per-tick replay/truth state should contain only quantized joint/plate state and solver inputs. If a presentation packet is needed, cap it at `<=64 bytes per active piece/tick` (or, preferably, recompute from the authoritative pose). Never send a neural hidden state, floating-point mesh, or unversioned SDF query result over the deterministic boundary.

glTF mapping:

- rigid plates: separate nodes/skins with explicit pivots; custom `extras` for limits/proxy IDs;
- flexible shells: `JOINTS_0/WEIGHTS_0`, `POSITION/NORMAL/TANGENT`, and at most a small set of morph/corrective targets;
- interchange compression: `KHR_mesh_quantization` / `EXT_meshopt_compression` only if the cooker and validator support them;
- runtime: cook to the project’s binary, preserving content hashes and deterministic resource ordering.

No reviewed paper above ships a glTF exporter for this contract. Export compatibility is therefore an engineering adapter, not a paper feature.

## Exact acceptance measurements

The following are **proposed Just Dodge gates**, not copied benchmark claims. A route is rejected if any hard gate fails.

### A. Asset/binding gates

1. Khronos glTF Validator: **0 errors**; unknown required extensions rejected by the cooker.
2. Skinning: **0 unbound vertices**, `<=4` influences per vertex, finite values, and `max(abs(sum(weights)-1.0)) <= 1e-5` after cook/reimport. Preserve the project’s stronger observed canary (`2.98e-8` maximum normalization error) when possible.
3. Bind/rest round trip: after glTF export → reimport → cook, `max vertex drift <=0.25 mm`, `p99 <=0.05 mm`; rigid plate pivot drift `<=0.10 mm` and orientation drift `<=0.05 degrees`.
4. Stable identity: source GLB hash, skeleton hash, binding-tool version, and cooked blob hash recorded in the asset receipt.

### B. Extreme-pose and clearance gates

1. Fixture: at least 12 authored extremes (T/A reference, shoulder 0/90/150 degrees, elbow 30/90/150 degrees, crouch, hip flexion, torso twist, forearm pronation, knee flexion, foot plant) plus **100 held-out valid random poses** sampled inside joint limits. Run on every plate/flexible-piece combination.
2. Rigid plate/body clearance: **0 triangle intersections** and minimum signed clearance `>=0.50 mm` after the authored contact margin. Flexible/strap clearance: `>=0.20 mm` except explicitly designated contact seams.
3. Mechanical seams: no plate overlap or gap greater than **2.0 mm** at a closed seam unless the manifest explicitly marks it as an intentional sliding gap; intentional sliding gaps must remain within their authored `[min,max]` clearance.
4. Plate articulation: joint-limit violation `0`; pivot/axis error `<=0.25 degrees`; rest-to-posed plate volume change `<=0.10%` for rigid pieces.
5. Visual/corrective fidelity against the offline teacher on held-out poses: rigid plate anchor RMS `<=1.0 mm`, p99 `<=2.0 mm`; flexible piece RMS `<=3.0 mm`, p99 `<=6.0 mm`. Quantization must add `<=0.10 mm` RMS and `<=0.50 mm` p99 over the float reference.
6. No visible hard-surface candy-wrapper collapse, spikes, detached islands, or finger/hand helper leakage in the existing human visual QA contact sheet. Matrix determinant/scale checks are necessary but not sufficient; CPU-skinned vertex renders remain the acceptance surface.

### C. Contact/tunneling gates

1. Run 1,000 deterministic 120 Hz sweeps of weapon/body/armor proxy pairs, including the fastest authored attack and active-ragdoll impulse. CCD reports **0 tunneled contacts**.
2. Body/armor truth proxies: maximum penetration depth `<=0.50 mm` for the chosen contact margin; normal impulses are nonnegative and constraint rows are stably ordered.
3. Presentation mesh may not create a contact event. Every gameplay contact must be reproducible from the authoritative body/plate proxy IDs and solved witnesses alone.

### D. Stability and active-ragdoll gates

1. Hold every extreme pose for 240 truth ticks: residual plate drift `<=0.25 mm`, residual joint angle drift `<=0.10 degrees`, and no limit overshoot.
2. Apply a fixed impulse at three plate/body locations. The plate must visibly respond, settle within **8 ticks** after the impulse ends, and never teleport back to the planned pose.
3. ROM clamp, mass, and integrity fields remain unchanged by presentation correctives. The same combat event stream must produce identical damage/visual-state records.

### E. Runtime and determinism gates

1. One armored actor: armor solve plus correctives `p99 <=0.25 ms` on the release CPU at 120 Hz; four actors `p99 <=1.0 ms`; zero heap allocations in the fixed-step path.
2. Replay: **1,000 repeated runs** from identical initial state and plan produce byte-identical truth snapshot/event hashes. Cross-thread execution with the same canonical ordering must also match.
3. Quantized route: no floating-point neural inference, dynamic hash-map iteration, variable solver iteration count, or wall-clock dependency in truth.
4. Packet admission rejects schema/hash/asset mismatch, out-of-range joint limits, non-normalized weights, and `K>8` corrective bases.

### F. Offline research gates

For any neural/physics teacher promoted to R1 data generation:

- actor/asset-disjoint held-out split; no training pose leakage;
- report RMS, p99, minimum clearance, B2G/intersection count, and wall-clock training cost;
- compare against deterministic R0 and a no-corrective ablation;
- promote only if held-out flexible-piece RMS improves by `>=25%` at equal runtime budget and all A–E hard gates remain green;
- otherwise revert to R0 and keep the teacher as an authoring-only tool.

## License and provenance rules

- **PhysSkin/PhySkin/PhysDrape/ClothTransformer/SkinCells:** paper licenses or repository visibility are not code licenses. No code license was established for the checked sources where no official `LICENSE` existed. Do not vendor or ship implementations under “arXiv” alone.
- **NeuralClothSim:** public repository has an MIT `LICENSE`, but its README contains a conflicting “non-commercial use” sentence. Resolve with the authors/legal review before commercial distribution.
- **SNUG:** custom non-commercial-only license; reject for a commercial runtime.
- **GAPS/ISP:** public research repositories but no `LICENSE` file located in the checked official sources; treat as research reference only.
- **ClothTransformer dataset:** CC BY 4.0 dataset license, with third-party asset terms retained (SMPL, Make-It-Animatable, 3D Garments, Objaverse/per-object licenses). A dataset license does not grant a model/code/runtime license.
- **MPFB/Meshy assets:** keep the project’s existing asset provenance receipts. Do not assume a research garment dataset’s SMPL body or clothing license transfers to MPFB/Meshy armor.

## Final ranking

| Rank | Route | Why | Ship status |
|---:|---|---|---|
| 1 | R0 rigid plate graph + sparse offline binding | Lowest risk, deterministic, matches existing hinge/armor substrate | Implement now |
| 2 | R1 baked low-rank correctives, PhySkin-inspired | Captures neural/physics quality while exporting fixed data | Next bounded experiment |
| 3 | R2 offline contact-aware layered authoring | Useful for straps/faulds/underlayers; isolates expensive simulation | Authoring tool only |
| 4 | R3 PhySkin/PhysSkin neural presentation shadow | Frontier research value, but missing code/license/export proof | Shadow experiment |
| 5 | R4 full neural cloth/plate runtime | Runtime cost, determinism, licensing, and hard-plate mismatch remain unresolved | Defer/reject for truth |

The falsifier is simple: if R1 cannot beat ordinary sparse skinning by at least 25% on held-out flexible armor while preserving the exact runtime and replay gates, the correct decision is to keep R0 and spend effort on plate pivots, collision proxies, and authored corrective morphs—not to add a larger neural model.

## Primary-source links

- SkinCells: https://arxiv.org/html/2506.14714 — https://elrnv.com/projects/skincells/
- Robust Biharmonic Skinning: https://arxiv.org/html/2406.00238v2
- PhySkin: https://arxiv.org/html/2603.27013
- PhysSkin: https://zju3dv.github.io/PhysSkin/ — https://github.com/zju3dv/PhysSkin — https://arxiv.org/abs/2603.23194
- PhysDrape: https://arxiv.org/html/2602.08020
- ClothTransformer: https://arxiv.org/html/2605.27852v4 — https://yucrazing.github.io/clothtransformer/ — https://huggingface.co/datasets/YuCrazing1/ClothTransformer-dataset
- NeuralClothSim: https://4dqv.mpi-inf.mpg.de/NeuralClothSim/ — https://github.com/navamikairanda/neuralclothsim
- ISP: https://liren2515.github.io/page/isp/isp.html — https://github.com/liren2515/ISP
- GAPS: https://arxiv.org/html/2312.01490v2 — https://github.com/Simonhfls/GAPS
- SNUG: https://openaccess.thecvf.com/content/CVPR2022/html/Santesteban_SNUG_Self-Supervised_Neural_Dynamic_Garments_CVPR_2022_paper.html — https://github.com/isantesteban/snug
- Just Dodge armor contract: `docs/ARMOR-DAMAGE-SYSTEM.md`
- Just Dodge Mixamo/armor canary: `assets/foundation/v2/qa/sg02_lifecycle_kit_redo/evidence/path_b_mixamo_canary_manifest.json`
