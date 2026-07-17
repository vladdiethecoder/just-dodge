//! Simultaneous-lock, goal-directed planning authority for the clean intent loop.
//!
//! Positions and ballistic state are integer millimetres. `glam` values are
//! created only at the measured `DuelWorld` boundary, then discarded; no float
//! result is admitted back into plan state.

use glam::{Vec3, vec3};
use serde::{Deserialize, Serialize};

use crate::cleanbox::action_frame;
use crate::duel_physics::Fighter;
use crate::duel_world::{DuelWorld, DuelWorldError, DuelWorldTarget};
use crate::truth::{Action, PhysicalContactBatch, Side};

use super::clinch::{self, ClinchResolution, ClinchState};
use super::combo::{AirState, ComboState};
use super::intent::{Intent, MoveDirection, StrikeVariant};

/// Root-space distance at which an unarmed grab becomes a clinch.
pub const GRAB_REACH_MM: i32 = 650;
/// Maximum deterministic root translation in one 60 Hz truth tick.
pub const ROOT_SPEED_MM_PER_TICK: i32 = 100;
/// Fixed recovery attached to an explicit cancel.
pub const CANCEL_PENALTY_FRAMES: u16 = 8;

/// A root coordinate quantized to whole millimetres at every state boundary.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct RootPosition {
    pub x_mm: i32,
    pub y_mm: i32,
    pub z_mm: i32,
}

impl RootPosition {
    pub const fn new(x_mm: i32, y_mm: i32, z_mm: i32) -> Self {
        Self { x_mm, y_mm, z_mm }
    }

    fn as_world_vec3(self) -> Vec3 {
        vec3(
            self.x_mm as f32 / 1000.0,
            self.y_mm as f32 / 1000.0,
            self.z_mm as f32 / 1000.0,
        )
    }
}

/// Current external state of the plan authority. `Planning` is the frozen
/// boundary: no truth tick advances until both next intents are supplied.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PlanStatus {
    Planning,
    Executing { frames_remaining: u16 },
}

/// Why a locked goal was returned to the chooser instead of becoming a whiff.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RepromptReason {
    GoalOutOfReach,
    GoalLostAtBoundary,
    ClinchRequired,
}

/// Non-committal responses available after a failed goal feasibility check.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RepromptOption {
    Continue,
    Feint,
    Cancel,
}

pub const REPROMPT_OPTIONS: [RepromptOption; 3] = [
    RepromptOption::Continue,
    RepromptOption::Feint,
    RepromptOption::Cancel,
];

/// Observable state-machine events emitted in deterministic fighter order.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PlanEvent {
    Locked {
        side: Side,
        intent: Intent,
    },
    Reprompt {
        side: Side,
        reason: RepromptReason,
        options: [RepromptOption; 3],
    },
    Feinted {
        side: Side,
    },
    Cancelled {
        side: Side,
        penalty_frames: u16,
    },
    ClinchEnter {
        initiator: Side,
    },
    ClinchExit {
        escaped_by: Side,
    },
}

/// A replay-hashable plan snapshot. The measured world packet is reduced to its
/// semantic presence so IEEE float payloads never become state-hash input.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct PlanSnapshot {
    pub truth_frame: u64,
    pub status: PlanStatus,
    pub roots: [RootPosition; 2],
    pub locked: [Option<Intent>; 2],
    pub recovery_frames: [u16; 2],
    pub combos: [ComboState; 2],
    pub clinch: Option<ClinchState>,
    pub last_contact_observed: bool,
}

/// Errors that prevent an external controller from mutating plan state.
#[derive(Debug)]
pub enum PlanError {
    NotPlanning,
    MissingIntent,
    ClinchIntentRequired,
    DuelWorld(DuelWorldError),
}

/// New clean simultaneous-lock game loop. This deliberately does not mutate
/// milestone3 state; it only adapts its measured physics/truth primitives.
#[derive(Debug)]
pub struct PlanPhase {
    status: PlanStatus,
    roots: [RootPosition; 2],
    submitted: [Option<Intent>; 2],
    locked: [Option<Intent>; 2],
    recovery_frames: [u16; 2],
    combos: [ComboState; 2],
    clinch: Option<ClinchState>,
    truth_frame: u64,
    last_contact_observed: bool,
    duel_world: DuelWorld,
}

impl Default for PlanPhase {
    fn default() -> Self {
        Self::new()
    }
}

impl PlanPhase {
    pub const fn new() -> Self {
        Self::with_roots(
            RootPosition::new(0, 0, 1000),
            RootPosition::new(0, 0, -1000),
        )
    }

    pub const fn with_roots(player: RootPosition, opponent: RootPosition) -> Self {
        Self {
            status: PlanStatus::Planning,
            roots: [player, opponent],
            submitted: [None, None],
            locked: [None, None],
            recovery_frames: [0, 0],
            combos: [ComboState {
                last_intent: None,
                cancel_window_frames: 0,
                air: AirState::Grounded,
            }; 2],
            clinch: None,
            truth_frame: 0,
            last_contact_observed: false,
            duel_world: DuelWorld::new(),
        }
    }

    pub const fn status(&self) -> PlanStatus {
        self.status
    }

    pub const fn root(&self, side: Side) -> RootPosition {
        self.roots[side_index(side)]
    }

    pub const fn recovery_frames(&self, side: Side) -> u16 {
        self.recovery_frames[side_index(side)]
    }

    pub const fn combo_state(&self, side: Side) -> ComboState {
        self.combos[side_index(side)]
    }

    pub const fn clinch(&self) -> Option<ClinchState> {
        self.clinch
    }

    /// Test/replay hook for deterministic launch reconstruction.
    pub fn set_air_state(&mut self, side: Side, air: AirState) {
        self.combos[side_index(side)].air = air;
    }

    pub fn snapshot(&self) -> PlanSnapshot {
        PlanSnapshot {
            truth_frame: self.truth_frame,
            status: self.status,
            roots: self.roots,
            locked: self.locked,
            recovery_frames: self.recovery_frames,
            combos: self.combos,
            clinch: self.clinch,
            last_contact_observed: self.last_contact_observed,
        }
    }

    /// Canonical FNV-1a hash over postcard's deterministic encoding of integer
    /// plan state. The hash can be recorded beside existing truth replay hashes.
    pub fn truth_hash(&self) -> u64 {
        let bytes = postcard::to_allocvec(&self.snapshot())
            .expect("plan snapshot contains only serializable fixed-point state");
        fnv1a(&bytes)
    }

    /// Supply one side's intent. Once both sides have supplied a feasible intent,
    /// both are locked atomically and the caller can advance measured truth ticks.
    pub fn submit_intent(
        &mut self,
        side: Side,
        intent: Intent,
    ) -> Result<Vec<PlanEvent>, PlanError> {
        if self.status != PlanStatus::Planning {
            return Err(PlanError::NotPlanning);
        }
        if self.clinch.is_some() && !matches!(intent, Intent::Clinch { .. }) {
            return Ok(vec![PlanEvent::Reprompt {
                side,
                reason: RepromptReason::ClinchRequired,
                options: REPROMPT_OPTIONS,
            }]);
        }
        if self.clinch.is_none() && matches!(intent, Intent::Clinch { .. }) {
            return Err(PlanError::ClinchIntentRequired);
        }

        self.submitted[side_index(side)] = Some(intent);
        if self.submitted.iter().any(Option::is_none) {
            return Ok(Vec::new());
        }
        self.lock_submitted()
    }

    /// Advance exactly one authoritative 60 Hz truth tick. It advances the
    /// measured `DuelWorld` by its required two 120 Hz substeps.
    pub fn step_truth_tick(&mut self) -> Result<Vec<PlanEvent>, PlanError> {
        let frames_remaining = match self.status {
            PlanStatus::Planning => return Err(PlanError::NotPlanning),
            PlanStatus::Executing { frames_remaining } => frames_remaining,
        };
        let intents = self.locked_intents()?;
        self.advance_roots(intents);

        let player_action = action_for(intents[side_index(Side::Player)]);
        let opponent_action = action_for(intents[side_index(Side::Opponent)]);
        let player_root = self.roots[side_index(Side::Player)].as_world_vec3();
        let opponent_root = self.roots[side_index(Side::Opponent)].as_world_vec3();
        let player_first = action_frame(Fighter::Player, player_action, player_root, 0);
        let opponent_first = action_frame(Fighter::Opponent, opponent_action, opponent_root, 0);
        let player_second = action_frame(Fighter::Player, player_action, player_root, 1);
        let opponent_second = action_frame(Fighter::Opponent, opponent_action, opponent_root, 1);
        let measured = self
            .duel_world
            .step_truth_tick(
                self.truth_frame as u32,
                DuelWorldTarget {
                    player: player_first.as_target(),
                    opponent: opponent_first.as_target(),
                },
                DuelWorldTarget {
                    player: player_second.as_target(),
                    opponent: opponent_second.as_target(),
                },
            )
            .map_err(PlanError::DuelWorld)?;
        self.last_contact_observed = measured.contact_batch.contact.is_some();
        self.apply_contact_outcomes(&measured.contact_batch, intents);
        self.truth_frame = self.truth_frame.saturating_add(1);

        let remaining = frames_remaining - 1;
        self.status = PlanStatus::Executing {
            frames_remaining: remaining,
        };
        if remaining == 0 {
            return Ok(self.finish_boundary(intents));
        }
        Ok(Vec::new())
    }

    /// Simulate the locked forecast through its next frozen plan boundary.
    pub fn simulate_to_boundary(&mut self) -> Result<Vec<PlanEvent>, PlanError> {
        let mut events = Vec::new();
        while matches!(self.status, PlanStatus::Executing { .. }) {
            events.extend(self.step_truth_tick()?);
        }
        Ok(events)
    }

    fn lock_submitted(&mut self) -> Result<Vec<PlanEvent>, PlanError> {
        let intents = self.submitted_intents()?;
        let mut events = Vec::new();
        for side in [Side::Player, Side::Opponent] {
            let intent = intents[side_index(side)];
            if !self.is_feasible(side, intent, intent.frame_cost()) {
                events.push(PlanEvent::Reprompt {
                    side,
                    reason: RepromptReason::GoalOutOfReach,
                    options: REPROMPT_OPTIONS,
                });
            }
        }
        if !events.is_empty() {
            self.submitted = [None, None];
            return Ok(events);
        }

        self.locked = self.submitted;
        self.submitted = [None, None];
        let phase_frames = intents[0].frame_cost().min(intents[1].frame_cost());
        self.status = PlanStatus::Executing {
            frames_remaining: phase_frames,
        };
        self.duel_world.clear_weapon_history();
        for side in [Side::Player, Side::Opponent] {
            let intent = intents[side_index(side)];
            self.combos[side_index(side)].lock(intent);
            events.push(PlanEvent::Locked { side, intent });
        }
        Ok(events)
    }

    fn finish_boundary(&mut self, intents: [Intent; 2]) -> Vec<PlanEvent> {
        let mut events = Vec::new();
        for side in [Side::Player, Side::Opponent] {
            match intents[side_index(side)] {
                Intent::Feint => events.push(PlanEvent::Feinted { side }),
                Intent::Cancel => {
                    let recovery = &mut self.recovery_frames[side_index(side)];
                    *recovery = recovery.saturating_add(CANCEL_PENALTY_FRAMES);
                    events.push(PlanEvent::Cancelled {
                        side,
                        penalty_frames: CANCEL_PENALTY_FRAMES,
                    });
                }
                _ => {}
            }
        }

        if let Some(clinch_state) = self.clinch {
            let player = clinch_intent(intents[side_index(Side::Player)]);
            let opponent = clinch_intent(intents[side_index(Side::Opponent)]);
            if let (Some(player), Some(opponent)) = (player, opponent) {
                match clinch::resolve(player, opponent) {
                    ClinchResolution::Continue => {}
                    ClinchResolution::Exit { escaped_by } => {
                        self.clinch = None;
                        events.push(PlanEvent::ClinchExit { escaped_by });
                    }
                    ClinchResolution::Launch { launched } => {
                        self.combos[side_index(launched)].launch();
                        let _ = clinch_state;
                    }
                }
            }
        } else if self.within_grab_reach()
            && (intents[side_index(Side::Player)] == Intent::Grab
                || intents[side_index(Side::Opponent)] == Intent::Grab)
        {
            let initiator = if intents[side_index(Side::Player)] == Intent::Grab {
                Side::Player
            } else {
                Side::Opponent
            };
            self.clinch = Some(ClinchState::new(initiator, self.truth_frame));
            events.push(PlanEvent::ClinchEnter { initiator });
        }

        let phase_frames = intents[0].frame_cost().min(intents[1].frame_cost());
        for side in [Side::Player, Side::Opponent] {
            let intent = intents[side_index(side)];
            let remaining = intent.frame_cost().saturating_sub(phase_frames);
            if remaining > 0 && !self.is_feasible(side, intent, remaining) {
                events.push(PlanEvent::Reprompt {
                    side,
                    reason: RepromptReason::GoalLostAtBoundary,
                    options: REPROMPT_OPTIONS,
                });
            }
        }

        self.locked = [None, None];
        self.status = PlanStatus::Planning;
        events
    }

    fn apply_contact_outcomes(&mut self, measured: &PhysicalContactBatch, intents: [Intent; 2]) {
        let Some(contact) = measured.contact else {
            return;
        };
        let attacker = contact.attacker;
        let defender = attacker.opposite();
        if matches!(intents[side_index(attacker)], Intent::Strike { .. })
            && self.combos[side_index(defender)].air.is_airborne()
        {
            // A measured weapon/body contact is the only source permitted to
            // refresh a juggle launch; animation cannot fabricate this outcome.
            self.combos[side_index(defender)].launch();
        }
    }

    fn advance_roots(&mut self, intents: [Intent; 2]) {
        let prior = self.roots;
        let mut next = prior;
        for side in [Side::Player, Side::Opponent] {
            let index = side_index(side);
            let opponent = prior[side_index(side.opposite())];
            next[index] = root_after_intent(prior[index], opponent, intents[index]);
        }
        self.roots = next;
        for side in [Side::Player, Side::Opponent] {
            let index = side_index(side);
            self.combos[index].tick(&mut self.roots[index].y_mm);
            self.recovery_frames[index] = self.recovery_frames[index].saturating_sub(1);
        }
    }

    fn is_feasible(&self, side: Side, intent: Intent, available_frames: u16) -> bool {
        match intent {
            Intent::Grab => {
                let distance = planar_distance_upper_bound(
                    self.roots[side_index(side)],
                    self.roots[side_index(side.opposite())],
                );
                let max_travel = ROOT_SPEED_MM_PER_TICK.saturating_mul(i32::from(available_frames));
                distance <= GRAB_REACH_MM.saturating_add(max_travel)
            }
            Intent::Clinch { .. } => self.clinch.is_some(),
            _ => true,
        }
    }

    fn within_grab_reach(&self) -> bool {
        planar_distance_upper_bound(self.roots[0], self.roots[1]) <= GRAB_REACH_MM
    }

    fn submitted_intents(&self) -> Result<[Intent; 2], PlanError> {
        match self.submitted {
            [Some(player), Some(opponent)] => Ok([player, opponent]),
            _ => Err(PlanError::MissingIntent),
        }
    }

    fn locked_intents(&self) -> Result<[Intent; 2], PlanError> {
        match self.locked {
            [Some(player), Some(opponent)] => Ok([player, opponent]),
            _ => Err(PlanError::MissingIntent),
        }
    }
}

const fn side_index(side: Side) -> usize {
    match side {
        Side::Player => 0,
        Side::Opponent => 1,
    }
}

fn action_for(intent: Intent) -> Action {
    match intent {
        Intent::Strike {
            variant: StrikeVariant::Thrust,
        } => Action::Thrust,
        Intent::Strike {
            variant: StrikeVariant::Slash,
        } => Action::Strike,
        Intent::Block => Action::Block,
        Intent::Dodge { .. } => Action::Dodge,
        Intent::Grab => Action::Grab,
        Intent::Move { .. }
        | Intent::Feint
        | Intent::Cancel
        | Intent::Idle
        | Intent::Clinch { .. } => Action::Block,
    }
}

fn clinch_intent(intent: Intent) -> Option<super::clinch::ClinchIntent> {
    match intent {
        Intent::Clinch { sub } => Some(sub),
        _ => None,
    }
}

fn root_after_intent(root: RootPosition, opponent: RootPosition, intent: Intent) -> RootPosition {
    match intent {
        Intent::Grab => step_toward(root, opponent, GRAB_REACH_MM, ROOT_SPEED_MM_PER_TICK),
        Intent::Move { dir } => step_direction(root, opponent, dir, ROOT_SPEED_MM_PER_TICK),
        Intent::Dodge { dir } => step_direction(root, opponent, dir, ROOT_SPEED_MM_PER_TICK * 2),
        _ => root,
    }
}

fn step_toward(
    root: RootPosition,
    opponent: RootPosition,
    desired_distance: i32,
    max_step: i32,
) -> RootPosition {
    let dx = opponent.x_mm - root.x_mm;
    let dz = opponent.z_mm - root.z_mm;
    let distance = dx.abs().saturating_add(dz.abs());
    let remaining = distance.saturating_sub(desired_distance);
    if remaining == 0 || distance == 0 {
        return root;
    }
    let step = remaining.min(max_step);
    RootPosition {
        x_mm: root.x_mm.saturating_add(dx.saturating_mul(step) / distance),
        y_mm: root.y_mm,
        z_mm: root.z_mm.saturating_add(dz.saturating_mul(step) / distance),
    }
}

fn step_direction(
    root: RootPosition,
    opponent: RootPosition,
    direction: MoveDirection,
    speed: i32,
) -> RootPosition {
    let dx = opponent.x_mm - root.x_mm;
    let dz = opponent.z_mm - root.z_mm;
    let (axis_x, axis_z) = match direction {
        MoveDirection::Approach => (dx.signum(), dz.signum()),
        MoveDirection::Retreat => (-dx.signum(), -dz.signum()),
        MoveDirection::LateralLeft | MoveDirection::CircleCounterClockwise => {
            (-dz.signum(), dx.signum())
        }
        MoveDirection::LateralRight | MoveDirection::CircleClockwise => (dz.signum(), -dx.signum()),
    };
    let divisor = i32::from(axis_x != 0) + i32::from(axis_z != 0);
    if divisor == 0 {
        return root;
    }
    let step = speed / divisor;
    RootPosition {
        x_mm: root.x_mm.saturating_add(axis_x * step),
        y_mm: root.y_mm,
        z_mm: root.z_mm.saturating_add(axis_z * step),
    }
}

fn planar_distance_upper_bound(left: RootPosition, right: RootPosition) -> i32 {
    left.x_mm
        .saturating_sub(right.x_mm)
        .abs()
        .saturating_add(left.z_mm.saturating_sub(right.z_mm).abs())
}

fn fnv1a(bytes: &[u8]) -> u64 {
    const OFFSET: u64 = 0xcbf29ce484222325;
    const PRIME: u64 = 0x00000100000001b3;
    let mut hash = OFFSET;
    for &byte in bytes {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(PRIME);
    }
    hash
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::intent::clinch::ClinchIntent;

    fn lock(phase: &mut PlanPhase, player: Intent, opponent: Intent) -> Vec<PlanEvent> {
        assert!(
            phase
                .submit_intent(Side::Player, player)
                .unwrap()
                .is_empty()
        );
        phase.submit_intent(Side::Opponent, opponent).unwrap()
    }

    #[test]
    fn simultaneous_lock_reproduces_events_and_state_hash() {
        let player = Intent::Move {
            dir: MoveDirection::Approach,
        };
        let opponent = Intent::Dodge {
            dir: MoveDirection::LateralLeft,
        };
        let mut left = PlanPhase::new();
        let mut right = PlanPhase::new();

        let left_lock = lock(&mut left, player, opponent);
        let right_lock = lock(&mut right, player, opponent);
        assert_eq!(left_lock, right_lock);
        assert_eq!(
            left.simulate_to_boundary().unwrap(),
            right.simulate_to_boundary().unwrap()
        );
        assert_eq!(left.snapshot(), right.snapshot());
        assert_eq!(left.truth_hash(), right.truth_hash());
    }

    #[test]
    fn out_of_reach_grab_reprompts_instead_of_locking_a_whiff() {
        let mut phase =
            PlanPhase::with_roots(RootPosition::new(0, 0, 0), RootPosition::new(0, 0, -10_000));
        let events = lock(&mut phase, Intent::Grab, Intent::Idle);
        assert_eq!(phase.status(), PlanStatus::Planning);
        assert!(events.iter().any(|event| {
            matches!(
                event,
                PlanEvent::Reprompt {
                    side: Side::Player,
                    reason: RepromptReason::GoalOutOfReach,
                    ..
                }
            )
        }));
        assert!(
            !events
                .iter()
                .any(|event| matches!(event, PlanEvent::Locked { .. }))
        );
    }

    #[test]
    fn cancel_applies_fixed_recovery_penalty() {
        let mut phase = PlanPhase::new();
        lock(&mut phase, Intent::Cancel, Intent::Idle);
        let events = phase.simulate_to_boundary().unwrap();
        assert_eq!(phase.recovery_frames(Side::Player), CANCEL_PENALTY_FRAMES);
        assert!(events.iter().any(|event| {
            matches!(
                event,
                PlanEvent::Cancelled {
                    side: Side::Player,
                    penalty_frames: CANCEL_PENALTY_FRAMES
                }
            )
        }));
    }

    #[test]
    fn grab_enters_and_tech_escapes_clinch() {
        let mut phase =
            PlanPhase::with_roots(RootPosition::new(0, 0, 300), RootPosition::new(0, 0, -300));
        lock(&mut phase, Intent::Grab, Intent::Idle);
        let enter = phase.simulate_to_boundary().unwrap();
        assert!(
            enter
                .iter()
                .any(|event| matches!(event, PlanEvent::ClinchEnter { .. }))
        );
        assert!(phase.clinch().is_some());

        lock(
            &mut phase,
            Intent::Clinch {
                sub: ClinchIntent::Hold,
            },
            Intent::Clinch {
                sub: ClinchIntent::Tech,
            },
        );
        let exit = phase.simulate_to_boundary().unwrap();
        assert!(exit.iter().any(|event| {
            matches!(
                event,
                PlanEvent::ClinchExit {
                    escaped_by: Side::Opponent
                }
            )
        }));
        assert_eq!(phase.clinch(), None);
    }

    #[test]
    fn measured_airborne_strike_contact_refreshes_juggle_launch() {
        let mut phase =
            PlanPhase::with_roots(RootPosition::new(0, 0, 400), RootPosition::new(0, 0, -400));
        phase.set_air_state(
            Side::Opponent,
            AirState::Launched {
                vertical_velocity_mm_per_tick: 50,
            },
        );
        phase.apply_contact_outcomes(
            &PhysicalContactBatch {
                truth_frame: 0,
                contact: Some(crate::truth::ContactGeometry {
                    distance: 0.0,
                    in_range: true,
                    attacker: Side::Player,
                    surface: crate::truth::ContactSurface::Body,
                }),
            },
            [
                Intent::Strike {
                    variant: StrikeVariant::Thrust,
                },
                Intent::Idle,
            ],
        );
        assert_eq!(
            phase.combo_state(Side::Opponent).air,
            AirState::Launched {
                vertical_velocity_mm_per_tick: super::super::combo::LAUNCH_VELOCITY_MM_PER_TICK,
            }
        );
    }
}
