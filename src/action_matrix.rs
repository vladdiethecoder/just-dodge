// 3-action matchup matrix and timing data for the prototype.
// See docs/design/IMPLEMENTATION_PLAN_3ACTION.md for the contract.

use std::sync::OnceLock;

use serde::Deserialize;

use crate::truth::{Action, ContactGeometry, HitLocation, Side, Stance};

/// Result of resolving a pair of committed actions.
#[derive(Debug, Clone)]
pub struct MatrixResult {
    pub contact_type: ContactType,
    pub initiative: Side,
    pub hit_location: HitLocation,
    pub force: f32,
    pub tempo_delta: i32,
}

/// Classification of how two actions interact.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
pub enum ContactType {
    Hit,
    Clash,
    Beat,
    Whiff,
    GrabSuccess,
    GrabTech,
}

/// Timing data for one action (frames at 60 Hz).
#[derive(Debug, Clone, Copy, Deserialize)]
pub struct Timing {
    pub startup: u32,
    pub active: u32,
    pub recovery: u32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
enum StanceCondition {
    Same,
    Different,
    Any,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
enum RelativeSide {
    A,
    B,
}

impl RelativeSide {
    fn to_side(self) -> Side {
        match self {
            RelativeSide::A => Side::Player,
            RelativeSide::B => Side::Opponent,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
struct Rule {
    a: Action,
    b: Action,
    stance: StanceCondition,
    contact: ContactType,
    initiative: RelativeSide,
    force: f32,
    hit_location: HitLocation,
}

/// Authoritative data loaded from `assets/data/action_matrix.ron`.
#[derive(Debug, Clone, Deserialize)]
pub(crate) struct ActionMatrixData {
    timing: Vec<(Action, Timing)>,
    rules: Vec<Rule>,
}

static MATRIX_DATA: OnceLock<ActionMatrixData> = OnceLock::new();

/// Embedded RON fallback, used when the external data file is missing or unreadable.
const FALLBACK_RON: &str = include_str!("../assets/data/action_matrix.ron");

/// Access the loaded action-matrix data.
pub(crate) fn matrix_data() -> &'static ActionMatrixData {
    MATRIX_DATA.get_or_init(|| {
        let path = "assets/data/action_matrix.ron";
        std::fs::read_to_string(path)
            .ok()
            .and_then(|text| ron::from_str::<ActionMatrixData>(&text).ok())
            .or_else(|| ron::from_str::<ActionMatrixData>(FALLBACK_RON).ok())
            .expect("action_matrix.ron is missing and the embedded fallback is invalid")
    })
}

/// Timing for a single action.
pub fn timing(action: Action) -> Option<Timing> {
    matrix_data()
        .timing
        .iter()
        .find(|(a, _)| *a == action)
        .map(|(_, t)| *t)
}

/// Resolve a pair of committed actions into a contact result.
///
/// `contact` is provided by the hitbox agent.  If it is `None` or out of range,
/// the result is a `Whiff`.
pub fn resolve(
    action_a: Action,
    action_b: Action,
    stance_a: Stance,
    stance_b: Stance,
    contact: &Option<ContactGeometry>,
) -> MatrixResult {
    // No contact geometry or out of range => whiff.
    if contact.map_or(true, |c| !c.in_range) {
        return whiff_result(Side::Player);
    }

    let same_stance = stance_a == stance_b;
    let data = matrix_data();

    for rule in &data.rules {
        if rule.a != action_a || rule.b != action_b {
            continue;
        }
        let stance_ok = match rule.stance {
            StanceCondition::Same => same_stance,
            StanceCondition::Different => !same_stance,
            StanceCondition::Any => true,
        };
        if stance_ok {
            return MatrixResult {
                contact_type: rule.contact,
                initiative: rule.initiative.to_side(),
                hit_location: rule.hit_location,
                force: rule.force,
                tempo_delta: 0,
            };
        }
    }

    // No explicit rule matched: safe fallback.
    whiff_result(Side::Player)
}

fn whiff_result(initiative: Side) -> MatrixResult {
    MatrixResult {
        contact_type: ContactType::Whiff,
        initiative,
        hit_location: HitLocation::Torso,
        force: 0.0,
        tempo_delta: 0,
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn in_range() -> Option<ContactGeometry> {
        Some(ContactGeometry {
            distance: 1.0,
            in_range: true,
        })
    }

    #[test]
    fn strike_beats_grab() {
        let r = resolve(Action::Strike, Action::Grab, Stance::Top, Stance::Top, &in_range());
        assert_eq!(r.contact_type, ContactType::Hit);
        assert_eq!(r.initiative, Side::Player);
    }

    #[test]
    fn block_beats_strike_same_stance() {
        let r = resolve(Action::Block, Action::Strike, Stance::Top, Stance::Top, &in_range());
        assert_eq!(r.contact_type, ContactType::Beat);
        assert_eq!(r.initiative, Side::Player);
    }

    #[test]
    fn grab_beats_block() {
        let r = resolve(Action::Grab, Action::Block, Stance::Top, Stance::Top, &in_range());
        assert_eq!(r.contact_type, ContactType::GrabSuccess);
        assert_eq!(r.initiative, Side::Player);
    }

    #[test]
    fn same_stance_strike_clashes() {
        let r = resolve(Action::Strike, Action::Strike, Stance::Left, Stance::Left, &in_range());
        assert_eq!(r.contact_type, ContactType::Clash);
    }

    #[test]
    fn missing_contact_is_whiff() {
        let r = resolve(Action::Strike, Action::Block, Stance::Top, Stance::Top, &None);
        assert_eq!(r.contact_type, ContactType::Whiff);
    }

    #[test]
    fn timing_table_loads() {
        for action in [Action::Strike, Action::Block, Action::Grab] {
            let t = timing(action).expect("timing entry missing");
            assert!(t.startup + t.active + t.recovery > 0);
        }
    }
}
