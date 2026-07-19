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
/// F-015 clinch position: who controls the tie-up and at what depth.
/// Overhook is the entry position; sustained double-Hold advances the
/// controller to BackControl (dominant — full throw/strike menu).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum ClinchPositionKind {
    Overhook,
    BackControl,
}

/// Live clinch state: which side initiated and when. The clinch forces the
/// clinch intent set on both fighters until it resolves.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub struct ClinchState {
    pub initiator: Side,
    pub entered_at_frame: u64,
    /// The side currently controlling the clinch (F-015): only the
    /// controller may Throw/Knee; only the controlled side may Tech/Break.
    pub controller: Side,
    pub position: ClinchPositionKind,
}

impl ClinchState {
    pub const fn new(initiator: Side, entered_at_frame: u64) -> Self {
        Self {
            initiator,
            entered_at_frame,
            controller: initiator,
            position: ClinchPositionKind::Overhook,
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
