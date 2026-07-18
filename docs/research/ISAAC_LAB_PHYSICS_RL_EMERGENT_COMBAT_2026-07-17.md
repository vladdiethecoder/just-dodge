# Isaac Lab / Physics RL for Emergent Combat

**Date:** 2026-07-17  
**Status:** research proposal, not runtime canon or an implementation claim.  
**Question:** can learned physical controllers make Just Dodge duels feel alive—circling, timing, roundhouse kicks, dodges, parries, recovery, and stylized special arts—where a kinematic generator alone cannot?

## Outcome

**Yes, with an important qualification:** reinforcement learning can learn dynamic martial-arts execution and paired combat behavior, but `reward shaping alone` is a poor plan. The viable stack is **motion prior / imitation → contact-aware active-ragdoll execution → curriculum → self-play**, with a learned planner operating above constrained motor control. MotionBricks should propose readable, sparse or short-horizon motion targets; a physics-trained controller should execute those targets under actual impacts. Only the deterministic Just Dodge simulation may declare a hit, parry, balance loss, injury, or outcome.

The recommended bounded experiment is **CV-LDC — Contact-Verified Latent Duel Controller**. It is an offline Isaac Lab training lane and a deterministic-runtime admission contract, not a replacement combat simulator.

---

## 1. What the evidence actually supports

| Question | Answer | Primary evidence |
|---|---|---|
| Can a physics policy learn martial-arts movement? | Yes. DeepMimic demonstrated physics-based imitation across martial arts; KungfuBot explicitly targets highly dynamic kungfu and includes a roundhouse-kick example. | [DeepMimic (2018)](https://arxiv.org/abs/1804.02717); [KungfuBot (2025)](https://arxiv.org/abs/2506.12851) |
| Can two simulated characters learn fighting interaction rather than isolated moves? | Yes, in research settings. MAAIP learns single-character motion and a multi-character interaction prior from boxing/full-body martial-arts demonstrations. RoboStriker adds a motion-tracker, latent skill manifold, and latent-space self-play for boxing. | [MAAIP (2023)](https://arxiv.org/abs/2311.02502); [RoboStriker (2026)](https://arxiv.org/abs/2601.22517) |
| Is Isaac Lab suitable for the *training* side? | Yes. Isaac Gym established GPU-resident simulation-to-tensor RL; current Isaac Lab is its maintained Isaac Sim framework, with PhysX, vectorized environments, contact sensing, domain randomization, Unitree humanoids, and RL/IL workflows. | [Isaac Gym (2021)](https://arxiv.org/abs/2108.10470); [Isaac Lab docs](https://isaac-sim.github.io/IsaacLab/main/index.html) |
| Does this make MotionBricks contact-correct? | No. MotionBricks is a fast kinematic generative backbone and smart-primitive interface. Its released public wrapper does not expose opponent, weapon-clearance, injury, or contact-conditioning channels. Those require a learned extension/retraining, and simulated contacts must still win. | [MotionBricks (2026)](https://arxiv.org/abs/2604.24833); [released repository](https://github.com/NVlabs/GR00T-WholeBodyControl/tree/main/motionbricks) |
| Can RL create anime/cinematic movement? | Partly. AMP learns a physical style prior from clips, while kinematic style-transfer work can supply references. Motions that violate momentum conservation require an explicitly modeled game ability/impulse, not a hidden animation correction. | [AMP (2021)](https://arxiv.org/abs/2104.02180); [Neural Assistive Impulses (2026)](https://arxiv.org/abs/2604.05394) |

### The critical distinction

A kinematic generator can make a kick *look* good. A physics controller can decide whether that kick remains balanced after a shin collision, misses because the opponent moved, is redirected by a parry, or turns into a stumble/recovery. The latter is the source of credible emergence.

No paper found demonstrates the exact Just Dodge combination of simultaneous hidden intent, weapon/body contact, deterministic cross-replay, localized injury, and cinematic presentation. Treat the literature as architecture evidence, not proof that the project requirement is solved.

---

## 2. Project anchors and current blocker

The current repository already has the correct authority direction, but not yet a coupled articulated plant:

- `src/motion_plan.rs` states that ARDy/MotionBricks proposals are validated, quantized, hashed, and replay-admitted; `DesiredContactV1` is explicitly only a desired constraint, not evidence.
- `src/active_ragdoll.rs:1-9` is intentionally an **independent** 34-joint rotational tracker plus root servo. It explicitly excludes parent-child coupling, gravity, limits, contact solving, and balance constraints.
- `src/duel_physics.rs` has deterministic 120 Hz swept proxy contact reduction. It is not a full articulated-body/contact-impulse solver.
- `src/motion_service_async.rs:1-13` correctly keeps generative motion off the 120 Hz truth path and documents that opponent/contact/injury conditions need learned packets and training.
- `README.md:10-13` classifies quantized plans and independent-joint active ragdoll as isolated foundations, not live gameplay.

**Prerequisite blocker:** do not train or claim a contact-accurate humanoid combat controller against the current independent-joint runtime. First build or select a coupled articulated training model: link masses/inertias, spherical joint limits, torque-limited motors, gravity, ground/body/weapon collision, stable contact manifolds, friction, continuous weapon collision, and deterministic state serialization. Its state/action convention must be mechanically translatable to the game’s future physics solver.

Isaac Lab/PhysX is appropriate for high-throughput learning and ablations; it must not become online combat truth. The Just Dodge runtime executes only admitted, quantized motor-target packets (or records a complete motor-target stream) through its own deterministic physics.

---

## 3. Recommended architecture: CV-LDC

```
Public Reveal state + accepted intent grammar + opponent-relative geometry
                         |
                         v
          strategic policy / self-play policy (low frequency)
          -> {intent-compatible latent z, timing, footwork, target envelope}
                         |
                         v
     combat smart primitive / retrained MotionBricks condition compiler
          -> short target window: root, pose, effectors, desired-contact,
             balance hints, model+normalization receipts
                         |
                         v
     low-level contact-aware active-ragdoll policy (120 Hz environment)
          obs: actual body/contact state + target window + opponent state
          act: bounded residual joint target / gain / torque command
                         |
                         v
        coupled physics, CCD, friction, joint limits, weapon constraints
                         |
             solved contacts, impulses, balance, injuries
                         |
                         +--> reward/training telemetry only
                         +--> deterministic runtime contact/truth reducer
```

### Roles and trust boundaries

1. **Strategic policy:** selects an intent-compatible latent skill and target envelope. It owns tactical variety: outside footwork, circling, feints, counter timing, recovery choice. It must not write a hit or force an outcome.
2. **MotionBricks / learned condition compiler:** creates a future reference/constraint window that supplies anticipation, silhouette, and follow-through. The released navigation-oriented checkpoint is not a combat model; combat needs a retrained conditioner with paired interaction data.
3. **Contact-aware controller:** converts reference plus current simulated state into bounded motor targets. This is where a kick adapts when contact arrives early and a parry redirects a weapon.
4. **Physics:** computes all contacts, impulses, traction, balance, material interaction, and injuries. Desired contacts are objectives, never facts.
5. **Replay:** never re-runs stochastic neural inference. Either (a) lock a quantized plan whose controller is deterministic on the recorded state, or (b) record the accepted `MotorTargetBatch` stream and replay that byte-for-byte. Bind model, normalizer, plan, and policy hashes in the receipt.

### Suggested training interface

This is a concrete design proposal, not a claim about an existing public network.

**Observation to low-level actor**

- Self: root pose/twist, joint rotations/velocities, torque saturation, joint-limit margins, COM/support information, previous action.
- Contacts: ordered body/weapon contact flags, normals, impulses, slip velocity, and recent contact history.
- Opponent: relative pelvis/chest/head/weapon/guard transforms and twists, visible motion phase, and collision distances. Do not give hidden player intent before the game’s reveal rule allows it.
- Reference: a short future root/pose/effector target window, desired-contact window, and intent/stance/tempo embedding.
- Domain parameters during training only: randomized mass/friction/motor/latency parameters. Keep them privileged to a critic/teacher unless an adaptation module is deliberately evaluated.

**Action from actor**

Start with residual joint-position targets and bounded stiffness/damping adjustments, then convert them to torque-limited PD motor rows in the same solver as contacts. Avoid raw unbounded torques. Do not post-solve teleport or replace decoded joints.

**Strategic action**

Use a small discrete intent/footwork action plus a bounded continuous latent `z`; this is the practical lesson from ASE/RoboStriker. Raw 34-joint multi-agent self-play is unstable and creates a huge exploration problem.

---

## 4. Learning a roundhouse kick, dodge, and parry

### Answer to “through reward shaping?”

**Yes, but do not start from a blank reward.** DeepMimic combines motion imitation with task objectives; AMP replaces manually crafted imitation with an adversarial motion prior; KungfuBot uses physically filtered/corrected motion and an adaptive tracking curriculum. MAAIP is the closest direct fighting precedent because it learns both motion and interaction priors from unstructured single-actor and paired demonstration sets.

A naked reward such as `+damage, -damage taken` is likely to learn reward hacks: perpetual spinning, falling onto a target, joint-limit abuse, body-checks that read as nothing, or frozen defense. A reference/style prior bounds the search to readable movement; sparse competitive reward decides *when* to use it.

### Reward terms for an isolated-skill curriculum

Use normalized, logged components rather than one opaque scalar:

| Component | Purpose | Must be derived from |
|---|---|---|
| `r_ref` | pose/root/effector and angular-velocity tracking to a legal reference or generated target window | simulated body state vs. reference |
| `r_style` | adversarial discriminator or style embedding score for readable martial/cinematic motion | physically simulated history, not rendered pixels |
| `r_balance` | COM/support viability, upright/recovery ability, no fall termination | solved body state |
| `r_effort` | torque, torque slew, joint-limit, and energy penalties | applied motor action / solver state |
| `r_contact_phase` | encourage a foot/weapon/guard to arrive at a *desired* spatial-temporal region | solved contact geometry; zero reward for an intent label alone |
| `r_safety` | penalize self-collision, penetration, unstable velocity spikes, invalid solver state | solver events |
| `r_duel` | sparse exchange outcome and future positional/tactical value | canonical physics/truth events |

For a **roundhouse**, track pelvis turn, support foot, kicking-foot arc, guard hand, recovery, and balance; award contact only if the swept shin/foot proxy hits the legitimate target at the correct phase. For a **dodge**, reward clearance from the opponent’s *actual swept attack volume*, preserve facing/recoverability, and prevent “dodge by ragdoll fall.” For a **parry**, reward an actual guard/weapon intercept that precedes body contact, using the same semantic ordering in `duel_physics.rs`; never reward merely selecting the Parry verb.

### Curriculum

1. **Reference-quality gate:** clean, licensed, retargeted single-person motions; reject clips with impossible penetrations or unresolved feet. MotionBricks/Kimodo may augment references, but are not labels of physical success.
2. **Single character:** tracking plus pushes, varied starting phase, randomized mass/ground/friction/motor lag. Train kick, guard, evasive step, and recovery separately.
3. **Fixed partner:** one scripted opponent motion at fixed distance and tempo. Add weapon/guard contact with CCD.
4. **Partner distribution:** randomized attack timing/height/side/range and frozen learned opponents. Mix genuine misses, late parries, and interrupted recoveries.
5. **Population self-play:** train against an archive of policies rather than only the current opponent. Include scripted anti-exploit opponents and held-out human-authored tactics so a strategy cannot win by exploiting one co-adapting adversary.
6. **Latent strategy:** train the strategic policy over primitive/skill latent actions. Give it an entropy/diversity objective only after physical validity is stable; do not incentivize visual noise.
7. **Deterministic admission:** distill/quantize the accepted controller interface, record model versions, and validate it through the Just Dodge physics path.

For For Honor-style pacing, do not permanently reward circling or aggression. Treat spacing, angular advantage, ring position, threatened attack lane, stamina/injury state, and opponent commitment as input to the strategic critic. Otherwise the policy can learn a visually silly orbiting attractor. The terminal/exchange reward remains the actual physical result; tactical shaping should be annealed down once self-play produces viable duel behavior.

---

## 5. MotionBricks + contact-accurate physics

MotionBricks is useful as a **reference planner**, not a contact resolver. Its paper/repository describes a root module, masked generative pose module, VQ-VAE decoder, and smart primitives; the released demo includes locomotion and object interaction. That does not supply a pairwise combat channel.

### Concrete integration strategy

1. **Train an interaction-aware condition compiler.** Inputs: public intent grammar, current state, relative opponent/root/weapon/guard transforms, desired effector/weapon arcs, and allowed range-of-motion after injury. Outputs: a bounded target window that fits `MotionPlanPacketV1` concepts—root targets, poses, effectors, desired contacts, and balance hints.
2. **Generate reference, do not overwrite simulation.** Decode MotionBricks to a reference pose sequence. The physics controller tracks it with finite gains/torques and may visibly fail, deflect, or recover. No post-decode FK patch, IK snap, or “hit-pose” replacement is allowed after solver contact.
3. **Give the controller live contact feedback.** A reference cannot know whether a sword was intercepted one tick ago. The controller sees solved contact state and can lower the weapon, brace, or transition into recovery.
4. **Train against interaction data.** Paired/weapon-aware demonstrations are necessary. MAAIP’s split between single-actor motion and paired interaction data is a directly useful pattern. Public motion-only pretraining can seed the style prior, but cannot teach a parry geometry it never observed.
5. **Use a teacher–student lane when references are bad.** InterMimic’s “perfect first, then scale up” approach—teacher trackers on easier subsets, distillation to a general student, then RL refinement—is appropriate for noisy combat capture and weapon contacts.

### Runtime schedule

- Neural planning runs asynchronously after Reveal and admits a content-addressed target packet before execution. It must not block a 120 Hz step.
- The coupled controller runs against actual state at the physics rate. If that cannot be made deterministic across gameplay machines, run it server-authoritatively and record its quantized motor batches for replay; do not infer it again during replay.
- Rendering consumes post-solve transforms. Weapon/body proxies are derived from that same simulated pose, not the generated reference.

---

## 6. Sim-to-real—and the relevant Just Dodge translation

For robots, sim-to-real means transferring from PhysX/MuJoCo to hardware. For Just Dodge the immediate problem is more accurately **sim-to-deterministic-runtime**: transferring an Isaac Lab-trained policy to a different solver, body asset, tick convention, and collision implementation. It is equally capable of failing.

### Transfer package

1. **System identification / calibration:** reproduce the game body in Isaac Lab: link lengths, mass, inertia, joints, motor saturation, weapon mass/COM, contact materials, and action delay. Build scenario tests for free swing, ground contact, guard intercept, body impact, and recovery.
2. **Domain randomization:** randomize body mass/inertia/COM, joint damping/friction/limits, torque scale, PD gain, action delay/hold, observation noise, solver/contact parameters, ground friction/restitution, weapon mass/compliance, initial phase, opponent morphology, and impulse disturbances. Isaac Lab explicitly includes domain-randomization support; RMA is evidence for training a base policy plus rapid adaptation module under latent environment variation.
3. **Asymmetric teacher/student:** a teacher critic/policy may observe simulator-only parameters and exact contact data. Distill a student that only sees runtime-visible state, then fine-tune without privileged terms. This is also documented as an Isaac Lab sim-to-real workflow.
4. **Latency and quantization during training:** train with the production control cadence, state quantization, packet horizon, dropped/replanned windows, and inference delay. A float-perfect zero-latency teacher is not a deployable combat controller.
5. **Cross-simulator differential test:** roll out the exact same admitted motor-target trace in Isaac Lab and the deterministic game plant. Compare contact order, gross root/weapon paths, falls, and outcome classification. Do not require bit equality across engines; reject policies whose physical category changes too often.
6. **Conservative fallback:** when a learned plan/controller reports out-of-distribution uncertainty, select an already admitted guard/recovery constraint—not a hidden kinematic correction. Log this event for retraining.

For any genuine hardware experiment, avoid adversarial contact testing on people. Robot boxing research is evidence of transfer feasibility, not a safety authorization.

---

## 7. DreamerV4 and world-model planning

[Dreamer 4](https://arxiv.org/abs/2509.24527) demonstrates an efficient transformer world model and training behaviors in imagination from offline data/video. It is promising for **high-level tactical planning**, but it is not evidence that a learned pixel world model can safely resolve 120 Hz weapon contact or replace deterministic melee truth.

### Recommended use: a tactical shadow model

Train a structured world model from versioned Just Dodge replays and Isaac Lab rollouts, not from raw video alone.

**Input token at each tactical step**

- public duel/truth state; both root and weapon/guard relative transforms and twists;
- compressed body/contact history; stance, injury/capability, arena geometry, and revealed intent phase;
- prior admitted latent skill/plan identifier and resulting physical event token.

**Model proposal**

- Transformer/RSSM-style latent state with separate heads for: next public state, contact category/order, balance/recovery class, plan feasibility, reward/value, and predictive uncertainty.
- Actor operates over `intent-compatible primitive × latent z × timing/footwork`, not raw torques.
- Train from replay plus counterfactual rollouts generated by the exact training simulator. Do not train it to peek at hidden opponent intent before Reveal.

**How it plans**

Dreamer-style actor/value learning inside imagination is the baseline. For explicit per-exchange planning, sample a small beam/CEM population of tactical latent sequences, score expected value **and uncertainty**, then validate the selected candidate with the exact deterministic simulator before admission. This resembles a learned proposal/value model plus authoritative physics, not a learned combat resolver.

**Hard limitation:** a world-model-predicted parry is never a parry. The actual physics rollout and `duel_physics`-compatible contact ordering decide. Reject or down-weight plans in high-uncertainty/contact-sensitive regions; add their real rollouts to the dataset. DreamerV4’s Minecraft result is strong evidence for offline imagination training, not proof of low-level humanoid-contact accuracy.

---

## 8. Anime/cinematic style without robotic motion or truth fraud

### Relevant work

- **AMP:** trains an adversarial discriminator over motion transitions, supplying a style reward from unstructured clips while task reward supplies goal direction. This is the most compatible physical-style mechanism.
- **ASE:** learns reusable latent physical skills from large unstructured motion data, then applies them to downstream objectives. It is a good skill-space design reference.
- **Unpaired Motion Style Transfer from Video to Animation:** separates content and style latents and can extract style from 2D video, but its output is kinematic; use it to obtain references/features, not gameplay truth.
- **SMooDi:** conditions diffusion motion generation on content and a reference style sequence; likewise useful as an offline style/reference generator.
- **Neural Assistive Impulses:** shows that dynamically infeasible exaggerated motions need explicit assistive impulses. In Just Dodge, such an impulse must be a named, balanced special-art mechanic with exact tick, source, magnitude, and material/injury consequence in the deterministic plan—never invisible “anime polish.”

### Recommended style architecture

1. Build a rights-cleared corpus with separate labels for **content** (kick, parry, dodge, recovery) and **style** (weight, anticipation, follow-through, sharpness, asymmetry, held pose, tempo). Treat 2D anime as partial supervision; retain confidence/provenance and do not pretend it provides physically valid 3D contacts.
2. Pretrain a content/style encoder or style discriminator from the corpus. MotionBricks/SMooDi/unpaired transfer may generate stylistic references for augmentation.
3. Condition both the reference compiler and the physics policy on a continuous `style_z`. Add AMP-like physical transition/style reward to the low-level controller, alongside balance/contact/effort terms.
4. Evaluate content preservation separately from style: a stylized parry must still intercept the same geometry and recover under an impact. If it only looks good in a camera shot, reject it.
5. Apply cinematic layers **after** deterministic execution: camera timing, held impact frame, stepped presentation, smear silhouette, afterimage, linework, VFX, and sound are presentation artifacts bound to an actual physics tick/contact. They may amplify an event, not invent it or change its timing.

---

## 9. Experiments, ablations, and promotion gates

### First bounded experiment

Train one unarmed **roundhouse → recover** controller and one weapon **guard intercept/parry → recover** controller in a two-humanoid Isaac Lab task, then transport their quantized reference/motor interface into a Just Dodge shadow harness. Do not add full duel self-play until these prove mechanical transfer.

### Required comparisons

1. Kinematic reference playback vs. PD tracking vs. contact-aware residual controller.
2. Task reward only vs. reference tracking vs. reference + AMP style prior.
3. Fixed opponent vs. frozen-policy mixture vs. population self-play.
4. No randomization vs. calibration/randomization vs. teacher–student distillation.
5. Tactical actor only vs. Dreamer-style imagination actor/value with identical exact-physics validation budget.
6. Plain physical style vs. style-conditioned controller; external special impulse only as a separately disclosed mechanic.

### Metrics

- Skill success on held-out target distance, timing, side, opponent morphology, and contact perturbation.
- Actual swept-contact order: guard-before-body for parry; correct foot/weapon target and phase for attack; clearance plus recovery for dodge.
- Fall rate, time-to-recover, penetration, self-collision, torque saturation, torque slew, joint-limit violations, foot slip, and energy.
- Tactical diversity: primitive/latent usage entropy, counter-strategy coverage, and win rate against an archived opponent population—not just the latest policy.
- Style: held-out discriminator/embedding score, anticipation/follow-through metrics, and blinded human readability review.
- Runtime: control/inference deadlines, packet replan rate, memory/VRAM, and actual-game frame pacing.
- Determinism: same initial state + same admitted plan/motor trace yields byte-identical Just Dodge hashes; replay never calls a neural sampler.

### Keep / revert gates

Promote CV-LDC only if all are true:

- The coupled-body/contact prerequisite exists and passes independent physics verification before policy training.
- The learned controller improves held-out physical skill metrics over reference-only PD tracking **without** increasing solver-invalid states, falls, or contact-order mistakes beyond pre-registered limits.
- It retains performance against a held-out archived opponent set; a self-play-only win-rate increase is insufficient.
- Kinematic and controller outputs are not patched after contact; a test that disables any post-decode correction must still show learned target tracking rather than exact hard-masked targets.
- A recorded plan/motor trace produces deterministic replay hashes in the Just Dodge path, and the motion service never blocks a 120 Hz step.
- Anomaly/OOD and cross-simulator discrepancy cases are captured in Motion Frontier Lab rather than silently resampled or hidden.

**Revert/hold** if the solution requires animation to set contact outcomes, depends on unsafely unbounded torques/hidden impulses, collapses to spinning/orbiting/falling exploits, fails the held-out opponent mixture, or changes outcome classification when transferred to the deterministic game plant.

---

## 10. Sources

1. Makoviychuk et al. (2021), [*Isaac Gym: High Performance GPU-Based Physics Simulation for Robot Learning*](https://arxiv.org/abs/2108.10470).
2. [Isaac Lab official documentation](https://isaac-sim.github.io/IsaacLab/main/index.html), accessed 2026-07-17.
3. Peng et al. (2018), [*DeepMimic*](https://arxiv.org/abs/1804.02717).
4. Peng et al. (2021), [*AMP: Adversarial Motion Priors for Stylized Physics-Based Character Control*](https://arxiv.org/abs/2104.02180).
5. Peng et al. (2022), [*ASE: Large-Scale Reusable Adversarial Skill Embeddings*](https://arxiv.org/abs/2205.01906).
6. Younes et al. (2023), [*MAAIP: Multi-Agent Adversarial Interaction Priors for imitation from fighting demonstrations for physics-based characters*](https://arxiv.org/abs/2311.02502).
7. Xie et al. (2025), [*KungfuBot: Physics-Based Humanoid Whole-Body Control for Learning Highly-Dynamic Skills*](https://arxiv.org/abs/2506.12851).
8. Yin et al. (2026), [*RoboStriker: Hierarchical Decision-Making for Autonomous Humanoid Boxing*](https://arxiv.org/abs/2601.22517).
9. Xin et al. (2026), [*RPG: Robust Policy Gating for Smooth Multi-Skill Transitions in Humanoid Fighting*](https://arxiv.org/abs/2604.21355).
10. Xu et al. (2025), [*InterMimic*](https://arxiv.org/abs/2502.20390).
11. Wang et al. (2026), [*MotionBricks*](https://arxiv.org/abs/2604.24833) and its [official release](https://github.com/NVlabs/GR00T-WholeBodyControl/tree/main/motionbricks).
12. Kumar et al. (2021), [*Rapid Motor Adaptation for Legged Robots*](https://arxiv.org/abs/2107.04034).
13. Rudin et al. (2021), [*Learning to Walk in Minutes Using Massively Parallel Deep Reinforcement Learning*](https://arxiv.org/abs/2109.11978).
14. Hafner et al. (2025), [*Training Agents Inside of Scalable World Models (Dreamer 4)*](https://arxiv.org/abs/2509.24527).
15. Aberman et al. (2020), [*Unpaired Motion Style Transfer from Video to Animation*](https://arxiv.org/abs/2005.05751).
16. Zhong et al. (2024), [*SMooDi: Stylized Motion Diffusion Model*](https://arxiv.org/abs/2407.12783).
17. Wang & Benes (2026), [*Neural Assistive Impulses*](https://arxiv.org/abs/2604.05394).
18. Kanervisto & Hautamäki (2019), [*ToriLLE: Learning Environment for Hand-to-Hand Combat*](https://arxiv.org/abs/1807.10110).
