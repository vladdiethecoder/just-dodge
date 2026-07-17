//! Validated G1 → 24-bone armored-duelist pose conversion.
//!
//! The prior generic `retarget::g1_to_skin` path targets a historical rich
//! skeleton and is not the C0 runtime boundary. This module maps source-frame
//! rotation deltas onto the actual SKM1 hierarchy, whose root is named `Hips`.

use crate::asset::{self, SkinnedMeshData};
use glam::{Mat4, Quat, Vec3};

/// Convert one G1 source frame into the armored-duelist's skinning matrices.
/// `source_reference` must be the first frame of the same immutable source
/// clip; it defines the zero-delta bind alignment for that action.
pub fn retarget_g1_frame_to_armored_skin(
    mesh: &SkinnedMeshData,
    source_reference: &[Mat4; 34],
    source_frame: &[Mat4; 34],
) -> std::io::Result<Vec<Mat4>> {
    retarget_g1_frame_to_armored_skin_internal(mesh, source_reference, source_frame, None)
}

pub fn retarget_g1_frame_to_armored_skin_with_foot_targets(
    mesh: &SkinnedMeshData,
    source_reference: &[Mat4; 34],
    source_frame: &[Mat4; 34],
    foot_targets: [Vec3; 2],
) -> std::io::Result<Vec<Mat4>> {
    retarget_g1_frame_to_armored_skin_internal(
        mesh,
        source_reference,
        source_frame,
        Some(foot_targets),
    )
}

fn retarget_g1_frame_to_armored_skin_internal(
    mesh: &SkinnedMeshData,
    source_reference: &[Mat4; 34],
    source_frame: &[Mat4; 34],
    foot_targets: Option<[Vec3; 2]>,
) -> std::io::Result<Vec<Mat4>> {
    let target_reference: Vec<Mat4> = mesh.bones.iter().map(|bone| bone.rest_local).collect();
    let mut target_local = asset::calibrated_g1_target_locals(
        source_frame,
        source_reference,
        mesh,
        &target_reference,
    )?;
    retarget_arm_segment_directions(
        mesh,
        &target_reference,
        &mut target_local,
        source_reference,
        source_frame,
    )?;
    close_two_hand_grip(mesh, &mut target_local, 0.160)?;
    if let Some(targets) = foot_targets {
        close_planted_feet(mesh, &mut target_local, targets)?;
    }
    align_head_forward_with_torso(mesh, &mut target_local)?;
    let skin = asset::reference_pose_skin_matrices(mesh, &target_local)?;
    validate_armored_skin(mesh, &skin)?;
    Ok(skin)
}

fn align_head_forward_with_torso(
    mesh: &SkinnedMeshData,
    target_local: &mut [Mat4],
) -> std::io::Result<()> {
    let head = bone_index(mesh, "Head")?;
    let head_front = bone_index(mesh, "headfront")?;
    let torso = bone_index(mesh, "Spine02")?;
    let world = hierarchy_world(mesh, target_local);
    let torso_forward = world[torso].z_axis.truncate().normalize_or_zero();
    let head_forward =
        (translation(world[head_front]) - translation(world[head])).normalize_or_zero();
    if torso_forward.length_squared() <= 1.0e-8 || head_forward.length_squared() <= 1.0e-8 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "head-forward calibration requires non-degenerate torso and head axes",
        ));
    }
    if head_forward.dot(torso_forward) >= 0.70 {
        return Ok(());
    }

    let correction = Quat::from_rotation_arc(head_forward, torso_forward);
    let (_, head_world_rotation, _) = world[head].to_scale_rotation_translation();
    let parent = mesh.bones[head].parent;
    if parent < 0 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "Head must have a parent for orientation calibration",
        ));
    }
    let (_, parent_world_rotation, _) = world[parent as usize].to_scale_rotation_translation();
    let (scale, _, local_translation) = target_local[head].to_scale_rotation_translation();
    target_local[head] = Mat4::from_scale_rotation_translation(
        scale,
        (parent_world_rotation.inverse() * correction * head_world_rotation).normalize(),
        local_translation,
    );

    let corrected = hierarchy_world(mesh, target_local);
    let corrected_head_forward =
        (translation(corrected[head_front]) - translation(corrected[head])).normalize_or_zero();
    if corrected_head_forward.dot(torso_forward) < 0.70 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "head-forward calibration did not align Head with Spine02",
        ));
    }
    Ok(())
}

fn close_planted_feet(
    mesh: &SkinnedMeshData,
    target_local: &mut [Mat4],
    targets: [Vec3; 2],
) -> std::io::Result<()> {
    let feet = ["LeftFoot", "RightFoot"];
    let chains = [["LeftLeg", "LeftUpLeg"], ["RightLeg", "RightUpLeg"]];
    for _ in 0..96 {
        for ((foot_name, target), chain) in feet.into_iter().zip(targets).zip(chains) {
            let foot = bone_index(mesh, foot_name)?;
            for joint_name in chain {
                rotate_joint_toward(
                    mesh,
                    target_local,
                    bone_index(mesh, joint_name)?,
                    foot,
                    target,
                )?;
            }
        }
    }
    let final_world = hierarchy_world(mesh, target_local);
    for (foot_name, target) in feet.into_iter().zip(targets) {
        let error = translation(final_world[bone_index(mesh, foot_name)?]).distance(target);
        if error >= 0.010 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("planted {foot_name} residual {error:.6}m exceeds 0.010m"),
            ));
        }
    }
    Ok(())
}

fn close_two_hand_grip(
    mesh: &SkinnedMeshData,
    target_local: &mut [Mat4],
    grip_span_m: f32,
) -> std::io::Result<()> {
    let left_hand = bone_index(mesh, "LeftHand")?;
    let right_hand = bone_index(mesh, "RightHand")?;
    let initial_world = hierarchy_world(mesh, target_local);
    let left = translation(initial_world[left_hand]);
    let right = translation(initial_world[right_hand]);
    let span = right - left;
    if span.length_squared() < 1.0e-8 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "closed grip requires distinct C0 hand positions",
        ));
    }
    let midpoint = (left + right) * 0.5;
    let direction = span.normalize();
    let targets = [
        ("LeftHand", midpoint - direction * (grip_span_m * 0.5)),
        ("RightHand", midpoint + direction * (grip_span_m * 0.5)),
    ];
    let chains = [
        ["LeftForeArm", "LeftArm", "LeftShoulder"],
        ["RightForeArm", "RightArm", "RightShoulder"],
    ];

    for _ in 0..64 {
        for ((hand_name, target), chain) in targets.iter().zip(chains) {
            let hand = bone_index(mesh, hand_name)?;
            for joint_name in chain {
                let joint = bone_index(mesh, joint_name)?;
                rotate_joint_toward(mesh, target_local, joint, hand, *target)?;
            }
        }
    }

    let final_world = hierarchy_world(mesh, target_local);
    for (hand_name, target) in targets {
        let hand = bone_index(mesh, hand_name)?;
        let error = translation(final_world[hand]).distance(target);
        if error > 0.012 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("closed grip {hand_name} residual {error:.6}m exceeds 0.012m"),
            ));
        }
    }
    Ok(())
}

fn rotate_joint_toward(
    mesh: &SkinnedMeshData,
    local: &mut [Mat4],
    joint: usize,
    hand: usize,
    target: Vec3,
) -> std::io::Result<()> {
    let world = hierarchy_world(mesh, local);
    let joint_position = translation(world[joint]);
    let to_hand = translation(world[hand]) - joint_position;
    let to_target = target - joint_position;
    if to_hand.length_squared() < 1.0e-8 || to_target.length_squared() < 1.0e-8 {
        return Ok(());
    }
    let correction = Quat::from_rotation_arc(to_hand.normalize(), to_target.normalize());
    let damped = Quat::IDENTITY.slerp(correction, 0.90).normalize();
    let (_, joint_world_rotation, _) = world[joint].to_scale_rotation_translation();
    let desired_world_rotation = damped * joint_world_rotation;
    let parent_world_rotation = if mesh.bones[joint].parent < 0 {
        Quat::IDENTITY
    } else {
        world[mesh.bones[joint].parent as usize]
            .to_scale_rotation_translation()
            .1
    };
    let (scale, _, local_translation) = local[joint].to_scale_rotation_translation();
    local[joint] = Mat4::from_scale_rotation_translation(
        scale,
        (parent_world_rotation.inverse() * desired_world_rotation).normalize(),
        local_translation,
    );
    Ok(())
}

fn hierarchy_world(mesh: &SkinnedMeshData, local: &[Mat4]) -> Vec<Mat4> {
    let mut world = vec![Mat4::IDENTITY; local.len()];
    for (index, bone) in mesh.bones.iter().enumerate() {
        world[index] = if bone.parent < 0 {
            local[index]
        } else {
            world[bone.parent as usize] * local[index]
        };
    }
    world
}

fn bone_index(mesh: &SkinnedMeshData, name: &str) -> std::io::Result<usize> {
    mesh.bones
        .iter()
        .position(|bone| bone.name == name)
        .ok_or_else(|| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("arm direction retarget requires {name} bone"),
            )
        })
}

fn translation(matrix: Mat4) -> Vec3 {
    matrix.to_scale_rotation_translation().2
}

fn retarget_arm_segment_directions(
    mesh: &SkinnedMeshData,
    target_reference_local: &[Mat4],
    target_local: &mut [Mat4],
    _source_reference: &[Mat4; 34],
    source_frame: &[Mat4; 34],
) -> std::io::Result<()> {
    let reference_world = hierarchy_world(mesh, target_reference_local);
    let segments = [
        ("LeftArm", "LeftForeArm", 20usize, 21usize),
        ("LeftForeArm", "LeftHand", 21usize, 25usize),
        ("RightArm", "RightForeArm", 28usize, 29usize),
        ("RightForeArm", "RightHand", 29usize, 33usize),
    ];

    for (target_bone_name, target_child_name, source_parent, source_child) in segments {
        let target_bone = bone_index(mesh, target_bone_name)?;
        let target_child = bone_index(mesh, target_child_name)?;
        let source_direction =
            translation(source_frame[source_child]) - translation(source_frame[source_parent]);
        let target_reference_direction =
            translation(reference_world[target_child]) - translation(reference_world[target_bone]);
        if source_direction.length_squared() < 1.0e-8
            || target_reference_direction.length_squared() < 1.0e-8
        {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("zero-length segment while retargeting {target_bone_name}"),
            ));
        }

        let target_reference_direction = target_reference_direction.normalize();
        let desired_direction = source_direction.normalize();
        let (_, target_reference_rotation, _) =
            reference_world[target_bone].to_scale_rotation_translation();
        let desired_world_rotation =
            Quat::from_rotation_arc(target_reference_direction, desired_direction)
                * target_reference_rotation;
        let target_world = hierarchy_world(mesh, target_local);
        let parent_world_rotation = if mesh.bones[target_bone].parent < 0 {
            Quat::IDENTITY
        } else {
            target_world[mesh.bones[target_bone].parent as usize]
                .to_scale_rotation_translation()
                .1
        };
        let (scale, _, local_translation) =
            target_reference_local[target_bone].to_scale_rotation_translation();
        target_local[target_bone] = Mat4::from_scale_rotation_translation(
            scale,
            (parent_world_rotation.conjugate() * desired_world_rotation).normalize(),
            local_translation,
        );
    }
    Ok(())
}

/// Deterministic receipt for presentation verification. It is deliberately not
/// a truth hash and is never supplied to M3 combat resolution.
pub fn armored_pose_receipt(skin: &[Mat4]) -> u64 {
    const FNV_OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
    const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;
    skin.iter()
        .flat_map(Mat4::to_cols_array)
        .map(|value| u64::from(value.to_bits()))
        .fold(FNV_OFFSET, |hash, bits| {
            (hash ^ bits).wrapping_mul(FNV_PRIME)
        })
}

fn validate_armored_skin(mesh: &SkinnedMeshData, skin: &[Mat4]) -> std::io::Result<()> {
    if mesh.bones.len() != 24 || skin.len() != mesh.bones.len() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            format!(
                "armored retarget requires 24 mesh bones and 24 skin matrices; got {}/{}",
                mesh.bones.len(),
                skin.len()
            ),
        ));
    }
    for required in ["Hips", "LeftHand", "RightHand"] {
        if !mesh.bones.iter().any(|bone| bone.name == required) {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("armored retarget requires {required} bone"),
            ));
        }
    }
    for (index, matrix) in skin.iter().enumerate() {
        let determinant = matrix.determinant();
        if !matrix.is_finite() || determinant <= 0.0 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("armored skin matrix {index} is non-finite or inverted"),
            ));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn source_with_valid_arm_segments() -> [Mat4; 34] {
        let mut source = [Mat4::IDENTITY; 34];
        for (joint, position) in [
            (20, Vec3::new(-0.25, 1.35, 0.0)),
            (21, Vec3::new(-0.55, 1.35, 0.0)),
            (25, Vec3::new(-0.85, 1.35, 0.0)),
            (28, Vec3::new(0.25, 1.35, 0.0)),
            (29, Vec3::new(0.55, 1.35, 0.0)),
            (33, Vec3::new(0.85, 1.35, 0.0)),
        ] {
            source[joint] = Mat4::from_translation(position);
        }
        source
    }

    fn armored_mesh() -> SkinnedMeshData {
        asset::load_skinned(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/assets/source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin"
        ))
        .expect("load armored duelist")
    }

    #[test]
    fn armored_hips_root_accepts_identity_and_delta_g1_frames() {
        let mesh = armored_mesh();
        let reference = source_with_valid_arm_segments();
        let mut changed = reference;
        changed[21] =
            Mat4::from_rotation_translation(Quat::from_rotation_x(0.3), translation(reference[21]));
        let first = retarget_g1_frame_to_armored_skin(&mesh, &reference, &changed).unwrap();
        let second = retarget_g1_frame_to_armored_skin(&mesh, &reference, &changed).unwrap();
        assert_eq!(first, second);
        assert_eq!(armored_pose_receipt(&first), armored_pose_receipt(&second));
        assert_eq!(first.len(), 24);
        assert!(first.iter().all(Mat4::is_finite));
        assert!(first.iter().all(|matrix| matrix.determinant() > 0.0));
    }

    #[test]
    fn source_arm_directions_place_armored_hands_overhead() {
        let mesh = armored_mesh();
        let reference = source_with_valid_arm_segments();
        let mut overhead = reference;
        for (joint, position) in [
            (21, Vec3::new(-0.25, 1.7, 0.0)),
            (25, Vec3::new(-0.15, 2.0, 0.0)),
            (29, Vec3::new(0.25, 1.7, 0.0)),
            (33, Vec3::new(0.15, 2.0, 0.0)),
        ] {
            overhead[joint] = Mat4::from_translation(position);
        }
        let skin = retarget_g1_frame_to_armored_skin(&mesh, &reference, &overhead).unwrap();
        let posed = |name: &str| {
            let index = bone_index(&mesh, name).unwrap();
            translation(skin[index] * mesh.bones[index].inverse_bind.inverse())
        };
        assert!(posed("LeftHand").y > posed("LeftShoulder").y);
        assert!(posed("RightHand").y > posed("RightShoulder").y);
    }
}
