//! Pinned Unitree G1 / MotionBricks articulation data.
//!
//! Generated from `NVlabs/GR00T-WholeBodyControl` commit
//! `021df739f0b36e514399f0030e3a195683a46383`.
//! `G1Skeleton34` supplies topology; `g1.xml` supplies physical values.
//! The two toe and two hand-roll nodes absent from MJCF remain explicit
//! zero-mass virtual markers and never participate in rigid-body dynamics.

pub const G1_NODE_COUNT: usize = 34;
pub const G1_PHYSICAL_BODY_COUNT: usize = 30;
pub const G1_TOTAL_MASS_MILLIGRAMS: u64 = 33341142;
pub const G1_SOURCE_COMMIT: &str = "021df739f0b36e514399f0030e3a195683a46383";
pub const G1_SKELETON_SHA256: &str =
    "6f5bc54dfafed7fb8ccd6133ed6a5114ad5c260bbfb01354ab2bd121ae641eac";
pub const G1_MJCF_SHA256: &str = "5d76cf92f00dd49d6eb9fae38d7d38e46886848b602ac691051e886c3bcccfb1";
const Q30_ONE: i64 = 1_i64 << 30;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum G1NodeKind {
    PhysicalRoot,
    ActuatedHinge,
    VirtualMarker,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct G1NodeV1 {
    pub name: &'static str,
    pub parent_index: i8,
    pub kind: G1NodeKind,
    pub body_offset_micrometers: [i32; 3],
    pub body_orientation_q30: [i32; 4],
    pub center_of_mass_micrometers: [i32; 3],
    pub inertia_orientation_q30: [i32; 4],
    pub mass_milligrams: u32,
    pub diagonal_inertia_nano_kg_m2: [u32; 3],
    pub hinge_axis_q30: [i32; 3],
    pub limits_microradians: [i32; 2],
    pub max_torque_millinewton_m: u32,
    pub armature_nano_kg_m2: u32,
    pub friction_loss_millinewton_m: u32,
}

pub const G1_NODES: [G1NodeV1; G1_NODE_COUNT] = [
    G1NodeV1 {
        name: "pelvis_skel",
        parent_index: -1,
        kind: G1NodeKind::PhysicalRoot,
        body_offset_micrometers: [0, 0, 793000],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [0, 0, -76050],
        inertia_orientation_q30: [1073741824, 0, -428582, 0],
        mass_milligrams: 3813000,
        diagonal_inertia_nano_kg_m2: [10549000, 9308900, 7918400],
        hinge_axis_q30: [0, 0, 0],
        limits_microradians: [0, 0],
        max_torque_millinewton_m: 0,
        armature_nano_kg_m2: 0,
        friction_loss_millinewton_m: 0,
    },
    G1NodeV1 {
        name: "left_hip_pitch_skel",
        parent_index: 0,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, 64452, -102700],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [2741, 47791, -26060],
        inertia_orientation_q30: [1025275266, 315641442, 32486703, 32343251],
        mass_milligrams: 1350000,
        diagonal_inertia_nano_kg_m2: [1815170, 1534220, 1162120],
        hinge_axis_q30: [0, 1073741824, 0],
        limits_microradians: [-2530700, 2879800],
        max_torque_millinewton_m: 88000,
        armature_nano_kg_m2: 10177520,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_hip_roll_skel",
        parent_index: 1,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, 52000, -30465],
        body_orientation_q30: [1069639056, 0, -93779108, 0],
        center_of_mass_micrometers: [29812, -1045, -87934],
        inertia_orientation_q30: [1049913345, -21165, 220735549, -43356943],
        mass_milligrams: 1520000,
        diagonal_inertia_nano_kg_m2: [2549860, 2411690, 1487550],
        hinge_axis_q30: [1073741824, 0, 0],
        limits_microradians: [-523600, 2967100],
        max_torque_millinewton_m: 139000,
        armature_nano_kg_m2: 25101925,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_hip_yaw_skel",
        parent_index: 2,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [25001, 0, -124120],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [-57709, -10981, -150780],
        inertia_orientation_q30: [644887192, 169994806, 239961970, 806574457],
        mass_milligrams: 1702000,
        diagonal_inertia_nano_kg_m2: [7761660, 7175750, 1601390],
        hinge_axis_q30: [0, 0, 1073741824],
        limits_microradians: [-2757600, 2757600],
        max_torque_millinewton_m: 88000,
        armature_nano_kg_m2: 10177520,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_knee_skel",
        parent_index: 3,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [-78273, 2149, -177340],
        body_orientation_q30: [1069639056, 0, 93779108, 0],
        center_of_mass_micrometers: [5457, 3964, -120740],
        inertia_orientation_q30: [991512528, -35186412, 16991535, 410241317],
        mass_milligrams: 1932000,
        diagonal_inertia_nano_kg_m2: [11380400, 11277800, 1464580],
        hinge_axis_q30: [0, 1073741824, 0],
        limits_microradians: [-87267, 2879800],
        max_torque_millinewton_m: 139000,
        armature_nano_kg_m2: 25101925,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_ankle_pitch_skel",
        parent_index: 4,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, -94, -300010],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [-7269, 0, 11137],
        inertia_orientation_q30: [647523228, 396452325, 396452325, 647523228],
        mass_milligrams: 74000,
        diagonal_inertia_nano_kg_m2: [18900, 14080, 6920],
        hinge_axis_q30: [0, 1073741824, 0],
        limits_microradians: [-872670, 523600],
        max_torque_millinewton_m: 50000,
        armature_nano_kg_m2: 7219450,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_ankle_roll_skel",
        parent_index: 5,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, 0, -17558],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [26505, 0, -16425],
        inertia_orientation_q30: [-516569, 782201591, -664611, 735582943],
        mass_milligrams: 608000,
        diagonal_inertia_nano_kg_m2: [1672180, 1616100, 217621],
        hinge_axis_q30: [1073741824, 0, 0],
        limits_microradians: [-261800, 261800],
        max_torque_millinewton_m: 50000,
        armature_nano_kg_m2: 7219450,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_toe_base",
        parent_index: 6,
        kind: G1NodeKind::VirtualMarker,
        body_offset_micrometers: [0, 0, 0],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [0, 0, 0],
        inertia_orientation_q30: [1073741824, 0, 0, 0],
        mass_milligrams: 0,
        diagonal_inertia_nano_kg_m2: [0, 0, 0],
        hinge_axis_q30: [0, 0, 0],
        limits_microradians: [0, 0],
        max_torque_millinewton_m: 0,
        armature_nano_kg_m2: 0,
        friction_loss_millinewton_m: 0,
    },
    G1NodeV1 {
        name: "right_hip_pitch_skel",
        parent_index: 0,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, -64452, -102700],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [2741, -47791, -26060],
        inertia_orientation_q30: [1025275266, -315641442, 32486703, -32343251],
        mass_milligrams: 1350000,
        diagonal_inertia_nano_kg_m2: [1815170, 1534220, 1162120],
        hinge_axis_q30: [0, 1073741824, 0],
        limits_microradians: [-2530700, 2879800],
        max_torque_millinewton_m: 88000,
        armature_nano_kg_m2: 10177520,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "right_hip_roll_skel",
        parent_index: 8,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, -52000, -30465],
        body_orientation_q30: [1069639056, 0, -93779108, 0],
        center_of_mass_micrometers: [29812, 1045, -87934],
        inertia_orientation_q30: [1049913345, 21165, 220735549, 43356943],
        mass_milligrams: 1520000,
        diagonal_inertia_nano_kg_m2: [2549860, 2411690, 1487550],
        hinge_axis_q30: [1073741824, 0, 0],
        limits_microradians: [-2967100, 523600],
        max_torque_millinewton_m: 139000,
        armature_nano_kg_m2: 25101925,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "right_hip_yaw_skel",
        parent_index: 9,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [25001, 0, -124120],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [-57709, 10981, -150780],
        inertia_orientation_q30: [806574457, 239961970, 169994806, 644887192],
        mass_milligrams: 1702000,
        diagonal_inertia_nano_kg_m2: [7761660, 7175750, 1601390],
        hinge_axis_q30: [0, 0, 1073741824],
        limits_microradians: [-2757600, 2757600],
        max_torque_millinewton_m: 88000,
        armature_nano_kg_m2: 10177520,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "right_knee_skel",
        parent_index: 10,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [-78273, -2149, -177340],
        body_orientation_q30: [1069639056, 0, 93779108, 0],
        center_of_mass_micrometers: [5457, -3964, -120740],
        inertia_orientation_q30: [991535076, 37073728, 12491161, -410182262],
        mass_milligrams: 1932000,
        diagonal_inertia_nano_kg_m2: [11374000, 11284300, 1464520],
        hinge_axis_q30: [0, 1073741824, 0],
        limits_microradians: [-87267, 2879800],
        max_torque_millinewton_m: 139000,
        armature_nano_kg_m2: 25101925,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "right_ankle_pitch_skel",
        parent_index: 11,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, 94, -300010],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [-7269, 0, 11137],
        inertia_orientation_q30: [647523228, 396452325, 396452325, 647523228],
        mass_milligrams: 74000,
        diagonal_inertia_nano_kg_m2: [18900, 14080, 6920],
        hinge_axis_q30: [0, 1073741824, 0],
        limits_microradians: [-872670, 523600],
        max_torque_millinewton_m: 50000,
        armature_nano_kg_m2: 7219450,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "right_ankle_roll_skel",
        parent_index: 12,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, 0, -17558],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [26505, 0, -16425],
        inertia_orientation_q30: [516569, 782201591, 664611, 735582943],
        mass_milligrams: 608000,
        diagonal_inertia_nano_kg_m2: [1672180, 1616100, 217621],
        hinge_axis_q30: [1073741824, 0, 0],
        limits_microradians: [-261800, 261800],
        max_torque_millinewton_m: 50000,
        armature_nano_kg_m2: 7219450,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "right_toe_base",
        parent_index: 13,
        kind: G1NodeKind::VirtualMarker,
        body_offset_micrometers: [0, 0, 0],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [0, 0, 0],
        inertia_orientation_q30: [1073741824, 0, 0, 0],
        mass_milligrams: 0,
        diagonal_inertia_nano_kg_m2: [0, 0, 0],
        hinge_axis_q30: [0, 0, 0],
        limits_microradians: [0, 0],
        max_torque_millinewton_m: 0,
        armature_nano_kg_m2: 0,
        friction_loss_millinewton_m: 0,
    },
    G1NodeV1 {
        name: "waist_yaw_skel",
        parent_index: 0,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, 0, 0],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [3494, 233, 18034],
        inertia_orientation_q30: [311059785, 634582492, -362704619, 722436048],
        mass_milligrams: 214000,
        diagonal_inertia_nano_kg_m2: [163531, 107714, 102205],
        hinge_axis_q30: [0, 0, 1073741824],
        limits_microradians: [-2618000, 2618000],
        max_torque_millinewton_m: 88000,
        armature_nano_kg_m2: 10177520,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "waist_roll_skel",
        parent_index: 15,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [-3964, 0, 44000],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [0, 23, 0],
        inertia_orientation_q30: [536870912, 536870912, -536870912, 536870912],
        mass_milligrams: 86000,
        diagonal_inertia_nano_kg_m2: [8245, 7079, 6339],
        hinge_axis_q30: [1073741824, 0, 0],
        limits_microradians: [-520000, 520000],
        max_torque_millinewton_m: 50000,
        armature_nano_kg_m2: 7219450,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "waist_pitch_skel",
        parent_index: 16,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, 0, 0],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [2032, 340, 184568],
        inertia_orientation_q30: [1073530297, -64781, 21287576, 1417189],
        mass_milligrams: 7818000,
        diagonal_inertia_nano_kg_m2: [121847000, 109825000, 27373500],
        hinge_axis_q30: [0, 1073741824, 0],
        limits_microradians: [-520000, 520000],
        max_torque_millinewton_m: 50000,
        armature_nano_kg_m2: 7219450,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_shoulder_pitch_skel",
        parent_index: 17,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [3956, 100220, 247780],
        body_orientation_q30: [1063287874, 149465936, 14895, -105964],
        center_of_mass_micrometers: [0, 35892, -11628],
        inertia_orientation_q30: [702390362, 14007821, -350326524, 732560359],
        mass_milligrams: 718000,
        diagonal_inertia_nano_kg_m2: [465864, 432842, 406394],
        hinge_axis_q30: [0, 1073741824, 0],
        limits_microradians: [-3089200, 2670400],
        max_torque_millinewton_m: 25000,
        armature_nano_kg_m2: 3609725,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_shoulder_roll_skel",
        parent_index: 18,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, 38000, -13831],
        body_orientation_q30: [1063292169, -149434797, 0, 0],
        center_of_mass_micrometers: [-227, 7270, -63243],
        inertia_orientation_q30: [752967897, -21069284, -7626971, 765152719],
        mass_milligrams: 643000,
        diagonal_inertia_nano_kg_m2: [691311, 618011, 388977],
        hinge_axis_q30: [1073741824, 0, 0],
        limits_microradians: [-1588200, 2251500],
        max_torque_millinewton_m: 25000,
        armature_nano_kg_m2: 3609725,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_shoulder_yaw_skel",
        parent_index: 19,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, 6240, -103200],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [10773, -2949, -72009],
        inertia_orientation_q30: [769742965, -103597725, -73008216, 737804514],
        mass_milligrams: 734000,
        diagonal_inertia_nano_kg_m2: [1061870, 1032170, 400661],
        hinge_axis_q30: [0, 0, 1073741824],
        limits_microradians: [-2618000, 2618000],
        max_torque_millinewton_m: 25000,
        armature_nano_kg_m2: 3609725,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_elbow_skel",
        parent_index: 20,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [15783, 0, -80518],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [64956, 4454, -10062],
        inertia_orientation_q30: [581715739, 683041534, 417493370, 416750340],
        mass_milligrams: 600000,
        diagonal_inertia_nano_kg_m2: [443035, 421612, 259353],
        hinge_axis_q30: [0, 1073741824, 0],
        limits_microradians: [-1047200, 2094400],
        max_torque_millinewton_m: 25000,
        armature_nano_kg_m2: 3609725,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_wrist_roll_skel",
        parent_index: 21,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [100000, 1888, -10000],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [17139, 538, 0],
        inertia_orientation_q30: [617764474, 442024075, -617300617, 441408821],
        mass_milligrams: 85445,
        diagonal_inertia_nano_kg_m2: [54821, 49665, 35780],
        hinge_axis_q30: [1073741824, 0, 0],
        limits_microradians: [-1972220, 1972220],
        max_torque_millinewton_m: 25000,
        armature_nano_kg_m2: 3609725,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_wrist_pitch_skel",
        parent_index: 22,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [38000, 0, 0],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [23000, -1117, -1117],
        inertia_orientation_q30: [268433309, 710133114, 314645009, 691068828],
        mass_milligrams: 484050,
        diagonal_inertia_nano_kg_m2: [430353, 429873, 164648],
        hinge_axis_q30: [0, 1073741824, 0],
        limits_microradians: [-1614430, 1614430],
        max_torque_millinewton_m: 5000,
        armature_nano_kg_m2: 4250000,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_wrist_yaw_skel",
        parent_index: 23,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [46000, 0, 0],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [70824, 192, 1617],
        inertia_orientation_q30: [548221437, 565104953, 502594925, 529556583],
        mass_milligrams: 254576,
        diagonal_inertia_nano_kg_m2: [646113, 559993, 147566],
        hinge_axis_q30: [0, 0, 1073741824],
        limits_microradians: [-1614430, 1614430],
        max_torque_millinewton_m: 5000,
        armature_nano_kg_m2: 4250000,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "left_hand_roll_skel",
        parent_index: 24,
        kind: G1NodeKind::VirtualMarker,
        body_offset_micrometers: [0, 0, 0],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [0, 0, 0],
        inertia_orientation_q30: [1073741824, 0, 0, 0],
        mass_milligrams: 0,
        diagonal_inertia_nano_kg_m2: [0, 0, 0],
        hinge_axis_q30: [0, 0, 0],
        limits_microradians: [0, 0],
        max_torque_millinewton_m: 0,
        armature_nano_kg_m2: 0,
        friction_loss_millinewton_m: 0,
    },
    G1NodeV1 {
        name: "right_shoulder_pitch_skel",
        parent_index: 17,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [3956, -100210, 247780],
        body_orientation_q30: [1063287874, -149465936, 14895, 105964],
        center_of_mass_micrometers: [0, -35892, -11628],
        inertia_orientation_q30: [732560359, -350326524, 14007821, 702390362],
        mass_milligrams: 718000,
        diagonal_inertia_nano_kg_m2: [465864, 432842, 406394],
        hinge_axis_q30: [0, 1073741824, 0],
        limits_microradians: [-3089200, 2670400],
        max_torque_millinewton_m: 25000,
        armature_nano_kg_m2: 3609725,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "right_shoulder_roll_skel",
        parent_index: 26,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, -38000, -13831],
        body_orientation_q30: [1063292169, 149434797, 0, 0],
        center_of_mass_micrometers: [-227, -7270, -63243],
        inertia_orientation_q30: [765152719, -7626971, -21069284, 752967897],
        mass_milligrams: 643000,
        diagonal_inertia_nano_kg_m2: [691311, 618011, 388977],
        hinge_axis_q30: [1073741824, 0, 0],
        limits_microradians: [-2251500, 1588200],
        max_torque_millinewton_m: 25000,
        armature_nano_kg_m2: 3609725,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "right_shoulder_yaw_skel",
        parent_index: 27,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [0, -6240, -103200],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [10773, 2949, -72009],
        inertia_orientation_q30: [737804514, -73008216, -103597725, 769742965],
        mass_milligrams: 734000,
        diagonal_inertia_nano_kg_m2: [1061870, 1032170, 400661],
        hinge_axis_q30: [0, 0, 1073741824],
        limits_microradians: [-2618000, 2618000],
        max_torque_millinewton_m: 25000,
        armature_nano_kg_m2: 3609725,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "right_elbow_skel",
        parent_index: 28,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [15783, 0, -80518],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [64956, -4454, -10062],
        inertia_orientation_q30: [416750340, 417493370, 683041534, 581715739],
        mass_milligrams: 600000,
        diagonal_inertia_nano_kg_m2: [443035, 421612, 259353],
        hinge_axis_q30: [0, 1073741824, 0],
        limits_microradians: [-1047200, 2094400],
        max_torque_millinewton_m: 25000,
        armature_nano_kg_m2: 3609725,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "right_wrist_roll_skel",
        parent_index: 29,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [100000, -1888, -10000],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [17139, -538, 0],
        inertia_orientation_q30: [442024075, 617764474, -441408821, 617300617],
        mass_milligrams: 85445,
        diagonal_inertia_nano_kg_m2: [54821, 49665, 35780],
        hinge_axis_q30: [1073741824, 0, 0],
        limits_microradians: [-1972220, 1972220],
        max_torque_millinewton_m: 25000,
        armature_nano_kg_m2: 3609725,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "right_wrist_pitch_skel",
        parent_index: 30,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [38000, 0, 0],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [23000, 1117, -1117],
        inertia_orientation_q30: [691068828, 314645009, 710133114, 268433309],
        mass_milligrams: 484050,
        diagonal_inertia_nano_kg_m2: [430353, 429873, 164648],
        hinge_axis_q30: [0, 1073741824, 0],
        limits_microradians: [-1614430, 1614430],
        max_torque_millinewton_m: 5000,
        armature_nano_kg_m2: 4250000,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "right_wrist_yaw_skel",
        parent_index: 31,
        kind: G1NodeKind::ActuatedHinge,
        body_offset_micrometers: [46000, 0, 0],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [70824, -192, 1617],
        inertia_orientation_q30: [529556583, 502594925, 565104953, 548221437],
        mass_milligrams: 254576,
        diagonal_inertia_nano_kg_m2: [646113, 559993, 147566],
        hinge_axis_q30: [0, 0, 1073741824],
        limits_microradians: [-1614430, 1614430],
        max_torque_millinewton_m: 5000,
        armature_nano_kg_m2: 4250000,
        friction_loss_millinewton_m: 100,
    },
    G1NodeV1 {
        name: "right_hand_roll_skel",
        parent_index: 32,
        kind: G1NodeKind::VirtualMarker,
        body_offset_micrometers: [0, 0, 0],
        body_orientation_q30: [1073741824, 0, 0, 0],
        center_of_mass_micrometers: [0, 0, 0],
        inertia_orientation_q30: [1073741824, 0, 0, 0],
        mass_milligrams: 0,
        diagonal_inertia_nano_kg_m2: [0, 0, 0],
        hinge_axis_q30: [0, 0, 0],
        limits_microradians: [0, 0],
        max_torque_millinewton_m: 0,
        armature_nano_kg_m2: 0,
        friction_loss_millinewton_m: 0,
    },
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum G1ModelError {
    RootInvariant,
    ParentOrder(usize),
    DuplicateName(usize),
    InvalidPhysicalBody(usize),
    InvalidQuaternion(usize),
    InvalidHinge(usize),
    InvalidMarker(usize),
    BilateralMismatch(usize, usize),
    PhysicalBodyCount,
    TotalMassMismatch,
}

pub fn validate_g1_articulation() -> Result<(), G1ModelError> {
    let roots = G1_NODES.iter().filter(|node| node.parent_index < 0).count();
    if roots != 1 || G1_NODES[0].kind != G1NodeKind::PhysicalRoot || G1_NODES[0].parent_index != -1
    {
        return Err(G1ModelError::RootInvariant);
    }
    for (index, node) in G1_NODES.iter().enumerate() {
        if index > 0 && !(0..index as i8).contains(&node.parent_index) {
            return Err(G1ModelError::ParentOrder(index));
        }
        if G1_NODES[..index]
            .iter()
            .any(|prior| prior.name == node.name)
        {
            return Err(G1ModelError::DuplicateName(index));
        }
        match node.kind {
            G1NodeKind::PhysicalRoot => {
                if index != 0 {
                    return Err(G1ModelError::RootInvariant);
                }
                validate_physical(index, node, false)?;
            }
            G1NodeKind::ActuatedHinge => validate_physical(index, node, true)?,
            G1NodeKind::VirtualMarker => {
                if node.mass_milligrams != 0
                    || node.diagonal_inertia_nano_kg_m2 != [0; 3]
                    || node.hinge_axis_q30 != [0; 3]
                    || node.limits_microradians != [0; 2]
                    || node.max_torque_millinewton_m != 0
                    || node.armature_nano_kg_m2 != 0
                    || node.friction_loss_millinewton_m != 0
                {
                    return Err(G1ModelError::InvalidMarker(index));
                }
            }
        }
    }
    let physical_count = G1_NODES
        .iter()
        .filter(|node| node.kind != G1NodeKind::VirtualMarker)
        .count();
    if physical_count != G1_PHYSICAL_BODY_COUNT {
        return Err(G1ModelError::PhysicalBodyCount);
    }
    for (left, right) in [
        (1, 8),
        (2, 9),
        (3, 10),
        (4, 11),
        (5, 12),
        (6, 13),
        (18, 26),
        (19, 27),
        (20, 28),
        (21, 29),
        (22, 30),
        (23, 31),
        (24, 32),
    ] {
        validate_bilateral(left, right)?;
    }
    let total: u64 = G1_NODES
        .iter()
        .map(|node| u64::from(node.mass_milligrams))
        .sum();
    if total != G1_TOTAL_MASS_MILLIGRAMS {
        return Err(G1ModelError::TotalMassMismatch);
    }
    Ok(())
}

fn validate_physical(index: usize, node: &G1NodeV1, hinge: bool) -> Result<(), G1ModelError> {
    if node.mass_milligrams == 0 || node.diagonal_inertia_nano_kg_m2.contains(&0) {
        return Err(G1ModelError::InvalidPhysicalBody(index));
    }
    if !unit_quaternion(node.body_orientation_q30) || !unit_quaternion(node.inertia_orientation_q30)
    {
        return Err(G1ModelError::InvalidQuaternion(index));
    }
    if hinge {
        let axis_norm: i64 = node
            .hinge_axis_q30
            .iter()
            .map(|v| i64::from(*v) * i64::from(*v))
            .sum();
        if (axis_norm - Q30_ONE * Q30_ONE).abs() > Q30_ONE
            || node.limits_microradians[0] >= node.limits_microradians[1]
            || node.max_torque_millinewton_m == 0
            || node.armature_nano_kg_m2 == 0
            || node.friction_loss_millinewton_m == 0
        {
            return Err(G1ModelError::InvalidHinge(index));
        }
    } else if node.hinge_axis_q30 != [0; 3] || node.max_torque_millinewton_m != 0 {
        return Err(G1ModelError::InvalidPhysicalBody(index));
    }
    Ok(())
}

fn unit_quaternion(value: [i32; 4]) -> bool {
    let norm: i128 = value.iter().map(|v| i128::from(*v) * i128::from(*v)).sum();
    let unit = i128::from(Q30_ONE) * i128::from(Q30_ONE);
    (norm - unit).abs() <= unit / 100_000
}

fn validate_bilateral(left: usize, right: usize) -> Result<(), G1ModelError> {
    let l = G1_NODES[left];
    let r = G1_NODES[right];
    let offsets_match = l.body_offset_micrometers[0] == r.body_offset_micrometers[0]
        && (l.body_offset_micrometers[1] + r.body_offset_micrometers[1]).abs() <= 20
        && l.body_offset_micrometers[2] == r.body_offset_micrometers[2];
    let limits_match = l.limits_microradians == r.limits_microradians
        || (l.limits_microradians[0] == -r.limits_microradians[1]
            && l.limits_microradians[1] == -r.limits_microradians[0]);
    let inertia_matches = l
        .diagonal_inertia_nano_kg_m2
        .iter()
        .zip(r.diagonal_inertia_nano_kg_m2)
        .all(|(left, right)| left.abs_diff(right) <= (*left).max(right) / 1_000);
    if l.kind != r.kind
        || l.mass_milligrams != r.mass_milligrams
        || !inertia_matches
        || l.max_torque_millinewton_m != r.max_torque_millinewton_m
        || !offsets_match
        || !limits_match
    {
        return Err(G1ModelError::BilateralMismatch(left, right));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pinned_model_passes_all_invariants() {
        assert_eq!(validate_g1_articulation(), Ok(()));
        assert_eq!(G1_NODES.len(), 34);
        assert_eq!(
            G1_NODES
                .iter()
                .filter(|node| node.kind != G1NodeKind::VirtualMarker)
                .count(),
            30
        );
        assert_eq!(
            G1_NODES
                .iter()
                .filter(|node| node.kind == G1NodeKind::VirtualMarker)
                .count(),
            4
        );
    }

    #[test]
    fn topology_matches_official_g1_skeleton34_order() {
        let parents: [i8; 34] = [
            -1, 0, 1, 2, 3, 4, 5, 6, 0, 8, 9, 10, 11, 12, 13, 0, 15, 16, 17, 18, 19, 20, 21, 22,
            23, 24, 17, 26, 27, 28, 29, 30, 31, 32,
        ];
        assert_eq!(G1_NODES.map(|node| node.parent_index), parents);
        assert_eq!(G1_NODES[7].name, "left_toe_base");
        assert_eq!(G1_NODES[25].name, "left_hand_roll_skel");
        assert_eq!(G1_NODES[33].name, "right_hand_roll_skel");
    }

    #[test]
    fn physical_receipts_match_official_mjcf() {
        assert_eq!(G1_TOTAL_MASS_MILLIGRAMS, 33341142);
        assert_eq!(G1_NODES[0].mass_milligrams, 3_813_000);
        assert_eq!(G1_NODES[17].mass_milligrams, 7_818_000);
        assert_eq!(G1_NODES[4].max_torque_millinewton_m, 139_000);
        assert_eq!(G1_NODES[24].max_torque_millinewton_m, 5_000);
        assert_eq!(G1_NODES[7].kind, G1NodeKind::VirtualMarker);
    }

    #[test]
    fn provenance_is_immutable_and_explicit() {
        assert_eq!(G1_SOURCE_COMMIT.len(), 40);
        assert_eq!(G1_SKELETON_SHA256.len(), 64);
        assert_eq!(G1_MJCF_SHA256.len(), 64);
    }
}
