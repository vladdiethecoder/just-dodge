//! Deterministic spherical-target to pinned G1 hinge-target adapter.
//!
//! This module performs representation conversion only. It does not advance
//! physics, resolve contacts, mutate accepted plans, or produce combat truth.

use crate::g1_articulation::{
    G1_NODE_COUNT, G1_NODES, G1ModelError, G1NodeKind, validate_g1_articulation,
};
use crate::hinge_projection::{HingeProjectionError, project_hinge_angle_microradians};
use crate::motion_plan::{MotionPlanError, MotorTargetBatchV1, SCHEMA_VERSION};

pub const G1_HINGE_TARGET_COUNT: usize = 29;

const Q30_ONE: i64 = 1_i64 << 30;
const FNV_OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct G1HingeTargetV1 {
    pub node_index: u8,
    pub desired_position_microradians: i32,
    pub desired_velocity_milliradians_s: i32,
    pub stiffness_q16: u16,
    pub damping_q16: u16,
    pub max_torque_millinewton_m: u32,
    pub was_position_clamped: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct G1HingeTargetBatchV1 {
    pub schema_version: u16,
    pub truth_tick: u64,
    pub plan_id: u64,
    pub targets: Vec<G1HingeTargetV1>,
}

impl G1HingeTargetBatchV1 {
    pub fn validate(&self) -> Result<(), G1HingeAdapterError> {
        if self.schema_version != SCHEMA_VERSION {
            return Err(G1HingeAdapterError::UnsupportedSchema(self.schema_version));
        }
        if self.plan_id == 0 {
            return Err(G1HingeAdapterError::ZeroPlanId);
        }
        if self.targets.is_empty() || self.targets.len() > G1_HINGE_TARGET_COUNT {
            return Err(G1HingeAdapterError::InvalidLength);
        }
        let mut previous = None;
        for target in &self.targets {
            let index = usize::from(target.node_index);
            if index >= G1_NODE_COUNT || G1_NODES[index].kind != G1NodeKind::ActuatedHinge {
                return Err(G1HingeAdapterError::NonHinge(target.node_index));
            }
            if previous.is_some_and(|prior| prior >= target.node_index) {
                return Err(G1HingeAdapterError::NonCanonicalOrder);
            }
            previous = Some(target.node_index);
            let model = G1_NODES[index];
            if !(model.limits_microradians[0]..=model.limits_microradians[1])
                .contains(&target.desired_position_microradians)
            {
                return Err(G1HingeAdapterError::PositionOutsideLimit(target.node_index));
            }
            if target.max_torque_millinewton_m > model.max_torque_millinewton_m {
                return Err(G1HingeAdapterError::TorqueOutsideLimit(target.node_index));
            }
        }
        Ok(())
    }

    pub fn receipt_hash(&self) -> u64 {
        let mut hash = FNV_OFFSET;
        hash_bytes(&mut hash, &self.schema_version.to_le_bytes());
        hash_bytes(&mut hash, &self.truth_tick.to_le_bytes());
        hash_bytes(&mut hash, &self.plan_id.to_le_bytes());
        hash_bytes(
            &mut hash,
            &u32::try_from(self.targets.len())
                .unwrap_or(u32::MAX)
                .to_le_bytes(),
        );
        for target in &self.targets {
            hash_bytes(&mut hash, &[target.node_index]);
            hash_bytes(
                &mut hash,
                &target.desired_position_microradians.to_le_bytes(),
            );
            hash_bytes(
                &mut hash,
                &target.desired_velocity_milliradians_s.to_le_bytes(),
            );
            hash_bytes(&mut hash, &target.stiffness_q16.to_le_bytes());
            hash_bytes(&mut hash, &target.damping_q16.to_le_bytes());
            hash_bytes(&mut hash, &target.max_torque_millinewton_m.to_le_bytes());
            hash_bytes(&mut hash, &[u8::from(target.was_position_clamped)]);
        }
        hash
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum G1HingeAdapterError {
    MotionPlan(MotionPlanError),
    Model(G1ModelError),
    Projection(HingeProjectionError),
    UnsupportedSchema(u16),
    ZeroPlanId,
    InvalidLength,
    NonHinge(u8),
    NonCanonicalOrder,
    PositionOutsideLimit(u8),
    TorqueOutsideLimit(u8),
    VelocityOverflow(u8),
}

impl From<MotionPlanError> for G1HingeAdapterError {
    fn from(value: MotionPlanError) -> Self {
        Self::MotionPlan(value)
    }
}

impl From<G1ModelError> for G1HingeAdapterError {
    fn from(value: G1ModelError) -> Self {
        Self::Model(value)
    }
}

impl From<HingeProjectionError> for G1HingeAdapterError {
    fn from(value: HingeProjectionError) -> Self {
        Self::Projection(value)
    }
}

pub fn adapt_g1_hinge_targets(
    source: &MotorTargetBatchV1,
) -> Result<G1HingeTargetBatchV1, G1HingeAdapterError> {
    source.validate()?;
    validate_g1_articulation()?;

    let mut targets = Vec::with_capacity(G1_HINGE_TARGET_COUNT);
    for source_target in &source.targets {
        let index = usize::from(source_target.joint_index);
        let model = G1_NODES[index];
        if model.kind != G1NodeKind::ActuatedHinge {
            continue;
        }
        let projected = project_hinge_angle_microradians(
            source_target.desired_rotation_6d_q15,
            model.hinge_axis_q30,
        )?;
        let desired_position =
            projected.clamp(model.limits_microradians[0], model.limits_microradians[1]);
        let desired_velocity = project_velocity_milliradians_s(
            source_target.desired_angular_velocity_millirad_s,
            model.hinge_axis_q30,
            source_target.joint_index,
        )?;
        targets.push(G1HingeTargetV1 {
            node_index: source_target.joint_index,
            desired_position_microradians: desired_position,
            desired_velocity_milliradians_s: desired_velocity,
            stiffness_q16: source_target.stiffness_q16,
            damping_q16: source_target.damping_q16,
            max_torque_millinewton_m: source_target
                .max_torque_millinewton_m
                .min(model.max_torque_millinewton_m),
            was_position_clamped: desired_position != projected,
        });
    }
    targets.sort_unstable_by_key(|target| target.node_index);

    let result = G1HingeTargetBatchV1 {
        schema_version: source.schema_version,
        truth_tick: source.truth_tick,
        plan_id: source.plan_id,
        targets,
    };
    result.validate()?;
    Ok(result)
}

fn project_velocity_milliradians_s(
    velocity_milliradians_s: [i32; 3],
    axis_q30: [i32; 3],
    joint_index: u8,
) -> Result<i32, G1HingeAdapterError> {
    let component = match axis_q30 {
        [x, 0, 0] if i64::from(x).abs() == Q30_ONE => {
            i64::from(velocity_milliradians_s[0]) * i64::from(x.signum())
        }
        [0, y, 0] if i64::from(y).abs() == Q30_ONE => {
            i64::from(velocity_milliradians_s[1]) * i64::from(y.signum())
        }
        [0, 0, z] if i64::from(z).abs() == Q30_ONE => {
            i64::from(velocity_milliradians_s[2]) * i64::from(z.signum())
        }
        _ => {
            return Err(G1HingeAdapterError::Projection(
                HingeProjectionError::InvalidHingeAxis,
            ));
        }
    };
    i32::try_from(component).map_err(|_| G1HingeAdapterError::VelocityOverflow(joint_index))
}

fn hash_bytes(hash: &mut u64, bytes: &[u8]) {
    for byte in bytes {
        *hash = (*hash ^ u64::from(*byte)).wrapping_mul(FNV_PRIME);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::active_ragdoll::IDENTITY_ROTATION_6D_Q15;
    use crate::motion_plan::JointMotorTargetV1;

    const COS_HALF_Q15: i16 = 28_756;
    const SIN_HALF_Q15: i16 = 15_709;

    fn rotation_x_half() -> [i16; 6] {
        [i16::MAX, 0, 0, 0, COS_HALF_Q15, SIN_HALF_Q15]
    }

    fn rotation_y_half() -> [i16; 6] {
        [COS_HALF_Q15, 0, -SIN_HALF_Q15, 0, i16::MAX, 0]
    }

    fn rotation_z_half() -> [i16; 6] {
        [
            COS_HALF_Q15,
            SIN_HALF_Q15,
            0,
            -SIN_HALF_Q15,
            COS_HALF_Q15,
            0,
        ]
    }

    fn source_batch(overrides: &[(usize, [i16; 6])]) -> MotorTargetBatchV1 {
        let targets = (0..G1_NODE_COUNT)
            .map(|index| {
                let rotation = overrides
                    .iter()
                    .find_map(|(target_index, rotation)| {
                        (*target_index == index).then_some(*rotation)
                    })
                    .unwrap_or(IDENTITY_ROTATION_6D_Q15);
                JointMotorTargetV1 {
                    joint_index: index as u8,
                    desired_rotation_6d_q15: rotation,
                    desired_angular_velocity_millirad_s: [100, -200, 300],
                    stiffness_q16: u16::MAX,
                    damping_q16: u16::MAX,
                    max_torque_millinewton_m: 200_000,
                }
            })
            .collect();
        MotorTargetBatchV1 {
            schema_version: SCHEMA_VERSION,
            truth_tick: 77,
            plan_id: 42,
            targets,
        }
    }

    #[test]
    fn canonical_axes_recover_position_and_velocity() {
        let source = source_batch(&[
            (2, rotation_x_half()),
            (1, rotation_y_half()),
            (3, rotation_z_half()),
        ]);
        let adapted = adapt_g1_hinge_targets(&source).unwrap();
        for (index, velocity) in [(1_u8, -200), (2, 100), (3, 300)] {
            let target = adapted
                .targets
                .iter()
                .find(|target| target.node_index == index)
                .unwrap();
            assert!(
                (target.desired_position_microradians - 500_000).abs() <= 100,
                "node {index}: {}",
                target.desired_position_microradians
            );
            assert_eq!(target.desired_velocity_milliradians_s, velocity);
        }
    }

    #[test]
    fn zero_torque_is_preserved_as_an_explicit_no_drive_target() {
        let mut source = source_batch(&[]);
        let target = source
            .targets
            .iter_mut()
            .find(|target| target.joint_index == 1)
            .unwrap();
        target.max_torque_millinewton_m = 0;

        let adapted = adapt_g1_hinge_targets(&source).unwrap();
        let target = adapted
            .targets
            .iter()
            .find(|target| target.node_index == 1)
            .unwrap();
        assert_eq!(target.max_torque_millinewton_m, 0);
        assert_eq!(adapted.validate(), Ok(()));
    }

    #[test]
    fn adapter_excludes_nonhinges_and_clamps_official_limits() {
        let x_pi = [i16::MAX, 0, 0, 0, -i16::MAX, 0];
        let source = source_batch(&[(19, x_pi)]);
        let adapted = adapt_g1_hinge_targets(&source).unwrap();
        assert_eq!(adapted.targets.len(), G1_HINGE_TARGET_COUNT);
        assert!(
            adapted
                .targets
                .iter()
                .all(|target| ![0, 7, 14, 25, 33].contains(&target.node_index))
        );
        let shoulder_roll = adapted
            .targets
            .iter()
            .find(|target| target.node_index == 19)
            .unwrap();
        assert_eq!(shoulder_roll.desired_position_microradians, 2_251_500);
        assert!(shoulder_roll.was_position_clamped);
        assert!(adapted.targets.iter().all(|target| {
            target.max_torque_millinewton_m
                == G1_NODES[usize::from(target.node_index)].max_torque_millinewton_m
        }));
    }

    #[test]
    fn off_axis_rotation_does_not_leak_into_hinge_target() {
        let source = source_batch(&[(2, rotation_z_half())]);
        let adapted = adapt_g1_hinge_targets(&source).unwrap();
        let hip_roll = adapted
            .targets
            .iter()
            .find(|target| target.node_index == 2)
            .unwrap();
        assert_eq!(hip_roll.desired_position_microradians, 0);
        assert!(!hip_roll.was_position_clamped);
    }

    #[test]
    fn identical_inputs_produce_identical_canonical_receipts() {
        let source = source_batch(&[(21, rotation_y_half())]);
        let first = adapt_g1_hinge_targets(&source).unwrap();
        let mut reordered_source = source.clone();
        reordered_source.targets.reverse();
        let second = adapt_g1_hinge_targets(&reordered_source).unwrap();
        assert_eq!(first, second);
        assert_eq!(first.receipt_hash(), second.receipt_hash());
        assert_eq!(first.validate(), Ok(()));
        assert_ne!(first.receipt_hash(), 0);
    }

    #[test]
    fn source_validation_and_empty_hinge_output_fail_closed() {
        let malformed = MotorTargetBatchV1 {
            schema_version: SCHEMA_VERSION,
            truth_tick: 1,
            plan_id: 9,
            targets: vec![JointMotorTargetV1 {
                joint_index: 1,
                desired_rotation_6d_q15: [0; 6],
                desired_angular_velocity_millirad_s: [0; 3],
                stiffness_q16: 1,
                damping_q16: 1,
                max_torque_millinewton_m: 1,
            }],
        };
        assert!(matches!(
            adapt_g1_hinge_targets(&malformed),
            Err(G1HingeAdapterError::MotionPlan(
                MotionPlanError::InvalidRotationBasis(1)
            ))
        ));

        let root_only = MotorTargetBatchV1 {
            targets: vec![JointMotorTargetV1 {
                joint_index: 0,
                desired_rotation_6d_q15: IDENTITY_ROTATION_6D_Q15,
                desired_angular_velocity_millirad_s: [0; 3],
                stiffness_q16: 1,
                damping_q16: 1,
                max_torque_millinewton_m: 1,
            }],
            ..malformed
        };
        assert_eq!(
            adapt_g1_hinge_targets(&root_only),
            Err(G1HingeAdapterError::InvalidLength)
        );
    }
}
