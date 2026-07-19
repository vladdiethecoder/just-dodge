//! F-001 data-driven matchup matrix over the intent/PlanPhase tier.
//!
//! The 13 canonical action identities are locked pairwise at contact range
//! (300 mm Manhattan) and simulated to their actionability boundary; the cell
//! outcome is classified ONLY from emitted events and snapshot state — never
//! from presentation. The canonical table in `CANONICAL` is measured output
//! locked as regression gold: the per-cell tests assert the classifier
//! reproduces it deterministically (twice, identical).

use serde::{Deserialize, Serialize};

use crate::intent::intent::Intent;
use crate::intent::plan_phase::{PlanEvent, PlanPhase, PlanStatus};
use crate::truth::Side;

/// The 13 canonical non-clinch action identities (clinch lanes are owned by
/// the S-08 grab/clinch tests and are not matrix cells).
pub const MATRIX_ACTIONS: [Intent; 13] = [
    Intent::Strike {
        variant: crate::intent::intent::StrikeVariant::Slash,
    },
    Intent::Strike {
        variant: crate::intent::intent::StrikeVariant::Thrust,
    },
    Intent::Block,
    Intent::Grab,
    Intent::Dodge {
        dir: crate::intent::intent::MoveDirection::LateralLeft,
    },
    Intent::move_standard(crate::intent::intent::MoveDirection::Approach),
    Intent::move_standard(crate::intent::intent::MoveDirection::Retreat),
    Intent::move_standard(crate::intent::intent::MoveDirection::LateralRight),
    Intent::move_standard(crate::intent::intent::MoveDirection::CircleCounterClockwise),
    Intent::move_standard(crate::intent::intent::MoveDirection::CircleClockwise),
    Intent::Feint,
    Intent::Cancel,
    Intent::Idle,
];

/// One matrix cell's exchange outcome.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CellOutcome {
    /// A's attack resolved unblocked (hit or secured grab).
    AWin,
    /// B's attack resolved unblocked.
    BWin,
    /// Both attacks resolved unblocked in the same window.
    Clash,
    /// The only attack contact was blocked (normal or perfect).
    Blocked,
    /// No contact and no positional resolution inside the window.
    Whiff,
    /// Positional resolution only (movement actions).
    Movement,
    /// Cell not resolvable (clinch outside an active clinch).
    NotApplicable,
}

/// Classify one cell by locking (a, b) at 300 mm Manhattan and simulating to
/// the first actionability boundary.
pub fn classify_cell(a: Intent, b: Intent) -> CellOutcome {
    let player = crate::intent::plan_phase::RootPosition::new(0, 0, 300);
    let opponent = crate::intent::plan_phase::RootPosition::new(0, 0, -300);
    let mut phase = PlanPhase::with_roots(player, opponent);
    let _ = phase.submit_intent(Side::Player, a);
    let _ = phase.submit_intent(Side::Opponent, b);
    if !matches!(phase.status(), PlanStatus::Executing { .. }) {
        return CellOutcome::NotApplicable;
    }
    let mut events = Vec::new();
    // Chain up to 3 actionability windows so slow resolutions (a full grab
    // from acquire to secure) classify by their actual outcome, not by the
    // first window's truncation.
    for _ in 0..3 {
        while matches!(phase.status(), PlanStatus::Executing { .. }) {
            events.extend(phase.step_truth_tick().expect("matrix cell sim"));
        }
        let mut relocked = false;
        for (side, intent) in [(Side::Player, a), (Side::Opponent, b)] {
            if phase.can_submit_intent(side) {
                let _ = phase.submit_intent(side, intent);
                relocked = true;
            }
        }
        if !relocked || !matches!(phase.status(), PlanStatus::Executing { .. }) {
            break;
        }
    }
    let snap = phase.snapshot();

    let a_grab_secure = events
        .iter()
        .any(|e| matches!(e, PlanEvent::ClinchEnter { initiator } if *initiator == Side::Player));
    let b_grab_secure = events
        .iter()
        .any(|e| matches!(e, PlanEvent::ClinchEnter { initiator } if *initiator == Side::Opponent));
    let a_blocked_contact = events
        .iter()
        .any(|e| matches!(e, PlanEvent::Parried { side } if *side == Side::Opponent))
        || (matches!(b, Intent::Block)
            && snap.last_contact_observed
            && matches!(a, Intent::Strike { .. }));
    let b_blocked_contact = events
        .iter()
        .any(|e| matches!(e, PlanEvent::Parried { side } if *side == Side::Player))
        || (matches!(a, Intent::Block)
            && snap.last_contact_observed
            && matches!(b, Intent::Strike { .. }));
    let a_hit = snap.last_contact_observed
        && matches!(a, Intent::Strike { .. })
        && !matches!(b, Intent::Block);
    let b_hit = snap.last_contact_observed
        && matches!(b, Intent::Strike { .. })
        && !matches!(a, Intent::Block);

    match (a_grab_secure, b_grab_secure) {
        (true, false) => return CellOutcome::AWin,
        (false, true) => return CellOutcome::BWin,
        (true, true) => return CellOutcome::Clash,
        _ => {}
    }
    match (a_hit, b_hit) {
        (true, true) => return CellOutcome::Clash,
        (true, false) => return CellOutcome::AWin,
        (false, true) => return CellOutcome::BWin,
        _ => {}
    }
    if a_blocked_contact || b_blocked_contact {
        return CellOutcome::Blocked;
    }
    let moved = snap.roots[0] != player || snap.roots[1] != opponent;
    if moved {
        CellOutcome::Movement
    } else {
        CellOutcome::Whiff
    }
}

/// Canonical measured matrix (2026-07-19, truth rev with stance/tempo W2):
/// rows = A (player), cols = B (opponent), order = MATRIX_ACTIONS.
/// a=AWin b=BWin c=Clash k=Blocked w=Whiff m=Movement
#[cfg(test)]
const CANONICAL: [&str; 13] = [
    "cckamammmmaaa",
    "cckamaammmaaa",
    "kkwbmmmmmmwww",
    "abaamaammmaaa",
    "bmmmmmmmmmmmm",
    "bbmbmmmmmmmmm",
    "mbmbmmmmmmmmm",
    "mmmmmmmmmmmmm",
    "mmmmmmmmmmmmm",
    "mmmmmmmmmmmmm",
    "bbwbmmmmmmwww",
    "bbwbmmmmmmwww",
    "bbwbmmmmmmwww",
];

#[cfg(test)]
fn decode(cell: u8) -> CellOutcome {
    match cell {
        b'a' => CellOutcome::AWin,
        b'b' => CellOutcome::BWin,
        b'c' => CellOutcome::Clash,
        b'k' => CellOutcome::Blocked,
        b'w' => CellOutcome::Whiff,
        b'm' => CellOutcome::Movement,
        _ => CellOutcome::NotApplicable,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Generator: prints the measured matrix for locking into CANONICAL.
    /// Run: cargo test --lib intent::matrix -- --nocapture
    #[test]
    fn print_measured_matrix() {
        for (i, a) in MATRIX_ACTIONS.iter().enumerate() {
            let row: Vec<String> = MATRIX_ACTIONS
                .iter()
                .map(|b| format!("{:?}", classify_cell(*a, *b)))
                .collect();
            println!("ROW {i}: {}", row.join(","));
        }
    }

    /// F-001 per-cell golden: every one of the 169 cells must classify to the
    /// canonical measured outcome, deterministically (classified twice).
    #[test]
    fn matrix_cells_match_canonical() {
        assert!(CANONICAL.iter().all(|row| row.len() == 13));
        for (i, a) in MATRIX_ACTIONS.iter().enumerate() {
            for (j, b) in MATRIX_ACTIONS.iter().enumerate() {
                let expected = decode(CANONICAL[i].as_bytes()[j]);
                let first = classify_cell(*a, *b);
                let second = classify_cell(*a, *b);
                assert_eq!(first, second, "cell ({i},{j}) must be deterministic");
                assert_eq!(
                    first, expected,
                    "cell ({i},{j}): {a:?} vs {b:?} expected {expected:?}, got {first:?}"
                );
            }
        }
    }
}
