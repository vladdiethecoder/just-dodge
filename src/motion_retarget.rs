//! Validated G1 → 24-bone armored-duelist pose conversion.
//!
//! The prior generic `retarget::g1_to_skin` path targets a historical rich
//! skeleton and is not the C0 runtime boundary. This module maps source-frame
//! rotation deltas onto the actual SKM1 hierarchy, whose root is named `Hips`.

use crate::asset::{self, SkinnedMeshData};
use glam::Mat4;

/// Convert one G1 source frame into the armored-duelist's skinning matrices.
/// `source_reference` must be the first frame of the same immutable source
/// clip; it defines the zero-delta bind alignment for that action.
pub fn retarget_g1_frame_to_armored_skin(
    mesh: &SkinnedMeshData,
    source_reference: &[Mat4; 34],
    source_frame: &[Mat4; 34],
) -> std::io::Result<Vec<Mat4>> {
    let target_reference: Vec<Mat4> = mesh.bones.iter().map(|bone| bone.rest_local).collect();
    let skin = asset::calibrated_g1_skin_matrices(
        source_frame,
        source_reference,
        mesh,
        &target_reference,
    )?;
    validate_armored_skin(mesh, &skin)?;
    Ok(skin)
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
        let reference = [Mat4::IDENTITY; 34];
        let mut changed = reference;
        changed[21] = Mat4::from_rotation_x(0.3);
        let first = retarget_g1_frame_to_armored_skin(&mesh, &reference, &changed).unwrap();
        let second = retarget_g1_frame_to_armored_skin(&mesh, &reference, &changed).unwrap();
        assert_eq!(first, second);
        assert_eq!(armored_pose_receipt(&first), armored_pose_receipt(&second));
        assert_eq!(first.len(), 24);
        assert!(first.iter().all(Mat4::is_finite));
        assert!(first.iter().all(|matrix| matrix.determinant() > 0.0));
    }
}
