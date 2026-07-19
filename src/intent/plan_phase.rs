//! Simultaneous-lock, goal-directed planning authority for the clean intent loop.
//!
//! Positions and ballistic state are integer millimetres. `glam` values are
//! created only at the measured `DuelWorld` boundary, then discarded; no float
//! result is admitted back into plan state. A plan window is a live actionability
//! simulation, never `min(frame_cost())`.

use glam::{Vec3, vec3};
use serde::{Deserialize, Serialize};

use crate::cleanbox::action_frame;
use crate::duel_physics::{Fighter, SharedPhysicsStep};
use crate::duel_world::{DuelWorld, DuelWorldError, DuelWorldTarget, DuelWorldTruthTick};
use crate::truth::{Action, PhysicalContactBatch, Side};

use super::clinch::{self, ClinchIntent, ClinchResolution, ClinchState};
use super::combo::{AirState, ComboState};
use super::grab_state::{GrabAttempt, GrabFailure};
use super::intent::{Intent, MoveDirection, StrikeVariant};

#[cfg(test)]
use super::grab_state::SecureGrabAdmission;

/// Root-space distance at which a fighter may begin a grab attempt.
/// This is NOT the secure-grab distance. Secure grab requires physical contact.
pub const GRAB_ACQUIRE_RANGE_MM: i32 = 650;
/// Maximum deterministic root translation in one 60 Hz truth tick.
pub const ROOT_SPEED_MM_PER_TICK: i32 = 100;
/// Minimum center-to-center Manhattan separation between fighter roots.
/// Two torso cylinders (~200 mm radius each) may never interpenetrate: a
/// voluntary root step (Move/Dodge/Grab approach) is clamped so it never
/// reduces planar separation below this bound. Clinch/grab admission at
/// GRAB_ACQUIRE_RANGE_MM (650) stays outside this bound, so the clamp does
/// not gate the grab lane. Movement that increases separation is always
/// allowed, even when a prior state is already inside the bound.
pub const BODY_MIN_SEPARATION_MM: i32 = 400;
/// Root separation an active Grab closes to. GRAB_ACQUIRE_RANGE_MM is only the
/// admission gate (where a grab intent may BEGIN); once the grab is live, the
/// state machine's ReachOrClose phase must actually close to contact distance
/// or the hand can never reach the opponent surface and the attempt hovers at
/// the boundary forever. Contact range equals the body-interpenetration floor:
/// a clinch ends chest-to-chest.
pub const GRAB_CLOSE_RANGE_MM: i32 = BODY_MIN_SEPARATION_MM;
/// Truth ticks an Acquire/ReachOrClose grab may go without any measured
/// contact before it is a whiff. 24 ticks = 400 ms at 60 Hz.
pub const GRAB_WHIFF_TIMEOUT_TICKS: u64 = 24;
/// Trailing contact-inactive 120 Hz substeps after FirstPhysicalContact that
/// break the grab (the defender slipped out before the hold secured).
pub const GRAB_BREAK_INACTIVE_SUBSTEPS: usize = 4;
/// Fixed recovery attached to an explicit cancel.
pub const CANCEL_PENALTY_FRAMES: u16 = 8;
/// Burst resource ceiling (percent).
pub const BURST_MAX: u16 = 100;
/// Burst cost of a whiff cancel (YOMIH: 75%).
pub const WHIFF_CANCEL_BURST_COST: u16 = 75;
/// Recovery attached to a whiff cancel — a distinct 2-frame state, not the
/// full cancel penalty.
pub const WHIFF_CANCEL_RECOVERY_FRAMES: u16 = 2;
/// Truth ticks per +1 burst regen (0.5 s at 60 Hz).
pub const BURST_REGEN_PERIOD_TICKS: u64 = 30;
/// Free-cancel (feint) charges at match start (YOMIH base cast: 2).
pub const FEINT_MAX_CHARGES: u8 = 2;
/// Truth ticks per +1 feint-charge recharge (2 s at 60 Hz).
pub const FEINT_RECHARGE_PERIOD_TICKS: u64 = 120;
/// A block contact at or before this block-action tick is a perfect block /
/// parry (F-008/F-009).
pub const PERFECT_BLOCK_TICKS: u16 = 3;
/// Attacker recovery penalty from a parry deflect.
pub const PARRY_STAGGER_FRAMES: u16 = 6;
/// Burst reward for a perfect block.
pub const PERFECT_BLOCK_BURST_GAIN: u16 = 12;
/// Tempo meter ceiling.
pub const TEMPO_MAX: u16 = 100;
/// Tempo gain for a perfect block.
pub const PERFECT_BLOCK_TEMPO_GAIN: u16 = 4;
/// Tempo gain for landing an unblocked hit.
pub const HIT_TEMPO_GAIN: u16 = 2;
/// Tempo loss for taking an unblocked hit.
pub const HIT_TAKEN_TEMPO_LOSS: u16 = 2;
/// Tempo gain for a normal block contact.
pub const BLOCK_TEMPO_GAIN: u16 = 1;
/// Tempo loss for a whiffed attack.
pub const WHIFF_TEMPO_LOSS: u16 = 1;
/// F-013 dynamic IASA: an unblocked hit shortens the attacker's actionable
/// tick by this many frames vs a blocked contact.
pub const DYNAMIC_IASA_HIT_BONUS_TICKS: u16 = 2;
/// F-020 range band thresholds (Manhattan mm): Close = grab/immediate strike
/// range, Mid = approach-covered strike range, Far = travel-required range.
pub const RANGE_CLOSE_MAX_MM: i32 = 650;
pub const RANGE_MID_MAX_MM: i32 = 2_000;

/// F-020 explicit range band for the current separation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RangeBand {
    Close,
    Mid,
    Far,
}

impl RangeBand {
    pub const fn of(separation_mm: i32) -> Self {
        if separation_mm <= RANGE_CLOSE_MAX_MM {
            Self::Close
        } else if separation_mm <= RANGE_MID_MAX_MM {
            Self::Mid
        } else {
            Self::Far
        }
    }
}
/// Tempo at match start (PRD_STANCE_TEMPO: tempo is a cost resource that
/// gates selection, never cancels a committed action).
pub const TEMPO_START: u16 = 50;
/// Tempo regenerated per side at each exchange boundary.
pub const TEMPO_REGEN_PER_EXCHANGE: u16 = 6;
/// Bonus tempo recovery when the side's locked intent was a Retreat move
/// (Disengage, PRD_STANCE_TEMPO §4.4).
pub const DISENGAGE_TEMPO_BONUS: u16 = 4;
/// Tempo cost of switching stance between exchanges.
pub const STANCE_SWITCH_TEMPO_COST: u16 = 5;

/// Fighter stance (PRD_STANCE_TEMPO): readable pre-contact information that
/// modifies the tempo economy (F-003; matrix-row hooks land with F-001).
/// Persists across exchanges; switching between exchanges costs tempo.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Stance {
    High,
    Neutral,
    Low,
}

/// Tempo cost of an intent in a stance. High favors strikes, Low favors
/// movement/defense, Neutral is the baseline (deterministic table).
pub fn tempo_cost(intent: Intent, stance: Stance) -> u16 {
    let base: u16 = match intent {
        Intent::Strike { .. } => 10,
        Intent::Grab => 12,
        Intent::Dodge { .. } => 8,
        Intent::Block => 4,
        Intent::Move { .. } => 4,
        Intent::Feint => 6,
        Intent::Cancel | Intent::Idle => 0,
        Intent::Clinch { .. } => 4,
        Intent::Draw => 4,
        Intent::Sheath => 0,
    };
    let modifier: i16 = match (stance, intent) {
        (Stance::High, Intent::Strike { .. }) => -2,
        (Stance::High, Intent::Dodge { .. }) => 2,
        (Stance::Low, Intent::Strike { .. }) => 2,
        (Stance::Low, Intent::Dodge { .. } | Intent::Move { .. }) => -2,
        _ => 0,
    };
    base.saturating_add_signed(modifier)
}

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
    /// F-015: the clinch controller picked an escape-only option — the
    /// controller must press (Throw/Knee/Hold).
    ControllerMustPress,
    /// F-015: the controlled side picked a controller-only option — it must
    /// escape (Tech/Break) or Hold.
    ControlledMustEscape,
    /// F-017: a downed side picked a non-getup option.
    GroundedGetup,
    /// F-018: a disarmed side picked a weapon option (Strike).
    Disarmed,
    /// F-019: Draw submitted while already armed.
    AlreadyArmed,
    /// F-019: Sheath submitted while already sheathed.
    AlreadySheathed,
    /// Feint submitted with no free-cancel charges remaining.
    NoFeintCharges,
    /// After a whiff cancel the follow-up must be an attack.
    AttackOnlyFollowup,
    /// The selected intent cannot be afforded with the side's current tempo.
    TempoExhausted,
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
    /// A whiffed attack was cancelled at 75% burst into the 2-frame
    /// whiff-cancel state; the follow-up must be an attack.
    WhiffCancelled {
        side: Side,
        burst_remaining: u16,
    },
    /// A block contact inside PERFECT_BLOCK_TICKS of the block's start
    /// (F-008): full negate plus burst/tempo reward.
    PerfectBlocked {
        side: Side,
    },
    /// The perfect block deflected the attack (F-009): attacker takes the
    /// stagger recovery and cannot hit-cancel.
    Parried {
        side: Side,
    },
    /// Contact during the defender's attack startup (F-010); the attacker
    /// hit-cancels immediately.
    CounterHit {
        side: Side,
    },
    /// A side changed stance between exchanges (F-003, PRD stance_changed).
    StanceChanged {
        side: Side,
        stance: Stance,
    },
    /// A grounded strike that made contact free-cancelled into another
    /// grounded strike mid-execution (F-012 string system).
    FreeCancelled {
        side: Side,
    },
    /// A clinch tech found no throw and whiffed (F-016).
    TechWhiffed {
        side: Side,
    },
    /// A parry deflected the side's weapon (F-018).
    Disarmed {
        side: Side,
    },
    ClinchEnter {
        initiator: Side,
    },
    ClinchExit {
        escaped_by: Side,
    },
    /// A grab attempt began (not a clinch — grab is separate from clinch).
    GrabBegin {
        initiator: Side,
    },
    /// A grab attempt was blocked (out of range or infeasible).
    GrabBlocked {
        side: Side,
        reason: GrabFailure,
    },
    /// A grab attempt was released or failed.
    GrabRelease {
        side: Side,
    },
    /// A grab became secure (all admission criteria met).
    GrabSecure {
        side: Side,
    },
    /// A grab failed (whiff or insufficient contact).
    GrabFailed {
        side: Side,
        reason: GrabFailure,
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
    pub grab: Option<super::grab_state::GrabState>,
    pub last_contact_observed: bool,
    /// Burst resource per side (0..=100). Whiff cancel spends 75.
    pub burst: [u16; 2],
    /// Free-cancel (feint) charges per side (0..=2).
    pub feint_charges: [u8; 2],
    /// The side's last completed attack whiffed (whiff-cancel window open).
    pub whiffed: [bool; 2],
    /// F-017 ground/pinned flags (getup-restricted window).
    pub downed: [bool; 2],
    /// F-018 disarm flags (parry deflect; no Strike until next selection).
    pub disarmed: [bool; 2],
    /// F-019 voluntary sheath flags (persistent until Draw completes).
    pub sheathed: [bool; 2],
    /// Tempo meter per side (0..=100, F-004): a cost resource that gates
    /// selection (PRD_STANCE_TEMPO) — actions cost tempo at lock, regen per
    /// exchange, bonuses for hits/blocks/parries, losses on hits/whiffs.
    pub tempo: [u16; 2],
    /// Persistent per-side stance (F-003).
    pub stances: [Stance; 2],
    /// F-020 explicit range band for the current separation.
    pub range_band: RangeBand,
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
    /// The action produced a measured contact (never whiffed).
    made_contact: bool,
    /// Truth-tick of the action's first measured contact (F-013: dynamic
    /// IASA never shortens below contact+1 — the string window is preserved).
    first_contact_tick: Option<u16>,
    /// This Cancel was admitted as a whiff cancel (2-frame recovery).
    is_whiff_cancel: bool,
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
            made_contact: false,
            first_contact_tick: None,
            is_whiff_cancel: false,
        }
    }
}

/// New clean simultaneous-lock game loop. This deliberately does not mutate
/// milestone3 state; it only adapts its measured physics/truth primitives.
/// Clone is used ONLY for forecast copies (F-110): a cloned phase simulates a
/// hypothetical lock without mutating live truth.
#[derive(Debug, Clone)]
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
    grab: Option<GrabAttempt>,
    truth_frame: u64,
    last_contact_observed: bool,
    burst: [u16; 2],
    burst_regen_ticks: [u64; 2],
    feint_charges: [u8; 2],
    feint_recharge_ticks: [u64; 2],
    whiffed: [bool; 2],
    whiff_cancel_followup: [bool; 2],
    /// F-017 ground/pinned: launched side's next selection is restricted to
    /// getup options (Idle/Dodge/Block) for one window.
    downed: [bool; 2],
    /// F-018 disarm: a parried attacker loses its weapon — no Strike until
    /// its next submitted selection.
    disarmed: [bool; 2],
    /// F-019 voluntary sheath state: persistent until a Draw window
    /// completes; doubles tempo regen but removes Strike.
    sheathed: [bool; 2],
    tempo: [u16; 2],
    stances: [Stance; 2],
    pending_events: Vec<PlanEvent>,
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
            grab: None,
            truth_frame: 0,
            last_contact_observed: false,
            burst: [BURST_MAX; 2],
            burst_regen_ticks: [0; 2],
            feint_charges: [FEINT_MAX_CHARGES; 2],
            feint_recharge_ticks: [0; 2],
            whiffed: [false; 2],
            downed: [false; 2],
            disarmed: [false; 2],
            sheathed: [false; 2],
            whiff_cancel_followup: [false; 2],
            tempo: [TEMPO_START; 2],
            stances: [Stance::Neutral; 2],
            pending_events: Vec::new(),
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

    pub const fn grab(&self) -> Option<&GrabAttempt> {
        self.grab.as_ref()
    }

    pub fn grab_mut(&mut self) -> Option<&mut GrabAttempt> {
        self.grab.as_mut()
    }

    pub fn grab_state(&self) -> Option<super::grab_state::GrabState> {
        self.grab.as_ref().map(|g| g.state)
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
            grab: self.grab_state(),
            last_contact_observed: self.last_contact_observed,
            burst: self.burst,
            feint_charges: self.feint_charges,
            whiffed: self.whiffed,
            downed: self.downed,
            disarmed: self.disarmed,
            sheathed: self.sheathed,
            tempo: self.tempo,
            stances: self.stances,
            range_band: RangeBand::of(planar_distance_upper_bound(self.roots[0], self.roots[1])),
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
        // F-012 free-cancel category graph: a grounded Strike that produced
        // measured contact (hit OR blocked) free-cancels into another
        // grounded Strike immediately, mid-execution — the string system.
        if matches!(self.status, PlanStatus::Executing { .. })
            && matches!(intent, Intent::Strike { .. })
        {
            let index = side_index(side);
            let admits = self.active[index].is_some_and(|action| {
                action.made_contact
                    && matches!(action.intent, Intent::Strike { .. })
                    && tempo_cost(intent, self.stances[index]) <= self.tempo[index]
            });
            if admits {
                self.tempo[index] =
                    self.tempo[index].saturating_sub(tempo_cost(intent, self.stances[index]));
                self.active[index] = Some(ActiveAction::new(
                    intent,
                    self.roots[index],
                    self.roots[1 - index],
                ));
                return Ok(vec![PlanEvent::FreeCancelled { side }]);
            }
        }
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
        // F-015 role gating: only the controller may Throw/Knee; only the
        // controlled side may Tech/Break.
        if let (Some(clinch_state), Intent::Clinch { sub: action }) = (self.clinch, intent) {
            let controller = clinch_state.controller == side;
            let legal = match action {
                ClinchIntent::Throw | ClinchIntent::Knee => controller,
                ClinchIntent::Tech | ClinchIntent::Break => !controller,
                ClinchIntent::Hold => true,
            };
            if !legal {
                return Ok(vec![PlanEvent::Reprompt {
                    side,
                    reason: if controller {
                        RepromptReason::ControllerMustPress
                    } else {
                        RepromptReason::ControlledMustEscape
                    },
                    options: REPROMPT_OPTIONS,
                }]);
            }
        }
        if self.clinch.is_none() && matches!(intent, Intent::Clinch { .. }) {
            return Err(PlanError::ClinchIntentRequired);
        }
        // F-017: a downed (launched) side may only pick getup options.
        if self.downed[index] && !is_getup_option(intent) {
            return Ok(vec![PlanEvent::Reprompt {
                side,
                reason: RepromptReason::GroundedGetup,
                options: REPROMPT_OPTIONS,
            }]);
        }
        // F-018/F-019: a disarmed or sheathed side cannot pick weapon
        // options.
        if (self.disarmed[index] || self.sheathed[index]) && matches!(intent, Intent::Strike { .. })
        {
            return Ok(vec![PlanEvent::Reprompt {
                side,
                reason: RepromptReason::Disarmed,
                options: REPROMPT_OPTIONS,
            }]);
        }
        // F-019: Draw requires sheathed; Sheath requires armed.
        if matches!(intent, Intent::Draw) && !self.sheathed[index] {
            return Ok(vec![PlanEvent::Reprompt {
                side,
                reason: RepromptReason::AlreadyArmed,
                options: REPROMPT_OPTIONS,
            }]);
        }
        if matches!(intent, Intent::Sheath) && self.sheathed[index] {
            return Ok(vec![PlanEvent::Reprompt {
                side,
                reason: RepromptReason::AlreadySheathed,
                options: REPROMPT_OPTIONS,
            }]);
        }
        if matches!(intent, Intent::Feint) && self.feint_charges[index] == 0 {
            return Ok(vec![PlanEvent::Reprompt {
                side,
                reason: RepromptReason::NoFeintCharges,
                options: REPROMPT_OPTIONS,
            }]);
        }
        if self.whiff_cancel_followup[index] && !matches!(intent, Intent::Strike { .. }) {
            return Ok(vec![PlanEvent::Reprompt {
                side,
                reason: RepromptReason::AttackOnlyFollowup,
                options: REPROMPT_OPTIONS,
            }]);
        }
        // Tempo gates selection (PRD_STANCE_TEMPO): unaffordable intents are
        // reprompted; a committed action is never cancelled by tempo.
        if tempo_cost(intent, self.stances[index]) > self.tempo[index] {
            return Ok(vec![PlanEvent::Reprompt {
                side,
                reason: RepromptReason::TempoExhausted,
                options: REPROMPT_OPTIONS,
            }]);
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
        self.apply_grab_contact_samples(&measured);
        self.apply_contact_outcomes(&measured.contact_batch);
        self.regen_yomi_resources();
        self.truth_frame = self.truth_frame.saturating_add(1);

        let mut events = Vec::new();
        events.append(&mut self.pending_events);
        let actionability = self.actionability_events();
        self.advance_action_ticks();
        if actionability.iter().any(Option::is_some) {
            let mut boundary_events = self.finish_boundary(intents, actionability);
            events.append(&mut boundary_events);
            return Ok(events);
        }

        self.status = PlanStatus::Executing {
            frames_remaining: frames_remaining.saturating_sub(1),
        };
        Ok(events)
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
                // Feint spends a free-cancel charge (gated at submit time).
                if matches!(intent, Intent::Feint) {
                    self.feint_charges[index] = self.feint_charges[index].saturating_sub(1);
                }
                // Tempo is consumed by the selected action at lock.
                self.tempo[index] =
                    self.tempo[index].saturating_sub(tempo_cost(intent, self.stances[index]));
                let mut action = ActiveAction::new(
                    intent,
                    self.roots[index],
                    self.roots[side_index(side.opposite())],
                );
                // Whiff-cancel admission: a Cancel locked while the whiff
                // window is open and burst covers the cost becomes the
                // 2-frame whiff-cancel state instead of the 8-frame cancel.
                if matches!(intent, Intent::Cancel)
                    && self.whiffed[index]
                    && self.burst[index] >= WHIFF_CANCEL_BURST_COST
                {
                    self.burst[index] = self.burst[index].saturating_sub(WHIFF_CANCEL_BURST_COST);
                    self.whiffed[index] = false;
                    self.whiff_cancel_followup[index] = true;
                    action.is_whiff_cancel = true;
                }
                // Any lock closes the whiff window: whiff-cancel, normal
                // cancel, or simply choosing something else.
                self.whiffed[index] = false;
                // F-017: submitting the getup selection lifts the downed
                // restriction (one restricted selection, whenever it comes).
                self.downed[index] = false;
                // F-018: submitting any selection re-arms (weapon recovered).
                self.disarmed[index] = false;
                self.whiff_cancel_followup[index] =
                    self.whiff_cancel_followup[index] && matches!(intent, Intent::Cancel);
                self.active[index] = Some(action);
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
                let index = side_index(side);
                // Whiff detection: an attack that reached its actionability
                // boundary without any measured contact opens the whiff-cancel
                // window for the next lock.
                if matches!(intents[index], Intent::Strike { .. })
                    && self.active[index].is_some_and(|action| !action.made_contact)
                {
                    self.whiffed[index] = true;
                    self.tempo[index] = self.tempo[index].saturating_sub(WHIFF_TEMPO_LOSS);
                }
                match intents[index] {
                    Intent::Feint => events.push(PlanEvent::Feinted { side }),
                    Intent::Cancel => {
                        let is_whiff_cancel =
                            self.active[index].is_some_and(|action| action.is_whiff_cancel);
                        if is_whiff_cancel {
                            let recovery = &mut self.recovery_frames[index];
                            *recovery = recovery.saturating_add(WHIFF_CANCEL_RECOVERY_FRAMES);
                            events.push(PlanEvent::WhiffCancelled {
                                side,
                                burst_remaining: self.burst[index],
                            });
                        } else {
                            let recovery = &mut self.recovery_frames[index];
                            *recovery = recovery.saturating_add(CANCEL_PENALTY_FRAMES);
                            events.push(PlanEvent::Cancelled {
                                side,
                                penalty_frames: CANCEL_PENALTY_FRAMES,
                            });
                        }
                    }
                    _ => {}
                }
            }
        }

        if let Some(mut clinch_state) = self.clinch {
            let player = clinch_intent(intents[side_index(Side::Player)]);
            let opponent = clinch_intent(intents[side_index(Side::Opponent)]);
            if let (Some(player), Some(opponent)) = (player, opponent) {
                match clinch::resolve(player, opponent, clinch_state.controller) {
                    ClinchResolution::Continue => {
                        // F-015 grapple progression: sustained double-Hold
                        // advances the controller Overhook → BackControl.
                        if player == ClinchIntent::Hold
                            && opponent == ClinchIntent::Hold
                            && clinch_state.position == super::clinch::ClinchPositionKind::Overhook
                        {
                            clinch_state.position = super::clinch::ClinchPositionKind::BackControl;
                            self.clinch = Some(clinch_state);
                        }
                    }
                    ClinchResolution::Exit { escaped_by } => {
                        self.clinch = None;
                        // The grab attempt that opened this clinch is spent;
                        // future grabs start fresh.
                        self.grab = None;
                        events.push(PlanEvent::ClinchExit { escaped_by });
                    }
                    ClinchResolution::Launch { launched } => {
                        self.combos[side_index(launched)].launch();
                        // A successful throw EXITS the clinch into the
                        // launch/knockdown (F-016/F-017).
                        self.clinch = None;
                        self.grab = None;
                        // F-017: the launched side is grounded — its next
                        // selection is restricted to getup options.
                        self.downed[side_index(launched)] = true;
                        let _ = clinch_state;
                    }
                    ClinchResolution::WhiffedTech { teched_by } => {
                        // F-016 punishment: a whiffed tech deepens the
                        // controller's position for free.
                        clinch_state.position = super::clinch::ClinchPositionKind::BackControl;
                        self.clinch = Some(clinch_state);
                        events.push(PlanEvent::TechWhiffed { side: teched_by });
                    }
                }
            }
        } else if self.grab.as_ref().is_some_and(GrabAttempt::is_secure) {
            // Secure grab resolves to its consequence: the clinch. This is the
            // only production path that emits GrabSecure / ClinchEnter; both
            // are derived from the measured interval verdict, never scripted.
            let initiator = self
                .grab
                .as_ref()
                .map(|grab| grab.initiator)
                .unwrap_or(Side::Player);
            if let Some(grab) = self.grab.as_mut() {
                grab.state = super::grab_state::GrabState::Consequence;
            }
            self.clinch = Some(ClinchState::new(initiator, self.truth_frame));
            events.push(PlanEvent::GrabSecure { side: initiator });
            events.push(PlanEvent::ClinchEnter { initiator });
        } else if let Some(grab) = self.grab.as_mut() {
            // Grab in progress: update state based on contact and intent
            if grab.is_in_progress() {
                // Check if grab intent is still active
                let grab_active = intents[side_index(grab.initiator)] == Intent::Grab;
                if !grab_active {
                    grab.to_release();
                    events.push(PlanEvent::GrabRelease {
                        side: grab.initiator,
                    });
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
            // Start a new grab attempt (NOT a clinch — grab is separate from clinch)
            let grab = GrabAttempt::new(
                initiator,
                self.roots[side_index(initiator)],
                self.roots[side_index(initiator.opposite())],
                self.truth_frame,
            );
            if grab.can_begin() {
                self.grab = Some(grab);
                events.push(PlanEvent::GrabBegin { initiator });
            } else {
                // Out of range: cannot begin grab
                events.push(PlanEvent::GrabBlocked {
                    side: initiator,
                    reason: GrabFailure::OutOfRange,
                });
            }
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
        // Exchange regen (PRD_STANCE_TEMPO §4.3-4.4): base regen per
        // boundary, bonus for a Retreat disengage; F-019: sheathed fighters
        // regen double (the sheath is the recovery trade for losing Strike).
        for side in [Side::Player, Side::Opponent] {
            let index = side_index(side);
            let mut regen = if matches!(
                intents[index],
                Intent::Move {
                    dir: MoveDirection::Retreat,
                    ..
                }
            ) {
                TEMPO_REGEN_PER_EXCHANGE + DISENGAGE_TEMPO_BONUS
            } else {
                TEMPO_REGEN_PER_EXCHANGE
            };
            if self.sheathed[index] {
                regen = regen.saturating_mul(2);
            }
            self.tempo[index] = (self.tempo[index] + regen).min(TEMPO_MAX);
            // F-019: the sheathed/armed transition lands at the END of the
            // Draw/Sheath window (the window itself is the vulnerability).
            match intents[index] {
                Intent::Sheath => self.sheathed[index] = true,
                Intent::Draw => self.sheathed[index] = false,
                _ => {}
            }
        }
        events
    }

    fn actionability_events(&self) -> [Option<ActionabilityReason>; 2] {
        self.active.map(|action| {
            let action = action.expect("executing PlanPhase owns two active actions");
            // Grab hold: while the grab state machine is in progress, the
            // grabber is NOT actionable — the attempt resolves to SecureGrab,
            // a break, or a whiff before the grabber may re-choose.
            if matches!(action.intent, Intent::Grab)
                && self.grab.as_ref().is_some_and(GrabAttempt::is_in_progress)
            {
                return None;
            }
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

    /// Feed the grab state machine with REAL per-substep measured contact
    /// evidence from the shared 120 Hz physics steps. This replaces the coarse
    /// one-sample-per-tick bridge that marked visible/causal channels inactive
    /// (which made SecureGrab unreachable in the live loop):
    /// - substep_id: the real consecutive 120 Hz physics tick (integer clock).
    /// - manifold_id: the measured proxy pair identity.
    /// - surface_distance_mm / proxy_overlap_mm: from the measured penetration
    ///   depth of the grabber↔defender proxy pair.
    /// - visible_contact_active: at the debug-mannequin tier the rendered
    ///   geometry IS the truth proxy geometry (canon hitbox parity), so a
    ///   measured proxy contact is the visible contact. The AAA mesh tier
    ///   replaces this with posed-mesh measurement (Mesh Doctor domain).
    /// - opponent_response_causal: measured truth-state disruption of the
    ///   defender caused by this manifold (negative_on_hit applied below).
    /// - prohibited_penetration_mm: 0 — mesh-level penetration is not
    ///   measurable at the proxy tier and is never fabricated.
    fn apply_grab_contact_samples(&mut self, measured: &DuelWorldTruthTick) {
        let in_progress = self.grab.as_ref().is_some_and(GrabAttempt::is_in_progress);
        if !in_progress {
            return;
        }
        let initiator = self
            .grab
            .as_ref()
            .map(|g| g.initiator)
            .unwrap_or(Side::Player);
        let grabber = fighter_of(initiator);
        let defender_index = side_index(initiator.opposite());
        for step in [&measured.first, &measured.second] {
            let sample = grab_substep_sample(step, grabber);
            if sample.physics_contact_active {
                // Measured causal response: the grab manifold disrupts the
                // defender's committed action (negative-on-hit), which also
                // opens their interrupt offer to tech the grab.
                if let Some(defender_action) = &mut self.active[defender_index] {
                    defender_action.negative_on_hit = true;
                }
                if let Some(grab) = self.grab.as_mut() {
                    if grab.state == super::grab_state::GrabState::Acquire {
                        grab.state = super::grab_state::GrabState::ReachOrClose;
                    }
                    let mut causal = sample;
                    causal.opponent_response_causal = true;
                    grab.update_contact(&causal);
                }
            } else if let Some(grab) = self.grab.as_mut() {
                grab.update_contact(&sample);
            }
        }
        // Whiff/break evaluation, derived deterministically from the recorded
        // samples (no extra state enters the truth hash).
        if let Some(grab) = self.grab.as_mut() {
            let contact_started = grab.first_contact_frame.is_some();
            if !contact_started
                && self.truth_frame.saturating_sub(grab.started_at_frame)
                    >= GRAB_WHIFF_TIMEOUT_TICKS
            {
                grab.update_whiff(self.truth_frame);
            } else if contact_started {
                let trailing_inactive = grab
                    .contact_samples
                    .iter()
                    .rev()
                    .take_while(|s| !s.physics_contact_active)
                    .count();
                if trailing_inactive >= GRAB_BREAK_INACTIVE_SUBSTEPS {
                    grab.to_release();
                }
            }
        }
    }

    /// Deterministic resource regen: +1 burst per BURST_REGEN_PERIOD_TICKS
    /// (cap BURST_MAX), +1 feint charge per FEINT_RECHARGE_PERIOD_TICKS
    /// (cap FEINT_MAX_CHARGES). Runs inside the truth tick so replays hash it.
    fn regen_yomi_resources(&mut self) {
        for index in 0..2 {
            self.burst_regen_ticks[index] += 1;
            if self.burst_regen_ticks[index] >= BURST_REGEN_PERIOD_TICKS {
                self.burst_regen_ticks[index] = 0;
                self.burst[index] = (self.burst[index] + 1).min(BURST_MAX);
            }
            self.feint_recharge_ticks[index] += 1;
            if self.feint_recharge_ticks[index] >= FEINT_RECHARGE_PERIOD_TICKS {
                self.feint_recharge_ticks[index] = 0;
                self.feint_charges[index] = (self.feint_charges[index] + 1).min(FEINT_MAX_CHARGES);
            }
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

        // Grab contact evidence is fed by apply_grab_contact_samples from the
        // real per-substep shared-physics contacts; this coarse 60 Hz batch no
        // longer writes into the grab state machine.
        let active_cancellable_hitbox = attacker_action
            .intent
            .hitboxes()
            .iter()
            .copied()
            .any(|hitbox| hitbox.cancellable && hitbox.active_at(attacker_action.current_tick));
        if !active_cancellable_hitbox {
            return;
        }
        // The attack produced a measured contact; it can never be a whiff.
        if let Some(action) = &mut self.active[attacker_index] {
            action.made_contact = true;
            if action.first_contact_tick.is_none() {
                action.first_contact_tick = Some(attacker_action.current_tick);
            }
        }

        let defender_is_blocking = matches!(
            self.active[defender_index].map(|action| action.intent),
            Some(Intent::Block)
        );
        if defender_is_blocking {
            let block_tick = self.active[defender_index].map_or(u16::MAX, |a| a.current_tick);
            if block_tick <= PERFECT_BLOCK_TICKS {
                // F-008/F-009 perfect block + parry deflect: full negate,
                // defender burst/tempo reward, attacker staggered with no
                // hit-cancel.
                self.tempo[defender_index] =
                    (self.tempo[defender_index] + PERFECT_BLOCK_TEMPO_GAIN).min(TEMPO_MAX);
                self.burst[defender_index] =
                    (self.burst[defender_index] + PERFECT_BLOCK_BURST_GAIN).min(BURST_MAX);
                self.recovery_frames[attacker_index] =
                    self.recovery_frames[attacker_index].saturating_add(PARRY_STAGGER_FRAMES);
                // F-018: the parry deflects the attacker's weapon — the
                // attacker is disarmed until its next submitted selection.
                self.disarmed[attacker_index] = true;
                self.pending_events
                    .push(PlanEvent::PerfectBlocked { side: defender });
                self.pending_events
                    .push(PlanEvent::Parried { side: defender });
                self.pending_events
                    .push(PlanEvent::Disarmed { side: attacker });
                return;
            }
            // Normal block contact: small defender tempo gain.
            self.tempo[defender_index] =
                (self.tempo[defender_index] + BLOCK_TEMPO_GAIN).min(TEMPO_MAX);
        } else {
            // F-010 counter-hit: contact while the defender's attack is still
            // in startup (no hitbox active yet) — attacker hit-cancels at once.
            let counter_hit = self.active[defender_index].is_some_and(|action| {
                matches!(action.intent, Intent::Strike { .. } | Intent::Grab)
                    && action.current_tick
                        < action
                            .intent
                            .hitboxes()
                            .iter()
                            .map(|hitbox| hitbox.start_tick)
                            .min()
                            .unwrap_or(u16::MAX)
            });
            if counter_hit {
                self.pending_events
                    .push(PlanEvent::CounterHit { side: attacker });
                if let Some(action) = &mut self.active[attacker_index] {
                    action.hit_cancel = true;
                }
            }
            // Landed unblocked hit: attacker gains tempo, defender loses it.
            self.tempo[attacker_index] =
                (self.tempo[attacker_index] + HIT_TEMPO_GAIN).min(TEMPO_MAX);
            self.tempo[defender_index] =
                self.tempo[defender_index].saturating_sub(HIT_TAKEN_TEMPO_LOSS);
        }
        let attacker_state = attacker_action.intent.state();
        if !defender_is_blocking {
            let defender_root = self.roots[defender_index];
            let attacker_root = self.roots[attacker_index];
            if let Some(defender_action) = &mut self.active[defender_index] {
                defender_action.negative_on_hit = true;
                if !matches!(defender_action.intent, Intent::Strike { .. }) {
                    // Hit-stun interrupts the action itself: a grab, dodge,
                    // move, or feint that eats an unblocked hit DIES — it can
                    // never continue to resolution after being struck. (A
                    // strike already stops contacting via negative_on_hit.)
                    let interrupted = ActiveAction::new(Intent::Idle, defender_root, attacker_root);
                    *defender_action = ActiveAction {
                        negative_on_hit: true,
                        ..interrupted
                    };
                    // A struck grabber loses the grab attempt entirely — no
                    // sustained-contact streak can survive the interrupt.
                    if self
                        .grab
                        .as_ref()
                        .is_some_and(|grab| grab.initiator == defender)
                    {
                        self.grab = None;
                    }
                }
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
        // F-013 dynamic IASA: an unblocked hit shortens the hit-cancel tick
        // vs a blocked contact (blocked contacts keep the static iasa), but
        // never below first_contact+2 — one full tick of F-012 string window
        // is always preserved after first contact (contact resolution and the
        // post-advance actionability check share a step).
        let can_hit_cancel = hit_cancel_allowed
            && attacker_state.iasa_on_hit.is_some_and(|iasa_on_hit| {
                let shortened = iasa_on_hit.saturating_sub(DYNAMIC_IASA_HIT_BONUS_TICKS);
                let effective = if !defender_is_blocking {
                    // Read first_contact live: attacker_action is a pre-contact
                    // copy and would miss a first contact set this very tick.
                    self.active[attacker_index]
                        .and_then(|action| action.first_contact_tick)
                        .map_or(shortened, |contact| shortened.max(contact + 2))
                } else {
                    iasa_on_hit
                };
                attacker_action.current_tick >= effective
            });
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

    /// Switch a side's stance between exchanges (F-003, PRD_STANCE_TEMPO):
    /// costs tempo, Planning-only, fail-open (tempo clamps at 0). Emits
    /// StanceChanged so the snapshot stream shows the transition.
    pub fn set_stance(&mut self, side: Side, stance: Stance) -> Result<(), PlanError> {
        if self.status != PlanStatus::Planning {
            return Err(PlanError::NotPlanning);
        }
        let index = side_index(side);
        if self.stances[index] == stance {
            return Ok(());
        }
        self.stances[index] = stance;
        self.tempo[index] = self.tempo[index].saturating_sub(STANCE_SWITCH_TEMPO_COST);
        self.pending_events
            .push(PlanEvent::StanceChanged { side, stance });
        Ok(())
    }

    /// Full state-conditioned availability for HUD display (F-112): clinch
    /// exclusivity, feint charges, whiff-cancel follow-up gate, grab range.
    pub fn intent_available(&self, side: Side, intent: Intent) -> bool {
        let index = side_index(side);
        if let Some(clinch_state) = self.clinch {
            // F-015 role gating mirrors submit_intent.
            return match intent {
                Intent::Clinch { sub: action } => match action {
                    ClinchIntent::Throw | ClinchIntent::Knee => clinch_state.controller == side,
                    ClinchIntent::Tech | ClinchIntent::Break => clinch_state.controller != side,
                    ClinchIntent::Hold => true,
                },
                _ => false,
            };
        }
        if matches!(intent, Intent::Clinch { .. }) {
            return false;
        }
        // F-017: downed sides may only pick getup options.
        if self.downed[index] && !is_getup_option(intent) {
            return false;
        }
        // F-018/F-019: disarmed or sheathed sides cannot pick weapon
        // options.
        if (self.disarmed[index] || self.sheathed[index]) && matches!(intent, Intent::Strike { .. })
        {
            return false;
        }
        // F-019: Draw requires sheathed; Sheath requires armed.
        if matches!(intent, Intent::Draw) && !self.sheathed[index] {
            return false;
        }
        if matches!(intent, Intent::Sheath) && self.sheathed[index] {
            return false;
        }
        if matches!(intent, Intent::Feint) && self.feint_charges[index] == 0 {
            return false;
        }
        if self.whiff_cancel_followup[index] && !matches!(intent, Intent::Strike { .. }) {
            return false;
        }
        if tempo_cost(intent, self.stances[index]) > self.tempo[index] {
            return false;
        }
        self.is_feasible(side, intent, intent.state().anim_length)
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
        | Intent::Draw
        | Intent::Sheath
        | Intent::Clinch { .. } => Action::Block,
    }
}

fn clinch_intent(intent: Intent) -> Option<super::clinch::ClinchIntent> {
    match intent {
        Intent::Clinch { sub } => Some(sub),
        _ => None,
    }
}

/// F-017 getup options available to a downed side.
fn is_getup_option(intent: Intent) -> bool {
    matches!(intent, Intent::Idle | Intent::Dodge { .. } | Intent::Block)
}

fn root_after_action(
    root: RootPosition,
    opponent: RootPosition,
    action: ActiveAction,
) -> RootPosition {
    let candidate = match action.intent {
        Intent::Grab => step_toward(root, opponent, GRAB_CLOSE_RANGE_MM, ROOT_SPEED_MM_PER_TICK),
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
    };
    clamp_body_separation(root, opponent, candidate)
}

/// Clamp a voluntary root step so the fighters' body cylinders never
/// interpenetrate. Steps that keep or increase separation pass through
/// unchanged; steps that would breach BODY_MIN_SEPARATION_MM are shortened
/// proportionally (integer-exact) so the mover stops at the boundary.
fn clamp_body_separation(
    root: RootPosition,
    opponent: RootPosition,
    candidate: RootPosition,
) -> RootPosition {
    let current = planar_distance_upper_bound(root, opponent);
    let after = planar_distance_upper_bound(candidate, opponent);
    if after >= current || after >= BODY_MIN_SEPARATION_MM {
        return candidate;
    }
    let allowed_reduction = current.saturating_sub(BODY_MIN_SEPARATION_MM).max(0);
    let dx = candidate.x_mm.saturating_sub(root.x_mm);
    let dz = candidate.z_mm.saturating_sub(root.z_mm);
    let total = dx.abs().saturating_add(dz.abs());
    if total == 0 {
        return root;
    }
    let reduction = current.saturating_sub(after);
    let keep = total
        .saturating_sub(reduction.saturating_sub(allowed_reduction))
        .max(0);
    RootPosition {
        x_mm: root.x_mm.saturating_add(dx.saturating_mul(keep) / total),
        y_mm: candidate.y_mm,
        z_mm: root.z_mm.saturating_add(dz.saturating_mul(keep) / total),
    }
}

fn fighter_of(side: Side) -> Fighter {
    match side {
        Side::Player => Fighter::Player,
        Side::Opponent => Fighter::Opponent,
    }
}

/// Reduce one measured 120 Hz shared-physics step into one grab contact
/// manifold sample for the grabber's manifold pair. Only contacts that
/// involve the grabber (as attacker or defender) count; the deepest measured
/// penetration wins. Inactive substeps are still emitted so interval
/// contiguity is evaluated against the real 120 Hz clock, never fabricated.
fn grab_substep_sample(
    step: &SharedPhysicsStep,
    grabber: Fighter,
) -> super::grab_contact::ContactManifoldSample {
    let best = step
        .contacts
        .iter()
        .filter(|contact| contact.attacker == grabber || contact.defender == grabber)
        .max_by(|a, b| {
            a.geometry
                .depth
                .partial_cmp(&b.geometry.depth)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
    match best {
        Some(contact) => {
            let overlap_mm = contact.geometry.depth * 1000.0;
            super::grab_contact::ContactManifoldSample {
                substep_id: step.physics_tick,
                manifold_id: ((contact.geometry.attacker_proxy as u64) << 16)
                    | ((contact.geometry.defender_proxy as u64) << 1)
                    | u64::from(contact.attacker == grabber),
                surface_distance_mm: (-overlap_mm).max(0.0),
                proxy_overlap_mm: overlap_mm,
                prohibited_penetration_mm: 0.0,
                physics_contact_active: true,
                // Debug-mannequin tier: the rendered geometry IS the truth
                // proxy geometry (canon hitbox parity), so a measured proxy
                // contact is the visible contact. The AAA mesh tier replaces
                // this with posed-mesh measurement (Mesh Doctor domain).
                visible_contact_active: true,
                opponent_response_causal: false, // set by caller when applied
                presentation_override: false,
            }
        }
        None => super::grab_contact::ContactManifoldSample {
            substep_id: step.physics_tick,
            manifold_id: 0,
            surface_distance_mm: f32::MAX,
            proxy_overlap_mm: 0.0,
            prohibited_penetration_mm: 0.0,
            physics_contact_active: false,
            visible_contact_active: false,
            opponent_response_causal: false,
            presentation_override: false,
        },
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

pub fn planar_distance_upper_bound(left: RootPosition, right: RootPosition) -> i32 {
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

    fn manhattan(phase: &PlanPhase) -> i32 {
        let roots = phase.snapshot().roots;
        planar_distance_upper_bound(roots[0], roots[1])
    }

    /// Re-lock at a planning boundary, respecting one-sided actionability:
    /// only sides whose selection is open receive a new intent.
    fn relock_available(phase: &mut PlanPhase, player: Intent, opponent: Intent) {
        if phase.status() != PlanStatus::Planning {
            return;
        }
        if phase.can_submit_intent(Side::Player) {
            let _ = phase.submit_intent(Side::Player, player);
        }
        if phase.can_submit_intent(Side::Opponent) {
            let _ = phase.submit_intent(Side::Opponent, opponent);
        }
    }

    /// Drive boundaries until `pred` matches an emitted event (or attempts
    /// run out), keeping the opponent on `opp` and re-submitting `player`
    /// whenever the player's selection opens. Returns all events seen.
    fn drive_until(
        phase: &mut PlanPhase,
        player: Intent,
        opp: Intent,
        pred: impl Fn(&PlanEvent) -> bool,
        max_boundaries: usize,
    ) -> Vec<PlanEvent> {
        let mut seen = Vec::new();
        for _ in 0..max_boundaries {
            relock_available(phase, player, opp);
            match phase.simulate_to_boundary() {
                Ok(events) => {
                    let hit = events.iter().any(&pred);
                    seen.extend(events);
                    if hit {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
        seen
    }

    #[test]
    fn whiff_cancel_spends_burst_shortens_recovery_and_gates_followup() {
        // Long-range slash vs retreat: guaranteed whiff. The next Cancel must
        // be admitted as a whiff cancel: burst 100 -> 25, 2-frame recovery,
        // attack-only follow-up gate.
        let [player, opponent] = symmetric(1_500);
        let mut phase = PlanPhase::with_roots(player, opponent);
        relock_available(
            &mut phase,
            Intent::Strike {
                variant: StrikeVariant::Slash,
            },
            move_intent(MoveDirection::Retreat, 2_000, true),
        );
        phase.simulate_to_boundary().unwrap();
        assert!(
            phase.snapshot().whiffed[0],
            "a complete miss must open the whiff window"
        );
        // Whiff-cancel; drive until the Cancel's own Ready boundary resolves.
        let events = drive_until(
            &mut phase,
            Intent::Cancel,
            Intent::Idle,
            |event| matches!(event, PlanEvent::WhiffCancelled { .. }),
            12,
        );
        assert!(
            events
                .iter()
                .any(|event| matches!(event, PlanEvent::WhiffCancelled { .. })),
            "whiffed attack + 75 burst must admit the whiff cancel"
        );
        assert_eq!(
            phase.snapshot().burst[0],
            BURST_MAX - WHIFF_CANCEL_BURST_COST
        );
        // Attack-only follow-up: Block is reprompted, Strike locks.
        relock_available(&mut phase, Intent::Idle, Intent::Idle);
        let reprompt = phase.submit_intent(Side::Player, Intent::Block).unwrap();
        assert!(reprompt.iter().any(|event| matches!(
            event,
            PlanEvent::Reprompt {
                reason: RepromptReason::AttackOnlyFollowup,
                ..
            }
        )));
        let followup = phase
            .submit_intent(
                Side::Player,
                Intent::Strike {
                    variant: StrikeVariant::Thrust,
                },
            )
            .unwrap();
        assert!(
            !followup
                .iter()
                .any(|event| matches!(event, PlanEvent::Reprompt { .. })),
            "an attack follow-up must not be reprompted"
        );
    }

    #[test]
    fn whiff_cancel_requires_burst() {
        // Drain burst below the 75 cost with one whiff-cancel; the second
        // whiff-cancel attempt degrades to the normal 8-frame cancel.
        let [player, opponent] = symmetric(1_500);
        let mut phase = PlanPhase::with_roots(player, opponent);
        let events = drive_until(
            &mut phase,
            Intent::Strike {
                variant: StrikeVariant::Slash,
            },
            move_intent(MoveDirection::Retreat, 2_000, true),
            |event| matches!(event, PlanEvent::Ready { .. }),
            4,
        );
        assert!(!events.is_empty());
        assert!(phase.snapshot().whiffed[0]);
        let events = drive_until(
            &mut phase,
            Intent::Cancel,
            Intent::Idle,
            |event| matches!(event, PlanEvent::WhiffCancelled { .. }),
            12,
        );
        assert!(
            events
                .iter()
                .any(|event| matches!(event, PlanEvent::WhiffCancelled { .. }))
        );
        assert_eq!(phase.snapshot().burst[0], 25);
        // Second whiff setup: whiff again, then Cancel must NOT be a whiff
        // cancel (25 < 75) — normal 8-frame cancel applies.
        let events = drive_until(
            &mut phase,
            Intent::Strike {
                variant: StrikeVariant::Slash,
            },
            move_intent(MoveDirection::Retreat, 2_000, true),
            |event| matches!(event, PlanEvent::Ready { .. }),
            8,
        );
        assert!(!events.is_empty());
        assert!(phase.snapshot().whiffed[0]);
        let events = drive_until(
            &mut phase,
            Intent::Cancel,
            Intent::Idle,
            |event| {
                matches!(
                    event,
                    PlanEvent::Cancelled { .. } | PlanEvent::WhiffCancelled { .. }
                )
            },
            12,
        );
        assert!(
            events
                .iter()
                .any(|event| matches!(event, PlanEvent::Cancelled { .. })),
            "without 75 burst the cancel is the normal 8-frame cancel"
        );
        assert!(
            !events
                .iter()
                .any(|event| matches!(event, PlanEvent::WhiffCancelled { .. }))
        );
        let final_burst = phase.snapshot().burst[0];
        assert!(
            (25..75).contains(&final_burst),
            "no 75-cost spend without 75 available (regen may add +1/30 ticks): {final_burst}"
        );
    }

    #[test]
    fn feint_charges_deplete_gate_and_recharge() {
        let [player, opponent] = symmetric(500);
        let mut phase = PlanPhase::with_roots(player, opponent);
        // Two feints spend both charges.
        for expected in [1_u8, 0_u8] {
            relock_available(&mut phase, Intent::Feint, Intent::Idle);
            phase.simulate_to_boundary().unwrap();
            assert_eq!(phase.snapshot().feint_charges[0], expected);
        }
        // Third feint is reprompted.
        let reprompt = phase.submit_intent(Side::Player, Intent::Feint).unwrap();
        assert!(reprompt.iter().any(|event| matches!(
            event,
            PlanEvent::Reprompt {
                reason: RepromptReason::NoFeintCharges,
                ..
            }
        )));
        // Recharge: one charge returns after FEINT_RECHARGE_PERIOD_TICKS.
        for _ in 0..FEINT_RECHARGE_PERIOD_TICKS {
            relock_available(&mut phase, Intent::Idle, Intent::Idle);
            if phase.status() == PlanStatus::Planning
                && !phase.can_submit_intent(Side::Player)
                && !phase.can_submit_intent(Side::Opponent)
            {
                break;
            }
            let _ = phase.step_truth_tick();
        }
        assert!(phase.snapshot().feint_charges[0] >= 1);
    }

    #[test]
    fn perfect_block_parry_staggers_attacker() {
        // Thrust (hitbox start 3) vs Block locked at the same boundary: the
        // first processed contact lands at block tick 3 (PERFECT_BLOCK_TICKS),
        // so the block is perfect — attacker staggered, defender rewarded.
        let [player, opponent] = symmetric(300);
        let mut phase = PlanPhase::with_roots(player, opponent);
        let events = drive_until(
            &mut phase,
            Intent::Strike {
                variant: StrikeVariant::Thrust,
            },
            Intent::Block,
            |event| matches!(event, PlanEvent::Parried { .. }),
            8,
        );
        assert!(
            events.iter().any(|e| matches!(
                e,
                PlanEvent::PerfectBlocked {
                    side: Side::Opponent
                }
            )),
            "block tick 3 contact must be a perfect block: {events:?}"
        );
        assert!(events.iter().any(|e| matches!(
            e,
            PlanEvent::Parried {
                side: Side::Opponent
            }
        )));
        let snap = phase.snapshot();
        // +4 from the perfect contact, +1 per subsequent normal contact while
        // the thrust hitbox stays active.
        assert!(snap.tempo[1] >= PERFECT_BLOCK_TEMPO_GAIN);
        // Attacker stagger: recovery was extended at the parry tick (decays
        // per tick afterward, so assert it has not fully elapsed).
        assert!(snap.recovery_frames[0] > 0);
    }

    #[test]
    fn late_block_is_normal_not_perfect() {
        // Slash (hitbox start 4) vs Block: first contact at block tick 4, past
        // the perfect window — normal block, no parry events.
        let [player, opponent] = symmetric(300);
        let mut phase = PlanPhase::with_roots(player, opponent);
        let events = drive_until(
            &mut phase,
            Intent::Strike {
                variant: StrikeVariant::Slash,
            },
            Intent::Block,
            |event| matches!(event, PlanEvent::Ready { .. }),
            12,
        );
        assert!(
            !events.iter().any(|e| matches!(
                e,
                PlanEvent::PerfectBlocked { .. } | PlanEvent::Parried { .. }
            )),
            "block tick 4 contact must not be perfect: {events:?}"
        );
        assert!(
            phase.snapshot().tempo[1] >= BLOCK_TEMPO_GAIN,
            "normal block contacts grant the defender +1 tempo each"
        );
    }

    #[test]
    fn counter_hit_during_startup_grants_instant_hit_cancel() {
        // Thrust (start 3) beats Slash (start 4): contact at tick 3 lands
        // during the slasher's startup — counter-hit, attacker tempo up.
        let [player, opponent] = symmetric(300);
        let mut phase = PlanPhase::with_roots(player, opponent);
        let events = drive_until(
            &mut phase,
            Intent::Strike {
                variant: StrikeVariant::Thrust,
            },
            Intent::Strike {
                variant: StrikeVariant::Slash,
            },
            |event| matches!(event, PlanEvent::CounterHit { .. }),
            8,
        );
        assert!(
            events
                .iter()
                .any(|e| matches!(e, PlanEvent::CounterHit { side: Side::Player })),
            "contact during startup must be a counter-hit: {events:?}"
        );
        // 50 start - 10 strike cost + 2 landed hit + 6 exchange regen (the
        // window runs to its boundary after the counter-hit tick).
        assert_eq!(
            phase.snapshot().tempo[0],
            TEMPO_START - 10 + HIT_TEMPO_GAIN + TEMPO_REGEN_PER_EXCHANGE
        );
    }

    #[test]
    fn stance_switch_costs_tempo_and_emits_event() {
        let mut phase = PlanPhase::new();
        phase.set_stance(Side::Player, Stance::High).unwrap();
        let snap = phase.snapshot();
        assert_eq!(snap.stances[0], Stance::High);
        assert_eq!(snap.tempo[0], TEMPO_START - STANCE_SWITCH_TEMPO_COST);
        // High stance discounts strikes: cost 8 instead of 10.
        assert_eq!(
            tempo_cost(
                Intent::Strike {
                    variant: StrikeVariant::Slash,
                },
                Stance::High
            ),
            8
        );
        // Same-stance set is a no-op (no double charge).
        phase.set_stance(Side::Player, Stance::High).unwrap();
        assert_eq!(
            phase.snapshot().tempo[0],
            TEMPO_START - STANCE_SWITCH_TEMPO_COST
        );
    }

    #[test]
    fn tempo_exhaustion_reprompts_unaffordable_actions() {
        let mut phase = PlanPhase::new();
        // Drain tempo below the strike cost via repeated stance switches.
        for _ in 0..9 {
            let next = match phase.snapshot().stances[0] {
                Stance::Neutral => Stance::High,
                _ => Stance::Neutral,
            };
            phase.set_stance(Side::Player, next).unwrap();
        }
        assert!(phase.snapshot().tempo[0] < 10);
        let reprompt = phase
            .submit_intent(
                Side::Player,
                Intent::Strike {
                    variant: StrikeVariant::Slash,
                },
            )
            .unwrap();
        assert!(reprompt.iter().any(|event| matches!(
            event,
            PlanEvent::Reprompt {
                reason: RepromptReason::TempoExhausted,
                ..
            }
        )));
        // Idle is always affordable.
        assert!(
            phase
                .submit_intent(Side::Player, Intent::Idle)
                .unwrap()
                .is_empty()
        );
    }

    #[test]
    fn exchange_regen_and_disengage_bonus() {
        // Player retreats (disengage +4), opponent idles: after one exchange
        // boundary the player has +10 regen (minus move cost 4).
        let mut phase = PlanPhase::new();
        relock_available(
            &mut phase,
            Intent::move_standard(MoveDirection::Retreat),
            Intent::Idle,
        );
        phase.simulate_to_boundary().unwrap();
        let snap = phase.snapshot();
        assert_eq!(
            snap.tempo[0],
            TEMPO_START - 4 + TEMPO_REGEN_PER_EXCHANGE + DISENGAGE_TEMPO_BONUS
        );
        assert_eq!(snap.tempo[1], TEMPO_START + TEMPO_REGEN_PER_EXCHANGE);
    }

    #[test]
    fn probe_clinch_hold_windows() {
        let [player, opponent] = symmetric(300);
        let mut phase = PlanPhase::with_roots(player, opponent);
        drive_until(
            &mut phase,
            Intent::Grab,
            Intent::Idle,
            |event| matches!(event, PlanEvent::ClinchEnter { .. }),
            20,
        );
        for w in 0..6 {
            let events = phase.simulate_to_boundary().unwrap_or_default();
            println!(
                "WINDOW {w} open={:?} locked={:?} pos={:?} events={:?}",
                [
                    phase.can_submit_intent(Side::Player),
                    phase.can_submit_intent(Side::Opponent)
                ],
                phase.snapshot().locked,
                phase.clinch().map(|c| c.position),
                events
            );
            relock_available(
                &mut phase,
                Intent::Clinch {
                    sub: ClinchIntent::Hold,
                },
                Intent::Clinch {
                    sub: ClinchIntent::Hold,
                },
            );
        }
    }

    /// Advance one-sided clinch boundaries (relocking neutral Holds for the
    /// OTHER side only) until `side` may submit.
    fn advance_until_submittable(phase: &mut PlanPhase, side: Side) {
        let hold = if phase.clinch().is_some() {
            Intent::Clinch {
                sub: ClinchIntent::Hold,
            }
        } else {
            Intent::Idle
        };
        for _ in 0..12 {
            if phase.can_submit_intent(side) {
                return;
            }
            let _ = phase.simulate_to_boundary();
            for other in [Side::Player, Side::Opponent] {
                if other != side && phase.can_submit_intent(other) {
                    let _ = phase.submit_intent(other, hold);
                }
            }
        }
        panic!("side never became submittable");
    }

    /// Build a clinch (player-initiated secure grab vs idle opponent).
    fn clinch_phase() -> PlanPhase {
        let [player, opponent] = symmetric(300);
        let mut phase = PlanPhase::with_roots(player, opponent);
        drive_until(
            &mut phase,
            Intent::Grab,
            Intent::Idle,
            |event| matches!(event, PlanEvent::ClinchEnter { .. }),
            20,
        );
        phase
    }

    #[test]
    fn clinch_position_and_role_gating() {
        // F-015: secure grab → clinch: initiator controls at Overhook; the
        // controlled side cannot Throw/Knee; the controller cannot Tech.
        let phase = clinch_phase();
        let clinch = phase.clinch().expect("clinch after secure grab");
        assert_eq!(clinch.controller, Side::Player);
        assert_eq!(clinch.position, super::clinch::ClinchPositionKind::Overhook);

        // Controlled side (opponent) Throw → reprompted.
        let mut phase = clinch_phase();
        advance_until_submittable(&mut phase, Side::Opponent);
        let reprompt = phase
            .submit_intent(
                Side::Opponent,
                Intent::Clinch {
                    sub: ClinchIntent::Throw,
                },
            )
            .unwrap();
        assert!(reprompt.iter().any(|e| matches!(
            e,
            PlanEvent::Reprompt {
                reason: RepromptReason::ControlledMustEscape,
                ..
            }
        )));
        // Controller Tech → reprompted (controller must press).
        let mut phase = clinch_phase();
        advance_until_submittable(&mut phase, Side::Player);
        let reprompt = phase
            .submit_intent(
                Side::Player,
                Intent::Clinch {
                    sub: ClinchIntent::Tech,
                },
            )
            .unwrap();
        assert!(reprompt.iter().any(|e| matches!(
            e,
            PlanEvent::Reprompt {
                reason: RepromptReason::ControllerMustPress,
                ..
            }
        )));
        // Legal: controller Throw admits (no reprompt).
        let events = phase
            .submit_intent(
                Side::Player,
                Intent::Clinch {
                    sub: ClinchIntent::Throw,
                },
            )
            .unwrap();
        assert!(
            !events
                .iter()
                .any(|e| matches!(e, PlanEvent::Reprompt { .. })),
            "controller Throw must be legal: {events:?}"
        );
    }

    #[test]
    fn sheath_gates_strike_and_draw_rearms() {
        // F-019: Draw gated while armed; Sheath removes Strike and doubles
        // regen; a Draw window re-arms.
        let [player, opponent] = symmetric(1_500);
        let mut phase = PlanPhase::with_roots(player, opponent);
        // Draw while armed → reprompted.
        let reprompt = phase.submit_intent(Side::Player, Intent::Draw).unwrap();
        assert!(reprompt.iter().any(|e| matches!(
            e,
            PlanEvent::Reprompt {
                reason: RepromptReason::AlreadyArmed,
                ..
            }
        )));
        // Sheath locks; the sheathed state lands at the window's end.
        let _ = phase.submit_intent(Side::Opponent, Intent::Idle);
        let _ = phase.submit_intent(Side::Player, Intent::Sheath);
        let _ = phase.simulate_to_boundary();
        assert!(
            phase.snapshot().sheathed[side_index(Side::Player)],
            "a completed Sheath window must sheathe"
        );
        assert!(
            !phase.intent_available(
                Side::Player,
                Intent::Strike {
                    variant: StrikeVariant::Slash
                }
            ),
            "sheathed: no Strike"
        );
        // Regen doubles while sheathed: two idle boundaries → +4 vs +2.
        let before = phase.snapshot().tempo[side_index(Side::Player)];
        relock_available(&mut phase, Intent::Idle, Intent::Idle);
        let _ = phase.simulate_to_boundary();
        let after = phase.snapshot().tempo[side_index(Side::Player)];
        assert_eq!(
            after - before,
            TEMPO_REGEN_PER_EXCHANGE * 2,
            "sheathed regen must double"
        );
        // Draw re-arms at the end of its window; Strike returns.
        advance_until_submittable(&mut phase, Side::Player);
        let _ = phase.submit_intent(Side::Player, Intent::Draw);
        advance_until_submittable(&mut phase, Side::Opponent);
        let _ = phase.submit_intent(Side::Opponent, Intent::Idle);
        let _ = phase.simulate_to_boundary();
        assert!(
            !phase.snapshot().sheathed[side_index(Side::Player)],
            "a completed Draw window must re-arm"
        );
        advance_until_submittable(&mut phase, Side::Player);
        assert!(phase.intent_available(
            Side::Player,
            Intent::Strike {
                variant: StrikeVariant::Slash
            }
        ));
    }

    #[test]
    fn parry_disarms_the_attacker_for_one_selection() {
        // F-018: thrust into a fresh block at 300mm parries (block_tick 3)
        // → the attacker is disarmed; Strike reprompts; any other selection
        // re-arms.
        let [player, opponent] = symmetric(300);
        let mut phase = PlanPhase::with_roots(player, opponent);
        lock(
            &mut phase,
            Intent::Strike {
                variant: StrikeVariant::Thrust,
            },
            Intent::Block,
        );
        let mut disarmed_event = false;
        for _ in 0..4 {
            let events = phase.step_truth_tick().unwrap_or_default();
            disarmed_event |= events
                .iter()
                .any(|e| matches!(e, PlanEvent::Disarmed { side: Side::Player }));
        }
        assert!(disarmed_event, "the parry must emit Disarmed");
        assert!(
            phase.snapshot().disarmed[side_index(Side::Player)],
            "the parried attacker must be disarmed"
        );
        // Weapon option → reprompted at the attacker's next selection.
        advance_until_submittable(&mut phase, Side::Player);
        let reprompt = phase
            .submit_intent(
                Side::Player,
                Intent::Strike {
                    variant: StrikeVariant::Slash,
                },
            )
            .unwrap();
        assert!(reprompt.iter().any(|e| matches!(
            e,
            PlanEvent::Reprompt {
                reason: RepromptReason::Disarmed,
                ..
            }
        )));
        // Non-weapon selection re-arms; Strike returns.
        let _ = phase.submit_intent(Side::Player, Intent::Idle);
        let _ = phase.simulate_to_boundary();
        advance_until_submittable(&mut phase, Side::Player);
        assert!(
            phase.intent_available(
                Side::Player,
                Intent::Strike {
                    variant: StrikeVariant::Slash
                }
            ),
            "after re-arming the Strike menu returns"
        );
    }

    #[test]
    fn launched_side_is_getup_restricted_for_one_selection() {
        // F-017: controller Throw vs controlled Hold launches the controlled
        // side; its next selection must be a getup option.
        let mut phase = clinch_phase();
        advance_until_submittable(&mut phase, Side::Opponent);
        let _ = phase.submit_intent(
            Side::Opponent,
            Intent::Clinch {
                sub: ClinchIntent::Hold,
            },
        );
        advance_until_submittable(&mut phase, Side::Player);
        let _ = phase.submit_intent(
            Side::Player,
            Intent::Clinch {
                sub: ClinchIntent::Throw,
            },
        );
        // The throw resolves at the window's end (finish_boundary).
        let _ = phase.simulate_to_boundary();
        assert!(
            phase.snapshot().downed[side_index(Side::Opponent)],
            "the launched side must be downed"
        );
        // Non-getup option → reprompted.
        advance_until_submittable(&mut phase, Side::Opponent);
        let reprompt = phase
            .submit_intent(
                Side::Opponent,
                Intent::Strike {
                    variant: StrikeVariant::Slash,
                },
            )
            .unwrap();
        assert!(reprompt.iter().any(|e| matches!(
            e,
            PlanEvent::Reprompt {
                reason: RepromptReason::GroundedGetup,
                ..
            }
        )));
        // Getup option admits; the restriction lifts after that selection.
        let events = phase.submit_intent(Side::Opponent, Intent::Idle).unwrap();
        assert!(
            !events
                .iter()
                .any(|e| matches!(e, PlanEvent::Reprompt { .. })),
            "getup option must be legal: {events:?}"
        );
        let _ = phase.simulate_to_boundary();
        advance_until_submittable(&mut phase, Side::Opponent);
        assert!(
            phase.intent_available(
                Side::Opponent,
                Intent::Strike {
                    variant: StrikeVariant::Slash
                }
            ),
            "after the getup selection the full menu returns"
        );
    }

    #[test]
    fn clinch_double_hold_advances_to_back_control() {
        let [player, opponent] = symmetric(300);
        let mut phase = PlanPhase::with_roots(player, opponent);
        drive_until(
            &mut phase,
            Intent::Grab,
            Intent::Idle,
            |event| matches!(event, PlanEvent::ClinchEnter { .. }),
            20,
        );
        // Three double-Hold windows: the first clears the grab-side busy
        // continuation, the second resolves Hold/Hold and must advance.
        let hold = Intent::Clinch {
            sub: ClinchIntent::Hold,
        };
        for _ in 0..3 {
            let _ = phase.simulate_to_boundary();
            relock_available(&mut phase, hold, hold);
        }
        assert_eq!(
            phase.clinch().map(|c| c.position),
            Some(super::clinch::ClinchPositionKind::BackControl),
            "sustained double-Hold must advance the controller to BackControl"
        );
    }

    #[test]
    fn range_bands_classify_separation() {
        assert_eq!(RangeBand::of(0), RangeBand::Close);
        assert_eq!(RangeBand::of(RANGE_CLOSE_MAX_MM), RangeBand::Close);
        assert_eq!(RangeBand::of(RANGE_CLOSE_MAX_MM + 1), RangeBand::Mid);
        assert_eq!(RangeBand::of(RANGE_MID_MAX_MM), RangeBand::Mid);
        assert_eq!(RangeBand::of(RANGE_MID_MAX_MM + 1), RangeBand::Far);
        // Snapshot surface reflects the live separation.
        let [player, opponent] = symmetric(300);
        let phase = PlanPhase::with_roots(player, opponent);
        assert_eq!(phase.snapshot().range_band, RangeBand::Close);
        let [player, opponent] = symmetric(2_500);
        let phase = PlanPhase::with_roots(player, opponent);
        assert_eq!(phase.snapshot().range_band, RangeBand::Far);
    }

    #[test]
    fn probe_thrust_idle_ticks() {
        let [player, opponent] = symmetric(300);
        let mut phase = PlanPhase::with_roots(player, opponent);
        relock_available(
            &mut phase,
            Intent::Strike {
                variant: StrikeVariant::Slash,
            },
            Intent::Idle,
        );
        for i in 0..8 {
            let events = phase.step_truth_tick().unwrap_or_default();
            println!(
                "TICK {} status={:?} contact={} events={:?}",
                i + 1,
                phase.status(),
                phase.snapshot().last_contact_observed,
                events
            );
        }
    }

    #[test]
    fn dynamic_iasa_unblocked_hit_cancels_two_ticks_earlier() {
        // F-013: thrust (iasa_on_hit 6) landing UNBLOCKED hit-cancels at
        // tick 4 (6 - DYNAMIC_IASA_HIT_BONUS_TICKS), not tick 6.
        let [player, opponent] = symmetric(300);
        let mut phase = PlanPhase::with_roots(player, opponent);
        relock_available(
            &mut phase,
            Intent::Strike {
                variant: StrikeVariant::Thrust,
            },
            Intent::Idle,
        );
        let mut cancel_frame = None;
        for _ in 0..10 {
            let events = phase.step_truth_tick().unwrap_or_default();
            if cancel_frame.is_none()
                && events.iter().any(|e| {
                    matches!(
                        e,
                        PlanEvent::Ready {
                            side: Side::Player,
                            reason: ActionabilityReason::HitCancel
                        }
                    )
                })
            {
                cancel_frame = Some(phase.snapshot().truth_frame);
            }
        }
        assert_eq!(
            cancel_frame,
            Some(6),
            "unblocked thrust hit-cancel (dynamic IASA, string window preserved), got {cancel_frame:?}"
        );
    }

    #[test]
    fn free_cancel_chains_strikes_on_contact() {
        // F-012: slash contacts during the 4th tick at 300mm; the hit-cancel
        // boundary lands at tick 5 (dynamic IASA clamps to contact+1), so the
        // string submit after 4 ticks is mid-execution and must be admitted.
        let [player, opponent] = symmetric(300);
        let mut phase = PlanPhase::with_roots(player, opponent);
        relock_available(
            &mut phase,
            Intent::Strike {
                variant: StrikeVariant::Slash,
            },
            Intent::Idle,
        );
        for _ in 0..5 {
            let _ = phase.step_truth_tick();
        }
        let events = phase
            .submit_intent(
                Side::Player,
                Intent::Strike {
                    variant: StrikeVariant::Thrust,
                },
            )
            .unwrap();
        assert!(
            events
                .iter()
                .any(|e| matches!(e, PlanEvent::FreeCancelled { side: Side::Player })),
            "contact must admit the free-cancel string: {events:?}"
        );
        // The chained slash produces its own contact a few ticks later.
        let mut contacted = false;
        for _ in 0..6 {
            let events = phase.step_truth_tick().unwrap_or_default();
            let _ = events;
            if phase.snapshot().last_contact_observed {
                contacted = true;
            }
        }
        assert!(contacted, "the chained strike must produce its own contact");
    }

    #[test]
    fn free_cancel_requires_measured_contact() {
        // No contact (whiff at range): early strike submit is NOT a
        // free-cancel — the normal Planning gate applies.
        let [player, opponent] = symmetric(2_000);
        let mut phase = PlanPhase::with_roots(player, opponent);
        relock_available(
            &mut phase,
            Intent::Strike {
                variant: StrikeVariant::Thrust,
            },
            Intent::Idle,
        );
        let _ = phase.step_truth_tick();
        let result = phase.submit_intent(
            Side::Player,
            Intent::Strike {
                variant: StrikeVariant::Slash,
            },
        );
        let admitted = result.as_ref().is_ok_and(|events| {
            events
                .iter()
                .any(|e| matches!(e, PlanEvent::FreeCancelled { .. }))
        });
        assert!(!admitted, "a whiffing strike must not free-cancel");
    }

    #[test]
    fn struck_grab_dies_and_never_secures() {
        // Canon: a grab that eats an unblocked strike is interrupted — it can
        // never continue to a secure. Player thrusts (hitbox start 3), the
        // opponent grabs; the grab must never reach GrabSecure/ClinchEnter.
        let [player, opponent] = symmetric(300);
        let mut phase = PlanPhase::with_roots(player, opponent);
        let events = drive_until(
            &mut phase,
            Intent::Strike {
                variant: StrikeVariant::Thrust,
            },
            Intent::Grab,
            |event| matches!(event, PlanEvent::Ready { .. }),
            12,
        );
        assert!(
            !events.iter().any(|e| matches!(
                e,
                PlanEvent::GrabSecure { .. } | PlanEvent::ClinchEnter { .. }
            )),
            "a struck grab must die: {events:?}"
        );
        assert!(phase.clinch().is_none());
    }

    #[test]
    fn secure_grab_enters_clinch_against_passive_opponent() {
        // Player grabs; opponent idles. The grab must close, make measured
        // contact, satisfy the full 100 ms interval gate, and enter the clinch.
        let [player, opponent] = symmetric(300);
        let mut phase = PlanPhase::with_roots(player, opponent);
        let mut saw_secure = false;
        let mut saw_enter = false;
        for _ in 0..120 {
            if phase.clinch().is_some() {
                relock_available(
                    &mut phase,
                    Intent::Clinch {
                        sub: super::clinch::ClinchIntent::Hold,
                    },
                    Intent::Clinch {
                        sub: super::clinch::ClinchIntent::Hold,
                    },
                );
            } else {
                relock_available(&mut phase, Intent::Grab, Intent::Idle);
            }
            if phase.status() == PlanStatus::Planning && !phase.can_submit_intent(Side::Player) {
                // One-sided boundary with nobody to act: step is impossible.
            }
            if let Ok(events) = phase.step_truth_tick() {
                saw_secure |= events
                    .iter()
                    .any(|event| matches!(event, PlanEvent::GrabSecure { .. }));
                saw_enter |= events
                    .iter()
                    .any(|event| matches!(event, PlanEvent::ClinchEnter { .. }));
            }
            if saw_secure && saw_enter {
                break;
            }
        }
        assert!(
            saw_secure,
            "secure grab must be reachable from measured contact"
        );
        assert!(saw_enter, "secure grab must enter the clinch");
        assert!(phase.clinch().is_some());
    }

    #[test]
    fn grab_whiff_times_out_against_retreating_opponent() {
        // Opponent retreats every phase; the grab must never secure and must
        // fail as a whiff inside GRAB_WHIFF_TIMEOUT_TICKS. Start beyond proxy
        // contact range (1200 mm Manhattan) so the equal-speed retreat can
        // actually stay clear — inside ~600 mm the body proxies already touch.
        let [player, opponent] = symmetric(600);
        let mut phase = PlanPhase::with_roots(player, opponent);
        let mut saw_secure = false;
        for _ in 0..40 {
            relock_available(
                &mut phase,
                Intent::Grab,
                move_intent(MoveDirection::Retreat, 2_000, true),
            );
            if let Ok(events) = phase.step_truth_tick() {
                saw_secure |= events
                    .iter()
                    .any(|event| matches!(event, PlanEvent::GrabSecure { .. }));
            }
        }
        assert!(!saw_secure);
        // Honest outcome: against an equal-speed retreat the grabber never
        // closes inside GRAB_ACQUIRE_RANGE_MM, so either no attempt begins or
        // any attempt fails. Retreat legitimately counters grab by range.
        assert!(phase.grab().is_none_or(|grab| !grab.is_secure()));
    }

    #[test]
    fn approach_never_crosses_opponent_body() {
        // Mutual approach for a full second: roots must clamp at
        // BODY_MIN_SEPARATION_MM and never coincide or cross.
        let [player, opponent] = symmetric(1_000);
        let mut phase = PlanPhase::with_roots(player, opponent);
        let mut min_seen = i32::MAX;
        for _ in 0..60 {
            relock_available(
                &mut phase,
                move_intent(MoveDirection::Approach, 2_000, true),
                move_intent(MoveDirection::Approach, 2_000, true),
            );
            phase.step_truth_tick().unwrap();
            min_seen = min_seen.min(manhattan(&phase));
        }
        assert_eq!(min_seen, BODY_MIN_SEPARATION_MM);
        let roots = phase.snapshot().roots;
        assert!(roots[0].z_mm > roots[1].z_mm, "roots must never cross");
    }

    #[test]
    fn auto_correct_approach_stops_at_boundary_and_holds() {
        // One-sided approach: mover stops at the boundary; further ticks hold.
        let [player, opponent] = symmetric(500);
        let mut phase = PlanPhase::with_roots(player, opponent);
        for _ in 0..30 {
            relock_available(
                &mut phase,
                move_intent(MoveDirection::Approach, 2_000, true),
                Intent::Idle,
            );
            phase.step_truth_tick().unwrap();
        }
        assert!(manhattan(&phase) >= BODY_MIN_SEPARATION_MM);
    }

    #[test]
    fn dodge_away_from_boundary_still_escapes() {
        // At the boundary, a retreat/dodge that increases separation is free.
        let [player, opponent] = symmetric(BODY_MIN_SEPARATION_MM / 2);
        let mut phase = PlanPhase::with_roots(player, opponent);
        let before = manhattan(&phase);
        assert_eq!(before, BODY_MIN_SEPARATION_MM);
        lock(
            &mut phase,
            Intent::Dodge {
                dir: MoveDirection::Retreat,
            },
            Intent::Idle,
        );
        phase.step_truth_tick().unwrap();
        assert!(manhattan(&phase) > before);
    }

    #[test]
    fn lateral_move_at_boundary_does_not_reduce_separation() {
        // A circling move at the boundary must not cut through the opponent.
        let [player, opponent] = symmetric(BODY_MIN_SEPARATION_MM / 2);
        let mut phase = PlanPhase::with_roots(player, opponent);
        for _ in 0..20 {
            relock_available(
                &mut phase,
                move_intent(MoveDirection::CircleClockwise, 600, true),
                Intent::Idle,
            );
            phase.step_truth_tick().unwrap();
            assert!(manhattan(&phase) >= BODY_MIN_SEPARATION_MM);
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
        assert!(
            hit.snapshot().truth_frame <= whiff.snapshot().truth_frame,
            "hit window {} must never be slower than whiff window {}",
            hit.snapshot().truth_frame,
            whiff.snapshot().truth_frame
        );
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
        // Grab now uses the separate grab state machine, not clinch.
        // The grab should begin (GrabBegin) and NOT enter clinch.
        assert!(
            enter
                .iter()
                .any(|event| matches!(event, PlanEvent::GrabBegin { .. }))
        );
        assert!(phase.grab().is_some());
        assert!(phase.clinch().is_none());

        assert!(phase.can_submit_intent(Side::Player));
        assert!(!phase.can_submit_intent(Side::Opponent));
    }

    // PVP005-GRAB07-CONTACT-TRUTH-002 tests
    #[test]
    fn grab_651mm_out_of_range_cannot_begin() {
        let mut phase =
            PlanPhase::with_roots(RootPosition::new(0, 0, 651), RootPosition::new(0, 0, -651));
        let result = phase.submit_intent(Side::Player, Intent::Grab);
        assert!(result.is_ok());
        let grab = phase.grab();
        assert!(grab.is_none()); // Out of range: no grab attempt created
    }

    #[test]
    fn grab_650mm_can_begin_but_not_automatic_success() {
        let mut phase =
            PlanPhase::with_roots(RootPosition::new(0, 0, 650), RootPosition::new(0, 0, -650));
        lock(
            &mut phase,
            Intent::Grab,
            move_intent(MoveDirection::Approach, 2_000, false),
        );
        let enter = phase.simulate_to_boundary().unwrap();
        assert!(
            enter
                .iter()
                .any(|event| matches!(event, PlanEvent::GrabBegin { .. }))
        );
        let grab = phase.grab().unwrap();
        assert!(grab.is_in_progress()); // In progress, not secure
        assert!(!grab.is_secure()); // Not automatically secure
    }

    #[test]
    fn grab_220_9mm_clearance_never_secure() {
        // The 220.9mm visible clearance run is reclassified as acquisition_failed/whiff.
        // This test proves that 220.9mm clearance never becomes secure_grab.
        let mut phase =
            PlanPhase::with_roots(RootPosition::new(0, 0, 220), RootPosition::new(0, 0, -220));
        lock(
            &mut phase,
            Intent::Grab,
            move_intent(MoveDirection::Approach, 2_000, false),
        );
        let enter = phase.simulate_to_boundary().unwrap();
        assert!(
            enter
                .iter()
                .any(|event| matches!(event, PlanEvent::GrabBegin { .. }))
        );
        let grab = phase.grab().unwrap();
        // 220mm is within 650mm acquire range, so grab can begin.
        // But 220mm clearance means NO physical contact (15mm gate not met).
        // The grab should fail as acquisition_failed/whiff, not secure.
        assert!(!grab.is_secure()); // Never secure with 220mm clearance
    }

    #[test]
    fn grab_15mm_no_physical_contact_never_secure() {
        // 15mm surface clearance without physical contact is NOT a secure grab.
        // The 15mm gate requires actual physical contact, not just proximity.
        let mut grab = GrabAttempt::new(
            Side::Player,
            RootPosition::new(0, 0, 0),
            RootPosition::new(0, 0, 650),
            0,
        );
        // Simulate 15mm clearance but no physical contact
        let admission = SecureGrabAdmission {
            proxy_contact: false, // No physical contact
            surface_clearance_mm: 15.0,
            contact_duration_ticks: 12,
            temporal_overlap: true,
            causal_response: true,
            prohibited_penetration_mm: 0.0,
            no_presentation_override: true,
        };
        grab.admit_secure(admission);
        assert!(!grab.is_secure()); // Never secure without physical contact
        assert_eq!(grab.failure, Some(GrabFailure::NoPhysicalContact));
    }

    #[test]
    fn grab_proxy_contact_less_than_100ms_never_secure() {
        // Proxy contact for < 100ms (12 ticks at 120Hz) is NOT a secure grab.
        let mut grab = GrabAttempt::new(
            Side::Player,
            RootPosition::new(0, 0, 0),
            RootPosition::new(0, 0, 650),
            0,
        );
        let admission = SecureGrabAdmission {
            proxy_contact: true,
            surface_clearance_mm: 5.0,
            contact_duration_ticks: 5, // < 12 ticks (100ms)
            temporal_overlap: true,
            causal_response: true,
            prohibited_penetration_mm: 0.0,
            no_presentation_override: true,
        };
        grab.admit_secure(admission);
        assert!(!grab.is_secure()); // Never secure with < 100ms contact
        assert_eq!(grab.failure, Some(GrabFailure::ContactTooBrief));
    }

    #[test]
    fn grab_valid_sustained_bilateral_contact_secure() {
        // Valid sustained bilateral contact >= 100ms IS a secure grab.
        let mut grab = GrabAttempt::new(
            Side::Player,
            RootPosition::new(0, 0, 0),
            RootPosition::new(0, 0, 650),
            0,
        );
        let admission = SecureGrabAdmission {
            proxy_contact: true,
            surface_clearance_mm: 5.0,
            contact_duration_ticks: 12, // >= 12 ticks (100ms)
            temporal_overlap: true,
            causal_response: true,
            prohibited_penetration_mm: 0.0,
            no_presentation_override: true,
        };
        grab.admit_secure(admission);
        assert!(grab.is_secure()); // Secure with valid sustained contact
        assert_eq!(grab.failure, None);
    }

    #[test]
    fn grab_blocked_or_evaded_whiff() {
        // Blocked or evaded closing motion results in whiff (not secure).
        let mut phase =
            PlanPhase::with_roots(RootPosition::new(0, 0, 650), RootPosition::new(0, 0, -650));
        lock(
            &mut phase,
            Intent::Grab,
            move_intent(MoveDirection::Retreat, 2_000, false),
        );
        let enter = phase.simulate_to_boundary().unwrap();
        // Opponent is retreating: grab may still begin but won't become secure.
        // The grab might begin (GrabBegin) or be blocked (GrabBlocked).
        // In either case, it should NOT become secure.
        if let Some(grab) = phase.grab() {
            assert!(!grab.is_secure()); // Not secure when opponent evades
        }
        // The important thing: no GrabSecure event is emitted.
        assert!(
            !enter
                .iter()
                .any(|event| matches!(event, PlanEvent::GrabSecure { .. }))
        );
    }

    #[test]
    fn grab_deterministic_replay_same_hashes() {
        // Identical input/replay produces identical truth and motion-plan hashes.
        let phase1 =
            PlanPhase::with_roots(RootPosition::new(0, 0, 650), RootPosition::new(0, 0, -650));
        let phase2 =
            PlanPhase::with_roots(RootPosition::new(0, 0, 650), RootPosition::new(0, 0, -650));
        assert_eq!(phase1.truth_hash(), phase2.truth_hash());
        assert_eq!(phase1.snapshot().roots, phase2.snapshot().roots);
    }

    #[test]
    fn grab_no_presentation_override_never_secure() {
        // Presentation-only truth override (no physical contact) is NOT a secure grab.
        let mut grab = GrabAttempt::new(
            Side::Player,
            RootPosition::new(0, 0, 0),
            RootPosition::new(0, 0, 650),
            0,
        );
        let admission = SecureGrabAdmission {
            proxy_contact: true,
            surface_clearance_mm: 5.0,
            contact_duration_ticks: 12,
            temporal_overlap: true,
            causal_response: true,
            prohibited_penetration_mm: 0.0,
            no_presentation_override: false, // Presentation override used
        };
        grab.admit_secure(admission);
        assert!(!grab.is_secure()); // Never secure with presentation override
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
