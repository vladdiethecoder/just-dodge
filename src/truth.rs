// Authoritative deterministic combat truth state machine.
// See docs/design/IMPLEMENTATION_PLAN_3ACTION.md for the contract.

use serde::Deserialize;

use crate::action_matrix::{self, ContactType, MatrixResult};

/// One of the two duelists.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, Deserialize)]
pub enum Side {
    Player,
    Opponent,
}

impl Side {
    pub fn opposite(self) -> Self {
        match self {
            Side::Player => Side::Opponent,
            Side::Opponent => Side::Player,
        }
    }
}

/// Current phase of the simultaneous-reveal exchange.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
pub enum Phase {
    Observe,
    Plan,
    Commit,
    Reveal,
    Resolve,
    Consequence,
}

impl Phase {
    fn next(self) -> Self {
        match self {
            Phase::Observe => Phase::Plan,
            Phase::Plan => Phase::Commit,
            Phase::Commit => Phase::Reveal,
            Phase::Reveal => Phase::Resolve,
            Phase::Resolve => Phase::Consequence,
            Phase::Consequence => Phase::Observe,
        }
    }

    fn duration_frames(self) -> u32 {
        match self {
            Phase::Observe => 30,
            Phase::Plan => 60,
            Phase::Commit => 5,
            Phase::Reveal => 15,
            Phase::Resolve => 30,
            Phase::Consequence => 30,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Phase::Observe => "Observe",
            Phase::Plan => "Plan",
            Phase::Commit => "Commit",
            Phase::Reveal => "Reveal",
            Phase::Resolve => "Resolve",
            Phase::Consequence => "Consequence",
        }
    }
}

/// The five actions of the Kimodo primitive library.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
pub enum Action {
    Strike,
    Block,
    Grab,
    Thrust,
    Dodge,
}

/// The three stances / guard heights.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
pub enum Stance {
    Top,
    Left,
    Right,
}

/// High-level input accepted from a fighter during the Plan phase.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
pub enum PlayerInput {
    SelectAction(Action),
    SelectStance(Stance),
    Commit,
}

/// The measured defender surface at a physical contact boundary.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
pub enum ContactSurface {
    Body,
    Guard,
}

/// Geometry of a contact event, produced by the shared physical world.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct ContactGeometry {
    pub distance: f32,
    pub in_range: bool,
    pub attacker: Side,
    pub surface: ContactSurface,
}

/// F-005/G5: real 120Hz substep truth packet emitted by DuelWorld.
/// Every field is measured from the solved pose — never substituted with
/// zero or inferred from the action label. The same solved pose drives
/// skinning, hand surfaces, collision proxies, contact evaluation, and
/// replay hashes.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct SubstepTruthPacket {
    /// Monotonic 120Hz physics substep identifier.
    pub substep_id: u64,
    /// Which bilateral contact manifold produced this measurement (0 if none).
    pub manifold_id: u32,
    /// Which body region the contact intersects.
    pub body_region: HitLocation,
    /// Measured surface distance in mm (attacker weapon/proxy to defender surface).
    pub surface_distance_mm: f32,
    /// AABB proxy overlap volume in mm^3 (0 = no overlap).
    pub proxy_overlap_mm3: f32,
    /// Prohibited mesh penetration depth in mm (0 = no penetration; >0 = penetration).
    /// Must never exceed 0.5mm for an admitted contact.
    pub prohibited_penetration_mm: f32,
    /// Whether the contact is visible (not occluded by either fighter's body).
    pub visible_contact: bool,
    /// Whether the defender exhibited a causal response (motion change attributable
    /// to the contact, not to the action label). Measured from position delta.
    pub causal_response: bool,
}

/// Complete physical-world result for one truth tick.
///
/// `contact: None` is an observed whiff; absence of a batch is an unresolved
/// physical step and must never be converted into a synthetic whiff.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct PhysicalContactBatch {
    pub truth_frame: u32,
    pub contact: Option<ContactGeometry>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContactSubmissionError {
    NotResolving,
    WrongTruthFrame { expected: u32, received: u32 },
    Duplicate,
}

/// Where on the body a hit lands.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
pub enum HitLocation {
    Head,
    Torso,
    Arms,
    Legs,
}

/// Mutable state for one fighter.
#[derive(Debug, Clone)]
pub struct FighterState {
    pub action: Option<Action>,
    pub stance: Stance,
    pub committed: bool,
    pub health: f32,
    pub stamina: f32,
    pub incapacitated: bool,
}

impl PartialEq for FighterState {
    fn eq(&self, other: &Self) -> bool {
        self.action == other.action
            && self.stance == other.stance
            && self.committed == other.committed
            && self.health.to_bits() == other.health.to_bits()
            && self.stamina.to_bits() == other.stamina.to_bits()
            && self.incapacitated == other.incapacitated
    }
}

/// A deterministic snapshot of the entire combat state.
#[derive(Debug, Clone)]
pub struct TruthSnapshot {
    pub frame: u32,
    pub phase: Phase,
    pub phase_frame: u32,
    pub player: FighterState,
    pub opponent: FighterState,
    pub last_contact: Option<ContactGeometry>,
    pub match_over: bool,
    pub winner: Option<Side>,
}

impl PartialEq for TruthSnapshot {
    fn eq(&self, other: &Self) -> bool {
        self.frame == other.frame
            && self.phase == other.phase
            && self.phase_frame == other.phase_frame
            && self.player == other.player
            && self.opponent == other.opponent
            && self.last_contact == other.last_contact
            && self.match_over == other.match_over
            && self.winner == other.winner
    }
}

/// Deterministic combat state machine.
#[derive(Debug, Clone)]
pub struct CombatTruth {
    snapshot: TruthSnapshot,
    exchange_resolved: bool,
    pending_physical_contact: Option<PhysicalContactBatch>,
}

impl CombatTruth {
    pub fn new() -> Self {
        // Ensure the action matrix data is loaded (authoritative RON or fallback).
        let _ = action_matrix::matrix_data();

        let fighter = FighterState {
            action: None,
            stance: Stance::Top,
            committed: false,
            health: 100.0,
            stamina: 100.0,
            incapacitated: false,
        };

        Self {
            snapshot: TruthSnapshot {
                frame: 0,
                phase: Phase::Observe,
                phase_frame: 0,
                player: fighter.clone(),
                opponent: fighter,
                last_contact: None,
                match_over: false,
                winner: None,
            },
            exchange_resolved: false,
            pending_physical_contact: None,
        }
    }

    pub fn phase(&self) -> Phase {
        self.snapshot.phase
    }

    pub fn snapshot(&self) -> &TruthSnapshot {
        &self.snapshot
    }

    /// The only truth frame accepted for the next physical contact batch.
    pub fn expected_contact_frame(&self) -> Option<u32> {
        (self.snapshot.phase == Phase::Resolve && !self.exchange_resolved)
            .then(|| self.snapshot.frame.saturating_add(1))
    }

    /// Submit the complete physical result for the next Resolve-phase truth tick.
    ///
    /// This accepts a measured contact or a measured absence of contact. It never
    /// accepts animation output as evidence and rejects stale or duplicate batches.
    pub fn submit_physical_contact(
        &mut self,
        batch: PhysicalContactBatch,
    ) -> Result<(), ContactSubmissionError> {
        let Some(expected) = self.expected_contact_frame() else {
            return Err(ContactSubmissionError::NotResolving);
        };
        if batch.truth_frame != expected {
            return Err(ContactSubmissionError::WrongTruthFrame {
                expected,
                received: batch.truth_frame,
            });
        }
        if self.pending_physical_contact.is_some() {
            return Err(ContactSubmissionError::Duplicate);
        }
        self.pending_physical_contact = Some(batch);
        Ok(())
    }

    /// Deterministic FNV-1a hash of the current snapshot.
    pub fn truth_hash(&self) -> u64 {
        fnv1a_hash(&self.snapshot)
    }

    /// Apply one input from one side. Only Plan-phase selects/commit are honored.
    pub fn apply_input(&mut self, side: Side, input: PlayerInput) {
        if self.snapshot.phase != Phase::Plan {
            return;
        }
        let fighter = self.state_mut(side);
        match input {
            PlayerInput::SelectAction(action)
                if crate::combat::is_first_playable_choice(action, fighter.stance) =>
            {
                fighter.action = Some(action)
            }
            PlayerInput::SelectStance(stance) if stance == crate::combat::FIRST_PLAYABLE_STANCE => {
                fighter.stance = stance
            }
            PlayerInput::SelectAction(_) | PlayerInput::SelectStance(_) => {}
            PlayerInput::Commit => {
                if fighter.action.is_none() {
                    fighter.action = Some(Action::Block);
                }
                fighter.committed = true;
            }
        }
    }

    /// Advance the authoritative state machine by exactly one 60 Hz tick.
    /// Wall-clock accumulation belongs to the application layer.
    pub fn tick(&mut self) {
        self.snapshot.frame += 1;
        self.snapshot.phase_frame += 1;

        let duration = self.snapshot.phase.duration_frames();
        if self.snapshot.phase == Phase::Resolve && !self.exchange_resolved {
            self.exchange_resolved = self.resolve_exchange();
        }
        if self.snapshot.phase_frame < duration {
            return;
        }

        // Phase budget exhausted: run end-of-phase logic, then advance.
        match self.snapshot.phase {
            Phase::Commit => self.end_commit(),
            Phase::Resolve if !self.exchange_resolved => {
                self.snapshot.phase_frame = duration;
            }
            _ => self.advance_phase(),
        }
    }

    fn advance_phase(&mut self) {
        self.enter_phase(self.snapshot.phase.next());
    }

    fn enter_phase(&mut self, phase: Phase) {
        self.snapshot.phase = phase;
        self.snapshot.phase_frame = 0;

        match phase {
            Phase::Observe => {
                // Return to idle for the next exchange.
                self.snapshot.player.action = None;
                self.snapshot.player.committed = false;
                self.snapshot.opponent.action = None;
                self.snapshot.opponent.committed = false;
                self.snapshot.last_contact = None;
                self.exchange_resolved = false;
                self.pending_physical_contact = None;
            }
            Phase::Commit => {
                // Lock inputs. Any side that has not committed defaults to Block.
                for side in [Side::Player, Side::Opponent] {
                    let fighter = self.state_mut(side);
                    if fighter.action.is_none() || !fighter.committed {
                        fighter.action = Some(Action::Block);
                    }
                }
            }
            Phase::Resolve => {
                self.exchange_resolved = false;
                self.pending_physical_contact = None;
            }
            _ => {}
        }
    }

    fn end_commit(&mut self) {
        for side in [Side::Player, Side::Opponent] {
            self.state_mut(side).committed = true;
        }
        self.advance_phase();
    }

    fn resolve_exchange(&mut self) -> bool {
        let Some(batch) = self.pending_physical_contact.take() else {
            return false;
        };
        let (Some(action_a), Some(action_b)) =
            (self.snapshot.player.action, self.snapshot.opponent.action)
        else {
            self.snapshot.last_contact = None;
            return true;
        };

        let result = action_matrix::resolve(
            action_a,
            action_b,
            self.snapshot.player.stance,
            self.snapshot.opponent.stance,
            &batch.contact,
        );
        self.snapshot.last_contact = batch.contact;
        self.apply_result(&result);
        true
    }

    fn apply_result(&mut self, result: &MatrixResult) {
        match result.contact_type {
            ContactType::Hit => {
                let victim = result.initiative.opposite();
                self.damage_health(victim, result.force * 2.0);
                self.damage_stamina(result.initiative, 5.0);
            }
            ContactType::Beat => {
                let victim = result.initiative.opposite();
                self.damage_stamina(victim, 15.0);
                self.damage_stamina(result.initiative, 3.0);
            }
            ContactType::Clash => {
                self.damage_stamina(Side::Player, 5.0);
                self.damage_stamina(Side::Opponent, 5.0);
            }
            ContactType::GrabSuccess => {
                let victim = result.initiative.opposite();
                self.damage_health(victim, result.force * 1.5);
                self.damage_stamina(victim, 12.0);
                self.damage_stamina(result.initiative, 8.0);
            }
            ContactType::GrabTech => {
                self.damage_stamina(Side::Player, 10.0);
                self.damage_stamina(Side::Opponent, 10.0);
            }
            ContactType::Whiff => {
                self.damage_stamina(result.initiative, 5.0);
            }
        }
        self.check_match_over();
    }

    fn damage_health(&mut self, side: Side, amount: f32) {
        let fighter = self.state_mut(side);
        fighter.health = (fighter.health - amount).max(0.0);
        if fighter.health <= 0.0 {
            fighter.incapacitated = true;
        }
    }

    fn damage_stamina(&mut self, side: Side, amount: f32) {
        let fighter = self.state_mut(side);
        fighter.stamina = (fighter.stamina - amount).max(0.0);
    }

    fn check_match_over(&mut self) {
        if self.snapshot.match_over {
            return;
        }
        if self.snapshot.opponent.health <= 0.0 {
            self.snapshot.match_over = true;
            self.snapshot.winner = Some(Side::Player);
        } else if self.snapshot.player.health <= 0.0 {
            self.snapshot.match_over = true;
            self.snapshot.winner = Some(Side::Opponent);
        }
    }

    fn state_mut(&mut self, side: Side) -> &mut FighterState {
        match side {
            Side::Player => &mut self.snapshot.player,
            Side::Opponent => &mut self.snapshot.opponent,
        }
    }
}

impl Default for CombatTruth {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Deterministic hashing
// ---------------------------------------------------------------------------

const FNV_OFFSET: u64 = 0xcbf29ce484222325;
const FNV_PRIME: u64 = 0x0100000001b3;

fn fnv1a(bytes: &[u8]) -> u64 {
    let mut hash = FNV_OFFSET;
    for &byte in bytes {
        hash ^= byte as u64;
        hash = hash.wrapping_mul(FNV_PRIME);
    }
    hash
}

fn write_option_action(buf: &mut Vec<u8>, action: Option<Action>) {
    match action {
        None => buf.push(0),
        Some(a) => {
            buf.push(1);
            buf.push(a as u8);
        }
    }
}

fn write_option_contact(buf: &mut Vec<u8>, contact: Option<ContactGeometry>) {
    match contact {
        None => buf.push(0),
        Some(c) => {
            buf.push(1);
            buf.extend_from_slice(&c.distance.to_bits().to_le_bytes());
            buf.push(if c.in_range { 1 } else { 0 });
            buf.push(c.attacker as u8);
            buf.push(c.surface as u8);
        }
    }
}

fn write_option_side(buf: &mut Vec<u8>, side: Option<Side>) {
    match side {
        None => buf.push(0),
        Some(s) => {
            buf.push(1);
            buf.push(s as u8);
        }
    }
}

fn quantize(value: f32) -> i32 {
    (value * 1000.0).round() as i32
}

fn fnv1a_hash(snapshot: &TruthSnapshot) -> u64 {
    let mut buf = Vec::with_capacity(128);

    buf.extend_from_slice(&snapshot.frame.to_le_bytes());
    buf.push(snapshot.phase as u8);
    buf.extend_from_slice(&snapshot.phase_frame.to_le_bytes());

    let p = &snapshot.player;
    write_option_action(&mut buf, p.action);
    buf.push(p.stance as u8);
    buf.push(if p.committed { 1 } else { 0 });
    buf.extend_from_slice(&quantize(p.health).to_le_bytes());
    buf.extend_from_slice(&quantize(p.stamina).to_le_bytes());
    buf.push(if p.incapacitated { 1 } else { 0 });

    let o = &snapshot.opponent;
    write_option_action(&mut buf, o.action);
    buf.push(o.stance as u8);
    buf.push(if o.committed { 1 } else { 0 });
    buf.extend_from_slice(&quantize(o.health).to_le_bytes());
    buf.extend_from_slice(&quantize(o.stamina).to_le_bytes());
    buf.push(if o.incapacitated { 1 } else { 0 });

    write_option_contact(&mut buf, snapshot.last_contact);
    buf.push(if snapshot.match_over { 1 } else { 0 });
    write_option_side(&mut buf, snapshot.winner);

    fnv1a(&buf)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn tick(truth: &mut CombatTruth, frames: u32) {
        for _ in 0..frames {
            truth.tick();
        }
    }

    #[test]
    fn phase_transitions_advance_correctly() {
        let mut truth = CombatTruth::new();
        assert_eq!(truth.phase(), Phase::Observe);

        tick(&mut truth, 30);
        assert_eq!(truth.phase(), Phase::Plan);

        tick(&mut truth, 60);
        assert_eq!(truth.phase(), Phase::Commit);

        tick(&mut truth, 5);
        assert_eq!(truth.phase(), Phase::Reveal);

        tick(&mut truth, 15);
        assert_eq!(truth.phase(), Phase::Resolve);

        truth
            .submit_physical_contact(PhysicalContactBatch {
                truth_frame: truth.expected_contact_frame().unwrap(),
                contact: None,
            })
            .unwrap();
        tick(&mut truth, 30);
        assert_eq!(truth.phase(), Phase::Consequence);

        tick(&mut truth, 30);
        assert_eq!(truth.phase(), Phase::Observe);
    }

    #[test]
    fn missing_commit_defaults_to_block() {
        let mut truth = CombatTruth::new();
        tick(&mut truth, 30); // Observe -> Plan
        // Select a stance but never commit during the whole Plan phase.
        truth.apply_input(Side::Player, PlayerInput::SelectStance(Stance::Left));
        tick(&mut truth, 60); // Plan -> Commit
        assert!(truth.snapshot().player.action.is_some());
        assert!(!truth.snapshot().player.committed);

        tick(&mut truth, 5); // Commit -> Reveal
        assert_eq!(truth.snapshot().player.action, Some(Action::Block));
        assert!(truth.snapshot().player.committed);
    }

    #[test]
    fn plan_rejects_actions_and_stances_outside_the_locked_slice() {
        let mut truth = CombatTruth::new();
        tick(&mut truth, 30); // Observe -> Plan

        truth.apply_input(Side::Player, PlayerInput::SelectAction(Action::Strike));
        truth.apply_input(Side::Player, PlayerInput::SelectStance(Stance::Left));

        assert_eq!(truth.snapshot().player.action, None);
        assert_eq!(truth.snapshot().player.stance, Stance::Top);

        truth.apply_input(Side::Player, PlayerInput::SelectAction(Action::Thrust));
        assert_eq!(truth.snapshot().player.action, Some(Action::Thrust));
    }

    #[test]
    fn truth_hash_is_stable_across_clones() {
        let truth = CombatTruth::new();
        let cloned = truth.clone();
        assert_eq!(truth.truth_hash(), cloned.truth_hash());

        // Perturb state deterministically and verify both clones still match.
        let mut a = CombatTruth::new();
        let mut b = CombatTruth::new();
        a.apply_input(Side::Player, PlayerInput::SelectAction(Action::Strike));
        a.apply_input(Side::Player, PlayerInput::Commit);
        b.apply_input(Side::Player, PlayerInput::SelectAction(Action::Strike));
        b.apply_input(Side::Player, PlayerInput::Commit);
        tick(&mut a, 45);
        tick(&mut b, 45);
        assert_eq!(a.snapshot(), b.snapshot());
        assert_eq!(a.truth_hash(), b.truth_hash());
    }

    #[test]
    fn resolve_phase_fails_closed_without_a_physical_batch() {
        let mut truth = CombatTruth::new();
        tick(&mut truth, 30); // Observe -> Plan
        truth.apply_input(Side::Player, PlayerInput::SelectAction(Action::Strike));
        truth.apply_input(Side::Player, PlayerInput::Commit);
        truth.apply_input(Side::Opponent, PlayerInput::SelectAction(Action::Block));
        truth.apply_input(Side::Opponent, PlayerInput::Commit);
        tick(&mut truth, 60); // Plan -> Commit
        tick(&mut truth, 5); // Commit -> Reveal
        tick(&mut truth, 15); // Reveal -> Resolve

        tick(&mut truth, 30);
        assert_eq!(truth.phase(), Phase::Resolve);
        assert!(truth.snapshot().last_contact.is_none());
        assert_eq!(truth.snapshot().player.health, 100.0);
        assert_eq!(truth.snapshot().opponent.health, 100.0);

        let expected = truth.expected_contact_frame().unwrap();
        let stale = PhysicalContactBatch {
            truth_frame: expected - 1,
            contact: None,
        };
        assert_eq!(
            truth.submit_physical_contact(stale),
            Err(ContactSubmissionError::WrongTruthFrame {
                expected,
                received: expected - 1,
            })
        );
    }

    #[test]
    fn guard_contact_beats_thrust_in_the_locked_slice() {
        let mut truth = CombatTruth::new();
        tick(&mut truth, 30); // Plan
        truth.apply_input(Side::Player, PlayerInput::SelectAction(Action::Thrust));
        truth.apply_input(Side::Player, PlayerInput::Commit);
        truth.apply_input(Side::Opponent, PlayerInput::SelectAction(Action::Block));
        truth.apply_input(Side::Opponent, PlayerInput::Commit);
        tick(&mut truth, 60); // Plan -> Commit
        tick(&mut truth, 5); // Commit -> Reveal
        tick(&mut truth, 15); // Reveal -> Resolve
        truth
            .submit_physical_contact(PhysicalContactBatch {
                truth_frame: truth.expected_contact_frame().unwrap(),
                contact: Some(ContactGeometry {
                    distance: 1.0,
                    in_range: true,
                    attacker: Side::Player,
                    surface: ContactSurface::Guard,
                }),
            })
            .unwrap();
        tick(&mut truth, 1);
        assert!(truth.snapshot().last_contact.is_some());
        // Player thrust; measured guard contact means player loses stamina.
        assert!(truth.snapshot().player.stamina < 100.0);
        assert_eq!(truth.snapshot().player.health, 100.0);
        assert_eq!(truth.snapshot().opponent.health, 100.0);
    }
}
