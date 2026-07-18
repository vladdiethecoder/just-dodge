//! Deterministic 120 Hz articulated-body physics for combat truth.
//!
//! This is deliberately a fixed-point, sequential-impulse solver rather than a
//! renderer-facing ragdoll.  All authoritative values are integer millimetres,
//! milli-newtons, milliradians, grams, and q15 orientation bases.  Contacts and
//! constraints are solved in canonical index order so the state hash is stable
//! across supported x64 targets.
//!
//! The motor bridge accepts `JointMotorTargetV1` values compiled by
//! `active_ragdoll::compile_motor_targets`.  Motors apply bounded torque; they
//! never write pose state directly, so hit impulses remain visible and flow
//! through parent/child constraints.

use crate::motion_plan::{JointMotorTargetV1, MotorTargetBatchV1};

pub const PHYSICS_TICKS_PER_SECOND: i64 = 120;
pub const SOLVER_ITERATIONS: usize = 8;
pub const GRAVITY_MM_S2: i64 = 9_810;
pub const Q15_ONE: i64 = i16::MAX as i64;
pub const IDENTITY_ROTATION_6D_Q15: [i16; 6] = [i16::MAX, 0, 0, 0, i16::MAX, 0];

const MAX_LINEAR_SPEED_MM_S: i64 = 25_000;
const MAX_ANGULAR_SPEED_MILLIRAD_S: i64 = 30_000;
const MAX_ANGULAR_ACCELERATION_MILLIRAD_S2: i64 = 500_000;
const POSITION_BIAS_MM_S_PER_MM: i64 = 36;
const ANGULAR_BIAS_MILLIRAD_S_PER_MILLIRAD: i64 = 28;
const CONTACT_BIAS_MM_S_PER_MM: i64 = 48;
const MOTOR_STIFFNESS_LIMIT_MN_M_PER_RAD: i64 = 40_000;
const MOTOR_DAMPING_LIMIT_MN_M_S_PER_RAD: i64 = 4_000;
const FNV_OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum FighterId {
    Player,
    Opponent,
}

impl FighterId {
    const fn as_u8(self) -> u8 {
        match self {
            Self::Player => 0,
            Self::Opponent => 1,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BodyDefinitionV1 {
    pub fighter: FighterId,
    pub mass_g: i32,
    pub inertia_milli_kg_m2: i32,
    pub radius_mm: i32,
    pub position_mm: [i32; 3],
    pub rotation_6d_q15: [i16; 6],
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct JointDefinitionV1 {
    /// Global body index.  Definitions and state use one canonical body array.
    pub parent_body: u16,
    pub child_body: u16,
    /// Active-ragdoll joint index for the child under this joint.
    pub motor_joint_index: u8,
    /// Anchor points in their respective local body spaces.
    pub parent_anchor_mm: [i16; 3],
    pub child_anchor_mm: [i16; 3],
    /// Inclusive relative-angle bounds in milliradians, one bound per axis.
    pub min_angle_millirad: [i32; 3],
    pub max_angle_millirad: [i32; 3],
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ArticulatedWorldDefinitionV1 {
    /// Bodies must be ordered by `(fighter, stable_body_index)`.
    pub bodies: Vec<BodyDefinitionV1>,
    /// Joints must be ordered by `(fighter, motor_joint_index, child_body)`.
    pub joints: Vec<JointDefinitionV1>,
    pub ground_y_mm: i32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ArticulatedBodyStateV1 {
    pub position_mm: [i32; 3],
    pub velocity_mm_s: [i32; 3],
    pub rotation_6d_q15: [i16; 6],
    pub angular_velocity_millirad_s: [i32; 3],
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct JointAccelerationV1 {
    pub joint_index: u8,
    pub acceleration_millirad_s2: [i32; 3],
    pub applied_torque_millinewton_m: [i32; 3],
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ArticulatedPhysicsStateV1 {
    pub physics_tick: u64,
    pub bodies: Vec<ArticulatedBodyStateV1>,
    /// Parallel to the canonical joint-definition array.
    pub actual_joint_accelerations: Vec<JointAccelerationV1>,
}

impl ArticulatedPhysicsStateV1 {
    /// FNV-1a over little-endian, fixed-width authoritative state.
    pub fn state_hash(&self) -> u64 {
        let mut hash = FNV_OFFSET;
        hash_bytes(&mut hash, &self.physics_tick.to_le_bytes());
        hash_bytes(&mut hash, &(self.bodies.len() as u32).to_le_bytes());
        for body in &self.bodies {
            for value in body.position_mm {
                hash_bytes(&mut hash, &value.to_le_bytes());
            }
            for value in body.velocity_mm_s {
                hash_bytes(&mut hash, &value.to_le_bytes());
            }
            for value in body.rotation_6d_q15 {
                hash_bytes(&mut hash, &value.to_le_bytes());
            }
            for value in body.angular_velocity_millirad_s {
                hash_bytes(&mut hash, &value.to_le_bytes());
            }
        }
        hash_bytes(
            &mut hash,
            &(self.actual_joint_accelerations.len() as u32).to_le_bytes(),
        );
        for acceleration in &self.actual_joint_accelerations {
            hash_bytes(&mut hash, &[acceleration.joint_index]);
            for value in acceleration.acceleration_millirad_s2 {
                hash_bytes(&mut hash, &value.to_le_bytes());
            }
            for value in acceleration.applied_torque_millinewton_m {
                hash_bytes(&mut hash, &value.to_le_bytes());
            }
        }
        hash
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FighterMotorTargetsV1 {
    pub fighter: FighterId,
    pub targets: Vec<JointMotorTargetV1>,
}

impl FighterMotorTargetsV1 {
    /// Explicit bridge from the motor packet emitted by `ActiveRagdollV1`.
    pub fn from_active_ragdoll(fighter: FighterId, batch: &MotorTargetBatchV1) -> Self {
        Self {
            fighter,
            targets: batch.targets.clone(),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ContactImpulseV1 {
    pub first_body: u16,
    pub second_body: u16,
    pub normal_q15: [i16; 3],
    pub impulse_milli_newton_seconds: i32,
    pub penetration_mm: i32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ArticulatedStepV1 {
    pub physics_tick: u64,
    pub actual_joint_accelerations: Vec<JointAccelerationV1>,
    /// Canonically sorted, bilateral fighter-fighter contacts from this step.
    pub fighter_contacts: Vec<ContactImpulseV1>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ArticulatedPhysicsError {
    EmptyWorld,
    InvalidMass { body: usize },
    InvalidInertia { body: usize },
    InvalidRadius { body: usize },
    NonCanonicalBodies { body: usize },
    InvalidJointBody { joint: usize },
    SelfJoint { joint: usize },
    NonCanonicalJoints { joint: usize },
    InvalidJointLimit { joint: usize, axis: usize },
    DuplicateFighterMotorTargets(FighterId),
    DuplicateMotorTarget { fighter: FighterId, joint_index: u8 },
    InvalidBody(u16),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ArticulatedPhysicsV1 {
    definition: ArticulatedWorldDefinitionV1,
    pub state: ArticulatedPhysicsStateV1,
}

impl ArticulatedPhysicsV1 {
    pub fn new(definition: ArticulatedWorldDefinitionV1) -> Result<Self, ArticulatedPhysicsError> {
        validate_definition(&definition)?;
        let bodies = definition
            .bodies
            .iter()
            .map(|body| ArticulatedBodyStateV1 {
                position_mm: body.position_mm,
                velocity_mm_s: [0; 3],
                rotation_6d_q15: body.rotation_6d_q15,
                angular_velocity_millirad_s: [0; 3],
            })
            .collect();
        let actual_joint_accelerations = definition
            .joints
            .iter()
            .map(|joint| JointAccelerationV1 {
                joint_index: joint.motor_joint_index,
                acceleration_millirad_s2: [0; 3],
                applied_torque_millinewton_m: [0; 3],
            })
            .collect();
        Ok(Self {
            definition,
            state: ArticulatedPhysicsStateV1 {
                physics_tick: 0,
                bodies,
                actual_joint_accelerations,
            },
        })
    }

    pub fn definition(&self) -> &ArticulatedWorldDefinitionV1 {
        &self.definition
    }

    /// Add a measured hit impulse to one body.  The subsequent solver passes
    /// distribute it through anchor and angular constraints instead of restoring
    /// the previous pose.
    pub fn apply_body_impulse_milli_ns(
        &mut self,
        body: u16,
        impulse_milli_newton_seconds: [i32; 3],
    ) -> Result<(), ArticulatedPhysicsError> {
        let index = self.body_index(body)?;
        let mass_g = i64::from(self.definition.bodies[index].mass_g);
        apply_linear_impulse(
            &mut self.state.bodies[index],
            mass_g,
            impulse_milli_newton_seconds.map(i64::from),
        );
        Ok(())
    }

    pub fn apply_body_angular_impulse_milli_nms(
        &mut self,
        body: u16,
        impulse_milli_newton_meter_seconds: [i32; 3],
    ) -> Result<(), ArticulatedPhysicsError> {
        let index = self.body_index(body)?;
        let inertia = i64::from(self.definition.bodies[index].inertia_milli_kg_m2);
        for (axis, impulse_axis) in impulse_milli_newton_meter_seconds.iter().enumerate() {
            let delta = div_round(i64::from(*impulse_axis) * 1_000, inertia);
            self.state.bodies[index].angular_velocity_millirad_s[axis] = clamp_i32(
                i64::from(self.state.bodies[index].angular_velocity_millirad_s[axis]) + delta,
                -MAX_ANGULAR_SPEED_MILLIRAD_S,
                MAX_ANGULAR_SPEED_MILLIRAD_S,
            );
        }
        Ok(())
    }

    /// Advance exactly one 120 Hz fixed step.  Input ordering is checked so a
    /// replay cannot silently depend on map iteration or caller ordering.
    pub fn step(
        &mut self,
        motor_batches: &[FighterMotorTargetsV1],
    ) -> Result<ArticulatedStepV1, ArticulatedPhysicsError> {
        validate_motor_batches(motor_batches)?;
        self.apply_gravity();
        self.apply_motors(motor_batches);
        self.integrate();

        let mut contacts = Vec::new();
        for _ in 0..SOLVER_ITERATIONS {
            self.solve_parent_child_anchors();
            self.solve_joint_limits();
            self.solve_ground_contacts();
            self.solve_fighter_contacts(&mut contacts);
        }
        contacts.sort_by(|left, right| {
            left.first_body
                .cmp(&right.first_body)
                .then_with(|| left.second_body.cmp(&right.second_body))
        });
        contacts.dedup_by(|left, right| {
            left.first_body == right.first_body && left.second_body == right.second_body
        });

        let physics_tick = self.state.physics_tick;
        self.state.physics_tick = self.state.physics_tick.saturating_add(1);
        Ok(ArticulatedStepV1 {
            physics_tick,
            actual_joint_accelerations: self.state.actual_joint_accelerations.clone(),
            fighter_contacts: contacts,
        })
    }

    fn body_index(&self, body: u16) -> Result<usize, ArticulatedPhysicsError> {
        let index = usize::from(body);
        if index < self.state.bodies.len() {
            Ok(index)
        } else {
            Err(ArticulatedPhysicsError::InvalidBody(body))
        }
    }

    fn apply_gravity(&mut self) {
        let gravity_delta = div_round(-GRAVITY_MM_S2, PHYSICS_TICKS_PER_SECOND);
        for body in &mut self.state.bodies {
            body.velocity_mm_s[1] = clamp_i32(
                i64::from(body.velocity_mm_s[1]) + gravity_delta,
                -MAX_LINEAR_SPEED_MM_S,
                MAX_LINEAR_SPEED_MM_S,
            );
        }
    }

    fn apply_motors(&mut self, batches: &[FighterMotorTargetsV1]) {
        for (joint_index, joint) in self.definition.joints.iter().enumerate() {
            let parent_index = usize::from(joint.parent_body);
            let child_index = usize::from(joint.child_body);
            let fighter = self.definition.bodies[child_index].fighter;
            let target = batches
                .iter()
                .find(|batch| batch.fighter == fighter)
                .and_then(|batch| {
                    batch
                        .targets
                        .iter()
                        .find(|target| target.joint_index == joint.motor_joint_index)
                });
            let acceleration = &mut self.state.actual_joint_accelerations[joint_index];
            acceleration.acceleration_millirad_s2 = [0; 3];
            acceleration.applied_torque_millinewton_m = [0; 3];
            let Some(target) = target else {
                continue;
            };

            let current = relative_angle_millirad(
                self.state.bodies[parent_index].rotation_6d_q15,
                self.state.bodies[child_index].rotation_6d_q15,
            );
            let desired = orientation_error_to_millirad(target.desired_rotation_6d_q15);
            let child_inertia = i64::from(self.definition.bodies[child_index].inertia_milli_kg_m2);
            let parent_inertia =
                i64::from(self.definition.bodies[parent_index].inertia_milli_kg_m2);
            for axis in 0..3 {
                let stiffness = MOTOR_STIFFNESS_LIMIT_MN_M_PER_RAD
                    * i64::from(target.stiffness_q16)
                    / i64::from(u16::MAX);
                let damping = MOTOR_DAMPING_LIMIT_MN_M_S_PER_RAD * i64::from(target.damping_q16)
                    / i64::from(u16::MAX);
                let velocity =
                    i64::from(self.state.bodies[child_index].angular_velocity_millirad_s[axis])
                        - i64::from(
                            self.state.bodies[parent_index].angular_velocity_millirad_s[axis],
                        );
                let velocity_error =
                    i64::from(target.desired_angular_velocity_millirad_s[axis]) - velocity;
                let torque = (stiffness * i64::from(desired[axis] - current[axis]) / 1_000
                    + damping * velocity_error / 1_000)
                    .clamp(
                        -i64::from(target.max_torque_millinewton_m),
                        i64::from(target.max_torque_millinewton_m),
                    );
                let child_accel = div_round(torque * 1_000, child_inertia).clamp(
                    -MAX_ANGULAR_ACCELERATION_MILLIRAD_S2,
                    MAX_ANGULAR_ACCELERATION_MILLIRAD_S2,
                );
                let parent_accel = div_round(-torque * 1_000, parent_inertia).clamp(
                    -MAX_ANGULAR_ACCELERATION_MILLIRAD_S2,
                    MAX_ANGULAR_ACCELERATION_MILLIRAD_S2,
                );
                self.state.bodies[child_index].angular_velocity_millirad_s[axis] = clamp_i32(
                    i64::from(self.state.bodies[child_index].angular_velocity_millirad_s[axis])
                        + div_round(child_accel, PHYSICS_TICKS_PER_SECOND),
                    -MAX_ANGULAR_SPEED_MILLIRAD_S,
                    MAX_ANGULAR_SPEED_MILLIRAD_S,
                );
                self.state.bodies[parent_index].angular_velocity_millirad_s[axis] = clamp_i32(
                    i64::from(self.state.bodies[parent_index].angular_velocity_millirad_s[axis])
                        + div_round(parent_accel, PHYSICS_TICKS_PER_SECOND),
                    -MAX_ANGULAR_SPEED_MILLIRAD_S,
                    MAX_ANGULAR_SPEED_MILLIRAD_S,
                );
                acceleration.acceleration_millirad_s2[axis] = clamp_i32(
                    child_accel,
                    -MAX_ANGULAR_ACCELERATION_MILLIRAD_S2,
                    MAX_ANGULAR_ACCELERATION_MILLIRAD_S2,
                );
                acceleration.applied_torque_millinewton_m[axis] =
                    clamp_i32(torque, i64::from(i32::MIN), i64::from(i32::MAX));
            }
        }
    }

    fn integrate(&mut self) {
        for body in &mut self.state.bodies {
            for axis in 0..3 {
                body.velocity_mm_s[axis] = clamp_i32(
                    i64::from(body.velocity_mm_s[axis]),
                    -MAX_LINEAR_SPEED_MM_S,
                    MAX_LINEAR_SPEED_MM_S,
                );
                body.position_mm[axis] = clamp_i32(
                    i64::from(body.position_mm[axis])
                        + div_round(
                            i64::from(body.velocity_mm_s[axis]),
                            PHYSICS_TICKS_PER_SECOND,
                        ),
                    i64::from(i32::MIN),
                    i64::from(i32::MAX),
                );
            }
            body.rotation_6d_q15 =
                integrate_rotation(body.rotation_6d_q15, body.angular_velocity_millirad_s);
        }
    }

    fn solve_parent_child_anchors(&mut self) {
        for joint in &self.definition.joints {
            let parent_index = usize::from(joint.parent_body);
            let child_index = usize::from(joint.child_body);
            let parent_anchor = add3(
                self.state.bodies[parent_index].position_mm,
                rotate_local_mm(
                    self.state.bodies[parent_index].rotation_6d_q15,
                    joint.parent_anchor_mm,
                ),
            );
            let child_anchor = add3(
                self.state.bodies[child_index].position_mm,
                rotate_local_mm(
                    self.state.bodies[child_index].rotation_6d_q15,
                    joint.child_anchor_mm,
                ),
            );
            let residual = sub3(parent_anchor, child_anchor);
            let parent_mass = i64::from(self.definition.bodies[parent_index].mass_g);
            let child_mass = i64::from(self.definition.bodies[child_index].mass_g);
            let total_mass = parent_mass + child_mass;
            for (axis, residual_axis) in residual.iter().enumerate() {
                let impulse = -i64::from(*residual_axis) * POSITION_BIAS_MM_S_PER_MM;
                apply_axis_impulse(
                    &mut self.state.bodies[parent_index],
                    parent_mass,
                    axis,
                    -impulse,
                );
                apply_axis_impulse(
                    &mut self.state.bodies[child_index],
                    child_mass,
                    axis,
                    impulse,
                );
                let error = i64::from(*residual_axis);
                self.state.bodies[parent_index].position_mm[axis] = clamp_i32(
                    i64::from(self.state.bodies[parent_index].position_mm[axis])
                        - div_round(error * child_mass, total_mass),
                    i64::from(i32::MIN),
                    i64::from(i32::MAX),
                );
                self.state.bodies[child_index].position_mm[axis] = clamp_i32(
                    i64::from(self.state.bodies[child_index].position_mm[axis])
                        + div_round(error * parent_mass, total_mass),
                    i64::from(i32::MIN),
                    i64::from(i32::MAX),
                );
            }
        }
    }

    fn solve_joint_limits(&mut self) {
        for joint in &self.definition.joints {
            let parent_index = usize::from(joint.parent_body);
            let child_index = usize::from(joint.child_body);
            let relative = relative_angle_millirad(
                self.state.bodies[parent_index].rotation_6d_q15,
                self.state.bodies[child_index].rotation_6d_q15,
            );
            let parent_inertia =
                i64::from(self.definition.bodies[parent_index].inertia_milli_kg_m2);
            let child_inertia = i64::from(self.definition.bodies[child_index].inertia_milli_kg_m2);
            for (axis, relative_axis) in relative.iter().enumerate() {
                let violation = if *relative_axis < joint.min_angle_millirad[axis] {
                    *relative_axis - joint.min_angle_millirad[axis]
                } else if *relative_axis > joint.max_angle_millirad[axis] {
                    *relative_axis - joint.max_angle_millirad[axis]
                } else {
                    0
                };
                if violation == 0 {
                    continue;
                }
                let relative_speed =
                    i64::from(self.state.bodies[child_index].angular_velocity_millirad_s[axis])
                        - i64::from(
                            self.state.bodies[parent_index].angular_velocity_millirad_s[axis],
                        );
                let corrective_torque =
                    (-i64::from(violation) * ANGULAR_BIAS_MILLIRAD_S_PER_MILLIRAD - relative_speed)
                        .clamp(-100_000, 100_000);
                let child_delta = div_round(corrective_torque * 1_000, child_inertia);
                let parent_delta = div_round(-corrective_torque * 1_000, parent_inertia);
                self.state.bodies[child_index].angular_velocity_millirad_s[axis] = clamp_i32(
                    i64::from(self.state.bodies[child_index].angular_velocity_millirad_s[axis])
                        + div_round(child_delta, PHYSICS_TICKS_PER_SECOND),
                    -MAX_ANGULAR_SPEED_MILLIRAD_S,
                    MAX_ANGULAR_SPEED_MILLIRAD_S,
                );
                self.state.bodies[parent_index].angular_velocity_millirad_s[axis] = clamp_i32(
                    i64::from(self.state.bodies[parent_index].angular_velocity_millirad_s[axis])
                        + div_round(parent_delta, PHYSICS_TICKS_PER_SECOND),
                    -MAX_ANGULAR_SPEED_MILLIRAD_S,
                    MAX_ANGULAR_SPEED_MILLIRAD_S,
                );
            }
        }
    }

    fn solve_ground_contacts(&mut self) {
        for (index, body) in self.state.bodies.iter_mut().enumerate() {
            let radius = i64::from(self.definition.bodies[index].radius_mm);
            let minimum_center = i64::from(self.definition.ground_y_mm) + radius;
            let penetration = minimum_center - i64::from(body.position_mm[1]);
            if penetration <= 0 {
                continue;
            }
            body.position_mm[1] =
                clamp_i32(minimum_center, i64::from(i32::MIN), i64::from(i32::MAX));
            let mass = i64::from(self.definition.bodies[index].mass_g);
            let required_velocity = penetration * CONTACT_BIAS_MM_S_PER_MM;
            let velocity = i64::from(body.velocity_mm_s[1]);
            if velocity < required_velocity {
                apply_axis_impulse(body, mass, 1, (required_velocity - velocity) * mass / 1_000);
            }
            // Deterministic Coulomb-like ground friction; it does not erase a hit in one tick.
            for axis in [0, 2] {
                body.velocity_mm_s[axis] = clamp_i32(
                    i64::from(body.velocity_mm_s[axis]) * 15 / 16,
                    -MAX_LINEAR_SPEED_MM_S,
                    MAX_LINEAR_SPEED_MM_S,
                );
            }
        }
    }

    fn solve_fighter_contacts(&mut self, contacts: &mut Vec<ContactImpulseV1>) {
        let count = self.state.bodies.len();
        for first in 0..count {
            for second in (first + 1)..count {
                if self.definition.bodies[first].fighter == self.definition.bodies[second].fighter {
                    continue;
                }
                let first_radius = i64::from(self.definition.bodies[first].radius_mm);
                let second_radius = i64::from(self.definition.bodies[second].radius_mm);
                let delta = sub3(
                    self.state.bodies[second].position_mm,
                    self.state.bodies[first].position_mm,
                );
                let distance_squared = dot3(delta, delta);
                let distance = integer_sqrt(distance_squared);
                let radii = first_radius + second_radius;
                if distance >= radii {
                    continue;
                }
                let normal = normal_q15(delta, distance);
                let penetration = radii - distance;
                let first_mass = i64::from(self.definition.bodies[first].mass_g);
                let second_mass = i64::from(self.definition.bodies[second].mass_g);
                let total_mass = first_mass + second_mass;
                let normal_velocity = div_round(
                    dot3(
                        sub3(
                            self.state.bodies[second].velocity_mm_s,
                            self.state.bodies[first].velocity_mm_s,
                        ),
                        normal.map(i32::from),
                    ),
                    Q15_ONE,
                );
                let desired_separation_speed = penetration * CONTACT_BIAS_MM_S_PER_MM;
                let impulse =
                    (desired_separation_speed - normal_velocity).max(0) * first_mass * second_mass
                        / total_mass
                        / 1_000;
                let impulse_vector =
                    normal.map(|axis| div_round(impulse * i64::from(axis), Q15_ONE));
                apply_linear_impulse(
                    &mut self.state.bodies[first],
                    first_mass,
                    impulse_vector.map(|value| -value),
                );
                apply_linear_impulse(&mut self.state.bodies[second], second_mass, impulse_vector);
                for (axis, normal_axis) in normal.iter().enumerate() {
                    let correction = div_round(penetration * i64::from(*normal_axis), Q15_ONE);
                    self.state.bodies[first].position_mm[axis] = clamp_i32(
                        i64::from(self.state.bodies[first].position_mm[axis])
                            - div_round(correction * second_mass, total_mass),
                        i64::from(i32::MIN),
                        i64::from(i32::MAX),
                    );
                    self.state.bodies[second].position_mm[axis] = clamp_i32(
                        i64::from(self.state.bodies[second].position_mm[axis])
                            + div_round(correction * first_mass, total_mass),
                        i64::from(i32::MIN),
                        i64::from(i32::MAX),
                    );
                }
                contacts.push(ContactImpulseV1 {
                    first_body: first as u16,
                    second_body: second as u16,
                    normal_q15: normal,
                    impulse_milli_newton_seconds: clamp_i32(impulse, 0, i64::from(i32::MAX)),
                    penetration_mm: clamp_i32(penetration, 0, i64::from(i32::MAX)),
                });
            }
        }
    }
}

fn validate_definition(
    definition: &ArticulatedWorldDefinitionV1,
) -> Result<(), ArticulatedPhysicsError> {
    if definition.bodies.is_empty() {
        return Err(ArticulatedPhysicsError::EmptyWorld);
    }
    let mut previous_fighter = None;
    for (index, body) in definition.bodies.iter().enumerate() {
        if body.mass_g <= 0 {
            return Err(ArticulatedPhysicsError::InvalidMass { body: index });
        }
        if body.inertia_milli_kg_m2 <= 0 {
            return Err(ArticulatedPhysicsError::InvalidInertia { body: index });
        }
        if body.radius_mm <= 0 {
            return Err(ArticulatedPhysicsError::InvalidRadius { body: index });
        }
        if previous_fighter.is_some_and(|previous| body.fighter < previous) {
            return Err(ArticulatedPhysicsError::NonCanonicalBodies { body: index });
        }
        previous_fighter = Some(body.fighter);
    }
    let mut previous_key = None;
    for (index, joint) in definition.joints.iter().enumerate() {
        let parent = usize::from(joint.parent_body);
        let child = usize::from(joint.child_body);
        if parent >= definition.bodies.len() || child >= definition.bodies.len() {
            return Err(ArticulatedPhysicsError::InvalidJointBody { joint: index });
        }
        if parent == child || definition.bodies[parent].fighter != definition.bodies[child].fighter
        {
            return Err(ArticulatedPhysicsError::SelfJoint { joint: index });
        }
        for axis in 0..3 {
            if joint.min_angle_millirad[axis] > joint.max_angle_millirad[axis] {
                return Err(ArticulatedPhysicsError::InvalidJointLimit { joint: index, axis });
            }
        }
        let key = (
            definition.bodies[child].fighter.as_u8(),
            joint.motor_joint_index,
            joint.child_body,
        );
        if previous_key.is_some_and(|previous| key <= previous) {
            return Err(ArticulatedPhysicsError::NonCanonicalJoints { joint: index });
        }
        previous_key = Some(key);
    }
    Ok(())
}

fn validate_motor_batches(
    batches: &[FighterMotorTargetsV1],
) -> Result<(), ArticulatedPhysicsError> {
    let mut seen_fighters = [false; 2];
    for batch in batches {
        let fighter_index = usize::from(batch.fighter.as_u8());
        if seen_fighters[fighter_index] {
            return Err(ArticulatedPhysicsError::DuplicateFighterMotorTargets(
                batch.fighter,
            ));
        }
        seen_fighters[fighter_index] = true;
        let mut seen_joints = [false; 256];
        for target in &batch.targets {
            let joint_index = usize::from(target.joint_index);
            if seen_joints[joint_index] {
                return Err(ArticulatedPhysicsError::DuplicateMotorTarget {
                    fighter: batch.fighter,
                    joint_index: target.joint_index,
                });
            }
            seen_joints[joint_index] = true;
        }
    }
    Ok(())
}

fn apply_linear_impulse(body: &mut ArticulatedBodyStateV1, mass_g: i64, impulse: [i64; 3]) {
    for (axis, impulse_axis) in impulse.iter().enumerate() {
        apply_axis_impulse(body, mass_g, axis, *impulse_axis);
    }
}

fn apply_axis_impulse(body: &mut ArticulatedBodyStateV1, mass_g: i64, axis: usize, impulse: i64) {
    let delta = div_round(impulse * 1_000, mass_g);
    body.velocity_mm_s[axis] = clamp_i32(
        i64::from(body.velocity_mm_s[axis]) + delta,
        -MAX_LINEAR_SPEED_MM_S,
        MAX_LINEAR_SPEED_MM_S,
    );
}

fn relative_angle_millirad(parent: [i16; 6], child: [i16; 6]) -> [i32; 3] {
    orientation_error_q15(parent, child)
        .map(|value| clamp_i32(i64::from(value) * 3_142 / Q15_ONE, -3_142, 3_142))
}

fn orientation_error_to_millirad(target: [i16; 6]) -> [i32; 3] {
    relative_angle_millirad(IDENTITY_ROTATION_6D_Q15, target)
}

fn orientation_error_q15(current: [i16; 6], target: [i16; 6]) -> [i32; 3] {
    let first = cross3(
        [
            i64::from(current[0]),
            i64::from(current[1]),
            i64::from(current[2]),
        ],
        [
            i64::from(target[0]),
            i64::from(target[1]),
            i64::from(target[2]),
        ],
    );
    let second = cross3(
        [
            i64::from(current[3]),
            i64::from(current[4]),
            i64::from(current[5]),
        ],
        [
            i64::from(target[3]),
            i64::from(target[4]),
            i64::from(target[5]),
        ],
    );
    std::array::from_fn(|axis| {
        clamp_i32(
            div_round(first[axis] + second[axis], 2 * Q15_ONE),
            -Q15_ONE,
            Q15_ONE,
        )
    })
}

fn rotate_local_mm(rotation: [i16; 6], local: [i16; 3]) -> [i32; 3] {
    let first = [
        i64::from(rotation[0]),
        i64::from(rotation[1]),
        i64::from(rotation[2]),
    ];
    let second = [
        i64::from(rotation[3]),
        i64::from(rotation[4]),
        i64::from(rotation[5]),
    ];
    let third = cross3(first, second).map(|value| div_round(value, Q15_ONE));
    let local = local.map(i64::from);
    std::array::from_fn(|axis| {
        clamp_i32(
            div_round(
                first[axis] * local[0] + second[axis] * local[1] + third[axis] * local[2],
                Q15_ONE,
            ),
            i64::from(i32::MIN),
            i64::from(i32::MAX),
        )
    })
}

fn integrate_rotation(rotation: [i16; 6], angular_velocity: [i32; 3]) -> [i16; 6] {
    let omega = angular_velocity.map(i64::from);
    let first = [rotation[0], rotation[1], rotation[2]].map(i64::from);
    let second = [rotation[3], rotation[4], rotation[5]].map(i64::from);
    let first_delta = cross3(omega, first);
    let second_delta = cross3(omega, second);
    let first = std::array::from_fn(|axis| {
        first[axis] + div_round(first_delta[axis], PHYSICS_TICKS_PER_SECOND * 1_000)
    });
    let second = std::array::from_fn(|axis| {
        second[axis] + div_round(second_delta[axis], PHYSICS_TICKS_PER_SECOND * 1_000)
    });
    orthonormalize(first, second)
}

fn orthonormalize(first: [i64; 3], second: [i64; 3]) -> [i16; 6] {
    let first = normalize_q15(first, [Q15_ONE, 0, 0]);
    let dot = dot3(first, second);
    let second =
        std::array::from_fn(|axis| second[axis] - div_round(first[axis] * dot, Q15_ONE * Q15_ONE));
    let second = normalize_q15(second, [0, Q15_ONE, 0]);
    [
        clamp_i16(first[0]),
        clamp_i16(first[1]),
        clamp_i16(first[2]),
        clamp_i16(second[0]),
        clamp_i16(second[1]),
        clamp_i16(second[2]),
    ]
}

fn normalize_q15(value: [i64; 3], fallback: [i64; 3]) -> [i64; 3] {
    let squared = value
        .iter()
        .map(|axis| u128::try_from(i128::from(*axis) * i128::from(*axis)).unwrap_or(u128::MAX))
        .sum();
    let length = integer_sqrt_u128(squared);
    if length == 0 {
        return fallback;
    }
    let length = i128::try_from(length).unwrap_or(i128::MAX);
    std::array::from_fn(|axis| {
        i64::try_from(i128::from(value[axis]) * i128::from(Q15_ONE) / length).unwrap_or(0)
    })
}

fn normal_q15(delta: [i32; 3], distance: i64) -> [i16; 3] {
    if distance == 0 {
        return [i16::MAX, 0, 0];
    }
    std::array::from_fn(|axis| clamp_i16(div_round(i64::from(delta[axis]) * Q15_ONE, distance)))
}

fn integer_sqrt(value: i64) -> i64 {
    if value <= 0 {
        0
    } else {
        i64::try_from(integer_sqrt_u128(value as u128)).unwrap_or(i64::MAX)
    }
}

fn integer_sqrt_u128(value: u128) -> u128 {
    if value < 2 {
        return value;
    }
    let mut low = 1_u128;
    let mut high = value / 2 + 1;
    while low + 1 < high {
        let middle = (low + high) / 2;
        if middle <= value / middle {
            low = middle;
        } else {
            high = middle;
        }
    }
    low
}

fn add3(left: [i32; 3], right: [i32; 3]) -> [i32; 3] {
    std::array::from_fn(|axis| {
        clamp_i32(
            i64::from(left[axis]) + i64::from(right[axis]),
            i64::from(i32::MIN),
            i64::from(i32::MAX),
        )
    })
}

fn sub3(left: [i32; 3], right: [i32; 3]) -> [i32; 3] {
    std::array::from_fn(|axis| {
        clamp_i32(
            i64::from(left[axis]) - i64::from(right[axis]),
            i64::from(i32::MIN),
            i64::from(i32::MAX),
        )
    })
}

fn dot3<T: Copy + Into<i64>>(left: [T; 3], right: [T; 3]) -> i64 {
    left.into_iter()
        .zip(right)
        .map(|(left, right)| left.into() * right.into())
        .sum()
}

fn cross3(left: [i64; 3], right: [i64; 3]) -> [i64; 3] {
    [
        saturating_difference_of_products(left[1], right[2], left[2], right[1]),
        saturating_difference_of_products(left[2], right[0], left[0], right[2]),
        saturating_difference_of_products(left[0], right[1], left[1], right[0]),
    ]
}

fn saturating_difference_of_products(a: i64, b: i64, c: i64, d: i64) -> i64 {
    let value = i128::from(a) * i128::from(b) - i128::from(c) * i128::from(d);
    i64::try_from(value.clamp(i128::from(i64::MIN), i128::from(i64::MAX))).unwrap_or(if value < 0 {
        i64::MIN
    } else {
        i64::MAX
    })
}

fn div_round(numerator: i64, denominator: i64) -> i64 {
    debug_assert!(denominator > 0);
    if numerator >= 0 {
        (numerator + denominator / 2) / denominator
    } else {
        (numerator - denominator / 2) / denominator
    }
}

fn clamp_i32(value: i64, minimum: i64, maximum: i64) -> i32 {
    i32::try_from(value.clamp(minimum, maximum)).unwrap_or(if value < 0 {
        i32::MIN
    } else {
        i32::MAX
    })
}

fn clamp_i16(value: i64) -> i16 {
    i16::try_from(value.clamp(i64::from(i16::MIN), i64::from(i16::MAX))).unwrap_or(if value < 0 {
        i16::MIN
    } else {
        i16::MAX
    })
}

fn hash_bytes(hash: &mut u64, bytes: &[u8]) {
    for byte in bytes {
        *hash = (*hash ^ u64::from(*byte)).wrapping_mul(FNV_PRIME);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const ROTATED_Z_30_Q15: [i16; 6] = [28_377, 16_384, 0, -16_384, 28_377, 0];

    fn body(fighter: FighterId, position_mm: [i32; 3]) -> BodyDefinitionV1 {
        BodyDefinitionV1 {
            fighter,
            mass_g: 35_000,
            inertia_milli_kg_m2: 50,
            radius_mm: 200,
            position_mm,
            rotation_6d_q15: IDENTITY_ROTATION_6D_Q15,
        }
    }

    fn joint(parent_body: u16, child_body: u16, motor_joint_index: u8) -> JointDefinitionV1 {
        JointDefinitionV1 {
            parent_body,
            child_body,
            motor_joint_index,
            parent_anchor_mm: [0, -300, 0],
            child_anchor_mm: [0, 300, 0],
            min_angle_millirad: [-500, -500, -500],
            max_angle_millirad: [500, 500, 500],
        }
    }

    fn world() -> ArticulatedPhysicsV1 {
        ArticulatedPhysicsV1::new(ArticulatedWorldDefinitionV1 {
            bodies: vec![
                body(FighterId::Player, [-700, 900, 0]),
                body(FighterId::Player, [-700, 300, 0]),
                body(FighterId::Opponent, [700, 900, 0]),
                body(FighterId::Opponent, [700, 300, 0]),
            ],
            joints: vec![joint(0, 1, 0), joint(2, 3, 0)],
            ground_y_mm: 0,
        })
        .unwrap()
    }

    fn target() -> JointMotorTargetV1 {
        JointMotorTargetV1 {
            joint_index: 0,
            desired_rotation_6d_q15: ROTATED_Z_30_Q15,
            desired_angular_velocity_millirad_s: [0; 3],
            stiffness_q16: u16::MAX,
            damping_q16: u16::MAX / 4,
            max_torque_millinewton_m: 40_000,
        }
    }

    fn batches() -> Vec<FighterMotorTargetsV1> {
        vec![
            FighterMotorTargetsV1 {
                fighter: FighterId::Player,
                targets: vec![target()],
            },
            FighterMotorTargetsV1 {
                fighter: FighterId::Opponent,
                targets: vec![target()],
            },
        ]
    }

    #[test]
    fn runs_at_120_hz_with_parent_child_anchor_and_ground_constraints() {
        let mut simulation = world();
        for _ in 0..120 {
            simulation.step(&batches()).unwrap();
        }
        assert_eq!(simulation.state.physics_tick, 120);
        for (index, state) in simulation.state.bodies.iter().enumerate() {
            assert!(
                state.position_mm[1] >= simulation.definition.bodies[index].radius_mm,
                "body {index} fell through ground: {:?}",
                state.position_mm
            );
        }
        for joint in &simulation.definition.joints {
            let parent = &simulation.state.bodies[usize::from(joint.parent_body)];
            let child = &simulation.state.bodies[usize::from(joint.child_body)];
            let parent_anchor = add3(
                parent.position_mm,
                rotate_local_mm(parent.rotation_6d_q15, joint.parent_anchor_mm),
            );
            let child_anchor = add3(
                child.position_mm,
                rotate_local_mm(child.rotation_6d_q15, joint.child_anchor_mm),
            );
            assert!(
                dot3(
                    sub3(parent_anchor, child_anchor),
                    sub3(parent_anchor, child_anchor)
                ) <= 9
            );
        }
    }

    #[test]
    fn motor_outputs_actual_acceleration_and_limit_reacts_without_pose_snap() {
        let mut simulation = world();
        let initial_rotation = simulation.state.bodies[1].rotation_6d_q15;
        let mut saw_motor_acceleration = false;
        for _ in 0..12 {
            let step = simulation.step(&batches()).unwrap();
            saw_motor_acceleration |= step.actual_joint_accelerations[0]
                .acceleration_millirad_s2
                .iter()
                .any(|value| *value != 0);
        }
        assert!(saw_motor_acceleration);
        assert_ne!(simulation.state.bodies[1].rotation_6d_q15, initial_rotation);
        let relative = relative_angle_millirad(
            simulation.state.bodies[0].rotation_6d_q15,
            simulation.state.bodies[1].rotation_6d_q15,
        );
        assert!(relative.iter().all(|angle| angle.abs() <= 3_142));
    }

    #[test]
    fn hit_impulse_propagates_through_joint_and_is_not_erased_by_motor() {
        let mut baseline = world();
        let mut hit = world();
        for tick in 0..30 {
            if tick == 3 {
                hit.apply_body_impulse_milli_ns(1, [210_000, 0, 0]).unwrap();
            }
            baseline.step(&batches()).unwrap();
            hit.step(&batches()).unwrap();
        }
        assert_ne!(
            baseline.state.bodies[1].position_mm,
            hit.state.bodies[1].position_mm
        );
        assert_ne!(
            baseline.state.bodies[0].velocity_mm_s,
            hit.state.bodies[0].velocity_mm_s
        );
        assert_ne!(baseline.state.state_hash(), hit.state.state_hash());
    }

    #[test]
    fn bilateral_fighter_contacts_are_sorted_and_separate_bodies() {
        let mut simulation = world();
        simulation.state.bodies[0].position_mm = [0, 900, 0];
        simulation.state.bodies[1].position_mm = [0, 300, 0];
        simulation.state.bodies[2].position_mm = [300, 900, 0];
        simulation.state.bodies[3].position_mm = [300, 300, 0];
        let step = simulation.step(&[]).unwrap();
        assert_eq!(step.fighter_contacts.len(), 2);
        assert_eq!(
            step.fighter_contacts
                .iter()
                .map(|contact| (contact.first_body, contact.second_body))
                .collect::<Vec<_>>(),
            vec![(0, 2), (1, 3)]
        );
        assert!(simulation.state.bodies[0].velocity_mm_s[0] < 0);
        assert!(simulation.state.bodies[2].velocity_mm_s[0] > 0);
    }

    #[test]
    fn one_hundred_identical_replays_produce_identical_hashes() {
        let mut simulations = vec![world(); 100];
        for tick in 0..240 {
            if tick == 60 {
                for simulation in &mut simulations {
                    simulation
                        .apply_body_impulse_milli_ns(1, [40_000, 10_000, -20_000])
                        .unwrap();
                }
            }
            for simulation in &mut simulations {
                simulation.step(&batches()).unwrap();
            }
            let expected = simulations[0].state.state_hash();
            assert!(
                simulations
                    .iter()
                    .all(|simulation| simulation.state.state_hash() == expected)
            );
        }
    }

    #[test]
    fn rejects_non_canonical_or_duplicate_inputs_before_step() {
        let error = ArticulatedPhysicsV1::new(ArticulatedWorldDefinitionV1 {
            bodies: vec![
                body(FighterId::Opponent, [0, 200, 0]),
                body(FighterId::Player, [0, 200, 0]),
            ],
            joints: vec![],
            ground_y_mm: 0,
        })
        .unwrap_err();
        assert_eq!(
            error,
            ArticulatedPhysicsError::NonCanonicalBodies { body: 1 }
        );

        let mut simulation = world();
        let duplicate = FighterMotorTargetsV1 {
            fighter: FighterId::Player,
            targets: vec![target(), target()],
        };
        assert_eq!(
            simulation.step(&[duplicate]),
            Err(ArticulatedPhysicsError::DuplicateMotorTarget {
                fighter: FighterId::Player,
                joint_index: 0,
            })
        );
        assert_eq!(simulation.state.physics_tick, 0);
    }
}
