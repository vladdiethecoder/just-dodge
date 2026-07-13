//! Deterministic kinematic target boundary for the shared duel physics world.
//!
//! This module intentionally does not generate motion. A caller must provide
//! world-space weapon transforms and body proxies from an external physical
//! target source. The world retains only prior weapon state required for CCD,
//! advances the bilateral reducer, and can reduce exactly two 120 Hz steps into
//! the explicit truth packet for one 60 Hz action tick.

use glam::Mat4;

use crate::duel_physics::{
    Fighter, FighterPhysicsInput, SharedDuelPhysics, SharedPhysicsError, SharedPhysicsInput,
    SharedPhysicsStep, TruthBridgeError, physical_contact_batch,
};
use crate::hitbox::{HitboxProxy, extract_weapon_proxy};
use crate::truth::PhysicalContactBatch;

/// External physical target state for one fighter at one 120 Hz substep.
///
/// `body_proxies` must come from the shared physical world. Renderer skinning
/// matrices and sampled/generated animation poses are not valid substitutes.
#[derive(Debug, Clone, Copy)]
pub struct FighterWorldTarget<'a> {
    pub weapon_transform: Mat4,
    pub guard_proxies: &'a [HitboxProxy],
    pub body_proxies: &'a [HitboxProxy],
}

/// Both fighters' targets sampled for the same shared 120 Hz substep.
#[derive(Debug, Clone, Copy)]
pub struct DuelWorldTarget<'a> {
    pub player: FighterWorldTarget<'a>,
    pub opponent: FighterWorldTarget<'a>,
}

/// A complete measured action-tick interval: two shared substeps plus the
/// resulting contact batch that may be submitted to `CombatTruth`.
#[derive(Debug, Clone)]
pub struct DuelWorldTruthTick {
    pub first: SharedPhysicsStep,
    pub second: SharedPhysicsStep,
    pub contact_batch: PhysicalContactBatch,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DuelWorldError {
    NonFiniteWeaponTransform { fighter: Fighter },
    NonFiniteBodyProxy { fighter: Fighter, index: usize },
    SharedPhysics(SharedPhysicsError),
    TruthBridge(TruthBridgeError),
}

/// Single-writer kinematic state required to make weapon CCD continuous across
/// externally supplied target frames.
#[derive(Debug, Default)]
pub struct DuelWorld {
    physics: SharedDuelPhysics,
    previous_player_weapon: Option<HitboxProxy>,
    previous_opponent_weapon: Option<HitboxProxy>,
}

impl DuelWorld {
    pub const fn new() -> Self {
        Self {
            physics: SharedDuelPhysics::new(),
            previous_player_weapon: None,
            previous_opponent_weapon: None,
        }
    }

    pub const fn next_physics_tick(&self) -> u64 {
        self.physics.next_physics_tick()
    }

    /// Clears swept-weapon history without changing the monotonic physics tick.
    /// Use only at a deterministic episode boundary before submitting targets
    /// for the next episode.
    pub fn clear_weapon_history(&mut self) {
        self.previous_player_weapon = None;
        self.previous_opponent_weapon = None;
    }

    /// Advance one measured 120 Hz shared physics substep.
    pub fn step(
        &mut self,
        target: DuelWorldTarget<'_>,
    ) -> Result<SharedPhysicsStep, DuelWorldError> {
        validate_target(Fighter::Player, target.player)?;
        validate_target(Fighter::Opponent, target.opponent)?;

        let player_current = extract_weapon_proxy(&target.player.weapon_transform);
        let opponent_current = extract_weapon_proxy(&target.opponent.weapon_transform);
        let player_previous = self
            .previous_player_weapon
            .as_ref()
            .unwrap_or(&player_current);
        let opponent_previous = self
            .previous_opponent_weapon
            .as_ref()
            .unwrap_or(&opponent_current);

        let step = self
            .physics
            .step(SharedPhysicsInput {
                player: FighterPhysicsInput {
                    previous_weapon: std::slice::from_ref(player_previous),
                    current_weapon: std::slice::from_ref(&player_current),
                    current_guard: target.player.guard_proxies,
                    current_body: target.player.body_proxies,
                },
                opponent: FighterPhysicsInput {
                    previous_weapon: std::slice::from_ref(opponent_previous),
                    current_weapon: std::slice::from_ref(&opponent_current),
                    current_guard: target.opponent.guard_proxies,
                    current_body: target.opponent.body_proxies,
                },
            })
            .map_err(DuelWorldError::SharedPhysics)?;

        self.previous_player_weapon = Some(player_current);
        self.previous_opponent_weapon = Some(opponent_current);
        Ok(step)
    }

    /// Advance exactly one 60 Hz truth interval from two externally measured
    /// 120 Hz targets. Both targets are validated before either substep can
    /// mutate the world clock or previous-weapon history.
    pub fn step_truth_tick(
        &mut self,
        truth_frame: u32,
        first_target: DuelWorldTarget<'_>,
        second_target: DuelWorldTarget<'_>,
    ) -> Result<DuelWorldTruthTick, DuelWorldError> {
        validate_target(Fighter::Player, first_target.player)?;
        validate_target(Fighter::Opponent, first_target.opponent)?;
        validate_target(Fighter::Player, second_target.player)?;
        validate_target(Fighter::Opponent, second_target.opponent)?;

        let first = self.step(first_target)?;
        let second = self.step(second_target)?;
        let contact_batch = physical_contact_batch(truth_frame, &first, &second)
            .map_err(DuelWorldError::TruthBridge)?;
        Ok(DuelWorldTruthTick {
            first,
            second,
            contact_batch,
        })
    }
}

fn validate_target(fighter: Fighter, target: FighterWorldTarget<'_>) -> Result<(), DuelWorldError> {
    if !target
        .weapon_transform
        .to_cols_array()
        .iter()
        .all(|value| value.is_finite())
    {
        return Err(DuelWorldError::NonFiniteWeaponTransform { fighter });
    }
    for (index, proxy) in target.body_proxies.iter().enumerate() {
        if !proxy.world_aabb.min.is_finite() || !proxy.world_aabb.max.is_finite() {
            return Err(DuelWorldError::NonFiniteBodyProxy { fighter, index });
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use glam::{Mat4, Vec3, Vec4, vec3};

    use super::*;
    use crate::hitbox::{Aabb, DamageType, ProxyRole};

    fn body_proxy(center: Vec3) -> HitboxProxy {
        let extents = Vec3::ONE;
        let half = extents * 0.5;
        HitboxProxy {
            bone_index: 0,
            local_aabb: Aabb::from_extents(extents),
            world_transform: Mat4::from_translation(center),
            damage_type: DamageType::Bash,
            role: ProxyRole::Body,
            world_aabb: Aabb {
                min: center - half,
                max: center + half,
            },
        }
    }

    fn target<'a>(
        player_weapon_x: f32,
        opponent_weapon_x: f32,
        player_body: &'a [HitboxProxy],
        opponent_body: &'a [HitboxProxy],
    ) -> DuelWorldTarget<'a> {
        DuelWorldTarget {
            player: FighterWorldTarget {
                weapon_transform: Mat4::from_translation(vec3(player_weapon_x, 0.0, 0.0)),
                guard_proxies: &[],
                body_proxies: player_body,
            },
            opponent: FighterWorldTarget {
                weapon_transform: Mat4::from_translation(vec3(opponent_weapon_x, 0.0, 0.0)),
                guard_proxies: &[],
                body_proxies: opponent_body,
            },
        }
    }

    #[test]
    fn target_pair_emits_one_truth_packet_from_two_substeps() {
        let player_body = [body_proxy(vec3(10.0, 0.0, 0.0))];
        let opponent_body = [body_proxy(Vec3::ZERO)];
        let mut world = DuelWorld::new();

        let result = world
            .step_truth_tick(
                77,
                target(-2.0, 10.0, &player_body, &opponent_body),
                target(2.0, 10.0, &player_body, &opponent_body),
            )
            .unwrap();

        assert_eq!(
            (result.first.physics_tick, result.first.action_tick),
            (0, 0)
        );
        assert_eq!(
            (result.second.physics_tick, result.second.action_tick),
            (1, 0)
        );
        assert!(!result.first.contacts.is_empty() || !result.second.contacts.is_empty());
        assert_eq!(result.contact_batch.truth_frame, 77);
        assert!(result.contact_batch.contact.is_some());
    }

    #[test]
    fn no_observed_contact_emits_an_explicit_whiff() {
        let player_body = [body_proxy(vec3(-10.0, 0.0, 0.0))];
        let opponent_body = [body_proxy(vec3(10.0, 0.0, 0.0))];
        let mut world = DuelWorld::new();

        let result = world
            .step_truth_tick(
                5,
                target(-2.0, 2.0, &player_body, &opponent_body),
                target(-1.0, 1.0, &player_body, &opponent_body),
            )
            .unwrap();

        assert_eq!(result.contact_batch.contact, None);
        assert_eq!(world.next_physics_tick(), 2);
    }

    #[test]
    fn non_finite_target_does_not_advance_the_world() {
        let mut world = DuelWorld::new();
        let invalid = DuelWorldTarget {
            player: FighterWorldTarget {
                weapon_transform: Mat4::from_cols(Vec4::NAN, Vec4::Y, Vec4::Z, Vec4::W),
                guard_proxies: &[],
                body_proxies: &[],
            },
            opponent: FighterWorldTarget {
                weapon_transform: Mat4::IDENTITY,
                guard_proxies: &[],
                body_proxies: &[],
            },
        };

        assert_eq!(
            world.step(invalid).unwrap_err(),
            DuelWorldError::NonFiniteWeaponTransform {
                fighter: Fighter::Player,
            }
        );
        assert_eq!(world.next_physics_tick(), 0);
    }

    #[test]
    fn identical_external_targets_reproduce_packet_presence() {
        let player_body = [body_proxy(vec3(10.0, 0.0, 0.0))];
        let opponent_body = [body_proxy(Vec3::ZERO)];
        let first = target(-2.0, 10.0, &player_body, &opponent_body);
        let second = target(2.0, 10.0, &player_body, &opponent_body);
        let mut left = DuelWorld::new();
        let mut right = DuelWorld::new();

        let left_result = left.step_truth_tick(11, first, second).unwrap();
        let right_result = right.step_truth_tick(11, first, second).unwrap();

        assert_eq!(left_result.contact_batch, right_result.contact_batch);
        assert_eq!(
            left_result.first.contacts.len(),
            right_result.first.contacts.len()
        );
        assert_eq!(
            left_result.second.contacts.len(),
            right_result.second.contacts.len()
        );
    }

    #[test]
    fn measured_world_packet_is_accepted_by_resolving_truth() {
        let player_body = [body_proxy(vec3(10.0, 0.0, 0.0))];
        let opponent_body = [body_proxy(Vec3::ZERO)];
        let mut truth = crate::truth::CombatTruth::new();
        for _ in 0..110 {
            truth.tick();
        }
        let truth_frame = truth.expected_contact_frame().unwrap();

        let packet = DuelWorld::new()
            .step_truth_tick(
                truth_frame,
                target(-2.0, 10.0, &player_body, &opponent_body),
                target(2.0, 10.0, &player_body, &opponent_body),
            )
            .unwrap()
            .contact_batch;
        truth.submit_physical_contact(packet).unwrap();
        truth.tick();

        assert!(truth.snapshot().last_contact.is_some());
    }
}
