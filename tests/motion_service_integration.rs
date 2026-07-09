use just_dodge::motion::{Action, ActionCondition, Stance};
use just_dodge::motion_service::MotionService;

#[test]
fn strike_generates_finite_frames() {
    let svc = MotionService::new().expect("Python service must initialize");
    let condition = ActionCondition {
        action: Action::Strike,
        stance: Stance::Top,
        from_pose: None,
    };
    let clip = just_dodge::motion::generate_action_clip(&condition, &svc)
        .expect("service should return a clip");
    assert!(!clip.is_empty(), "clip must contain frames");
    for (fi, frame) in clip.iter().enumerate() {
        for (ji, m) in frame.iter().enumerate() {
            assert!(m.is_finite(), "non-finite matrix at frame {fi} joint {ji}");
        }
    }
}

#[test]
fn strike_is_deterministic() {
    let svc = MotionService::new().expect("Python service must initialize");
    let condition = ActionCondition {
        action: Action::Strike,
        stance: Stance::Top,
        from_pose: None,
    };
    let a = just_dodge::motion::generate_action_clip(&condition, &svc).unwrap();
    let b = just_dodge::motion::generate_action_clip(&condition, &svc).unwrap();
    assert_eq!(a.len(), b.len());
    assert_eq!(a, b, "same seed must produce identical frames");
}
