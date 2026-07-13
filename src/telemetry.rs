//! Per-frame structured telemetry emitted to a JSONL file.
//!
//! Activated by `--telemetry` flag. Writes one JSON object per
//! rendered frame to /tmp/just_dodge_tlm.jsonl.

use std::fs::File;
use std::io::{BufWriter, Write};

/// Aggregated telemetry for a single frame.
#[derive(Default)]
pub struct TelemetryFrame {
    pub t: f32,
    pub player_pos: [f32; 3],
    pub player_intent: String,
    pub opponent_phase: String,
    pub combat_result: Option<String>,
    pub clip_frame: usize,
}

pub struct Telemetry {
    writer: Option<BufWriter<File>>,
    frame_count: u64,
}

impl Telemetry {
    /// Create telemetry system. If `enabled` is false, writes are no-ops.
    pub fn new(enabled: bool) -> Self {
        let writer = if enabled {
            File::create("/tmp/just_dodge_tlm.jsonl")
                .ok()
                .map(BufWriter::new)
        } else {
            None
        };
        Self {
            writer,
            frame_count: 0,
        }
    }

    /// Write one frame. No-op if telemetry is disabled.
    pub fn emit(&mut self, f: &TelemetryFrame) {
        if let Some(w) = &mut self.writer {
            self.frame_count += 1;
            let combat = match &f.combat_result {
                Some(s) => format!("\"{}\"", s),
                None => "null".to_string(),
            };
            let line = format!(
                r#"{{"fn":{},"t":{:.3},"player_pos":[{:.3},{:.3},{:.3}],"intent":"{}","phase":"{}","combat":{},"frame":{}}}"#,
                self.frame_count,
                f.t,
                f.player_pos[0],
                f.player_pos[1],
                f.player_pos[2],
                f.player_intent,
                f.opponent_phase,
                combat,
                f.clip_frame,
            );
            let _ = writeln!(w, "{}", line);
        }
    }

    pub fn flush(&mut self) {
        if let Some(w) = &mut self.writer {
            let _ = w.flush();
        }
    }
}
