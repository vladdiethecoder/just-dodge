//! M4 non-blocking MotionBricks presentation plan service.
//!
//! The deterministic 120 Hz physics / 60 Hz truth path never owns this service
//! and never waits for it. A plan lock submits a presentation request; subsequent
//! truth ticks only poll a buffered result. Until a clip arrives, presentation
//! keeps the previous pose. Motion readiness and timing are deliberately absent
//! from [`PlanPhase`](crate::intent::PlanPhase)'s snapshot and truth hash.
//!
//! The released MotionBricks conditioning surface used here is deliberately
//! narrow: root plus complete-pose keyframes for learned in-betweening. This
//! module does **not** accept clearance, limb-state, weapon-hand, opponent,
//! injury, momentum, speed, or velocity conditions. Those need new learned
//! condition packets and training; decoded-joint replacement is forbidden.

use std::collections::HashMap;
#[cfg(feature = "motion-inference")]
use std::collections::HashSet;
use std::fmt;
use std::sync::Arc;
use std::time::Duration;
#[cfg(feature = "motion-inference")]
use std::time::Instant;

use glam::{Mat4, Vec3};

use crate::intent::{Intent, MoveDirection, PlanEvent, PlanPhase, PlanSnapshot, RootPosition};
#[cfg(feature = "motion-inference")]
use crate::motion::Action;
use crate::motion::G1_NB;
use crate::truth::Side;

/// A presentation-only G1 full-body pose. It is never admitted into truth.
pub type FullPose = [Mat4; G1_NB];
/// Stable local identifier for one plan-lock presentation request.
pub type MotionRequestId = u64;

/// The six baked runtime clip families required by the M4 shipped path.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CoreMotionIntent {
    Strike,
    Block,
    Grab,
    Move,
    Dodge,
    Idle,
}

impl CoreMotionIntent {
    /// Map non-core visual transitions to Idle rather than inventing a runtime
    /// model condition. Core match actions retain their own baked family.
    pub const fn from_intent(intent: Intent) -> Self {
        match intent {
            Intent::Strike { .. } => Self::Strike,
            Intent::Block => Self::Block,
            Intent::Grab => Self::Grab,
            Intent::Move { .. } => Self::Move,
            Intent::Dodge { .. } => Self::Dodge,
            Intent::Idle
            | Intent::Feint
            | Intent::Cancel
            | Intent::Draw
            | Intent::Sheath
            | Intent::Clinch { .. } => Self::Idle,
        }
    }

    #[cfg(feature = "motion-inference")]
    const fn motionbricks_action(self) -> Action {
        match self {
            Self::Strike => Action::Strike,
            Self::Block => Action::Block,
            Self::Grab => Action::Grab,
            // The released bridge has a dodge primitive but no explicit
            // displacement-control input. Root keyframes carry the supported
            // displacement condition for these two action families.
            Self::Move | Self::Dodge => Action::Dodge,
            Self::Idle => Action::Idle,
        }
    }
}

/// The official released conditioning surface: a root transform and complete
/// G1 poses at both ends of an in-betweening interval.
#[derive(Clone)]
pub struct SupportedKeyframes {
    pub start_root: Mat4,
    pub end_root: Mat4,
    pub start_pose: FullPose,
    pub end_pose: FullPose,
}

impl fmt::Debug for SupportedKeyframes {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("SupportedKeyframes")
            .finish_non_exhaustive()
    }
}

/// Immutable request captured when M1 locks an intent. All fields are
/// presentation inputs; the source snapshot is read-only and is not mutated.
#[derive(Debug, Clone)]
pub struct MotionPlanRequest {
    pub id: MotionRequestId,
    pub side: Side,
    pub intent: CoreMotionIntent,
    pub displacement_mm: [i32; 3],
    pub keyframes: SupportedKeyframes,
}

/// A ready presentation clip. The `Arc` permits the baked provider to serve
/// immutable embedded data without copying it on every plan lock.
#[derive(Debug, Clone)]
pub struct MotionClip {
    pub request_id: MotionRequestId,
    pub intent: CoreMotionIntent,
    pub frames: Arc<[FullPose]>,
    pub receipt: MotionGenerationReceipt,
}

/// Measured completion data. It is diagnostics only and explicitly excluded
/// from the deterministic truth state and its hash.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MotionGenerationReceipt {
    pub request_id: MotionRequestId,
    pub provider: MotionProviderKind,
    pub generation_latency: Duration,
    pub frame_count: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MotionProviderKind {
    Baked,
    /// Dev/training-only provider using released root/full-pose keyframe
    /// in-betweening. Never compiled into a no-default-features shipped build.
    GenerativeKeyframeInbetweening,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MotionSubmitReceipt {
    pub request_id: MotionRequestId,
    pub provider: MotionProviderKind,
}

#[derive(Debug, Clone)]
pub enum MotionPoll {
    Pending,
    Ready(MotionClip),
    Rejected(MotionServiceError),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MotionServiceError(String);

impl MotionServiceError {
    fn new(message: impl Into<String>) -> Self {
        Self(message.into())
    }
}

impl fmt::Display for MotionServiceError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for MotionServiceError {}

/// Non-blocking provider contract. `submit` enqueues work and `poll` uses only
/// already-buffered data; neither method may wait for inference.
pub trait AsyncMotionPlanProvider: Send {
    fn submit(
        &mut self,
        request: MotionPlanRequest,
    ) -> Result<MotionSubmitReceipt, MotionServiceError>;
    /// Discards a superseded plan-lock request without waiting for a worker.
    /// A detached inference worker may finish later; its result is ignored.
    fn cancel(&mut self, request_id: MotionRequestId);
    fn poll(&mut self, request_id: MotionRequestId) -> MotionPoll;
}

/// Presentation plan-service handle used by M1-facing glue. It owns no truth
/// state and cannot call `PlanPhase::step_truth_tick`.
pub struct MotionPlanService {
    provider: Box<dyn AsyncMotionPlanProvider>,
}

impl MotionPlanService {
    pub fn new(provider: impl AsyncMotionPlanProvider + 'static) -> Self {
        Self {
            provider: Box::new(provider),
        }
    }

    /// TEST-ONLY: embedded baked clips for deterministic provider tests.
    /// Canon (2026-07-19 ruling): baked clips are forbidden in every runtime
    /// mode — ship is live generative MotionBricks — so no runtime
    /// constructor exists; this survives only to exercise the provider
    /// contract in tests.
    pub fn baked() -> Result<Self, MotionServiceError> {
        Ok(Self::new(BakedClipProvider::embedded()?))
    }

    pub fn submit(
        &mut self,
        request: MotionPlanRequest,
    ) -> Result<MotionSubmitReceipt, MotionServiceError> {
        self.provider.submit(request)
    }

    pub fn cancel(&mut self, request_id: MotionRequestId) {
        self.provider.cancel(request_id);
    }

    /// Strictly non-blocking: this only consumes a result that a provider has
    /// already buffered, or reports `Pending`.
    pub fn poll(&mut self, request_id: MotionRequestId) -> MotionPoll {
        self.provider.poll(request_id)
    }
}

/// TEST-ONLY provider: embedded `assets/motion/m4_baked/` clips. Baked clips
/// are canon-forbidden at runtime (2026-07-19 ruling); this type exists only
/// to test the provider contract deterministically.
pub struct BakedClipProvider {
    clips: HashMap<CoreMotionIntent, Arc<[FullPose]>>,
    pending: HashMap<MotionRequestId, CoreMotionIntent>,
}

impl BakedClipProvider {
    pub fn embedded() -> Result<Self, MotionServiceError> {
        let clips = [
            (
                CoreMotionIntent::Strike,
                include_bytes!("../assets/motion/m4_baked/strike.g1").as_slice(),
            ),
            (
                CoreMotionIntent::Block,
                include_bytes!("../assets/motion/m4_baked/block.g1").as_slice(),
            ),
            (
                CoreMotionIntent::Grab,
                include_bytes!("../assets/motion/m4_baked/grab.g1").as_slice(),
            ),
            (
                CoreMotionIntent::Move,
                include_bytes!("../assets/motion/m4_baked/move.g1").as_slice(),
            ),
            (
                CoreMotionIntent::Dodge,
                include_bytes!("../assets/motion/m4_baked/dodge.g1").as_slice(),
            ),
            (
                CoreMotionIntent::Idle,
                include_bytes!("../assets/motion/m4_baked/idle.g1").as_slice(),
            ),
        ]
        .into_iter()
        .map(|(intent, bytes)| load_validated_baked_clip(intent, bytes).map(|clip| (intent, clip)))
        .collect::<Result<HashMap<_, _>, _>>()?;
        Ok(Self {
            clips,
            pending: HashMap::new(),
        })
    }
}

impl AsyncMotionPlanProvider for BakedClipProvider {
    fn submit(
        &mut self,
        request: MotionPlanRequest,
    ) -> Result<MotionSubmitReceipt, MotionServiceError> {
        if self.pending.insert(request.id, request.intent).is_some() {
            return Err(MotionServiceError::new("duplicate baked motion request id"));
        }
        Ok(MotionSubmitReceipt {
            request_id: request.id,
            provider: MotionProviderKind::Baked,
        })
    }

    fn cancel(&mut self, request_id: MotionRequestId) {
        self.pending.remove(&request_id);
    }

    fn poll(&mut self, request_id: MotionRequestId) -> MotionPoll {
        let Some(intent) = self.pending.remove(&request_id) else {
            return MotionPoll::Pending;
        };
        let Some(frames) = self.clips.get(&intent) else {
            return MotionPoll::Rejected(MotionServiceError::new("missing baked core-intent clip"));
        };
        MotionPoll::Ready(MotionClip {
            request_id,
            intent,
            frames: Arc::clone(frames),
            receipt: MotionGenerationReceipt {
                request_id,
                provider: MotionProviderKind::Baked,
                generation_latency: Duration::ZERO,
                frame_count: frames.len(),
            },
        })
    }
}

fn load_validated_baked_clip(
    intent: CoreMotionIntent,
    bytes: &[u8],
) -> Result<Arc<[FullPose]>, MotionServiceError> {
    let frames = crate::motion::load_g1_frames_from_bytes(bytes).map_err(|error| {
        MotionServiceError::new(format!("invalid {intent:?} baked motion clip: {error}"))
    })?;
    validate_full_pose_clip(&frames).map_err(|error| {
        MotionServiceError::new(format!("invalid {intent:?} baked motion clip: {error}"))
    })?;
    Ok(Arc::from(frames))
}

fn validate_full_pose_clip(frames: &[FullPose]) -> Result<(), &'static str> {
    if frames.len() < 2 {
        return Err("requires at least two frames");
    }
    if frames
        .iter()
        .flat_map(|frame| frame.iter())
        .any(|matrix| !matrix.is_finite())
    {
        return Err("contains a non-finite transform");
    }
    Ok(())
}

/// Dev/training-only asynchronous MotionBricks provider. ONE persistent
/// worker thread owns the validated `MotionPipeline` and the PyO3
/// `MotionService` (a single model load, serialized inference — concurrent
/// per-request services crash the GPU/bridge), draining a request queue.
/// The truth/presentation caller only observes its `mpsc::try_recv` buffer.
#[cfg(feature = "motion-inference")]
pub struct GenerativeMotionProvider {
    request_tx: std::sync::mpsc::Sender<MotionPlanRequest>,
    receiver: std::sync::mpsc::Receiver<GenerativeWorkerResult>,
    pending: HashSet<MotionRequestId>,
    ready: HashMap<MotionRequestId, Result<MotionClip, MotionServiceError>>,
}

#[cfg(feature = "motion-inference")]
struct GenerativeWorkerResult {
    request_id: MotionRequestId,
    result: Result<MotionClip, MotionServiceError>,
}

#[cfg(feature = "motion-inference")]
impl GenerativeMotionProvider {
    pub fn new(assets_path: impl Into<String>) -> Self {
        let (request_tx, request_rx) = std::sync::mpsc::channel::<MotionPlanRequest>();
        let (result_tx, receiver) = std::sync::mpsc::channel();
        let assets_path = assets_path.into();
        std::thread::spawn(move || {
            // Persistent single-worker loop: artifact validation and the
            // Python service start ONCE; a startup failure rejects every
            // request with the same error; a generation panic rejects that
            // request only.
            eprintln!("[generative-worker] boot");
            let startup = crate::motion::MotionPipeline::new(&assets_path)
                .map(|_| ())
                .and_then(|_| crate::motion_service::MotionService::new());
            eprintln!("[generative-worker] startup ready={}", startup.is_ok());
            for request in request_rx {
                let start = Instant::now();
                let request_id = request.id;
                let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    let service = startup.as_ref().map_err(|error| {
                        MotionServiceError::new(format!(
                            "MotionBricks bridge startup failed: {error}"
                        ))
                    })?;
                    generate_supported_keyframe_inbetweening(service, request, start)
                }))
                .unwrap_or_else(|_| {
                    Err(MotionServiceError::new(
                        "generative worker panicked (bridge/assets unavailable)",
                    ))
                });
                eprintln!(
                    "[generative-worker] request={request_id} ok={} latency_ms={}{}",
                    result.is_ok(),
                    start.elapsed().as_millis(),
                    result
                        .as_ref()
                        .err()
                        .map(|e| format!(" err={e}"))
                        .unwrap_or_default()
                );
                // The receiver may have been dropped at application shutdown;
                // a worker result is presentation-only, so discard is safe.
                let _ = result_tx.send(GenerativeWorkerResult { request_id, result });
            }
        });
        Self {
            request_tx,
            receiver,
            pending: HashSet::new(),
            ready: HashMap::new(),
        }
    }

    fn drain_ready(&mut self) {
        while let Ok(worker_result) = self.receiver.try_recv() {
            if self.pending.remove(&worker_result.request_id) {
                self.ready
                    .insert(worker_result.request_id, worker_result.result);
            }
        }
    }
}

#[cfg(feature = "motion-inference")]
impl AsyncMotionPlanProvider for GenerativeMotionProvider {
    fn submit(
        &mut self,
        request: MotionPlanRequest,
    ) -> Result<MotionSubmitReceipt, MotionServiceError> {
        if !self.pending.insert(request.id) {
            return Err(MotionServiceError::new(
                "duplicate generative motion request id",
            ));
        }
        let request_id = request.id;
        self.request_tx.send(request).map_err(|_| {
            self.pending.remove(&request_id);
            MotionServiceError::new("generative worker disconnected")
        })?;
        Ok(MotionSubmitReceipt {
            request_id,
            provider: MotionProviderKind::GenerativeKeyframeInbetweening,
        })
    }

    fn cancel(&mut self, request_id: MotionRequestId) {
        self.pending.remove(&request_id);
        self.ready.remove(&request_id);
    }

    fn poll(&mut self, request_id: MotionRequestId) -> MotionPoll {
        self.drain_ready();
        match self.ready.remove(&request_id) {
            Some(Ok(clip)) => MotionPoll::Ready(clip),
            Some(Err(error)) => MotionPoll::Rejected(error),
            None => MotionPoll::Pending,
        }
    }
}

/// Runs only in a worker thread and only with `motion-inference`. The current
/// bridge accepts full G1 matrix context; the two supplied poses carry the
/// officially-supported root/full-pose keyframes. No decoded transform is
/// rewritten after generation.
#[cfg(feature = "motion-inference")]
fn generate_supported_keyframe_inbetweening(
    service: &crate::motion_service::MotionService,
    request: MotionPlanRequest,
    start: Instant,
) -> Result<MotionClip, MotionServiceError> {
    let action = format!("{:?}", request.intent.motionbricks_action());
    let keyframes = [request.keyframes.start_pose, request.keyframes.end_pose];
    let frames =
        match service.generate_clip(&action, "Longsword", "Top", Some(&keyframes), request.id) {
            Ok(frames) => frames,
            Err(first_error) => {
                // Measured (2026-07-19): the second sequential keyed-context call
                // fails with RuntimeError "unknown parameter type" inside the
                // bridge, while neutral-context generation and both standalone
                // keyed calls succeed. Retry once with the neutral context and
                // LOG it — never silently.
                eprintln!(
                    "[generative-worker] keyed context failed ({first_error}); retrying neutral"
                );
                service
                .generate_clip(&action, "Longsword", "Top", None, request.id)
                .map_err(|error| {
                    MotionServiceError::new(format!(
                        "MotionBricks generation failed (keyed: {first_error}; neutral: {error})"
                    ))
                })?
            }
        };
    validate_full_pose_clip(&frames)
        .map_err(|error| MotionServiceError::new(format!("invalid generative clip: {error}")))?;
    let latency = start.elapsed();
    let frame_count = frames.len();
    log::info!(
        "motion_generation_complete request_id={} provider=generative-keyframe-inbetweening latency_us={} frames={}",
        request.id,
        latency.as_micros(),
        frame_count
    );
    Ok(MotionClip {
        request_id: request.id,
        intent: request.intent,
        frames: Arc::from(frames),
        receipt: MotionGenerationReceipt {
            request_id: request.id,
            provider: MotionProviderKind::GenerativeKeyframeInbetweening,
            generation_latency: latency,
            frame_count,
        },
    })
}

/// Read-only M1 lock adapter. It encodes requested displacement in the two root
/// keyframes and passes complete start/end G1 poses to the provider.
#[cfg(feature = "motion-inference")]
pub struct PlanPhaseMotionAdapter {
    requests: [Option<MotionRequestId>; 2],
    last_pose: [FullPose; 2],
    /// F-022 clip streaming: the consumed clip and the truth tick it started,
    /// so rendering advances one generated frame per truth tick.
    active_clip: [Option<(MotionClip, u64)>; 2],
}

#[cfg(feature = "motion-inference")]
impl PlanPhaseMotionAdapter {
    pub fn new(initial_player_pose: FullPose, initial_opponent_pose: FullPose) -> Self {
        Self {
            requests: [None, None],
            last_pose: [initial_player_pose, initial_opponent_pose],
            active_clip: [None, None],
        }
    }

    /// Submit each currently locked M1 intent. Call immediately after both
    /// `submit_intent` calls have emitted `PlanEvent::Locked`; this function only
    /// reads `PlanPhase::snapshot` and cannot mutate truth.
    pub fn submit_locked(
        &mut self,
        phase: &PlanPhase,
        service: &mut MotionPlanService,
    ) -> Result<Vec<MotionSubmitReceipt>, MotionServiceError> {
        let snapshot = phase.snapshot();
        let mut receipts = Vec::new();
        for side in [Side::Player, Side::Opponent] {
            let index = side_index(side);
            if let Some(request) =
                motion_request_from_plan_lock(&snapshot, side, self.last_pose[index])
                && self.requests[index] != Some(request.id)
            {
                if let Some(superseded) = self.requests[index] {
                    service.cancel(superseded);
                }
                let receipt = service.submit(request)?;
                self.requests[index] = Some(receipt.request_id);
                receipts.push(receipt);
            }
        }
        Ok(receipts)
    }

    /// Cancel every in-flight request (dev-lane teardown; avoids abandoning
    /// worker threads at process exit).
    pub fn cancel_all(&mut self, service: &mut MotionPlanService) {
        for request in self.requests.iter_mut() {
            if let Some(id) = request.take() {
                service.cancel(id);
            }
        }
    }

    /// Advance authoritative truth first, then poll the buffered presentation
    /// service. `poll` cannot wait on inference, and a hash check makes the
    /// presentation-only boundary explicit even in debug builds.
    pub fn step_truth_tick(
        &mut self,
        phase: &mut PlanPhase,
        service: &mut MotionPlanService,
    ) -> Result<(Vec<PlanEvent>, MotionPresentationSample), crate::intent::PlanError> {
        let events = phase.step_truth_tick()?;
        let truth_hash_after_tick = phase.truth_hash();
        let sample = self.poll_presentation(service, phase.snapshot().truth_frame);
        debug_assert_eq!(truth_hash_after_tick, phase.truth_hash());
        Ok((events, sample))
    }

    /// F-022 playback: the generated clip's frame for this truth tick
    /// (one frame per tick, clamped at the clip end), or the last pose when
    /// no clip is active (underrun/before the first clip).
    pub fn playback_pose(&self, side: Side, truth_tick: u64) -> FullPose {
        let index = side_index(side);
        if let Some((clip, started)) = &self.active_clip[index] {
            let offset = truth_tick.saturating_sub(*started) as usize;
            return clip.frames[offset.min(clip.frames.len().saturating_sub(1))];
        }
        self.last_pose[index]
    }

    /// Consume ready clips only; pending or rejected requests retain the last
    /// presentation pose. This is the required underrun behavior.
    pub fn poll_presentation(
        &mut self,
        service: &mut MotionPlanService,
        truth_tick: u64,
    ) -> MotionPresentationSample {
        let mut poses = self.last_pose;
        let mut held_last_pose = [true; 2];
        let mut receipts = [None, None];
        let mut rejected = [false; 2];
        for side in [Side::Player, Side::Opponent] {
            let index = side_index(side);
            let Some(request_id) = self.requests[index] else {
                continue;
            };
            match service.poll(request_id) {
                MotionPoll::Ready(clip) => {
                    // F-022 streaming: keep the whole clip; playback advances
                    // one generated frame per truth tick from this sample.
                    if let Some(first) = clip.frames.first() {
                        poses[index] = *first;
                        self.last_pose[index] = *first;
                        held_last_pose[index] = false;
                    }
                    receipts[index] = Some(clip.receipt);
                    self.active_clip[index] = Some((clip, truth_tick));
                    self.requests[index] = None;
                }
                MotionPoll::Rejected(_) => {
                    // Surface the rejection (bridge/generation failure class)
                    // and clear the request so the next lock can retry.
                    rejected[index] = true;
                    self.requests[index] = None;
                }
                MotionPoll::Pending => {}
            }
        }
        MotionPresentationSample {
            poses,
            held_last_pose,
            receipts,
            rejected,
        }
    }
}

#[derive(Debug, Clone)]
pub struct MotionPresentationSample {
    pub poses: [FullPose; 2],
    pub held_last_pose: [bool; 2],
    pub receipts: [Option<MotionGenerationReceipt>; 2],
    /// A poll consumed a provider rejection this sample (F-021 observability).
    pub rejected: [bool; 2],
}

/// Read-only M1 lock adapter. It encodes requested displacement in the two root
/// keyframes and passes complete start/end G1 poses to the provider.
pub fn motion_request_from_plan_lock(
    snapshot: &PlanSnapshot,
    side: Side,
    current_pose: FullPose,
) -> Option<MotionPlanRequest> {
    let intent = snapshot.locked[side_index(side)]?;
    let displacement_mm = intent_displacement(intent);
    let root = snapshot.roots[side_index(side)];
    let start_root = root_transform(root);
    let start_pose = align_pose_root(current_pose, root);
    let end_root = root_transform(RootPosition::new(
        root.x_mm.saturating_add(displacement_mm[0]),
        root.y_mm.saturating_add(displacement_mm[1]),
        root.z_mm.saturating_add(displacement_mm[2]),
    ));
    let end_pose = translate_pose(
        start_pose,
        Vec3::new(
            displacement_mm[0] as f32 / 1000.0,
            displacement_mm[1] as f32 / 1000.0,
            displacement_mm[2] as f32 / 1000.0,
        ),
    );
    Some(MotionPlanRequest {
        id: stable_request_id(
            snapshot,
            side,
            CoreMotionIntent::from_intent(intent),
            displacement_mm,
        ),
        side,
        intent: CoreMotionIntent::from_intent(intent),
        displacement_mm,
        keyframes: SupportedKeyframes {
            start_root,
            end_root,
            start_pose: current_pose,
            end_pose,
        },
    })
}

fn root_transform(root: RootPosition) -> Mat4 {
    Mat4::from_translation(Vec3::new(
        root.x_mm as f32 / 1000.0,
        root.y_mm as f32 / 1000.0,
        root.z_mm as f32 / 1000.0,
    ))
}

fn align_pose_root(pose: FullPose, root: RootPosition) -> FullPose {
    let desired = Vec3::new(
        root.x_mm as f32 / 1000.0,
        root.y_mm as f32 / 1000.0,
        root.z_mm as f32 / 1000.0,
    );
    translate_pose(pose, desired - pose[0].w_axis.truncate())
}

fn translate_pose(mut pose: FullPose, displacement: Vec3) -> FullPose {
    for joint in &mut pose {
        joint.w_axis += displacement.extend(0.0);
    }
    pose
}

const fn intent_displacement(intent: Intent) -> [i32; 3] {
    match intent {
        Intent::Move {
            dir, distance_mm, ..
        } => direction_displacement(dir, distance_mm as i32),
        Intent::Dodge { dir } => direction_displacement(dir, 300),
        _ => [0, 0, 0],
    }
}

const fn direction_displacement(direction: MoveDirection, distance_mm: i32) -> [i32; 3] {
    match direction {
        MoveDirection::Approach => [0, 0, -distance_mm],
        MoveDirection::Retreat => [0, 0, distance_mm],
        MoveDirection::LateralLeft | MoveDirection::CircleCounterClockwise => [-distance_mm, 0, 0],
        MoveDirection::LateralRight | MoveDirection::CircleClockwise => [distance_mm, 0, 0],
    }
}

fn stable_request_id(
    snapshot: &PlanSnapshot,
    side: Side,
    intent: CoreMotionIntent,
    displacement_mm: [i32; 3],
) -> MotionRequestId {
    const OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
    const PRIME: u64 = 0x0000_0100_0000_01b3;
    let side = match side {
        Side::Player => 0,
        Side::Opponent => 1,
    };
    let intent = match intent {
        CoreMotionIntent::Strike => 0,
        CoreMotionIntent::Block => 1,
        CoreMotionIntent::Grab => 2,
        CoreMotionIntent::Move => 3,
        CoreMotionIntent::Dodge => 4,
        CoreMotionIntent::Idle => 5,
    };
    [
        snapshot.truth_frame as i64,
        side,
        intent,
        snapshot.roots[side as usize].x_mm as i64,
        snapshot.roots[side as usize].y_mm as i64,
        snapshot.roots[side as usize].z_mm as i64,
        displacement_mm[0] as i64,
        displacement_mm[1] as i64,
        displacement_mm[2] as i64,
    ]
    .into_iter()
    .fold(OFFSET, |hash, field| {
        (hash ^ field as u64).wrapping_mul(PRIME)
    })
}

const fn side_index(side: Side) -> usize {
    match side {
        Side::Player => 0,
        Side::Opponent => 1,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::intent::{PlanStatus, StrikeVariant};

    fn identity_pose() -> FullPose {
        [Mat4::IDENTITY; G1_NB]
    }

    fn request(id: MotionRequestId, intent: Intent) -> MotionPlanRequest {
        let keyframes = SupportedKeyframes {
            start_root: Mat4::IDENTITY,
            end_root: Mat4::IDENTITY,
            start_pose: identity_pose(),
            end_pose: identity_pose(),
        };
        MotionPlanRequest {
            id,
            side: Side::Player,
            intent: CoreMotionIntent::from_intent(intent),
            displacement_mm: [0, 0, 0],
            keyframes,
        }
    }

    #[test]
    fn baked_provider_returns_a_deterministic_validated_clip_for_each_core_intent() {
        let mut provider = BakedClipProvider::embedded().unwrap();
        for (index, intent) in [
            CoreMotionIntent::Strike,
            CoreMotionIntent::Block,
            CoreMotionIntent::Grab,
            CoreMotionIntent::Move,
            CoreMotionIntent::Dodge,
            CoreMotionIntent::Idle,
        ]
        .into_iter()
        .enumerate()
        {
            let request = request(
                index as u64 + 1,
                match intent {
                    CoreMotionIntent::Strike => Intent::Strike {
                        variant: StrikeVariant::Slash,
                    },
                    CoreMotionIntent::Block => Intent::Block,
                    CoreMotionIntent::Grab => Intent::Grab,
                    CoreMotionIntent::Move => Intent::move_standard(MoveDirection::Approach),
                    CoreMotionIntent::Dodge => Intent::Dodge {
                        dir: MoveDirection::LateralLeft,
                    },
                    CoreMotionIntent::Idle => Intent::Idle,
                },
            );
            provider.submit(request).unwrap();
            let MotionPoll::Ready(first) = provider.poll(index as u64 + 1) else {
                panic!("{intent:?} baked clip was not ready");
            };
            assert_eq!(first.intent, intent);
            assert!(first.frames.len() >= 2);
            assert_eq!(first.receipt.generation_latency, Duration::ZERO);
            assert!(
                first
                    .frames
                    .iter()
                    .flat_map(|frame| frame.iter())
                    .all(Mat4::is_finite)
            );
        }
    }

    struct PendingProvider;

    /// Stub that returns a fixed 4-frame clip immediately (deterministic
    /// streaming proof without the Python bridge).
    struct FixedClipProvider;

    impl AsyncMotionPlanProvider for FixedClipProvider {
        fn submit(
            &mut self,
            request: MotionPlanRequest,
        ) -> Result<MotionSubmitReceipt, MotionServiceError> {
            Ok(MotionSubmitReceipt {
                request_id: request.id,
                provider: MotionProviderKind::GenerativeKeyframeInbetweening,
            })
        }

        fn cancel(&mut self, _request_id: MotionRequestId) {}

        fn poll(&mut self, request_id: MotionRequestId) -> MotionPoll {
            let frames: Vec<FullPose> = (0..4)
                .map(|i| {
                    let mut pose = [Mat4::IDENTITY; G1_NB];
                    pose[0] = Mat4::from_translation(glam::Vec3::new(i as f32, 0.0, 0.0));
                    pose
                })
                .collect();
            MotionPoll::Ready(MotionClip {
                request_id,
                intent: CoreMotionIntent::Idle,
                frames: frames.into(),
                receipt: MotionGenerationReceipt {
                    request_id,
                    provider: MotionProviderKind::GenerativeKeyframeInbetweening,
                    generation_latency: Duration::from_millis(1),
                    frame_count: 4,
                },
            })
        }
    }

    #[test]
    fn playback_streams_one_generated_frame_per_truth_tick_and_clamps() {
        // F-022: after a clip is consumed at tick T, playback advances
        // frame-per-tick and clamps at the clip end; underrun holds last pose.
        let mut phase = PlanPhase::new();
        let mut service = MotionPlanService::new(FixedClipProvider);
        let mut adapter = PlanPhaseMotionAdapter::new(identity_pose(), identity_pose());
        phase
            .submit_intent(Side::Player, Intent::Idle)
            .expect("idle submits");
        phase
            .submit_intent(Side::Opponent, Intent::Idle)
            .expect("idle submits");
        let receipts = adapter.submit_locked(&phase, &mut service).unwrap();
        assert_eq!(receipts.len(), 2);
        let consumed_tick = phase.snapshot().truth_frame;
        let sample = adapter.poll_presentation(&mut service, consumed_tick);
        assert!(sample.receipts[0].is_some(), "clip must be consumed");
        let x = |side: Side, t: u64| adapter.playback_pose(side, t)[0].w_axis.x;
        for (offset, expected) in [(0, 0.0), (1, 1.0), (2, 2.0), (3, 3.0), (9, 3.0)] {
            assert_eq!(
                x(Side::Player, consumed_tick + offset),
                expected,
                "tick offset {offset} must play frame {expected} (clamped)"
            );
        }
    }

    impl AsyncMotionPlanProvider for PendingProvider {
        fn submit(
            &mut self,
            request: MotionPlanRequest,
        ) -> Result<MotionSubmitReceipt, MotionServiceError> {
            Ok(MotionSubmitReceipt {
                request_id: request.id,
                provider: MotionProviderKind::GenerativeKeyframeInbetweening,
            })
        }

        fn cancel(&mut self, _request_id: MotionRequestId) {}

        fn poll(&mut self, _request_id: MotionRequestId) -> MotionPoll {
            MotionPoll::Pending
        }
    }

    #[test]
    fn truth_tick_advances_while_generation_is_pending_and_hash_ignores_motion() {
        let mut with_motion = PlanPhase::new();
        let mut truth_only = PlanPhase::new();
        for phase in [&mut with_motion, &mut truth_only] {
            phase
                .submit_intent(
                    Side::Player,
                    Intent::Strike {
                        variant: StrikeVariant::Slash,
                    },
                )
                .unwrap();
            phase.submit_intent(Side::Opponent, Intent::Block).unwrap();
            assert!(matches!(phase.status(), PlanStatus::Executing { .. }));
        }
        assert_eq!(with_motion.truth_hash(), truth_only.truth_hash());

        let mut adapter = PlanPhaseMotionAdapter::new(identity_pose(), identity_pose());
        let mut service = MotionPlanService::new(PendingProvider);
        assert_eq!(
            adapter
                .submit_locked(&with_motion, &mut service)
                .unwrap()
                .len(),
            2
        );
        let before_truth_frame = with_motion.snapshot().truth_frame;
        let (_events, sample) = adapter
            .step_truth_tick(&mut with_motion, &mut service)
            .unwrap();
        truth_only.step_truth_tick().unwrap();

        assert_eq!(with_motion.snapshot().truth_frame, before_truth_frame + 1);
        assert_eq!(with_motion.truth_hash(), truth_only.truth_hash());
        assert_eq!(sample.held_last_pose, [true, true]);
    }

    #[test]
    fn lock_request_carries_displacement_and_full_pose_keyframes() {
        let mut phase = PlanPhase::new();
        phase
            .submit_intent(
                Side::Player,
                Intent::Move {
                    dir: MoveDirection::LateralRight,
                    distance_mm: 600,
                    auto_correct: true,
                },
            )
            .unwrap();
        phase.submit_intent(Side::Opponent, Intent::Idle).unwrap();
        let request =
            motion_request_from_plan_lock(&phase.snapshot(), Side::Player, identity_pose())
                .expect("locked player request");
        assert_eq!(request.intent, CoreMotionIntent::Move);
        assert_eq!(request.displacement_mm, [600, 0, 0]);
        assert_eq!(request.keyframes.end_pose[0].w_axis.x, 0.6);
    }
}
