use glam::Mat4;
use just_dodge::intent::{Intent, MoveDirection, PlanPhase, PlanStatus, StrikeVariant};
use just_dodge::motion::G1_NB;
use just_dodge::motion_service_async::{
    AsyncMotionPlanProvider, CoreMotionIntent, FullPose, MotionPlanRequest, MotionPlanService,
    MotionPoll, MotionProviderKind, MotionServiceError, MotionSubmitReceipt,
    PlanPhaseMotionAdapter,
};
use just_dodge::truth::Side;

fn identity_pose() -> FullPose {
    [Mat4::IDENTITY; G1_NB]
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
fn movement_request_maps_to_move_motion_intent() {
    assert_eq!(
        CoreMotionIntent::from_intent(Intent::move_standard(MoveDirection::Approach)),
        CoreMotionIntent::Move
    );
}
