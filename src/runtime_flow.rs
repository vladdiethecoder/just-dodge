//! Truth-isolated outer player flow and deterministic replay playback.
//!
//! Menu, establishing, result, and replay are presentation states. They may
//! decide when the existing Milestone 3 session advances, but they never write
//! combat state or fabricate replay events.

use crate::milestone3 as m3;

pub const ESTABLISHING_TICKS: u16 = 90;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Screen {
    Menu,
    Establishing,
    Duel,
    Replay,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FlowStage {
    Menu,
    Establishing,
    Observe,
    Replan,
    Plan,
    Commit,
    Reveal,
    Resolve,
    Consequence,
    Result,
    Replay,
}

impl FlowStage {
    pub const fn captures_cursor(self) -> bool {
        matches!(
            self,
            Self::Observe
                | Self::Replan
                | Self::Plan
                | Self::Commit
                | Self::Reveal
                | Self::Resolve
                | Self::Consequence
        )
    }
}

pub struct ReplayCursor {
    replay: m3::Replay,
    game: m3::Match,
    event_index: usize,
    contact_index: usize,
    trace_index: usize,
    total_exchanges: u16,
}

impl ReplayCursor {
    pub fn new(replay: m3::Replay) -> Result<Self, String> {
        if replay.hash_trace.is_empty() {
            return Err("replay has no initial truth hash".to_string());
        }
        m3::replay(&replay).map_err(|error| format!("replay validation failed: {error}"))?;
        let game = m3::Match::new(replay.seed);
        if game.truth_hash() != replay.hash_trace[0] {
            return Err("replay initial truth hash does not match its seed".to_string());
        }
        let total_exchanges = replay
            .events
            .iter()
            .filter(|event| event.side == m3::Side::Player && event.input == m3::Input::Commit)
            .count()
            .try_into()
            .map_err(|_| "replay has more exchanges than the cinematic timeline supports")?;
        Ok(Self {
            replay,
            game,
            event_index: 0,
            contact_index: 0,
            trace_index: 1,
            total_exchanges,
        })
    }

    pub fn snapshot(&self) -> &m3::Snapshot {
        self.game.snapshot()
    }

    pub fn is_finished(&self) -> bool {
        self.trace_index >= self.replay.hash_trace.len()
    }

    pub const fn total_exchanges(&self) -> u16 {
        self.total_exchanges
    }

    pub fn advance(&mut self) -> Result<bool, String> {
        if self.is_finished() {
            return Ok(false);
        }

        while let Some(event) = self.replay.events.get(self.event_index) {
            if event.frame != self.game.snapshot().frame {
                break;
            }
            self.game
                .apply(event.side, event.input)
                .map_err(|error| format!("replay input at frame {}: {error}", event.frame))?;
            self.event_index += 1;
        }

        if let Some(expected_frame) = self.game.expected_contact_frame() {
            let batch = self
                .replay
                .physical_contacts
                .get(self.contact_index)
                .ok_or_else(|| {
                    format!("replay missing physical contact for frame {expected_frame}")
                })?;
            self.game.submit_physical_contact(*batch).map_err(|error| {
                format!(
                    "replay physical contact at frame {}: {error:?}",
                    batch.truth_frame
                )
            })?;
            self.contact_index += 1;
        }

        self.game.tick();
        let expected_hash = self.replay.hash_trace[self.trace_index];
        let actual_hash = self.game.truth_hash();
        if actual_hash != expected_hash {
            return Err(format!(
                "replay hash mismatch at frame {}: {expected_hash:016x} != {actual_hash:016x}",
                self.game.snapshot().frame
            ));
        }
        self.trace_index += 1;
        Ok(true)
    }

    pub fn advance_cinematic(&mut self) -> Result<bool, String> {
        loop {
            if !self.advance()? {
                return Ok(false);
            }
            if matches!(
                self.snapshot().phase,
                m3::Phase::Commit
                    | m3::Phase::Reveal
                    | m3::Phase::Resolve
                    | m3::Phase::Consequence
                    | m3::Phase::MatchResult
            ) {
                return Ok(true);
            }
        }
    }
}

pub struct RuntimeFlow {
    screen: Screen,
    establishing_elapsed: u16,
    replay: Option<ReplayCursor>,
}

impl RuntimeFlow {
    pub const fn menu() -> Self {
        Self {
            screen: Screen::Menu,
            establishing_elapsed: 0,
            replay: None,
        }
    }

    pub const fn autoplay() -> Self {
        Self {
            screen: Screen::Duel,
            establishing_elapsed: ESTABLISHING_TICKS,
            replay: None,
        }
    }

    pub fn stage(&self, snapshot: &m3::Snapshot) -> FlowStage {
        match self.screen {
            Screen::Menu => FlowStage::Menu,
            Screen::Establishing => FlowStage::Establishing,
            Screen::Replay => FlowStage::Replay,
            Screen::Duel => match snapshot.phase {
                m3::Phase::Observe if snapshot.exchange > 0 => FlowStage::Replan,
                m3::Phase::Observe => FlowStage::Observe,
                m3::Phase::Plan => FlowStage::Plan,
                m3::Phase::Commit => FlowStage::Commit,
                m3::Phase::Reveal => FlowStage::Reveal,
                m3::Phase::Resolve => FlowStage::Resolve,
                m3::Phase::Consequence => FlowStage::Consequence,
                m3::Phase::MatchResult => FlowStage::Result,
            },
        }
    }

    pub fn start_match(&mut self) -> bool {
        if self.screen != Screen::Menu {
            return false;
        }
        self.begin_establishing();
        true
    }

    pub fn begin_rematch(&mut self) -> bool {
        if !matches!(self.screen, Screen::Duel | Screen::Replay) {
            return false;
        }
        self.begin_establishing();
        true
    }

    fn begin_establishing(&mut self) {
        self.screen = Screen::Establishing;
        self.establishing_elapsed = 0;
        self.replay = None;
    }

    pub fn back_to_menu(&mut self) {
        self.screen = Screen::Menu;
        self.establishing_elapsed = 0;
        self.replay = None;
    }

    pub fn tick_establishing(&mut self) -> bool {
        if self.screen != Screen::Establishing {
            return false;
        }
        self.establishing_elapsed = self.establishing_elapsed.saturating_add(1);
        if self.establishing_elapsed >= ESTABLISHING_TICKS {
            self.screen = Screen::Duel;
            return true;
        }
        false
    }

    pub const fn establishing_remaining(&self) -> u16 {
        ESTABLISHING_TICKS.saturating_sub(self.establishing_elapsed)
    }

    pub fn enter_replay(
        &mut self,
        snapshot: &m3::Snapshot,
        replay: m3::Replay,
    ) -> Result<(), String> {
        if self.stage(snapshot) != FlowStage::Result {
            return Err("replay is only available from Result".to_string());
        }
        self.replay = Some(ReplayCursor::new(replay)?);
        self.screen = Screen::Replay;
        Ok(())
    }

    pub fn advance_replay(&mut self) -> Result<bool, String> {
        let replay = self
            .replay
            .as_mut()
            .ok_or_else(|| "replay playback is not active".to_string())?;
        replay.advance_cinematic()
    }

    pub fn replay_snapshot(&self) -> Option<&m3::Snapshot> {
        self.replay.as_ref().map(ReplayCursor::snapshot)
    }

    pub fn replay_total_exchanges(&self) -> Option<u16> {
        self.replay.as_ref().map(ReplayCursor::total_exchanges)
    }

    pub fn replay_finished(&self) -> bool {
        self.replay.as_ref().is_some_and(ReplayCursor::is_finished)
    }

    pub fn truth_ticks_allowed(&self, snapshot: &m3::Snapshot) -> bool {
        self.screen == Screen::Duel && snapshot.phase != m3::Phase::MatchResult
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn complete_replay(seed: u64) -> m3::Replay {
        let mut session = m3::Session::new(seed);
        while session.game.snapshot().phase != m3::Phase::Plan {
            session.tick();
        }
        session
            .apply(m3::Side::Player, m3::Input::Select(m3::Action::Strike))
            .unwrap();
        session.apply(m3::Side::Player, m3::Input::Commit).unwrap();
        session
            .apply(m3::Side::Opponent, m3::Input::Select(m3::Action::Grab))
            .unwrap();
        session
            .apply(m3::Side::Opponent, m3::Input::Commit)
            .unwrap();
        while session.game.snapshot().phase != m3::Phase::Resolve {
            session.tick();
        }
        let frame = session.game.expected_contact_frame().unwrap();
        session
            .submit_physical_contact(m3::PhysicalContactBatch {
                truth_frame: frame,
                contact: Some(m3::PhysicalContact {
                    attacker: m3::Side::Player,
                    surface: m3::ContactSurface::Body,
                    region: m3::BodyRegion::Head,
                    severity: 2,
                }),
            })
            .unwrap();
        while session.game.snapshot().phase != m3::Phase::MatchResult {
            session.tick();
        }
        session.replay
    }

    fn multi_exchange_replay(seed: u64) -> m3::Replay {
        let mut session = m3::Session::new(seed);
        let exchanges = [
            (m3::Action::Strike, m3::Action::Block),
            (m3::Action::Block, m3::Action::Grab),
            (m3::Action::Move, m3::Action::Strike),
            (m3::Action::Grab, m3::Action::Strike),
        ];
        for (index, (player, opponent)) in exchanges.into_iter().enumerate() {
            while session.game.snapshot().phase != m3::Phase::Plan {
                session.tick();
            }
            session
                .apply(m3::Side::Player, m3::Input::Select(player))
                .unwrap();
            if player == m3::Action::Move {
                session
                    .apply(
                        m3::Side::Player,
                        m3::Input::SetRadialDi(m3::RadialDi {
                            right_q15: i16::MAX,
                            forward_q15: 0,
                        }),
                    )
                    .unwrap();
            }
            session.apply(m3::Side::Player, m3::Input::Commit).unwrap();
            session
                .apply(m3::Side::Opponent, m3::Input::Select(opponent))
                .unwrap();
            session
                .apply(m3::Side::Opponent, m3::Input::Commit)
                .unwrap();
            while session.game.snapshot().phase != m3::Phase::Resolve {
                session.tick();
            }
            let contact = (index + 1 == exchanges.len()).then_some(m3::PhysicalContact {
                attacker: m3::Side::Player,
                surface: m3::ContactSurface::Body,
                region: m3::BodyRegion::Head,
                severity: 2,
            });
            session
                .submit_physical_contact(m3::PhysicalContactBatch {
                    truth_frame: session.game.expected_contact_frame().unwrap(),
                    contact,
                })
                .unwrap();
            session.tick();
            if session.game.snapshot().phase == m3::Phase::MatchResult {
                break;
            }
        }
        session.replay
    }

    #[test]
    fn outer_flow_covers_every_required_stage_and_cursor_policy() {
        let seed = 41;
        let mut flow = RuntimeFlow::menu();
        let snapshot = m3::Match::new(seed).snapshot().clone();
        assert_eq!(flow.stage(&snapshot), FlowStage::Menu);
        assert!(!flow.stage(&snapshot).captures_cursor());
        assert!(flow.start_match());
        assert_eq!(flow.stage(&snapshot), FlowStage::Establishing);
        for _ in 0..ESTABLISHING_TICKS {
            flow.tick_establishing();
        }
        assert_eq!(flow.stage(&snapshot), FlowStage::Observe);
        assert!(flow.stage(&snapshot).captures_cursor());

        let replay = complete_replay(seed);
        let terminal = m3::replay(&replay).unwrap();
        assert_eq!(flow.stage(terminal.snapshot()), FlowStage::Result);
        assert!(!flow.stage(terminal.snapshot()).captures_cursor());
        flow.enter_replay(terminal.snapshot(), replay).unwrap();
        assert_eq!(flow.stage(terminal.snapshot()), FlowStage::Replay);
        assert!(!flow.stage(terminal.snapshot()).captures_cursor());
    }

    #[test]
    fn replay_playback_reconstructs_hashes_without_mutating_live_truth() {
        let replay = complete_replay(73);
        let live = m3::replay(&replay).unwrap();
        let live_hash = live.truth_hash();
        let mut cursor = ReplayCursor::new(replay).unwrap();
        while cursor.advance().unwrap() {}
        assert_eq!(cursor.snapshot(), live.snapshot());
        assert_eq!(live.truth_hash(), live_hash);
    }

    #[test]
    fn cinematic_replay_chains_every_exchange_without_displaying_idle_phases() {
        let replay = multi_exchange_replay(79);
        let terminal = m3::replay(&replay).unwrap();
        let mut cursor = ReplayCursor::new(replay).unwrap();
        assert_eq!(cursor.total_exchanges(), 4);

        let mut exchanges = Vec::new();
        while cursor.advance_cinematic().unwrap() {
            let snapshot = cursor.snapshot();
            assert!(!matches!(
                snapshot.phase,
                m3::Phase::Observe | m3::Phase::Plan
            ));
            if snapshot.phase == m3::Phase::Commit && snapshot.phase_frame == 0 {
                exchanges.push(snapshot.exchange);
            }
        }

        assert_eq!(exchanges, vec![0, 1, 2, 3]);
        assert_eq!(cursor.snapshot(), terminal.snapshot());
    }

    #[test]
    fn menu_and_establishing_never_advance_truth() {
        let game = m3::Match::new(99);
        let initial_hash = game.truth_hash();
        let mut flow = RuntimeFlow::menu();
        assert!(!flow.truth_ticks_allowed(game.snapshot()));
        flow.start_match();
        for _ in 0..ESTABLISHING_TICKS - 1 {
            flow.tick_establishing();
            assert!(!flow.truth_ticks_allowed(game.snapshot()));
        }
        assert_eq!(game.truth_hash(), initial_hash);
    }
}
