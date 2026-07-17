//! Renderer-independent Milestone 3 deterministic duel truth.
//!
//! This module deliberately owns no winit, wgpu, asset, camera, audio, or
//! MotionBricks state. Presentation may consume `Snapshot`; it cannot mutate
//! `Match` except through the same `Input` accepted by tests, replay, and AI.

use serde::{Deserialize, Serialize};

pub const TICK_RATE_HZ: u32 = 60;
pub const ACTIONS: [Action; 4] = [Action::Strike, Action::Block, Action::Grab, Action::Move];
const MOVE_MM_PER_REVEAL_TICK: i32 = 25;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Side {
    Player,
    Opponent,
}

impl Side {
    pub const fn other(self) -> Self {
        match self {
            Self::Player => Self::Opponent,
            Self::Opponent => Self::Player,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Action {
    Strike,
    Block,
    Grab,
    Move,
}

impl Action {
    pub const fn index(self) -> usize {
        match self {
            Self::Strike => 0,
            Self::Block => 1,
            Self::Grab => 2,
            Self::Move => 3,
        }
    }
}

/// Replay-stable radial directional input. Components are signed Q15 in the
/// horizontal combat plane; diagonal keyboard input is normalized before it
/// crosses this authority boundary.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct RadialDi {
    pub right_q15: i16,
    pub forward_q15: i16,
}

impl RadialDi {
    pub const ZERO: Self = Self {
        right_q15: 0,
        forward_q15: 0,
    };

    pub const fn is_zero(self) -> bool {
        self.right_q15 == 0 && self.forward_q15 == 0
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Phase {
    Observe,
    Plan,
    Commit,
    Reveal,
    Resolve,
    Consequence,
    MatchResult,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Outcome {
    PlayerWins,
    OpponentWins,
    Clash,
}

/// Measured defender surface selected from a canonical 120 Hz contact batch.
/// This is physical evidence, never an action-intent label.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ContactSurface {
    Body,
    Guard,
}

/// One reduced contact selected from the two measured physics substeps that
/// compose an authoritative 60 Hz action tick.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct PhysicalContact {
    pub attacker: Side,
    pub surface: ContactSurface,
    pub region: BodyRegion,
    pub severity: u8,
}

/// Complete measured result for one Resolve truth frame.
///
/// `contact: None` is an explicit measured whiff. Absence of this whole batch
/// remains unresolved and must never be converted into a synthetic outcome.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct PhysicalContactBatch {
    pub truth_frame: u32,
    pub contact: Option<PhysicalContact>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContactSubmissionError {
    NotResolving,
    WrongTruthFrame { expected: u32, received: u32 },
    Duplicate,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BodyRegion {
    Head,
    Torso,
    Arms,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Injury {
    pub region: BodyRegion,
    pub severity: u8,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Fighter {
    pub planned: Option<Action>,
    pub radial_di: RadialDi,
    pub displacement_mm: [i32; 2],
    pub committed: bool,
    pub head_injury: u8,
    pub torso_injury: u8,
    pub arm_injury: u8,
}

impl Fighter {
    pub const fn fresh() -> Self {
        Self {
            planned: None,
            radial_di: RadialDi::ZERO,
            displacement_mm: [0; 2],
            committed: false,
            head_injury: 0,
            torso_injury: 0,
            arm_injury: 0,
        }
    }

    pub const fn total_injury(self) -> u8 {
        self.head_injury + self.torso_injury + self.arm_injury
    }

    pub const fn incapacitated(self) -> bool {
        self.head_injury >= 2 || self.torso_injury >= 3 || self.total_injury() >= 5
    }

    fn apply(&mut self, injury: Injury) {
        match injury.region {
            BodyRegion::Head => self.head_injury = self.head_injury.saturating_add(injury.severity),
            BodyRegion::Torso => {
                self.torso_injury = self.torso_injury.saturating_add(injury.severity)
            }
            BodyRegion::Arms => self.arm_injury = self.arm_injury.saturating_add(injury.severity),
        }
    }

    fn clear_exchange(&mut self) {
        self.planned = None;
        self.radial_di = RadialDi::ZERO;
        self.committed = false;
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Snapshot {
    pub seed: u64,
    pub frame: u32,
    pub exchange: u32,
    pub phase: Phase,
    pub phase_frame: u16,
    pub player: Fighter,
    pub opponent: Fighter,
    pub revealed: Option<(Action, Action)>,
    pub last_contact: Option<PhysicalContact>,
    pub last_outcome: Option<Outcome>,
    pub last_injury: Option<(Side, Injury)>,
    pub winner: Option<Side>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Input {
    Select(Action),
    SetRadialDi(RadialDi),
    Commit,
    Restart { seed: u64 },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InputError {
    NotPlanning,
    AlreadyCommitted,
    MissingAction,
    MissingDirection,
    NotTerminal,
}

impl std::fmt::Display for InputError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let message = match self {
            Self::NotPlanning => "input is only legal during Plan",
            Self::AlreadyCommitted => "fighter has already committed this exchange",
            Self::MissingAction => "commit requires a selected action",
            Self::MissingDirection => "Move requires a non-zero radial direction",
            Self::NotTerminal => "restart is only legal after MatchResult",
        };
        f.write_str(message)
    }
}

impl std::error::Error for InputError {}

#[derive(Debug, Clone)]
pub struct Match {
    snapshot: Snapshot,
    pending_physical_contact: Option<PhysicalContactBatch>,
}

impl Match {
    pub fn new(seed: u64) -> Self {
        Self {
            snapshot: Snapshot {
                seed,
                frame: 0,
                exchange: 0,
                phase: Phase::Observe,
                phase_frame: 0,
                player: Fighter::fresh(),
                opponent: Fighter::fresh(),
                revealed: None,
                last_contact: None,
                last_outcome: None,
                last_injury: None,
                winner: None,
            },
            pending_physical_contact: None,
        }
    }

    pub fn snapshot(&self) -> &Snapshot {
        &self.snapshot
    }

    pub fn truth_hash(&self) -> u64 {
        canonical_hash(&self.snapshot)
    }

    /// The single Resolve frame that may accept the next measured packet.
    pub fn expected_contact_frame(&self) -> Option<u32> {
        (self.snapshot.phase == Phase::Resolve && self.pending_physical_contact.is_none())
            .then(|| self.snapshot.frame.saturating_add(1))
    }

    /// Admit one complete measured result for the next Resolve tick.
    ///
    /// The packet is retained until the resolver migration unit. This schema
    /// unit deliberately leaves existing tactical consequences unchanged.
    pub fn submit_physical_contact(
        &mut self,
        batch: PhysicalContactBatch,
    ) -> Result<(), ContactSubmissionError> {
        let Some(expected) = self.expected_contact_frame() else {
            return if self.snapshot.phase == Phase::Resolve {
                Err(ContactSubmissionError::Duplicate)
            } else {
                Err(ContactSubmissionError::NotResolving)
            };
        };
        if batch.truth_frame != expected {
            return Err(ContactSubmissionError::WrongTruthFrame {
                expected,
                received: batch.truth_frame,
            });
        }
        self.pending_physical_contact = Some(batch);
        Ok(())
    }

    pub fn apply(&mut self, side: Side, input: Input) -> Result<(), InputError> {
        match input {
            Input::Restart { seed } => {
                if self.snapshot.phase != Phase::MatchResult {
                    return Err(InputError::NotTerminal);
                }
                *self = Self::new(seed);
                Ok(())
            }
            Input::Select(action) => {
                let fighter = self.fighter_mut(side)?;
                fighter.planned = Some(action);
                Ok(())
            }
            Input::SetRadialDi(radial_di) => {
                let fighter = self.fighter_mut(side)?;
                fighter.radial_di = radial_di;
                Ok(())
            }
            Input::Commit => {
                let fighter = self.fighter_mut(side)?;
                if fighter.planned.is_none() {
                    return Err(InputError::MissingAction);
                }
                if fighter.planned == Some(Action::Move) && fighter.radial_di.is_zero() {
                    return Err(InputError::MissingDirection);
                }
                fighter.committed = true;
                Ok(())
            }
        }
    }

    pub fn tick(&mut self) {
        if self.snapshot.phase == Phase::MatchResult {
            return;
        }
        if self.snapshot.phase == Phase::Resolve && self.pending_physical_contact.is_none() {
            return;
        }
        self.snapshot.frame = self.snapshot.frame.saturating_add(1);
        self.snapshot.phase_frame = self.snapshot.phase_frame.saturating_add(1);
        if self.snapshot.phase == Phase::Reveal {
            apply_move_tick(&mut self.snapshot.player);
            apply_move_tick(&mut self.snapshot.opponent);
        }

        if self.snapshot.phase == Phase::Plan
            && self.snapshot.player.committed
            && self.snapshot.opponent.committed
        {
            self.enter(Phase::Commit);
            return;
        }

        let duration = match self.snapshot.phase {
            Phase::Observe => 6,
            Phase::Plan => return,
            Phase::Commit => 2,
            Phase::Reveal => 12,
            Phase::Resolve => 1,
            Phase::Consequence => 18,
            Phase::MatchResult => return,
        };
        if self.snapshot.phase_frame < duration {
            return;
        }

        match self.snapshot.phase {
            Phase::Observe => self.enter(Phase::Plan),
            Phase::Commit => self.enter(Phase::Reveal),
            Phase::Reveal => self.enter(Phase::Resolve),
            Phase::Resolve => {
                self.resolve();
                if self.snapshot.winner.is_some() {
                    self.enter(Phase::MatchResult);
                } else {
                    self.enter(Phase::Consequence);
                }
            }
            Phase::Consequence => {
                self.snapshot.exchange = self.snapshot.exchange.saturating_add(1);
                self.snapshot.player.clear_exchange();
                self.snapshot.opponent.clear_exchange();
                self.snapshot.revealed = None;
                self.snapshot.last_contact = None;
                self.snapshot.last_injury = None;
                self.enter(Phase::Observe);
            }
            Phase::Plan | Phase::MatchResult => unreachable!(),
        }
    }

    fn fighter_mut(&mut self, side: Side) -> Result<&mut Fighter, InputError> {
        if self.snapshot.phase != Phase::Plan {
            return Err(InputError::NotPlanning);
        }
        let fighter = match side {
            Side::Player => &mut self.snapshot.player,
            Side::Opponent => &mut self.snapshot.opponent,
        };
        if fighter.committed {
            return Err(InputError::AlreadyCommitted);
        }
        Ok(fighter)
    }

    fn enter(&mut self, phase: Phase) {
        self.snapshot.phase = phase;
        self.snapshot.phase_frame = 0;
        if phase == Phase::Resolve {
            self.pending_physical_contact = None;
        }
        if phase == Phase::Reveal {
            self.snapshot.revealed = Some((
                self.snapshot
                    .player
                    .planned
                    .expect("committed player action"),
                self.snapshot
                    .opponent
                    .planned
                    .expect("committed opponent action"),
            ));
        }
    }

    fn resolve(&mut self) {
        let batch = self
            .pending_physical_contact
            .take()
            .expect("Resolve requires an admitted physical packet");
        self.snapshot.last_contact = batch.contact;
        let outcome = match batch.contact {
            None
            | Some(PhysicalContact {
                surface: ContactSurface::Guard,
                ..
            }) => Outcome::Clash,
            Some(PhysicalContact {
                attacker: Side::Player,
                surface: ContactSurface::Body,
                ..
            }) => Outcome::PlayerWins,
            Some(PhysicalContact {
                attacker: Side::Opponent,
                surface: ContactSurface::Body,
                ..
            }) => Outcome::OpponentWins,
        };
        self.snapshot.last_outcome = Some(outcome);
        self.snapshot.last_injury = None;

        if let Some(PhysicalContact {
            attacker,
            surface: ContactSurface::Body,
            region,
            severity,
        }) = batch.contact
        {
            let injury = Injury { region, severity };
            let victim = attacker.other();
            let fighter = match victim {
                Side::Player => &mut self.snapshot.player,
                Side::Opponent => &mut self.snapshot.opponent,
            };
            fighter.apply(injury);
            self.snapshot.last_injury = Some((victim, injury));
        }
        self.snapshot.winner = if self.snapshot.player.incapacitated() {
            Some(Side::Opponent)
        } else if self.snapshot.opponent.incapacitated() {
            Some(Side::Player)
        } else {
            None
        };
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AiStrategy {
    Cycle,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct SeededAi {
    pub seed: u64,
    pub strategy: AiStrategy,
}

impl SeededAi {
    pub const fn new(seed: u64) -> Self {
        Self {
            seed,
            strategy: AiStrategy::Cycle,
        }
    }

    /// Uses only public state. `Snapshot` intentionally has no API exposing an
    /// opponent's uncommitted intent to this policy.
    pub const fn choose(&self, public_exchange: u32) -> Action {
        ACTIONS[((self.seed as u32).wrapping_add(public_exchange) % 3) as usize]
    }

    pub const fn move_di(&self, public_exchange: u32) -> RadialDi {
        const DIAGONAL_Q15: i16 = 23_170;
        const DIRECTIONS: [RadialDi; 8] = [
            RadialDi {
                right_q15: 0,
                forward_q15: i16::MAX,
            },
            RadialDi {
                right_q15: DIAGONAL_Q15,
                forward_q15: DIAGONAL_Q15,
            },
            RadialDi {
                right_q15: i16::MAX,
                forward_q15: 0,
            },
            RadialDi {
                right_q15: DIAGONAL_Q15,
                forward_q15: -DIAGONAL_Q15,
            },
            RadialDi {
                right_q15: 0,
                forward_q15: -i16::MAX,
            },
            RadialDi {
                right_q15: -DIAGONAL_Q15,
                forward_q15: -DIAGONAL_Q15,
            },
            RadialDi {
                right_q15: -i16::MAX,
                forward_q15: 0,
            },
            RadialDi {
                right_q15: -DIAGONAL_Q15,
                forward_q15: DIAGONAL_Q15,
            },
        ];
        DIRECTIONS[((self.seed as u32)
            .rotate_left(5)
            .wrapping_add(public_exchange)
            % 8) as usize]
    }
}

fn apply_move_tick(fighter: &mut Fighter) {
    if fighter.planned != Some(Action::Move) {
        return;
    }
    fighter.displacement_mm[0] =
        fighter.displacement_mm[0].saturating_add(q15_step(fighter.radial_di.right_q15));
    fighter.displacement_mm[1] =
        fighter.displacement_mm[1].saturating_add(q15_step(fighter.radial_di.forward_q15));
}

fn q15_step(value: i16) -> i32 {
    let numerator = i32::from(value) * MOVE_MM_PER_REVEAL_TICK;
    let half = i32::from(i16::MAX) / 2;
    if numerator >= 0 {
        (numerator + half) / i32::from(i16::MAX)
    } else {
        (numerator - half) / i32::from(i16::MAX)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReplayEvent {
    pub frame: u32,
    pub side: Side,
    pub input: Input,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Replay {
    pub version: u16,
    pub seed: u64,
    pub events: Vec<ReplayEvent>,
    #[serde(default)]
    pub physical_contacts: Vec<PhysicalContactBatch>,
    pub hash_trace: Vec<u64>,
}

impl Replay {
    pub fn new(seed: u64) -> Self {
        Self {
            version: 2,
            seed,
            events: Vec::new(),
            physical_contacts: Vec::new(),
            hash_trace: Vec::new(),
        }
    }

    pub fn save(&self, path: &std::path::Path) -> std::io::Result<()> {
        let text = ron::ser::to_string_pretty(self, ron::ser::PrettyConfig::default())
            .expect("Milestone 3 replay serialization");
        std::fs::write(path, text)
    }

    pub fn load(path: &std::path::Path) -> Result<Self, ReplayError> {
        let text = std::fs::read_to_string(path).map_err(ReplayError::Io)?;
        ron::from_str(&text).map_err(ReplayError::Decode)
    }
}

#[derive(Debug)]
pub enum ReplayError {
    Io(std::io::Error),
    Decode(ron::error::SpannedError),
    Input {
        frame: u32,
        error: InputError,
    },
    PhysicalContact {
        frame: u32,
        error: ContactSubmissionError,
    },
    MissingPhysicalContact {
        frame: u32,
    },
    HashMismatch {
        frame: u32,
        expected: u64,
        actual: u64,
    },
}

impl std::fmt::Display for ReplayError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(error) => write!(f, "replay I/O: {error}"),
            Self::Decode(error) => write!(f, "replay decode: {error}"),
            Self::Input { frame, error } => write!(f, "replay input at frame {frame}: {error:?}"),
            Self::PhysicalContact { frame, error } => {
                write!(f, "replay physical contact at frame {frame}: {error:?}")
            }
            Self::MissingPhysicalContact { frame } => {
                write!(
                    f,
                    "replay missing physical contact for Resolve frame {frame}"
                )
            }
            Self::HashMismatch {
                frame,
                expected,
                actual,
            } => write!(
                f,
                "replay hash mismatch at frame {frame}: {expected:016x} != {actual:016x}"
            ),
        }
    }
}

impl std::error::Error for ReplayError {}

/// Mutable recording façade. The exact same `apply`/`tick` paths are used for
/// interactive play, scripted verification, and replay playback.
pub struct Session {
    pub game: Match,
    pub replay: Replay,
}

impl Session {
    pub fn new(seed: u64) -> Self {
        let game = Match::new(seed);
        let mut replay = Replay::new(seed);
        replay.hash_trace.push(game.truth_hash());
        Self { game, replay }
    }

    pub fn apply(&mut self, side: Side, input: Input) -> Result<(), InputError> {
        self.game.apply(side, input)?;
        self.replay.events.push(ReplayEvent {
            frame: self.game.snapshot().frame,
            side,
            input,
        });
        Ok(())
    }

    pub fn submit_physical_contact(
        &mut self,
        batch: PhysicalContactBatch,
    ) -> Result<(), ContactSubmissionError> {
        self.game.submit_physical_contact(batch)?;
        self.replay.physical_contacts.push(batch);
        Ok(())
    }

    pub fn tick(&mut self) {
        if self.game.snapshot().phase == Phase::MatchResult {
            return;
        }
        self.game.tick();
        self.replay.hash_trace.push(self.game.truth_hash());
    }
}

pub fn replay(replay: &Replay) -> Result<Match, ReplayError> {
    let mut game = Match::new(replay.seed);
    let mut events = replay.events.iter().peekable();
    let mut physical_contacts = replay.physical_contacts.iter().peekable();
    let mut trace_index = 0usize;
    verify_hash(&game, replay, trace_index)?;
    trace_index += 1;
    while trace_index < replay.hash_trace.len() {
        while let Some(event) = events.peek() {
            if event.frame != game.snapshot().frame {
                break;
            }
            let event = events.next().expect("peeked event");
            game.apply(event.side, event.input)
                .map_err(|error| ReplayError::Input {
                    frame: event.frame,
                    error,
                })?;
        }
        if let Some(expected) = game.expected_contact_frame() {
            let Some(batch) = physical_contacts.next() else {
                return Err(ReplayError::MissingPhysicalContact { frame: expected });
            };
            game.submit_physical_contact(*batch)
                .map_err(|error| ReplayError::PhysicalContact {
                    frame: batch.truth_frame,
                    error,
                })?;
        }
        game.tick();
        verify_hash(&game, replay, trace_index)?;
        trace_index += 1;
    }
    Ok(game)
}

fn verify_hash(game: &Match, replay: &Replay, trace_index: usize) -> Result<(), ReplayError> {
    let actual = game.truth_hash();
    let expected = replay.hash_trace[trace_index];
    if actual == expected {
        Ok(())
    } else {
        Err(ReplayError::HashMismatch {
            frame: game.snapshot().frame,
            expected,
            actual,
        })
    }
}

fn canonical_hash(snapshot: &Snapshot) -> u64 {
    let mut bytes = Vec::with_capacity(64);
    bytes.extend_from_slice(&snapshot.seed.to_le_bytes());
    bytes.extend_from_slice(&snapshot.frame.to_le_bytes());
    bytes.extend_from_slice(&snapshot.exchange.to_le_bytes());
    bytes.push(snapshot.phase as u8);
    bytes.extend_from_slice(&snapshot.phase_frame.to_le_bytes());
    write_fighter(&mut bytes, snapshot.player);
    write_fighter(&mut bytes, snapshot.opponent);
    write_opt_actions(&mut bytes, snapshot.revealed);
    write_opt_contact(&mut bytes, snapshot.last_contact);
    write_opt_outcome(&mut bytes, snapshot.last_outcome);
    write_opt_injury(&mut bytes, snapshot.last_injury);
    write_opt_side(&mut bytes, snapshot.winner);
    fnv1a(&bytes)
}

fn write_fighter(bytes: &mut Vec<u8>, fighter: Fighter) {
    bytes.push(fighter.planned.map_or(255, |action| action as u8));
    bytes.push(u8::from(fighter.committed));
    bytes.push(fighter.head_injury);
    bytes.push(fighter.torso_injury);
    bytes.push(fighter.arm_injury);
}

fn write_opt_actions(bytes: &mut Vec<u8>, actions: Option<(Action, Action)>) {
    match actions {
        Some((player, opponent)) => bytes.extend_from_slice(&[1, player as u8, opponent as u8]),
        None => bytes.push(0),
    }
}

fn write_opt_contact(bytes: &mut Vec<u8>, contact: Option<PhysicalContact>) {
    match contact {
        Some(contact) => bytes.extend_from_slice(&[
            1,
            contact.attacker as u8,
            contact.surface as u8,
            contact.region as u8,
            contact.severity,
        ]),
        None => bytes.push(0),
    }
}

fn write_opt_outcome(bytes: &mut Vec<u8>, outcome: Option<Outcome>) {
    bytes.push(outcome.map_or(255, |outcome| outcome as u8));
}

fn write_opt_injury(bytes: &mut Vec<u8>, injury: Option<(Side, Injury)>) {
    match injury {
        Some((side, injury)) => {
            bytes.extend_from_slice(&[1, side as u8, injury.region as u8, injury.severity])
        }
        None => bytes.push(0),
    }
}

fn write_opt_side(bytes: &mut Vec<u8>, side: Option<Side>) {
    bytes.push(side.map_or(255, |side| side as u8));
}

fn fnv1a(bytes: &[u8]) -> u64 {
    let mut hash = 0xcbf2_9ce4_8422_2325_u64;
    for byte in bytes {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
    hash
}

#[cfg(test)]
mod tests {
    use super::*;

    fn to_plan(session: &mut Session) {
        while session.game.snapshot().phase != Phase::Plan {
            session.tick();
        }
    }

    fn resolve_exchange(session: &mut Session, player: Action, opponent: Action) {
        to_plan(session);
        session.apply(Side::Player, Input::Select(player)).unwrap();
        session
            .apply(Side::Opponent, Input::Select(opponent))
            .unwrap();
        session.apply(Side::Player, Input::Commit).unwrap();
        session.apply(Side::Opponent, Input::Commit).unwrap();
        while session.game.snapshot().phase != Phase::Resolve {
            session.tick();
        }
        session
            .submit_physical_contact(PhysicalContactBatch {
                truth_frame: session.game.expected_contact_frame().unwrap(),
                contact: Some(PhysicalContact {
                    attacker: Side::Player,
                    surface: ContactSurface::Body,
                    region: BodyRegion::Torso,
                    severity: 1,
                }),
            })
            .unwrap();
        while session.game.snapshot().phase != Phase::Consequence
            && session.game.snapshot().phase != Phase::MatchResult
        {
            session.tick();
        }
    }

    fn to_resolve(game: &mut Match) {
        while game.snapshot().phase != Phase::Plan {
            game.tick();
        }
        game.apply(Side::Player, Input::Select(Action::Strike))
            .unwrap();
        game.apply(Side::Opponent, Input::Select(Action::Block))
            .unwrap();
        game.apply(Side::Player, Input::Commit).unwrap();
        game.apply(Side::Opponent, Input::Commit).unwrap();
        while game.snapshot().phase != Phase::Resolve {
            game.tick();
        }
    }

    #[test]
    fn physical_packet_admission_is_frame_exact_and_single_use() {
        let mut game = Match::new(9);
        assert_eq!(
            game.submit_physical_contact(PhysicalContactBatch {
                truth_frame: 1,
                contact: None,
            }),
            Err(ContactSubmissionError::NotResolving)
        );

        to_resolve(&mut game);
        let expected = game.expected_contact_frame().unwrap();
        let body_hit = PhysicalContactBatch {
            truth_frame: expected,
            contact: Some(PhysicalContact {
                attacker: Side::Player,
                surface: ContactSurface::Body,
                region: BodyRegion::Torso,
                severity: 1,
            }),
        };
        assert_eq!(
            game.submit_physical_contact(PhysicalContactBatch {
                truth_frame: expected.saturating_add(1),
                ..body_hit
            }),
            Err(ContactSubmissionError::WrongTruthFrame {
                expected,
                received: expected.saturating_add(1),
            })
        );
        assert_eq!(game.submit_physical_contact(body_hit), Ok(()));
        assert_eq!(
            game.submit_physical_contact(body_hit),
            Err(ContactSubmissionError::Duplicate)
        );
    }

    #[test]
    fn resolve_holds_without_a_measured_packet() {
        let mut game = Match::new(10);
        to_resolve(&mut game);
        let before = game.snapshot().clone();
        let before_hash = game.truth_hash();
        game.tick();
        assert_eq!(game.snapshot(), &before);
        assert_eq!(game.truth_hash(), before_hash);
    }

    #[test]
    fn body_packet_overrides_action_labels_and_guard_packet_causes_no_injury() {
        let mut body_game = Match::new(11);
        to_resolve(&mut body_game); // Strike vs Block would have favored Opponent in the removed matrix.
        body_game
            .submit_physical_contact(PhysicalContactBatch {
                truth_frame: body_game.expected_contact_frame().unwrap(),
                contact: Some(PhysicalContact {
                    attacker: Side::Player,
                    surface: ContactSurface::Body,
                    region: BodyRegion::Head,
                    severity: 2,
                }),
            })
            .unwrap();
        body_game.tick();
        assert_eq!(body_game.snapshot().last_outcome, Some(Outcome::PlayerWins));
        assert_eq!(body_game.snapshot().winner, Some(Side::Player));
        assert_eq!(body_game.snapshot().opponent.head_injury, 2);

        let mut guard_game = Match::new(12);
        to_resolve(&mut guard_game);
        guard_game
            .submit_physical_contact(PhysicalContactBatch {
                truth_frame: guard_game.expected_contact_frame().unwrap(),
                contact: Some(PhysicalContact {
                    attacker: Side::Opponent,
                    surface: ContactSurface::Guard,
                    region: BodyRegion::Arms,
                    severity: 9,
                }),
            })
            .unwrap();
        guard_game.tick();
        assert_eq!(guard_game.snapshot().last_outcome, Some(Outcome::Clash));
        assert_eq!(guard_game.snapshot().player.total_injury(), 0);
        assert_eq!(guard_game.snapshot().opponent.total_injury(), 0);
    }

    #[test]
    fn reveal_requires_both_commits_and_ai_cannot_read_hidden_player_action() {
        let mut game = Match::new(7);
        while game.snapshot().phase != Phase::Plan {
            game.tick();
        }
        let ai = SeededAi::new(7);
        let public_exchange = game.snapshot().exchange;
        let before = ai.choose(public_exchange);
        game.apply(Side::Player, Input::Select(Action::Grab))
            .unwrap();
        assert_eq!(ai.choose(public_exchange), before);
        game.apply(Side::Opponent, Input::Select(before)).unwrap();
        game.apply(Side::Opponent, Input::Commit).unwrap();
        for _ in 0..120 {
            game.tick();
        }
        assert_eq!(game.snapshot().phase, Phase::Plan);
        game.apply(Side::Player, Input::Commit).unwrap();
        game.tick();
        assert_eq!(game.snapshot().phase, Phase::Commit);
    }

    #[test]
    fn localized_injury_ends_match_and_restart_is_terminal_only() {
        let mut session = Session::new(2);
        while session.game.snapshot().phase != Phase::MatchResult {
            resolve_exchange(&mut session, Action::Strike, Action::Grab);
            if session.game.snapshot().phase != Phase::MatchResult {
                while session.game.snapshot().phase != Phase::Observe {
                    session.tick();
                }
            }
        }
        assert_eq!(session.game.snapshot().winner, Some(Side::Player));
        assert!(session.game.snapshot().opponent.incapacitated());
        assert_eq!(
            session.apply(Side::Player, Input::Restart { seed: 99 }),
            Ok(())
        );
        assert_eq!(session.game.snapshot().phase, Phase::Observe);
        assert_eq!(session.game.snapshot().seed, 99);
    }

    #[test]
    fn terminal_session_does_not_append_post_result_replay_ticks() {
        let mut session = Session::new(0x4d33);
        while session.game.snapshot().phase != Phase::MatchResult {
            resolve_exchange(&mut session, Action::Strike, Action::Grab);
            while matches!(
                session.game.snapshot().phase,
                Phase::Consequence | Phase::Observe
            ) {
                session.tick();
            }
        }

        let terminal = session.game.snapshot().clone();
        let terminal_hash = session.game.truth_hash();
        let terminal_trace_len = session.replay.hash_trace.len();
        for _ in 0..8 {
            session.tick();
        }

        assert_eq!(session.game.snapshot(), &terminal);
        assert_eq!(session.game.truth_hash(), terminal_hash);
        assert_eq!(session.replay.hash_trace.len(), terminal_trace_len);
    }

    #[test]
    fn replay_reconstructs_every_hash_of_a_complete_match() {
        let mut session = Session::new(1234);
        while session.game.snapshot().phase != Phase::MatchResult {
            resolve_exchange(&mut session, Action::Strike, Action::Grab);
            while session.game.snapshot().phase == Phase::Consequence
                || session.game.snapshot().phase == Phase::Observe
            {
                session.tick();
            }
        }
        let replayed = replay(&session.replay).unwrap();
        assert_eq!(replayed.snapshot(), session.game.snapshot());
        assert_eq!(replayed.truth_hash(), session.game.truth_hash());
    }

    #[test]
    fn one_hundred_replay_reconstructions_keep_the_same_truth_hash() {
        let mut session = Session::new(0x4d33_1000);
        while session.game.snapshot().phase != Phase::MatchResult {
            resolve_exchange(&mut session, Action::Strike, Action::Grab);
            while session.game.snapshot().phase == Phase::Consequence
                || session.game.snapshot().phase == Phase::Observe
            {
                session.tick();
            }
        }
        let expected_snapshot = session.game.snapshot();
        let expected_hash = session.game.truth_hash();
        for _ in 0..100 {
            let replayed = replay(&session.replay).unwrap();
            assert_eq!(replayed.snapshot(), expected_snapshot);
            assert_eq!(replayed.truth_hash(), expected_hash);
        }
    }

    #[test]
    fn move_requires_radial_di_and_advances_in_replay_stable_millimetres() {
        let mut session = Session::new(0x4d30_5633);
        while session.game.snapshot().phase != Phase::Plan {
            session.tick();
        }
        session
            .apply(Side::Player, Input::Select(Action::Move))
            .unwrap();
        assert_eq!(
            session.apply(Side::Player, Input::Commit),
            Err(InputError::MissingDirection)
        );
        session
            .apply(
                Side::Player,
                Input::SetRadialDi(RadialDi {
                    right_q15: i16::MAX,
                    forward_q15: 0,
                }),
            )
            .unwrap();
        session.apply(Side::Player, Input::Commit).unwrap();
        session
            .apply(Side::Opponent, Input::Select(Action::Block))
            .unwrap();
        session.apply(Side::Opponent, Input::Commit).unwrap();
        while session.game.snapshot().phase != Phase::Resolve {
            session.tick();
        }
        assert_eq!(session.game.snapshot().player.displacement_mm, [300, 0]);
        session
            .submit_physical_contact(PhysicalContactBatch {
                truth_frame: session.game.expected_contact_frame().unwrap(),
                contact: None,
            })
            .unwrap();
        session.tick();

        let replayed = replay(&session.replay).unwrap();
        assert_eq!(replayed.snapshot(), session.game.snapshot());
        assert_eq!(replayed.truth_hash(), session.game.truth_hash());
    }

    #[test]
    fn canonical_hash_is_not_affected_by_an_independent_snapshot_clone() {
        let match_a = Match::new(8);
        let match_b = match_a.clone();
        assert_eq!(match_a.truth_hash(), match_b.truth_hash());
    }
}
