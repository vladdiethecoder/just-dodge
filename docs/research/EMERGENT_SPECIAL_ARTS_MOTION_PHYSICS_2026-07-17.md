# Emergent Special Arts: Generative Motion + Deterministic Physics

**Date:** 2026-07-17
**Scope:** Mid-air roundhouse kicks, wall-running attacks, projectile deflection/cutting, and deliberately physics-defying anime arts, with no runtime hand-authored animation.
**Verdict:** Treat a special art as a learned, bounded *intent and motor-target plan* that a deterministic articulated simulator either executes or rejects. Motion generation supplies a desired future; it never supplies a hit, a cut, a contact, or a root teleport.

## 1. Binding project facts and blocker

The repository already has the correct packet/motor boundary, but not a sufficient physical substrate for these techniques:

- `src/motion_plan.rs` has canonical quantized `MotionPlanPacketV1`, root/effector/pose targets, desired contacts, and 120 Hz `MotorTargetBatchV1`. `DesiredContactV1` is already correctly documented as a request, not proof of contact.
- `src/active_ragdoll.rs` is deliberately **not** an articulated/contact solver: it advances independent joint/root states and excludes parent-child coupling, gravity, joint limits, contact, and balance. This is the immediate prerequisite blocker for any claim that a mid-air kick, wall run, or sword/projectile interaction is physics-driven.
- `src/intent/plan_phase.rs` keeps gameplay roots in integer millimetres and sets `GRAB_REACH_MM = 650`; this is a useful precedent for exact, quantized feasibility rules.
- `docs/quality/ADVERSARIAL_VISUAL_CONTRACT.md` requires packet-only, asynchronous neural delivery and byte-identical recorded packets for replay. Preserve that contract.

**Do not promote a special art until the articulated-body/contact layer exists.** Current pose replacement or isolated joint tracking would be an animation result, not emergent physical execution.

## 2. What the frontier sources actually provide

| Source | Concrete technique / architecture | What transfers | Important limit |
|---|---|---|---|
| [MotionBricks (Wang et al., SIGGRAPH 2026)](https://arxiv.org/abs/2604.24833) | Structured eight-head discrete pose tokenizer; separate root and pose Transformer modules; root module predicts duration/trajectory, masked pose-token module predicts local pose, decoder emits continuous motion. Smart locomotion/object primitives turn events into proxy keyframes; generated windows are buffered/replanned. | The correct generative planner/in-betweening layer for a transient kick, wall-run approach, weapon line, or recovery. | Public G1 wrapper is whole-frame root/full-pose in-betweening, not an opponent/weapon/projectile/wall-conditioned combat model. The released checkpoint must not be relabelled as one. |
| [SONIC / GEAR-SONIC (Luo et al., 2026)](https://arxiv.org/abs/2511.07820) | Motion-tracking whole-body policy scaled from 1.2M to 42M parameters, 100M+ frames/700 h data; kinematic planner and common token interface for higher-level policies. | Best NVIDIA-style *physics tracker* role: plan/reference in, bounded motor actions out. | Motion tracking is not combat decision-making, material failure, or authoritative game truth. |
| [KungfuBot / PBHC (Xie et al., NeurIPS 2025)](https://arxiv.org/abs/2506.12851) | Filter/correct/retarget dynamic references, contact masks, then PPO asymmetric actor-critic. Bi-level adaptive tracking tolerance relaxes impossible references rather than destabilizing training. It reports jump-kick/roundhouse-kick contact-mask ablations. | A training recipe for high-spin kicks: contact-aware preprocessing, privileged critic, proprioceptive actor, adaptive tracking curriculum. | Optimizes single-agent reference tracking. Add paired target, weapon, projectile, and environment conditions rather than assuming they emerge. |
| [HIL: Hybrid Imitation Learning (Wang et al., 2026)](https://arxiv.org/abs/2505.12619) | A single goal-conditioned controller is jointly trained in parallel: precise motion-tracking tasks plus adversarial-imitation tasks. Tracking preserves athletic repertoire; the discriminator permits adaptation/skill composition in new obstacle courses. | Strongest direct template for wall-runs and environment-conditioned attacks. | Requires broad, procedurally varied environment training; pure tracking does not generalize around arbitrary walls. |
| [PARC (Xu et al., SIGGRAPH 2025)](https://arxiv.org/abs/2505.04002) | Iterative loop: small core traversal corpus -> generator -> physics tracker repairs artifacts -> corrected rollouts augment corpus -> repeat. | Practical answer to scarce wall-run / aerial-combat capture: use simulation to produce admissible new training examples, not runtime clips. | Every synthetic sample still requires physical and visual admission; do not train on unfiltered generator failures. |
| [DeepMimic (Peng et al., 2018)](https://arxiv.org/abs/1804.02717) | PPO-style physics controller combines pose/velocity/end-effector tracking with task reward; learns recoveries and multi-skill agents including flips, spins, and martial arts. | Baseline loss decomposition and reset/curriculum strategy. | Reference following alone tends to be brittle when a live projectile or wall forces a deviation. |
| [AMP (Peng et al., 2021)](https://arxiv.org/abs/2104.02180) | Adversarial motion prior learns a style reward from unstructured clips; task reward determines what to do, with automatic skill choice/composition. | A style prior for natural martial arts while task objectives drive intercept/escape. | AMP can mode-collapse and cannot certify that an emergent contact is valid. Pair it with tracking/physics and hard safety gates. |
| [RoboStriker (Yin et al., 2026)](https://arxiv.org/abs/2601.22517) | Train a tracker, distill it into a unit-hypersphere latent action manifold, then run neural fictitious self-play in latent space instead of raw torque space. | Good tactical policy pattern: self-play chooses `intercept/feint/air-kick/wall-attack` latent plan, while a low-level controller handles balance. | Research result, no located public implementation; reproduce the architecture rather than treating it as a drop-in asset. |
| [RPG (Xin et al., 2026)](https://arxiv.org/abs/2604.21355) | Hybrid expert policy with motion-transition and temporal randomization, trained to make fighting skills interruptible and stable. | Required data augmentation for canceling a kick to parry a projectile or leaving a wall run early. | Does not solve projectile geometry/fracture. |
| [Neural Assistive Impulses / NAI (Wang & Benes, 2026)](https://arxiv.org/abs/2604.05394) | For intentionally infeasible anime motion, derive nominal root impulse from inverse dynamics/RNEA and learn a low-frequency residual; a confidence gate mixes them. Optimize impulse (finite momentum transfer), not force spikes. | The cleanest published pattern for a rising aerial roundhouse, mid-air dash, double-jump, or wall-release boost. | The assist must be an explicit, budgeted simulation input. A neural root-position overwrite is not physics-driven and destroys replay accountability. |
| [InterMimic (Xu et al., 2025)](https://arxiv.org/abs/2502.20390) | Train many small teacher controllers to physically repair/retarget imperfect dynamic-object MoCap; distill them into a Transformer student; then RL fine-tune. | Training architecture for sword/hand/object coupling and projected projectile interaction data. | Their own discussion reports residual penetration/failure on corrupted references; use an SDF/CCD termination gate. |
| [Humanoid Parkour Learning (Zhuang et al., 2024)](https://arxiv.org/abs/2406.10759) | Train an oracle across an automatic difficulty curriculum/varied terrain, then DAgger-distill privileged terrain sensing to onboard depth perception. | Separate privileged training geometry from game-runtime geometry; curriculum over wall angle, height, approach velocity, and attack timing. | It demonstrates jumps/hurdles/gaps, not stylized wall-combat. |
| [Embrace Collisions (Zhuang & Zhao, 2025)](https://arxiv.org/abs/2502.01465) | Whole-body policy trained to survive unpredictable, non-foot/non-hand contacts and large base rotations. | A useful recovery/roll/fall prior after missed air attacks or projectile impacts. | Not a precise weapon/contact controller. |

### NVIDIA / GR00T clarification

“GR00T-style” should not mean importing a language-action robot policy into the combat truth loop. The relevant NVIDIA division is:

1. **MotionBricks** — generates a kinematic short-horizon motion proposal from smart-primitive constraints.
2. **SONIC / GEAR-SONIC** — tracks a planned motion with a whole-body policy and exposes a high-level token interface.
3. **Your deterministic articulated physics** — evaluates contacts, impulses, damage, projectile topology, and special-energy spending.

The public MotionBricks release is explicitly not a ready-made paired martial-arts model. The repository’s `motion_service_async.rs` accurately notes the current lack of clearance, limb-state, weapon-hand, opponent, injury, momentum, and velocity conditioning. Add these to a trained condition interface; never repair them after decode.

## 3. Proposed runtime: Special-Art Constraint Packet (SACP)

Extend the existing `MotionPlanPacketV1` rather than introducing an untracked AI side channel. The following are **learned conditioning inputs / requested constraints**, never asserted outcomes:

```text
SpecialArtConditionV1[t] {
  kind: aerial_roundhouse | wall_attack | projectile_deflect | projectile_cut,
  phase: load | launch | flight | intercept | recovery,
  target: actor/object/projectile stable ID + relative position/velocity,
  effectors: per-effector pose target + availability mask,
  wall: stable collider ID, local anchor, Q15 normal/tangent, attach interval,
  weapon: grip state, local blade frame, swept-line samples,
  projectile: stable ID, predicted root-relative track samples + radius/material class,
  contact_window: [start_tick, end_tick],
  clearance: signed-distance samples / occupancy along body-and-weapon sweeps,
  assistance: allowed linear/angular impulse budget and special-energy budget,
  masks: field validity at every time sample
}
```

### Three time scales

```text
10–20 Hz tactical self-play / game intent
  choose an admissible special art, target ID, timing window, and energy budget
                    ↓ recorded request / deterministic legality
20–30 Hz asynchronous ARDY + MotionBricks planning
  ARDY: long horizon sparse condition inpainting; MotionBricks: 4-frame-token
  short-horizon local pose/root completion and replan buffer
                    ↓ quantize, validate, hash, publish (never await in truth)
120 Hz deterministic articulated simulation
  target pose -> bounded motors; CCD -> contacts -> impulses/fracture -> next state
                    ↓
wgpu visualizes the solved skeleton/sword/projectile state only
```

At 120 Hz, one tick is 8.333 ms. MotionBricks’ paper reports 2 ms/15,000 FPS, but that is a paper/project claim, not a Just Dodge target-hardware measurement; ARDY horizons/diffusion are much slower. The existing asynchronous packet and recorded-replay design is therefore mandatory, not an optimization.

### Controller model to train

Use a **hybrid tracker**, not a direct pose player:

```text
encoder:
  proprioception(q, dq, joint-limit margin, COM, support/contact state)
  + SACP horizon (root/effector targets, masks, desired contact windows)
  + local scene tokens (wall SDF/normal/tangent and projectile trajectory)
  + weapon state (grip/socket/blade pose and solved blade velocity)
  + special-energy remaining
       -> state MLP + scene-token Transformer / PointNet fusion
policy:
  motor head -> desired joint rotations/velocities + stiffness/damping/torque caps
  assist head -> bounded [linear impulse, angular impulse, confidence beta]
critic (training only): privileged exact contacts, future projectile path, SDF,
  actor/opponent state, material threshold and simulator state
loss/reward:
  adaptive reference tracking (PBHC) + AMP/HIL style distribution
  + task success + balance/energy + contact timing
  - penetration/self-collision/invalid-grip/limit violation
  - illegal-assist energy / non-authorized impulse
```

The actor must receive only game-legitimate observations at runtime. The critic may receive simulator-only geometry/true future paths during training, then distill or remove that privilege. Train in parallel task families (HIL): tracking-only episodes preserve style; task/adversarial episodes force adaptation around walls/projectiles.

## 4. Four concrete special arts

### A. Mid-air roundhouse kick

**Plan:** `flight` root targets + one free kicking-foot trajectory + hip/chest orientation + predicted target capsule and a narrow contact window. Do not request a foot/body collision as true.

**Training:** Capture or legally obtain kick/roundhouse/jump references; retarget/filter them with PBHC-style contact masks. Randomize initial angular/linear velocity, target height/range, opponent recoil, timing, and missed contact. Use transition/temporal randomization from RPG so a projectile response can interrupt flight.

**Execution:** An active-ragdoll tracker converts the plan into torque-limited motors. At contact, the 120 Hz solver decides whether the foot actually reaches target, transfers impulse, and alters both bodies’ momenta. If the art allows an anime boost, admit one finite `J` impulse in a named phase only:

```text
v_next = v + J / mass
ΔK is debited from the packet’s quantized special-energy budget
```

The NAI-inspired controller may predict a residual only inside the packet’s cap; inverse-dynamics guidance provides the nominal direction. Quantize `J`, source tick, application point, residual/gate receipt, and remaining budget. This creates a physics-defying look without an unbounded neural teleport.

### B. Wall-running attack

**Plan:** Bind to a specific deterministic wall collider and local anchor; condition on normal/tangent, surface material, approach velocity, body clearance, attachment/release times, and weapon/foot contact windows. A generic world-space target is insufficient: it drifts when level geometry changes.

**Training:** Curriculum: broad walls -> different normal/height/curvature/material -> approach angles -> enemy placement -> attacks while bound -> partial/missing wall contact. PARC can grow the corpus: physics-repaired successful rollouts become training material only after admission.

**Execution:** The solver supplies normal/friction impulses only while a real contact exists. A requested wall force with no contact is rejected; a special-art impulse can augment it but must be separately budgeted. This supports both physically plausible wall traction and explicit anime “chi” assistance without hiding the distinction.

### C. Projectile deflection and cutting

**Plan:** The learned policy is responsible for body/weapon positioning and timing, conditioned on the projectile’s *public/predicted* track. It cannot declare `cut=true`. MotionBricks needs new projectile-track, blade-sweep, and contact-window condition channels plus paired training data to produce the readable intercept pose.

**Deterministic continuous collision:** At each 120 Hz step, build the solved blade sweep from the simulated weapon edge endpoints and the projectile sweep from its solved position/velocity. Broad phase uses swept AABBs. Narrow phase must find earliest time-of-impact (TOI), not merely test endpoints:

- Represent the blade as a swept thin capsule or triangular-prism volume, and projectile as sphere/capsule/convex volume.
- Use fixed-iteration conservative advancement / interval CCD in a deterministic CPU truth module. `Tight Inclusion` is the strongest direct reference for conservative TOI reporting; Zhang et al. provides articulated-link CCD with TOC and witness features.
- Quantize TOI, witness feature IDs, normal, contact point, material parameters, and tie-break simultaneous hits by `(toi, projectile_id, blade_feature_id)`. Use integer/fixed-point arithmetic where feasible, or a pinned deterministic numeric implementation with fixed iteration/order. Do **not** use wgpu/GPU physics for network truth.

**Response:**

1. Solve deflection impulse from solved relative velocity, restitution, friction, and blade-body effective mass; apply equal/opposite impulse to projectile and articulated sword/hand.
2. Classify a cut only after TOI using a deterministic material rule, e.g. normal/tangential blade-speed component, blade orientation, projectile mass/energy, and toughness/fracture-energy threshold.
3. On cut, replace parent projectile at TOI with two deterministic children (`parent_event_id`, stable child IDs). Split mass/shape by the blade cut plane; offset children by a fixed epsilon; allocate momentum so linear momentum is conserved after the contact impulse and debit fracture energy. A magical projectile may legally add energy only through its separately declared effect budget.
4. The renderer receives those exact child bodies and fracture-surface data; it does not fake a half-projectile VFX over an intact truth projectile.

For generic rigid/destructible projectiles, use a precomputed fracture library rather than online FEM. [Breaking Good](https://arxiv.org/abs/2111.05249) precomputes low-energy fracture modes and projects runtime impacts to them without online crack propagation. For an energy bolt, a deterministic analytic split mesh/volume is simpler and more replayable.

## 5. Physics / geometry references

- [Wang et al. 2021, *A Large-scale Benchmark and an Inclusion-based Algorithm for CCD*](https://doi.org/10.1145/3460775): interval/predicate CCD reports a conservative TOI and explicitly exposes false-positive/runtime tradeoffs. Use its benchmark philosophy for thin, fast blade/projectile degenerate cases.
- [Zhang et al. 2007, *CCD for Articulated Models using Taylor Models and Temporal Culling*](https://doi.org/10.1145/1275808.1276396): continuous articulated-link collision, TOC, and witness features; particularly relevant because the blade is driven by a solved arm chain.
- [Yang et al. 2023, *Jade*](https://arxiv.org/abs/2309.04710): CCD TOI plus backtracking and multi-friction contact solver structure; useful training-simulation reference, not a reason to make production truth floating/differentiable.
- [Sellán et al. 2023, *Breaking Good*](https://doi.org/10.1145/3549540): impact-dependent precomputed fracture modes for real-time destruction.

## 6. Recommended first experiment: `AerialIntercept-1`

Do not start with projectile cutting. The smallest falsifiable vertical slice is a **mid-air roundhouse / deflect**, because it validates planner -> motor -> articulated physics -> CCD -> replay without topological fracture.

1. Add a no-outcome `SpecialArtConditionV1` schema and hash it into `MotionPlanPacketV1`; only `aerial_roundhouse` + `projectile_deflect` are legal initially.
2. Complete the real coupled deterministic articulated layer before touching model training. It must provide gravity, joint limits, parent-child constraints, body/sword proxies, blade endpoint velocities, contacts, and a fixed-order CCD query.
3. Train a small PBHC/HIL-style tracker on legally cleared kick/guard/intercept motion plus randomized projectile trajectories. Generate plans asynchronously; record accepted packet bytes.
4. Add blade/projectile CCD and only the **deflect** response. Keep cutting disabled.
5. Verify fixed-seed, packet-recorded replay over 1,000 identical replays: state/contact/impact hashes must match exactly. Test a grid over target range/height, projectile velocity/radius/approach, left/right stance, initial air velocity, and missed intercepts.
6. Promote only if: zero CCD tunneling in the adversarial thin/fast suite; zero plan-buffer underruns; no non-finite/limit violation; no contact claimed before TOI; actual solved blade is the render/socket/proxy source; visual first-person/readability gates pass.

### Falsifiers / revert conditions

- Removing post-decode pose repair causes target error to explode: the neural conditioning is not genuinely learned; retrain rather than mask output.
- Exact replay diverges across runs: packet/state/TOI numeric contract is inadequate; do not tune art/model quality first.
- The solver reports a cut/deflect when CCD finds no TOI, or misses a known sweep collision: block special-art promotion.
- The model only works against fixed reference projectile tracks/walls and fails on held-out geometry: it is a choreography tracker, not emergent environment-conditioned control.
- Assistive impulses account for unbounded/undeclared kinetic energy: reject as a root-override/teleport.

## 7. Evidence quality / source notes

The sources above support architecture and training hypotheses, not a claim that Just Dodge has these capabilities. MotionBricks is a generative kinematic backbone; SONIC/PBHC/HIL are control/training examples; CCD/fracture papers are geometry/physics references. None replaces the project’s missing coupled articulated solver, paired weapon/projectile data, or deterministic admission/replay gates.
