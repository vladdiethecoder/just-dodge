// Deterministic replay recorder and loader.
// See docs/design/IMPLEMENTATION_PLAN_3ACTION.md for the contract.

use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::io::{Read, Write};
use std::path::Path;

use anyhow::{Context, bail};

use crate::duel_world::DuelWorldTruthTick;
use crate::truth::{ContactSurface, Side, TruthSnapshot};

const MAGIC: &[u8; 4] = b"JDRP";
const VERSION: u32 = 1;
const HEADER_LEN: usize = 16;

/// A discrete event that happened during a match.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct MatchEvent {
    pub frame: u32,
    pub kind: EventKind,
}

/// Kinds of events that can be recorded in a replay.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub enum EventKind {
    PhaseChange {
        from: String,
        to: String,
    },
    ActionCommitted {
        side: Side,
        action: String,
    },
    Contact {
        point: [f32; 3],
        normal: [f32; 3],
    },
    Damage {
        side: Side,
        region: String,
        amount: f32,
    },
    MatchEnd {
        winner: Option<Side>,
    },
    ResolvePacket {
        receipt: ResolvePacketReceipt,
    },
}

/// Replay-stable classification of an explicitly observed Resolve packet.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum ResolveOutcome {
    Whiff,
    Guard,
    Body,
}

/// One canonical role-tagged contact retained from a 120 Hz physics substep.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ResolveContactReceipt {
    pub physics_tick: u64,
    pub action_tick: u64,
    pub attacker: String,
    pub defender: String,
    pub attacker_role: String,
    pub defender_role: String,
    pub time_of_impact: f32,
}

/// Compact, independently interpretable evidence for one 60 Hz Resolve.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ResolvePacketReceipt {
    pub truth_frame: u32,
    pub player_action: String,
    pub opponent_action: String,
    pub first_physics_tick: u64,
    pub second_physics_tick: u64,
    pub action_tick: u64,
    pub contacts: Vec<ResolveContactReceipt>,
    pub outcome: ResolveOutcome,
    pub player_health_delta_tenths: i32,
    pub opponent_health_delta_tenths: i32,
    pub player_stamina_delta_tenths: i32,
    pub opponent_stamina_delta_tenths: i32,
    pub resolved_truth_hash: u64,
}

/// One frame of recorded truth state.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ReplayFrame {
    pub frame: u32,
    pub truth_hash: u64,
    pub serialized_state: Vec<u8>, // postcard of ReplaySnapshot
}

/// Serializable subset of combat truth stored per frame.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct ReplaySnapshot {
    pub frame: u32,
    pub phase: String,
    pub player_health: u32, // quantized to 0..1000
    pub opponent_health: u32,
    pub player_stamina: u32,
    pub opponent_stamina: u32,
}

/// Records truth snapshots and events for deterministic replay.
pub struct ReplayRecorder {
    pub seed: u64,
    pub frames: Vec<ReplayFrame>,
    pub events: Vec<MatchEvent>,
}

impl ReplayRecorder {
    pub fn new(seed: u64) -> Self {
        Self {
            seed,
            frames: Vec::new(),
            events: Vec::new(),
        }
    }

    /// Record a single frame snapshot.
    pub fn record_frame(&mut self, frame: u32, truth_hash: u64, snapshot: &ReplaySnapshot) {
        let serialized_state =
            postcard::to_stdvec(snapshot).expect("ReplaySnapshot serialization must not fail");
        self.frames.push(ReplayFrame {
            frame,
            truth_hash,
            serialized_state,
        });
    }

    /// Record a single match event.
    pub fn record_event(&mut self, event: MatchEvent) {
        self.events.push(event);
    }

    /// Record the measured 120 Hz packet and the truth state that admitted it.
    pub fn record_resolve_packet(
        &mut self,
        before: &TruthSnapshot,
        after: &TruthSnapshot,
        packet: &DuelWorldTruthTick,
        resolved_truth_hash: u64,
    ) {
        assert_eq!(packet.contact_batch.truth_frame, after.frame);
        self.record_event(MatchEvent {
            frame: after.frame,
            kind: EventKind::ResolvePacket {
                receipt: resolve_packet_receipt(before, after, packet, resolved_truth_hash),
            },
        });
    }

    /// Save the replay to a binary file.
    ///
    /// Format:
    ///   bytes 0..4   magic "JDRP"
    ///   bytes 4..8   little-endian u32 version
    ///   bytes 8..16  little-endian u64 seed
    ///   remainder    postcard-encoded (frames, events)
    pub fn save(&self, path: &Path) -> Result<(), anyhow::Error> {
        let mut file = File::create(path)
            .with_context(|| format!("failed to create replay file {}", path.display()))?;

        file.write_all(MAGIC)?;
        file.write_all(&VERSION.to_le_bytes())?;
        file.write_all(&self.seed.to_le_bytes())?;

        let payload = postcard::to_stdvec(&(&self.frames, &self.events))
            .context("failed to serialize replay payload")?;
        file.write_all(&payload)?;

        Ok(())
    }

    /// Load a replay from a binary file.
    pub fn load(path: &Path) -> Result<Self, anyhow::Error> {
        let mut file = File::open(path)
            .with_context(|| format!("failed to open replay file {}", path.display()))?;

        let mut header = [0u8; HEADER_LEN];
        file.read_exact(&mut header)?;

        if &header[0..4] != MAGIC {
            bail!(
                "bad replay magic: expected {:?}, got {:?}",
                MAGIC,
                &header[0..4]
            );
        }

        let version = u32::from_le_bytes(header[4..8].try_into().unwrap());
        if version != VERSION {
            bail!("unsupported replay version: {}", version);
        }

        let seed = u64::from_le_bytes(header[8..16].try_into().unwrap());

        let mut payload = Vec::new();
        file.read_to_end(&mut payload)?;

        let (frames, events): (Vec<ReplayFrame>, Vec<MatchEvent>) =
            postcard::from_bytes(&payload).context("failed to deserialize replay payload")?;

        Ok(Self {
            seed,
            frames,
            events,
        })
    }

    /// Load and independently validate a replay's resolved physical receipts.
    pub fn reduce_file(path: &Path) -> Result<String, anyhow::Error> {
        let replay = Self::load(path)?;
        replay.reduce_resolve_packets()
    }

    /// Produce a stable, human-readable table without modifying replay state.
    pub fn reduce_resolve_packets(&self) -> Result<String, anyhow::Error> {
        let frame_hashes = validated_frame_hashes(&self.frames)?;
        let mut seen_resolve_frames = BTreeSet::new();
        let mut rows = Vec::new();
        let mut contact_rows = Vec::new();
        for event in &self.events {
            let EventKind::ResolvePacket { receipt } = &event.kind else {
                continue;
            };
            validate_receipt(
                event.frame,
                receipt,
                &frame_hashes,
                &mut seen_resolve_frames,
            )?;
            rows.push(format!(
                "{:>5} {:>5} {:>9}/{:<9} {:<5} {:>2} {:<14} {:<14} {:#018x}",
                receipt.truth_frame,
                receipt.action_tick,
                receipt.first_physics_tick,
                receipt.second_physics_tick,
                format!("{:?}", receipt.outcome),
                receipt.contacts.len(),
                receipt.player_action,
                receipt.opponent_action,
                receipt.resolved_truth_hash,
            ));
            for contact in &receipt.contacts {
                contact_rows.push(format!(
                    "contact {} {} {} {:.6} {} {}",
                    receipt.truth_frame,
                    contact.action_tick,
                    contact.physics_tick,
                    contact.time_of_impact,
                    contact.attacker_role,
                    contact.defender_role,
                ));
            }
        }
        let mut report = format!(
            "seed={}\nframes={}\nresolve_packets={}\nframe action physics_ticks outcome contacts player_action opponent_action truth_hash\n",
            self.seed,
            self.frames.len(),
            rows.len(),
        );
        if rows.is_empty() {
            report.push_str("(none)\n");
        } else {
            for row in rows {
                report.push_str(&row);
                report.push('\n');
            }
        }
        if contact_rows.is_empty() {
            report.push_str("contact (none)\n");
        } else {
            for row in contact_rows {
                report.push_str(&row);
                report.push('\n');
            }
        }
        report.push_str("verdict=PASS\n");
        Ok(report)
    }
}

fn validated_frame_hashes(frames: &[ReplayFrame]) -> Result<BTreeMap<u32, u64>, anyhow::Error> {
    let mut hashes = BTreeMap::new();
    for frame in frames {
        let snapshot: ReplaySnapshot = postcard::from_bytes(&frame.serialized_state)
            .context("failed to deserialize replay frame snapshot")?;
        if snapshot.frame != frame.frame {
            bail!(
                "snapshot frame mismatch: outer={}, encoded={}",
                frame.frame,
                snapshot.frame
            );
        }
        if hashes.insert(frame.frame, frame.truth_hash).is_some() {
            bail!("duplicate replay frame {}", frame.frame);
        }
    }
    Ok(hashes)
}

fn validate_receipt(
    event_frame: u32,
    receipt: &ResolvePacketReceipt,
    frame_hashes: &BTreeMap<u32, u64>,
    seen_resolve_frames: &mut BTreeSet<u32>,
) -> Result<(), anyhow::Error> {
    if event_frame != receipt.truth_frame {
        bail!(
            "ResolvePacket event frame mismatch: event={}, receipt={}",
            event_frame,
            receipt.truth_frame
        );
    }
    if !seen_resolve_frames.insert(receipt.truth_frame) {
        bail!(
            "duplicate ResolvePacket truth frame {}",
            receipt.truth_frame
        );
    }
    let Some(frame_hash) = frame_hashes.get(&receipt.truth_frame) else {
        bail!(
            "ResolvePacket frame {} has no snapshot",
            receipt.truth_frame
        );
    };
    if *frame_hash != receipt.resolved_truth_hash {
        bail!(
            "ResolvePacket truth hash mismatch at frame {}: receipt={:#018x}, snapshot={:#018x}",
            receipt.truth_frame,
            receipt.resolved_truth_hash,
            frame_hash
        );
    }
    if receipt.second_physics_tick != receipt.first_physics_tick + 1 {
        bail!(
            "ResolvePacket frame {} has nonconsecutive physics ticks {}/{}",
            receipt.truth_frame,
            receipt.first_physics_tick,
            receipt.second_physics_tick
        );
    }
    if receipt.player_action.is_empty() || receipt.opponent_action.is_empty() {
        bail!(
            "ResolvePacket frame {} has missing selected action",
            receipt.truth_frame
        );
    }
    for contact in &receipt.contacts {
        if contact.action_tick != receipt.action_tick {
            bail!(
                "ResolvePacket frame {} has mismatched contact action tick",
                receipt.truth_frame
            );
        }
        if contact.physics_tick != receipt.first_physics_tick
            && contact.physics_tick != receipt.second_physics_tick
        {
            bail!(
                "ResolvePacket frame {} has contact outside its substeps",
                receipt.truth_frame
            );
        }
        if !contact.time_of_impact.is_finite() || !(0.0..=1.0).contains(&contact.time_of_impact) {
            bail!(
                "ResolvePacket frame {} has invalid contact TOI",
                receipt.truth_frame
            );
        }
    }
    match receipt.outcome {
        ResolveOutcome::Whiff if !receipt.contacts.is_empty() => {
            bail!(
                "ResolvePacket frame {} contradicts Whiff with contacts",
                receipt.truth_frame
            );
        }
        ResolveOutcome::Guard
            if !receipt
                .contacts
                .iter()
                .any(|contact| contact.defender_role == "WeaponGuard") =>
        {
            bail!(
                "ResolvePacket frame {} contradicts Guard without a WeaponGuard target",
                receipt.truth_frame
            );
        }
        ResolveOutcome::Body
            if !receipt
                .contacts
                .iter()
                .any(|contact| contact.defender_role == "Body") =>
        {
            bail!(
                "ResolvePacket frame {} contradicts Body without a Body target",
                receipt.truth_frame
            );
        }
        _ => {}
    }
    Ok(())
}

fn resolve_packet_receipt(
    before: &TruthSnapshot,
    after: &TruthSnapshot,
    packet: &DuelWorldTruthTick,
    resolved_truth_hash: u64,
) -> ResolvePacketReceipt {
    let mut contacts = Vec::new();
    for step in [&packet.first, &packet.second] {
        contacts.extend(step.contacts.iter().map(|contact| ResolveContactReceipt {
            physics_tick: step.physics_tick,
            action_tick: step.action_tick,
            attacker: format!("{:?}", contact.attacker),
            defender: format!("{:?}", contact.defender),
            attacker_role: format!("{:?}", contact.attacker_role),
            defender_role: format!("{:?}", contact.defender_role),
            time_of_impact: contact.geometry.time_of_impact,
        }));
    }
    let outcome = match packet.contact_batch.contact.map(|contact| contact.surface) {
        None => ResolveOutcome::Whiff,
        Some(ContactSurface::Guard) => ResolveOutcome::Guard,
        Some(ContactSurface::Body) => ResolveOutcome::Body,
    };
    ResolvePacketReceipt {
        truth_frame: packet.contact_batch.truth_frame,
        player_action: format!("{:?}", before.player.action),
        opponent_action: format!("{:?}", before.opponent.action),
        first_physics_tick: packet.first.physics_tick,
        second_physics_tick: packet.second.physics_tick,
        action_tick: packet.first.action_tick,
        contacts,
        outcome,
        player_health_delta_tenths: quantized_delta(before.player.health, after.player.health),
        opponent_health_delta_tenths: quantized_delta(
            before.opponent.health,
            after.opponent.health,
        ),
        player_stamina_delta_tenths: quantized_delta(before.player.stamina, after.player.stamina),
        opponent_stamina_delta_tenths: quantized_delta(
            before.opponent.stamina,
            after.opponent.stamina,
        ),
        resolved_truth_hash,
    }
}

fn quantized_delta(before: f32, after: f32) -> i32 {
    ((after - before) * 10.0).round() as i32
}

#[cfg(test)]
mod tests {
    use std::env;

    use glam::vec3;

    use super::*;
    use crate::cleanbox;
    use crate::duel_world::DuelWorld;
    use crate::truth::{Action, CombatTruth, PlayerInput, Stance};

    fn snapshot(frame: u32) -> ReplaySnapshot {
        ReplaySnapshot {
            frame,
            phase: "Plan".to_string(),
            player_health: 1000,
            opponent_health: 1000,
            player_stamina: 500,
            opponent_stamina: 500,
        }
    }

    fn events() -> Vec<MatchEvent> {
        vec![
            MatchEvent {
                frame: 0,
                kind: EventKind::PhaseChange {
                    from: "Observe".to_string(),
                    to: "Plan".to_string(),
                },
            },
            MatchEvent {
                frame: 12,
                kind: EventKind::ActionCommitted {
                    side: Side::Player,
                    action: "Thrust".to_string(),
                },
            },
            MatchEvent {
                frame: 12,
                kind: EventKind::ActionCommitted {
                    side: Side::Opponent,
                    action: "Block".to_string(),
                },
            },
            MatchEvent {
                frame: 60,
                kind: EventKind::Contact {
                    point: [0.1, 1.2, 0.3],
                    normal: [0.0, 1.0, 0.0],
                },
            },
            MatchEvent {
                frame: 120,
                kind: EventKind::MatchEnd { winner: None },
            },
        ]
    }

    #[test]
    fn replay_save_load_roundtrip() {
        let path = env::temp_dir().join("just_dodge_replay_roundtrip.jdrp");
        let _ = std::fs::remove_file(&path);

        let mut recorder = ReplayRecorder::new(0xDEAD_BEEF_CAFE_BABE);
        recorder.record_frame(0, 1, &snapshot(0));
        recorder.record_frame(1, 2, &snapshot(1));
        for e in events() {
            recorder.record_event(e);
        }

        recorder.save(&path).expect("save failed");
        let loaded = ReplayRecorder::load(&path).expect("load failed");

        assert_eq!(loaded.seed, recorder.seed);
        assert_eq!(loaded.frames.len(), recorder.frames.len());
        assert_eq!(loaded.events.len(), recorder.events.len());

        for (orig, loaded) in recorder.frames.iter().zip(&loaded.frames) {
            assert_eq!(orig.frame, loaded.frame);
            assert_eq!(orig.truth_hash, loaded.truth_hash);
            assert_eq!(orig.serialized_state, loaded.serialized_state);
            let orig_snap: ReplaySnapshot = postcard::from_bytes(&orig.serialized_state).unwrap();
            let loaded_snap: ReplaySnapshot =
                postcard::from_bytes(&loaded.serialized_state).unwrap();
            assert_eq!(orig_snap, loaded_snap);
        }

        assert_eq!(loaded.events, recorder.events);
    }

    #[test]
    fn replay_bytes_identical_for_identical_input() {
        let path_a = env::temp_dir().join("just_dodge_replay_identical_a.jdrp");
        let path_b = env::temp_dir().join("just_dodge_replay_identical_b.jdrp");
        let _ = std::fs::remove_file(&path_a);
        let _ = std::fs::remove_file(&path_b);

        for path in [&path_a, &path_b] {
            let mut recorder = ReplayRecorder::new(1234);
            recorder.record_frame(0, 42, &snapshot(0));
            recorder.record_frame(1, 43, &snapshot(1));
            recorder.record_event(MatchEvent {
                frame: 1,
                kind: EventKind::Damage {
                    side: Side::Opponent,
                    region: "Head".to_string(),
                    amount: 15.5,
                },
            });
            recorder.save(path).unwrap();
        }

        let bytes_a = std::fs::read(&path_a).unwrap();
        let bytes_b = std::fs::read(&path_b).unwrap();
        assert_eq!(bytes_a, bytes_b);
    }

    fn resolved_packet(
        opponent_action: Action,
    ) -> (TruthSnapshot, TruthSnapshot, DuelWorldTruthTick, u64) {
        let mut truth = CombatTruth::new();
        for _ in 0..30 {
            truth.tick();
        }
        for (side, action) in [
            (Side::Player, Action::Thrust),
            (Side::Opponent, opponent_action),
        ] {
            truth.apply_input(side, PlayerInput::SelectAction(action));
            truth.apply_input(side, PlayerInput::SelectStance(Stance::Top));
            truth.apply_input(side, PlayerInput::Commit);
        }
        for _ in 0..80 {
            truth.tick();
        }
        let before = truth.snapshot().clone();
        let mut world = DuelWorld::new();
        let packet = cleanbox::submit_resolve_packet(
            &mut truth,
            &mut world,
            vec3(0.0, 0.0, 1.0),
            vec3(0.0, 0.0, -1.0),
        )
        .unwrap()
        .unwrap();
        truth.tick();
        let after = truth.snapshot().clone();
        let hash = truth.truth_hash();
        (before, after, packet, hash)
    }

    fn resolved_guard_packet() -> (TruthSnapshot, TruthSnapshot, DuelWorldTruthTick, u64) {
        resolved_packet(Action::Block)
    }

    fn recorder_with_resolved_packet(opponent_action: Action) -> ReplayRecorder {
        let (before, after, packet, hash) = resolved_packet(opponent_action);
        let mut recorder = ReplayRecorder::new(77);
        recorder.record_frame(
            after.frame,
            hash,
            &ReplaySnapshot {
                frame: after.frame,
                phase: after.phase.name().to_string(),
                player_health: (after.player.health * 10.0).round() as u32,
                opponent_health: (after.opponent.health * 10.0).round() as u32,
                player_stamina: (after.player.stamina * 10.0).round() as u32,
                opponent_stamina: (after.opponent.stamina * 10.0).round() as u32,
            },
        );
        recorder.record_resolve_packet(&before, &after, &packet, hash);
        recorder
    }

    #[test]
    fn resolve_receipt_retains_full_physics_and_truth_evidence() {
        let (before, after, packet, hash) = resolved_guard_packet();
        let mut recorder = ReplayRecorder::new(77);
        recorder.record_resolve_packet(&before, &after, &packet, hash);

        assert_eq!(recorder.events.len(), 1);
        assert_eq!(recorder.events[0].frame, after.frame);
        let EventKind::ResolvePacket { receipt } = &recorder.events[0].kind else {
            panic!("expected one ResolvePacket event");
        };
        assert_eq!(receipt.truth_frame, after.frame);
        assert_eq!(receipt.first_physics_tick + 1, receipt.second_physics_tick);
        assert_eq!(receipt.outcome, ResolveOutcome::Guard);
        assert_eq!(receipt.player_action, "Some(Thrust)");
        assert_eq!(receipt.opponent_action, "Some(Block)");
        assert!(!receipt.contacts.is_empty());
        assert!(
            receipt
                .contacts
                .iter()
                .all(|contact| contact.time_of_impact.is_finite())
        );
        assert!(receipt.player_stamina_delta_tenths < 0);
        assert_eq!(receipt.resolved_truth_hash, hash);
    }

    #[test]
    fn resolve_receipt_save_load_is_byte_stable() {
        let path_a = env::temp_dir().join("just_dodge_resolve_receipt_a.jdrp");
        let path_b = env::temp_dir().join("just_dodge_resolve_receipt_b.jdrp");
        let _ = std::fs::remove_file(&path_a);
        let _ = std::fs::remove_file(&path_b);
        for path in [&path_a, &path_b] {
            let recorder = recorder_with_resolved_packet(Action::Block);
            recorder.save(path).unwrap();
            let loaded = ReplayRecorder::load(path).unwrap();
            assert_eq!(loaded.events, recorder.events);
            assert_eq!(
                loaded.reduce_resolve_packets().unwrap(),
                recorder.reduce_resolve_packets().unwrap()
            );
        }
        assert_eq!(
            std::fs::read(path_a).unwrap(),
            std::fs::read(path_b).unwrap()
        );
    }

    #[test]
    fn reducer_emits_stable_guard_and_whiff_tables() {
        let guard = recorder_with_resolved_packet(Action::Block);
        let guard_report = guard.reduce_resolve_packets().unwrap();
        assert!(guard_report.contains("resolve_packets=1"));
        assert!(guard_report.contains("Guard"));
        assert!(guard_report.contains("Some(Thrust)"));
        assert_eq!(
            guard_report
                .lines()
                .filter(|line| line.starts_with("contact ") && !line.ends_with("(none)"))
                .count(),
            2
        );
        assert!(guard_report.ends_with("verdict=PASS\n"));

        let whiff = recorder_with_resolved_packet(Action::Dodge);
        let whiff_report = whiff.reduce_resolve_packets().unwrap();
        assert!(whiff_report.contains("Whiff"));
        assert!(whiff_report.contains("Some(Dodge)"));
        assert!(whiff_report.contains("contact (none)"));
    }

    #[test]
    fn reducer_rejects_receipt_invariant_violations() {
        let mut missing_snapshot = recorder_with_resolved_packet(Action::Block);
        missing_snapshot.frames.clear();
        assert!(missing_snapshot.reduce_resolve_packets().is_err());

        let mut mismatched_hash = recorder_with_resolved_packet(Action::Block);
        let EventKind::ResolvePacket { receipt } = &mut mismatched_hash.events[0].kind else {
            unreachable!();
        };
        receipt.resolved_truth_hash ^= 1;
        assert!(mismatched_hash.reduce_resolve_packets().is_err());

        let mut nonconsecutive = recorder_with_resolved_packet(Action::Block);
        let EventKind::ResolvePacket { receipt } = &mut nonconsecutive.events[0].kind else {
            unreachable!();
        };
        receipt.second_physics_tick += 1;
        assert!(nonconsecutive.reduce_resolve_packets().is_err());

        let mut invalid_toi = recorder_with_resolved_packet(Action::Block);
        let EventKind::ResolvePacket { receipt } = &mut invalid_toi.events[0].kind else {
            unreachable!();
        };
        receipt.contacts[0].time_of_impact = f32::NAN;
        assert!(invalid_toi.reduce_resolve_packets().is_err());

        let mut contradictory_outcome = recorder_with_resolved_packet(Action::Block);
        let EventKind::ResolvePacket { receipt } = &mut contradictory_outcome.events[0].kind else {
            unreachable!();
        };
        receipt.outcome = ResolveOutcome::Whiff;
        assert!(contradictory_outcome.reduce_resolve_packets().is_err());

        let mut duplicate_frame = recorder_with_resolved_packet(Action::Block);
        duplicate_frame
            .events
            .push(duplicate_frame.events[0].clone());
        assert!(duplicate_frame.reduce_resolve_packets().is_err());
    }

    #[test]
    fn replay_load_bad_magic_fails() {
        let path = env::temp_dir().join("just_dodge_replay_bad_magic.jdrp");
        let _ = std::fs::remove_file(&path);
        std::fs::write(&path, b"NOTJDRP\0\0\0\0").unwrap();
        assert!(ReplayRecorder::load(&path).is_err());
    }

    #[test]
    fn replay_load_bad_version_fails() {
        let path = env::temp_dir().join("just_dodge_replay_bad_version.jdrp");
        let _ = std::fs::remove_file(&path);
        let mut bytes = Vec::new();
        bytes.extend_from_slice(MAGIC);
        bytes.extend_from_slice(&9999u32.to_le_bytes());
        bytes.extend_from_slice(&0u64.to_le_bytes());
        std::fs::write(&path, bytes).unwrap();
        assert!(ReplayRecorder::load(&path).is_err());
    }
}
