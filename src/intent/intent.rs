//! Intent vocabulary and fixed data-tuned frame costs for the intent loop.

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

/// The action a fighter locks during a simultaneous planning phase.
///
/// Frame costs are deliberately action-family constants. They are independent
/// of generated motion so that a replay can re-simulate the same truth budget.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Intent {
    Strike {
        variant: StrikeVariant,
    },
    Block,
    Grab,
    Move {
        dir: MoveDirection,
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
}

impl Intent {
    /// Fixed truth-frame cost for this action family.
    pub const fn frame_cost(self) -> u16 {
        match self {
            Self::Strike {
                variant: StrikeVariant::Thrust,
            } => 18,
            Self::Strike {
                variant: StrikeVariant::Slash,
            } => 22,
            Self::Block => 12,
            Self::Grab => 20,
            Self::Move { .. } => 12,
            Self::Dodge { .. } => 10,
            Self::Feint => 6,
            Self::Cancel => 8,
            Self::Idle => 6,
            Self::Clinch { sub } => sub.frame_cost(),
        }
    }
}
