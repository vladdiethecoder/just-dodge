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
    let skin = asset::reference_pose_skin_matrices(mesh, &target_local)?;
    validate_armored_skin(mesh, &skin)?;
    Ok(skin)
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
