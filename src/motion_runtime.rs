//! Fail-closed local MotionBricks source-cache loader for M3.
//!
//! This validates the checked-in Rust ONNX/NPY artifact bundle and preloads the
//! measured G1 source windows needed by the current three-action M3 slice. The
//! cache is presentation-only: it neither writes truth nor promotes the source
//! windows to C0 runtime playback before retarget and readability gates pass.

use anyhow::{Context, Result, bail};
use glam::Mat4;
use std::time::{Duration, Instant};

use crate::motion::{Action, MotionPipeline};
use crate::motion_request::MotionRequest;
use crate::motion_service::MotionService;

const G1_PARENTS: [i32; 34] = [
    -1, 0, 1, 2, 3, 4, 5, 6, 0, 8, 9, 10, 11, 12, 13, 0, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
    17, 26, 27, 28, 29, 30, 31, 32,
];
#[cfg(test)]
const M3_ACTIONS: [Action; 3] = [Action::Strike, Action::Block, Action::Grab];

/// Evidence from one fail-closed source-clip preload.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MotionClipReceipt {
    pub action: Action,
    pub frame_count: usize,
    pub preload_time: Duration,
}

/// Immutable source cache for the public M3 motion contract.
pub struct MotionRuntime {
    /// Keep validated ONNX/NPY sessions resident. The cached M3 source clips are
    /// not a substitute for future action-conditioned neural generation.
    _artifact_pipeline: MotionPipeline,
    strike: Vec<[Mat4; 34]>,
    block: Vec<[Mat4; 34]>,
    grab: Vec<[Mat4; 34]>,
    receipts: [MotionClipReceipt; 3],
    total_preload_time: Duration,
}

impl MotionRuntime {
    /// Load every required artifact and source clip before match start.
    ///
    /// No fallback is provided: missing ONNX/NPY artifacts, unavailable Python
    /// service, missing source primitive, non-finite matrix, or non-rigid G1
    /// segment aborts loading with the exact action and frame in the error.
    pub fn load(assets_path: &str) -> Result<Self> {
        let total_start = Instant::now();
        let artifact_pipeline = MotionPipeline::new(assets_path)
            .with_context(|| format!("MotionBricks artifact validation failed at {assets_path}"))?;
        let service =
            MotionService::new().context("MotionBricks Python service initialization failed")?;

        let (strike, strike_receipt) = Self::load_clip(&service, Action::Strike)?;
        let (block, block_receipt) = Self::load_clip(&service, Action::Block)?;
        let (grab, grab_receipt) = Self::load_clip(&service, Action::Grab)?;
        Ok(Self {
            _artifact_pipeline: artifact_pipeline,
            strike,
            block,
            grab,
            receipts: [strike_receipt, block_receipt, grab_receipt],
            total_preload_time: total_start.elapsed(),
        })
    }

    /// Return the exact cached source window for a public M3 request.
    pub fn frames_for_request(&self, request: MotionRequest) -> Result<&[[Mat4; 34]]> {
        self.frames_for_action(request.action)
    }

    /// Return the exact cached source window for one M3 action.
    pub fn frames_for_action(&self, action: Action) -> Result<&[[Mat4; 34]]> {
        match action {
            Action::Strike => Ok(&self.strike),
            Action::Block => Ok(&self.block),
            Action::Grab => Ok(&self.grab),
            unsupported => bail!(
                "M3 MotionRuntime has no source clip for {unsupported:?}; refusing bind-pose fallback"
            ),
        }
    }

    pub const fn receipts(&self) -> &[MotionClipReceipt; 3] {
        &self.receipts
    }

    pub const fn total_preload_time(&self) -> Duration {
        self.total_preload_time
    }

    fn load_clip(
        service: &MotionService,
        action: Action,
    ) -> Result<(Vec<[Mat4; 34]>, MotionClipReceipt)> {
        let start = Instant::now();
        let action_name = match action {
            Action::Strike => "strike",
            Action::Block => "block",
            Action::Grab => "grab",
            unsupported => bail!("M3 source preload does not admit {unsupported:?}"),
        };
        let frames = service
            .load_primitive_clip(action_name, "longsword", "top")
            .with_context(|| {
                format!("missing or invalid M3 source primitive {action_name}/longsword/top")
            })?;
        validate_g1_clip(action, &frames)?;
        let receipt = MotionClipReceipt {
            action,
            frame_count: frames.len(),
            preload_time: start.elapsed(),
        };
        Ok((frames, receipt))
    }
}

fn validate_g1_clip(action: Action, frames: &[[Mat4; 34]]) -> Result<()> {
    if frames.len() < 2 {
        bail!(
            "{action:?} source clip has {} frame(s); require at least two",
            frames.len()
        );
    }
    let reference_lengths: [f32; 34] = std::array::from_fn(|joint| {
        if G1_PARENTS[joint] < 0 {
            0.0
        } else {
            segment_length(&frames[0], joint)
        }
    });
    for (frame_index, frame) in frames.iter().enumerate() {
        for joint in 0..34 {
            if !frame[joint].is_finite() {
                bail!("{action:?} source frame {frame_index} joint {joint} is non-finite");
            }
            if G1_PARENTS[joint] >= 0 {
                let length = segment_length(frame, joint);
                let delta = (length - reference_lengths[joint]).abs();
                if delta >= 1e-4 {
                    bail!(
                        "{action:?} source frame {frame_index} joint {joint} changed segment length: {length:.9} vs {:.9} (delta {delta:.9})",
                        reference_lengths[joint]
                    );
                }
            }
        }
    }
    Ok(())
}

fn segment_length(frame: &[Mat4; 34], joint: usize) -> f32 {
    let parent = G1_PARENTS[joint] as usize;
    (frame[joint].w_axis.truncate() - frame[parent].w_axis.truncate()).length()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::asset;
    use crate::milestone3 as m3;
    use crate::motion_request::motion_request_from_snapshot;
    use crate::motion_retarget;

    #[test]
    fn missing_artifacts_fail_closed_before_motion_service_startup() {
        let missing = concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/target/missing-motion-artifacts"
        );
        std::fs::create_dir_all(missing).unwrap();
        let error = match MotionRuntime::load(missing) {
            Ok(_) => panic!("missing artifacts must fail closed"),
            Err(error) => error.to_string(),
        };
        assert!(error.contains("artifact validation failed"), "{error}");
    }

    #[test]
    #[ignore = "requires the separately hydrated, manifest-verified MotionBricks artifact bundle"]
    fn preloaded_m3_clips_are_finite_rigid_and_cached() {
        let runtime = MotionRuntime::load(concat!(env!("CARGO_MANIFEST_DIR"), "/assets"))
            .expect("M3 source cache must load valid local artifacts and clips");
        assert_eq!(runtime.receipts().map(|receipt| receipt.action), M3_ACTIONS);
        assert!(
            runtime
                .receipts()
                .iter()
                .all(|receipt| receipt.frame_count >= 2)
        );

        for action in M3_ACTIONS {
            let cache_read_start = Instant::now();
            let first = runtime.frames_for_action(action).unwrap();
            assert!(
                cache_read_start.elapsed() <= Duration::from_millis(16),
                "{action:?} cache lookup exceeded the per-frame presentation budget"
            );
            let second = runtime.frames_for_action(action).unwrap();
            assert!(std::ptr::eq(first.as_ptr(), second.as_ptr()));
            validate_g1_clip(action, first).unwrap();
        }
        let unsupported = runtime
            .frames_for_action(Action::Idle)
            .unwrap_err()
            .to_string();
        assert!(
            unsupported.contains("refusing bind-pose fallback"),
            "{unsupported}"
        );

        let mesh = asset::load_skinned(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/assets/source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin"
        ))
        .unwrap();
        for action in M3_ACTIONS {
            let frames = runtime.frames_for_action(action).unwrap();
            let source_reference = &frames[0];
            let first_receipts: Vec<u64> = frames
                .iter()
                .map(|frame| {
                    let skin = motion_retarget::retarget_g1_frame_to_armored_skin(
                        &mesh,
                        source_reference,
                        frame,
                    )
                    .unwrap();
                    motion_retarget::armored_pose_receipt(&skin)
                })
                .collect();
            let second_receipts: Vec<u64> = frames
                .iter()
                .map(|frame| {
                    let skin = motion_retarget::retarget_g1_frame_to_armored_skin(
                        &mesh,
                        source_reference,
                        frame,
                    )
                    .unwrap();
                    motion_retarget::armored_pose_receipt(&skin)
                })
                .collect();
            assert_eq!(first_receipts, second_receipts, "{action:?} pose receipts");
        }

        let mut game = m3::Match::new(99);
        while game.snapshot().phase != m3::Phase::Plan {
            game.tick();
        }
        game.apply(m3::Side::Player, m3::Input::Select(m3::Action::Strike))
            .unwrap();
        game.apply(m3::Side::Opponent, m3::Input::Select(m3::Action::Grab))
            .unwrap();
        game.apply(m3::Side::Player, m3::Input::Commit).unwrap();
        game.apply(m3::Side::Opponent, m3::Input::Commit).unwrap();
        while game.snapshot().phase != m3::Phase::Reveal {
            game.tick();
        }
        let request = motion_request_from_snapshot(game.snapshot(), m3::Side::Player).unwrap();
        assert_eq!(request.action, Action::Strike);
        assert_eq!(
            runtime.frames_for_request(request).unwrap(),
            runtime.frames_for_action(Action::Strike).unwrap()
        );
    }
}
