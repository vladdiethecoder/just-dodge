//! Deterministic active-ragdoll tracking core.
//!
//! This module owns no combat outcomes and performs no collision detection. It
//! converts an admitted motion plan into bounded spherical-joint motor targets,
//! advances 34 independent integer rotational states plus root servo dynamics
//! at 120 Hz, and preserves perturbations instead of snapping back to kinematic
//! poses. Parent-child rigid-body coupling, joint limits, gravity, contacts, and
//! balance constraints belong to the next articulated-physics layer; this file
//! must not be presented as that completed layer.

use crate::motion_plan::{
    JointMotorTargetV1, MAX_MOTOR_TARGETS, MotionPlanError, MotionPlanPacketV1, MotorTargetBatchV1,
    PoseTargetV1, RootTargetV1, SCHEMA_VERSION,
};

pub const PHYSICS_TICKS_PER_SECOND: i64 = 120;
pub const PHYSICS_SUBSTEPS_PER_TRUTH_TICK: u64 = 2;
pub const JOINT_COUNT: usize = MAX_MOTOR_TARGETS;
pub const IDENTITY_ROTATION_6D_Q15: [i16; 6] = [i16::MAX, 0, 0, 0, i16::MAX, 0];

const Q15_ONE: i64 = i16::MAX as i64;
const ROOT_MASS_GRAMS: i64 = 70_000;
const JOINT_INERTIA_MILLI_KG_M2: i64 = 50;
// Force gains: mN/mm and mN*s/mm. F[mN] * 1_000 / mass[g] = a[mm/s^2].
const ROOT_STIFFNESS_MILLI_NEWTON_PER_MM: i64 = ROOT_MASS_GRAMS * 16 / 1_000;
const ROOT_DAMPING_MILLI_NEWTON_SECOND_PER_MM: i64 = ROOT_MASS_GRAMS * 8 / 1_000;
const MAX_ROOT_ACCEL_MM_S2: i64 = 20_000;
const MAX_ROOT_SPEED_MM_S: i64 = 10_000;
const MAX_ANGULAR_SPEED_MILLIRAD_S: i64 = 20_000;
const STIFFNESS_LIMIT_NM_PER_RAD: i64 = 40;
const DAMPING_LIMIT_NM_S_PER_RAD: i64 = 4;
const FNV_OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct JointStateV1 {
    pub rotation_6d_q15: [i16; 6],
    pub angular_velocity_millirad_s: [i32; 3],
    pub applied_torque_millinewton_m: [i32; 3],
}

impl Default for JointStateV1 {
    fn default() -> Self {
        Self {
            rotation_6d_q15: IDENTITY_ROTATION_6D_Q15,
            angular_velocity_millirad_s: [0; 3],
            applied_torque_millinewton_m: [0; 3],
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ActiveRagdollStateV1 {
    pub physics_tick: u64,
    pub plan_id: u64,
    pub plan_hash: u64,
    pub root_position_mm: [i32; 3],
    pub root_velocity_mm_s: [i32; 3],
    pub joints: [JointStateV1; JOINT_COUNT],
}

impl ActiveRagdollStateV1 {
    pub fn state_hash(&self) -> u64 {
        let mut hash = FNV_OFFSET;
        hash_bytes(&mut hash, &self.physics_tick.to_le_bytes());
        hash_bytes(&mut hash, &self.plan_id.to_le_bytes());
        hash_bytes(&mut hash, &self.plan_hash.to_le_bytes());
        for value in self.root_position_mm {
            hash_bytes(&mut hash, &value.to_le_bytes());
        }
        for value in self.root_velocity_mm_s {
            hash_bytes(&mut hash, &value.to_le_bytes());
        }
        for joint in &self.joints {
            for value in joint.rotation_6d_q15 {
                hash_bytes(&mut hash, &value.to_le_bytes());
            }
            for value in joint.angular_velocity_millirad_s {
                hash_bytes(&mut hash, &value.to_le_bytes());
            }
            for value in joint.applied_torque_millinewton_m {
                hash_bytes(&mut hash, &value.to_le_bytes());
            }
        }
        hash
    }

    pub fn kinetic_energy_millijoules(&self) -> u64 {
        // Translational: g * (mm/s)^2 / 2_000_000 = mJ.
        let root_speed_squared: i128 = self
            .root_velocity_mm_s
            .iter()
            .map(|value| i128::from(*value) * i128::from(*value))
            .sum();
        let root = i128::from(ROOT_MASS_GRAMS) * root_speed_squared / 2_000_000;
        // Rotational: milli-kg*m^2 * (millirad/s)^2 / 2_000_000 = mJ.
        let joints: i128 = self
            .joints
            .iter()
            .flat_map(|joint| joint.angular_velocity_millirad_s)
            .map(|value| {
                i128::from(JOINT_INERTIA_MILLI_KG_M2) * i128::from(value) * i128::from(value)
                    / 2_000_000
            })
            .sum();
        u64::try_from(root.saturating_add(joints)).unwrap_or(u64::MAX)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ActiveRagdollV1 {
    pub state: ActiveRagdollStateV1,
}

impl ActiveRagdollV1 {
    pub fn from_plan(plan: &MotionPlanPacketV1) -> Result<Self, ActiveRagdollError> {
        plan.validate()?;
        let first_root = plan
            .root_targets
            .first()
            .ok_or(ActiveRagdollError::MissingInitialRootTarget)?;
        let mut joints = [JointStateV1::default(); JOINT_COUNT];
        for joint_index in 0..JOINT_COUNT {
            let joint_index_u8 = joint_index as u8;
            let target = initial_pose_for_joint(&plan.pose_targets, joint_index_u8).ok_or(
                ActiveRagdollError::MissingInitialJointTarget(joint_index_u8),
            )?;
            joints[joint_index].rotation_6d_q15 = target.rotation_6d_q15;
        }
        Ok(Self {
            state: ActiveRagdollStateV1 {
                physics_tick: 0,
                plan_id: plan.plan_id,
                plan_hash: plan.plan_hash,
                root_position_mm: first_root.position_mm,
                root_velocity_mm_s: first_root.velocity_mm_s,
                joints,
            },
        })
    }

    pub fn expected_truth_tick(&self, plan: &MotionPlanPacketV1) -> u64 {
        plan.valid_from_truth_tick + self.state.physics_tick / PHYSICS_SUBSTEPS_PER_TRUTH_TICK
    }

    /// Applies impulse in milli-newton-seconds; dividing by grams yields delta mm/s.
    pub fn apply_root_impulse_milli_ns(&mut self, impulse: [i32; 3]) {
        for (velocity, impulse_axis) in self.state.root_velocity_mm_s.iter_mut().zip(impulse) {
            let delta = i64::from(impulse_axis) * 1_000 / ROOT_MASS_GRAMS;
            *velocity = clamp_i32(
                i64::from(*velocity) + delta,
                -MAX_ROOT_SPEED_MM_S,
                MAX_ROOT_SPEED_MM_S,
            );
        }
    }

    pub fn apply_joint_angular_impulse_milli_nms(
        &mut self,
        joint_index: u8,
        impulse: [i32; 3],
    ) -> Result<(), ActiveRagdollError> {
        let joint = self
            .state
            .joints
            .get_mut(usize::from(joint_index))
            .ok_or(ActiveRagdollError::InvalidJoint(joint_index))?;
        for (velocity, impulse_axis) in joint.angular_velocity_millirad_s.iter_mut().zip(impulse) {
            let delta = i64::from(impulse_axis) * 1_000 / JOINT_INERTIA_MILLI_KG_M2;
            *velocity = clamp_i32(
                i64::from(*velocity) + delta,
                -MAX_ANGULAR_SPEED_MILLIRAD_S,
                MAX_ANGULAR_SPEED_MILLIRAD_S,
            );
        }
        Ok(())
    }

    pub fn step(
        &mut self,
        plan: &MotionPlanPacketV1,
        motors: &MotorTargetBatchV1,
    ) -> Result<(), ActiveRagdollError> {
        plan.validate()?;
        motors.validate()?;
        if plan.plan_id != self.state.plan_id
            || plan.plan_hash != self.state.plan_hash
            || motors.plan_id != self.state.plan_id
        {
            return Err(ActiveRagdollError::PlanMismatch);
        }
        let expected_tick = self.expected_truth_tick(plan);
        if motors.truth_tick != expected_tick {
            return Err(ActiveRagdollError::TickMismatch {
                expected: expected_tick,
                actual: motors.truth_tick,
            });
        }
        let offset = plan_offset(plan, expected_tick)?;
        let root_target = sample_root_target(&plan.root_targets, offset);
        step_root(&mut self.state, root_target);
        for target in &motors.targets {
            step_joint(
                &mut self.state.joints[usize::from(target.joint_index)],
                target,
            );
        }
        self.state.physics_tick = self.state.physics_tick.saturating_add(1);
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ActiveRagdollError {
    MotionPlan(MotionPlanError),
    MissingInitialRootTarget,
    MissingInitialJointTarget(u8),
    PlanBeforeValidity,
    PlanExpired,
    PlanMismatch,
    TickMismatch { expected: u64, actual: u64 },
    InvalidJoint(u8),
}

impl From<MotionPlanError> for ActiveRagdollError {
    fn from(value: MotionPlanError) -> Self {
        Self::MotionPlan(value)
    }
}

pub fn compile_motor_targets(
    plan: &MotionPlanPacketV1,
    truth_tick: u64,
) -> Result<MotorTargetBatchV1, ActiveRagdollError> {
    plan.validate()?;
    let offset = plan_offset(plan, truth_tick)?;
    let offset = u16::try_from(offset).map_err(|_| ActiveRagdollError::PlanExpired)?;
    let mut targets = Vec::with_capacity(JOINT_COUNT);
    for joint_index in 0..JOINT_COUNT {
        if let Some(target) = pose_for_joint_at(&plan.pose_targets, joint_index as u8, offset) {
            targets.push(JointMotorTargetV1 {
                joint_index: joint_index as u8,
                desired_rotation_6d_q15: target.rotation_6d_q15,
                desired_angular_velocity_millirad_s: [0; 3],
                stiffness_q16: u16::MAX,
                damping_q16: u16::MAX,
                max_torque_millinewton_m: 80_000,
            });
        }
    }
    let batch = MotorTargetBatchV1 {
        schema_version: SCHEMA_VERSION,
        truth_tick,
        plan_id: plan.plan_id,
        targets,
    };
    batch.validate()?;
    Ok(batch)
}

pub fn orientation_error_q15(current: [i16; 6], target: [i16; 6]) -> [i32; 3] {
    let current_first = [current[0], current[1], current[2]];
    let current_second = [current[3], current[4], current[5]];
    let target_first = [target[0], target[1], target[2]];
    let target_second = [target[3], target[4], target[5]];
    let first = cross_q30(current_first, target_first);
    let second = cross_q30(current_second, target_second);
    std::array::from_fn(|axis| {
        clamp_i32(
            (first[axis] + second[axis]) / (2 * Q15_ONE),
            -Q15_ONE,
            Q15_ONE,
        )
    })
}

fn initial_pose_for_joint(targets: &[PoseTargetV1], joint_index: u8) -> Option<&PoseTargetV1> {
    targets
        .iter()
        .find(|target| target.joint_index == joint_index && target.tick_offset == 0)
}

fn pose_for_joint_at(
    targets: &[PoseTargetV1],
    joint_index: u8,
    offset: u16,
) -> Option<&PoseTargetV1> {
    targets
        .iter()
        .rev()
        .find(|target| target.joint_index == joint_index && target.tick_offset <= offset)
}

fn plan_offset(plan: &MotionPlanPacketV1, truth_tick: u64) -> Result<u64, ActiveRagdollError> {
    let offset = truth_tick
        .checked_sub(plan.valid_from_truth_tick)
        .ok_or(ActiveRagdollError::PlanBeforeValidity)?;
    if offset >= u64::from(plan.horizon_truth_ticks) {
        return Err(ActiveRagdollError::PlanExpired);
    }
    Ok(offset)
}

fn sample_root_target(targets: &[RootTargetV1], offset: u64) -> RootTargetV1 {
    let offset = u16::try_from(offset).unwrap_or(u16::MAX);
    let first = targets[0];
    if offset <= first.tick_offset {
        return first;
    }
    for pair in targets.windows(2) {
        let left = pair[0];
        let right = pair[1];
        if offset <= right.tick_offset {
            let numerator = i64::from(offset - left.tick_offset);
            let denominator = i64::from(right.tick_offset - left.tick_offset);
            return RootTargetV1 {
                tick_offset: offset,
                position_mm: lerp3(left.position_mm, right.position_mm, numerator, denominator),
                velocity_mm_s: lerp3(
                    left.velocity_mm_s,
                    right.velocity_mm_s,
                    numerator,
                    denominator,
                ),
                heading_q15: lerp2_i16(left.heading_q15, right.heading_q15, numerator, denominator),
            };
        }
    }
    targets[targets.len() - 1]
}

fn step_root(state: &mut ActiveRagdollStateV1, target: RootTargetV1) {
    for axis in 0..3 {
        let position_error =
            i64::from(target.position_mm[axis]) - i64::from(state.root_position_mm[axis]);
        let velocity_error =
            i64::from(target.velocity_mm_s[axis]) - i64::from(state.root_velocity_mm_s[axis]);
        let force_millinewtons = position_error * ROOT_STIFFNESS_MILLI_NEWTON_PER_MM
            + velocity_error * ROOT_DAMPING_MILLI_NEWTON_SECOND_PER_MM;
        let acceleration = div_round(force_millinewtons * 1_000, ROOT_MASS_GRAMS)
            .clamp(-MAX_ROOT_ACCEL_MM_S2, MAX_ROOT_ACCEL_MM_S2);
        let velocity = i64::from(state.root_velocity_mm_s[axis])
            + div_round(acceleration, PHYSICS_TICKS_PER_SECOND);
        state.root_velocity_mm_s[axis] =
            clamp_i32(velocity, -MAX_ROOT_SPEED_MM_S, MAX_ROOT_SPEED_MM_S);
        state.root_position_mm[axis] = clamp_i32(
            i64::from(state.root_position_mm[axis])
                + div_round(
                    i64::from(state.root_velocity_mm_s[axis]),
                    PHYSICS_TICKS_PER_SECOND,
                ),
            i64::from(i32::MIN),
            i64::from(i32::MAX),
        );
    }
}

fn step_joint(state: &mut JointStateV1, target: &JointMotorTargetV1) {
    let error_q15 = orientation_error_q15(state.rotation_6d_q15, target.desired_rotation_6d_q15);
    let stiffness =
        STIFFNESS_LIMIT_NM_PER_RAD * i64::from(target.stiffness_q16) / i64::from(u16::MAX);
    let damping = DAMPING_LIMIT_NM_S_PER_RAD * i64::from(target.damping_q16) / i64::from(u16::MAX);
    let torque_limit = i64::from(target.max_torque_millinewton_m);
    for axis in 0..3 {
        let error_millirad = i64::from(error_q15[axis]) * 1_000 / Q15_ONE;
        let velocity_error = i64::from(target.desired_angular_velocity_millirad_s[axis])
            - i64::from(state.angular_velocity_millirad_s[axis]);
        let torque = (stiffness * error_millirad + damping * velocity_error)
            .clamp(-torque_limit, torque_limit);
        state.applied_torque_millinewton_m[axis] =
            clamp_i32(torque, -i64::from(i32::MAX), i64::from(i32::MAX));
        let acceleration_millirad_s2 = torque * 1_000 / JOINT_INERTIA_MILLI_KG_M2;
        let velocity = i64::from(state.angular_velocity_millirad_s[axis])
            + div_round(acceleration_millirad_s2, PHYSICS_TICKS_PER_SECOND);
        state.angular_velocity_millirad_s[axis] = clamp_i32(
            velocity,
            -MAX_ANGULAR_SPEED_MILLIRAD_S,
            MAX_ANGULAR_SPEED_MILLIRAD_S,
        );
    }
    state.rotation_6d_q15 =
        integrate_rotation(state.rotation_6d_q15, state.angular_velocity_millirad_s);
}

fn integrate_rotation(rotation: [i16; 6], angular_velocity: [i32; 3]) -> [i16; 6] {
    let omega = angular_velocity.map(i64::from);
    let first = [rotation[0], rotation[1], rotation[2]].map(i64::from);
    let second = [rotation[3], rotation[4], rotation[5]].map(i64::from);
    let first_delta = cross_i64(omega, first);
    let second_delta = cross_i64(omega, second);
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
    let dot: i64 = first
        .iter()
        .zip(second)
        .map(|(left, right)| left * right)
        .sum();
    let second = std::array::from_fn(|axis| second[axis] - first[axis] * dot / (Q15_ONE * Q15_ONE));
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
    let squared: u128 = value
        .iter()
        .map(|axis| u128::try_from(axis * axis).unwrap_or(u128::MAX))
        .sum();
    let length = integer_sqrt(squared);
    if length == 0 {
        return fallback;
    }
    std::array::from_fn(|axis| {
        let numerator = i128::from(value[axis]) * i128::from(Q15_ONE);
        i64::try_from(numerator / i128::try_from(length).unwrap_or(i128::MAX)).unwrap_or(0)
    })
}

fn integer_sqrt(value: u128) -> u128 {
    if value < 2 {
        return value;
    }
    let mut low = 1;
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

fn cross_q30(left: [i16; 3], right: [i16; 3]) -> [i64; 3] {
    cross_i64(left.map(i64::from), right.map(i64::from))
}

fn cross_i64(left: [i64; 3], right: [i64; 3]) -> [i64; 3] {
    [
        difference_of_products(left[1], right[2], left[2], right[1]),
        difference_of_products(left[2], right[0], left[0], right[2]),
        difference_of_products(left[0], right[1], left[1], right[0]),
    ]
}

fn difference_of_products(a: i64, b: i64, c: i64, d: i64) -> i64 {
    let value = i128::from(a) * i128::from(b) - i128::from(c) * i128::from(d);
    i64::try_from(value.clamp(i128::from(i64::MIN), i128::from(i64::MAX))).unwrap_or(if value < 0 {
        i64::MIN
    } else {
        i64::MAX
    })
}

fn lerp3(left: [i32; 3], right: [i32; 3], numerator: i64, denominator: i64) -> [i32; 3] {
    std::array::from_fn(|axis| {
        clamp_i32(
            i64::from(left[axis])
                + (i64::from(right[axis]) - i64::from(left[axis])) * numerator / denominator,
            i64::from(i32::MIN),
            i64::from(i32::MAX),
        )
    })
}

fn lerp2_i16(left: [i16; 2], right: [i16; 2], numerator: i64, denominator: i64) -> [i16; 2] {
    std::array::from_fn(|axis| {
        clamp_i16(
            i64::from(left[axis])
                + (i64::from(right[axis]) - i64::from(left[axis])) * numerator / denominator,
        )
    })
}

fn div_round(numerator: i64, denominator: i64) -> i64 {
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
    use crate::motion_plan::{
        IntentCommitment, IntentDirection, IntentFootwork, IntentGrammarV1, IntentStance,
        IntentTarget, IntentTempo, IntentVerb, ModelReceiptV1, PublicMotionPhase,
    };
    use crate::truth::Side;

    const ROTATED_Z_30_Q15: [i16; 6] = [28_377, 16_384, 0, -16_384, 28_377, 0];

    fn sample_plan() -> MotionPlanPacketV1 {
        let mut pose_targets = Vec::with_capacity(JOINT_COUNT * 2);
        for tick in [0, 1] {
            for joint_index in 0..JOINT_COUNT {
                pose_targets.push(PoseTargetV1 {
                    tick_offset: tick,
                    joint_index: joint_index as u8,
                    rotation_6d_q15: if tick == 1 && joint_index == 10 {
                        ROTATED_Z_30_Q15
                    } else {
                        IDENTITY_ROTATION_6D_Q15
                    },
                });
            }
        }
        MotionPlanPacketV1 {
            schema_version: SCHEMA_VERSION,
            plan_id: 501,
            parent_plan_id: None,
            actor: Side::Player,
            source_phase: PublicMotionPhase::Reveal,
            source_truth_tick: 10,
            valid_from_truth_tick: 12,
            horizon_truth_ticks: 180,
            intent: IntentGrammarV1 {
                verb: IntentVerb::new(1).unwrap(),
                target: IntentTarget::WeaponArm,
                direction: IntentDirection::DiagonalDownRight,
                stance: IntentStance::Top,
                footwork: IntentFootwork::Advance,
                tempo: IntentTempo::Explosive,
                commitment: IntentCommitment::Committed,
            },
            legal_response_bits: 0b11,
            selected_response_bit: 0b01,
            models: ModelReceiptV1 {
                ardy_sha256: [1; 32],
                motionbricks_sha256: [2; 32],
                normalization_sha256: [3; 32],
            },
            root_targets: vec![
                RootTargetV1 {
                    tick_offset: 0,
                    position_mm: [0, 1_000, 0],
                    velocity_mm_s: [0; 3],
                    heading_q15: [0, i16::MAX],
                },
                RootTargetV1 {
                    tick_offset: 120,
                    position_mm: [240, 1_000, -120],
                    velocity_mm_s: [120, 0, -60],
                    heading_q15: [0, i16::MAX],
                },
            ],
            effector_targets: vec![],
            desired_contacts: vec![],
            pose_targets,
            balance_hints: vec![],
            plan_hash: 0,
        }
        .seal()
        .unwrap()
    }

    #[test]
    fn compiler_emits_all_spherical_joint_targets_from_sealed_plan() {
        let plan = sample_plan();
        let initial = compile_motor_targets(&plan, plan.valid_from_truth_tick).unwrap();
        assert_eq!(initial.targets.len(), JOINT_COUNT);
        assert_eq!(
            initial.targets[10].desired_rotation_6d_q15,
            IDENTITY_ROTATION_6D_Q15
        );
        let changed = compile_motor_targets(&plan, plan.valid_from_truth_tick + 1).unwrap();
        assert_eq!(
            changed.targets[10].desired_rotation_6d_q15,
            ROTATED_Z_30_Q15
        );
        assert_eq!(changed.validate(), Ok(()));
    }

    #[test]
    fn tracking_reduces_error_with_bounded_torque_and_energy() {
        let plan = sample_plan();
        let mut body = ActiveRagdollV1::from_plan(&plan).unwrap();
        for _ in 0..2 {
            let tick = body.expected_truth_tick(&plan);
            let motors = compile_motor_targets(&plan, tick).unwrap();
            body.step(&plan, &motors).unwrap();
        }
        let before =
            orientation_error_q15(body.state.joints[10].rotation_6d_q15, ROTATED_Z_30_Q15)[2].abs();
        let mut peak_energy = 0;
        for _ in 0..238 {
            let tick = body.expected_truth_tick(&plan);
            let motors = compile_motor_targets(&plan, tick).unwrap();
            body.step(&plan, &motors).unwrap();
            peak_energy = peak_energy.max(body.state.kinetic_energy_millijoules());
            for joint in &body.state.joints {
                assert!(
                    joint
                        .applied_torque_millinewton_m
                        .iter()
                        .all(|torque| torque.abs() <= 80_000)
                );
            }
        }
        let after =
            orientation_error_q15(body.state.joints[10].rotation_6d_q15, ROTATED_Z_30_Q15)[2].abs();
        assert!(
            after < before,
            "orientation error did not improve: {before} -> {after}"
        );
        assert!(
            peak_energy < 5_000_000,
            "kinetic energy escaped: {peak_energy} mJ"
        );
        assert!((body.state.root_position_mm[1] - 1_000).abs() <= 1);
        eprintln!(
            "B15C_TRACKING before_q15={before} after_q15={after} peak_energy_mj={peak_energy} root={:?}",
            body.state.root_position_mm
        );
    }

    #[test]
    fn identical_plan_and_impulses_produce_identical_hashes() {
        let plan = sample_plan();
        let mut first = ActiveRagdollV1::from_plan(&plan).unwrap();
        let mut second = ActiveRagdollV1::from_plan(&plan).unwrap();
        for step in 0..240 {
            if step == 60 {
                first.apply_root_impulse_milli_ns([35_000, 0, -17_500]);
                second.apply_root_impulse_milli_ns([35_000, 0, -17_500]);
                first
                    .apply_joint_angular_impulse_milli_nms(10, [0, 0, 150])
                    .unwrap();
                second
                    .apply_joint_angular_impulse_milli_nms(10, [0, 0, 150])
                    .unwrap();
            }
            let tick = first.expected_truth_tick(&plan);
            let motors = compile_motor_targets(&plan, tick).unwrap();
            first.step(&plan, &motors).unwrap();
            second.step(&plan, &motors).unwrap();
            assert_eq!(first.state.state_hash(), second.state.state_hash());
        }
        assert_eq!(first.state, second.state);
        eprintln!("B15C_REPLAY final_state_hash={}", first.state.state_hash());
    }

    #[test]
    fn impulse_perturbs_physics_without_mutating_plan() {
        let plan = sample_plan();
        let bytes_before = plan.canonical_bytes().unwrap();
        let hash_before = plan.plan_hash;
        let mut baseline = ActiveRagdollV1::from_plan(&plan).unwrap();
        let mut perturbed = baseline.clone();
        for step in 0..120 {
            if step == 20 {
                perturbed.apply_root_impulse_milli_ns([70_000, 0, 0]);
                perturbed
                    .apply_joint_angular_impulse_milli_nms(10, [0, 0, -200])
                    .unwrap();
            }
            let tick = baseline.expected_truth_tick(&plan);
            let motors = compile_motor_targets(&plan, tick).unwrap();
            baseline.step(&plan, &motors).unwrap();
            perturbed.step(&plan, &motors).unwrap();
        }
        assert_ne!(baseline.state.state_hash(), perturbed.state.state_hash());
        assert_ne!(
            baseline.state.root_position_mm,
            perturbed.state.root_position_mm
        );
        assert_eq!(plan.plan_hash, hash_before);
        assert_eq!(plan.canonical_bytes().unwrap(), bytes_before);
        let displacement = std::array::from_fn::<_, 3, _>(|axis| {
            perturbed.state.root_position_mm[axis] - baseline.state.root_position_mm[axis]
        });
        eprintln!(
            "B15C_IMPULSE displacement_mm={displacement:?} baseline_hash={} perturbed_hash={}",
            baseline.state.state_hash(),
            perturbed.state.state_hash()
        );
    }

    #[test]
    fn missing_initial_joint_is_rejected_without_anticipating_future_pose() {
        let mut plan = sample_plan();
        plan.pose_targets
            .retain(|target| !(target.joint_index == 10 && target.tick_offset == 0));
        plan.plan_hash = 0;
        let plan = plan.seal().unwrap();
        assert_eq!(
            ActiveRagdollV1::from_plan(&plan),
            Err(ActiveRagdollError::MissingInitialJointTarget(10))
        );
        let before = compile_motor_targets(&plan, plan.valid_from_truth_tick).unwrap();
        assert!(before.targets.iter().all(|target| target.joint_index != 10));
        let at_tick = compile_motor_targets(&plan, plan.valid_from_truth_tick + 1).unwrap();
        assert_eq!(
            at_tick
                .targets
                .iter()
                .find(|target| target.joint_index == 10)
                .unwrap()
                .desired_rotation_6d_q15,
            ROTATED_Z_30_Q15
        );
    }

    #[test]
    fn initialization_requires_a_tick_zero_root_target() {
        let mut plan = sample_plan();
        plan.root_targets[0].tick_offset = 1;
        plan.plan_hash = 0;
        assert_eq!(plan.seal(), Err(MotionPlanError::MissingInitialRootTarget));
    }

    #[test]
    fn kinetic_energy_units_match_hand_calculations() {
        let mut state = ActiveRagdollStateV1 {
            physics_tick: 0,
            plan_id: 1,
            plan_hash: 1,
            root_position_mm: [0; 3],
            root_velocity_mm_s: [1_000, 0, 0],
            joints: [JointStateV1::default(); JOINT_COUNT],
        };
        // 70 kg at 1 m/s: 0.5 * 70 * 1^2 = 35 J = 35,000 mJ.
        assert_eq!(state.kinetic_energy_millijoules(), 35_000);
        state.root_velocity_mm_s = [0; 3];
        state.joints[0].angular_velocity_millirad_s = [1_000, 0, 0];
        // 0.05 kg*m^2 at 1 rad/s: 0.025 J = 25 mJ.
        assert_eq!(state.kinetic_energy_millijoules(), 25);
    }

    #[test]
    fn timing_and_plan_identity_errors_fail_closed() {
        let plan = sample_plan();
        assert_eq!(
            compile_motor_targets(&plan, plan.valid_from_truth_tick - 1),
            Err(ActiveRagdollError::PlanBeforeValidity)
        );
        assert_eq!(
            compile_motor_targets(
                &plan,
                plan.valid_from_truth_tick + u64::from(plan.horizon_truth_ticks)
            ),
            Err(ActiveRagdollError::PlanExpired)
        );

        let mut body = ActiveRagdollV1::from_plan(&plan).unwrap();
        let mut wrong_tick = compile_motor_targets(&plan, plan.valid_from_truth_tick).unwrap();
        wrong_tick.truth_tick += 1;
        assert_eq!(
            body.step(&plan, &wrong_tick),
            Err(ActiveRagdollError::TickMismatch {
                expected: plan.valid_from_truth_tick,
                actual: plan.valid_from_truth_tick + 1,
            })
        );

        let motors = compile_motor_targets(&plan, plan.valid_from_truth_tick).unwrap();
        let mut other_plan = plan.clone();
        other_plan.plan_id += 1;
        other_plan.plan_hash = 0;
        let other_plan = other_plan.seal().unwrap();
        assert_eq!(
            body.step(&other_plan, &motors),
            Err(ActiveRagdollError::PlanMismatch)
        );
    }

    #[test]
    fn cross_product_saturates_instead_of_overflowing() {
        assert_eq!(
            difference_of_products(i64::MAX, i64::MAX, i64::MIN, i64::MAX),
            i64::MAX
        );
        assert_eq!(
            difference_of_products(i64::MIN, i64::MAX, i64::MAX, i64::MAX),
            i64::MIN
        );
    }
}
