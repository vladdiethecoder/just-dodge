//! Adapter from the active three-action authority to the shared 120 Hz cleanbox.

use glam::Vec3;

use crate::cleanbox;
use crate::duel_world::{DuelWorld, DuelWorldError, DuelWorldTarget, DuelWorldTruthTick};
use crate::milestone3 as m3;
use crate::truth;

#[derive(Debug)]
pub enum M3CleanboxError {
    MissingReveal,
    DuelWorld(DuelWorldError),
    Submit(m3::ContactSubmissionError),
}

#[derive(Debug, Default)]
pub struct M3CleanboxWorld {
    world: DuelWorld,
}

impl M3CleanboxWorld {
    pub const fn new() -> Self {
        Self {
            world: DuelWorld::new(),
        }
    }

    pub const fn next_physics_tick(&self) -> u64 {
        self.world.next_physics_tick()
    }

    /// Submits exactly two measured 120 Hz substeps for an unresolved M3 Resolve.
    pub fn submit_resolve_packet(
        &mut self,
        session: &mut m3::Session,
        player_root: Vec3,
        opponent_root: Vec3,
    ) -> Result<bool, M3CleanboxError> {
        let Some(truth_frame) = session.game.expected_contact_frame() else {
            return Ok(false);
        };
        let (player, opponent) = session
            .game
            .snapshot()
            .revealed
            .ok_or(M3CleanboxError::MissingReveal)?;
        let tick = cleanbox::step_actions(
            &mut self.world,
            truth_frame,
            target_action(player),
            target_action(opponent),
            player_root,
            opponent_root,
        )
        .map_err(M3CleanboxError::DuelWorld)?;
        submit_tick(session, tick)?;
        Ok(true)
    }

    pub fn submit_measured_resolve_packet(
        &mut self,
        session: &mut m3::Session,
        first: DuelWorldTarget<'_>,
        second: DuelWorldTarget<'_>,
    ) -> Result<bool, M3CleanboxError> {
        let Some(truth_frame) = session.game.expected_contact_frame() else {
            return Ok(false);
        };
        self.world.clear_weapon_history();
        let tick = self
            .world
            .step_truth_tick(truth_frame, first, second)
            .map_err(M3CleanboxError::DuelWorld)?;
        submit_tick(session, tick)?;
        Ok(true)
    }
}

fn submit_tick(session: &mut m3::Session, tick: DuelWorldTruthTick) -> Result<(), M3CleanboxError> {
    let truth_frame = tick.contact_batch.truth_frame;
    let to_m3_contact = |contact: truth::ContactGeometry| m3::PhysicalContact {
        attacker: match contact.attacker {
            truth::Side::Player => m3::Side::Player,
            truth::Side::Opponent => m3::Side::Opponent,
        },
        surface: match contact.surface {
            truth::ContactSurface::Body => m3::ContactSurface::Body,
            truth::ContactSurface::Guard => m3::ContactSurface::Guard,
        },
        region: m3::BodyRegion::Torso,
        severity: 1,
    };
    let contact = tick.contact_batch.contact.map(to_m3_contact);
    let opposing_contact = tick.contact_batch.opposing_contact.map(to_m3_contact);
    session
        .submit_physical_contact(m3::PhysicalContactBatch {
            truth_frame,
            contact,
            opposing_contact,
        })
        .map_err(M3CleanboxError::Submit)?;
    Ok(())
}

pub const fn target_action(action: m3::Action) -> truth::Action {
    match action {
        m3::Action::Strike => truth::Action::Thrust,
        m3::Action::Block => truth::Action::Block,
        m3::Action::Grab => truth::Action::Grab,
        m3::Action::Move => truth::Action::Dodge,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use glam::vec3;

    fn to_resolve(session: &mut m3::Session) {
        while session.game.snapshot().phase != m3::Phase::Plan {
            session.tick();
        }
        session
            .apply(m3::Side::Player, m3::Input::Select(m3::Action::Strike))
            .unwrap();
        session
            .apply(m3::Side::Opponent, m3::Input::Select(m3::Action::Block))
            .unwrap();
        session.apply(m3::Side::Player, m3::Input::Commit).unwrap();
        session
            .apply(m3::Side::Opponent, m3::Input::Commit)
            .unwrap();
        while session.game.snapshot().phase != m3::Phase::Resolve {
            session.tick();
        }
    }

    #[test]
    fn resolve_submission_advances_exactly_two_physics_substeps() {
        let mut session = m3::Session::new(1);
        let mut world = M3CleanboxWorld::new();
        to_resolve(&mut session);
        assert!(
            world
                .submit_resolve_packet(&mut session, vec3(0.0, 0.0, 1.0), vec3(0.0, 0.0, -1.0))
                .unwrap()
        );
        assert_eq!(world.next_physics_tick(), 2);
        session.tick();
        assert_ne!(session.game.snapshot().phase, m3::Phase::Resolve);
    }

    #[test]
    fn measured_strike_exchange_preserves_bilateral_contacts() {
        let mut session = m3::Session::new(2);
        while session.game.snapshot().phase != m3::Phase::Plan {
            session.tick();
        }
        session
            .apply(m3::Side::Player, m3::Input::Select(m3::Action::Strike))
            .unwrap();
        session
            .apply(m3::Side::Opponent, m3::Input::Select(m3::Action::Strike))
            .unwrap();
        session.apply(m3::Side::Player, m3::Input::Commit).unwrap();
        session
            .apply(m3::Side::Opponent, m3::Input::Commit)
            .unwrap();
        while session.game.snapshot().phase != m3::Phase::Resolve {
            session.tick();
        }

        let mut world = M3CleanboxWorld::new();
        assert!(
            world
                .submit_resolve_packet(&mut session, vec3(0.0, 0.0, 1.0), vec3(0.0, 0.0, -1.0),)
                .unwrap()
        );
        session.tick();
        assert!(session.game.snapshot().last_contact.is_some());
        assert!(session.game.snapshot().last_opposing_contact.is_some());
    }

    #[test]
    fn repeated_measured_bilateral_strikes_end_in_replayable_draw() {
        let mut session = m3::Session::new(3);
        let mut world = M3CleanboxWorld::new();
        for _ in 0..3 {
            while session.game.snapshot().phase != m3::Phase::Plan {
                session.tick();
            }
            session
                .apply(m3::Side::Player, m3::Input::Select(m3::Action::Strike))
                .unwrap();
            session
                .apply(m3::Side::Opponent, m3::Input::Select(m3::Action::Strike))
                .unwrap();
            session.apply(m3::Side::Player, m3::Input::Commit).unwrap();
            session
                .apply(m3::Side::Opponent, m3::Input::Commit)
                .unwrap();
            while session.game.snapshot().phase != m3::Phase::Resolve {
                session.tick();
            }
            assert!(
                world
                    .submit_resolve_packet(&mut session, vec3(0.0, 0.0, 1.0), vec3(0.0, 0.0, -1.0),)
                    .unwrap()
            );
            session.tick();
        }

        assert_eq!(session.game.snapshot().phase, m3::Phase::MatchResult);
        assert!(session.game.snapshot().draw);
        assert!(session.game.snapshot().player.incapacitated());
        assert!(session.game.snapshot().opponent.incapacitated());
        let replayed = m3::replay(&session.replay).unwrap();
        assert_eq!(replayed.snapshot(), session.game.snapshot());
        assert_eq!(replayed.truth_hash(), session.game.truth_hash());
    }
}
