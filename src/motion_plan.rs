//! Quantized neural motion-plan and active-ragdoll controller boundary.
//!
//! ARDy and MotionBricks may propose movement after Reveal. A proposal becomes
//! controller input only after validation, quantization, hashing, and replay
//! admission. Deterministic articulated physics remains outcome authority.

use serde::{Deserialize, Serialize};

use crate::truth::Side;

pub const SCHEMA_VERSION: u16 = 1;
pub const INTENT_VERB_COUNT: u8 = 13;
pub const MAX_PLAN_SAMPLES: usize = 64;
pub const MAX_POSE_TARGETS: usize = MAX_PLAN_SAMPLES * 34;
pub const MAX_MOTOR_TARGETS: usize = 34;

const FNV_OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct IntentVerb(u8);

impl IntentVerb {
    pub fn new(value: u8) -> Result<Self, MotionPlanError> {
        (value < INTENT_VERB_COUNT)
            .then_some(Self(value))
            .ok_or(MotionPlanError::InvalidIntentVerb(value))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum IntentTarget {
    SelfRoot,
    HeadLine,
    TorsoLine,
    LegLine,
    WeaponArm,
    WeaponWrist,
    Weapon,
    Ground,
    Projectile,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum IntentDirection {
    Center,
    Left,
    Right,
    Up,
    Down,
    DiagonalUpLeft,
    DiagonalUpRight,
    DiagonalDownLeft,
    DiagonalDownRight,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum IntentStance {
    Top,
    Left,
    Right,
    Low,
    Transitional,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum IntentFootwork {
    Planted,
    Advance,
    Retreat,
    StepLeft,
    StepRight,
    PivotLeft,
    PivotRight,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum IntentTempo {
    Delayed,
    Measured,
    Explosive,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum IntentCommitment {
    Soft,
    Committed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct IntentGrammarV1 {
    pub verb: IntentVerb,
    pub target: IntentTarget,
    pub direction: IntentDirection,
    pub stance: IntentStance,
    pub footwork: IntentFootwork,
    pub tempo: IntentTempo,
    pub commitment: IntentCommitment,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PublicMotionPhase {
    Reveal,
    Resolve,
    Consequence,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MotionAnchor {
    Root,
    Pelvis,
    Chest,
    Head,
    LeadHand,
    TrailHand,
    LeadFoot,
    TrailFoot,
    WeaponGrip,
    WeaponGuard,
    WeaponEdge,
    WeaponTip,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PhysicalRole {
    Body,
    WeaponEdge,
    WeaponGuard,
    WeaponTip,
    ShieldFace,
    Projectile,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModelReceiptV1 {
    pub ardy_sha256: [u8; 32],
    pub motionbricks_sha256: [u8; 32],
    pub normalization_sha256: [u8; 32],
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct RootTargetV1 {
    pub tick_offset: u16,
    pub position_mm: [i32; 3],
    pub velocity_mm_s: [i32; 3],
    pub heading_q15: [i16; 2],
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct EffectorTargetV1 {
    pub tick_offset: u16,
    pub anchor: MotionAnchor,
    pub position_mm: [i32; 3],
    pub rotation_6d_q15: [i16; 6],
}

/// A desired contact is a plan constraint, never evidence that contact occurred.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct DesiredContactV1 {
    pub tick_offset: u16,
    pub emitter: MotionAnchor,
    pub target_role: PhysicalRole,
    pub position_mm: [i32; 3],
    pub normal_q15: [i16; 3],
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct PoseTargetV1 {
    pub tick_offset: u16,
    pub joint_index: u8,
    pub rotation_6d_q15: [i16; 6],
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct BalanceHintV1 {
    pub tick_offset: u16,
    pub center_of_mass_mm: [i32; 3],
    pub support_center_mm: [i32; 3],
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MotionPlanPacketV1 {
    pub schema_version: u16,
    pub plan_id: u64,
    pub parent_plan_id: Option<u64>,
    pub actor: Side,
    pub source_phase: PublicMotionPhase,
    pub source_truth_tick: u64,
    pub valid_from_truth_tick: u64,
    pub horizon_truth_ticks: u16,
    pub intent: IntentGrammarV1,
    pub legal_response_bits: u16,
    pub selected_response_bit: u16,
    pub models: ModelReceiptV1,
    pub root_targets: Vec<RootTargetV1>,
    pub effector_targets: Vec<EffectorTargetV1>,
    pub desired_contacts: Vec<DesiredContactV1>,
    pub pose_targets: Vec<PoseTargetV1>,
    pub balance_hints: Vec<BalanceHintV1>,
    pub plan_hash: u64,
}

impl MotionPlanPacketV1 {
    pub fn seal(mut self) -> Result<Self, MotionPlanError> {
        self.plan_hash = 0;
        self.validate_structure()?;
        self.plan_hash = fnv1a64(&self.payload()?);
        Ok(self)
    }

    pub fn validate(&self) -> Result<(), MotionPlanError> {
        self.validate_structure()?;
        if self.plan_hash == 0 {
            return Err(MotionPlanError::MissingPlanHash);
        }
        let expected = fnv1a64(&self.payload()?);
        (self.plan_hash == expected)
            .then_some(())
            .ok_or(MotionPlanError::PlanHashMismatch)
    }

    pub fn canonical_bytes(&self) -> Result<Vec<u8>, MotionPlanError> {
        self.validate()?;
        postcard::to_stdvec(self).map_err(|_| MotionPlanError::Serialization)
    }

    fn payload(&self) -> Result<Vec<u8>, MotionPlanError> {
        let mut value = self.clone();
        value.plan_hash = 0;
        postcard::to_stdvec(&value).map_err(|_| MotionPlanError::Serialization)
    }

    fn validate_structure(&self) -> Result<(), MotionPlanError> {
        if self.schema_version != SCHEMA_VERSION {
            return Err(MotionPlanError::UnsupportedSchema(self.schema_version));
        }
        if self.plan_id == 0 {
            return Err(MotionPlanError::ZeroPlanId);
        }
        if self.parent_plan_id == Some(self.plan_id) {
            return Err(MotionPlanError::SelfParentPlan);
        }
        if self.valid_from_truth_tick < self.source_truth_tick {
            return Err(MotionPlanError::PlanPredatesSource);
        }
        if self.horizon_truth_ticks == 0 {
            return Err(MotionPlanError::ZeroHorizon);
        }
        if !self.selected_response_bit.is_power_of_two()
            || self.selected_response_bit & self.legal_response_bits == 0
        {
            return Err(MotionPlanError::IllegalResponse);
        }
        if self.models.ardy_sha256 == [0; 32]
            || self.models.motionbricks_sha256 == [0; 32]
            || self.models.normalization_sha256 == [0; 32]
        {
            return Err(MotionPlanError::MissingModelReceipt);
        }
        bounded("root_targets", self.root_targets.len(), 1, MAX_PLAN_SAMPLES)?;
        bounded(
            "effector_targets",
            self.effector_targets.len(),
            0,
            MAX_PLAN_SAMPLES,
        )?;
        bounded(
            "desired_contacts",
            self.desired_contacts.len(),
            0,
            MAX_PLAN_SAMPLES,
        )?;
        bounded("pose_targets", self.pose_targets.len(), 1, MAX_POSE_TARGETS)?;
        bounded(
            "balance_hints",
            self.balance_hints.len(),
            0,
            MAX_PLAN_SAMPLES,
        )?;
        strict_ticks(
            "root_targets",
            self.root_targets.iter().map(|v| v.tick_offset),
            self.horizon_truth_ticks,
        )?;
        ordered_ticks(
            "effector_targets",
            self.effector_targets.iter().map(|v| v.tick_offset),
            self.horizon_truth_ticks,
        )?;
        ordered_ticks(
            "desired_contacts",
            self.desired_contacts.iter().map(|v| v.tick_offset),
            self.horizon_truth_ticks,
        )?;
        ordered_ticks(
            "balance_hints",
            self.balance_hints.iter().map(|v| v.tick_offset),
            self.horizon_truth_ticks,
        )?;
        pose_targets(&self.pose_targets, self.horizon_truth_ticks)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct JointMotorTargetV1 {
    pub joint_index: u8,
    pub desired_position_millirad: i32,
    pub desired_velocity_millirad_s: i32,
    pub stiffness_q16: u16,
    pub damping_q16: u16,
    pub max_torque_millinewton_m: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MotorTargetBatchV1 {
    pub schema_version: u16,
    pub truth_tick: u64,
    pub plan_id: u64,
    pub targets: Vec<JointMotorTargetV1>,
}

impl MotorTargetBatchV1 {
    pub fn validate(&self) -> Result<(), MotionPlanError> {
        if self.schema_version != SCHEMA_VERSION {
            return Err(MotionPlanError::UnsupportedSchema(self.schema_version));
        }
        if self.plan_id == 0 {
            return Err(MotionPlanError::ZeroPlanId);
        }
        bounded("motor_targets", self.targets.len(), 1, MAX_MOTOR_TARGETS)?;
        let mut seen = [false; MAX_MOTOR_TARGETS];
        for target in &self.targets {
            let joint = usize::from(target.joint_index);
            if joint >= MAX_MOTOR_TARGETS {
                return Err(MotionPlanError::InvalidJoint(target.joint_index));
            }
            if seen[joint] {
                return Err(MotionPlanError::DuplicateJoint(target.joint_index));
            }
            seen[joint] = true;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ImpactEventV1 {
    pub schema_version: u16,
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

impl ImpactEventV1 {
    pub fn validate(&self) -> Result<(), MotionPlanError> {
        if self.schema_version != SCHEMA_VERSION {
            return Err(MotionPlanError::UnsupportedSchema(self.schema_version));
        }
        if self.contact_id == 0 {
            return Err(MotionPlanError::ZeroContactId);
        }
        if self.attacker == self.defender {
            return Err(MotionPlanError::SameImpactSides);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MotionPlanError {
    UnsupportedSchema(u16),
    InvalidIntentVerb(u8),
    ZeroPlanId,
    SelfParentPlan,
    PlanPredatesSource,
    ZeroHorizon,
    IllegalResponse,
    MissingModelReceipt,
    InvalidLength(&'static str),
    TickOutOfHorizon(&'static str),
    NonCanonicalOrder(&'static str),
    InvalidJoint(u8),
    DuplicateJoint(u8),
    MissingPlanHash,
    PlanHashMismatch,
    Serialization,
    ZeroContactId,
    SameImpactSides,
}

fn bounded(
    field: &'static str,
    actual: usize,
    minimum: usize,
    maximum: usize,
) -> Result<(), MotionPlanError> {
    (minimum..=maximum)
        .contains(&actual)
        .then_some(())
        .ok_or(MotionPlanError::InvalidLength(field))
}

fn strict_ticks(
    field: &'static str,
    ticks: impl Iterator<Item = u16>,
    horizon: u16,
) -> Result<(), MotionPlanError> {
    let mut previous = None;
    for tick in ticks {
        if tick >= horizon {
            return Err(MotionPlanError::TickOutOfHorizon(field));
        }
        if previous.is_some_and(|value| tick <= value) {
            return Err(MotionPlanError::NonCanonicalOrder(field));
        }
        previous = Some(tick);
    }
    Ok(())
}

fn ordered_ticks(
    field: &'static str,
    ticks: impl Iterator<Item = u16>,
    horizon: u16,
) -> Result<(), MotionPlanError> {
    let mut previous = None;
    for tick in ticks {
        if tick >= horizon {
            return Err(MotionPlanError::TickOutOfHorizon(field));
        }
        if previous.is_some_and(|value| tick < value) {
            return Err(MotionPlanError::NonCanonicalOrder(field));
        }
        previous = Some(tick);
    }
    Ok(())
}

fn pose_targets(targets: &[PoseTargetV1], horizon: u16) -> Result<(), MotionPlanError> {
    let mut previous = None;
    for target in targets {
        if target.tick_offset >= horizon {
            return Err(MotionPlanError::TickOutOfHorizon("pose_targets"));
        }
        if usize::from(target.joint_index) >= MAX_MOTOR_TARGETS {
            return Err(MotionPlanError::InvalidJoint(target.joint_index));
        }
        let key = (target.tick_offset, target.joint_index);
        if previous.is_some_and(|value| key <= value) {
            return Err(MotionPlanError::NonCanonicalOrder("pose_targets"));
        }
        previous = Some(key);
    }
    Ok(())
}

fn fnv1a64(bytes: &[u8]) -> u64 {
    bytes.iter().fold(FNV_OFFSET, |hash, byte| {
        (hash ^ u64::from(*byte)).wrapping_mul(FNV_PRIME)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::replay::{EventKind, ReplayRecorder};

    fn sample_plan() -> MotionPlanPacketV1 {
        MotionPlanPacketV1 {
            schema_version: SCHEMA_VERSION,
            plan_id: 7,
            parent_plan_id: None,
            actor: Side::Player,
            source_phase: PublicMotionPhase::Reveal,
            source_truth_tick: 100,
            valid_from_truth_tick: 104,
            horizon_truth_ticks: 48,
            intent: IntentGrammarV1 {
                verb: IntentVerb::new(1).unwrap(),
                target: IntentTarget::HeadLine,
                direction: IntentDirection::DiagonalDownRight,
                stance: IntentStance::Top,
                footwork: IntentFootwork::Advance,
                tempo: IntentTempo::Explosive,
                commitment: IntentCommitment::Committed,
            },
            legal_response_bits: 0b0111,
            selected_response_bit: 0b0010,
            models: ModelReceiptV1 {
                ardy_sha256: [1; 32],
                motionbricks_sha256: [2; 32],
                normalization_sha256: [3; 32],
            },
            root_targets: vec![
                RootTargetV1 {
                    tick_offset: 0,
                    position_mm: [0, 1_000, 0],
                    velocity_mm_s: [0, 0, 0],
                    heading_q15: [0, i16::MAX],
                },
                RootTargetV1 {
                    tick_offset: 24,
                    position_mm: [120, 1_000, -80],
                    velocity_mm_s: [300, 0, -100],
                    heading_q15: [0, i16::MAX],
                },
            ],
            effector_targets: vec![EffectorTargetV1 {
                tick_offset: 20,
                anchor: MotionAnchor::WeaponGuard,
                position_mm: [180, 1_520, -250],
                rotation_6d_q15: [i16::MAX, 0, 0, 0, i16::MAX, 0],
            }],
            desired_contacts: vec![DesiredContactV1 {
                tick_offset: 20,
                emitter: MotionAnchor::WeaponGuard,
                target_role: PhysicalRole::WeaponEdge,
                position_mm: [180, 1_520, -250],
                normal_q15: [i16::MAX, 0, 0],
            }],
            pose_targets: vec![PoseTargetV1 {
                tick_offset: 20,
                joint_index: 21,
                rotation_6d_q15: [i16::MAX, 0, 0, 0, i16::MAX, 0],
            }],
            balance_hints: vec![BalanceHintV1 {
                tick_offset: 20,
                center_of_mass_mm: [0, 900, 0],
                support_center_mm: [0, 0, 0],
            }],
            plan_hash: 0,
        }
    }

    fn sample_impact() -> ImpactEventV1 {
        ImpactEventV1 {
            schema_version: SCHEMA_VERSION,
            truth_tick: 120,
            contact_id: 9,
            contact_point_mm: [0, 1_200, 0],
            impulse_milli_ns: [400, 0, -200],
            dissipated_energy_millijoules: 800,
            relative_velocity_mm_s: [2_000, 0, -500],
            material_failure_bits: 1,
            anatomical_severity_q16: 12_000,
            attacker: Side::Player,
            defender: Side::Opponent,
        }
    }

    #[test]
    fn plan_hash_and_bytes_are_stable_and_tamper_evident() {
        let first = sample_plan().seal().unwrap();
        let second = sample_plan().seal().unwrap();
        assert_eq!(first.plan_hash, second.plan_hash);
        assert_eq!(
            first.canonical_bytes().unwrap(),
            second.canonical_bytes().unwrap()
        );

        let mut tampered = first;
        tampered.root_targets[1].position_mm[0] += 1;
        assert_eq!(tampered.validate(), Err(MotionPlanError::PlanHashMismatch));
    }

    #[test]
    fn invalid_parent_legality_order_and_horizon_fail_closed() {
        let mut parent = sample_plan();
        parent.parent_plan_id = Some(parent.plan_id);
        assert_eq!(parent.seal(), Err(MotionPlanError::SelfParentPlan));

        let mut illegal = sample_plan();
        illegal.selected_response_bit = 0b1000;
        assert_eq!(illegal.seal(), Err(MotionPlanError::IllegalResponse));

        let mut unordered = sample_plan();
        unordered.pose_targets = vec![
            PoseTargetV1 {
                tick_offset: 20,
                joint_index: 22,
                rotation_6d_q15: [0; 6],
            },
            PoseTargetV1 {
                tick_offset: 20,
                joint_index: 21,
                rotation_6d_q15: [0; 6],
            },
        ];
        assert_eq!(
            unordered.seal(),
            Err(MotionPlanError::NonCanonicalOrder("pose_targets"))
        );

        let mut overflow = sample_plan();
        overflow.root_targets[1].tick_offset = overflow.horizon_truth_ticks;
        assert_eq!(
            overflow.seal(),
            Err(MotionPlanError::TickOutOfHorizon("root_targets"))
        );
    }

    #[test]
    fn motor_targets_reject_duplicate_and_unknown_joints() {
        let target = JointMotorTargetV1 {
            joint_index: 3,
            desired_position_millirad: 100,
            desired_velocity_millirad_s: 0,
            stiffness_q16: 32_768,
            damping_q16: 16_384,
            max_torque_millinewton_m: 80_000,
        };
        let duplicate = MotorTargetBatchV1 {
            schema_version: SCHEMA_VERSION,
            truth_tick: 120,
            plan_id: 7,
            targets: vec![target, target],
        };
        assert_eq!(
            duplicate.validate(),
            Err(MotionPlanError::DuplicateJoint(3))
        );
        let invalid = MotorTargetBatchV1 {
            targets: vec![JointMotorTargetV1 {
                joint_index: 34,
                ..target
            }],
            ..duplicate
        };
        assert_eq!(invalid.validate(), Err(MotionPlanError::InvalidJoint(34)));
    }

    #[test]
    fn impacts_reject_nonphysical_identity() {
        assert_eq!(sample_impact().validate(), Ok(()));
        let invalid = ImpactEventV1 {
            defender: Side::Player,
            ..sample_impact()
        };
        assert_eq!(invalid.validate(), Err(MotionPlanError::SameImpactSides));
    }

    #[test]
    fn replay_accepts_only_sealed_plans_and_validated_impacts() {
        let mut replay = ReplayRecorder::new(99);
        assert_eq!(
            replay.record_motion_plan(10, sample_plan()),
            Err(MotionPlanError::MissingPlanHash)
        );
        let plan = sample_plan().seal().unwrap();
        replay.record_motion_plan(10, plan.clone()).unwrap();
        assert!(matches!(
            &replay.events[0].kind,
            EventKind::MotionPlan { packet } if packet == &plan
        ));
        let impact = sample_impact();
        replay.record_impact(11, impact).unwrap();
        assert!(matches!(
            replay.events[1].kind,
            EventKind::Impact { event } if event == impact
        ));
    }
}
