//! Simultaneous-lock, goal-directed planning authority for the clean intent loop.
//!
//! Positions and ballistic state are integer millimetres. `glam` values are
//! created only at the measured `DuelWorld` boundary, then discarded; no float
//! result is admitted back into plan state. A plan window is a live actionability
//! simulation, never `min(frame_cost())`.

use glam::{Vec3, vec3};
use serde::{Deserialize, Serialize};

use crate::cleanbox::action_frame;
use crate::duel_physics::Fighter;
use crate::duel_world::{DuelWorld, DuelWorldError, DuelWorldTarget};
use crate::truth::{Action, PhysicalContactBatch, Side};

use super::clinch::{self, ClinchResolution, ClinchState};
use super::combo::{AirState, ComboState};
use super::intent::{Intent, MoveDirection, StrikeVariant};

/// Root-space distance at which a fighter may begin a grab attempt.
/// This is NOT the secure-grab distance. Secure grab requires physical contact.
pub const GRAB_ACQUIRE_RANGE_MM: i32 = 650;
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
/// boundary: no truth tick advances until all eligible next intents are supplied.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PlanStatus {
    Planning,
    /// `frames_remaining` is retained for API compatibility as a running-phase
    /// sentinel. It is not a predicted window duration and never chooses a
    /// boundary; live actionability events do that.
    Executing {
        frames_remaining: u16,
    },
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

/// The first actionability condition reached by a state in a live forecast.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ActionabilityReason {
    Iasa,
    InterruptFrame,
    AnimationEnd,
    HitCancel,
}

/// Why the non-ready fighter may also supply a next action at a frozen boundary.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum InterruptOfferReason {
    Ioot,
    Feint,
    NegativeOnHit,
}

/// Observable state-machine events emitted in deterministic fighter order.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PlanEvent {
    Locked {
        side: Side,
        intent: Intent,
    },
    /// A fighter's own state reached actionability at this forecast boundary.
    Ready {
        side: Side,
        reason: ActionabilityReason,
    },
    /// The other fighter did not independently become ready, but is allowed to
    /// interrupt because its state is IOOT, a feint, or negative-on-hit.
    InterruptOffer {
        side: Side,
        reason: InterruptOfferReason,
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
    /// Current committed intents, including the busy continuation retained at a
    /// one-sided boundary.
    pub locked: [Option<Intent>; 2],
    pub action_ticks: [u16; 2],
    pub selection_open: [bool; 2],
    pub recovery_frames: [u16; 2],
    pub combos: [ComboState; 2],
    pub clinch: Option<ClinchState>,
    pub last_contact_observed: bool,
}

/// Errors that prevent an external controller from mutating plan state.
#[derive(Debug)]
pub enum PlanError {
    NotPlanning,
    SideBusy,
    MissingIntent,
    ClinchIntentRequired,
    DuelWorld(DuelWorldError),
}

#[derive(Debug, Clone, Copy)]
struct MovementHeading {
    axis_x: i32,
    axis_z: i32,
}

#[derive(Debug, Clone, Copy)]
struct ActiveAction {
    intent: Intent,
    current_tick: u16,
    hit_cancel: bool,
    negative_on_hit: bool,
    remaining_distance_mm: i32,
    locked_heading: MovementHeading,
}

impl ActiveAction {
    fn new(intent: Intent, root: RootPosition, opponent: RootPosition) -> Self {
        let locked_heading = match intent {
            Intent::Move { dir, .. } | Intent::Dodge { dir } => heading_for(root, opponent, dir),
            _ => MovementHeading {
                axis_x: 0,
                axis_z: 0,
            },
        };
        Self {
            intent,
            current_tick: 0,
            hit_cancel: false,
            negative_on_hit: false,
            remaining_distance_mm: intent
                .movement_parameters()
                .map_or(0, |parameters| i32::from(parameters.distance_mm)),
            locked_heading,
        }
    }
}

/// New clean simultaneous-lock game loop. This deliberately does not mutate
/// milestone3 state; it only adapts its measured physics/truth primitives.
#[derive(Debug)]
pub struct PlanPhase {
    status: PlanStatus,
    roots: [RootPosition; 2],
    submitted: [Option<Intent>; 2],
    locked: [Option<Intent>; 2],
    active: [Option<ActiveAction>; 2],
    selection_open: [bool; 2],
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
            active: [None, None],
            selection_open: [true, true],
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

    /// Whether this fighter is ready or conditionally interruptible at the
    /// current frozen boundary. A false value means the fighter remains busy.
    pub fn can_submit_intent(&self, side: Side) -> bool {
        self.status == PlanStatus::Planning && self.selection_open[side_index(side)]
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
            action_ticks: self
                .active
                .map(|action| action.map_or(0, |action| action.current_tick)),
            selection_open: self.selection_open,
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

    /// Supply one side's intent. Once every ready/interrupt-offered side has
    /// supplied an intent, it is locked atomically with any busy continuation.
    pub fn submit_intent(
        &mut self,
        side: Side,
        intent: Intent,
    ) -> Result<Vec<PlanEvent>, PlanError> {
        if self.status != PlanStatus::Planning {
            return Err(PlanError::NotPlanning);
        }
        let index = side_index(side);
        if !self.selection_open[index] {
            return Err(PlanError::SideBusy);
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

        self.submitted[index] = Some(intent);
        if self
            .selection_open
            .iter()
            .enumerate()
            .any(|(index, open)| *open && self.submitted[index].is_none())
        {
            return Ok(Vec::new());
        }
        self.lock_submitted()
    }

    /// Advance exactly one authoritative 60 Hz truth tick. It advances the
    /// measured `DuelWorld` by its required two 120 Hz substeps and freezes only
    /// when a live actionability event is observed.
    pub fn step_truth_tick(&mut self) -> Result<Vec<PlanEvent>, PlanError> {
        let frames_remaining = match self.status {
            PlanStatus::Planning => return Err(PlanError::NotPlanning),
            PlanStatus::Executing { frames_remaining } => frames_remaining,
        };
        let intents = self.active_intents()?;
        self.advance_roots();

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
        self.apply_contact_outcomes(&measured.contact_batch);
        self.truth_frame = self.truth_frame.saturating_add(1);

        let actionability = self.actionability_events();
        self.advance_action_ticks();
        if actionability.iter().any(Option::is_some) {
            return Ok(self.finish_boundary(intents, actionability));
        }

        self.status = PlanStatus::Executing {
            frames_remaining: frames_remaining.saturating_sub(1),
        };
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
        let mut intents = self.active_intents_or_idle();
        let mut events = Vec::new();
        for side in [Side::Player, Side::Opponent] {
            let index = side_index(side);
            if self.selection_open[index] {
                let intent = self.submitted[index].ok_or(PlanError::MissingIntent)?;
                if !self.is_feasible(side, intent, intent.frame_cost()) {
                    events.push(PlanEvent::Reprompt {
                        side,
                        reason: RepromptReason::GoalOutOfReach,
                        options: REPROMPT_OPTIONS,
                    });
                }
                intents[index] = intent;
            }
        }
        if !events.is_empty() {
            self.submitted = [None, None];
            return Ok(events);
        }

        for side in [Side::Player, Side::Opponent] {
            let index = side_index(side);
            if self.selection_open[index] {
                let intent = intents[index];
                self.active[index] = Some(ActiveAction::new(
                    intent,
                    self.roots[index],
                    self.roots[side_index(side.opposite())],
                ));
                self.combos[index].lock(intent);
                events.push(PlanEvent::Locked { side, intent });
            }
        }
        self.locked = self.active.map(|action| action.map(|action| action.intent));
        self.submitted = [None, None];
        self.selection_open = [false, false];
        // Retain the public field without allowing it to participate in window
        // resolution. The authoritative stop condition is `actionability_events`.
        self.status = PlanStatus::Executing {
            frames_remaining: u16::MAX,
        };
        self.duel_world.clear_weapon_history();
        Ok(events)
    }

    fn finish_boundary(
        &mut self,
        intents: [Intent; 2],
        ready: [Option<ActionabilityReason>; 2],
    ) -> Vec<PlanEvent> {
        let mut events = Vec::new();
        for side in [Side::Player, Side::Opponent] {
            if let Some(reason) = ready[side_index(side)] {
                events.push(PlanEvent::Ready { side, reason });
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

        self.selection_open = [ready[0].is_some(), ready[1].is_some()];
        for side in [Side::Player, Side::Opponent] {
            let index = side_index(side);
            if self.selection_open[index] {
                continue;
            }
            if let Some(reason) = self.interrupt_offer_reason(side) {
                self.selection_open[index] = true;
                events.push(PlanEvent::InterruptOffer { side, reason });
            }
        }
        self.submitted = [None, None];
        self.status = PlanStatus::Planning;
        // Preserve active busy actions for a one-sided next lock. A non-IOOT
        // fighter therefore cannot select an intent and continues its state.
        self.locked = self.active.map(|action| action.map(|action| action.intent));
        events
    }

    fn actionability_events(&self) -> [Option<ActionabilityReason>; 2] {
        self.active.map(|action| {
            let action = action.expect("executing PlanPhase owns two active actions");
            let state = action.intent.state();
            if action.hit_cancel {
                Some(ActionabilityReason::HitCancel)
            } else if state.interrupt_frames.contains(&action.current_tick) {
                Some(ActionabilityReason::InterruptFrame)
            } else if action.current_tick >= state.iasa_at {
                Some(ActionabilityReason::Iasa)
            } else if action.current_tick >= state.anim_length.saturating_sub(1) {
                Some(ActionabilityReason::AnimationEnd)
            } else {
                None
            }
        })
    }

    fn interrupt_offer_reason(&self, side: Side) -> Option<InterruptOfferReason> {
        let action = self.active[side_index(side)]?;
        if action.intent.state().interruptible_on_opponent_turn {
            Some(InterruptOfferReason::Ioot)
        } else if matches!(action.intent, Intent::Feint) {
            Some(InterruptOfferReason::Feint)
        } else if action.negative_on_hit {
            Some(InterruptOfferReason::NegativeOnHit)
        } else {
            None
        }
    }

    fn apply_contact_outcomes(&mut self, measured: &PhysicalContactBatch) {
        let Some(contact) = measured.contact else {
            return;
        };
        let attacker = contact.attacker;
        let defender = attacker.opposite();
        let attacker_index = side_index(attacker);
        let defender_index = side_index(defender);
        let Some(attacker_action) = self.active[attacker_index] else {
            return;
        };
        let active_cancellable_hitbox = attacker_action
            .intent
            .hitboxes()
            .iter()
            .copied()
            .any(|hitbox| hitbox.cancellable && hitbox.active_at(attacker_action.current_tick));
        if !active_cancellable_hitbox {
            return;
        }

        let defender_is_blocking = matches!(
            self.active[defender_index].map(|action| action.intent),
            Some(Intent::Block)
        );
        let attacker_state = attacker_action.intent.state();
        if !defender_is_blocking {
            if let Some(defender_action) = &mut self.active[defender_index] {
                defender_action.negative_on_hit = true;
            }
            if matches!(attacker_action.intent, Intent::Strike { .. })
                && self.combos[defender_index].air.is_airborne()
            {
                // A measured weapon/body contact is the only source permitted to
                // refresh a juggle launch; animation cannot fabricate this outcome.
                self.combos[defender_index].launch();
            }
        }
        let hit_cancel_allowed = !defender_is_blocking || attacker_state.iasa_on_hit_on_block;
        let can_hit_cancel = hit_cancel_allowed
            && attacker_state
                .iasa_on_hit
                .is_some_and(|iasa_on_hit| attacker_action.current_tick >= iasa_on_hit);
        if can_hit_cancel {
            let action = &mut self.active[attacker_index];
            if let Some(action) = action {
                action.hit_cancel = true;
            }
        }
    }

    fn advance_roots(&mut self) {
        let prior = self.roots;
        let active = self.active;
        let mut next = prior;
        for side in [Side::Player, Side::Opponent] {
            let index = side_index(side);
            let action = active[index].expect("executing PlanPhase owns two active actions");
            next[index] =
                root_after_action(prior[index], prior[side_index(side.opposite())], action);
        }
        self.roots = next;
        for side in [Side::Player, Side::Opponent] {
            let index = side_index(side);
            if let Some(action) = &mut self.active[index]
                && matches!(action.intent, Intent::Move { .. })
            {
                action.remaining_distance_mm = action
                    .remaining_distance_mm
                    .saturating_sub(ROOT_SPEED_MM_PER_TICK);
            }
            self.combos[index].tick(&mut self.roots[index].y_mm);
            self.recovery_frames[index] = self.recovery_frames[index].saturating_sub(1);
        }
    }

    fn advance_action_ticks(&mut self) {
        for action in self.active.iter_mut().flatten() {
            action.current_tick = action.current_tick.saturating_add(1);
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
                distance <= GRAB_ACQUIRE_RANGE_MM.saturating_add(max_travel)
            }
            Intent::Clinch { .. } => self.clinch.is_some(),
            _ => true,
        }
    }

    fn within_grab_reach(&self) -> bool {
        planar_distance_upper_bound(self.roots[0], self.roots[1]) <= GRAB_ACQUIRE_RANGE_MM
    }

    fn active_intents(&self) -> Result<[Intent; 2], PlanError> {
        match self.active {
            [Some(player), Some(opponent)] => Ok([player.intent, opponent.intent]),
            _ => Err(PlanError::MissingIntent),
        }
    }

    fn active_intents_or_idle(&self) -> [Intent; 2] {
        self.active
            .map(|action| action.map_or(Intent::Idle, |action| action.intent))
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

fn root_after_action(
    root: RootPosition,
    opponent: RootPosition,
    action: ActiveAction,
) -> RootPosition {
    match action.intent {
        Intent::Grab => step_toward(
            root,
            opponent,
            GRAB_ACQUIRE_RANGE_MM,
            ROOT_SPEED_MM_PER_TICK,
        ),
        Intent::Move {
            dir, auto_correct, ..
        } if action.remaining_distance_mm > 0 => {
            let speed = ROOT_SPEED_MM_PER_TICK.min(action.remaining_distance_mm);
            if auto_correct {
                step_direction(root, opponent, dir, speed)
            } else {
                step_heading(root, action.locked_heading, speed)
            }
        }
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

fn heading_for(
    root: RootPosition,
    opponent: RootPosition,
    direction: MoveDirection,
) -> MovementHeading {
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
    MovementHeading { axis_x, axis_z }
}

fn step_direction(
    root: RootPosition,
    opponent: RootPosition,
    direction: MoveDirection,
    speed: i32,
) -> RootPosition {
    step_heading(root, heading_for(root, opponent, direction), speed)
}

fn step_heading(root: RootPosition, heading: MovementHeading, speed: i32) -> RootPosition {
    let divisor = i32::from(heading.axis_x != 0) + i32::from(heading.axis_z != 0);
    if divisor == 0 {
        return root;
    }
    let step = speed / divisor;
    RootPosition {
        x_mm: root.x_mm.saturating_add(heading.axis_x * step),
        y_mm: root.y_mm,
        z_mm: root.z_mm.saturating_add(heading.axis_z * step),
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

    // --- Shared staging fixtures -------------------------------------------------
    // Centralize the fighter-separation invariants so no test hand-places roots
    // with ad-hoc magic numbers. `planar_distance_upper_bound` is MANHATTAN
    // (|dx|+|dz|), so two fighters at symmetric roots ±D on Z are 2D apart.
    // Reach/feasibility constants come from the production code, not re-derived
    // per test, so a tuning change updates every test consistently.
    const fn symmetric(d: i32) -> [RootPosition; 2] {
        [RootPosition::new(0, 0, d), RootPosition::new(0, 0, -d)]
    }

    /// The farthest symmetric separation at which a Grab is still feasible:
    /// distance <= GRAB_ACQUIRE_RANGE_MM + ROOT_SPEED_MM_PER_TICK * grab frame cost.
    fn grab_feasible_phase() -> PlanPhase {
        // 2D <= 650 + 100*20 = 2650 => D <= 1325. Use D=1200 (2400mm) with margin.
        let [player, opponent] = symmetric(1_200);
        PlanPhase::with_roots(player, opponent)
    }

    /// A separation where both fighters whiff every attack (no contact, no
    /// negative_on_hit interrupt offer). Well beyond weapon + body reach.
    fn whiff_phase() -> PlanPhase {
        let [player, opponent] = symmetric(4_000);
        PlanPhase::with_roots(player, opponent)
    }

    /// A close separation where a strike is guaranteed to make contact.
    fn contact_phase() -> PlanPhase {
        let [player, opponent] = symmetric(200);
        PlanPhase::with_roots(player, opponent)
    }

    fn move_intent(dir: MoveDirection, distance_mm: u16, auto_correct: bool) -> Intent {
        Intent::Move {
            dir,
            distance_mm,
            auto_correct,
        }
    }

    fn lock(phase: &mut PlanPhase, player: Intent, opponent: Intent) -> Vec<PlanEvent> {
        assert!(phase.can_submit_intent(Side::Player));
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
        let player = move_intent(MoveDirection::Approach, 400, true);
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
    fn window_stops_at_earliest_live_actionability_not_minimum_animation_length() {
        // Player Strike iasa_at=14; opponent Grab iasa_at=16 (later), so the
        // window stops at the PLAYER's earliest actionability (tick 14), proving
        // live-actionability, not min(anim_length)=18. Grab must be feasible (see
        // grab_feasible_phase) and stay out of clinch through the window.
        let mut phase = grab_feasible_phase();
        let player = Intent::Strike {
            variant: StrikeVariant::Thrust,
        };
        let opponent = Intent::Grab;
        lock(&mut phase, player, opponent);
        let events = phase.simulate_to_boundary().unwrap();

        assert!(
            phase.snapshot().truth_frame
                < u64::from(player.frame_cost().min(opponent.frame_cost()))
        );
        assert!(events.iter().any(|event| {
            matches!(
                event,
                PlanEvent::Ready {
                    side: Side::Player,
                    ..
                }
            )
        }));
        assert!(matches!(phase.status(), PlanStatus::Planning));
    }

    #[test]
    fn hit_cancel_shortens_window_compared_with_a_whiff() {
        let strike = Intent::Strike {
            variant: StrikeVariant::Thrust,
        };
        let mut hit = contact_phase();
        let mut whiff = whiff_phase();
        lock(&mut hit, strike, Intent::Idle);
        lock(&mut whiff, strike, Intent::Idle);
        let hit_events = hit.simulate_to_boundary().unwrap();
        let whiff_events = whiff.simulate_to_boundary().unwrap();

        assert!(
            hit.snapshot().last_contact_observed,
            "close DuelWorld strike must be measured"
        );
        assert!(hit.snapshot().truth_frame < whiff.snapshot().truth_frame);
        assert!(hit_events.iter().any(|event| {
            matches!(
                event,
                PlanEvent::Ready {
                    side: Side::Player,
                    reason: ActionabilityReason::HitCancel
                }
            )
        }));
        assert!(!whiff_events.iter().any(|event| {
            matches!(
                event,
                PlanEvent::Ready {
                    side: Side::Player,
                    reason: ActionabilityReason::HitCancel
                }
            )
        }));
    }

    #[test]
    fn ioot_is_offered_but_non_ioot_stays_busy() {
        let mut ioot = PlanPhase::new();
        lock(
            &mut ioot,
            Intent::Strike {
                variant: StrikeVariant::Thrust,
            },
            Intent::Block,
        );
        let ioot_events = ioot.simulate_to_boundary().unwrap();
        assert!(ioot_events.iter().any(|event| {
            matches!(
                event,
                PlanEvent::InterruptOffer {
                    side: Side::Opponent,
                    reason: InterruptOfferReason::Ioot
                }
            )
        }));
        assert!(ioot.can_submit_intent(Side::Opponent));

        // Busy (non-IOOT) branch: both fighters whiff at long range (no contact,
        // no negative_on_hit interrupt offer). Player Thrust has iasa_at=14 and
        // reaches Ready first; opponent Slash has iasa_at=17 and is non-IOOT, so
        // it stays busy and cannot submit.
        let mut busy = whiff_phase();
        lock(
            &mut busy,
            Intent::Strike {
                variant: StrikeVariant::Thrust,
            },
            Intent::Strike {
                variant: StrikeVariant::Slash,
            },
        );
        busy.simulate_to_boundary().unwrap();
        assert!(!busy.can_submit_intent(Side::Opponent));
        assert!(matches!(
            busy.submit_intent(Side::Opponent, Intent::Idle),
            Err(PlanError::SideBusy)
        ));
    }

    #[test]
    fn parameterized_auto_correct_reaims_against_a_moving_opponent() {
        let player = move_intent(MoveDirection::Approach, 600, true);
        let fixed = move_intent(MoveDirection::Approach, 600, false);
        let opponent = Intent::Dodge {
            dir: MoveDirection::LateralRight,
        };
        let mut corrected = PlanPhase::new();
        let mut locked_heading = PlanPhase::new();
        lock(&mut corrected, player, opponent);
        lock(&mut locked_heading, fixed, opponent);
        corrected.step_truth_tick().unwrap();
        locked_heading.step_truth_tick().unwrap();
        corrected.step_truth_tick().unwrap();
        locked_heading.step_truth_tick().unwrap();

        assert_ne!(
            corrected.root(Side::Player),
            locked_heading.root(Side::Player)
        );
        assert!(corrected.root(Side::Player).x_mm != locked_heading.root(Side::Player).x_mm);
    }

    #[test]
    fn same_inputs_have_the_same_hash_across_one_hundred_runs() {
        let mut expected = None;
        for _ in 0..100 {
            let mut phase = PlanPhase::with_roots(
                RootPosition::new(-300, 0, 500),
                RootPosition::new(250, 0, -350),
            );
            lock(
                &mut phase,
                move_intent(MoveDirection::CircleClockwise, 550, true),
                Intent::Strike {
                    variant: StrikeVariant::Slash,
                },
            );
            let events = phase.simulate_to_boundary().unwrap();
            let observation = (events, phase.snapshot(), phase.truth_hash());
            if let Some(previous) = &expected {
                assert_eq!(previous, &observation);
            } else {
                expected = Some(observation);
            }
        }
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
        lock(&mut phase, Intent::Cancel, Intent::Grab);
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
    fn grab_enters_clinch_at_its_own_actionability_boundary() {
        let mut phase =
            PlanPhase::with_roots(RootPosition::new(0, 0, 300), RootPosition::new(0, 0, -300));
        lock(
            &mut phase,
            Intent::Grab,
            move_intent(MoveDirection::Approach, 2_000, false),
        );
        let enter = phase.simulate_to_boundary().unwrap();
        assert!(
            enter
                .iter()
                .any(|event| matches!(event, PlanEvent::ClinchEnter { .. }))
        );
        assert!(phase.clinch().is_some());

        assert!(phase.can_submit_intent(Side::Player));
        assert!(!phase.can_submit_intent(Side::Opponent));
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
        let strike = Intent::Strike {
            variant: StrikeVariant::Thrust,
        };
        phase.active = [
            Some(ActiveAction::new(strike, phase.roots[0], phase.roots[1])),
            Some(ActiveAction::new(
                Intent::Idle,
                phase.roots[1],
                phase.roots[0],
            )),
        ];
        phase.active[0].as_mut().unwrap().current_tick = 3;
        phase.apply_contact_outcomes(&PhysicalContactBatch {
            truth_frame: 0,
            contact: Some(crate::truth::ContactGeometry {
                distance: 0.0,
                in_range: true,
                attacker: Side::Player,
                surface: crate::truth::ContactSurface::Body,
            }),
        });
        assert_eq!(
            phase.combo_state(Side::Opponent).air,
            AirState::Launched {
                vertical_velocity_mm_per_tick: super::super::combo::LAUNCH_VELOCITY_MM_PER_TICK,
            }
        );
    }
}
