//! Deterministic kinematic cleanbox targets for the locked first playable slice.
//!
//! These targets are authored collision constraints, not renderer pose samples
//! and not generated motion. They exist only to exercise the 120 Hz shared-world
//! contract for `Longsword / Top / {Thrust, Block, Dodge}`.

use std::f32::consts::PI;

use glam::{Mat4, Vec3, vec3};

use crate::duel_physics::Fighter;
use crate::duel_world::{
    DuelWorld, DuelWorldError, DuelWorldTarget, DuelWorldTruthTick, FighterWorldTarget,
};
use crate::hitbox::{Aabb, DamageType, HitboxProxy, ProxyRole};
use crate::truth::{Action, CombatTruth, ContactSubmissionError, TruthSnapshot};

const TORSO_EXTENTS: Vec3 = vec3(0.60, 0.90, 0.45);
const GUARD_EXTENTS: Vec3 = vec3(0.90, 0.25, 0.12);
const TORSO_HEIGHT: f32 = 1.10;
const GUARD_HEIGHT: f32 = 1.20;
const GUARD_FORWARD_OFFSET: f32 = 0.45;
const DODGE_LATERAL_OFFSET: f32 = 0.80;
const THRUST_REACH: [f32; 2] = [0.90, 1.65];
const READY_REACH: f32 = 0.50;

/// Error from producing or admitting one cleanbox Resolve packet.
#[derive(Debug)]
pub enum CleanboxRuntimeError {
    DuelWorld(DuelWorldError),
    Truth(ContactSubmissionError),
}

/// Submit the exact two 120 Hz cleanbox substeps required for the pending
/// Resolve tick. Returns `None` outside the unresolved Resolve boundary.
pub fn submit_resolve_packet(
    truth: &mut CombatTruth,
    world: &mut DuelWorld,
    player_root: Vec3,
    opponent_root: Vec3,
) -> Result<Option<DuelWorldTruthTick>, CleanboxRuntimeError> {
    let Some(truth_frame) = truth.expected_contact_frame() else {
        return Ok(None);
    };
    let snapshot = truth.snapshot().clone();
    let first = targets_for_substep(&snapshot, player_root, opponent_root, 0);
    let second = targets_for_substep(&snapshot, player_root, opponent_root, 1);

    // A new Resolve is a new deterministic exchange. Do not sweep stale
    // recovery geometry from the prior exchange into this one.
    world.clear_weapon_history();
    let tick = world
        .step_truth_tick(truth_frame, first.as_target(), second.as_target())
        .map_err(CleanboxRuntimeError::DuelWorld)?;
    truth
        .submit_physical_contact(tick.contact_batch)
        .map_err(CleanboxRuntimeError::Truth)?;
    Ok(Some(tick))
}

/// Produce one measured 60 Hz packet from exactly two 120 Hz cleanbox targets
/// without submitting it to a particular combat authority.
pub fn step_actions(
    world: &mut DuelWorld,
    truth_frame: u32,
    player_action: Action,
    opponent_action: Action,
    player_root: Vec3,
    opponent_root: Vec3,
) -> Result<DuelWorldTruthTick, DuelWorldError> {
    let first = CleanboxTargetFrame {
        player: fighter_frame(Fighter::Player, player_action, player_root, 0),
        opponent: fighter_frame(Fighter::Opponent, opponent_action, opponent_root, 0),
    };
    let second = CleanboxTargetFrame {
        player: fighter_frame(Fighter::Player, player_action, player_root, 1),
        opponent: fighter_frame(Fighter::Opponent, opponent_action, opponent_root, 1),
    };
    world.clear_weapon_history();
    world.step_truth_tick(truth_frame, first.as_target(), second.as_target())
}

#[derive(Debug)]
struct CleanboxTargetFrame {
    player: FighterFrame,
    opponent: FighterFrame,
}

impl CleanboxTargetFrame {
    fn as_target(&self) -> DuelWorldTarget<'_> {
        DuelWorldTarget {
            player: self.player.as_target(),
            opponent: self.opponent.as_target(),
        }
    }
}

#[derive(Debug)]
pub struct FighterFrame {
    weapon_transform: Mat4,
    guard_proxies: Vec<HitboxProxy>,
    body_proxies: Vec<HitboxProxy>,
}

impl FighterFrame {
    pub fn measured(
        weapon_transform: Mat4,
        guard_proxies: Vec<HitboxProxy>,
        body_proxies: Vec<HitboxProxy>,
    ) -> Self {
        Self {
            weapon_transform,
            guard_proxies,
            body_proxies,
        }
    }

    pub fn as_target(&self) -> FighterWorldTarget<'_> {
        FighterWorldTarget {
            weapon_transform: self.weapon_transform,
            guard_proxies: &self.guard_proxies,
            body_proxies: &self.body_proxies,
        }
    }
}

fn targets_for_substep(
    snapshot: &TruthSnapshot,
    player_root: Vec3,
    opponent_root: Vec3,
    substep: usize,
) -> CleanboxTargetFrame {
    CleanboxTargetFrame {
        player: fighter_frame(
            Fighter::Player,
            snapshot.player.action.unwrap_or(Action::Block),
            player_root,
            substep,
        ),
        opponent: fighter_frame(
            Fighter::Opponent,
            snapshot.opponent.action.unwrap_or(Action::Block),
            opponent_root,
            substep,
        ),
    }
}

pub fn action_frame(fighter: Fighter, action: Action, root: Vec3, substep: usize) -> FighterFrame {
    fighter_frame(fighter, action, root, substep)
}

fn fighter_frame(fighter: Fighter, action: Action, root: Vec3, substep: usize) -> FighterFrame {
    let forward = forward(fighter);
    let root = root + dodge_offset(fighter, action);
    let reach = match action {
        Action::Thrust => THRUST_REACH[substep],
        Action::Block | Action::Dodge => READY_REACH,
        // Truth prevents these from entering the locked slice. Keep this
        // fallback deterministic if a malformed external snapshot is supplied.
        Action::Strike | Action::Grab => READY_REACH,
    };
    let weapon_center = root + forward * reach + Vec3::Y * GUARD_HEIGHT;
    let weapon_transform = Mat4::from_translation(weapon_center) * weapon_rotation(fighter);
    let body_center = root + Vec3::Y * TORSO_HEIGHT;
    let guard_proxies = (action == Action::Block)
        .then(|| guard_proxy(root + forward * GUARD_FORWARD_OFFSET + Vec3::Y * GUARD_HEIGHT))
        .into_iter()
        .collect();

    FighterFrame {
        weapon_transform,
        guard_proxies,
        body_proxies: vec![body_proxy(body_center)],
    }
}

const fn forward(fighter: Fighter) -> Vec3 {
    match fighter {
        Fighter::Player => vec3(0.0, 0.0, -1.0),
        Fighter::Opponent => vec3(0.0, 0.0, 1.0),
    }
}

fn dodge_offset(fighter: Fighter, action: Action) -> Vec3 {
    if action != Action::Dodge {
        return Vec3::ZERO;
    }
    match fighter {
        Fighter::Player => vec3(DODGE_LATERAL_OFFSET, 0.0, 0.0),
        Fighter::Opponent => vec3(-DODGE_LATERAL_OFFSET, 0.0, 0.0),
    }
}

fn weapon_rotation(fighter: Fighter) -> Mat4 {
    match fighter {
        Fighter::Player => Mat4::from_rotation_y(PI),
        Fighter::Opponent => Mat4::IDENTITY,
    }
}

fn body_proxy(center: Vec3) -> HitboxProxy {
    proxy(center, TORSO_EXTENTS, DamageType::Bash, ProxyRole::Body)
}

fn guard_proxy(center: Vec3) -> HitboxProxy {
    proxy(
        center,
        GUARD_EXTENTS,
        DamageType::Bash,
        ProxyRole::WeaponGuard,
    )
}

fn proxy(center: Vec3, extents: Vec3, damage_type: DamageType, role: ProxyRole) -> HitboxProxy {
    let half = extents * 0.5;
    HitboxProxy {
        bone_index: 0,
        local_aabb: Aabb::from_extents(extents),
        world_transform: Mat4::from_translation(center),
        damage_type,
        role,
        world_aabb: Aabb {
            min: center - half,
            max: center + half,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::truth::{ContactSurface, PlayerInput, Side, Stance};

    const PLAYER_ROOT: Vec3 = vec3(0.0, 0.0, 1.0);
    const OPPONENT_ROOT: Vec3 = vec3(0.0, 0.0, -1.0);

    fn resolving_truth(player_action: Action, opponent_action: Action) -> CombatTruth {
        let mut truth = CombatTruth::new();
        for _ in 0..30 {
            truth.tick();
        }
        truth.apply_input(Side::Player, PlayerInput::SelectAction(player_action));
        truth.apply_input(Side::Player, PlayerInput::SelectStance(Stance::Top));
        truth.apply_input(Side::Player, PlayerInput::Commit);
        truth.apply_input(Side::Opponent, PlayerInput::SelectAction(opponent_action));
        truth.apply_input(Side::Opponent, PlayerInput::SelectStance(Stance::Top));
        truth.apply_input(Side::Opponent, PlayerInput::Commit);
        for _ in 0..80 {
            truth.tick();
        }
        assert_eq!(truth.expected_contact_frame(), Some(111));
        truth
    }

    #[test]
    fn thrust_into_block_produces_a_guard_packet_then_a_beat() {
        let mut truth = resolving_truth(Action::Thrust, Action::Block);
        let mut world = DuelWorld::new();

        let packet = submit_resolve_packet(&mut truth, &mut world, PLAYER_ROOT, OPPONENT_ROOT)
            .unwrap()
            .unwrap();
        assert_eq!(
            packet.contact_batch.contact.unwrap().surface,
            ContactSurface::Guard
        );
        assert_eq!(world.next_physics_tick(), 2);

        truth.tick();
        assert_eq!(
            truth.snapshot().last_contact.unwrap().surface,
            ContactSurface::Guard
        );
        assert!(truth.snapshot().player.stamina < 100.0);
    }

    #[test]
    fn thrust_into_dodge_produces_an_explicit_whiff() {
        let mut truth = resolving_truth(Action::Thrust, Action::Dodge);
        let mut world = DuelWorld::new();

        let packet = submit_resolve_packet(&mut truth, &mut world, PLAYER_ROOT, OPPONENT_ROOT)
            .unwrap()
            .unwrap();
        assert_eq!(packet.contact_batch.contact, None);

        truth.tick();
        assert_eq!(truth.snapshot().last_contact, None);
        assert!(truth.snapshot().player.stamina < 100.0);
    }

    #[test]
    fn identical_locked_inputs_produce_identical_packet_and_truth_hash() {
        let mut left_truth = resolving_truth(Action::Thrust, Action::Block);
        let mut right_truth = resolving_truth(Action::Thrust, Action::Block);
        let mut left_world = DuelWorld::new();
        let mut right_world = DuelWorld::new();

        let left =
            submit_resolve_packet(&mut left_truth, &mut left_world, PLAYER_ROOT, OPPONENT_ROOT)
                .unwrap()
                .unwrap();
        let right = submit_resolve_packet(
            &mut right_truth,
            &mut right_world,
            PLAYER_ROOT,
            OPPONENT_ROOT,
        )
        .unwrap()
        .unwrap();
        assert_eq!(left.contact_batch, right.contact_batch);

        left_truth.tick();
        right_truth.tick();
        assert_eq!(left_truth.truth_hash(), right_truth.truth_hash());
    }
}
