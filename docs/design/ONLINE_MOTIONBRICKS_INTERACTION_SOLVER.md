# Physics-Authoritative Neural Motion and Active-Ragdoll Contract

Status: B14W design boundary. Production runtime remains frozen until the probes and gates below pass.

## Non-negotiable product contract

- Dodge, Block, Parry, Strike, Grab, and the remaining combat primitives are intents, not animation IDs.
- No release path selects, preloads, or plays a baked action/variation clip.
- ARDy proposes a semantic short-horizon plan from public post-Reveal state.
- MotionBricks completes locomotion, in-betweening, and sparse-constraint realization; it never declares outcomes.
- A physics-trained active-ragdoll controller converts the quantized plan into joint-motor targets.
- The deterministic 120 Hz articulated physical world alone decides hit, guard, whiff, balance, momentum transfer, material failure, and injury.
- Teacher motion is offline training/QA evidence only. Teacher frames, authored clips, and teacher-file lookups are forbidden runtime inputs.
- Every accepted neural plan or event-driven replan is quantized, assigned a stable ID/hash, and serialized into replay. Replay/networking reuse the packet verbatim instead of rerunning neural inference.

```text
public post-Reveal state
    -> ARDy semantic short-horizon plan
    -> MotionBricks locomotion/in-betweening/constraint completion
    -> quantized MotionPlanPacket (ID + hash + replay record)
    -> physics-trained active-ragdoll controller
    -> deterministic joint motors and articulated physics
    -> measured contacts, momentum, material failure, injury, ImpactEvent
    -> event-driven neural replan when required
```

## Verified released-MotionBricks boundary

The checked-out released model cannot satisfy this contract unchanged.

- `motion_backbone/inference/motion_inference.py:44-68` accepts global root, local root, local pose, masks, and duration. It has no interaction-state argument.
- `motion_inference.py:54-64` requires an eight-frame sparse input and assumes the first four frames are available.
- `motion_inference.py:266-285` constructs pose conditioning from only the first four poses and the final four target poses. Caller-supplied middle poses do not reach the pose backbone.
- `root_backbone.py:91-97` creates fixed start/end projections and an eight-position embedding: four start plus four end frames.
- `motionbricks_service/generate.py:519-553` follows that exact contract by concatenating four context and four target frames.
- Live checkpoint probe: pose/root text conditioning is disabled; `frames_per_token=4`; duration is 6–16 tokens, or 24–64 generated frames.

Consequences:

1. The released checkpoint can interpolate sparse start/end states.
2. It cannot condition directly on attack geometry, time-to-contact, legality, or mid-horizon contact changes.
3. Repeatedly choosing target poses outside MotionBricks would move the interaction solver into handwritten IK/clip logic and is not acceptable.
4. MotionBricks therefore requires a trained interaction-conditioning extension in both root and pose backbones. ARDy supplies the semantic plan, not runtime frames or outcomes. The existing VQVAE/decoder may be initialized from B14V.

## Authoritative 120 Hz input schema

All fields below are derived deterministically from the shared physical world. Integer units are used at the truth/replay boundary; neural normalization occurs after the immutable snapshot is produced.

```rust
pub struct InteractionConstraintFrameV1 {
    pub schema_version: u16,
    pub truth_tick: u64,
    pub interaction_id: u64,
    pub actor: Side,
    pub opponent: Side,

    pub actor_intent: IntentId,
    pub opponent_intent: IntentId,
    pub legal_response_bits: u16,
    pub emitter_role: PhysicalRole,
    pub target_role: PhysicalRole,

    // Opponent attack geometry in actor-root local coordinates.
    pub attack_origin_mm: [i32; 3],
    pub attack_target_mm: [i32; 3],
    pub attack_direction_q15: [i16; 3],
    pub attack_velocity_mm_s: [i32; 3],
    pub attack_angular_velocity_mrad_s: [i32; 3],
    pub reach_mm: u16,

    // Forecast from swept 120 Hz geometry, never from an action matchup table.
    pub contact_tick_offset: i16,
    pub contact_window_start_tick_offset: i16,
    pub contact_window_end_tick_offset: i16,
    pub expected_impulse_milli_ns: u32,
    pub expected_energy_millijoules: u32,

    // Current actor state in the same local frame.
    pub actor_root_position_mm: [i32; 3],
    pub actor_root_heading_q15: [i16; 2],
    pub actor_root_velocity_mm_s: [i32; 3],
    pub actor_joint_positions_mm: [[i16; 3]; 34],
    pub actor_joint_rotations_6d_q15: [[i16; 6]; 34],
    pub footing_bits: u8,
    pub recovery_ticks_remaining: u16,
    pub injury_q8: [u8; 4],

    // Deterministic local-space clearance probes used by Dodge/root planning.
    pub clearance_mm: [u16; 6], // left, right, back, forward, up, down
}
```

`legal_response_bits` is computed from live physical feasibility and rules. It is not an outcome lookup. An intent that is illegal for the measured attack cannot be requested from the neural solver.

The snapshot is immutable, replayable, and hashable. Arrays use stable joint/role order; no hash-map iteration is permitted.

## Neural conditioning schema

The model receives a rolling sequence, not an action filename.

```text
interaction_ids:       [B, T] int64
interaction_continuous:[B, T, C] float32
interaction_valid:     [B, T] bool
current_pose:          [B, 4, pose_dim] float32
current_root:          [B, 4, root_dim] float32
pose_tokens:           [B, N, pose_heads] int64
num_tokens:            [B, 1] int64, N in [6, 16]
```

`interaction_ids` embeds categorical intent, legality, side, emitter role, and target role. `interaction_continuous` is a versioned, normalized projection of the integer geometry/timing/state fields. Every normalization constant is checkpoint metadata and hash-verified at load.

Required model changes:

1. Add `interaction_embedding` to the root backbone before duration/root prediction.
2. Add the same per-token interaction embedding to the pose backbone before token prediction.
3. Train with time-varying interaction sequences and perturbations, not one constant label per trajectory.
4. Keep sparse start-state conditioning for continuity. End-pose conditioning is optional training supervision, not a required runtime target.
5. Preserve deterministic argmax token selection for verification; stochastic sampling is not admitted into truth-facing QA.

Text prompts are not the interaction API. The current checkpoint has no text channel, and natural-language embeddings would be an under-specified, non-versioned substitute for physical state.

## Quantized motion-plan packet

Neural output becomes authoritative controller input only after quantization and serialization. It is never authoritative evidence that an interaction succeeded.

```rust
pub struct MotionPlanPacketV1 {
    pub schema_version: u16,
    pub plan_id: u64,
    pub parent_plan_id: Option<u64>,
    pub source_truth_tick: u64,
    pub valid_from_truth_tick: u64,
    pub intent: IntentGrammarV1,
    pub root_samples: Vec<QuantizedRootTarget>,
    pub end_effector_samples: Vec<QuantizedEffectorTarget>,
    pub desired_contact_samples: Vec<QuantizedDesiredContact>,
    pub pose_samples: Vec<QuantizedPoseTarget>,
    pub balance_hints: Vec<QuantizedBalanceHint>,
    pub plan_hash: u64,
}
```

The implementation uses bounded/preallocated storage rather than unbounded `Vec`; the illustrative shape names the semantic contents. The hash covers canonical integer encoding, model/version receipts, and the parent replan ID.

## Runtime solve loop

Neural planning/completion runs asynchronously while articulated physics runs at 120 Hz.

1. At each 120 Hz tick, shared physics updates the immutable interaction snapshot and contact forecast.
2. After Reveal, ARDy proposes a semantic plan from public state; MotionBricks completes its locomotion/constraint representation.
3. Quantize, validate, ID, hash, and record `MotionPlanPacketV1` before the active-ragdoll controller may consume it.
4. Warm-start the controller and MotionBricks from the accepted packet and current articulated state. Store only bounded transient working state; never write an action animation file or cache by action name.
5. At 120 Hz, the active-ragdoll policy proposes motor targets and deterministic articulated physics integrates joints, contacts, friction, grips, impulses, and balance.
6. A physics event or forecast discontinuity may request a replan. The replacement packet records its parent plan ID and activation tick; replay uses the same packet sequence verbatim.
7. Combat truth consumes measured solver events, never neural success labels. Presentation consumes the same measured events and articulated state.

```rust
pub struct OnlineMotionSolveRequestV1<'a> {
    pub request_id: u64,
    pub source_truth_tick: u64,
    pub deterministic_seed: u64,
    pub actor_intent: IntentId,
    pub interaction_history: &'a [InteractionConstraintFrameV1],
    pub current_f413: &'a [[f32; 413]; 4],
    pub requested_horizon_frames: u8,
}

pub struct TransientMotionWindow {
    pub request_id: u64,
    pub source_truth_tick: u64,
    pub interaction_id: u64,
    pub frame_count: u8,
    pub f413: [[f32; 413]; 64],
}
```

The transient window is a neural/controller working set. `MotionPlanPacketV1` is replayed authority input; deterministic physics remains outcome authority.

## Determinism boundary

- `deterministic_seed = hash(match_seed, interaction_id, actor, source_truth_tick, model_version)`.
- Argmax token decode is mandatory for determinism probes.
- Model/checkpoint/normalization hashes and every accepted plan packet are recorded in replay metadata.
- Live inference need not reproduce bit-identically across CUDA/TensorRT targets because replay/networking consume canonical quantized packet bytes.
- Identical packet bytes and physical inputs must reproduce identical 120 Hz truth hashes.
- Neural output cannot enter controller authority until quantized and recorded; divergent unquantized output never feeds contact/injury truth.

## Active-ragdoll and impact boundary

The whole-body controller outputs desired joint positions/velocities plus PD/impedance gains and torque limits. Deterministic physics applies those motor commands subject to joint limits, balance, contacts, grips, friction, and external impulses. The controller cannot teleport bodies or override the solver.

One solver-derived event drives all impact response:

```rust
pub struct ImpactEventV1 {
    pub truth_tick: u64,
    pub contact_id: u64,
    pub contact_point_mm: [i32; 3],
    pub impulse_milli_ns: [i32; 3],
    pub dissipated_energy_millijoules: u32,
    pub relative_velocity_mm_s: [i32; 3],
    pub material_failure_bits: u16,
    pub anatomical_severity_q16: u16,
    pub attacker: Side,
    pub defender: Side,
}
```

Motor-gain softening, camera kick, sound, VFX, debris, blood, and recovery consume this event. None may fabricate a second contact result.

## Latency and continuity gates

No fallback clip is allowed when a deadline is missed. A model that misses the target budget is not shippable until optimized or distilled.

Measure rather than assume:

- solve latency p50/p95/p99 and worst case;
- queue delay and deadline misses;
- output-buffer lead in 30 Hz frames;
- positional/angular discontinuity at every replan seam;
- contact-anchor error at forecast contact ticks;
- root/foot sliding and interpenetration;
- RTX 5090 and Steam Deck separately.

Initial falsification budgets:

- steady-state replan cadence: 30 Hz;
- p99 solve completion: <= 33.33 ms on target hardware;
- zero deadline misses over 10,000 adversarial replans;
- seam root displacement <= 5 mm and joint angular jump <= 1 degree after continuity blending inside MotionBricks;
- contact anchor error <= geometry tolerance defined by the 120 Hz proxy model.

These are gates to test, not claims about the current checkpoint.

## Closed-loop test matrix

A static clip test cannot pass B14W. Minimum tests vary:

- attack primitive and physical emitter role;
- left/right/center line;
- head/torso/leg target height;
- near/far reach;
- early/nominal/late contact forecast;
- Block/Dodge/Parry legality combinations;
- injured/uninjured arm and footing state;
- opponent acceleration, feint, redirection, and interrupted attack after the first solve;
- constrained clearance on each side;
- render rates 30/60/144/240 Hz with identical truth hashes.

Required evidence per case:

1. legal intent only;
2. deterministic request tensor hash;
3. bounded solve latency;
4. continuous replan seams;
5. physically aligned guard/evasion/contact geometry;
6. unchanged truth stream with renderer/MotionBricks disabled versus enabled for the same authoritative physical inputs;
7. no runtime read of an action animation file.

## Migration boundary

Current `src/motion_runtime.rs` preloads one `Vec<[Mat4; 34]>` for Strike/Block/Grab. It is QA scaffolding and cannot be promoted. Replacement requires ARDy planning, MotionBricks completion, quantized/replayed plan packets, a physics-trained active-ragdoll controller, articulated deterministic simulation, latency probes, closed-loop semantics, and replay verification.
