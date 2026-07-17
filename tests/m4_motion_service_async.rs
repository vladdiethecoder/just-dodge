use glam::Mat4;
use just_dodge::intent::{Intent, MoveDirection, PlanPhase, PlanStatus, StrikeVariant};
use just_dodge::motion::G1_NB;
use just_dodge::motion_service_async::{
    AsyncMotionPlanProvider, BakedClipProvider, CoreMotionIntent, FullPose, MotionPlanRequest,
    MotionPlanService, MotionPoll, MotionProviderKind, MotionServiceError, MotionSubmitReceipt,
    PlanPhaseMotionAdapter, SupportedKeyframes,
};
use just_dodge::truth::Side;

fn identity_pose() -> FullPose {
    [Mat4::IDENTITY; G1_NB]
}

fn request(id: u64, intent: CoreMotionIntent) -> MotionPlanRequest {
    MotionPlanRequest {
        id,
        side: Side::Player,
        intent,
        displacement_mm: [0, 0, 0],
        keyframes: SupportedKeyframes {
            start_root: Mat4::IDENTITY,
            end_root: Mat4::IDENTITY,
            start_pose: identity_pose(),
            end_pose: identity_pose(),
        },
    }
}

#[test]
fn baked_provider_serves_each_core_intent_deterministically() {
    let intents = [
        CoreMotionIntent::Strike,
        CoreMotionIntent::Block,
        CoreMotionIntent::Grab,
        CoreMotionIntent::Move,
        CoreMotionIntent::Dodge,
        CoreMotionIntent::Idle,
    ];
    let mut first_provider = BakedClipProvider::embedded().unwrap();
    let mut second_provider = BakedClipProvider::embedded().unwrap();

    for (index, intent) in intents.into_iter().enumerate() {
        let id = index as u64 + 1;
        first_provider.submit(request(id, intent)).unwrap();
        second_provider.submit(request(id, intent)).unwrap();
        let MotionPoll::Ready(first) = first_provider.poll(id) else {
            panic!("first {intent:?} baked clip was not ready")
        };
        let MotionPoll::Ready(second) = second_provider.poll(id) else {
            panic!("second {intent:?} baked clip was not ready")
        };
        assert_eq!(first.intent, intent);
        assert_eq!(first.frames.as_ref(), second.frames.as_ref());
        assert!(first.frames.len() >= 2);
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

    fn cancel(&mut self, _request_id: u64) {}

    fn poll(&mut self, _request_id: u64) -> MotionPoll {
        MotionPoll::Pending
    }
}

#[test]
fn pending_generation_never_gates_m1_truth_tick_or_truth_hash() {
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
    let frame_before = with_motion.snapshot().truth_frame;
    let (_events, presentation) = adapter
        .step_truth_tick(&mut with_motion, &mut service)
        .unwrap();
    truth_only.step_truth_tick().unwrap();

    assert_eq!(with_motion.snapshot().truth_frame, frame_before + 1);
    assert_eq!(with_motion.truth_hash(), truth_only.truth_hash());
    assert_eq!(presentation.held_last_pose, [true, true]);
}

#[test]
fn movement_request_is_core_baked_family() {
    assert_eq!(
        CoreMotionIntent::from_intent(Intent::move_standard(MoveDirection::Approach)),
        CoreMotionIntent::Move
    );
}
