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
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ClinchResolution {
    Continue,
    Exit {
        escaped_by: Side,
    },
    Launch {
        launched: Side,
    },
    /// F-016: the controlled side teched with no throw coming — the tech
    /// whiffs and the controller deepens for free (deterministic punishment).
    WhiffedTech {
        teched_by: Side,
    },
}

/// F-016 deterministic throw/tech contest, controller-relative:
/// - Throw vs Tech: the tech reads the throw → escape.
/// - Throw vs anything else: the throw launches the controlled side.
/// - Tech vs non-Throw: the tech whiffs (WhiffedTech).
///
/// Tech by the controller is illegal upstream (F-015 gate), so only the
/// controlled side's tech is considered.
pub fn resolve(player: ClinchIntent, opponent: ClinchIntent, controller: Side) -> ClinchResolution {
    let (controller_pick, controlled_pick, controlled) = if controller == Side::Player {
        (player, opponent, Side::Opponent)
    } else {
        (opponent, player, Side::Player)
    };
    if controlled_pick == ClinchIntent::Break {
        return ClinchResolution::Exit {
            escaped_by: controlled,
        };
    }
    if controlled_pick == ClinchIntent::Tech {
        if controller_pick == ClinchIntent::Throw {
            return ClinchResolution::Exit {
                escaped_by: controlled,
            };
        }
        return ClinchResolution::WhiffedTech {
            teched_by: controlled,
        };
    }
    if controller_pick == ClinchIntent::Throw {
        return ClinchResolution::Launch {
            launched: controlled,
        };
    }
    ClinchResolution::Continue
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn throw_vs_tech_escapes_the_controlled_side() {
        assert_eq!(
            resolve(ClinchIntent::Throw, ClinchIntent::Tech, Side::Player),
            ClinchResolution::Exit {
                escaped_by: Side::Opponent
            }
        );
        // Symmetric: controller = Opponent.
        assert_eq!(
            resolve(ClinchIntent::Tech, ClinchIntent::Throw, Side::Opponent),
            ClinchResolution::Exit {
                escaped_by: Side::Player
            }
        );
    }

    #[test]
    fn throw_against_no_tech_launches_the_controlled_side() {
        assert_eq!(
            resolve(ClinchIntent::Throw, ClinchIntent::Hold, Side::Player),
            ClinchResolution::Launch {
                launched: Side::Opponent
            }
        );
    }

    #[test]
    fn tech_against_no_throw_whiffs() {
        assert_eq!(
            resolve(ClinchIntent::Hold, ClinchIntent::Tech, Side::Player),
            ClinchResolution::WhiffedTech {
                teched_by: Side::Opponent
            }
        );
    }

    #[test]
    fn break_always_escapes() {
        assert_eq!(
            resolve(ClinchIntent::Throw, ClinchIntent::Break, Side::Player),
            ClinchResolution::Exit {
                escaped_by: Side::Opponent
            }
        );
    }
}
