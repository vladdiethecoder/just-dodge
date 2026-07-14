//! Deterministic Stage-0 combat primitives for MotionBricks.
//!
//! A primitive is an intent contract, not a combat result or an animation clip.
//! It feeds sparse T1/T2/T3 constraints to MotionBricks while preserving the
//! truth-owned contact and deep-anatomy boundary.

use crate::truth::{Action, HitLocation, Stance};

/// MotionBricks emits one motion frame every 1/30 second.
pub const MOTIONBRICKS_FPS: u16 = 30;
/// Combat truth advances at exactly 60 Hz.
pub const TRUTH_FPS: u16 = 60;
pub const TRUTH_TICKS_PER_MOTION_FRAME: u16 = TRUTH_FPS / MOTIONBRICKS_FPS;
const MIN_MOTION_FRAMES: u16 = 12;
const MAX_MOTION_FRAMES: u16 = 64;
const TOKEN_FRAMES: u16 = 4;

/// The only selectable contract for the first playable cleanbox.
///
/// Broader action data remains admissible as source/training evidence, but it
/// must not leak into player input, AI decisions, or truth commits until it
/// has a matching physical-world and motion contract.
pub const FIRST_PLAYABLE_WEAPON: &str = "Longsword";
pub const FIRST_PLAYABLE_STANCE: Stance = Stance::Top;
pub const FIRST_PLAYABLE_ACTIONS: [Action; 3] = [Action::Thrust, Action::Block, Action::Dodge];

pub const fn is_first_playable_action(action: Action) -> bool {
    matches!(action, Action::Thrust | Action::Block | Action::Dodge)
}

pub const fn is_first_playable_choice(action: Action, stance: Stance) -> bool {
    is_first_playable_action(action) && matches!(stance, FIRST_PLAYABLE_STANCE)
}

/// Millimetre coordinates avoid introducing presentation floats into a truth
/// request. Conversion to normalized MotionBricks feature space is a one-way
/// presentation bridge and is deliberately outside this module.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Millimetres {
    pub x: i32,
    pub y: i32,
    pub z: i32,
}

/// Semantic anchors are mapped to G1 joints/sockets by the retarget contract.
/// They are intentionally not raw renderer bone indices.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
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

/// The role of a pose target inside an authored martial primitive.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PrimitivePhase {
    Guard,
    Windup,
    Contact,
    Recovery,
}

/// A hard constraint must be reached; a soft constraint may be left early.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ConstraintStrength {
    Hard,
    Soft { allow_early_motion_frames: u8 },
}

/// A root target supplies the MotionBricks T1/T2 portions of a keyframe.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct RootConstraint {
    pub motion_frame: u16,
    pub local_linear_velocity_mm_per_s: [i16; 2],
    pub local_yaw_millirad_per_s: i16,
    pub root_height_mm: i16,
    pub world_offset_mm: Millimetres,
    pub heading_millirad: i16,
}

/// A T3 pose keyframe expressed relative to a truth-owned anchor.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct PoseConstraint {
    pub motion_frame: u16,
    pub phase: PrimitivePhase,
    pub anchor: MotionAnchor,
    pub target_anchor: MotionAnchor,
    pub target_offset_mm: Millimetres,
    pub strength: ConstraintStrength,
}

/// The physical feature whose swept geometry may create a contact. This is a
/// geometric request only; it cannot prescribe a hit, injury, or damage value.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ContactEmitter {
    WeaponEdge,
    WeaponTip,
    WeaponGuard,
    ShieldFace,
    Hand,
    Foot,
    Grapple,
}

/// Layers queried by the future 500–1,000-structure anatomy atlas. A broad
/// hit location is an acceleration hint only; no layer/result is authoritative
/// until deterministic geometry resolves concrete structure IDs.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct AnatomyLayers(u16);

impl AnatomyLayers {
    pub const ARMOR: Self = Self(1 << 0);
    pub const SKIN: Self = Self(1 << 1);
    pub const FASCIA: Self = Self(1 << 2);
    pub const MUSCLE: Self = Self(1 << 3);
    pub const TENDON: Self = Self(1 << 4);
    pub const LIGAMENT: Self = Self(1 << 5);
    pub const BONE: Self = Self(1 << 6);
    pub const VESSEL: Self = Self(1 << 7);
    pub const NERVE: Self = Self(1 << 8);
    pub const ORGAN: Self = Self(1 << 9);

    pub const fn from_bits(bits: u16) -> Self {
        Self(bits)
    }

    pub const fn bits(self) -> u16 {
        self.0
    }

    pub const fn contains(self, layers: Self) -> bool {
        self.0 & layers.0 == layers.0
    }

    pub const fn is_empty(self) -> bool {
        self.0 == 0
    }
}

/// Candidate anatomy selected before exact continuous collision determines
/// concrete stable structure IDs and causal propagation edges.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct AnatomyTarget {
    pub acceleration_region: HitLocation,
    pub candidate_layers: AnatomyLayers,
}

/// Inclusive/exclusive 60 Hz truth window for continuous contact testing.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ContactWindow {
    pub start_tick: u16,
    pub end_tick_exclusive: u16,
    pub emitter: ContactEmitter,
    pub target: AnatomyTarget,
}

/// State label for future combat-conditioned training data. It describes a
/// requested interaction, never the truth result of that interaction.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum InterAgentContactState {
    Guard,
    Strike,
    Parry,
    Grab,
    Impact,
    Knockdown,
}

/// Opponent root expressed in this fighter's local frame. This is the
/// opponent-relative conditioning channel required for paired combat data.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct OpponentRelativeRoot {
    pub offset_mm: Millimetres,
    pub heading_millirad: i16,
}

/// Training/reaction label only. Truth calculates actual force from swept
/// geometry and may reject this intent entirely.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ImpactIntent {
    pub force_millinewtons: u32,
    pub direction_milli: [i16; 3],
}

/// Paired keyframe metadata for independently inferred fighters. A hard frame
/// may couple sockets visually but cannot resolve hit/parry/grab truth.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct InterAgentConstraint {
    pub motion_frame: u16,
    pub phase: PrimitivePhase,
    pub state: InterAgentContactState,
    pub self_anchor: MotionAnchor,
    pub opponent_anchor: MotionAnchor,
    pub opponent_relative_root: OpponentRelativeRoot,
    pub target: AnatomyTarget,
    pub strength: ConstraintStrength,
    pub impact: Option<ImpactIntent>,
}

/// A complete intent contract. Its data can be serialized into a replay or an
/// authored primitive asset. MotionBricks may vary kinematics inside the
/// constraints, but cannot alter this contact schedule or anatomy query.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CombatPrimitive {
    pub action: Action,
    pub stance: Stance,
    pub motion_frames: u16,
    pub root_constraints: Vec<RootConstraint>,
    pub pose_constraints: Vec<PoseConstraint>,
    pub contact_windows: Vec<ContactWindow>,
    pub inter_agent_constraints: Vec<InterAgentConstraint>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PrimitiveValidationError {
    InvalidMotionFrameCount,
    ConstraintFrameOutOfRange,
    InvalidContactWindow,
    EmptyAnatomyQuery,
    MissingGuard,
    MissingWindup,
    MissingRecovery,
    MissingHardContactConstraint,
    InteractionFrameOutOfRange,
    HardInteractionOutsideActiveWindow,
    EmptyInteractionAnatomyQuery,
    InvalidImpactIntent,
}

impl CombatPrimitive {
    pub const fn truth_duration_ticks(&self) -> u16 {
        self.motion_frames * TRUTH_TICKS_PER_MOTION_FRAME
    }

    /// Contact authority is evaluated against this window at 60 Hz; generated
    /// animation samples never open or close it.
    pub fn is_active_at(&self, truth_tick: u16) -> bool {
        let mut index = 0;
        while index < self.contact_windows.len() {
            let window = self.contact_windows[index];
            if truth_tick >= window.start_tick && truth_tick < window.end_tick_exclusive {
                return true;
            }
            index += 1;
        }
        false
    }

    /// Reject incomplete primitives before they can reach MotionBricks or the
    /// truth bridge. This is deliberately structural, not a martial-quality
    /// assessment; source-motion visual QA remains a separate gate.
    pub fn validate(&self) -> Result<(), PrimitiveValidationError> {
        if !(MIN_MOTION_FRAMES..=MAX_MOTION_FRAMES).contains(&self.motion_frames)
            || !self.motion_frames.is_multiple_of(TOKEN_FRAMES)
        {
            return Err(PrimitiveValidationError::InvalidMotionFrameCount);
        }

        if self
            .root_constraints
            .iter()
            .any(|constraint| constraint.motion_frame >= self.motion_frames)
            || self
                .pose_constraints
                .iter()
                .any(|constraint| constraint.motion_frame >= self.motion_frames)
        {
            return Err(PrimitiveValidationError::ConstraintFrameOutOfRange);
        }
        if self
            .inter_agent_constraints
            .iter()
            .any(|constraint| constraint.motion_frame >= self.motion_frames)
        {
            return Err(PrimitiveValidationError::InteractionFrameOutOfRange);
        }

        let has_guard = self
            .pose_constraints
            .iter()
            .any(|constraint| constraint.phase == PrimitivePhase::Guard);
        if !has_guard {
            return Err(PrimitiveValidationError::MissingGuard);
        }
        let has_windup = self
            .pose_constraints
            .iter()
            .any(|constraint| constraint.phase == PrimitivePhase::Windup);
        if !has_windup {
            return Err(PrimitiveValidationError::MissingWindup);
        }
        let has_recovery = self
            .pose_constraints
            .iter()
            .any(|constraint| constraint.phase == PrimitivePhase::Recovery);
        if !has_recovery {
            return Err(PrimitiveValidationError::MissingRecovery);
        }

        let duration = self.truth_duration_ticks();
        for window in &self.contact_windows {
            if window.start_tick >= window.end_tick_exclusive
                || window.end_tick_exclusive > duration
            {
                return Err(PrimitiveValidationError::InvalidContactWindow);
            }
            if window.target.candidate_layers.is_empty() {
                return Err(PrimitiveValidationError::EmptyAnatomyQuery);
            }

            let has_hard_contact = self.pose_constraints.iter().any(|constraint| {
                constraint.phase == PrimitivePhase::Contact
                    && constraint.strength == ConstraintStrength::Hard
                    && constraint.motion_frame * TRUTH_TICKS_PER_MOTION_FRAME >= window.start_tick
                    && constraint.motion_frame * TRUTH_TICKS_PER_MOTION_FRAME
                        < window.end_tick_exclusive
            });
            if !has_hard_contact {
                return Err(PrimitiveValidationError::MissingHardContactConstraint);
            }
        }

        for constraint in &self.inter_agent_constraints {
            if constraint.target.candidate_layers.is_empty() {
                return Err(PrimitiveValidationError::EmptyInteractionAnatomyQuery);
            }
            if let Some(impact) = constraint.impact
                && (impact.force_millinewtons == 0 || impact.direction_milli == [0, 0, 0])
            {
                return Err(PrimitiveValidationError::InvalidImpactIntent);
            }
            if constraint.strength == ConstraintStrength::Hard
                && matches!(
                    constraint.state,
                    InterAgentContactState::Strike
                        | InterAgentContactState::Parry
                        | InterAgentContactState::Grab
                        | InterAgentContactState::Impact
                )
                && !self.is_active_at(constraint.motion_frame * TRUTH_TICKS_PER_MOTION_FRAME)
            {
                return Err(PrimitiveValidationError::HardInteractionOutsideActiveWindow);
            }
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_thrust() -> CombatPrimitive {
        CombatPrimitive {
            action: Action::Thrust,
            stance: Stance::Top,
            motion_frames: 16,
            root_constraints: vec![
                RootConstraint {
                    motion_frame: 0,
                    local_linear_velocity_mm_per_s: [0, 0],
                    local_yaw_millirad_per_s: 0,
                    root_height_mm: 0,
                    world_offset_mm: Millimetres { x: 0, y: 0, z: 0 },
                    heading_millirad: 0,
                },
                RootConstraint {
                    motion_frame: 8,
                    local_linear_velocity_mm_per_s: [1_200, 0],
                    local_yaw_millirad_per_s: 0,
                    root_height_mm: -40,
                    world_offset_mm: Millimetres { x: 0, y: 0, z: 600 },
                    heading_millirad: 0,
                },
            ],
            pose_constraints: vec![
                PoseConstraint {
                    motion_frame: 0,
                    phase: PrimitivePhase::Guard,
                    anchor: MotionAnchor::WeaponTip,
                    target_anchor: MotionAnchor::Chest,
                    target_offset_mm: Millimetres { x: 0, y: 0, z: 650 },
                    strength: ConstraintStrength::Soft {
                        allow_early_motion_frames: 1,
                    },
                },
                PoseConstraint {
                    motion_frame: 4,
                    phase: PrimitivePhase::Windup,
                    anchor: MotionAnchor::WeaponTip,
                    target_anchor: MotionAnchor::Chest,
                    target_offset_mm: Millimetres {
                        x: 0,
                        y: 50,
                        z: -250,
                    },
                    strength: ConstraintStrength::Soft {
                        allow_early_motion_frames: 1,
                    },
                },
                PoseConstraint {
                    motion_frame: 8,
                    phase: PrimitivePhase::Contact,
                    anchor: MotionAnchor::WeaponTip,
                    target_anchor: MotionAnchor::Chest,
                    target_offset_mm: Millimetres { x: 0, y: 0, z: 900 },
                    strength: ConstraintStrength::Hard,
                },
                PoseConstraint {
                    motion_frame: 12,
                    phase: PrimitivePhase::Recovery,
                    anchor: MotionAnchor::WeaponTip,
                    target_anchor: MotionAnchor::Chest,
                    target_offset_mm: Millimetres { x: 0, y: 0, z: 700 },
                    strength: ConstraintStrength::Soft {
                        allow_early_motion_frames: 2,
                    },
                },
            ],
            contact_windows: vec![ContactWindow {
                start_tick: 16,
                end_tick_exclusive: 20,
                emitter: ContactEmitter::WeaponTip,
                target: AnatomyTarget {
                    acceleration_region: HitLocation::Torso,
                    candidate_layers: AnatomyLayers::from_bits(
                        AnatomyLayers::ARMOR.bits()
                            | AnatomyLayers::SKIN.bits()
                            | AnatomyLayers::MUSCLE.bits()
                            | AnatomyLayers::BONE.bits()
                            | AnatomyLayers::VESSEL.bits()
                            | AnatomyLayers::NERVE.bits()
                            | AnatomyLayers::ORGAN.bits(),
                    ),
                },
            }],
            inter_agent_constraints: vec![InterAgentConstraint {
                motion_frame: 8,
                phase: PrimitivePhase::Contact,
                state: InterAgentContactState::Impact,
                self_anchor: MotionAnchor::WeaponTip,
                opponent_anchor: MotionAnchor::Chest,
                opponent_relative_root: OpponentRelativeRoot {
                    offset_mm: Millimetres { x: 0, y: 0, z: 900 },
                    heading_millirad: 0,
                },
                target: AnatomyTarget {
                    acceleration_region: HitLocation::Torso,
                    candidate_layers: AnatomyLayers::from_bits(
                        AnatomyLayers::ARMOR.bits()
                            | AnatomyLayers::SKIN.bits()
                            | AnatomyLayers::BONE.bits(),
                    ),
                },
                strength: ConstraintStrength::Hard,
                impact: Some(ImpactIntent {
                    force_millinewtons: 900_000,
                    direction_milli: [0, 0, 1_000],
                }),
            }],
        }
    }

    #[test]
    fn combat_primitive_validates_a_hard_contact_with_deep_anatomy_query() {
        let primitive = valid_thrust();
        assert_eq!(primitive.truth_duration_ticks(), 32);
        assert!(primitive.validate().is_ok());
        assert!(primitive.is_active_at(16));
        assert!(primitive.is_active_at(19));
        assert!(!primitive.is_active_at(20));
    }

    #[test]
    fn contact_phase_requires_a_hard_pose_constraint_in_its_truth_window() {
        let mut primitive = valid_thrust();
        primitive.pose_constraints[2].strength = ConstraintStrength::Soft {
            allow_early_motion_frames: 0,
        };
        assert_eq!(
            primitive.validate(),
            Err(PrimitiveValidationError::MissingHardContactConstraint)
        );
    }

    #[test]
    fn primitive_supports_multiple_contact_windows_for_compound_martial_actions() {
        let mut primitive = valid_thrust();
        primitive.pose_constraints[3].motion_frame = 14;
        primitive.pose_constraints.push(PoseConstraint {
            motion_frame: 12,
            phase: PrimitivePhase::Contact,
            anchor: MotionAnchor::WeaponEdge,
            target_anchor: MotionAnchor::Chest,
            target_offset_mm: Millimetres {
                x: 180,
                y: 100,
                z: 700,
            },
            strength: ConstraintStrength::Hard,
        });
        primitive.contact_windows.push(ContactWindow {
            start_tick: 24,
            end_tick_exclusive: 26,
            emitter: ContactEmitter::WeaponEdge,
            target: primitive.contact_windows[0].target,
        });

        assert!(primitive.validate().is_ok());
        assert!(primitive.is_active_at(16));
        assert!(primitive.is_active_at(24));
        assert!(!primitive.is_active_at(26));
    }

    #[test]
    fn primitive_rejects_a_contact_without_an_anatomical_layer_query() {
        let mut primitive = valid_thrust();
        primitive.contact_windows[0].target.candidate_layers = AnatomyLayers::from_bits(0);
        assert_eq!(
            primitive.validate(),
            Err(PrimitiveValidationError::EmptyAnatomyQuery)
        );
    }

    #[test]
    fn primitive_rejects_a_non_token_aligned_motion_duration() {
        let mut primitive = valid_thrust();
        primitive.motion_frames = 14;
        assert_eq!(
            primitive.validate(),
            Err(PrimitiveValidationError::InvalidMotionFrameCount)
        );
    }

    #[test]
    fn hard_paired_impact_must_be_scheduled_inside_truth_active_time() {
        let mut primitive = valid_thrust();
        primitive.inter_agent_constraints[0].motion_frame = 11;
        assert_eq!(
            primitive.validate(),
            Err(PrimitiveValidationError::HardInteractionOutsideActiveWindow)
        );
    }

    #[test]
    fn first_playable_registry_is_exactly_longsword_top_thrust_block_dodge() {
        assert_eq!(FIRST_PLAYABLE_WEAPON, "Longsword");
        assert_eq!(FIRST_PLAYABLE_STANCE, Stance::Top);
        assert_eq!(
            FIRST_PLAYABLE_ACTIONS,
            [Action::Thrust, Action::Block, Action::Dodge]
        );
        assert!(is_first_playable_choice(Action::Thrust, Stance::Top));
        assert!(!is_first_playable_choice(Action::Strike, Stance::Top));
        assert!(!is_first_playable_choice(Action::Thrust, Stance::Left));
    }
}
