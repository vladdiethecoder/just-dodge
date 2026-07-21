# Diffusion Motion Generation for Interactive Two-Fighter Combat — Research Decision (2026-07-17)

## Decision

**Do not replace the MotionBricks runtime backbone with vanilla MDM/MLD.** They are strong offline, single-person diverse-motion priors but their sampling latency, fixed-window generation, and lack of paired combat/environment conditioning make them the wrong direct runtime replacement.

**Recommended runtime direction:** retain MotionBricks as the fast tokenized motion/in-betweening engine and replace the narrow `TemporalGrabConditioner` with a **paired-actor, contact-and-scene-conditioned causal latent planner**. Its best architecture is an **ARDY/MotionStreamer-style causal latent sequence model with a dual-actor interaction encoder**, trained first as 4-step diffusion and then distilled to a 1–2-step latent-consistency head (the MotionLCM approach). The planner generates a short, diverse future target window asynchronously; MotionBricks may then in-between/retarget it, and the existing deterministic active-ragdoll/physics layer remains the sole contact/outcome authority.

This is an **augment-and-retrain** path, not a drop-in checkpoint swap. Released MotionBricks and ARDY APIs do not accept an opponent state, attack swept volume, weapon/grip state, or scene SDF as learned input; the new condition channels require paired training data and model training.

## Local baseline and the actual gap

`tools/qa/train_grab07_seq_conditioner.py` implements the owner-mandated sequence-model option:

- a three-layer 1-D temporal CNN with FiLM conditioning;
- input trajectory `[T, 102]` joint positions plus root `[T, 3]`;
- condition = target position, axis, normalized phase, and a reach-cell one-hot;
- output = residual pose and root trajectories; it deliberately has no post-decode FK mask.

That is a genuine temporal conditioner rather than the old static MLP, but it is **not yet an interaction generator**. It has no time-indexed opponent pose/velocity, opponent weapon geometry, contact graph, environment representation, or action/reaction history. Its current target is also derived from the source root at the contact frame. Thus it cannot learn the actual closed-loop question: *where must this fighter place a hand/weapon while the other fighter moves, blocks, retreats, and changes available contact geometry?*

The nearby P3 report proves that genuine target-conditioned prediction can generalize without post-decode masking, but it remains a research proof, not a paired-combat runtime checkpoint. The next model should preserve that no-masking rule while moving the control representation into the learned sequence backbone.

## Relevant diffusion landscape

| Model / paper | Architecture and useful idea | Multi-person / geometry status | Interactive-runtime verdict |
|---|---|---|---|
| **MDM** — [Tevet et al., ICLR 2023](https://guytevet.github.io/mdm-page/) | Transformer DDPM over raw motion; predicts clean sample rather than noise, enabling geometric location/velocity/foot-contact losses. Classifier-free conditioning trades fidelity for diversity; supports text, action, inpainting and joint-space editing. | Baseline is single-person; no native opponent or scene model. | **Offline teacher / baseline only.** Reported later comparisons put raw MDM at seconds per sequence, not combat-tick inference. Its explicit geometric-loss design is worth retaining. |
| **MLD** — [Chen et al., CVPR 2023](https://chenxin.tech/mld/) | VAE compresses a whole motion sequence; diffusion operates on continuous latent codes. The paper reports approximately two orders of magnitude less compute than raw diffusion. | Single-person HumanML3D/KIT-style conditioning; no paired contact or scene input. | **Offline or starting representation**, not sufficient as-is. Its VAE is the direct predecessor of the preferred latent planner. |
| **EMDM** — [Zhou et al., ECCV 2024](https://arxiv.org/html/2312.02256v3) | Conditional denoising diffusion GAN learns non-Gaussian large reverse steps plus geometric losses. It reports 0.02 s/action-conditioned and 0.05 s/text-conditioned sequence generation versus 2.5 s/12.3 s for its MDM comparisons. | Single-person and no contact/partner architecture. | **Useful few-step training idea**, but not evidence of two-fighter game latency. |
| **StableMoFusion** — [Huang et al., 2024](https://arxiv.org/html/2405.05691v2) | Conv1D U-Net, efficient sampling, cached text embeddings, low precision; detects foot contact and corrects foot motion during denoising. It reports 10 rather than 1000 iterations, but about 0.5 s/sample. | Foot-ground only; no partner/contact geometry. | **Quality/foot-contact reference, not runtime candidate.** |
| **MotionLCM** — [Dai et al., ECCV 2024](https://arxiv.org/html/2404.19759) | Distils MLD’s latent diffusion into a latent consistency model. A latent ControlNet conditions on initial joint trajectories and is supervised after decoding in motion space. Project reports one-step text generation around 30 ms/sample and controlled generation around 34 ms/sample. | Single-person; controls are mainly initial trajectories, not an opponent/scene representation. | **Best acceleration mechanism to adopt after paired training.** A 30–34 ms paper number is a planning latency, not a 120 Hz motor-tick budget. |
| **MotionStreamer** — [Xiao et al., ICCV 2025](https://zju3dv.github.io/MotionStreamer/) | Causal temporal autoencoder plus autoregressive model with a diffusion head to predict the next continuous latent. Each latent decodes causally/online; two-forward training limits autoregressive exposure/error accumulation. | Single person, text/history benchmarks; no pair or contact conditioning. | **Best temporal/streaming template.** Adapt the causal encoder and history protocol, not its single-actor checkpoint. |
| **ARDY** — [Zhao et al., SIGGRAPH 2026](https://research.nvidia.com/labs/sil/projects/ardy/) | Streaming, autoregressive two-stage transformer diffusion: explicit root trajectory first, latent body tokens second. It accepts variable history and sparse masked root, full-body, and end-effector pose/rotation constraints. | Released interface has sparse body constraints, but no opponent, weapon, SDF, swept volume, or limb-state channels. | **Best production-adjacent base architecture.** NVIDIA reports 33 ms for 4-step generation on RTX 4090 for a 40-frame/2 s window; use an asynchronous buffer. |
| **MotionBricks** — [Wang et al., SIGGRAPH 2026](https://nvlabs.github.io/motionbricks/) | Structured multi-headed discrete tokenizer, masked/BERT-style iterative token infilling, separate root and pose modules, plus smart primitives that make target keyframes. It reports 15,000 FPS / 2 ms and generates a new buffer only on new target keyframes, not every rendered frame. | Smart objects handle proxy keyframes and object binding, but the released G1 interface is whole-frame; it has no learned second actor/weapon/environment tensor. | **Keep as the low-latency renderer/in-betweener.** The public navigation checkpoint must not be misrepresented as combat-capable. |

### Two-person interaction architectures

| Work | How it models the pair | Combat relevance / limitation |
|---|---|---|
| **InterGen** — [Liang et al., IJCV 2024](https://arxiv.org/html/2304.05684v2) | Joint two-person representation; two weight-sharing transformer denoisers with mutual attention. Global relative performer relations and spatial-relation regularizers prevent treating the partner as unrelated noise. InterHuman includes boxing among its interaction categories. | Strong baseline for synchronized two-body generation. It is text-guided, offline/full-window and trained on non-commercial InterHuman data; no arbitrary game scene or weapon volumes. |
| **Two-in-One** — [Li et al., 2024](https://arxiv.org/html/2412.16670v1) | Treats two actors as one interaction sample: InterVAE creates a unified pair latent, then one conditional latent diffusion transformer generates it. Claims >4× faster than two independent branches. | Prefer this **unified latent** idea over independent self/opponent generation when a grab, bind, clash, or counter requires reciprocal timing. Still text/offline research, not combat runtime proof. |
| **It Takes Two** — [Shi et al., 2024](https://arxiv.org/html/2412.02419v1) | Dual-stream autoregressive diffusion conditions each actor on both actors’ past states plus an external trajectory. It uses overlap/transition blending for clip continuity. | The most directly applicable **reactive paired-state** topology, but its data/task are co-speech, not combat/contact forces. Reuse architecture only after combat training. |
| **InterControl** — [Wang et al., NeurIPS 2024](https://arxiv.org/html/2311.15864) | Adds a ControlNet to MDM and defines inter-person relations as time-indexed joint-pair contact/separation targets. It adds differentiable IK guidance during denoising for tight position alignment and supports arbitrary group size zero-shot. | Excellent constraint ABI reference for `hand-to-wrist`, `hand-to-weapon`, etc. **Do not ship its optimization/IK guidance as a substitute for learned conditioning**: it is expensive and conflicts with Just Dodge’s no post-decode pose-replacement intent. |

### Contact, target geometry, and environment methods

| Work | Mechanism | Transfer to combat |
|---|---|---|
| **CG-HOI** — [Diller & Dai, CVPR 2024](https://arxiv.org/html/2311.16097) | Jointly diffuses body motion, object transform, and body-surface-to-object contact distances; cross-attention couples all three. Contact-distance guidance is applied while sampling; geometry is a 256-point surface encoding. | Best direct precedent for a **contact token / signed-distance condition**. Substitute opponent body/weapon capsules and sampled weapon surfaces for an object, and learn human–human / weapon contact rather than merely projecting hands afterward. |
| **InterDiff** — [Xu et al., ICCV 2023](https://sirui-xu.github.io/InterDiff/) | Diffuses human and dynamic-object future jointly, then runs a physics-informed interaction correction in a contact-relative coordinate frame. | Validates contact-relative frames as an easier prediction space. Keep the relative transform representation, but runtime physics should validate the result instead of allowing neural correction to declare collision truth. |
| **OmniControl** — [Xie et al., ICLR 2024](https://neu-vi.github.io/omnicontrol/) | MDM with arbitrary sparse joint/time spatial controls; analytic spatial and realism guidance balance adherence and coherent unobserved joints. Demonstrates wrist, foot, head and multi-joint controls. | Useful training interface: sparse *time × joint × mask* controls. Its iterative analytic guidance is too slow (MotionLCM cites approximately 81 s/sequence) for runtime and does not encode an opponent. |
| **Sitcom-Crafter** — [Chen et al., 2025](https://arxiv.org/html/2410.10790v2) | Scene-aware human–human generator augments interaction space with synthetic binary SDF points and collision revision. | Evidence that an SDF/local occupancy representation can prevent partner/scene collision. Its generated scenes are synthetic and it still reports integration/transition limitations; use a real game-local SDF and combat data. |

## Required learned condition ABI

The condition must be time-indexed and masked, injected before root/body generation—not repaired after decoding:

```text
C[t] = {
  self_history:     local pose/velocity/contact history,
  opponent_history: relative root, joint rotations/positions, linear/angular velocity,
  interaction:      contact graph edges (self_joint, opponent_joint|weapon),
                    desired relative transform / distance / normal / phase / validity mask,
  targets:          target point or surface coordinate, target orientation/axis, event time window,
  geometry:         local signed-distance / occupancy samples for opponent body,
                    weapon, arena props, floor, and self-collision proxy,
  weapon_state:     transforms, grip sockets, one/two-hand/available/impaired categorical state,
  intent:           public revealed action, role (attacker/defender), stance/style, seed,
  future_masks:     which condition fields are known at each future frame
}
```

Implementation rules:

1. Express opponent and target signals in the actor-local/root-aligned frame **and** retain explicit world-root planning. This is the pair equivalent of ARDY’s explicit root + latent body split and avoids losing reach calibration to relative-motion integration drift.
2. Encode geometry with a bounded local field (capsules/SDF samples or a small point/voxel encoder) around each relevant effector and weapon. Do not feed an unbounded world mesh every planner call.
3. Train on paired sequences with symmetric actor swapping and role embeddings. For unarmed contact, use contact edges; for weapons, add a rigid socket-relative orientation loss and weapon trajectory/SDF conditions.
4. Add losses on 6D rotations, root/effector velocity and acceleration, foot-contact/slip, contact distance/relative velocity, weapon grip transform, pair penetration, and condition dropout for classifier-free diversity. Evaluate held-out *pair identity, opponent response, target placement, arena layout, and action/reaction cell* splits.
5. The neural output is a proposal packet only. Quantize/hash/admit it before active-ragdoll tracking; deterministic articulated physics decides collision, balance, hit, injury, and outcome. A plan must never change a resolved truth tick.

## Temporal consistency and game scheduling

A diffusion model cannot be invoked synchronously at Just Dodge’s 120 Hz truth cadence (8.333 ms/tick):

- Raw MDM/MLD/full-sequence interaction diffusion is offline.
- EMDM, MotionLCM, and ARDY reduce sampling to a planning-scale latency, but their published measurements are not two-fighter combat measurements on this project hardware.
- MotionBricks’ reported 2 ms is promising, but is an upstream claim that must be measured with the actual exported model, planner constraints, actor count, and GPU contention.

Use a **receding-horizon asynchronous service**:

1. At Reveal or public replan, snapshot public state and emit a request with a deterministic seed and the condition ABI.
2. Generate `H` future frames in a worker (initially 0.32–0.8 s; ARDY’s smallest released window is 8 frames/25 Hz = 320 ms). Keep the last displayed context frames in the next request.
3. Validate finite transforms, rotation quality, condition error, penetration, foot/contact metrics, controller tracking feasibility, latency/deadline, and model/normalization hashes. Then quantize/hash the accepted plan.
4. Consume the accepted buffer at rendering/control rate; begin next replan before buffer depletion. Interrupt only at a public planning boundary and blend/overlap at the **target-window level**, never by mutating historical plan frames.
5. For two actors, generate a **single pair packet** or coordinated packets from one shared latent sample. Independent per-character sampling is the primary cause of missed grabs and hand/weapon pass-through.

The packet provides visual intent and motor targets; it is not a simulation result. If the neural job misses deadline, preserve the previous accepted plan or use a deterministic truth-safe behavior—not a silently invented hit pose.

## Architecture recommendation and sequencing

### A. Recommended now — augment MotionBricks with a paired causal latent planner

**Architecture:**

```text
public snapshot + C[t]
  -> shared dual-actor interaction encoder (cross-attention / graph edges)
  -> explicit-root planner (both roots jointly)
  -> causal VAE body latent planner (both bodies jointly)
  -> 4-step conditional diffusion during training/quality lane
  -> 1–2-step latent-consistency distillation for serving
  -> decoded future target window
  -> MotionBricks constrained in-betweening / retarget
  -> bounded active-ragdoll motors -> deterministic physics
```

Why this is the preferred path:

- It fixes the exact grab failure: reach is learned from full temporal, opponent-relative, target-surface data rather than a static target cell or a self-only residual sequence.
- It combines the strongest complementary ideas: ARDY’s root/body factorization and masked sparse constraints, Two-in-One/InterGen’s joint pair representation, CG-HOI’s contact/geometry coupling, MotionStreamer’s causal streaming, and MotionLCM’s practical distillation.
- It retains MotionBricks where it is currently strongest: sub-frame low-latency latent in-betweening and smart-primitive integration.
- It is compatible with the project’s immutable accepted-plan and physics-authority boundaries.

**Status:** research build. No cited released checkpoint has this complete opponent + weapon + SDF combat ABI.

### B. Lowest-risk near-term experiment — extend ARDY’s masked constraint compiler

Fork/extend the ARDY two-stage model with the condition ABI, first without a weapon and only for `grab/reach/withdraw` two-person windows. Start with a joint pair latent, explicit dual-root stage, hand-to-torso contact target, and opponent-relative root/hand history. This is the highest-confidence way to test whether diffusion improves held-out reach calibration.

Do not declare success from a single target or a zero error: use held-out actors/pairs/target cells, condition ablation, no condition replacement, and raw decoded contact error before any physics tracker. If the result beats the temporal CNN on unseen pair dynamics and meets planning latency, distil the trained latent model with MotionLCM.

### C. Alternatives that should *not* replace the current conditioner directly

- **MDM/MLD/InterGen checkpoints:** wrong skeleton/data domain and offline; useful baselines/teachers only.
- **InterControl/OmniControl guidance loops:** valuable for constraint design and offline evaluation, but do not satisfy an interactive 120 Hz combat runtime or the project’s learned-conditioning requirement by themselves.
- **MotionLCM alone:** fast, but no opponent/contact/scene representation. Distilling an inadequate single-person teacher will only make the inadequate model faster.
- **MotionStreamer alone:** correct streaming topology, but its HumanML3D/BABEL training does not establish combat/contact plausibility.
- **Full replacement of MotionBricks today:** unjustified. MotionBricks has the strongest published real-time engine integration, while the project lacks a combat-trained paired diffusion checkpoint and a live neural path.

## Data requirements and evidence gates

The model architecture is not a substitute for paired combat data. The local combat-corpus survey identifies the usable starting split:

- **Harmony4D (MIT):** strongest source of multi-person close contact (grappling, wrestling, MMA, karate, fencing), with SMPL meshes/poses and contact-oriented annotations.
- **Kyokushin Karate (CC0):** Vicon dual-subject opponent captures, strong strikes, spacing, shield/opponent contact proxy.
- **CMU direct:** permissive strike/boxing/sword motion plus one paired arm-wrestle recording, but not a grappling corpus.
- Keep non-commercial or model-training-restricted data out of a commercial teacher corpus; in particular, do not use BONES-SEED as a generative-motion teacher without a license that authorizes this use.

Promotion gates must include:

1. paired held-out contact/endpoint/weapon-relative-transform error;
2. contact precision/recall, penetration, foot sliding, grip, and root/path metrics;
3. diversity over fixed public intent while preserving geometry constraints;
4. p50/p95/p99 generation, queue, GPU, and controller-tracking times for 1, 2, and stress-count actors on target hardware;
5. causal long-run/interruption continuity and replay identity from admitted packet bytes;
6. full-rate visual review of strikes, blocks, grabs, dodges, whiffs, collisions, and interrupted plans; and
7. a physics-authority falsifier proving altered neural samples cannot alter the deterministic combat outcome without corresponding simulated contact.

## Bottom line

Diffusion is **better than the current self-only temporal CNN as a research path for diverse, conditioned, reciprocal combat planning**, but only after it becomes a *paired, geometry-aware, causal* diffusion system. Vanilla MDM/MLD is not that system. The practical winner is a **dual-actor ARDY/MotionStreamer-style latent planner, accelerated by MotionLCM, coupled to MotionBricks rather than replacing it**. Use deterministic physics to validate and execute every accepted proposal.

## Primary sources

- MDM — https://guytevet.github.io/mdm-page/
- MLD — https://chenxin.tech/mld/
- EMDM — https://arxiv.org/html/2312.02256v3
- MotionLCM — https://arxiv.org/html/2404.19759
- MotionStreamer — https://zju3dv.github.io/MotionStreamer/
- ARDY — https://research.nvidia.com/labs/sil/projects/ardy/
- MotionBricks — https://arxiv.org/html/2604.24833
- InterGen — https://arxiv.org/html/2304.05684v2
- Two-in-One — https://arxiv.org/html/2412.16670v1
- It Takes Two — https://arxiv.org/html/2412.02419v1
- InterControl — https://arxiv.org/html/2311.15864
- OmniControl — https://neu-vi.github.io/omnicontrol/
- CG-HOI — https://arxiv.org/html/2311.16097
- InterDiff — https://sirui-xu.github.io/InterDiff/
- Sitcom-Crafter — https://arxiv.org/html/2410.10790v2
