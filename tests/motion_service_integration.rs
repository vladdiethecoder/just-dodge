use just_dodge::motion::{Action, ActionCondition, Stance};
use just_dodge::motion_service::MotionService;
use std::sync::{Mutex, MutexGuard, OnceLock};

fn motionbricks_service_lock() -> MutexGuard<'static, ()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

fn finite_clip(condition: &ActionCondition, svc: &MotionService) -> Vec<[glam::Mat4; 34]> {
    let clip = just_dodge::motion::generate_action_clip(condition, svc)
        .expect("service should return a clip");
    assert!(!clip.is_empty(), "clip must contain frames");
    for (fi, frame) in clip.iter().enumerate() {
        for (ji, m) in frame.iter().enumerate() {
            assert!(m.is_finite(), "non-finite matrix at frame {fi} joint {ji}");
        }
    }
    clip
}

fn strike_generates_finite_frames() {
    let _service_lock = motionbricks_service_lock();
    let svc = MotionService::new().expect("Python service must initialize");
    let condition = ActionCondition {
        action: Action::Strike,
        stance: Stance::Top,
        from_pose: None,
    };
    finite_clip(&condition, &svc);
}

fn strike_is_deterministic() {
    let _service_lock = motionbricks_service_lock();
    let svc = MotionService::new().expect("Python service must initialize");
    let condition = ActionCondition {
        action: Action::Strike,
        stance: Stance::Top,
        from_pose: None,
    };
    let a = finite_clip(&condition, &svc);
    let b = finite_clip(&condition, &svc);
    assert_eq!(a.len(), b.len());
    assert_eq!(a, b, "same seed must produce identical frames");
}

fn all_actions_generate_finite_frames() {
    let _service_lock = motionbricks_service_lock();
    let svc = MotionService::new().expect("Python service must initialize");
    for action in [
        Action::Idle,
        Action::Strike,
        Action::Block,
        Action::Thrust,
        Action::Grab,
        Action::Dodge,
    ] {
        let condition = ActionCondition {
            action,
            stance: Stance::Top,
            from_pose: None,
        };
        finite_clip(&condition, &svc);
    }
}

fn all_actions_are_deterministic() {
    let _service_lock = motionbricks_service_lock();
    let svc = MotionService::new().expect("Python service must initialize");
    for action in [
        Action::Idle,
        Action::Strike,
        Action::Block,
        Action::Thrust,
        Action::Grab,
        Action::Dodge,
    ] {
        let condition = ActionCondition {
            action,
            stance: Stance::Top,
            from_pose: None,
        };
        let a = finite_clip(&condition, &svc);
        let b = finite_clip(&condition, &svc);
        assert_eq!(a.len(), b.len(), "{action:?}: clips must have same length");
        assert_eq!(a, b, "{action:?}: same seed must produce identical frames");
    }
}

fn all_top_primitives_are_present_and_rigid() {
    let _service_lock = motionbricks_service_lock();
    const PARENTS: [i32; 34] = [
        -1, 0, 1, 2, 3, 4, 5, 6, 0, 8, 9, 10, 11, 12, 13, 0, 15, 16, 17, 18, 19, 20, 21, 22, 23,
        24, 17, 26, 27, 28, 29, 30, 31, 32,
    ];
    let svc = MotionService::new().expect("Python service must initialize");

    for action in ["idle", "strike", "block", "thrust", "grab", "dodge"] {
        let clip = svc
            .load_primitive_clip(action, "longsword", "top")
            .unwrap_or_else(|error| {
                panic!("missing verified primitive {action}/longsword/top: {error}")
            });
        assert!(
            clip.len() >= 2,
            "{action} requires at least two source frames"
        );

        let reference_lengths: [f32; 34] = std::array::from_fn(|joint| {
            if PARENTS[joint] < 0 {
                0.0
            } else {
                (clip[0][joint].w_axis.truncate()
                    - clip[0][PARENTS[joint] as usize].w_axis.truncate())
                .length()
            }
        });
        for (frame_index, frame) in clip.iter().enumerate() {
            for joint in 0..34 {
                assert!(
                    frame[joint].is_finite(),
                    "{action} frame {frame_index} joint {joint} is non-finite"
                );
                if PARENTS[joint] >= 0 {
                    let length = (frame[joint].w_axis.truncate()
                        - frame[PARENTS[joint] as usize].w_axis.truncate())
                    .length();
                    assert!(
                        (length - reference_lengths[joint]).abs() < 1e-4,
                        "{action} frame {frame_index} joint {joint} changed segment length"
                    );
                }
            }
        }
    }
}

fn official_navigation_adapter_is_finite_continuous_and_deterministic() {
    let _service_lock = motionbricks_service_lock();
    let svc = MotionService::new().expect("Python service must initialize");
    let first = svc
        .generate_official_navigation_clip(1234)
        .expect("official MotionBricks navigation adapter must generate");
    let second = svc
        .generate_official_navigation_clip(1234)
        .expect("official MotionBricks navigation adapter must be repeatable");
    assert_eq!(first, second, "fixed seed must reproduce exact G1 frames");
    assert!(first.len() >= 8, "official adapter returned too few frames");

    let mut max_joint_step = 0.0f32;
    for pair in first.windows(2) {
        for (previous, current) in pair[0].iter().zip(&pair[1]) {
            assert!(previous.is_finite());
            assert!(current.is_finite());
            max_joint_step = max_joint_step
                .max((current.w_axis.truncate() - previous.w_axis.truncate()).length());
        }
    }
    assert!(
        max_joint_step < 0.2,
        "official adapter discontinuity {max_joint_step:.3} m/frame"
    );
}

/// PyO3 owns one process-wide interpreter and CUDA context. Although each
/// helper guards its service calls, the Rust test harness can schedule their
/// setup/teardown concurrently. Run this suite as one ordered test to make the
/// lifecycle deterministic without adding a serial-test dependency.
#[test]
fn motion_service_contracts_are_serial_and_complete() {
    strike_generates_finite_frames();
    strike_is_deterministic();
    all_actions_generate_finite_frames();
    all_actions_are_deterministic();
    all_top_primitives_are_present_and_rigid();
    official_navigation_adapter_is_finite_continuous_and_deterministic();
}
