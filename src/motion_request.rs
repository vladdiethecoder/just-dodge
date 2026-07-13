//! Public M3 snapshot → presentation motion request boundary.
//!
//! This module intentionally sits on the presentation side of M3. It reads an
//! immutable public snapshot and never reads planned actions before Reveal or
//! exposes a mutation path back into truth.

use crate::milestone3 as m3;
use crate::motion::Action;

/// Public injury state available to presentation. This is a snapshot of M3
/// capability consequences, not authority for combat resolution.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct InjuryModifiers {
    pub head: u8,
    pub torso: u8,
    pub arms: u8,
}

/// Stable, presentation-only request for one visible actor at one public M3
/// frame. No request exists during Observe, Plan, or Commit: action selection
/// remains hidden until M3 enters Reveal.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MotionRequest {
    pub request_id: u64,
    pub side: m3::Side,
    pub action: Action,
    pub phase: m3::Phase,
    pub phase_frame: u16,
    pub injury: InjuryModifiers,
}

/// Derive the request for one actor from an immutable M3 snapshot. It never
/// reads planned actions, so hidden commitments cannot reach motion generation.
pub fn motion_request_from_snapshot(
    snapshot: &m3::Snapshot,
    side: m3::Side,
) -> Option<MotionRequest> {
    if !matches!(
        snapshot.phase,
        m3::Phase::Reveal | m3::Phase::Resolve | m3::Phase::Consequence | m3::Phase::MatchResult
    ) {
        return None;
    }
    let (player_action, opponent_action) = snapshot.revealed?;
    let (action, fighter) = match side {
        m3::Side::Player => (player_action, snapshot.player),
        m3::Side::Opponent => (opponent_action, snapshot.opponent),
    };
    let action = match action {
        m3::Action::Strike => Action::Strike,
        m3::Action::Block => Action::Block,
        m3::Action::Grab => Action::Grab,
    };
    let injury = InjuryModifiers {
        head: fighter.head_injury,
        torso: fighter.torso_injury,
        arms: fighter.arm_injury,
    };
    Some(MotionRequest {
        request_id: stable_motion_request_id(snapshot, side, action, injury),
        side,
        action,
        phase: snapshot.phase,
        phase_frame: snapshot.phase_frame,
        injury,
    })
}

/// Produce both actor requests in stable Player/Opponent order.
pub fn motion_requests_from_snapshot(snapshot: &m3::Snapshot) -> [Option<MotionRequest>; 2] {
    [
        motion_request_from_snapshot(snapshot, m3::Side::Player),
        motion_request_from_snapshot(snapshot, m3::Side::Opponent),
    ]
}

fn stable_motion_request_id(
    snapshot: &m3::Snapshot,
    side: m3::Side,
    action: Action,
    injury: InjuryModifiers,
) -> u64 {
    const FNV_OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
    const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;
    let side = match side {
        m3::Side::Player => 0,
        m3::Side::Opponent => 1,
    };
    let action = match action {
        Action::Strike => 0,
        Action::Block => 1,
        Action::Grab => 2,
        Action::Thrust => 3,
        Action::Dodge => 4,
        Action::Idle => 5,
    };
    let phase = match snapshot.phase {
        m3::Phase::Observe => 0,
        m3::Phase::Plan => 1,
        m3::Phase::Commit => 2,
        m3::Phase::Reveal => 3,
        m3::Phase::Resolve => 4,
        m3::Phase::Consequence => 5,
        m3::Phase::MatchResult => 6,
    };
    [
        snapshot.seed,
        u64::from(snapshot.exchange),
        u64::from(snapshot.frame),
        side,
        action,
        phase,
        u64::from(snapshot.phase_frame),
        u64::from(injury.head),
        u64::from(injury.torso),
        u64::from(injury.arms),
    ]
    .into_iter()
    .fold(FNV_OFFSET, |hash, field| {
        (hash ^ field).wrapping_mul(FNV_PRIME)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn advance_to_plan(game: &mut m3::Match) {
        while game.snapshot().phase != m3::Phase::Plan {
            game.tick();
        }
    }

    fn revealed_match(seed: u64) -> m3::Match {
        let mut game = m3::Match::new(seed);
        advance_to_plan(&mut game);
        game.apply(m3::Side::Player, m3::Input::Select(m3::Action::Strike))
            .unwrap();
        game.apply(m3::Side::Opponent, m3::Input::Select(m3::Action::Grab))
            .unwrap();
        game.apply(m3::Side::Player, m3::Input::Commit).unwrap();
        game.apply(m3::Side::Opponent, m3::Input::Commit).unwrap();
        while game.snapshot().phase != m3::Phase::Reveal {
            game.tick();
        }
        game
    }

    #[test]
    fn hidden_plan_and_commit_intent_never_emit_motion_requests() {
        let mut game = m3::Match::new(7);
        advance_to_plan(&mut game);
        game.apply(m3::Side::Player, m3::Input::Select(m3::Action::Strike))
            .unwrap();
        assert_eq!(motion_requests_from_snapshot(game.snapshot()), [None, None]);

        game.apply(m3::Side::Opponent, m3::Input::Select(m3::Action::Grab))
            .unwrap();
        game.apply(m3::Side::Player, m3::Input::Commit).unwrap();
        game.apply(m3::Side::Opponent, m3::Input::Commit).unwrap();
        game.tick();
        assert_eq!(game.snapshot().phase, m3::Phase::Commit);
        assert_eq!(motion_requests_from_snapshot(game.snapshot()), [None, None]);
    }

    #[test]
    fn revealed_requests_are_public_deterministic_and_truth_read_only() {
        let game = revealed_match(13);
        let before_hash = game.truth_hash();
        let first = motion_requests_from_snapshot(game.snapshot());
        let second = motion_requests_from_snapshot(&game.snapshot().clone());
        assert_eq!(first, second);
        assert_eq!(game.truth_hash(), before_hash);

        let player = first[0].expect("Reveal must publish the player request");
        let opponent = first[1].expect("Reveal must publish the opponent request");
        assert_eq!(player.side, m3::Side::Player);
        assert_eq!(player.action, Action::Strike);
        assert_eq!(opponent.side, m3::Side::Opponent);
        assert_eq!(opponent.action, Action::Grab);
        assert_eq!(player.phase, m3::Phase::Reveal);
        assert_eq!(opponent.phase, m3::Phase::Reveal);
    }

    #[test]
    fn identical_m3_replays_emit_identical_motion_request_receipts() {
        let first = revealed_match(0x4d33).snapshot().clone();
        let second = revealed_match(0x4d33).snapshot().clone();
        assert_eq!(first, second);
        assert_eq!(
            motion_requests_from_snapshot(&first),
            motion_requests_from_snapshot(&second)
        );
    }
}
