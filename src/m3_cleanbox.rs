//! Adapter from the active three-action authority to the shared 120 Hz cleanbox.

use glam::Vec3;

use crate::cleanbox;
use crate::duel_world::{DuelWorld, DuelWorldError};
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
        let contact = tick
            .contact_batch
            .contact
            .map(|contact| m3::PhysicalContact {
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
            });
        session
            .submit_physical_contact(m3::PhysicalContactBatch {
                truth_frame,
                contact,
            })
            .map_err(M3CleanboxError::Submit)?;
        Ok(true)
    }
}

const fn target_action(action: m3::Action) -> truth::Action {
    match action {
        m3::Action::Strike => truth::Action::Thrust,
        m3::Action::Block => truth::Action::Block,
        m3::Action::Grab => truth::Action::Grab,
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
}
