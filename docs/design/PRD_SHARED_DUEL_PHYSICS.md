# PRD: Shared Duel Physics and Combat Resolution

## Status

Authoritative architecture contract. This supersedes any interpretation of generated motion as a combat referee.

## 1. Ownership boundary

```text
committed timelines -> action compiler -> Motion Synthesis -> target buffers
                                                        -> Shared Duel Physics -> bilateral contacts
                                                                              -> Combat Resolution -> truth/replay/hash
```

- **Motion Synthesis** produces unilateral desired root, joint, hand/grip, and weapon-corridor targets. It cannot create contact, impulse, damage, blocks, parries, or outcomes.
- **Shared Duel Physics** advances both fighters, weapons, armor, arena colliders, grip constraints, and ground in one world. It is the only producer of physical contact packets.
- **Combat Resolution** derives labels and applies armor/anatomy/capability deltas from the complete contact manifold. It never manufactures impulse from an action label.
- **Truth/replay** owns ordered state, inputs, substep packets, capability deltas, and canonical hashes. Presentation is read-only.

A generated sword target may specify a corridor through an anatomical region. It must never hard-constrain a weapon to the opponent body: that would preselect a hit.

## 2. Clock contract

| Domain | Rate | Rule |
|---|---:|---|
| Timeline/action compiler | 60 Hz | One committed action tick. |
| Physics | 120 Hz | Exactly two substeps per action tick. |
| Motion target buffer | 60 Hz target samples | Motor tracking interpolates targets for both 120 Hz substeps. |
| Rendering | independent | Interpolates authoritative solved state only. |

The current public MotionBricks checkpoint remains a 30 Hz preview/planning reference. It may fill overlapping temporary buffers, but its sampled duration or target error is never rank-authoritative. The production combat representation is retrained at 60 Hz with supplied exact timing.

## 3. Required action compiler output

`SmartCombatIntent` is unilateral and immutable after commit/reveal:

```text
start/end action ticks
root + facing corridor
foot-contact preferences
weapon target corridor
anatomical target region
hand/grip anchors
torso/gaze/guard targets
stiffness and compliance curve
torque expenditure envelope
cancel/commit/recovery windows
style keyframe references
```

Hard constraints are only player-controlled or pre-existing anchors: action timing, planted foot, grip socket, existing weapon bind, and valid grapple latch. Soft constraints are preparation, torso, gaze, and recovery. Actual contact, penetration, recoil, grip failure, injury, and collapse are physical-only.

## 4. One 120 Hz substep

Given immutable pre-step state `S_t`:

1. Evaluate both committed timeline intents.
2. Sample both target-motion buffers.
3. Compute capability-limited motor torques for both fighters.
4. Step all articulated bodies, weapons, joints, armor, arena, and constraints together.
5. Collect the complete contact manifold.
6. Canonicalize contacts by stable entity/body/feature IDs.
7. Build bilateral biomechanical packets.
8. Evaluate every same-substep injury from the same pre-contact `S_t`.
9. Merge all injury/capability deltas without actor-order bias.
10. Apply the merged deltas only at the next substep boundary.
11. Record quantized state, contacts, injuries, and the substep hash.

No post-contact IK, transform teleport, or animation overwrite may move a solved body or weapon. Target refinement is permitted before the solver only.

## 5. Motor-tracking contract

For joint `i`, the physical controller attempts but is not guaranteed to reach a target:

```text
τ_i = clamp(Kp_i(q*_i - q_i) + Kd_i(q̇*_i - q̇_i) + τff_i, -τmax_i, τmax_i)
```

`τmax`, range, stiffness, damping, and grip limits derive from morphology, armor, fatigue, posture, and current injury/capability state. Weapon grips are compliant, breakable constraints. Two-handed weapons use two constraints rather than one rigid parent transform.

## 6. Bilateral contact packet

Every packet has deterministic, quantized fields and is independent of UI labels:

```text
contact_id
physics_tick
body_a / anatomy_a / feature_a
body_b / anatomy_b / feature_b
contact_point
normal
normal_impulse
tangential_impulse
relative_linear_velocity
relative_angular_velocity
contact_area_proxy
penetration_or_deformation_proxy
weapon_profile
armor_material_pair
posture_and_load_a
posture_and_load_b
```

`Hit`, `Block`, `Parry`, `Bind`, `Grapple`, and `Whiff` are derived classifications:

- **Whiff:** no qualifying weapon/body or weapon/guard packet.
- **Hit:** damaging weapon feature reaches armor/body with qualifying closing velocity and impulse.
- **Block:** guard feature intercepts before a qualifying body packet.
- **Parry:** committed parry plus guard contact plus redirection outside the original strike corridor.
- **Bind:** sustained weapon contact with low separation and opposing load.
- **Grapple:** explicit grab intent, legal hand contact, sufficient grip capacity, and successful physical constraint creation.

## 7. Injury and match consequences

Same-substep contacts resolve together. Injury is not a sequence-end batch. Capability deltas enter on the next 120 Hz substep: grip failure can release a weapon; structural damage can reduce torque/range; balance failure can activate physical recovery/collapse. Mutual lethal contact defaults to a double-KO draw until a different explicit canon rule exists.

## 8. Determinism and replay

- One duel is single-threaded unless deterministic constraint ordering is mechanically proven.
- Contact canonicalization, insertion order, entity IDs, quantization, solver configuration, action compiler, model manifest, skeleton, anatomy, armor, and arena versions are replay-hashed.
- GPU inference is never independently run by heterogeneous ranked clients. Rank authority uses baked quantized targets, signed server-generated targets, or server-resolved physics.

## 9. Acceptance gates

1. Mirrored fighter/order permutation yields equal canonical state and packet hashes.
2. A fast weapon passing through a defender between endpoint samples is detected by swept CCD at 120 Hz.
3. A block packet preceding a body packet classifies as Block, not Hit.
4. Same-substep mutual lethal contacts produce a draw and equal capability-update timing.
5. Grip overload breaks a two-handed constraint without a transform teleport.
6. A replay at two render rates emits identical 60 Hz action and 120 Hz physics hashes.
7. Motion targets are perturbed within the public model error bound; physics remains the sole outcome source.

## 10. Immediate implementation order

1. Deterministic swept weapon geometry (current unit).
2. Explicit physical contact batch admission; remove synthetic truth contact fallback.
3. Versioned 60/120 Hz state and replay packet schema.
4. One articulated body, dynamic sword, compliant grip, and ground contact.
5. Two hand-authored strike/guard target buffers in the shared world.
6. Bilateral contact packets and four reduced injury outcomes.
7. MotionBricks runtime parity as a separate planner boundary.
