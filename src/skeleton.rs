//! Rich combat skeleton (103 bones) for martial-arts simulation.
//!
//! Bone index layout (103 bones):
//!   [0]             Pelvis (root)
//!   [1..20]         Spine: L5→L1, T12→T6, C7→C1   (19 bones)
//!   [20..28]        Left leg: Hip→Femur→...         (8 bones)
//!   [28..36]        Right leg                        (8 bones)
//!   [36..46]        Left arm: Clavicle→...           (10 bones)
//!   [46..56]        Right arm                        (10 bones)
//!   [56..71]        Left fingers: 5×3 phalanges     (15 bones)
//!   [71..86]        Right fingers                    (15 bones)
//!   [86..93]        Left foot details               (7 bones)
//!   [93..100]       Right foot details               (7 bones)
//!   [100..103]      Head: Skull, Jaw, HeadIK        (3 bones)

use crate::asset::SkinnedMeshData;
use glam::Mat4;

// ── constants ───────────────────────────────────────────────────────────────

pub const BONE_COUNT: usize = 103;

pub const PELVIS: usize = 0;

pub const SPINE_FIRST: usize = 1;
pub const SPINE_COUNT: usize = 19;
pub const SPINE_LAST: usize = SPINE_FIRST + SPINE_COUNT; // 20

pub const LEG_LEFT_FIRST: usize = 20;
pub const LEG_COUNT: usize = 8;
pub const LEG_LEFT_LAST: usize = LEG_LEFT_FIRST + LEG_COUNT;

pub const LEG_RIGHT_FIRST: usize = 28;
pub const LEG_RIGHT_LAST: usize = LEG_RIGHT_FIRST + LEG_COUNT;

pub const ARM_LEFT_FIRST: usize = 36;
pub const ARM_COUNT: usize = 10;
pub const ARM_LEFT_LAST: usize = ARM_LEFT_FIRST + ARM_COUNT;

pub const ARM_RIGHT_FIRST: usize = 46;
pub const ARM_RIGHT_LAST: usize = ARM_RIGHT_FIRST + ARM_COUNT;

pub const FINGER_LEFT_FIRST: usize = 56;
pub const FINGER_COUNT: usize = 15;
pub const FINGER_LEFT_LAST: usize = FINGER_LEFT_FIRST + FINGER_COUNT;

pub const FINGER_RIGHT_FIRST: usize = 71;
pub const FINGER_RIGHT_LAST: usize = FINGER_RIGHT_FIRST + FINGER_COUNT;

pub const FOOT_LEFT_FIRST: usize = 86;
pub const FOOT_DETAIL_COUNT: usize = 7;
pub const FOOT_LEFT_LAST: usize = FOOT_LEFT_FIRST + FOOT_DETAIL_COUNT;

pub const FOOT_RIGHT_FIRST: usize = 93;
pub const FOOT_RIGHT_LAST: usize = FOOT_RIGHT_FIRST + FOOT_DETAIL_COUNT;

pub const HEAD_FIRST: usize = 100;
pub const HEAD_COUNT: usize = 3;
pub const HEAD_LAST: usize = HEAD_FIRST + HEAD_COUNT;

pub const HEAD_SKULL: usize = 100;
pub const HEAD_JAW: usize = 101;
pub const HEAD_IK: usize = 102;

// Key spine vertebrae
pub const C7: usize = 13;
pub const C1: usize = 19;

// ── bone names ──────────────────────────────────────────────────────────────

pub const BONE_NAMES: [&str; BONE_COUNT] = [
    // 0
    "Pelvis",
    // 1..20: spine (19 bones)
    "L5",
    "L4",
    "L3",
    "L2",
    "L1",
    "T12",
    "T11",
    "T10",
    "T9",
    "T8",
    "T7",
    "T6",
    "C7",
    "C6",
    "C5",
    "C4",
    "C3",
    "C2",
    "C1",
    // 20..28: left leg (8)
    "LeftHip",
    "LeftFemur",
    "LeftKnee",
    "LeftTibia",
    "LeftFibula",
    "LeftAnkle",
    "LeftSubtalar",
    "LeftToeBase",
    // 28..36: right leg (8)
    "RightHip",
    "RightFemur",
    "RightKnee",
    "RightTibia",
    "RightFibula",
    "RightAnkle",
    "RightSubtalar",
    "RightToeBase",
    // 36..46: left arm (10)
    "LeftClavicle",
    "LeftScapula",
    "LeftShoulder",
    "LeftHumerus",
    "LeftElbow",
    "LeftRadius",
    "LeftUlna",
    "LeftWrist",
    "LeftHand",
    "LeftHandIK",
    // 46..56: right arm (10)
    "RightClavicle",
    "RightScapula",
    "RightShoulder",
    "RightHumerus",
    "RightElbow",
    "RightRadius",
    "RightUlna",
    "RightWrist",
    "RightHand",
    "RightHandIK",
    // 56..71: left fingers (15)
    "LThumb1",
    "LThumb2",
    "LThumb3",
    "LIndex1",
    "LIndex2",
    "LIndex3",
    "LMiddle1",
    "LMiddle2",
    "LMiddle3",
    "LRing1",
    "LRing2",
    "LRing3",
    "LPinky1",
    "LPinky2",
    "LPinky3",
    // 71..86: right fingers (15)
    "RThumb1",
    "RThumb2",
    "RThumb3",
    "RIndex1",
    "RIndex2",
    "RIndex3",
    "RMiddle1",
    "RMiddle2",
    "RMiddle3",
    "RRing1",
    "RRing2",
    "RRing3",
    "RPinky1",
    "RPinky2",
    "RPinky3",
    // 86..93: left foot (7)
    "LMetatarsal1",
    "LMetatarsal2",
    "LMetatarsal3",
    "LMetatarsal4",
    "LMetatarsal5",
    "LToeTip",
    "LFootIK",
    // 93..100: right foot (7)
    "RMetatarsal1",
    "RMetatarsal2",
    "RMetatarsal3",
    "RMetatarsal4",
    "RMetatarsal5",
    "RToeTip",
    "RFootIK",
    // 100..103: head (3)
    "Skull",
    "Jaw",
    "HeadIK",
];

// ── parent indices ──────────────────────────────────────────────────────────

/// Parent index (-1 for root) for each bone.
pub fn bone_parent(i: usize) -> i32 {
    const PARENTS: [i32; BONE_COUNT] = {
        let mut p = [-1i32; BONE_COUNT];
        let mut i = 0;

        // Pelvis
        p[0] = -1;

        // Spine chain: Pelvis → L5 → L4 → … → C1
        while i < 19 {
            p[1 + i] = i as i32;
            i += 1;
        }

        // Left leg
        p[20] = 0; // Hip → Pelvis
        p[21] = 20; // Femur → Hip
        p[22] = 21; // Knee → Femur
        p[23] = 22; // Tibia → Knee
        p[24] = 22; // Fibula → Knee
        p[25] = 23; // Ankle → Tibia
        p[26] = 25; // Subtalar → Ankle
        p[27] = 26; // ToeBase → Subtalar

        // Right leg
        p[28] = 0; // Hip → Pelvis
        p[29] = 28; // Femur → Hip
        p[30] = 29; // Knee → Femur
        p[31] = 30; // Tibia → Knee
        p[32] = 30; // Fibula → Knee
        p[33] = 31; // Ankle → Tibia
        p[34] = 33; // Subtalar → Ankle
        p[35] = 34; // ToeBase → Subtalar

        // Left arm (attached to C7=13)
        p[36] = 13; // Clavicle → C7
        p[37] = 36; // Scapula → Clavicle
        p[38] = 37; // Shoulder → Scapula
        p[39] = 38; // Humerus → Shoulder
        p[40] = 39; // Elbow → Humerus
        p[41] = 40; // Radius → Elbow
        p[42] = 40; // Ulna → Elbow
        p[43] = 41; // Wrist → Radius
        p[44] = 43; // Hand → Wrist
        p[45] = 44; // HandIK → Hand

        // Right arm
        p[46] = 13; // Clavicle → C7
        p[47] = 46; // Scapula → Clavicle
        p[48] = 47; // Shoulder → Scapula
        p[49] = 48; // Humerus → Shoulder
        p[50] = 49; // Elbow → Humerus
        p[51] = 50; // Radius → Elbow
        p[52] = 50; // Ulna → Elbow
        p[53] = 51; // Wrist → Radius
        p[54] = 53; // Hand → Wrist
        p[55] = 54; // HandIK → Hand

        // Left fingers (parent = LeftHand=44)
        p[56] = 44;
        p[57] = 56;
        p[58] = 57; // Thumb
        p[59] = 44;
        p[60] = 59;
        p[61] = 60; // Index
        p[62] = 44;
        p[63] = 62;
        p[64] = 63; // Middle
        p[65] = 44;
        p[66] = 65;
        p[67] = 66; // Ring
        p[68] = 44;
        p[69] = 68;
        p[70] = 69; // Pinky

        // Right fingers (parent = RightHand=54)
        p[71] = 54;
        p[72] = 71;
        p[73] = 72;
        p[74] = 54;
        p[75] = 74;
        p[76] = 75;
        p[77] = 54;
        p[78] = 77;
        p[79] = 78;
        p[80] = 54;
        p[81] = 80;
        p[82] = 81;
        p[83] = 54;
        p[84] = 83;
        p[85] = 84;

        // Left foot (parent = LeftToeBase=27, LeftSubtalar=26)
        p[86] = 27;
        p[87] = 27;
        p[88] = 27;
        p[89] = 27;
        p[90] = 27; // Metatarsals
        p[91] = 27; // LToeTip → LeftToeBase
        p[92] = 26; // LFootIK → LeftSubtalar

        // Right foot (parent = RightToeBase=35, RightSubtalar=34)
        p[93] = 35;
        p[94] = 35;
        p[95] = 35;
        p[96] = 35;
        p[97] = 35;
        p[98] = 35; // RToeTip → RightToeBase
        p[99] = 34; // RFootIK → RightSubtalar

        // Head (attached to C1=19)
        p[100] = 19; // Skull → C1
        p[101] = 100; // Jaw → Skull
        p[102] = 19; // HeadIK → C1

        p
    };
    if i < BONE_COUNT { PARENTS[i] } else { -1 }
}

// ── G1 source indices ───────────────────────────────────────────────────────

pub const G1_MAP: [i32; BONE_COUNT] = {
    let mut m = [-1i32; BONE_COUNT];

    m[0] = 0; // Pelvis

    // Left leg
    m[20] = 1; // LeftHip ← left_hip_pitch
    m[22] = 4; // LeftKnee ← left_knee
    m[25] = 5; // LeftAnkle ← left_ankle_pitch
    m[27] = 7; // LeftToeBase ← left_toe_base

    // Right leg
    m[28] = 8; // RightHip ← right_hip_pitch
    m[30] = 11; // RightKnee ← right_knee
    m[33] = 12; // RightAnkle ← right_ankle_pitch
    m[35] = 14; // RightToeBase ← right_toe_base

    // Spine anchors
    m[1] = 15; // L5 ← waist_yaw
    m[6] = 15; // T12 ← waist_yaw
    m[13] = 17; // C7 ← waist_pitch
    m[19] = 17; // C1 ← waist_pitch

    // Left arm
    m[36] = 18; // LeftClavicle ← left_shoulder_pitch
    m[39] = 18; // LeftHumerus ← left_shoulder_pitch
    m[40] = 21; // LeftElbow ← left_elbow
    m[43] = 23; // LeftWrist ← left_wrist_pitch
    m[44] = 23; // LeftHand ← left_wrist_pitch

    // Right arm
    m[46] = 26; // RightClavicle ← right_shoulder_pitch
    m[49] = 26; // RightHumerus ← right_shoulder_pitch
    m[50] = 29; // RightElbow ← right_elbow
    m[53] = 31; // RightWrist ← right_wrist_pitch
    m[54] = 31; // RightHand ← right_wrist_pitch

    m
};

// ── mannequin skin mapping ──────────────────────────────────────────────────

pub const SKIN_MAP: [i32; BONE_COUNT] = {
    let mut s = [-1i32; BONE_COUNT];

    s[0] = 0; // Pelvis → Hips(0)

    // Left leg → LeftUpLeg(1), LeftLeg(2), LeftFoot(3), LeftToeBase(4)
    s[20] = 1;
    s[22] = 2;
    s[25] = 3;
    s[27] = 4;

    // Right leg → RightUpLeg(5), RightLeg(6), RightFoot(7), RightToeBase(8)
    s[28] = 5;
    s[30] = 6;
    s[33] = 7;
    s[35] = 8;

    // Spine → Spine02(9), Spine01(10), Spine(11)
    s[1] = 9;
    s[6] = 9; // L5, T12 → Spine02
    s[11] = 10;
    s[13] = 10; // T7, C7 → Spine01
    s[16] = 11;
    s[19] = 11; // C4, C1 → Spine

    // Left arm → LeftShoulder(12), LeftArm(13), LeftForeArm(14), LeftHand(15)
    s[36] = 12;
    s[39] = 13;
    s[40] = 14;
    s[43] = 15;
    s[44] = 15;

    // Right arm → RightShoulder(16), RightArm(17), RightForeArm(18), RightHand(19)
    s[46] = 16;
    s[49] = 17;
    s[50] = 18;
    s[53] = 19;
    s[54] = 19;

    // Head → neck(20)
    s[100] = 20;

    s
};

// ── hit zone definitions ────────────────────────────────────────────────────

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HitZone {
    Head,
    Neck,
    Spine,
    Shoulder(LR),
    UpperArm(LR),
    Elbow(LR),
    Forearm(LR),
    WristHand(LR),
    Torso,
    Pelvis,
    UpperLeg(LR),
    Knee(LR),
    Shin(LR),
    AnkleFoot(LR),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LR {
    Left,
    Right,
}

pub fn hit_zone(idx: usize) -> HitZone {
    use HitZone::*;
    match idx {
        100..=102 => Head,
        13..=19 => Neck,
        1..=12 => Spine,
        // hips
        20..=21 | 28..=29 => Pelvis,
        // left shoulder
        36..=38 => Shoulder(LR::Left),
        39 => UpperArm(LR::Left),
        40 => Elbow(LR::Left),
        41..=42 => Forearm(LR::Left),
        43..=45 => WristHand(LR::Left),
        // right shoulder
        46..=48 => Shoulder(LR::Right),
        49 => UpperArm(LR::Right),
        50 => Elbow(LR::Right),
        51..=52 => Forearm(LR::Right),
        53..=55 => WristHand(LR::Right),
        // left leg
        22..=24 => UpperLeg(LR::Left),
        25 => Knee(LR::Left),
        26..=27 => Shin(LR::Left),
        // right leg
        30..=32 => UpperLeg(LR::Right),
        33 => Knee(LR::Right),
        34..=35 => Shin(LR::Right),
        // feet
        86..=92 => AnkleFoot(LR::Left),
        93..=99 => AnkleFoot(LR::Right),
        _ => Torso,
    }
}

// ── armor slot definitions ──────────────────────────────────────────────────

pub const ARMOR_SLOTS: &[(&str, &[usize])] = &[
    ("Helm", &[100, 101]),
    ("Gorget", &[14, 15, 16, 17, 18]),
    ("Breastplate", &[7, 8, 9, 10, 11, 12]),
    ("Fauld", &[1, 2, 3, 4, 5, 0]),
    ("Pauldron_L", &[36, 37, 38]),
    ("Rerebrace_L", &[39]),
    ("Couter_L", &[40]),
    ("Vambrace_L", &[41, 42]),
    ("Cuisses_L", &[21, 22]),
    ("Poleyn_L", &[23, 24]),
    ("Greave_L", &[25, 26]),
    ("Pauldron_R", &[46, 47, 48]),
    ("Rerebrace_R", &[49]),
    ("Couter_R", &[50]),
    ("Vambrace_R", &[51, 52]),
    ("Cuisses_R", &[29, 30]),
    ("Poleyn_R", &[31, 32]),
    ("Greave_R", &[33, 34]),
];

/// Initialize a default rest-pose transform array.
pub fn default_rest_transforms() -> [Mat4; BONE_COUNT] {
    [Mat4::IDENTITY; BONE_COUNT]
}

/// Build rich skeleton rest-pose world transforms from mannequin mesh bind data.
///
/// For rich bones that map to a skin bone (via SKIN_MAP), the rest-pose world
/// transform is derived from the mannequin's inverse_bind matrix.
/// For rich bones without a skin mapping (fingers, foot details, IK targets),
/// the transform follows the hierarchy with identity local transforms.
pub fn rest_pose_from_mesh(mesh: &SkinnedMeshData) -> [Mat4; BONE_COUNT] {
    let mut world = [Mat4::IDENTITY; BONE_COUNT];

    // Build skin-bind world matrices from inverse_bind
    let mut skin_bind = [Mat4::IDENTITY; 24];
    for i in 0..24.min(mesh.bones.len()) {
        skin_bind[i] = mesh.bones[i].inverse_bind.inverse();
    }

    // Map SKIN_MAP: rich bone → skin bind world (when available)
    for rich_idx in 0..BONE_COUNT {
        let skin_idx = SKIN_MAP[rich_idx];
        if skin_idx >= 0 && (skin_idx as usize) < mesh.bones.len() {
            world[rich_idx] = skin_bind[skin_idx as usize];
        }
    }

    // Fill unmapped bones via rest-pose hierarchy (identity local transforms)
    // This means fingers, foot details, IK targets follow their parents.
    // Already handled because they start as IDENTITY and propagate via FK.
    // But we need at least one pass of FK for the unmapped bones.
    for i in 0..BONE_COUNT {
        if SKIN_MAP[i] < 0 || (SKIN_MAP[i] as usize) >= mesh.bones.len() {
            let p = bone_parent(i);
            if p >= 0 {
                world[i] = world[p as usize]; // identity local → same as parent
            }
        }
    }

    world
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bone_count_consistent() {
        assert_eq!(BONE_COUNT, 103);
        assert_eq!(BONE_NAMES.len(), BONE_COUNT);
    }

    #[test]
    fn all_non_root_bones_have_parent() {
        for i in 0..BONE_COUNT {
            if i != PELVIS {
                assert!(
                    bone_parent(i) >= 0,
                    "bone {i} ({}) has no parent",
                    BONE_NAMES[i]
                );
            }
        }
    }

    #[test]
    fn head_chain() {
        assert_eq!(bone_parent(HEAD_IK), C1 as i32);
        assert_eq!(bone_parent(HEAD_SKULL), C1 as i32);
        assert_eq!(bone_parent(HEAD_JAW), HEAD_SKULL as i32);
    }
}
