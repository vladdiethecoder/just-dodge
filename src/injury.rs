//! Deterministic anatomical injury truth.
//!
//! This module is the authoritative 60 Hz injury layer.  It deliberately stores
//! no region health bars and no floating point state: hitbox geometry is
//! quantized at the boundary, then fixed-point integers, stable structure IDs,
//! sorted active sets, and explicit cadence counters carry the simulation.
//!
//! P0 seeds 64 anatomically typed structures.  The schema and IDs are the
//! canonical extensibility contract for the eventual 500--1,000 structure atlas;
//! adding structures must append stable IDs rather than repurpose an existing ID.

use crate::hitbox::{ContactGeometry, DamageType};

pub const TRUTH_HZ: u32 = 60;
pub const HEMORRHAGE_DIVISOR: u32 = 2;
pub const SHOCK_DIVISOR: u32 = 4;
pub const STRUCTURE_COUNT: usize = 64;
pub const CANONICAL_ATLAS_TARGET_MIN: usize = 500;
pub const STATE_MAX_Q: u16 = 1_000;
pub const NORMAL_Q15_MAX: i16 = 32_767;
pub const MAX_DEFORMATION_MODES: usize = 4;
const ACTIVE_WORDS: usize = STRUCTURE_COUNT.div_ceil(64);
const INITIAL_BLOOD_Q: u32 = 5_000;

/// A stable, append-only canonical identifier.  It is never a broad body region.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[repr(transparent)]
pub struct StructureId(pub u16);

impl StructureId {
    pub const HEAD_SKIN: Self = Self(0);
    pub const SKULL: Self = Self(1);
    pub const BRAIN: Self = Self(2);
    pub const NECK_MUSCLE: Self = Self(3);
    pub const LEFT_CAROTID: Self = Self(4);
    pub const CERVICAL_NERVE: Self = Self(5);
    pub const THORAX_SKIN: Self = Self(6);
    pub const THORAX_FAT: Self = Self(7);
    pub const THORAX_FASCIA: Self = Self(8);
    pub const RIB_CAGE: Self = Self(9);
    pub const HEART: Self = Self(10);
    pub const LUNGS: Self = Self(11);
    pub const AORTA: Self = Self(12);
    pub const THORACIC_SPINE: Self = Self(13);
    pub const SPINAL_CORD: Self = Self(14);
    pub const PELVIS: Self = Self(15);
    pub const LEFT_ARM_SKIN: Self = Self(16);
    pub const LEFT_ARM_MUSCLE: Self = Self(17);
    pub const LEFT_HUMERUS: Self = Self(18);
    pub const LEFT_ELBOW: Self = Self(19);
    pub const LEFT_RADIUS_ULNA: Self = Self(20);
    pub const LEFT_BRACHIAL_VESSEL: Self = Self(21);
    pub const LEFT_MEDIAN_NERVE: Self = Self(22);
    pub const LEFT_HAND: Self = Self(23);
    pub const RIGHT_ARM_SKIN: Self = Self(24);
    pub const RIGHT_ARM_MUSCLE: Self = Self(25);
    pub const RIGHT_HUMERUS: Self = Self(26);
    pub const RIGHT_ELBOW: Self = Self(27);
    pub const RIGHT_RADIUS_ULNA: Self = Self(28);
    pub const RIGHT_BRACHIAL_VESSEL: Self = Self(29);
    pub const RIGHT_MEDIAN_NERVE: Self = Self(30);
    pub const RIGHT_HAND: Self = Self(31);
    pub const LEFT_LEG_SKIN: Self = Self(32);
    pub const LEFT_LEG_MUSCLE: Self = Self(33);
    pub const LEFT_FEMUR: Self = Self(34);
    pub const LEFT_KNEE: Self = Self(35);
    pub const LEFT_TIBIA: Self = Self(36);
    pub const LEFT_FEMORAL_VESSEL: Self = Self(37);
    pub const LEFT_SCIATIC_NERVE: Self = Self(38);
    pub const LEFT_FOOT: Self = Self(39);
    pub const RIGHT_LEG_SKIN: Self = Self(40);
    pub const RIGHT_LEG_MUSCLE: Self = Self(41);
    pub const RIGHT_FEMUR: Self = Self(42);
    pub const RIGHT_KNEE: Self = Self(43);
    pub const RIGHT_TIBIA: Self = Self(44);
    pub const RIGHT_FEMORAL_VESSEL: Self = Self(45);
    pub const RIGHT_SCIATIC_NERVE: Self = Self(46);
    pub const RIGHT_FOOT: Self = Self(47);
    pub const LIVER: Self = Self(48);
    pub const LEFT_KIDNEY: Self = Self(49);
    pub const RIGHT_KIDNEY: Self = Self(50);
    pub const SPLEEN: Self = Self(51);
    pub const STOMACH: Self = Self(52);
    pub const DIAPHRAGM: Self = Self(53);
    pub const LEFT_CLAVICLE: Self = Self(54);
    pub const RIGHT_CLAVICLE: Self = Self(55);
    pub const STERNUM: Self = Self(56);
    pub const LUMBAR_MUSCLE: Self = Self(57);
    pub const LEFT_ULNAR_NERVE: Self = Self(58);
    pub const RIGHT_ULNAR_NERVE: Self = Self(59);
    pub const LEFT_RADIAL_VESSEL: Self = Self(60);
    pub const RIGHT_RADIAL_VESSEL: Self = Self(61);
    pub const LEFT_ANKLE: Self = Self(62);
    pub const RIGHT_ANKLE: Self = Self(63);

    pub const fn index(self) -> usize {
        self.0 as usize
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum StructureKind {
    Skin,
    Fat,
    Fascia,
    Muscle,
    Bone,
    Joint,
    Vessel,
    Nerve,
    Organ,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum MaterialLaw {
    Dermal,
    Adipose,
    Fascia,
    Muscle,
    CorticalBone,
    Joint,
    VesselWall,
    NerveFascicle,
    OrganParenchyma,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BodySide {
    Center,
    Left,
    Right,
}

/// Immutable atlas definition.  `adjacency` is a typed local propagation graph;
/// only the first `adjacency_len` entries are populated and they are ordered by
/// stable ID for deterministic wake and traversal.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StructureDef {
    pub id: StructureId,
    pub parent: Option<StructureId>,
    pub kind: StructureKind,
    pub material: MaterialLaw,
    pub side: BodySide,
    pub adjacency: [StructureId; 4],
    pub adjacency_len: u8,
}

const fn def(
    id: u16,
    parent: Option<u16>,
    kind: StructureKind,
    material: MaterialLaw,
    side: BodySide,
    adjacency: [u16; 4],
    adjacency_len: u8,
) -> StructureDef {
    StructureDef {
        id: StructureId(id),
        parent: match parent {
            Some(parent) => Some(StructureId(parent)),
            None => None,
        },
        kind,
        material,
        side,
        adjacency: [
            StructureId(adjacency[0]),
            StructureId(adjacency[1]),
            StructureId(adjacency[2]),
            StructureId(adjacency[3]),
        ],
        adjacency_len,
    }
}

/// P0 stable atlas.  It is deliberately not a region-HP table: every entry is
/// a concrete anatomical layer, junction, conduit, or organ.
pub static STRUCTURE_ATLAS: [StructureDef; STRUCTURE_COUNT] = [
    def(
        0,
        None,
        StructureKind::Skin,
        MaterialLaw::Dermal,
        BodySide::Center,
        [1, 3, 4, 5],
        4,
    ),
    def(
        1,
        Some(0),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Center,
        [0, 2, 5, 13],
        4,
    ),
    def(
        2,
        Some(1),
        StructureKind::Organ,
        MaterialLaw::OrganParenchyma,
        BodySide::Center,
        [1, 5, 13, 14],
        4,
    ),
    def(
        3,
        Some(0),
        StructureKind::Muscle,
        MaterialLaw::Muscle,
        BodySide::Center,
        [0, 4, 5, 13],
        4,
    ),
    def(
        4,
        Some(3),
        StructureKind::Vessel,
        MaterialLaw::VesselWall,
        BodySide::Left,
        [0, 3, 5, 12],
        4,
    ),
    def(
        5,
        Some(3),
        StructureKind::Nerve,
        MaterialLaw::NerveFascicle,
        BodySide::Center,
        [1, 2, 3, 14],
        4,
    ),
    def(
        6,
        Some(15),
        StructureKind::Skin,
        MaterialLaw::Dermal,
        BodySide::Center,
        [7, 8, 9, 56],
        4,
    ),
    def(
        7,
        Some(6),
        StructureKind::Fat,
        MaterialLaw::Adipose,
        BodySide::Center,
        [6, 8, 9, 10],
        4,
    ),
    def(
        8,
        Some(7),
        StructureKind::Fascia,
        MaterialLaw::Fascia,
        BodySide::Center,
        [6, 7, 9, 10],
        4,
    ),
    def(
        9,
        Some(8),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Center,
        [6, 8, 10, 11],
        4,
    ),
    def(
        10,
        Some(9),
        StructureKind::Organ,
        MaterialLaw::OrganParenchyma,
        BodySide::Center,
        [9, 11, 12, 56],
        4,
    ),
    def(
        11,
        Some(9),
        StructureKind::Organ,
        MaterialLaw::OrganParenchyma,
        BodySide::Center,
        [9, 10, 12, 53],
        4,
    ),
    def(
        12,
        Some(9),
        StructureKind::Vessel,
        MaterialLaw::VesselWall,
        BodySide::Center,
        [4, 10, 11, 13],
        4,
    ),
    def(
        13,
        Some(15),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Center,
        [1, 5, 12, 14],
        4,
    ),
    def(
        14,
        Some(13),
        StructureKind::Nerve,
        MaterialLaw::NerveFascicle,
        BodySide::Center,
        [2, 5, 13, 57],
        4,
    ),
    def(
        15,
        None,
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Center,
        [6, 13, 34, 42],
        4,
    ),
    def(
        16,
        Some(54),
        StructureKind::Skin,
        MaterialLaw::Dermal,
        BodySide::Left,
        [17, 18, 21, 22],
        4,
    ),
    def(
        17,
        Some(16),
        StructureKind::Muscle,
        MaterialLaw::Muscle,
        BodySide::Left,
        [16, 18, 21, 22],
        4,
    ),
    def(
        18,
        Some(54),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Left,
        [17, 19, 20, 54],
        4,
    ),
    def(
        19,
        Some(18),
        StructureKind::Joint,
        MaterialLaw::Joint,
        BodySide::Left,
        [18, 20, 22, 23],
        4,
    ),
    def(
        20,
        Some(19),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Left,
        [18, 19, 22, 23],
        4,
    ),
    def(
        21,
        Some(17),
        StructureKind::Vessel,
        MaterialLaw::VesselWall,
        BodySide::Left,
        [16, 17, 20, 60],
        4,
    ),
    def(
        22,
        Some(17),
        StructureKind::Nerve,
        MaterialLaw::NerveFascicle,
        BodySide::Left,
        [17, 19, 20, 58],
        4,
    ),
    def(
        23,
        Some(20),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Left,
        [19, 20, 22, 58],
        4,
    ),
    def(
        24,
        Some(55),
        StructureKind::Skin,
        MaterialLaw::Dermal,
        BodySide::Right,
        [25, 26, 29, 30],
        4,
    ),
    def(
        25,
        Some(24),
        StructureKind::Muscle,
        MaterialLaw::Muscle,
        BodySide::Right,
        [24, 26, 29, 30],
        4,
    ),
    def(
        26,
        Some(55),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Right,
        [25, 27, 28, 55],
        4,
    ),
    def(
        27,
        Some(26),
        StructureKind::Joint,
        MaterialLaw::Joint,
        BodySide::Right,
        [26, 28, 30, 31],
        4,
    ),
    def(
        28,
        Some(27),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Right,
        [26, 27, 30, 31],
        4,
    ),
    def(
        29,
        Some(25),
        StructureKind::Vessel,
        MaterialLaw::VesselWall,
        BodySide::Right,
        [24, 25, 28, 61],
        4,
    ),
    def(
        30,
        Some(25),
        StructureKind::Nerve,
        MaterialLaw::NerveFascicle,
        BodySide::Right,
        [25, 27, 28, 59],
        4,
    ),
    def(
        31,
        Some(28),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Right,
        [27, 28, 30, 59],
        4,
    ),
    def(
        32,
        Some(15),
        StructureKind::Skin,
        MaterialLaw::Dermal,
        BodySide::Left,
        [33, 34, 37, 38],
        4,
    ),
    def(
        33,
        Some(32),
        StructureKind::Muscle,
        MaterialLaw::Muscle,
        BodySide::Left,
        [32, 34, 37, 38],
        4,
    ),
    def(
        34,
        Some(15),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Left,
        [33, 35, 36, 37],
        4,
    ),
    def(
        35,
        Some(34),
        StructureKind::Joint,
        MaterialLaw::Joint,
        BodySide::Left,
        [34, 36, 38, 39],
        4,
    ),
    def(
        36,
        Some(35),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Left,
        [34, 35, 38, 62],
        4,
    ),
    def(
        37,
        Some(33),
        StructureKind::Vessel,
        MaterialLaw::VesselWall,
        BodySide::Left,
        [32, 33, 34, 38],
        4,
    ),
    def(
        38,
        Some(33),
        StructureKind::Nerve,
        MaterialLaw::NerveFascicle,
        BodySide::Left,
        [33, 35, 36, 62],
        4,
    ),
    def(
        39,
        Some(36),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Left,
        [35, 36, 38, 62],
        4,
    ),
    def(
        40,
        Some(15),
        StructureKind::Skin,
        MaterialLaw::Dermal,
        BodySide::Right,
        [41, 42, 45, 46],
        4,
    ),
    def(
        41,
        Some(40),
        StructureKind::Muscle,
        MaterialLaw::Muscle,
        BodySide::Right,
        [40, 42, 45, 46],
        4,
    ),
    def(
        42,
        Some(15),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Right,
        [41, 43, 44, 45],
        4,
    ),
    def(
        43,
        Some(42),
        StructureKind::Joint,
        MaterialLaw::Joint,
        BodySide::Right,
        [42, 44, 46, 47],
        4,
    ),
    def(
        44,
        Some(43),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Right,
        [42, 43, 46, 63],
        4,
    ),
    def(
        45,
        Some(41),
        StructureKind::Vessel,
        MaterialLaw::VesselWall,
        BodySide::Right,
        [40, 41, 42, 46],
        4,
    ),
    def(
        46,
        Some(41),
        StructureKind::Nerve,
        MaterialLaw::NerveFascicle,
        BodySide::Right,
        [41, 43, 44, 63],
        4,
    ),
    def(
        47,
        Some(44),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Right,
        [43, 44, 46, 63],
        4,
    ),
    def(
        48,
        Some(15),
        StructureKind::Organ,
        MaterialLaw::OrganParenchyma,
        BodySide::Right,
        [12, 49, 50, 52],
        4,
    ),
    def(
        49,
        Some(15),
        StructureKind::Organ,
        MaterialLaw::OrganParenchyma,
        BodySide::Left,
        [12, 48, 50, 57],
        4,
    ),
    def(
        50,
        Some(15),
        StructureKind::Organ,
        MaterialLaw::OrganParenchyma,
        BodySide::Right,
        [12, 48, 49, 57],
        4,
    ),
    def(
        51,
        Some(15),
        StructureKind::Organ,
        MaterialLaw::OrganParenchyma,
        BodySide::Left,
        [12, 48, 52, 53],
        4,
    ),
    def(
        52,
        Some(15),
        StructureKind::Organ,
        MaterialLaw::OrganParenchyma,
        BodySide::Center,
        [12, 48, 51, 53],
        4,
    ),
    def(
        53,
        Some(9),
        StructureKind::Muscle,
        MaterialLaw::Muscle,
        BodySide::Center,
        [9, 11, 51, 52],
        4,
    ),
    def(
        54,
        Some(56),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Left,
        [16, 18, 19, 56],
        4,
    ),
    def(
        55,
        Some(56),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Right,
        [24, 26, 27, 56],
        4,
    ),
    def(
        56,
        Some(9),
        StructureKind::Bone,
        MaterialLaw::CorticalBone,
        BodySide::Center,
        [6, 9, 10, 54],
        4,
    ),
    def(
        57,
        Some(13),
        StructureKind::Muscle,
        MaterialLaw::Muscle,
        BodySide::Center,
        [13, 14, 49, 50],
        4,
    ),
    def(
        58,
        Some(22),
        StructureKind::Nerve,
        MaterialLaw::NerveFascicle,
        BodySide::Left,
        [20, 22, 23, 60],
        4,
    ),
    def(
        59,
        Some(30),
        StructureKind::Nerve,
        MaterialLaw::NerveFascicle,
        BodySide::Right,
        [28, 30, 31, 61],
        4,
    ),
    def(
        60,
        Some(21),
        StructureKind::Vessel,
        MaterialLaw::VesselWall,
        BodySide::Left,
        [20, 21, 22, 58],
        4,
    ),
    def(
        61,
        Some(29),
        StructureKind::Vessel,
        MaterialLaw::VesselWall,
        BodySide::Right,
        [28, 29, 30, 59],
        4,
    ),
    def(
        62,
        Some(36),
        StructureKind::Joint,
        MaterialLaw::Joint,
        BodySide::Left,
        [36, 38, 39, 35],
        4,
    ),
    def(
        63,
        Some(44),
        StructureKind::Joint,
        MaterialLaw::Joint,
        BodySide::Right,
        [43, 44, 46, 47],
        4,
    ),
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StructureFlags(u16);

impl StructureFlags {
    pub const NONE: Self = Self(0);
    pub const FRACTURED: Self = Self(1 << 0);
    pub const LACERATED: Self = Self(1 << 1);
    pub const VESSEL_SEVERED: Self = Self(1 << 2);
    pub const NERVE_TRANSECTED: Self = Self(1 << 3);
    pub const ORGAN_RUPTURED: Self = Self(1 << 4);

    pub const fn contains(self, flag: Self) -> bool {
        self.0 & flag.0 != 0
    }

    const fn insert(&mut self, flag: Self) {
        self.0 |= flag.0;
    }

    const fn bits(self) -> u16 {
        self.0
    }
}

/// Mutable fixed-point state for one concrete atlas structure.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StructureState {
    pub integrity_q: u16,
    pub strain_q: i16,
    pub deformation_modes_q: [i16; MAX_DEFORMATION_MODES],
    pub perfusion_q: u16,
    pub neural_conduction_q: u16,
    pub blood_loss_q: u16,
    pub flags: StructureFlags,
}

impl Default for StructureState {
    fn default() -> Self {
        Self {
            integrity_q: STATE_MAX_Q,
            strain_q: 0,
            deformation_modes_q: [0; MAX_DEFORMATION_MODES],
            perfusion_q: STATE_MAX_Q,
            neural_conduction_q: STATE_MAX_Q,
            blood_loss_q: 0,
            flags: StructureFlags::NONE,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContactMaterial {
    Blunt,
    Edge,
    Point,
}

impl From<DamageType> for ContactMaterial {
    fn from(value: DamageType) -> Self {
        match value {
            DamageType::Bash => Self::Blunt,
            DamageType::Slash => Self::Edge,
            DamageType::Pierce => Self::Point,
        }
    }
}

/// Float-free contact boundary.  Positions/depth/normals are quantized before
/// this enters truth; impact and area are supplied by the deterministic physics
/// solver in millinewtons and square millimetres.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct QuantizedContactGeometry {
    pub point_mm: [i32; 3],
    pub normal_q15: [i16; 3],
    pub penetration_mm: u16,
    pub time_of_impact_q16: u16,
    pub attacker_proxy: u16,
    pub defender_proxy: u16,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct InjuryContact {
    pub geometry: QuantizedContactGeometry,
    pub target: StructureId,
    pub material: ContactMaterial,
    pub impulse_mn: u32,
    pub contact_area_mm2: u32,
    pub edge_alignment_q15: i16,
}

impl InjuryContact {
    /// Quantize renderer/physics geometry at the injury authority boundary.
    /// The returned value contains no platform float state.
    pub fn from_contact_geometry(
        geometry: &ContactGeometry,
        target: StructureId,
        material: ContactMaterial,
        impulse_mn: u32,
        contact_area_mm2: u32,
        edge_alignment_q15: i16,
    ) -> Self {
        Self {
            geometry: QuantizedContactGeometry {
                point_mm: [
                    quantize_mm(geometry.point.x),
                    quantize_mm(geometry.point.y),
                    quantize_mm(geometry.point.z),
                ],
                normal_q15: [
                    quantize_normal(geometry.normal.x),
                    quantize_normal(geometry.normal.y),
                    quantize_normal(geometry.normal.z),
                ],
                penetration_mm: quantize_depth_mm(geometry.depth),
                time_of_impact_q16: quantize_unit_q16(geometry.time_of_impact),
                attacker_proxy: geometry.attacker_proxy.min(u16::MAX as usize) as u16,
                defender_proxy: geometry.defender_proxy.min(u16::MAX as usize) as u16,
            },
            target,
            material,
            impulse_mn,
            contact_area_mm2: contact_area_mm2.max(1),
            edge_alignment_q15: edge_alignment_q15.clamp(0, NORMAL_Q15_MAX),
        }
    }

    /// Adapter for existing measured body proxy contacts.  The proxy mapping is
    /// only a deterministic acceleration choice; the resulting injury unit is a
    /// concrete atlas ID and adjacent layers are then causally activated.
    pub fn from_proxy_contact(
        geometry: &ContactGeometry,
        material: ContactMaterial,
        impulse_mn: u32,
        contact_area_mm2: u32,
        edge_alignment_q15: i16,
    ) -> Self {
        let target = proxy_target(geometry.defender_proxy);
        Self::from_contact_geometry(
            geometry,
            target,
            material,
            impulse_mn,
            contact_area_mm2,
            edge_alignment_q15,
        )
    }
}

fn quantize_mm(value_m: f32) -> i32 {
    (value_m * 1_000.0)
        .round()
        .clamp(i32::MIN as f32, i32::MAX as f32) as i32
}

fn quantize_depth_mm(value_m: f32) -> u16 {
    (value_m.max(0.0) * 1_000.0)
        .round()
        .clamp(0.0, u16::MAX as f32) as u16
}

fn quantize_normal(value: f32) -> i16 {
    (value * NORMAL_Q15_MAX as f32)
        .round()
        .clamp(-(NORMAL_Q15_MAX as f32), NORMAL_Q15_MAX as f32) as i16
}

fn quantize_unit_q16(value: f32) -> u16 {
    (value.clamp(0.0, 1.0) * u16::MAX as f32).round() as u16
}

fn proxy_target(proxy: usize) -> StructureId {
    match proxy {
        0 | 9..=11 => StructureId::THORAX_SKIN,
        1 | 2 => StructureId::LEFT_LEG_SKIN,
        5 | 6 => StructureId::RIGHT_LEG_SKIN,
        12..=15 => StructureId::LEFT_ARM_SKIN,
        16..=19 => StructureId::RIGHT_ARM_SKIN,
        20..=23 => StructureId::HEAD_SKIN,
        _ => StructureId::THORAX_SKIN,
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PhysiologicalEvent {
    Fracture { structure: StructureId },
    VesselSevered { structure: StructureId },
    NerveTransected { structure: StructureId },
    OrganRuptured { structure: StructureId },
    Hemorrhage { structure: StructureId, loss_q: u16 },
    Incapacitated,
}

/// Intent capabilities deliberately name limb ownership instead of making a
/// single generic arm stat hide action availability.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum AnatomyIntent {
    StrikeLeft,
    StrikeRight,
    GrabLeft,
    GrabRight,
    Block,
    Move,
    Dodge,
    Feint,
    Cancel,
    Idle,
}

pub const ALL_ANATOMY_INTENTS: [AnatomyIntent; 10] = [
    AnatomyIntent::StrikeLeft,
    AnatomyIntent::StrikeRight,
    AnatomyIntent::GrabLeft,
    AnatomyIntent::GrabRight,
    AnatomyIntent::Block,
    AnatomyIntent::Move,
    AnatomyIntent::Dodge,
    AnatomyIntent::Feint,
    AnatomyIntent::Cancel,
    AnatomyIntent::Idle,
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MotionKinematicsQ {
    pub momentum_q: [i16; 3],
    pub speed_mm_per_s: u16,
    pub velocity_mm_per_s: [i16; 3],
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct InjuryConditioning {
    /// Stable vector for motion conditioning.  Values are all quantized integers.
    pub values: [i16; 16],
}

/// Authoritative, sparse-active anatomy truth.  `structures` is dense canonical
/// state.  The sorted vector and bitset are only a deterministic working set.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FighterAnatomyTruth {
    pub structures: Box<[StructureState]>,
    pub active_ids: Vec<StructureId>,
    pub active_bits: [u64; ACTIVE_WORDS],
    pub circulating_blood_q: u32,
    pub shock_q: u16,
    pub consciousness_q: u16,
    pub truth_tick: u32,
    pub incapacitated: bool,
    events: Vec<PhysiologicalEvent>,
}

/// Replay snapshot contains all hash-relevant canonical state.  It is a
/// copyable, serialization-ready fixed-point boundary without presentation data.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AnatomySnapshot {
    pub structures: Box<[StructureState]>,
    pub active_ids: Vec<StructureId>,
    pub active_bits: [u64; ACTIVE_WORDS],
    pub circulating_blood_q: u32,
    pub shock_q: u16,
    pub consciousness_q: u16,
    pub truth_tick: u32,
    pub incapacitated: bool,
}

impl Default for FighterAnatomyTruth {
    fn default() -> Self {
        Self::new()
    }
}

impl FighterAnatomyTruth {
    pub fn new() -> Self {
        Self {
            structures: vec![StructureState::default(); STRUCTURE_COUNT].into_boxed_slice(),
            active_ids: Vec::new(),
            active_bits: [0; ACTIVE_WORDS],
            circulating_blood_q: INITIAL_BLOOD_Q,
            shock_q: 0,
            consciousness_q: STATE_MAX_Q,
            truth_tick: 0,
            incapacitated: false,
            events: Vec::new(),
        }
    }

    pub fn state(&self, id: StructureId) -> &StructureState {
        &self.structures[id.index()]
    }

    pub fn events(&self) -> &[PhysiologicalEvent] {
        &self.events
    }

    pub fn snapshot(&self) -> AnatomySnapshot {
        AnatomySnapshot {
            structures: self.structures.clone(),
            active_ids: self.active_ids.clone(),
            active_bits: self.active_bits,
            circulating_blood_q: self.circulating_blood_q,
            shock_q: self.shock_q,
            consciousness_q: self.consciousness_q,
            truth_tick: self.truth_tick,
            incapacitated: self.incapacitated,
        }
    }

    pub fn restore(&mut self, snapshot: &AnatomySnapshot) {
        self.structures = snapshot.structures.clone();
        self.active_ids = snapshot.active_ids.clone();
        self.active_bits = snapshot.active_bits;
        self.circulating_blood_q = snapshot.circulating_blood_q;
        self.shock_q = snapshot.shock_q;
        self.consciousness_q = snapshot.consciousness_q;
        self.truth_tick = snapshot.truth_tick;
        self.incapacitated = snapshot.incapacitated;
        self.events.clear();
    }

    /// Contact/deformation stage at the mandatory 60 Hz truth cadence.
    pub fn apply_contact(&mut self, contact: InjuryContact) {
        self.events.clear();
        if contact.target.index() >= STRUCTURE_COUNT || self.incapacitated {
            return;
        }
        self.activate_with_adjacency(contact.target);
        let pressure_q = contact.impulse_mn / contact.contact_area_mm2;
        let damage_q = damage_from_contact(contact, pressure_q);
        self.apply_structure_damage(contact.target, damage_q, contact, pressure_q);
        self.apply_adjacency_strain(contact.target, damage_q);
        self.refresh_incapacitation();
    }

    /// Advance exactly one truth tick.  Directly active deformation runs at 60
    /// Hz, hemorrhage at 30 Hz, and shock/ischemia at 15 Hz.
    pub fn tick_60hz(&mut self) {
        self.events.clear();
        self.truth_tick = self.truth_tick.wrapping_add(1);
        self.integrate_deformation_60hz();
        if self.truth_tick.is_multiple_of(HEMORRHAGE_DIVISOR) {
            self.integrate_hemorrhage_30hz();
        }
        if self.truth_tick.is_multiple_of(SHOCK_DIVISOR) {
            self.integrate_shock_15hz();
        }
        self.refresh_incapacitation();
    }

    pub fn truth_hash(&self) -> u64 {
        fnv1a(&self.canonical_bytes())
    }

    /// Explicit byte layout used for replay hashes and serialization boundaries.
    pub fn canonical_bytes(&self) -> Vec<u8> {
        let mut bytes = Vec::with_capacity(STRUCTURE_COUNT * 18 + 128);
        bytes.extend_from_slice(&self.truth_tick.to_le_bytes());
        bytes.extend_from_slice(&self.circulating_blood_q.to_le_bytes());
        bytes.extend_from_slice(&self.shock_q.to_le_bytes());
        bytes.extend_from_slice(&self.consciousness_q.to_le_bytes());
        bytes.push(u8::from(self.incapacitated));
        for state in self.structures.iter() {
            bytes.extend_from_slice(&state.integrity_q.to_le_bytes());
            bytes.extend_from_slice(&state.strain_q.to_le_bytes());
            for mode in state.deformation_modes_q {
                bytes.extend_from_slice(&mode.to_le_bytes());
            }
            bytes.extend_from_slice(&state.perfusion_q.to_le_bytes());
            bytes.extend_from_slice(&state.neural_conduction_q.to_le_bytes());
            bytes.extend_from_slice(&state.blood_loss_q.to_le_bytes());
            bytes.extend_from_slice(&state.flags.bits().to_le_bytes());
        }
        for word in self.active_bits {
            bytes.extend_from_slice(&word.to_le_bytes());
        }
        bytes.extend_from_slice(&(self.active_ids.len() as u16).to_le_bytes());
        for id in &self.active_ids {
            bytes.extend_from_slice(&id.0.to_le_bytes());
        }
        bytes
    }

    /// Injury state as a compact, all-integer conditioning primitive for motion.
    /// It includes limb capability, shock/blood, and the supplied current
    /// momentum/speed/velocity rather than inventing motion from injury alone.
    pub fn conditioning(&self, motion: MotionKinematicsQ) -> InjuryConditioning {
        let left_arm = limb_quality(
            self,
            &[StructureId::LEFT_MEDIAN_NERVE, StructureId::LEFT_HUMERUS],
        );
        let right_arm = limb_quality(
            self,
            &[StructureId::RIGHT_MEDIAN_NERVE, StructureId::RIGHT_HUMERUS],
        );
        let left_leg = limb_quality(
            self,
            &[StructureId::LEFT_SCIATIC_NERVE, StructureId::LEFT_FEMUR],
        );
        let right_leg = limb_quality(
            self,
            &[StructureId::RIGHT_SCIATIC_NERVE, StructureId::RIGHT_FEMUR],
        );
        InjuryConditioning {
            values: [
                self.consciousness_q as i16,
                self.shock_q as i16,
                self.circulating_blood_q.min(i16::MAX as u32) as i16,
                left_arm,
                right_arm,
                left_leg,
                right_leg,
                motion.momentum_q[0],
                motion.momentum_q[1],
                motion.momentum_q[2],
                motion.speed_mm_per_s.min(i16::MAX as u16) as i16,
                motion.velocity_mm_per_s[0],
                motion.velocity_mm_per_s[1],
                motion.velocity_mm_per_s[2],
                self.state(StructureId::BRAIN).integrity_q as i16,
                u8::from(self.incapacitated) as i16,
            ],
        }
    }

    fn activate_with_adjacency(&mut self, id: StructureId) {
        self.activate(id);
        let definition = STRUCTURE_ATLAS[id.index()];
        for adjacent in definition
            .adjacency
            .into_iter()
            .take(definition.adjacency_len as usize)
        {
            self.activate(adjacent);
        }
    }

    fn activate(&mut self, id: StructureId) {
        let index = id.index();
        let word = index / 64;
        let bit = index % 64;
        if self.active_bits[word] & (1_u64 << bit) != 0 {
            return;
        }
        self.active_bits[word] |= 1_u64 << bit;
        let insertion = self.active_ids.binary_search(&id).unwrap_or_else(|at| at);
        self.active_ids.insert(insertion, id);
    }

    fn apply_structure_damage(
        &mut self,
        id: StructureId,
        damage_q: u16,
        contact: InjuryContact,
        pressure_q: u32,
    ) {
        let definition = STRUCTURE_ATLAS[id.index()];
        let cutting = matches!(
            contact.material,
            ContactMaterial::Edge | ContactMaterial::Point
        ) && contact.geometry.penetration_mm >= 2;
        let event = match definition.kind {
            StructureKind::Bone | StructureKind::Joint
                if contact.impulse_mn >= 120_000 && contact.geometry.penetration_mm >= 2 =>
            {
                let state = &mut self.structures[id.index()];
                state.integrity_q = state.integrity_q.saturating_sub(damage_q).min(300);
                state.strain_q = state.strain_q.saturating_add((damage_q / 2) as i16);
                state.deformation_modes_q[0] =
                    state.deformation_modes_q[0].saturating_add(damage_q as i16);
                if cutting {
                    state.flags.insert(StructureFlags::LACERATED);
                }
                state.flags.insert(StructureFlags::FRACTURED);
                Some(PhysiologicalEvent::Fracture { structure: id })
            }
            StructureKind::Vessel
                if cutting
                    && contact.edge_alignment_q15 >= 20_000
                    && (contact.geometry.penetration_mm >= 3 || pressure_q >= 25_000) =>
            {
                let state = &mut self.structures[id.index()];
                state.integrity_q = state.integrity_q.saturating_sub(damage_q).min(150);
                state.strain_q = state.strain_q.saturating_add((damage_q / 2) as i16);
                state.deformation_modes_q[0] =
                    state.deformation_modes_q[0].saturating_add(damage_q as i16);
                state.flags.insert(StructureFlags::LACERATED);
                state.flags.insert(StructureFlags::VESSEL_SEVERED);
                state.perfusion_q = state.perfusion_q.min(200);
                Some(PhysiologicalEvent::VesselSevered { structure: id })
            }
            StructureKind::Nerve
                if cutting
                    && contact.edge_alignment_q15 >= 18_000
                    && contact.geometry.penetration_mm >= 2 =>
            {
                let state = &mut self.structures[id.index()];
                state.integrity_q = state.integrity_q.saturating_sub(damage_q).min(200);
                state.strain_q = state.strain_q.saturating_add((damage_q / 2) as i16);
                state.deformation_modes_q[0] =
                    state.deformation_modes_q[0].saturating_add(damage_q as i16);
                state.flags.insert(StructureFlags::LACERATED);
                state.flags.insert(StructureFlags::NERVE_TRANSECTED);
                state.neural_conduction_q = 0;
                Some(PhysiologicalEvent::NerveTransected { structure: id })
            }
            StructureKind::Organ
                if (matches!(
                    contact.material,
                    ContactMaterial::Point | ContactMaterial::Edge
                ) && contact.geometry.penetration_mm >= 8
                    && contact.impulse_mn >= 50_000)
                    || (matches!(contact.material, ContactMaterial::Blunt)
                        && contact.impulse_mn >= 220_000
                        && pressure_q >= 40_000) =>
            {
                let state = &mut self.structures[id.index()];
                state.integrity_q = state.integrity_q.saturating_sub(damage_q).min(150);
                state.strain_q = state.strain_q.saturating_add((damage_q / 2) as i16);
                state.deformation_modes_q[0] =
                    state.deformation_modes_q[0].saturating_add(damage_q as i16);
                if cutting {
                    state.flags.insert(StructureFlags::LACERATED);
                }
                state.flags.insert(StructureFlags::ORGAN_RUPTURED);
                state.perfusion_q = state.perfusion_q.min(250);
                Some(PhysiologicalEvent::OrganRuptured { structure: id })
            }
            _ => {
                let state = &mut self.structures[id.index()];
                state.integrity_q = state.integrity_q.saturating_sub(damage_q);
                state.strain_q = state.strain_q.saturating_add((damage_q / 2) as i16);
                state.deformation_modes_q[0] =
                    state.deformation_modes_q[0].saturating_add(damage_q as i16);
                if cutting {
                    state.flags.insert(StructureFlags::LACERATED);
                }
                None
            }
        };
        if let Some(event) = event {
            self.events.push(event);
        }
    }

    fn apply_adjacency_strain(&mut self, id: StructureId, damage_q: u16) {
        let definition = STRUCTURE_ATLAS[id.index()];
        let transmitted = (damage_q / 8) as i16;
        for adjacent in definition
            .adjacency
            .into_iter()
            .take(definition.adjacency_len as usize)
        {
            let state = &mut self.structures[adjacent.index()];
            state.strain_q = state.strain_q.saturating_add(transmitted);
            state.deformation_modes_q[1] = state.deformation_modes_q[1].saturating_add(transmitted);
        }
    }

    fn integrate_deformation_60hz(&mut self) {
        for index in 0..self.active_ids.len() {
            let id = self.active_ids[index];
            let state = &mut self.structures[id.index()];
            state.strain_q = state.strain_q.saturating_sub(2);
            state.deformation_modes_q[0] = state.deformation_modes_q[0].saturating_sub(1);
        }
    }

    fn integrate_hemorrhage_30hz(&mut self) {
        for index in 0..self.active_ids.len() {
            let id = self.active_ids[index];
            let state = &mut self.structures[id.index()];
            let loss = if state.flags.contains(StructureFlags::VESSEL_SEVERED) {
                180
            } else if state.flags.contains(StructureFlags::ORGAN_RUPTURED) {
                120
            } else {
                0
            };
            if loss == 0 {
                continue;
            }
            state.blood_loss_q = state.blood_loss_q.saturating_add(loss);
            state.perfusion_q = state.perfusion_q.saturating_sub(loss / 4);
            self.circulating_blood_q = self.circulating_blood_q.saturating_sub(loss as u32);
            self.events.push(PhysiologicalEvent::Hemorrhage {
                structure: id,
                loss_q: loss,
            });
        }
    }

    fn integrate_shock_15hz(&mut self) {
        let blood_deficit = INITIAL_BLOOD_Q.saturating_sub(self.circulating_blood_q) as u16;
        let ischemia = self
            .active_ids
            .iter()
            .map(|id| STATE_MAX_Q.saturating_sub(self.structures[id.index()].perfusion_q))
            .max()
            .unwrap_or(0);
        self.shock_q = self
            .shock_q
            .saturating_add((blood_deficit / 20).saturating_add(ischemia / 100))
            .min(STATE_MAX_Q);
        let consciousness_loss = self.shock_q / 16 + blood_deficit / 100;
        self.consciousness_q = self.consciousness_q.saturating_sub(consciousness_loss);
    }

    fn refresh_incapacitation(&mut self) {
        let vital_destroyed = [StructureId::BRAIN, StructureId::HEART]
            .into_iter()
            .any(|id| self.state(id).integrity_q <= 200);
        let now_incapacitated = vital_destroyed
            || self.circulating_blood_q <= 1_500
            || self.shock_q >= 800
            || self.consciousness_q <= 200;
        if now_incapacitated && !self.incapacitated {
            self.incapacitated = true;
            self.events.push(PhysiologicalEvent::Incapacitated);
        }
    }
}

fn damage_from_contact(contact: InjuryContact, pressure_q: u32) -> u16 {
    let impulse = (contact.impulse_mn / 500).min(700) as u16;
    let pressure = (pressure_q / 1_000).min(200) as u16;
    let penetration = contact.geometry.penetration_mm.saturating_mul(10).min(300);
    let edge = if matches!(
        contact.material,
        ContactMaterial::Edge | ContactMaterial::Point
    ) {
        (contact.edge_alignment_q15 as u16 / 164).min(200)
    } else {
        0
    };
    impulse
        .saturating_add(pressure)
        .saturating_add(penetration)
        .saturating_add(edge)
}

fn limb_quality(truth: &FighterAnatomyTruth, ids: &[StructureId]) -> i16 {
    ids.iter()
        .map(|id| {
            let state = truth.state(*id);
            state.integrity_q.min(state.neural_conduction_q) as i16
        })
        .min()
        .unwrap_or(STATE_MAX_Q as i16)
}

/// Capability rules:
/// - transected/unconductive arm nerve, or a severe humerus/forearm fracture,
///   removes that arm's Strike and Grab intents;
/// - severe femur/tibia fracture or sciatic loss removes Move and Dodge;
/// - global shock/consciousness loss leaves only Idle/Cancel as the fighter is
///   approaching incapacitation; actual incapacitation exposes no intents.
pub fn available_intents(truth: &FighterAnatomyTruth) -> Vec<AnatomyIntent> {
    if is_incapacitated(truth) {
        return Vec::new();
    }
    let left_arm_disabled = arm_disabled(
        truth,
        StructureId::LEFT_MEDIAN_NERVE,
        StructureId::LEFT_HUMERUS,
        StructureId::LEFT_RADIUS_ULNA,
    );
    let right_arm_disabled = arm_disabled(
        truth,
        StructureId::RIGHT_MEDIAN_NERVE,
        StructureId::RIGHT_HUMERUS,
        StructureId::RIGHT_RADIUS_ULNA,
    );
    let leg_disabled = leg_disabled(
        truth,
        StructureId::LEFT_SCIATIC_NERVE,
        StructureId::LEFT_FEMUR,
        StructureId::LEFT_TIBIA,
    ) || leg_disabled(
        truth,
        StructureId::RIGHT_SCIATIC_NERVE,
        StructureId::RIGHT_FEMUR,
        StructureId::RIGHT_TIBIA,
    );
    if truth.shock_q >= 650 || truth.consciousness_q <= 350 {
        return vec![AnatomyIntent::Cancel, AnatomyIntent::Idle];
    }
    ALL_ANATOMY_INTENTS
        .into_iter()
        .filter(|intent| match intent {
            AnatomyIntent::StrikeLeft | AnatomyIntent::GrabLeft => !left_arm_disabled,
            AnatomyIntent::StrikeRight | AnatomyIntent::GrabRight => !right_arm_disabled,
            AnatomyIntent::Move | AnatomyIntent::Dodge => !leg_disabled,
            AnatomyIntent::Block
            | AnatomyIntent::Feint
            | AnatomyIntent::Cancel
            | AnatomyIntent::Idle => true,
        })
        .collect()
}

pub fn is_incapacitated(truth: &FighterAnatomyTruth) -> bool {
    truth.incapacitated
}

fn arm_disabled(
    truth: &FighterAnatomyTruth,
    nerve: StructureId,
    upper: StructureId,
    forearm: StructureId,
) -> bool {
    let nerve = truth.state(nerve);
    nerve.flags.contains(StructureFlags::NERVE_TRANSECTED)
        || nerve.neural_conduction_q <= 200
        || truth.state(upper).flags.contains(StructureFlags::FRACTURED)
        || truth
            .state(forearm)
            .flags
            .contains(StructureFlags::FRACTURED)
}

fn leg_disabled(
    truth: &FighterAnatomyTruth,
    nerve: StructureId,
    femur: StructureId,
    tibia: StructureId,
) -> bool {
    let nerve = truth.state(nerve);
    nerve.flags.contains(StructureFlags::NERVE_TRANSECTED)
        || nerve.neural_conduction_q <= 200
        || truth.state(femur).flags.contains(StructureFlags::FRACTURED)
        || truth.state(tibia).flags.contains(StructureFlags::FRACTURED)
}

const FNV_OFFSET: u64 = 0xcbf29ce484222325;
const FNV_PRIME: u64 = 0x0100000001b3;
fn fnv1a(bytes: &[u8]) -> u64 {
    bytes.iter().fold(FNV_OFFSET, |hash, byte| {
        (hash ^ u64::from(*byte)).wrapping_mul(FNV_PRIME)
    })
}

#[cfg(test)]
mod tests {
    use glam::{Vec3, vec3};

    use super::*;

    fn geometry(depth: f32) -> ContactGeometry {
        ContactGeometry {
            point: vec3(0.10, 1.20, -0.30),
            normal: Vec3::X,
            depth,
            time_of_impact: 0.25,
            attacker_proxy: 7,
            defender_proxy: 3,
        }
    }

    fn contact(
        target: StructureId,
        material: ContactMaterial,
        impulse_mn: u32,
        penetration_m: f32,
    ) -> InjuryContact {
        InjuryContact::from_contact_geometry(
            &geometry(penetration_m),
            target,
            material,
            impulse_mn,
            2,
            NORMAL_Q15_MAX,
        )
    }

    #[test]
    fn atlas_is_stable_typed_and_not_a_region_hp_table() {
        assert_eq!(STRUCTURE_ATLAS.len(), STRUCTURE_COUNT);
        for (index, definition) in STRUCTURE_ATLAS.iter().enumerate() {
            assert_eq!(definition.id.index(), index);
            assert!(definition.adjacency_len <= 4);
        }
        assert!(
            STRUCTURE_ATLAS
                .iter()
                .any(|entry| entry.kind == StructureKind::Fat)
        );
        assert!(
            STRUCTURE_ATLAS
                .iter()
                .any(|entry| entry.kind == StructureKind::Fascia)
        );
        assert!(
            STRUCTURE_ATLAS
                .iter()
                .any(|entry| entry.kind == StructureKind::Vessel)
        );
        assert!(
            STRUCTURE_ATLAS
                .iter()
                .any(|entry| entry.kind == StructureKind::Nerve)
        );
        assert!(
            STRUCTURE_ATLAS
                .iter()
                .any(|entry| entry.kind == StructureKind::Organ)
        );
    }

    #[test]
    fn identical_quantized_contacts_hash_identically_across_one_hundred_runs() {
        let sequence = [
            contact(
                StructureId::LEFT_HUMERUS,
                ContactMaterial::Blunt,
                150_000,
                0.004,
            ),
            contact(
                StructureId::LEFT_BRACHIAL_VESSEL,
                ContactMaterial::Edge,
                80_000,
                0.006,
            ),
            contact(
                StructureId::RIGHT_MEDIAN_NERVE,
                ContactMaterial::Edge,
                70_000,
                0.004,
            ),
            contact(StructureId::LIVER, ContactMaterial::Point, 80_000, 0.010),
        ];
        let mut hashes = Vec::new();
        for _ in 0..100 {
            let mut truth = FighterAnatomyTruth::new();
            for event in sequence {
                truth.apply_contact(event);
                for _ in 0..8 {
                    truth.tick_60hz();
                }
            }
            hashes.push(truth.truth_hash());
        }
        assert!(hashes.windows(2).all(|pair| pair[0] == pair[1]));
    }

    #[test]
    fn geometry_and_material_produce_distinct_injury_classes() {
        let mut truth = FighterAnatomyTruth::new();
        truth.apply_contact(contact(
            StructureId::LEFT_FEMUR,
            ContactMaterial::Blunt,
            150_000,
            0.004,
        ));
        assert!(
            truth
                .state(StructureId::LEFT_FEMUR)
                .flags
                .contains(StructureFlags::FRACTURED)
        );

        truth.apply_contact(contact(
            StructureId::LEFT_BRACHIAL_VESSEL,
            ContactMaterial::Edge,
            80_000,
            0.006,
        ));
        assert!(
            truth
                .state(StructureId::LEFT_BRACHIAL_VESSEL)
                .flags
                .contains(StructureFlags::VESSEL_SEVERED)
        );
        truth.tick_60hz();
        truth.tick_60hz();
        assert!(truth.state(StructureId::LEFT_BRACHIAL_VESSEL).blood_loss_q > 0);

        truth.apply_contact(contact(
            StructureId::RIGHT_MEDIAN_NERVE,
            ContactMaterial::Edge,
            70_000,
            0.004,
        ));
        assert!(
            truth
                .state(StructureId::RIGHT_MEDIAN_NERVE)
                .flags
                .contains(StructureFlags::NERVE_TRANSECTED)
        );
        assert_eq!(
            truth
                .state(StructureId::RIGHT_MEDIAN_NERVE)
                .neural_conduction_q,
            0
        );

        truth.apply_contact(contact(
            StructureId::LIVER,
            ContactMaterial::Point,
            80_000,
            0.010,
        ));
        assert!(
            truth
                .state(StructureId::LIVER)
                .flags
                .contains(StructureFlags::ORGAN_RUPTURED)
        );
        assert!(truth.state(StructureId::LIVER).perfusion_q < STATE_MAX_Q);
    }

    #[test]
    fn nerve_and_fracture_gate_only_the_affected_capabilities() {
        let mut truth = FighterAnatomyTruth::new();
        truth.apply_contact(contact(
            StructureId::LEFT_MEDIAN_NERVE,
            ContactMaterial::Edge,
            70_000,
            0.004,
        ));
        let intents = available_intents(&truth);
        assert!(!intents.contains(&AnatomyIntent::StrikeLeft));
        assert!(!intents.contains(&AnatomyIntent::GrabLeft));
        assert!(intents.contains(&AnatomyIntent::StrikeRight));
        assert!(intents.contains(&AnatomyIntent::Move));

        truth.apply_contact(contact(
            StructureId::RIGHT_FEMUR,
            ContactMaterial::Blunt,
            150_000,
            0.004,
        ));
        let intents = available_intents(&truth);
        assert!(!intents.contains(&AnatomyIntent::Move));
        assert!(!intents.contains(&AnatomyIntent::Dodge));
    }

    #[test]
    fn hemorrhage_accumulation_incapacitate_without_hidden_health() {
        let mut truth = FighterAnatomyTruth::new();
        truth.apply_contact(contact(
            StructureId::AORTA,
            ContactMaterial::Edge,
            100_000,
            0.008,
        ));
        assert!(
            truth
                .state(StructureId::AORTA)
                .flags
                .contains(StructureFlags::VESSEL_SEVERED)
        );
        for _ in 0..40 {
            truth.tick_60hz();
        }
        assert!(is_incapacitated(&truth));
        assert!(available_intents(&truth).is_empty());
        assert!(truth.circulating_blood_q <= 1_500);
    }

    #[test]
    fn snapshot_restore_replay_and_conditioning_are_exact() {
        let mut truth = FighterAnatomyTruth::new();
        truth.apply_contact(contact(
            StructureId::LIVER,
            ContactMaterial::Point,
            80_000,
            0.010,
        ));
        for _ in 0..6 {
            truth.tick_60hz();
        }
        let snapshot = truth.snapshot();
        for _ in 0..24 {
            truth.tick_60hz();
        }
        let replay_hash = truth.truth_hash();
        truth.restore(&snapshot);
        for _ in 0..24 {
            truth.tick_60hz();
        }
        assert_eq!(truth.truth_hash(), replay_hash);
        assert_eq!(truth.active_ids, snapshot.active_ids);
        let conditioning = truth.conditioning(MotionKinematicsQ {
            momentum_q: [1, 2, 3],
            speed_mm_per_s: 450,
            velocity_mm_per_s: [10, -20, 30],
        });
        assert_eq!(conditioning.values[7..14], [1, 2, 3, 450, 10, -20, 30]);
    }
}
