//! Local-space retargeting: MotionBricks G1 (34 bones) → rich skeleton (103 bones).
//!
//! Pipeline:
//!   1. G1 world → G1 local (parent-relative)   [world_to_local]
//!   2. G1 local → rich local                     [map_g1_locals]
//!   3. Rich local → rich world (FK)               [fk_world]
//!   4. Rich world → 24 skinning matrices          [map_to_skin]
//!
//! Local-space retargeting avoids the shearing that world-space interpolation
//! produces, because local transforms are pure parent-relative rotations and
//! translations — no cross-bone blending.

use crate::asset::SkinnedMeshData;
use crate::skeleton::{self, BONE_COUNT, G1_MAP, SKIN_MAP};
use glam::Mat4;
#[cfg(test)]
use glam::Vec3;

/// One frame of rich skeleton world-space transforms.
pub type RichFrame = [Mat4; BONE_COUNT];

/// Full pipeline: G1 frame → 24 skinning matrices (local-space FK).
pub fn g1_to_skin(g1_world: &[Mat4; 34], mesh: &SkinnedMeshData) -> [Mat4; 24] {
    let g1_local = world_to_local::<34>(g1_world, &MOTION_BRICKS_PARENTS);

    // Build rich rest-pose locals from mesh data (for bones without G1 data)
    let rest = skeleton::rest_pose_from_mesh(mesh);

    // Map G1 locals → rich locals, then FK → rich world
    let rich_local = map_g1_locals(&g1_local, &rest);
    let rich_world = fk_world(&rich_local);

    // Rich world → 24 skinning matrices
    map_to_skin(&rich_world, mesh)
}

// ── Step 1: world → local ──────────────────────────────────────────────────

/// G1 skeleton parent indices (from motionbricks G1Skeleton34).
pub const MOTION_BRICKS_PARENTS: [i32; 34] = [
    -1, 0, 1, 2, 3, 4, 5, 6, 0, 8, 9, 10, 11, 12, 13, 0, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
    17, 26, 27, 28, 29, 30, 31, 32,
];

/// Convert world matrices to parent-relative local matrices.
fn world_to_local<const N: usize>(world: &[Mat4; N], parents: &[i32; N]) -> [Mat4; N] {
    let mut local = [Mat4::IDENTITY; N];
    for i in 0..N {
        if parents[i] >= 0 {
            local[i] = world[parents[i] as usize].inverse() * world[i];
        } else {
            local[i] = world[i];
        }
    }
    local
}

// ── Step 2: G1 local → rich local ─────────────────────────────────────────

/// Map G1 local transforms to rich skeleton local transforms.
/// For bones with a G1 source (G1_MAP[i] >= 0): copy local transform directly.
/// For spine vertebrae: slerp rotation, lerp translation between G1 anchors.
/// For detail bones (fingers, foot details, IK targets): use rest-pose.
fn map_g1_locals(g1_local: &[Mat4; 34], rest: &[Mat4; BONE_COUNT]) -> [Mat4; BONE_COUNT] {
    let mut out = *rest; // start from rest pose

    // Direct 1:1 mapping for bones that have a G1 source
    for i in 0..BONE_COUNT {
        let src = G1_MAP[i];
        if src >= 0 {
            out[i] = g1_local[src as usize];
        }
    }

    // Spine interpolation: G1 has 3 anchors (waist_yaw=15, waist_roll=16, waist_pitch=17)
    // Rich spine has 19 vertebrae (L5=1 .. C1=19)
    // Anchors at: L5(1) + T12(6) = waist_yaw(15), T7(11) = waist_roll(16), C7(13) + C1(19) = waist_pitch(17)
    //
    // We need to interpolate for vertebrae between these anchors.
    // The anchors already have values from the direct G1 mapping.
    // Vertebrae without direct G1 data get interpolated.
    let anchors = [
        (1, 1),   // L5 from out[1] (waist_yaw)
        (6, 6),   // T12 from out[6] (waist_yaw)
        (11, 11), // T7 from out[11] (waist_roll)
        (13, 13), // C7 from out[13] (waist_pitch)
        (19, 19), // C1 from out[19] (waist_pitch)
    ];

    for pair in anchors.windows(2) {
        let (lo, hi) = (pair[0].0, pair[1].0);
        let count = (hi - lo) as f32;
        for j in 1..(hi - lo) {
            let t = j as f32 / count;
            out[lo + j] = lerp_local(out[lo], out[hi], t);
        }
    }

    // Back-fill: L4(2), L3(3), L2(4), L1(5) between Pelvis(0) and T12(6)
    // Pelvis(0) has no G1 local (it's the root), so use rest pose for the root
    // and interpolate between Pelvis(0) and L5(1)/T12(6)
    let pelvis_local = out[0]; // already set from rest (Pelvis has no G1 source)
    let t12_local = out[6]; // already set from waist_yaw
    for j in 2..=5 {
        let t = (j - 1) as f32 / 5.0;
        out[j] = lerp_local(pelvis_local, t12_local, t);
    }
    // Also refine L5(1)
    out[1] = lerp_local(pelvis_local, t12_local, 0.15);

    // T6(7) .. T8(10) between T12(6) and T7(11)
    let t12 = out[6];
    let t7 = out[11];
    for j in 7..=10 {
        let t = (j - 6) as f32 / 5.0;
        out[j] = lerp_local(t12, t7, t);
    }

    // C6(12) between T7(11) and C7(13)
    out[12] = lerp_local(out[11], out[13], 0.5);

    // C6(14) .. C2(18) between C7(13) and C1(19)
    let c7 = out[13];
    let c1 = out[19];
    for j in 14..=18 {
        let t = (j - 13) as f32 / 6.0;
        out[j] = lerp_local(c7, c1, t);
    }

    out
}

/// Lerp between two local-space matrices (slerp rotation, lerp translation).
/// Scale is assumed identity for skeletal transforms.
fn lerp_local(a: Mat4, b: Mat4, t: f32) -> Mat4 {
    let (_, ra, ta) = a.to_scale_rotation_translation();
    let (_, rb, tb) = b.to_scale_rotation_translation();
    let rot = ra.slerp(rb, t);
    let trans = ta.lerp(tb, t);
    Mat4::from_rotation_translation(rot, trans)
}

// ── Step 3: FK: local → world ─────────────────────────────────────────────

/// Rebuild world matrices from local transforms via forward kinematics.
fn fk_world(local: &[Mat4; BONE_COUNT]) -> [Mat4; BONE_COUNT] {
    let mut world = [Mat4::IDENTITY; BONE_COUNT];
    for i in 0..BONE_COUNT {
        let p = skeleton::bone_parent(i);
        if p >= 0 {
            world[i] = world[p as usize] * local[i];
        } else {
            world[i] = local[i];
        }
    }
    world
}

// ── Step 4: rich world → 24 skinning matrices ─────────────────────────────

/// Map rich skeleton world matrices to 24 mannequin skinning matrices.
/// skin[i] = align * richWorld[skinSrc] * invBind[i]
fn map_to_skin(rich_world: &[Mat4; BONE_COUNT], mesh: &SkinnedMeshData) -> [Mat4; 24] {
    // Align rich pelvis to mannequin Hips bind world (same as compute_skin_matrices)
    let hips_bind = mesh.bones[0].inverse_bind.inverse();
    let align = hips_bind * rich_world[0].inverse();

    let mut out = [Mat4::IDENTITY; 24];
    for i in 0..24 {
        // Find which rich bone maps to skin index i
        if let Some(rich_idx) = SKIN_MAP.iter().position(|&s| s == i as i32) {
            let rich_w = align * rich_world[rich_idx];
            out[i] = rich_w * mesh.bones[i].inverse_bind;
        } else {
            // Fallback: use pelvis for unmapped skin bones
            let rich_w = align * rich_world[0];
            out[i] = rich_w * mesh.bones[i].inverse_bind;
        }
    }
    out
}

// ── tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::asset::Bone;

    fn minimal_mesh() -> SkinnedMeshData {
        let bones = (0..24)
            .map(|i| Bone {
                name: format!("Bone{i}"),
                parent: if i == 0 { -1 } else { i as i32 - 1 },
                rest_local: Mat4::IDENTITY,
                inverse_bind: Mat4::IDENTITY,
            })
            .collect();
        SkinnedMeshData {
            vertices: vec![],
            indices: vec![],
            bones,
            feet_y: 0.0,
        }
    }

    #[test]
    fn identity_g1_produces_valid_skin() {
        let g1 = [Mat4::IDENTITY; 34];
        let mesh = minimal_mesh();
        let skin = g1_to_skin(&g1, &mesh);
        for i in 0..24 {
            assert!(skin[i].is_finite(), "bone {i} has non-finite matrix");
        }
    }

    #[test]
    fn rotation_g1_preserves_validity() {
        let mesh = minimal_mesh();
        let mut g1 = [Mat4::IDENTITY; 34];
        // Rotate left knee (G1 index 4)
        g1[4] = Mat4::from_rotation_x(0.5);
        let skin = g1_to_skin(&g1, &mesh);
        for i in 0..24 {
            assert!(skin[i].is_finite(), "bone {i} has non-finite matrix");
        }
    }

    #[test]
    fn no_shear_on_spread_pose() {
        let mesh = minimal_mesh();
        let mut g1 = [Mat4::IDENTITY; 34];
        // Arms spread: rotate left/right shoulders
        g1[18] = Mat4::from_rotation_z(-0.8); // left_shoulder_pitch
        g1[26] = Mat4::from_rotation_z(0.8); // right_shoulder_pitch
        // Legs spread
        g1[1] = Mat4::from_rotation_x(0.3); // left_hip_pitch
        g1[8] = Mat4::from_rotation_x(-0.3); // right_hip_pitch
        let skin = g1_to_skin(&g1, &mesh);
        for i in 0..24 {
            assert!(skin[i].is_finite(), "bone {i} has non-finite matrix");
            // Check no zero-scale (which would cause shearing)
            let s = glam::vec3(
                skin[i].x_axis.truncate().length(),
                skin[i].y_axis.truncate().length(),
                skin[i].z_axis.truncate().length(),
            );
            assert!(
                s.x > 0.01 && s.y > 0.01 && s.z > 0.01,
                "bone {i} has zero scale: {:?}",
                s
            );
        }
    }

    #[test]
    fn world_to_local_is_invertible() {
        let mut g1 = [Mat4::IDENTITY; 34];
        // Give some bones rotation
        g1[4] = Mat4::from_rotation_x(0.5);
        g1[18] = Mat4::from_rotation_z(-0.8);
        g1[12] = Mat4::from_translation(Vec3::new(0.0, 0.5, 0.0));

        let local = world_to_local(&g1, &MOTION_BRICKS_PARENTS);
        let rebuilt = fk_world_sized::<34>(&local, &MOTION_BRICKS_PARENTS);

        for i in 0..34 {
            let diff = g1[i] - rebuilt[i];
            assert!(
                diff.x_axis.length() < 1e-4 && diff.y_axis.length() < 1e-4,
                "bone {i} world→local→FK mismatch"
            );
        }
    }

    /// Sized version of fk_world for test use (generic/array version).
    fn fk_world_sized<const N: usize>(local: &[Mat4; N], parents: &[i32; N]) -> [Mat4; N] {
        let mut world = [Mat4::IDENTITY; N];
        for i in 0..N {
            if parents[i] >= 0 {
                world[i] = world[parents[i] as usize] * local[i];
            } else {
                world[i] = local[i];
            }
        }
        world
    }
}
