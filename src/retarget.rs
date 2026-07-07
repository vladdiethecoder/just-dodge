//! Retargeting: MotionBricks G1 (34 bones) → rich skeleton (102 bones).
//!
//! Pipeline:
//!   1. Compute G1 world matrices → align to mannequin mesh space
//!   2. Map G1 bones to rich skeleton via G1_MAP
//!   3. Interpolate spine (3 G1 bones → 18 vertebrae)
//!   4. Propagate arm/leg detail bones from G1 parents
//!   5. Finger/toe IK stubs (identity for now)
//!   6. Head derived from C1
//!   7. Rich skeleton → 24 skinning matrices for render

use crate::asset::SkinnedMeshData;
use crate::skeleton::{self, BONE_COUNT, G1_MAP, SKIN_MAP};
use glam::Mat4;

/// One frame of rich skeleton world-space transforms.
pub type RichFrame = [Mat4; BONE_COUNT];

/// Retarget a single G1 frame (34 world matrices) into a rich skeleton frame.
pub fn retarget_frame(
    g1_world: &[Mat4; 34],
    mesh: &SkinnedMeshData,
) -> RichFrame {
    // Align G1 pelvis to mannequin Hips bind world.
    let hips_bind = mesh.bones[0].inverse_bind.inverse();
    let align = hips_bind * g1_world[0].inverse();

    let mut out = [Mat4::IDENTITY; BONE_COUNT];

    // Step 1: direct G1 mapping for bones that have a G1 source
    for i in 0..BONE_COUNT {
        let src = G1_MAP[i];
        if src >= 0 {
            out[i] = align * g1_world[src as usize];
        }
    }

    // Step 2: spine interpolation (3 G1 spine bones → 18 vertebrae)
    // G1 spine joints: 15=waist_yaw, 16=waist_roll, 17=waist_pitch
    // We have out[1]=L5, out[6]=T12 (both waist_yaw), out[12]=C7, out[18]=C1 (both waist_pitch)
    // Interpolate between these anchors.
    interpolate_spine(&mut out);

    // Step 3: propagate arm detail bones from their G1-driven parents
    propagate_arms(&mut out);

    // Step 4: propagate leg detail bones from their G1-driven parents
    propagate_legs(&mut out);

    // Step 5: finger IK stubs — identity for now (they follow the hand)
    for i in skeleton::FINGER_LEFT_FIRST..skeleton::FINGER_LEFT_LAST {
        out[i] = out[43]; // follow LeftHand
    }
    for i in skeleton::FINGER_RIGHT_FIRST..skeleton::FINGER_RIGHT_LAST {
        out[i] = out[53]; // follow RightHand
    }

    // Step 6: foot detail bones follow their parents
    for i in skeleton::FOOT_LEFT_FIRST..skeleton::FOOT_LEFT_LAST {
        out[i] = out[skeleton::bone_parent(i) as usize];
    }
    for i in skeleton::FOOT_RIGHT_FIRST..skeleton::FOOT_RIGHT_LAST {
        out[i] = out[skeleton::bone_parent(i) as usize];
    }

    // Step 7: head bones from C1
    out[99] = out[18]; // Skull → C1
    out[100] = out[18]; // Jaw → C1
    out[101] = out[18]; // HeadIK → C1

    out
}

/// Interpolate the rich spine from 3 G1 anchor bones (waist_yaw, waist_roll, waist_pitch).
/// Anchors are placed at L5(1), T12(6), C7(12), C1(18) and we lerp between them.
fn interpolate_spine(out: &mut RichFrame) {
    // Anchor positions (G1-driven rich bones)
    let anchors: [(usize, usize); 4] = [
        (1, 1),   // L5
        (6, 6),   // T12
        (12, 12), // C7
        (18, 18), // C1
    ];

    // For each gap between anchors, lerp translations and slerp rotations
    for pair in anchors.windows(2) {
        let (lo_idx, hi_idx) = (pair[0].0, pair[1].0);
        let (lo_src, hi_src) = (pair[0].1, pair[1].1);
        let count = (hi_idx - lo_idx) as f32;

        let lo = out[lo_src];
        let hi = out[hi_src];

        for j in 1..(hi_idx - lo_idx) {
            let t = j as f32 / count;
            out[lo_idx + j] = lerp_mat4(lo, hi, t);
        }
    }

    // Back-fill L5..L1 chain (indices 1..5) — they should be below T12
    // Actually they're between Pelvis(0) and T12(6).
    // L5(1) already assigned from waist_yaw. Interpolate L4(2)..L1(5) between Pelvis and T12.
    // But pelvis is driven by G1[0], not spine. The spine chain goes Pelvis→L5→...→C1.
    // L5's parent is Pelvis (via bone_parent), and L4's parent is L5, etc.
    // We should interpolate between pelvis(0) and T12(6) for L5→L1.
    let pelvis = out[0];
    let t12 = out[6];
    for j in 2..=5 {
        let t = (j - 1) as f32 / 5.0; // j=2→t=0.2, j=5→t=0.8
        out[j] = lerp_mat4(pelvis, t12, t);
    }
    // L5(1) stays at pelvis→t12 interpolation too
    out[1] = lerp_mat4(pelvis, t12, 0.1);

    // T6(11) through T8(10) — between T12(6) and C7(12)
    let t12_m = out[6];
    let c7 = out[12];
    for j in 7..=11 {
        let t = (j - 6) as f32 / 6.0;
        out[j] = lerp_mat4(t12_m, c7, t);
    }

    // C6(13) through C2(17) — between C7(12) and C1(18)
    let c7_m = out[12];
    let c1 = out[18];
    for j in 13..18 {
        let t = (j - 12) as f32 / 6.0;
        out[j] = lerp_mat4(c7_m, c1, t);
    }
}

/// Propagate arm detail bones that have no G1 source.
/// Clavicle→Scapula→Shoulder→Humerus are already G1-driven (share shoulder_pitch).
/// Elbow, Wrist, Hand are G1-driven.
/// Radius/Ulna follow Elbow. HandIK follows Hand.
fn propagate_arms(out: &mut RichFrame) {
    for (child, parent) in [
        (36, 35), // LeftScapula ← LeftClavicle
        (37, 36), // LeftShoulder ← LeftScapula
        (40, 39), // LeftRadius ← LeftElbow
        (41, 39), // LeftUlna ← LeftElbow
        (44, 43), // LeftHandIK ← LeftHand
        (46, 45), // RightScapula ← RightClavicle
        (47, 46), // RightShoulder ← RightScapula
        (50, 49), // RightRadius ← RightElbow
        (51, 49), // RightUlna ← RightElbow
        (54, 53), // RightHandIK ← RightHand
    ] {
        out[child] = out[parent];
    }
}

/// Propagate leg detail bones.
/// Femur, Tibia, Fibula, Subtalar follow their G1-driven parents.
fn propagate_legs(out: &mut RichFrame) {
    for (child, parent) in [
        (20, 19), // LeftFemur ← LeftHip
        (22, 21), // LeftTibia ← LeftKnee
        (23, 21), // LeftFibula ← LeftKnee
        (25, 24), // LeftSubtalar ← LeftAnkle
        (28, 27), // RightFemur ← RightHip
        (30, 29), // RightTibia ← RightKnee
        (31, 29), // RightFibula ← RightKnee
        (33, 32), // RightSubtalar ← RightAnkle
    ] {
        out[child] = out[parent];
    }
}

/// Compute 24 skinning matrices from a rich skeleton frame.
/// skin[i] = richWorld[skinSrc] * invBind[i]
pub fn rich_to_skin_matrices(rich: &RichFrame, mesh: &SkinnedMeshData) -> [Mat4; 24] {
    let mut out = [Mat4::IDENTITY; 24];
    for i in 0..24 {
        let src = SKIN_MAP.iter().position(|&s| s == i as i32);
        if let Some(skin_idx) = src {
            out[i] = rich[skin_idx] * mesh.bones[i].inverse_bind;
        }
    }
    out
}

/// Full pipeline: G1 frame → 24 skinning matrices.
pub fn g1_to_skin(g1_world: &[Mat4; 34], mesh: &SkinnedMeshData) -> [Mat4; 24] {
    let rich = retarget_frame(g1_world, mesh);
    rich_to_skin_matrices(&rich, mesh)
}

// ── math helpers ────────────────────────────────────────────────────────────

/// Simple linear interpolation between two Mat4s (lerp position, slerp rotation).
fn lerp_mat4(a: Mat4, b: Mat4, t: f32) -> Mat4 {
    let (sa, ra, ta) = a.to_scale_rotation_translation();
    let (sb, rb, tb) = b.to_scale_rotation_translation();

    let t_trans = ta.lerp(tb, t);
    let t_scale = sa.lerp(sb, t);
    let t_rot = ra.slerp(rb, t);

    Mat4::from_scale_rotation_translation(t_scale, t_rot, t_trans)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn retarget_identity_motion() {
        // Identity G1 frame — all bones at origin with identity rotation.
        let g1 = [Mat4::IDENTITY; 34];

        // Minimal mesh with one bone
        let bones = vec![Bone {
            name: "test".into(),
            parent: -1,
            rest_local: Mat4::IDENTITY,
            inverse_bind: Mat4::IDENTITY,
        }];
        let mesh = SkinnedMeshData {
            vertices: vec![],
            indices: vec![],
            bones,
            feet_y: 0.0,
        };

        let rich = retarget_frame(&g1, &mesh);

        // All bones should have valid transforms (no NaN, no zero scale)
        for i in 0..BONE_COUNT {
            let m = rich[i];
            assert!(m.is_finite(), "bone {} has non-finite matrix", i);
        }
    }

    #[test]
    fn skeleton_constants_consistent() {
        assert_eq!(BONE_COUNT, 102);
        assert_eq!(skeleton::FINGER_LEFT_LAST, 70);
        assert_eq!(skeleton::FINGER_RIGHT_LAST, 85);
        assert_eq!(skeleton::HEAD_LAST, 102);
    }
}
