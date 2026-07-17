//! Deterministic clinch-only simultaneous sub-exchange.

use serde::{Deserialize, Serialize};

use crate::truth::Side;

/// A close-range action available only while the duel is in a clinch.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ClinchIntent {
    Hold,
    Knee,
    Throw,
    /// A simultaneous grab-tech that exits the clinch instead of trading.
    Tech,
    Break,
}

impl ClinchIntent {
    pub const fn frame_cost(self) -> u16 {
        match self {
            Self::Hold => 8,
            Self::Knee => 12,
            Self::Throw => 16,
            Self::Tech => 6,
            Self::Break => 10,
        }
    }
}

/// State owned by the intent authority while two fighters are clinched.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ClinchState {
    pub initiator: Side,
    pub entered_at_frame: u64,
}

impl ClinchState {
    pub const fn new(initiator: Side, entered_at_frame: u64) -> Self {
        Self {
            initiator,
            entered_at_frame,
        }
    }
}

/// Result of one simultaneously locked clinch exchange.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ClinchResolution {
    Continue,
    Exit { escaped_by: Side },
    Launch { launched: Side },
}

/// Resolve without an initiative-order bias. Tech wins as an escape if either
/// fighter selected it; matching throws otherwise launch both into the regular
/// deterministic ballistic state.
pub fn resolve(player: ClinchIntent, opponent: ClinchIntent) -> ClinchResolution {
    if player == ClinchIntent::Tech {
        return ClinchResolution::Exit {
            escaped_by: Side::Player,
        };
    }
    if opponent == ClinchIntent::Tech {
        return ClinchResolution::Exit {
            escaped_by: Side::Opponent,
        };
    }
    if player == ClinchIntent::Break {
        return ClinchResolution::Exit {
            escaped_by: Side::Player,
        };
    }
    if opponent == ClinchIntent::Break {
        return ClinchResolution::Exit {
            escaped_by: Side::Opponent,
        };
    }
    if player == ClinchIntent::Throw && opponent == ClinchIntent::Throw {
        return ClinchResolution::Launch {
            launched: Side::Player,
        };
    }
    if player == ClinchIntent::Throw {
        return ClinchResolution::Launch {
            launched: Side::Opponent,
        };
    }
    if opponent == ClinchIntent::Throw {
        return ClinchResolution::Launch {
            launched: Side::Player,
        };
    }
    ClinchResolution::Continue
}
