// Deterministic replay recorder and loader.
// See docs/design/IMPLEMENTATION_PLAN_3ACTION.md for the contract.

use std::fs::File;
use std::io::{Read, Write};
use std::path::Path;

use anyhow::{bail, Context};

use crate::truth::Side;

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
    PhaseChange { from: String, to: String },
    ActionCommitted { side: Side, action: String },
    Contact { point: [f32; 3], normal: [f32; 3] },
    Damage { side: Side, region: String, amount: f32 },
    MatchEnd { winner: Option<Side> },
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
        let serialized_state = postcard::to_stdvec(snapshot)
            .expect("ReplaySnapshot serialization must not fail");
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
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;

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
                    action: "Strike".to_string(),
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
            let loaded_snap: ReplaySnapshot = postcard::from_bytes(&loaded.serialized_state).unwrap();
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
