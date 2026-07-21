//! F-110 forecast engine: hypothetical-lock copy simulation for the forecast
//! timeline / what-if UI (design authority: docs/design/FORECAST_HUD_DESIGN.md).
//!
//! A forecast clones the live `PlanPhase`, locks hypothetical intents on the
//! clone, and steps the SAME `step_truth_tick` path the live game runs, so the
//! emitted event stream is real engine output — never a parallel re-simulation.
//! The live phase is never mutated (clone-in/clone-out).

use serde::{Deserialize, Serialize};

use super::intent::Intent;
use super::plan_phase::{PlanError, PlanEvent, PlanPhase, PlanSnapshot, PlanStatus, RootPosition};
use crate::truth::Side;

/// One forecast run: the full event stream to the first actionability
/// boundary, the per-tick root track (in-world ghost input), and the terminal
/// snapshot. All fields derive from replay-hashed state — the forecast is
/// itself deterministic for a given (phase, player, opponent) triple.
#[derive(Debug, Clone)]
pub struct ForecastOutcome {
    /// Intents actually locked on the clone (post-feasibility).
    pub locked: [Option<Intent>; 2],
    /// Truth ticks simulated to the boundary.
    pub ticks: u64,
    /// All events emitted, in order (Locked, Ready, contact outcomes,
    /// GrabSecure/ClinchEnter, Reprompt, ...).
    pub events: Vec<PlanEvent>,
    /// Per-tick root positions for both fighters (index 0 = tick 0).
    pub root_track: [Vec<RootPosition>; 2],
    /// Snapshot at the boundary (window end).
    pub end_snapshot: PlanSnapshot,
}

/// A flat, UI-consumable summary of the predicted contact outcome.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PredictedOutcome {
    /// No contact is predicted inside the window (a valid readout, never a
    /// fabricated one).
    NoContact,
    /// A strike contact is predicted.
    StrikeContact,
    /// A grab begins inside the window.
    GrabBegin,
    /// The grab is predicted to secure and enter the clinch.
    SecureGrabClinch,
    /// The grab is predicted to fail (whiff or break).
    GrabFails,
}

/// Run a hypothetical-lock forecast from `phase` without mutating it.
///
/// Returns `Err(PlanError)` when the live phase is not at a planning boundary,
/// and `Ok(None)` when a side's selection is closed (busy continuation — the
/// UI should forecast with the retained intent instead).
pub fn forecast(
    phase: &PlanPhase,
    player: Intent,
    opponent: Intent,
) -> Result<Option<ForecastOutcome>, PlanError> {
    if phase.status() != PlanStatus::Planning {
        return Err(PlanError::NotPlanning);
    }
    let mut clone = phase.clone();
    if clone.can_submit_intent(Side::Player) {
        let _ = clone.submit_intent(Side::Player, player)?;
    }
    if clone.can_submit_intent(Side::Opponent) {
        let _ = clone.submit_intent(Side::Opponent, opponent)?;
    }
    let mut events = Vec::new();
    let mut root_track: [Vec<RootPosition>; 2] = [Vec::new(), Vec::new()];
    let start_frame = clone.snapshot().truth_frame;
    while matches!(clone.status(), PlanStatus::Executing { .. }) {
        let tick_events = clone.step_truth_tick()?;
        let snap = clone.snapshot();
        root_track[0].push(snap.roots[0]);
        root_track[1].push(snap.roots[1]);
        events.extend(tick_events);
    }
    let end_snapshot = clone.snapshot();
    let ticks = end_snapshot.truth_frame.saturating_sub(start_frame);
    Ok(Some(ForecastOutcome {
        locked: end_snapshot.locked,
        ticks,
        events,
        root_track,
        end_snapshot,
    }))
}

/// Reduce a forecast to its predicted contact outcome for the HUD readout.
pub fn predicted_outcome(outcome: &ForecastOutcome) -> PredictedOutcome {
    use super::plan_phase::PlanEvent as E;
    let has = |pred: fn(&E) -> bool| outcome.events.iter().any(pred);
    if has(|e| matches!(e, E::ClinchEnter { .. })) {
        return PredictedOutcome::SecureGrabClinch;
    }
    if has(|e| matches!(e, E::GrabFailed { .. } | E::GrabBlocked { .. })) {
        return PredictedOutcome::GrabFails;
    }
    if has(|e| matches!(e, E::GrabBegin { .. })) {
        return PredictedOutcome::GrabBegin;
    }
    if outcome.end_snapshot.last_contact_observed {
        return PredictedOutcome::StrikeContact;
    }
    PredictedOutcome::NoContact
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::intent::plan_phase::PlanPhase;
    use crate::intent::{MoveDirection, StrikeVariant};

    fn strike() -> Intent {
        Intent::Strike {
            variant: StrikeVariant::Slash,
        }
    }

    #[test]
    fn forecast_does_not_mutate_live_truth() {
        let phase = PlanPhase::new();
        let hash_before = phase.truth_hash();
        let outcome = forecast(&phase, strike(), Intent::Block).unwrap().unwrap();
        assert!(outcome.ticks > 0);
        assert_eq!(phase.truth_hash(), hash_before);
        assert_eq!(phase.status(), PlanStatus::Planning);
    }

    #[test]
    fn forecast_is_deterministic() {
        let phase = PlanPhase::new();
        let a = forecast(&phase, strike(), Intent::Grab).unwrap().unwrap();
        let b = forecast(&phase, strike(), Intent::Grab).unwrap().unwrap();
        assert_eq!(a.ticks, b.ticks);
        assert_eq!(a.end_snapshot, b.end_snapshot);
        assert_eq!(a.root_track, b.root_track);
    }

    #[test]
    fn forecast_events_match_stepped_copy() {
        let phase = PlanPhase::new();
        let outcome = forecast(&phase, strike(), Intent::Block).unwrap().unwrap();
        // Independent copy: lock the same intents and step manually.
        let mut copy = phase.clone();
        let _ = copy.submit_intent(Side::Player, strike());
        let _ = copy.submit_intent(Side::Opponent, Intent::Block);
        let mut events = Vec::new();
        while matches!(copy.status(), PlanStatus::Executing { .. }) {
            events.extend(copy.step_truth_tick().unwrap());
        }
        assert_eq!(outcome.ticks, copy.snapshot().truth_frame);
        assert_eq!(format!("{:?}", outcome.events), format!("{:?}", events));
    }

    #[test]
    fn forecast_window_chain_reaches_secure_clinch() {
        // One window cannot span a whole grab from neutral range; chaining
        // windows (forecast → apply → forecast) must reach the clinch, and the
        // window-local forecast must honestly report the grab beginning.
        let mut live = PlanPhase::with_roots(
            crate::intent::plan_phase::RootPosition::new(0, 0, 300),
            crate::intent::plan_phase::RootPosition::new(0, 0, -300),
        );
        let mut saw_grab_begin = false;
        for _ in 0..12 {
            let (player, opponent) = if live.clinch().is_some() {
                (
                    Intent::Clinch {
                        sub: crate::intent::ClinchIntent::Hold,
                    },
                    Intent::Clinch {
                        sub: crate::intent::ClinchIntent::Hold,
                    },
                )
            } else {
                (Intent::Block, Intent::Grab)
            };
            let outcome = forecast(&live, player, opponent).unwrap().unwrap();
            saw_grab_begin |= outcome
                .events
                .iter()
                .any(|e| matches!(e, PlanEvent::GrabBegin { .. }));
            let _ = live.submit_intent(Side::Player, player);
            let _ = live.submit_intent(Side::Opponent, opponent);
            live.simulate_to_boundary().unwrap();
            if live.clinch().is_some() {
                break;
            }
        }
        assert!(saw_grab_begin, "the grab must begin inside some window");
        assert!(
            live.clinch().is_some(),
            "window chaining must reach the clinch"
        );
    }

    #[test]
    fn forecast_out_of_range_grab_predicts_no_secure() {
        // Retreating opponent at 2000mm neutral start: grab never acquires.
        let phase = PlanPhase::new();
        let outcome = forecast(
            &phase,
            Intent::Grab,
            Intent::move_standard(MoveDirection::Retreat),
        )
        .unwrap()
        .unwrap();
        assert_ne!(
            predicted_outcome(&outcome),
            PredictedOutcome::SecureGrabClinch
        );
    }
}
