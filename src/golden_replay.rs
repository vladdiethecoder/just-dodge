//! Game-first deterministic golden replay harness.
//!
//! This is intentionally independent of renderer, physics presentation, and
//! wall-clock time.  It is a narrow M6 compatibility layer while M1 intent and
//! M5 injury are built in parallel; all state crossing this boundary is fixed
//! integer data and appears in the per-truth-tick golden document.

use std::fmt;
use std::fmt::Write as _;
use std::fs;
use std::path::Path;

use sha2::{Digest, Sha256};

use crate::ai_script::{
    ClinchIntent, Intent, MoveDirection, PlanIntentPolicy, ScriptKind, ScriptedAi, StrikeVariant,
    intent_name,
};

pub const GOLDEN_FORMAT: &str = "just-dodge-golden-replay-v1";
const GRAB_REACH_MM: i32 = 1_000;

trait IntentName {
    fn name(self) -> &'static str;
}

impl IntentName for Intent {
    fn name(self) -> &'static str {
        intent_name(self)
    }
}

const fn is_strike(intent: Intent) -> bool {
    matches!(intent, Intent::Strike { .. })
}

/// Minimal M5-facing capability view.  It is intentionally a value rather than
/// a collection so hashing and iteration order cannot depend on a hash map.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IntentCapabilities {
    pub strike: bool,
    pub grab: bool,
    pub move_: bool,
}

impl IntentCapabilities {
    fn names(self) -> String {
        let mut result = Vec::new();
        if self.strike {
            result.push("Strike");
        }
        if self.grab {
            result.push("Grab");
        }
        if self.move_ {
            result.push("Move");
        }
        result.join("+")
    }
}

/// Narrow adapter that M5 will implement when its public API is available.
///
/// TODO(M5): wire this to M5's `contact -> injury`, `available_intents()`,
/// `is_incapacitated()`, and replay-hashable injury state.  The M6 stub exists
/// only so golden-replay behavior is testable without waiting for M5.
pub trait InjuryTruthAdapter {
    fn apply_contact(&mut self, contact: ContactPlan);
    fn available_intents(&self) -> IntentCapabilities;
    fn is_incapacitated(&self) -> bool;
    fn replay_hash_words(&self) -> [u64; 2];
    fn arm_trauma(&self) -> u16;
    fn torso_trauma(&self) -> u16;
}

/// Deterministic temporary M5 adapter: two arm trauma disables strike/grab;
/// four torso trauma incapacitates the fighter.  No aggregate HP is used.
#[derive(Debug, Clone, Copy, Default)]
pub struct StubInjuryTruth {
    arm_trauma: u16,
    torso_trauma: u16,
}

impl InjuryTruthAdapter for StubInjuryTruth {
    fn apply_contact(&mut self, contact: ContactPlan) {
        match contact.part {
            BodyPart::Arm => self.arm_trauma = self.arm_trauma.saturating_add(contact.severity),
            BodyPart::Torso => {
                self.torso_trauma = self.torso_trauma.saturating_add(contact.severity)
            }
        }
    }

    fn available_intents(&self) -> IntentCapabilities {
        IntentCapabilities {
            strike: self.arm_trauma < 2,
            grab: self.arm_trauma < 2,
            move_: !self.is_incapacitated(),
        }
    }

    fn is_incapacitated(&self) -> bool {
        self.torso_trauma >= 4
    }

    fn replay_hash_words(&self) -> [u64; 2] {
        [u64::from(self.arm_trauma), u64::from(self.torso_trauma)]
    }

    fn arm_trauma(&self) -> u16 {
        self.arm_trauma
    }

    fn torso_trauma(&self) -> u16 {
        self.torso_trauma
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BodyPart {
    Arm,
    Torso,
}

impl BodyPart {
    const fn name(self) -> &'static str {
        match self {
            Self::Arm => "Arm",
            Self::Torso => "Torso",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ContactPlan {
    pub part: BodyPart,
    pub severity: u16,
}

impl ContactPlan {
    const NONE: Option<Self> = None;
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GoldenScenario {
    AllIntents,
    ClinchGrabTech,
    CancelCombo,
    Juggle,
    InjuryCapabilityChange,
    Incapacitation,
    OutOfReachReprompt,
}

impl GoldenScenario {
    pub const ALL: [Self; 7] = [
        Self::AllIntents,
        Self::ClinchGrabTech,
        Self::CancelCombo,
        Self::Juggle,
        Self::InjuryCapabilityChange,
        Self::Incapacitation,
        Self::OutOfReachReprompt,
    ];

    pub const fn name(self) -> &'static str {
        match self {
            Self::AllIntents => "all_intents",
            Self::ClinchGrabTech => "clinch_grab_tech",
            Self::CancelCombo => "cancel_combo",
            Self::Juggle => "juggle",
            Self::InjuryCapabilityChange => "injury_capability_change",
            Self::Incapacitation => "incapacitation",
            Self::OutOfReachReprompt => "out_of_reach_reprompt",
        }
    }

    const fn script_kind(self) -> ScriptKind {
        match self {
            Self::AllIntents | Self::CancelCombo | Self::Juggle | Self::Incapacitation => {
                ScriptKind::Aggressive
            }
            Self::ClinchGrabTech | Self::OutOfReachReprompt => ScriptKind::Defensive,
            Self::InjuryCapabilityChange => ScriptKind::Mixed,
        }
    }

    const fn seed(self) -> u64 {
        // Zero intentionally starts each readable canned script at its first row.
        match self {
            Self::AllIntents => 0,
            Self::ClinchGrabTech => 0,
            Self::CancelCombo => 0,
            Self::Juggle => 0,
            Self::InjuryCapabilityChange => 0,
            Self::Incapacitation => 0,
            Self::OutOfReachReprompt => 0,
        }
    }

    const fn initial_distance_mm(self) -> i32 {
        match self {
            Self::OutOfReachReprompt => 3_000,
            _ => 800,
        }
    }

    const fn player_script(self) -> &'static [Intent] {
        match self {
            Self::AllIntents => &[
                Intent::Strike {
                    variant: StrikeVariant::Thrust,
                },
                Intent::Block,
                Intent::Grab,
                Intent::Move {
                    dir: MoveDirection::Approach,
                },
                Intent::Dodge {
                    dir: MoveDirection::Retreat,
                },
                Intent::Feint,
                Intent::Cancel,
                Intent::Idle,
                Intent::Clinch {
                    sub: ClinchIntent::Hold,
                },
            ],
            Self::ClinchGrabTech => &[
                Intent::Grab,
                Intent::Clinch {
                    sub: ClinchIntent::Hold,
                },
                Intent::Idle,
            ],
            Self::CancelCombo => &[
                Intent::Strike {
                    variant: StrikeVariant::Thrust,
                },
                Intent::Cancel,
                Intent::Strike {
                    variant: StrikeVariant::Slash,
                },
            ],
            Self::Juggle => &[
                Intent::Strike {
                    variant: StrikeVariant::Thrust,
                },
                Intent::Strike {
                    variant: StrikeVariant::Slash,
                },
                Intent::Strike {
                    variant: StrikeVariant::Thrust,
                },
            ],
            Self::InjuryCapabilityChange => &[
                Intent::Strike {
                    variant: StrikeVariant::Slash,
                },
                Intent::Block,
            ],
            Self::Incapacitation => &[
                Intent::Strike {
                    variant: StrikeVariant::Thrust,
                },
                Intent::Strike {
                    variant: StrikeVariant::Slash,
                },
            ],
            Self::OutOfReachReprompt => &[
                Intent::Grab,
                Intent::Strike {
                    variant: StrikeVariant::Thrust,
                },
            ],
        }
    }

    const fn contact_at(self, plan: usize) -> Option<ContactPlan> {
        match (self, plan) {
            (Self::InjuryCapabilityChange, 0) => Some(ContactPlan {
                part: BodyPart::Arm,
                severity: 2,
            }),
            (Self::Incapacitation, 0 | 1) => Some(ContactPlan {
                part: BodyPart::Torso,
                severity: 2,
            }),
            _ => ContactPlan::NONE,
        }
    }
}

/// Complete replay-stable state after an authoritative truth tick.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TruthTick {
    pub tick: u32,
    pub requested_player: Intent,
    pub player_locked: Intent,
    pub opponent_locked: Intent,
    pub distance_mm: i32,
    pub clinched: bool,
    pub airborne_ticks: u8,
    pub combo_count: u8,
    pub events: Vec<&'static str>,
    pub contact: Option<ContactPlan>,
    pub arm_trauma: u16,
    pub torso_trauma: u16,
    pub available_intents: String,
    pub incapacitated: bool,
    pub truth_hash: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GoldenTrace {
    pub scenario: GoldenScenario,
    pub seed: u64,
    pub ticks: Vec<TruthTick>,
    pub final_truth_hash: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReplayDivergence {
    pub tick: u32,
    pub field: &'static str,
    pub expected: String,
    pub actual: String,
}

impl fmt::Display for ReplayDivergence {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "golden replay divergence at tick {} field {}: expected {}, got {}",
            self.tick, self.field, self.expected, self.actual
        )
    }
}

impl std::error::Error for ReplayDivergence {}

#[derive(Debug, Clone, Copy)]
struct MatchState<I: InjuryTruthAdapter> {
    distance_mm: i32,
    clinched: bool,
    airborne_ticks: u8,
    combo_count: u8,
    previous_player: Intent,
    injury: I,
}

impl<I: InjuryTruthAdapter> MatchState<I> {
    fn new(distance_mm: i32, injury: I) -> Self {
        Self {
            distance_mm,
            clinched: false,
            airborne_ticks: 0,
            combo_count: 0,
            previous_player: Intent::Idle,
            injury,
        }
    }
}

/// Re-simulate one fixed scenario from its declared seed and canned AI script.
pub fn run_scenario(scenario: GoldenScenario) -> GoldenTrace {
    let seed = scenario.seed();
    let ai = ScriptedAi::new(scenario.script_kind(), seed);
    let mut state = MatchState::new(scenario.initial_distance_mm(), StubInjuryTruth::default());
    let mut ticks = Vec::new();

    for (plan, requested_player) in scenario.player_script().iter().copied().enumerate() {
        let mut events = vec!["PlanLocked"];
        let mut player_locked = requested_player;
        let opponent_locked = ai.intent_for_plan(plan as u32);

        // This is the mid-execution feasibility check called for by the intent
        // spec.  It records the rejected goal and emits an explicit reprompt.
        if scenario == GoldenScenario::OutOfReachReprompt
            && plan == 0
            && requested_player == Intent::Grab
            && state.distance_mm > GRAB_REACH_MM
        {
            player_locked = Intent::Feint;
            state.distance_mm = 900;
            events.push("FeasibilityReprompt");
            events.push("RepromptFeint");
        }

        if matches!(player_locked, Intent::Move { .. })
            || matches!(opponent_locked, Intent::Move { .. })
        {
            state.distance_mm = (state.distance_mm - 100).max(0);
            events.push("MovementResolved");
        }

        if player_locked == Intent::Grab && state.distance_mm <= GRAB_REACH_MM {
            state.clinched = true;
            events.push("ClinchEntry");
        }
        if state.clinched
            && matches!(player_locked, Intent::Clinch { .. })
            && matches!(
                opponent_locked,
                Intent::Clinch {
                    sub: ClinchIntent::Tech
                }
            )
        {
            state.clinched = false;
            events.push("GrabTechEscape");
        }

        if player_locked == Intent::Cancel && is_strike(state.previous_player) {
            state.combo_count = state.combo_count.saturating_add(1);
            events.push("CancelIntoCombo");
        }
        if state.combo_count > 0 && is_strike(player_locked) {
            events.push("ComboFollowUp");
        }

        if scenario == GoldenScenario::Juggle && is_strike(player_locked) {
            if state.airborne_ticks > 0 {
                events.push("JuggleHit");
            } else {
                events.push("Launch");
            }
            state.airborne_ticks = 2;
        }

        let contact = scenario.contact_at(plan);
        let before_caps = state.injury.available_intents();
        if let Some(contact) = contact {
            state.injury.apply_contact(contact);
            events.push("ContactResolved");
            if state.injury.available_intents() != before_caps {
                events.push("InjuryCapabilityChanged");
            }
        }
        if state.injury.is_incapacitated() {
            events.push("MatchEndIncapacitation");
        }

        if state.airborne_ticks > 0 {
            state.airborne_ticks -= 1;
        }
        state.previous_player = player_locked;
        let capabilities = state.injury.available_intents();
        let mut tick = TruthTick {
            tick: plan as u32,
            requested_player,
            player_locked,
            opponent_locked,
            distance_mm: state.distance_mm,
            clinched: state.clinched,
            airborne_ticks: state.airborne_ticks,
            combo_count: state.combo_count,
            events,
            contact,
            arm_trauma: state.injury.arm_trauma(),
            torso_trauma: state.injury.torso_trauma(),
            available_intents: capabilities.names(),
            incapacitated: state.injury.is_incapacitated(),
            truth_hash: 0,
        };
        tick.truth_hash = hash_tick(scenario, seed, &tick, state.injury.replay_hash_words());
        ticks.push(tick);
        if state.injury.is_incapacitated() {
            break;
        }
    }

    let final_truth_hash = ticks.last().map_or(0, |tick| tick.truth_hash);
    GoldenTrace {
        scenario,
        seed,
        ticks,
        final_truth_hash,
    }
}

/// Compare two simulations structurally.  This is intentionally field-level so
/// a future truth change reports its first exact tick/field rather than a vague
/// final hash mismatch.
pub fn compare_traces(
    expected: &GoldenTrace,
    actual: &GoldenTrace,
) -> Result<(), ReplayDivergence> {
    if expected.scenario != actual.scenario {
        return Err(divergence(
            0,
            "scenario",
            expected.scenario.name(),
            actual.scenario.name(),
        ));
    }
    if expected.seed != actual.seed {
        return Err(divergence(0, "seed", expected.seed, actual.seed));
    }
    if expected.ticks.len() != actual.ticks.len() {
        return Err(divergence(
            expected.ticks.len().min(actual.ticks.len()) as u32,
            "tick_count",
            expected.ticks.len(),
            actual.ticks.len(),
        ));
    }
    for (expected_tick, actual_tick) in expected.ticks.iter().zip(&actual.ticks) {
        compare_tick(expected_tick, actual_tick)?;
    }
    if expected.final_truth_hash != actual.final_truth_hash {
        return Err(divergence_final(expected, actual));
    }
    Ok(())
}

fn divergence_final(expected: &GoldenTrace, actual: &GoldenTrace) -> ReplayDivergence {
    divergence(
        expected.ticks.last().map_or(0, |tick| tick.tick),
        "final_truth_hash",
        format_hash(expected.final_truth_hash),
        format_hash(actual.final_truth_hash),
    )
}

fn compare_tick(expected: &TruthTick, actual: &TruthTick) -> Result<(), ReplayDivergence> {
    compare_field(expected.tick, "tick", expected.tick, actual.tick)?;
    compare_field(
        expected.tick,
        "requested_player",
        expected.requested_player.name(),
        actual.requested_player.name(),
    )?;
    compare_field(
        expected.tick,
        "player_locked",
        expected.player_locked.name(),
        actual.player_locked.name(),
    )?;
    compare_field(
        expected.tick,
        "opponent_locked",
        expected.opponent_locked.name(),
        actual.opponent_locked.name(),
    )?;
    compare_field(
        expected.tick,
        "distance_mm",
        expected.distance_mm,
        actual.distance_mm,
    )?;
    compare_field(
        expected.tick,
        "clinched",
        expected.clinched,
        actual.clinched,
    )?;
    compare_field(
        expected.tick,
        "airborne_ticks",
        expected.airborne_ticks,
        actual.airborne_ticks,
    )?;
    compare_field(
        expected.tick,
        "combo_count",
        expected.combo_count,
        actual.combo_count,
    )?;
    compare_field(
        expected.tick,
        "events",
        expected.events.join("|"),
        actual.events.join("|"),
    )?;
    compare_field(
        expected.tick,
        "contact",
        format_contact(expected.contact),
        format_contact(actual.contact),
    )?;
    compare_field(
        expected.tick,
        "arm_trauma",
        expected.arm_trauma,
        actual.arm_trauma,
    )?;
    compare_field(
        expected.tick,
        "torso_trauma",
        expected.torso_trauma,
        actual.torso_trauma,
    )?;
    compare_field(
        expected.tick,
        "available_intents",
        &expected.available_intents,
        &actual.available_intents,
    )?;
    compare_field(
        expected.tick,
        "incapacitated",
        expected.incapacitated,
        actual.incapacitated,
    )?;
    compare_field(
        expected.tick,
        "truth_hash",
        format_hash(expected.truth_hash),
        format_hash(actual.truth_hash),
    )?;
    Ok(())
}

fn compare_field<T: PartialEq + fmt::Display>(
    tick: u32,
    field: &'static str,
    expected: T,
    actual: T,
) -> Result<(), ReplayDivergence> {
    if expected == actual {
        Ok(())
    } else {
        Err(divergence(tick, field, expected, actual))
    }
}

fn divergence(
    tick: u32,
    field: &'static str,
    expected: impl fmt::Display,
    actual: impl fmt::Display,
) -> ReplayDivergence {
    ReplayDivergence {
        tick,
        field,
        expected: expected.to_string(),
        actual: actual.to_string(),
    }
}

/// The required 100-run assertion.  Run zero is the baseline and 99 independent
/// fresh simulations must match every per-tick state field and final truth hash.
pub fn assert_one_hundred_identical(scenario: GoldenScenario) -> Result<u64, ReplayDivergence> {
    let baseline = run_scenario(scenario);
    for _ in 1..100 {
        let replay = run_scenario(scenario);
        compare_traces(&baseline, &replay)?;
    }
    Ok(baseline.final_truth_hash)
}

/// Canonical golden JSON; no pretty-printer, map iteration, timestamp, or host
/// path is allowed into these bytes.
pub fn golden_json(trace: &GoldenTrace) -> String {
    let mut output = String::new();
    writeln!(&mut output, "{{").expect("write String");
    writeln!(&mut output, "  \"format\":\"{GOLDEN_FORMAT}\",").expect("write String");
    writeln!(&mut output, "  \"scenario\":\"{}\",", trace.scenario.name()).expect("write String");
    writeln!(&mut output, "  \"seed\":{},", trace.seed).expect("write String");
    writeln!(
        &mut output,
        "  \"final_truth_hash\":\"{}\",",
        format_hash(trace.final_truth_hash)
    )
    .expect("write String");
    writeln!(&mut output, "  \"ticks\":[").expect("write String");
    for (index, tick) in trace.ticks.iter().enumerate() {
        let comma = if index + 1 == trace.ticks.len() {
            ""
        } else {
            ","
        };
        writeln!(
            &mut output,
            "    {{\"tick\":{},\"requested_player\":\"{}\",\"player_locked\":\"{}\",\"opponent_locked\":\"{}\",\"distance_mm\":{},\"clinched\":{},\"airborne_ticks\":{},\"combo_count\":{},\"events\":{},\"contact\":{},\"injury\":{{\"arm_trauma\":{},\"torso_trauma\":{},\"available_intents\":\"{}\",\"incapacitated\":{}}},\"truth_hash\":\"{}\"}}{}",
            tick.tick,
            tick.requested_player.name(),
            tick.player_locked.name(),
            tick.opponent_locked.name(),
            tick.distance_mm,
            tick.clinched,
            tick.airborne_ticks,
            tick.combo_count,
            events_json(&tick.events),
            contact_json(tick.contact),
            tick.arm_trauma,
            tick.torso_trauma,
            tick.available_intents,
            tick.incapacitated,
            format_hash(tick.truth_hash),
            comma,
        )
        .expect("write String");
    }
    writeln!(&mut output, "  ]").expect("write String");
    writeln!(&mut output, "}}").expect("write String");
    output
}

/// Generate seven replay files plus a standard SHA-256 manifest.  The manifest
/// deliberately covers only replay files, never itself, avoiding a self-hash.
pub fn write_golden_set(output_dir: &Path) -> Result<Vec<(GoldenScenario, u64)>, std::io::Error> {
    fs::create_dir_all(output_dir)?;
    let mut manifest = String::from("# just-dodge M6 golden replay SHA-256 manifest\n");
    let mut hashes = String::from("# scenario final_truth_hash\n");
    let mut results = Vec::new();
    for scenario in GoldenScenario::ALL {
        let trace = run_scenario(scenario);
        let document = golden_json(&trace);
        let filename = format!("{}.golden.json", scenario.name());
        fs::write(output_dir.join(&filename), document.as_bytes())?;
        writeln!(
            &mut manifest,
            "{}  {filename}",
            sha256_hex(document.as_bytes())
        )
        .expect("write String");
        writeln!(
            &mut hashes,
            "{} {}",
            scenario.name(),
            format_hash(trace.final_truth_hash)
        )
        .expect("write String");
        results.push((scenario, trace.final_truth_hash));
    }
    fs::write(output_dir.join("MANIFEST.sha256"), manifest)?;
    fs::write(output_dir.join("scenario_truth_hashes.txt"), hashes)?;
    Ok(results)
}

/// Reconstruct all scenarios, run their 100-run checks, then compare their
/// canonical bytes to an existing golden directory.  A byte mismatch is
/// fail-closed; in-memory comparisons above provide the first tick and field
/// if the simulator itself diverges.
pub fn verify_golden_set(output_dir: &Path) -> Result<Vec<(GoldenScenario, u64)>, String> {
    let mut results = Vec::new();
    for scenario in GoldenScenario::ALL {
        let hash = assert_one_hundred_identical(scenario).map_err(|error| error.to_string())?;
        let expected = golden_json(&run_scenario(scenario));
        let path = output_dir.join(format!("{}.golden.json", scenario.name()));
        let actual = fs::read_to_string(&path)
            .map_err(|error| format!("cannot read {}: {error}", path.display()))?;
        if actual != expected {
            return Err(format!(
                "golden byte mismatch for {}; rerun divergence assertion reports first tick/field; expected_sha256={} actual_sha256={}",
                scenario.name(),
                sha256_hex(expected.as_bytes()),
                sha256_hex(actual.as_bytes())
            ));
        }
        results.push((scenario, hash));
    }
    Ok(results)
}

fn hash_tick(scenario: GoldenScenario, seed: u64, tick: &TruthTick, injury_words: [u64; 2]) -> u64 {
    let mut hash = 0xcbf2_9ce4_8422_2325_u64;
    mix_str(&mut hash, GOLDEN_FORMAT);
    mix_str(&mut hash, scenario.name());
    mix(&mut hash, seed);
    mix(&mut hash, u64::from(tick.tick));
    mix_str(&mut hash, tick.requested_player.name());
    mix_str(&mut hash, tick.player_locked.name());
    mix_str(&mut hash, tick.opponent_locked.name());
    mix(&mut hash, tick.distance_mm as i64 as u64);
    mix(&mut hash, u64::from(tick.clinched));
    mix(&mut hash, u64::from(tick.airborne_ticks));
    mix(&mut hash, u64::from(tick.combo_count));
    for event in &tick.events {
        mix_str(&mut hash, event);
    }
    match tick.contact {
        Some(contact) => {
            mix_str(&mut hash, contact.part.name());
            mix(&mut hash, u64::from(contact.severity));
        }
        None => mix_str(&mut hash, "None"),
    }
    mix(&mut hash, injury_words[0]);
    mix(&mut hash, injury_words[1]);
    mix_str(&mut hash, &tick.available_intents);
    mix(&mut hash, u64::from(tick.incapacitated));
    hash
}

fn mix(hash: &mut u64, value: u64) {
    *hash ^= value;
    *hash = hash.wrapping_mul(0x1000_0000_01b3);
}

fn mix_str(hash: &mut u64, value: &str) {
    for byte in value.bytes() {
        mix(hash, u64::from(byte));
    }
    mix(hash, 0xff);
}

fn events_json(events: &[&str]) -> String {
    let names: Vec<String> = events.iter().map(|event| format!("\"{event}\"")).collect();
    format!("[{}]", names.join(","))
}

fn contact_json(contact: Option<ContactPlan>) -> String {
    match contact {
        Some(contact) => format!(
            "{{\"part\":\"{}\",\"severity\":{}}}",
            contact.part.name(),
            contact.severity
        ),
        None => "null".to_owned(),
    }
}

fn format_contact(contact: Option<ContactPlan>) -> String {
    match contact {
        Some(contact) => format!("{}:{}", contact.part.name(), contact.severity),
        None => "None".to_owned(),
    }
}

fn format_hash(hash: u64) -> String {
    format!("{hash:016x}")
}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_scenario_is_identical_across_one_hundred_fresh_replays() {
        for scenario in GoldenScenario::ALL {
            assert_one_hundred_identical(scenario)
                .unwrap_or_else(|error| panic!("{}: {error}", scenario.name()));
        }
    }

    #[test]
    fn golden_suite_covers_required_intents_and_event_paths() {
        let traces: Vec<_> = GoldenScenario::ALL.into_iter().map(run_scenario).collect();
        let locked: Vec<_> = traces
            .iter()
            .flat_map(|trace| {
                trace
                    .ticks
                    .iter()
                    .flat_map(|tick| [tick.player_locked.name(), tick.opponent_locked.name()])
            })
            .collect();
        for intent in [
            "Strike(Thrust)",
            "Strike(Slash)",
            "Block",
            "Grab",
            "Move",
            "Dodge",
            "Feint",
            "Cancel",
            "Idle",
            "Clinch(Hold)",
        ] {
            assert!(locked.contains(&intent), "goldens did not lock {intent}");
        }
        let events: Vec<_> = traces
            .iter()
            .flat_map(|trace| {
                trace
                    .ticks
                    .iter()
                    .flat_map(|tick| tick.events.iter().copied())
            })
            .collect();
        for required in [
            "ClinchEntry",
            "GrabTechEscape",
            "CancelIntoCombo",
            "JuggleHit",
            "InjuryCapabilityChanged",
            "MatchEndIncapacitation",
            "FeasibilityReprompt",
        ] {
            assert!(
                events.contains(&required),
                "goldens did not cover {required}"
            );
        }
    }

    #[test]
    fn divergence_reports_first_tick_and_field() {
        let expected = run_scenario(GoldenScenario::CancelCombo);
        let mut actual = expected.clone();
        actual.ticks[1].combo_count = 99;
        let error = compare_traces(&expected, &actual).expect_err("must fail closed");
        assert_eq!(error.tick, 1);
        assert_eq!(error.field, "combo_count");
    }

    #[test]
    fn generated_json_is_stable_and_has_per_tick_truth() {
        let trace = run_scenario(GoldenScenario::InjuryCapabilityChange);
        let first = golden_json(&trace);
        let second = golden_json(&run_scenario(GoldenScenario::InjuryCapabilityChange));
        assert_eq!(first, second);
        assert!(first.contains("\"truth_hash\""));
        assert!(first.contains("\"available_intents\":\"Move\""));
    }
}
