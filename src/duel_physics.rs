//! Deterministic shared-world contact reduction at 120 Hz.
//!
//! This module has no renderer, motion-model, or action-outcome dependency.
//! It accepts measured proxy state, preserves contact roles, and produces a
//! canonical physical packet for the 60 Hz truth state machine.

use std::cmp::Ordering;

#[cfg(test)]
use glam::{Mat4, Vec3, vec3};

use crate::hitbox::{ContactGeometry, HitboxProxy, ProxyRole, swept_contacts};
use crate::truth::{
    ContactGeometry as TruthContactGeometry, ContactSurface, PhysicalContactBatch, Side,
};

pub const PHYSICS_TICKS_PER_SECOND: u64 = 120;
pub const PHYSICS_TICKS_PER_ACTION_TICK: u64 = 2;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Fighter {
    Player,
    Opponent,
}

impl Fighter {
    const fn other(self) -> Self {
        match self {
            Self::Player => Self::Opponent,
            Self::Opponent => Self::Player,
        }
    }

    pub const fn to_side(self) -> Side {
        match self {
            Self::Player => Side::Player,
            Self::Opponent => Side::Opponent,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct FighterPhysicsInput<'a> {
    pub previous_weapon: &'a [HitboxProxy],
    pub current_weapon: &'a [HitboxProxy],
    /// Measured defensive interaction volumes, such as a weapon guard.
    pub current_guard: &'a [HitboxProxy],
    pub current_body: &'a [HitboxProxy],
}

#[derive(Debug, Clone, Copy)]
pub struct SharedPhysicsInput<'a> {
    pub player: FighterPhysicsInput<'a>,
    pub opponent: FighterPhysicsInput<'a>,
}

#[derive(Debug, Clone)]
pub struct BilateralContact {
    pub attacker: Fighter,
    pub defender: Fighter,
    pub attacker_role: ProxyRole,
    pub defender_role: ProxyRole,
    pub geometry: ContactGeometry,
}

#[derive(Debug, Clone)]
pub struct SharedPhysicsStep {
    pub physics_tick: u64,
    pub action_tick: u64,
    pub contacts: Vec<BilateralContact>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PhysicsInputKind {
    PreviousWeapon,
    CurrentWeapon,
    CurrentGuard,
    CurrentBody,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SharedPhysicsError {
    NonFiniteProxy {
        fighter: Fighter,
        kind: PhysicsInputKind,
        index: usize,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TruthBridgeError {
    NonConsecutivePhysicsTicks { first: u64, second: u64 },
    MismatchedActionTicks { first: u64, second: u64 },
}

#[derive(Debug, Default, Clone)]
pub struct SharedDuelPhysics {
    next_physics_tick: u64,
}

impl SharedDuelPhysics {
    pub const fn new() -> Self {
        Self {
            next_physics_tick: 0,
        }
    }

    pub const fn next_physics_tick(&self) -> u64 {
        self.next_physics_tick
    }

    /// Advance exactly one 120 Hz shared physics step.
    pub fn step(
        &mut self,
        input: SharedPhysicsInput<'_>,
    ) -> Result<SharedPhysicsStep, SharedPhysicsError> {
        validate_fighter_input(Fighter::Player, input.player)?;
        validate_fighter_input(Fighter::Opponent, input.opponent)?;

        let physics_tick = self.next_physics_tick;
        self.next_physics_tick = self
            .next_physics_tick
            .checked_add(1)
            .expect("physics tick counter overflowed");

        let mut contacts = Vec::new();
        collect_directional_contacts(
            &mut contacts,
            Fighter::Player,
            input.player,
            input.opponent.current_guard,
            input.opponent.current_body,
        );
        collect_directional_contacts(
            &mut contacts,
            Fighter::Opponent,
            input.opponent,
            input.player.current_guard,
            input.player.current_body,
        );
        contacts.sort_by(canonical_contact_order);

        Ok(SharedPhysicsStep {
            physics_tick,
            action_tick: physics_tick / PHYSICS_TICKS_PER_ACTION_TICK,
            contacts,
        })
    }
}

/// Reduce exactly one measured 60 Hz interval into an explicit truth packet.
/// Equal-time guard contacts outrank body contacts, preventing a sword from
/// reporting a through-guard body hit on the same measured boundary.
pub fn physical_contact_batch(
    truth_frame: u32,
    first: &SharedPhysicsStep,
    second: &SharedPhysicsStep,
) -> Result<PhysicalContactBatch, TruthBridgeError> {
    if first.physics_tick.checked_add(1) != Some(second.physics_tick) {
        return Err(TruthBridgeError::NonConsecutivePhysicsTicks {
            first: first.physics_tick,
            second: second.physics_tick,
        });
    }
    if first.action_tick != second.action_tick {
        return Err(TruthBridgeError::MismatchedActionTicks {
            first: first.action_tick,
            second: second.action_tick,
        });
    }

    let contacts = || first.contacts.iter().chain(second.contacts.iter());
    let reduce = |fighter| {
        contacts()
            .filter(|contact| contact.attacker == fighter)
            .min_by(semantic_contact_order)
            .map(|contact| TruthContactGeometry {
                distance: 0.0,
                in_range: true,
                attacker: contact.attacker.to_side(),
                surface: match contact.defender_role {
                    ProxyRole::WeaponGuard => ContactSurface::Guard,
                    ProxyRole::Body | ProxyRole::WeaponEdge => ContactSurface::Body,
                },
            })
    };
    let player_contact = reduce(Fighter::Player);
    let opponent_contact = reduce(Fighter::Opponent);
    Ok(PhysicalContactBatch {
        truth_frame,
        contact: player_contact.or(opponent_contact),
        opposing_contact: player_contact.and(opponent_contact),
    })
}

fn collect_directional_contacts(
    contacts: &mut Vec<BilateralContact>,
    attacker: Fighter,
    attacker_input: FighterPhysicsInput<'_>,
    defender_guard: &[HitboxProxy],
    defender_body: &[HitboxProxy],
) {
    for defender_proxies in [defender_guard, defender_body] {
        for geometry in swept_contacts(
            attacker_input.previous_weapon,
            attacker_input.current_weapon,
            defender_proxies,
        ) {
            contacts.push(BilateralContact {
                attacker,
                defender: attacker.other(),
                attacker_role: attacker_input.current_weapon[geometry.attacker_proxy].role,
                defender_role: defender_proxies[geometry.defender_proxy].role,
                geometry,
            });
        }
    }
}

fn canonical_contact_order(left: &BilateralContact, right: &BilateralContact) -> Ordering {
    left.geometry
        .time_of_impact
        .total_cmp(&right.geometry.time_of_impact)
        .then_with(|| left.attacker.cmp(&right.attacker))
        .then_with(|| left.defender.cmp(&right.defender))
        .then_with(|| left.defender_role.cmp(&right.defender_role))
        .then_with(|| {
            left.geometry
                .attacker_proxy
                .cmp(&right.geometry.attacker_proxy)
        })
        .then_with(|| {
            left.geometry
                .defender_proxy
                .cmp(&right.geometry.defender_proxy)
        })
}

fn semantic_contact_order(left: &&BilateralContact, right: &&BilateralContact) -> Ordering {
    left.geometry
        .time_of_impact
        .total_cmp(&right.geometry.time_of_impact)
        .then_with(|| role_rank(left.defender_role).cmp(&role_rank(right.defender_role)))
        .then_with(|| canonical_contact_order(left, right))
}

const fn role_rank(role: ProxyRole) -> u8 {
    match role {
        ProxyRole::WeaponGuard => 0,
        ProxyRole::Body => 1,
        ProxyRole::WeaponEdge => 2,
    }
}

fn validate_fighter_input(
    fighter: Fighter,
    input: FighterPhysicsInput<'_>,
) -> Result<(), SharedPhysicsError> {
    validate_proxies(
        fighter,
        PhysicsInputKind::PreviousWeapon,
        input.previous_weapon,
    )?;
    validate_proxies(
        fighter,
        PhysicsInputKind::CurrentWeapon,
        input.current_weapon,
    )?;
    validate_proxies(fighter, PhysicsInputKind::CurrentGuard, input.current_guard)?;
    validate_proxies(fighter, PhysicsInputKind::CurrentBody, input.current_body)
}

fn validate_proxies(
    fighter: Fighter,
    kind: PhysicsInputKind,
    proxies: &[HitboxProxy],
) -> Result<(), SharedPhysicsError> {
    for (index, proxy) in proxies.iter().enumerate() {
        if !proxy.world_aabb.min.is_finite() || !proxy.world_aabb.max.is_finite() {
            return Err(SharedPhysicsError::NonFiniteProxy {
                fighter,
                kind,
                index,
            });
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hitbox::{Aabb, DamageType};

    fn proxy(center: Vec3, full_extents: Vec3, role: ProxyRole) -> HitboxProxy {
        let half = full_extents * 0.5;
        HitboxProxy {
            bone_index: 0,
            local_aabb: Aabb::from_extents(full_extents),
            world_transform: Mat4::from_translation(center),
            damage_type: DamageType::Slash,
            role,
            world_aabb: Aabb {
                min: center - half,
                max: center + half,
            },
        }
    }

    fn empty() -> FighterPhysicsInput<'static> {
        FighterPhysicsInput {
            previous_weapon: &[],
            current_weapon: &[],
            current_guard: &[],
            current_body: &[],
        }
    }

    fn step(tick: u64, contacts: Vec<BilateralContact>) -> SharedPhysicsStep {
        SharedPhysicsStep {
            physics_tick: tick,
            action_tick: tick / 2,
            contacts,
        }
    }

    fn measured(
        attacker: Fighter,
        defender_role: ProxyRole,
        time_of_impact: f32,
    ) -> BilateralContact {
        BilateralContact {
            attacker,
            defender: attacker.other(),
            attacker_role: ProxyRole::WeaponEdge,
            defender_role,
            geometry: ContactGeometry {
                point: Vec3::ZERO,
                normal: Vec3::X,
                depth: 0.0,
                time_of_impact,
                attacker_proxy: 0,
                defender_proxy: 0,
            },
        }
    }

    #[test]
    fn maps_two_physics_steps_to_one_action_tick() {
        let mut physics = SharedDuelPhysics::new();
        let input = SharedPhysicsInput {
            player: empty(),
            opponent: empty(),
        };
        let first = physics.step(input).unwrap();
        let second = physics.step(input).unwrap();
        assert_eq!((first.physics_tick, first.action_tick), (0, 0));
        assert_eq!((second.physics_tick, second.action_tick), (1, 0));
    }

    #[test]
    fn guard_feature_blocks_even_when_body_contact_is_equally_early() {
        let body = measured(Fighter::Player, ProxyRole::Body, 0.25);
        let guard = measured(Fighter::Player, ProxyRole::WeaponGuard, 0.25);
        let packet =
            physical_contact_batch(7, &step(0, vec![body, guard]), &step(1, vec![])).unwrap();
        assert_eq!(
            packet.contact,
            Some(TruthContactGeometry {
                distance: 0.0,
                in_range: true,
                attacker: Side::Player,
                surface: ContactSurface::Guard,
            })
        );
    }

    #[test]
    fn reducer_preserves_one_contact_per_attacker_in_a_bilateral_truth_tick() {
        let player = measured(Fighter::Player, ProxyRole::Body, 0.25);
        let opponent = measured(Fighter::Opponent, ProxyRole::Body, 0.10);
        let packet =
            physical_contact_batch(8, &step(0, vec![opponent, player]), &step(1, vec![])).unwrap();

        assert_eq!(packet.contact.unwrap().attacker, Side::Player);
        assert_eq!(packet.opposing_contact.unwrap().attacker, Side::Opponent);
    }

    #[test]
    fn reducer_preserves_guard_and_body_roles_from_measured_proxies() {
        let previous_weapon = [proxy(
            vec3(-2.0, 0.0, 0.0),
            vec3(0.1, 0.1, 0.1),
            ProxyRole::WeaponEdge,
        )];
        let current_weapon = [proxy(
            vec3(2.0, 0.0, 0.0),
            vec3(0.1, 0.1, 0.1),
            ProxyRole::WeaponEdge,
        )];
        let guard = [proxy(Vec3::ZERO, Vec3::ONE, ProxyRole::WeaponGuard)];
        let mut physics = SharedDuelPhysics::new();
        let result = physics
            .step(SharedPhysicsInput {
                player: FighterPhysicsInput {
                    previous_weapon: &previous_weapon,
                    current_weapon: &current_weapon,
                    current_guard: &[],
                    current_body: &[],
                },
                opponent: FighterPhysicsInput {
                    previous_weapon: &[],
                    current_weapon: &[],
                    current_guard: &guard,
                    current_body: &[],
                },
            })
            .unwrap();
        assert_eq!(result.contacts.len(), 1);
        assert_eq!(result.contacts[0].defender_role, ProxyRole::WeaponGuard);
    }

    #[test]
    fn rejects_non_finite_guard_before_advancing() {
        let invalid = [proxy(
            Vec3::new(f32::NAN, 0.0, 0.0),
            Vec3::ONE,
            ProxyRole::WeaponGuard,
        )];
        let mut physics = SharedDuelPhysics::new();
        let error = physics
            .step(SharedPhysicsInput {
                player: empty(),
                opponent: FighterPhysicsInput {
                    current_guard: &invalid,
                    ..empty()
                },
            })
            .unwrap_err();
        assert_eq!(
            error,
            SharedPhysicsError::NonFiniteProxy {
                fighter: Fighter::Opponent,
                kind: PhysicsInputKind::CurrentGuard,
                index: 0
            }
        );
        assert_eq!(physics.next_physics_tick(), 0);
    }
}
