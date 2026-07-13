# Frontier Humanoid Combat / Martial-Arts Control — 2025–2026 Research Review

**Date:** 2026-07-09
**Scope:** Physics-based whole-body controllers, diffusion/transformer motion policies, language/action-conditioned control, contact-rich manipulation, adversarial/self-play, and motion generation constrained by physical goals. Primary sources and code only.
**Context:** Just Dodge uses MotionBricks-driven animation and simultaneous hidden actions. Combat outcomes must emerge from geometry, balance, momentum, contact, injury, grip, and constraints — not scripted matchup tables.
**Status:** Research lead inventory, not project canon. Performance, licensing, code availability and deterministic replay claims require local reproduction before adoption.

---

## Key Finding

No reviewed method currently satisfies Just Dodge's full requirement: **named hidden intent → two-agent emergent physical melee → deterministic 60 Hz replay → deformable injury truth**. The most directly applicable published motion stack is a latent generative backbone plus action-conditioned smart primitives (MotionBricks / GR00T-WholeBodyControl), potentially informed by:

1. **Adversarial/self-play latent combat policy** (RoboStriker) for emergent paired tactics.
2. **Robust multi-skill gating** (RPG) for interruptible combat-move transitions.
3. **Contact-agnostic whole-body control** (Embrace Collisions / InterMimic / Whole-Body MPPI) if the game needs grounded, physics-truth reactions rather than purely kinematic presentation.

Pure kinematic diffusion (Kimodo, BeyondMimic) is excellent for authoring clips and demonstration data, but it is not a physics combat resolver and must stay on the **presentation-only** side of the truth boundary.

---

## Taxonomy of Relevant Methods

| Method | Category | Conditioning / Intent | Physics? | Real-time? | Code / Source | Relevance to Just Dodge |
|--------|----------|----------------------|----------|------------|---------------|------------------------|
| **MotionBricks** | Latent generative smart-primitive backbone | Velocity, heading, style, object keyframes, keyframe poses | Kinematic generation; outputs drive physics tracker in robotics | Yes — 15 k FPS, 2 ms | `NVlabs/GR00T-WholeBodyControl/motionbricks`, arXiv:2604.24833 | Core animation engine; smart primitives map intent to emergent motion clips |
| **SONIC (GEAR-SONIC)** | Scaled motion-tracking foundation model | Motion reference, VR teleop tokens, VLA tokens | Yes — physics tracker + kinematic planner | Yes | `NVlabs/GR00T-WholeBodyControl`, arXiv:2511.07820 | Tracker that can execute MotionBricks-generated references; token interface for high-level commands |
| **RoboStriker** | MARL self-play for humanoid boxing | Latent combat strategy → motion tracker | Yes — full physics + contact | Yes (policy inference) | Project page + arXiv:2601.22517 (no public repo found) | Best existing architecture for emergent paired combat tactics |
| **RPG** | Robust policy gating for fighting skills | Named skill commands + locomotion | Yes — physics-based | Yes | arXiv:2604.21355 | Smooth interruptible transitions between named attacks/parries/dodges |
| **KungfuBot / PBHC** | Physics-based dynamic skill imitation | Reference motion (kungfu/dance) | Yes — full-body RL | Yes | `TeleHuman/PBHC`, arXiv:2506.12851 | Highly dynamic martial-arts motion tracking; single-agent, no combat |
| **InterMimic** | Universal whole-body human-object interaction | Imperfect MoCap references | Yes — physics sim | Yes | `Sirui-Xu/InterMimic`, arXiv:2502.20390 | Contact-rich manipulation / environment interaction; can correct contact artifacts |
| **AnyBody** | Free-form keypoint-conditioned controller | Arbitrary subset of body keypoints | Yes — physics tracker | Yes | `hazel-hammer/Anybody`, arXiv:2606.29209 | Sparse intent → coordinated whole-body motion; useful for teleop/authoring |
| **Kimodo** | Large-scale kinematic motion diffusion | Text, keyframes, 2D paths, joint constraints | No (kinematic) | Offline / batch | `nv-tlabs/kimodo`, arXiv:2603.15546 | Authoring combat demonstration clips, NOT runtime resolver |
| **BeyondMimic** | Guided diffusion + motion tracking | Goals / joystick / obstacle avoidance | Yes — physics tracker executes generated refs | Yes (tracker); diffusion slower | Project page + arXiv:2508.08241 | Downstream task composition via classifier guidance; useful for clip variation |
| **ALMI** | Adversarial upper/lower-body policy | Velocity command + upper-body motion | Yes — full physics | Yes | `TeleHuman/ALMI-Open`, arXiv:2504.14305 | Separates locomotion and upper-body action; stable loco-manipulation |
| **Embrace Collisions** | Contact-agnostic whole-body control | Keyframe motion commands | Yes — full-body contacts | Yes | Project page + arXiv:2502.01465 | Ground contact with non-feet/non-hands body parts; falls, rolls, getups |
| **Neural Assistive Impulses (NAI)** | Exaggerated physics-based animation | Skill reference + learned residual impulses | Yes — with external impulses | Yes | arXiv:2604.05394 | Anime-style exaggerated combat moves that violate normal physics |
| **Whole-Body MPPI** | Sampling-based MPC with MuJoCo | Task cost / goal | Yes — full physics | Yes (on real quadruped) | `jrapudg/RTWholeBodyMPPI`, arXiv:2409.10469 | Emergent contact sequencing; expensive, best for short-horizon reactions |

---

## Method Cards

### 1. MotionBricks (SIGGRAPH 2026)
- **Paper:** Wang et al., *MotionBricks: Scalable Real-Time Motions with Modular Latent Generative Model and Smart Primitives*, arXiv:2604.24833.
- **Code:** `https://github.com/NVlabs/GR00T-WholeBodyControl/tree/main/motionbricks`
- **Architecture:**
  - Structured multi-headed VQVAE tokenizer → encoder/decoder/quantizer.
  - Root module: predicts timing + global/local root trajectory.
  - Pose module: masked generative transformer predicts pose tokens.
  - Smart primitives (locomotion / object) convert high-level commands into sparse keyframe constraints.
- **Intent → Execution:**
  - **Smart locomotion:** velocity + heading + style → proxy keyframes → backbone fills natural motion.
  - **Smart object:** object-relative keyframes → backbone fills approach, contact, follow-through.
  - Supports arbitrary combinations of constraints; zero-shot to new tasks.
- **Emergence:** Motion is not looked up; it is generated from latent space conditioned on sparse intent.
- **Limitations:**
  - No built-in two-agent combat primitive; object/smart primitives are single-actor.
  - No physics truth in the animation layer — contacts are implied by mocap priors, not enforced by a sim.
  - Full release (complete training pipeline + GR00T embedding) is still pending.

### 2. SONIC / GEAR-SONIC (NVIDIA 2025–2026)
- **Paper:** Luo et al., *SONIC: Supersizing Motion Tracking for Natural Humanoid Whole-Body Control*, arXiv:2511.07820.
- **Code:** Same GR00T-WholeBodyControl repo.
- **Architecture:**
  - 42 M-param physics-based motion tracker trained on 100 M+ frames.
  - Universal token space unifies robot, human, and hybrid motion inputs.
  - Real-time kinematic planner + C++ inference stack.
- **Intent → Execution:** High-level planner or VLA emits tokens/keyframes → tracker executes physically plausible whole-body motion.
- **Emergence:** Tracker generalizes to unseen motions; no per-motion reward engineering.
- **Limitations:** Tracker follows references; it does not itself perform adversarial combat reasoning.

### 3. RoboStriker (2026)
- **Paper:** Yin et al., *RoboStriker: Hierarchical Decision-Making for Autonomous Humanoid Boxing*, arXiv:2601.22517.
- **Code:** Project page only; public repo not located in this review.
- **Architecture (three-stage):**
  1. **Motion tracker:** DeepMimic-style policy learns boxing skill repertoire from MoCap.
  2. **Latent manifold:** Skills distilled into a bounded spherical latent space (topological latent distillation).
  3. **LS-NFSP:** Latent-Space Neural Fictitious Self-Play — competing agents evolve strategies in latent action space, not raw motor space.
- **Intent → Execution:** Named strategic intent (attack, defend, feint) is selected at a high level; the latent policy and physics tracker produce emergent punches, slips, counters, footwork.
- **Emergence:** Paired tactics arise from self-play under physical constraints; zero-shot sim-to-real shown.
- **Limitations:**
  - Single boxing morphology (Unitree G1, 29 DoF).
  - No public code as of review date.
  - Training is heavy; not designed for player-vs-player rollback determinism.

### 4. RPG — Robust Policy Gating (2026)
- **Paper:** Xin et al., *RPG: Robust Policy Gating for Smooth Multi-Skill Transitions in Humanoid Fighting*, arXiv:2604.21355.
- **Architecture:**
  - Train multiple expert policies on distinct fighting skills (punch, sword swing, jump, kick).
  - Policy-transition and temporal randomization during expert training.
  - Lightweight gating network blends expert actions, regularized for torque/contact smoothness.
  - Integrated locomotion + fighting pipeline.
- **Intent → Execution:** Player triggers a named skill → gating network composes experts → physics policy executes.
- **Emergence:** Smooth transitions and recoveries even from abrupt interrupts; human-like prolonged combat.
- **Limitations:**
  - Skill set is fixed by trained experts; novel actions require new experts.
  - No explicit opponent modeling or strategic self-play.

### 5. KungfuBot / PBHC (NeurIPS 2025)
- **Paper:** Xie et al., *KungfuBot: Physics-Based Humanoid Whole-Body Control for Learning Highly-Dynamic Skills*, arXiv:2506.12851.
- **Code:** `https://github.com/TeleHuman/PBHC`
- **Architecture:**
  - Motion processing: extract → filter by physical feasibility → contact mask → correction → retarget.
  - Adaptive motion tracking via bi-level optimization of tracking tolerance.
  - Asymmetric actor-critic with reward vectorization.
- **Intent → Execution:** Reference motion (e.g., “roundhouse kick”) → adaptive tracker → G1 executes.
- **Emergence:** Physical feasibility filtering allows highly dynamic skills that would otherwise fail.
- **Limitations:** Single-agent imitation; no combat interaction.

### 6. InterMimic (CVPR 2025)
- **Paper:** Xu et al., *InterMimic: Towards Universal Whole-Body Control for Physics-Based Human-Object Interactions*, arXiv:2502.20390.
- **Code:** `https://github.com/Sirui-Xu/InterMimic`
- **Architecture:**
  - Teacher policies on small interaction subsets mimic, retarget, and refine imperfect MoCap.
  - Student distillation with online teacher supervision + RL fine-tuning.
- **Intent → Execution:** Interaction reference → refined physics rollout.
- **Emergence:** Contacts are corrected by physics; object geometry/generalization handled by unified policy.
- **Limitations:** Teacher training can fail on severely corrupted references; focused on object interaction, not combat.

### 7. AnyBody (2026)
- **Paper:** Li et al., *AnyBody: Free-Form Whole-Body Humanoid Control from Arbitrary Keypoint Guidance*, arXiv:2606.29209.
- **Code:** `https://github.com/hazel-hammer/Anybody`
- **Architecture:**
  - Privileged teacher tracker → distilled encoder-decoder with spherical latent.
  - Transformer keypoint encoder accepts arbitrary body-keypoint subsets.
  - Residual corrector for downstream RL tasks.
- **Intent → Execution:** Sparse keypoints (e.g., wrist trajectory, torso position) → full-body coordinated motion.
- **Emergence:** Whole-body motion is synthesized from partial intent; retargeting-free.
- **Limitations:** No combat or opponent awareness; keypoints must be provided.

### 8. Kimodo (NVIDIA 2026)
- **Paper:** Rempe et al., *Kimodo: Scaling Controllable Human Motion Generation*, arXiv:2603.15546.
- **Code:** `https://github.com/nv-tlabs/kimodo`
- **Architecture:**
  - Two-stage transformer diffusion denoiser trained on 700 h optical mocap.
  - Text + keyframes + 2D paths + joint constraints as conditioning.
- **Intent → Execution:** Text/constraint prompt → kinematic motion clip.
- **Emergence:** High-quality stylistic variation; G1 retargeted output available.
- **Limitations:**
  - Kinematic, not physics-grounded at generation time.
  - Not real-time interactive control; best for clip authoring / data augmentation.

### 9. BeyondMimic (2025)
- **Paper:** Liao et al., *BeyondMimic: From Motion Tracking to Versatile Humanoid Control via Guided Diffusion*, arXiv:2508.08241.
- **Architecture:**
  - Compact motion tracker with only three regularization terms + task reward.
  - Unified latent diffusion model for goal specification and skill composition.
  - Classifier guidance at test time for unseen tasks (inpainting, teleop, obstacle avoidance).
- **Intent → Execution:** Goal / joystick / obstacle cost → diffusion plan → tracker executes.
- **Emergence:** Composition of agile skills without task-specific retraining.
- **Limitations:** Diffusion planning is slower than MotionBricks backbone; combat not demonstrated.

### 10. ALMI (NeurIPS 2025)
- **Paper:** Shi et al., *Adversarial Locomotion and Motion Imitation for Humanoid Policy Learning*, arXiv:2504.14305.
- **Code:** `https://github.com/TeleHuman/ALMI-Open`
- **Architecture:**
  - Lower-body locomotion policy vs. upper-body motion-tracking policy trained adversarially.
  - Iterative updates converge to coordinated equilibrium.
- **Intent → Execution:** Velocity command + upper-body reference → stable whole-body behavior.
- **Emergence:** Lower body learns robustness to disruptive upper-body motions; upper body learns tracking despite locomotion instability.
- **Limitations:** No combat interaction; open-loop upper-body control.

### 11. Embrace Collisions (2025)
- **Paper:** Zhuang & Zhao, *Embrace Collisions: Humanoid Shadowing for Deployable Contact-Agnostics Motions*, arXiv:2502.01465.
- **Architecture:**
  - Keyframe-based motion commands encoded by transformer.
  - Multi-critic advantage mixing for sparse task vs. dense regularization rewards.
  - New termination conditions for arbitrary base orientation.
- **Intent → Execution:** Keyframe command → whole-body policy → ground rolling, getups, crawling.
- **Emergence:** Contacts with knees, torso, hands emerge without prespecified contact schedule.
- **Limitations:** No opponent; extreme contacts are hard to tune safely.

### 12. Neural Assistive Impulses (NAI) (2026)
- **Paper:** Wang & Benes, *Neural Assistive Impulses: Synthesizing Exaggerated Motions for Physics-based Characters*, arXiv:2604.05394.
- **Architecture:**
  - Analytic high-frequency inverse-dynamics impulse + learned low-frequency residual.
  - Confidence-aware dynamics gate blends the two.
  - Impulse-space control avoids force-spike training instability.
- **Intent → Execution:** Exaggerated reference (e.g., aerial rising kick + mid-air dash) → hybrid policy applies assistive impulses.
- **Emergence:** Physically impossible anime maneuvers become reproducible in a standard simulator.
- **Limitations:** Requires external assistive impulses; combat interaction not shown.

### 13. Whole-Body MPPI (ICRA 2025)
- **Paper:** Alvarez-Padilla et al., *Real-Time Whole-Body Control of Legged Robots with Model-Predictive Path Integral Control*, arXiv:2409.10469.
- **Code:** `https://github.com/jrapudg/RTWholeBodyMPPI`
- **Architecture:**
  - Sampling-based MPC (MPPI) using MuJoCo dynamics and finite-difference derivatives.
  - Single policy for locomotion + manipulation; contacts emergent.
- **Intent → Execution:** Task cost → sampled rollouts → selected action.
- **Emergence:** Whole-body contact sequences (box push, climb, rough terrain) without contact pre-specification.
- **Limitations:**
  - Real-time on quadruped; humanoid combat horizon would be expensive.
  - No learned motion prior → motions can look less human-like than imitation methods.

---

## Recommended Architecture for Just Dodge

Given the project constraints (MotionBricks-only animation source, simultaneous hidden actions, deterministic combat truth), the most implementable path is:

```
┌─────────────────────────────────────────────────────────────────────┐
│  HIGH-LEVEL COMBAT INTENT (YOMI-style, hidden until reveal)         │
│  Named intents: thrust / slash / feint / dodge / parry / grapple    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│  SMART PRIMITIVE AUTHORING LAYER                                    │
│  • Per-intent keyframe templates (tell keyframes, hit window,       │
│    recovery keyframes, root displacement envelope).                 │
│  • Opponent-relative binding: target distance, facing angle,        │
│    height, weapon/side constraints.                                 │
│  • Injury/ROM constraints applied as post-decode clamps/IK.         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│  MOTIONBRICKS LATENT BACKBONE (ONNX in Rust)                        │
│  Root module → pose module → VQVAE decoder → local/root transforms  │
│  Sampling path must be made deterministic and proven by replay     │
│  hashes; publication/code availability does not establish parity.  │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│  RETARGET + RICH SKELETON                                           │
│  34-joint G1 output → ~103-bone rich skeleton → 24-bone mannequin   │
│  Spine spline interpolation, weapon socket IK, finger/toe procedural│
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│  COMBAT TRUTH RESOLVER (deterministic, 60 Hz, fixed-point where     │
│  possible)                                                          │
│  • Swept capsule continuous collision between weapon/body proxies.  │
│  • Momentum/impulse, balance, grip, contact, tissue-layer injury.   │
│  • Resolver emits discrete injury events; presentation reacts.      │
└─────────────────────────────────────────────────────────────────────┘
```

### Where emergent execution comes from

| Emergent property | Source |
|-------------------|--------|
| **Tell shape and timing** | Authoring smart-primitive keyframes; MotionBricks interpolates the in-between with natural motion prior. |
| **Hit/whiff/miss** | Geometry + swept collision + distance/velocity at reveal frame; not a table lookup. |
| **Injury consequence** | Tissue-layer model driven by impact force, impulse, edge alignment, and defender state. |
| **Balance / knockback** | Momentum transfer from resolver applied to root trajectory / next primitive selection. |
| **Interrupts / feints** | Replanning on intent change; MotionBricks deterministic replanning preserves continuity. |
| **Stance transitions** | RPG-style policy gating or smart-locomotion style blending. |
| **Adaptive opponent tactics** | RoboStriker-style latent-space self-play for AI (offline training; runtime policy inference). |

### Methods to adopt vs. isolate

- **Adopt as animation source:** MotionBricks (already project canon).
- **Adopt for smooth skill transitions:** RPG gating, or MotionBricks smart-locomotion style blending.
- **Adopt for AI opponent tactics:** RoboStriker LS-NFSP pattern, but train offline and import the latent policy as a fixed opponent brain.
- **Adopt for contact-rich environment reactions:** InterMimic / Embrace Collisions physics-correction ideas, but only for presentation ragdoll, never for combat truth.
- **Use for clip authoring only:** Kimodo, BeyondMimic — generate training/reference clips for smart primitives.
- **Use cautiously / future work:** Whole-Body MPPI for short-horizon balance recovery; NAI for exaggerated special moves.

---

## Critical Limitations

1. **No public two-agent combat generative model.** RoboStriker is the closest but has no public code; it would need to be reimplemented or its architecture adapted.
2. **MotionBricks is not a combat simulator.** It generates kinematic motion. Combat truth must be a separate deterministic resolver; the model only provides poses and plausible contact timing.
3. **Smart primitives for combat are unbuilt.** NVIDIA demonstrates locomotion and object interaction, not paired sword/empty-hand/fist combat. Authoring per-weapon keyframe templates is custom work.
4. **Physics-based policies mutate physical state.** DeepMimic/AMP/RoboStriker/InterMimic policies own the body state. In Just Dodge, physics must be **presentation-only** and isolated from truth to guarantee deterministic replay and rollback parity.
5. **Determinism vs. sampling.** Stochastic sampling can break replay parity. A fixed/argmax path may be implementable, but must not be called deterministic until repeated and cross-platform hash tests prove it.
6. **Skeleton mismatch.** MotionBricks outputs a 34-joint G1 skeleton. Rich hit zones and readable tells require an intermediate ~103-bone skeleton and retargeting, which is not provided by NVIDIA.

---

## Primary Sources

1. Wang, T., et al. (2026). *MotionBricks: Scalable Real-Time Motions with Modular Latent Generative Model and Smart Primitives.* arXiv:2604.24833. Code: `https://github.com/NVlabs/GR00T-WholeBodyControl/tree/main/motionbricks`
2. Luo, Z., et al. (2025). *SONIC: Supersizing Motion Tracking for Natural Humanoid Whole-Body Control.* arXiv:2511.07820. Code: `https://github.com/NVlabs/GR00T-WholeBodyControl`
3. Yin, K., et al. (2026). *RoboStriker: Hierarchical Decision-Making for Autonomous Humanoid Boxing.* arXiv:2601.22517.
4. Xin, Y., et al. (2026). *RPG: Robust Policy Gating for Smooth Multi-Skill Transitions in Humanoid Fighting.* arXiv:2604.21355.
5. Xie, W., et al. (2025). *KungfuBot: Physics-Based Humanoid Whole-Body Control for Learning Highly-Dynamic Skills.* arXiv:2506.12851. Code: `https://github.com/TeleHuman/PBHC`
6. Xu, S., et al. (2025). *InterMimic: Towards Universal Whole-Body Control for Physics-Based Human-Object Interactions.* arXiv:2502.20390. Code: `https://github.com/Sirui-Xu/InterMimic`
7. Li, S., et al. (2026). *AnyBody: Free-Form Whole-Body Humanoid Control from Arbitrary Keypoint Guidance.* arXiv:2606.29209. Code: `https://github.com/hazel-hammer/Anybody`
8. Rempe, D., et al. (2026). *Kimodo: Scaling Controllable Human Motion Generation.* arXiv:2603.15546. Code: `https://github.com/nv-tlabs/kimodo`
9. Liao, Q., et al. (2025). *BeyondMimic: From Motion Tracking to Versatile Humanoid Control via Guided Diffusion.* arXiv:2508.08241.
10. Shi, J., et al. (2025). *Adversarial Locomotion and Motion Imitation for Humanoid Policy Learning.* arXiv:2504.14305. Code: `https://github.com/TeleHuman/ALMI-Open`
11. Zhuang, Z., & Zhao, H. (2025). *Embrace Collisions: Humanoid Shadowing for Deployable Contact-Agnostics Motions.* arXiv:2502.01465.
12. Wang, Z., & Benes, B. (2026). *Neural Assistive Impulses: Synthesizing Exaggerated Motions for Physics-based Characters.* arXiv:2604.05394.
13. Alvarez-Padilla, J., et al. (2025). *Real-Time Whole-Body Control of Legged Robots with Model-Predictive Path Integral Control.* ICRA 2025 / arXiv:2409.10469. Code: `https://github.com/jrapudg/RTWholeBodyMPPI`
