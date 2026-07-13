use glam::Mat4;
use just_dodge::{asset, motion_service::MotionService};

const C0_ROOT: &str = "assets/source/meshy/c0_base_fighter/pose_carrier_001/cooked";

#[test]
fn official_motionbricks_trajectory_calibrates_into_c0_163_joint_skinning() {
    let mesh = asset::load_skinned(&format!("{C0_ROOT}/c0_pose_carrier.bin"))
        .expect("accepted C0 carrier must load");
    let reference = asset::load_skeletal_animation(&format!("{C0_ROOT}/c0_reference.anim"))
        .expect("accepted C0 reference pose must load");
    assert_eq!(mesh.bones.len(), 163);
    assert_eq!(reference.bone_count, mesh.bones.len());

    let service = MotionService::new().expect("MotionBricks Python bridge must initialize");
    let source = service
        .generate_official_navigation_clip(1234)
        .expect("official MotionBricks control path must generate");
    let source_reference = source.first().expect("official clip must not be empty");

    let mut changed_frames = 0usize;
    for (frame_index, source_frame) in source.iter().enumerate() {
        let c0_local = asset::calibrated_g1_target_locals(
            source_frame,
            source_reference,
            &mesh,
            &reference.frames[0],
        )
        .unwrap_or_else(|error| panic!("frame {frame_index} C0 local calibration failed: {error}"));
        assert_eq!(c0_local.len(), 163);
        assert!(c0_local.iter().all(Mat4::is_finite));

        let skin = asset::reference_pose_skin_matrices(&mesh, &c0_local)
            .unwrap_or_else(|error| panic!("frame {frame_index} C0 skinning failed: {error}"));
        assert_eq!(skin.len(), 163);
        assert!(skin.iter().all(Mat4::is_finite));
        assert!(skin.iter().all(|matrix| matrix.determinant() > 0.0));
        changed_frames += usize::from(
            skin.iter()
                .any(|matrix| !matrix.abs_diff_eq(Mat4::IDENTITY, 1e-4)),
        );
    }
    assert!(
        changed_frames > 1,
        "official motion must drive more than one C0 frame"
    );
}
