//! Intent vocabulary and authoritative STATE + HITBOX data for the intent loop.
//!
//! `frame_cost()` remains as the canonical animation length for callers that
//! need a bounded feasibility budget. It is *not* a forecast-window duration:
//! `PlanPhase` advances the live interaction until an actionability event.

use serde::{Deserialize, Serialize};

/// A named weapon attack family. The frame budget is owned by [`Intent`], not
/// by presentation animation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum StrikeVariant {
    Thrust,
    Slash,
}

/// Relative kinematic movement goals. All directions are resolved against the
/// current opponent root by the plan-phase authority.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MoveDirection {
    Approach,
    Retreat,
    LateralLeft,
    LateralRight,
    CircleClockwise,
    CircleCounterClockwise,
}

/// Authoritative movement parameters committed at the simultaneous lock.
///
/// `distance_mm` is the total requested root travel, not a request to approach
/// indefinitely. `auto_correct` re-samples the opponent-relative heading each
/// truth tick; when false, the heading captured at lock is retained.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct MoveParameters {
    pub distance_mm: u16,
    pub auto_correct: bool,
}

impl MoveParameters {
    pub const DEFAULT_DISTANCE_MM: u16 = 600;

    pub const fn standard() -> Self {
        Self {
            distance_mm: Self::DEFAULT_DISTANCE_MM,
            auto_correct: true,
        }
    }
}

/// A cancellable, state-owned hit region. The measured DuelWorld contact is
/// accepted only while an applicable hitbox is active.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Hitbox {
    pub start_tick: u16,
    pub active_ticks: u16,
    pub cancellable: bool,
    pub target_eligibility: TargetEligibility,
}

impl Hitbox {
    pub const fn active_at(self, tick: u16) -> bool {
        tick >= self.start_tick && tick < self.start_tick.saturating_add(self.active_ticks)
    }
}

/// Target classification retained in the state data instead of inferred from
/// presentation animation. M1 currently resolves only opponent body contact.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum TargetEligibility {
    OpponentBody,
}

/// Action state data used by the live actionability simulation.
///
/// The category strings are intentionally data, not UI text: later cancel
/// systems can query them without deriving recovery from startup/active/recovery
/// presentation segments.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct State {
    pub anim_length: u16,
    pub iasa_at: u16,
    pub interrupt_frames: &'static [u16],
    pub iasa_on_hit: Option<u16>,
    pub iasa_on_hit_on_block: bool,
    pub interruptible_on_opponent_turn: bool,
    pub cancel_categories: &'static [&'static str],
    pub feint_cancel_categories: &'static [&'static str],
}

const NO_INTERRUPTS: &[u16] = &[];
const DEFENSIVE_INTERRUPTS: &[u16] = &[8];

const GROUND_CANCELS: &[&str] = &["Grounded"];
const FEINT_CANCELS: &[&str] = &["Grounded", "Aerial"];

const THRUST_HITBOXES: &[Hitbox] = &[Hitbox {
    start_tick: 3,
    active_ticks: 5,
    cancellable: true,
    target_eligibility: TargetEligibility::OpponentBody,
}];
const SLASH_HITBOXES: &[Hitbox] = &[Hitbox {
    start_tick: 4,
    active_ticks: 6,
    cancellable: true,
    target_eligibility: TargetEligibility::OpponentBody,
}];
const GRAB_HITBOXES: &[Hitbox] = &[Hitbox {
    start_tick: 5,
    active_ticks: 4,
    cancellable: false,
    target_eligibility: TargetEligibility::OpponentBody,
}];
const NO_HITBOXES: &[Hitbox] = &[];

/// The action a fighter locks during a simultaneous planning phase.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Intent {
    Strike {
        variant: StrikeVariant,
    },
    Block,
    Grab,
    Move {
        dir: MoveDirection,
        distance_mm: u16,
        auto_correct: bool,
    },
    Dodge {
        dir: MoveDirection,
    },
    /// A committed feint. `Cancel` is the cheap cancel-feint route.
    Feint,
    /// Cancels the prior chain but creates a deterministic recovery penalty.
    Cancel,
    Idle,
    Clinch {
        sub: super::clinch::ClinchIntent,
    },
    /// F-019: voluntarily draw the weapon — re-arms at the end of the
    /// window; the draw window is unarmed and counter-hit vulnerable.
    Draw,
    /// F-019: voluntarily sheath the weapon — loses Strike until Draw, but
    /// accelerates tempo regen while sheathed.
    Sheath,
}

impl Intent {
    /// Construct a standard 600 mm auto-correcting movement intent.
    pub const fn move_standard(dir: MoveDirection) -> Self {
        Self::Move {
            dir,
            distance_mm: MoveParameters::DEFAULT_DISTANCE_MM,
            auto_correct: true,
        }
    }

    pub const fn movement_parameters(self) -> Option<MoveParameters> {
        match self {
            Self::Move {
                distance_mm,
                auto_correct,
                ..
            } => Some(MoveParameters {
                distance_mm,
                auto_correct,
            }),
            _ => None,
        }
    }

    /// Per-move authoritative STATE data. Movement's IASA scales with the
    /// committed distance rather than using a generic frame-cost constant.
    pub const fn state(self) -> State {
        match self {
            Self::Strike {
                variant: StrikeVariant::Thrust,
            } => State {
                anim_length: 18,
                iasa_at: 14,
                interrupt_frames: NO_INTERRUPTS,
                iasa_on_hit: Some(4),
                iasa_on_hit_on_block: true,
                interruptible_on_opponent_turn: false,
                cancel_categories: GROUND_CANCELS,
                feint_cancel_categories: NO_CANCELS,
            },
            Self::Strike {
                variant: StrikeVariant::Slash,
            } => State {
                anim_length: 22,
                iasa_at: 17,
                interrupt_frames: NO_INTERRUPTS,
                iasa_on_hit: Some(5),
                iasa_on_hit_on_block: false,
                interruptible_on_opponent_turn: false,
                cancel_categories: GROUND_CANCELS,
                feint_cancel_categories: NO_CANCELS,
            },
            Self::Block => State {
                anim_length: 12,
                iasa_at: 9,
                interrupt_frames: DEFENSIVE_INTERRUPTS,
                iasa_on_hit: None,
                iasa_on_hit_on_block: false,
                interruptible_on_opponent_turn: true,
                cancel_categories: GROUND_CANCELS,
                feint_cancel_categories: NO_CANCELS,
            },
            Self::Grab => State {
                anim_length: 20,
                iasa_at: 16,
                interrupt_frames: NO_INTERRUPTS,
                iasa_on_hit: None,
                iasa_on_hit_on_block: false,
                interruptible_on_opponent_turn: false,
                cancel_categories: NO_CANCELS,
                feint_cancel_categories: NO_CANCELS,
            },
            Self::Move { distance_mm, .. } => {
                let iasa_at = move_iasa_at(distance_mm);
                State {
                    anim_length: iasa_at.saturating_add(3),
                    iasa_at,
                    interrupt_frames: NO_INTERRUPTS,
                    iasa_on_hit: None,
                    iasa_on_hit_on_block: false,
                    interruptible_on_opponent_turn: false,
                    cancel_categories: GROUND_CANCELS,
                    feint_cancel_categories: NO_CANCELS,
                }
            }
            Self::Dodge { .. } => State {
                anim_length: 10,
                iasa_at: 8,
                interrupt_frames: DEFENSIVE_INTERRUPTS,
                iasa_on_hit: None,
                iasa_on_hit_on_block: false,
                interruptible_on_opponent_turn: true,
                cancel_categories: GROUND_CANCELS,
                feint_cancel_categories: NO_CANCELS,
            },
            Self::Feint => State {
                anim_length: 6,
                iasa_at: 5,
                interrupt_frames: NO_INTERRUPTS,
                iasa_on_hit: None,
                iasa_on_hit_on_block: false,
                interruptible_on_opponent_turn: false,
                cancel_categories: GROUND_CANCELS,
                feint_cancel_categories: FEINT_CANCELS,
            },
            Self::Cancel => State {
                anim_length: 8,
                iasa_at: 6,
                interrupt_frames: NO_INTERRUPTS,
                iasa_on_hit: None,
                iasa_on_hit_on_block: false,
                interruptible_on_opponent_turn: false,
                cancel_categories: GROUND_CANCELS,
                feint_cancel_categories: NO_CANCELS,
            },
            Self::Idle => State {
                anim_length: 6,
                iasa_at: 5,
                interrupt_frames: NO_INTERRUPTS,
                iasa_on_hit: None,
                iasa_on_hit_on_block: false,
                interruptible_on_opponent_turn: true,
                cancel_categories: GROUND_CANCELS,
                feint_cancel_categories: NO_CANCELS,
            },
            Self::Clinch { sub } => State {
                anim_length: sub.frame_cost(),
                iasa_at: sub.frame_cost().saturating_sub(1),
                interrupt_frames: NO_INTERRUPTS,
                iasa_on_hit: None,
                iasa_on_hit_on_block: false,
                interruptible_on_opponent_turn: false,
                cancel_categories: NO_CANCELS,
                feint_cancel_categories: NO_CANCELS,
            },
            Self::Draw => State {
                anim_length: 16,
                iasa_at: 15,
                interrupt_frames: NO_INTERRUPTS,
                iasa_on_hit: None,
                iasa_on_hit_on_block: false,
                interruptible_on_opponent_turn: false,
                cancel_categories: GROUND_CANCELS,
                feint_cancel_categories: NO_CANCELS,
            },
            Self::Sheath => State {
                anim_length: 12,
                iasa_at: 10,
                interrupt_frames: NO_INTERRUPTS,
                iasa_on_hit: None,
                iasa_on_hit_on_block: false,
                interruptible_on_opponent_turn: false,
                cancel_categories: GROUND_CANCELS,
                feint_cancel_categories: NO_CANCELS,
            },
        }
    }

    pub const fn hitboxes(self) -> &'static [Hitbox] {
        match self {
            Self::Strike {
                variant: StrikeVariant::Thrust,
            } => THRUST_HITBOXES,
            Self::Strike {
                variant: StrikeVariant::Slash,
            } => SLASH_HITBOXES,
            Self::Grab => GRAB_HITBOXES,
            _ => NO_HITBOXES,
        }
    }

    /// Canonical animation length, retained for feasibility callers. Forecast
    /// boundaries are resolved exclusively by live actionability events.
    pub const fn frame_cost(self) -> u16 {
        self.state().anim_length
    }
}

const NO_CANCELS: &[&str] = &[];

const fn move_iasa_at(distance_mm: u16) -> u16 {
    // A 100 mm/tick dash needs one extra commit tick plus a fixed startup. The
    // ceiling division is integer-only and capped to avoid unbounded plans.
    let travel_ticks = distance_mm.saturating_add(99) / 100;
    3 + if travel_ticks > 21 { 21 } else { travel_ticks }
}
