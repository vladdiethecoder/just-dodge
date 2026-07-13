//! Renderer-independent Milestone 3 deterministic duel truth.
//!
//! This module deliberately owns no winit, wgpu, asset, camera, audio, or
//! MotionBricks state. Presentation may consume `Snapshot`; it cannot mutate
//! `Match` except through the same `Input` accepted by tests, replay, and AI.

use serde::{Deserialize, Serialize};

pub const TICK_RATE_HZ: u32 = 60;
pub const ACTIONS: [Action; 3] = [Action::Strike, Action::Block, Action::Grab];

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
}

impl Action {
    pub const fn index(self) -> usize {
        match self {
            Self::Strike => 0,
            Self::Block => 1,
            Self::Grab => 2,
        }
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

/// Exhaustive first-playable resolver. Rows are Player action, columns are
/// Opponent action, in `ACTIONS` order. This is the sole tactical rule table.
const RESOLVER: [[Outcome; 3]; 3] = [
    [Outcome::Clash, Outcome::OpponentWins, Outcome::PlayerWins],
    [Outcome::PlayerWins, Outcome::Clash, Outcome::OpponentWins],
    [Outcome::OpponentWins, Outcome::PlayerWins, Outcome::Clash],
];

pub const fn resolve_actions(player: Action, opponent: Action) -> Outcome {
    RESOLVER[player.index()][opponent.index()]
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
    pub committed: bool,
    pub head_injury: u8,
    pub torso_injury: u8,
    pub arm_injury: u8,
}

impl Fighter {
    pub const fn fresh() -> Self {
        Self {
            planned: None,
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
    pub last_outcome: Option<Outcome>,
    pub last_injury: Option<(Side, Injury)>,
    pub winner: Option<Side>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Input {
    Select(Action),
    Commit,
    Restart { seed: u64 },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InputError {
    NotPlanning,
    AlreadyCommitted,
    MissingAction,
    NotTerminal,
}

impl std::fmt::Display for InputError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let message = match self {
            Self::NotPlanning => "input is only legal during Plan",
            Self::AlreadyCommitted => "fighter has already committed this exchange",
            Self::MissingAction => "commit requires a selected action",
            Self::NotTerminal => "restart is only legal after MatchResult",
        };
        f.write_str(message)
    }
}

impl std::error::Error for InputError {}

#[derive(Debug, Clone)]
pub struct Match {
    snapshot: Snapshot,
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
                last_outcome: None,
                last_injury: None,
                winner: None,
            },
        }
    }

    pub fn snapshot(&self) -> &Snapshot {
        &self.snapshot
    }

    pub fn truth_hash(&self) -> u64 {
        canonical_hash(&self.snapshot)
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
            Input::Commit => {
                let fighter = self.fighter_mut(side)?;
                if fighter.planned.is_none() {
                    return Err(InputError::MissingAction);
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
        self.snapshot.frame = self.snapshot.frame.saturating_add(1);
        self.snapshot.phase_frame = self.snapshot.phase_frame.saturating_add(1);

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
        let (player_action, opponent_action) =
            self.snapshot.revealed.expect("reveal before resolve");
        let outcome = resolve_actions(player_action, opponent_action);
        self.snapshot.last_outcome = Some(outcome);
        self.snapshot.last_injury = None;

        let injury = match outcome {
            Outcome::Clash => Injury {
                region: BodyRegion::Arms,
                severity: 1,
            },
            Outcome::PlayerWins | Outcome::OpponentWins => Injury {
                // Alternate torso/head so a complete match demonstrates localized effects.
                region: if self.snapshot.exchange % 2 == 0 {
                    BodyRegion::Torso
                } else {
                    BodyRegion::Head
                },
                severity: 1,
            },
        };
        match outcome {
            Outcome::PlayerWins => {
                self.snapshot.opponent.apply(injury);
                self.snapshot.last_injury = Some((Side::Opponent, injury));
            }
            Outcome::OpponentWins => {
                self.snapshot.player.apply(injury);
                self.snapshot.last_injury = Some((Side::Player, injury));
            }
            Outcome::Clash => {
                self.snapshot.player.apply(injury);
                self.snapshot.opponent.apply(injury);
            }
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
    pub hash_trace: Vec<u64>,
}

impl Replay {
    pub fn new(seed: u64) -> Self {
        Self {
            version: 1,
            seed,
            events: Vec::new(),
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

    pub fn tick(&mut self) {
        self.game.tick();
        self.replay.hash_trace.push(self.game.truth_hash());
    }
}

pub fn replay(replay: &Replay) -> Result<Match, ReplayError> {
    let mut game = Match::new(replay.seed);
    let mut events = replay.events.iter().peekable();
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
        while session.game.snapshot().phase != Phase::Consequence
            && session.game.snapshot().phase != Phase::MatchResult
        {
            session.tick();
        }
    }

    #[test]
    fn resolver_is_exhaustive_and_has_the_required_triangle() {
        let expected = [
            [Outcome::Clash, Outcome::OpponentWins, Outcome::PlayerWins],
            [Outcome::PlayerWins, Outcome::Clash, Outcome::OpponentWins],
            [Outcome::OpponentWins, Outcome::PlayerWins, Outcome::Clash],
        ];
        for (row, player) in ACTIONS.into_iter().enumerate() {
            for (column, opponent) in ACTIONS.into_iter().enumerate() {
                assert_eq!(resolve_actions(player, opponent), expected[row][column]);
            }
        }
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
    fn canonical_hash_is_not_affected_by_an_independent_snapshot_clone() {
        let match_a = Match::new(8);
        let match_b = match_a.clone();
        assert_eq!(match_a.truth_hash(), match_b.truth_hash());
    }
}
