// Geometry-accurate hitbox proxy extraction and contact detection.
// See docs/design/IMPLEMENTATION_PLAN_3ACTION.md for the contract.

use glam::{Mat4, Vec3, vec3};

/// Axis-aligned bounding box in 3D space.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Aabb {
    pub min: Vec3,
    pub max: Vec3,
}

impl Aabb {
    /// Build an AABB centered at the origin from full extents.
    pub fn from_extents(extents: Vec3) -> Self {
        let half = extents * 0.5;
        Self {
            min: -half,
            max: half,
        }
    }

    pub fn center(&self) -> Vec3 {
        (self.min + self.max) * 0.5
    }

    pub fn is_empty(&self) -> bool {
        self.min.x > self.max.x || self.min.y > self.max.y || self.min.z > self.max.z
    }
}

/// Classification of damage for a proxy.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum DamageType {
    Slash,
    Bash,
    Pierce,
}

/// A single collision proxy: bone-local AABB transformed into world space.
#[derive(Debug, Clone)]
pub struct HitboxProxy {
    pub bone_index: usize,
    pub local_aabb: Aabb,
    pub world_transform: Mat4,
    pub damage_type: DamageType,
    pub world_aabb: Aabb,
}

/// Contact manifold data for a single attacker-defender proxy pair.
#[derive(Debug, Clone)]
pub struct ContactGeometry {
    pub point: Vec3,
    pub normal: Vec3,
    pub depth: f32,
    pub attacker_proxy: usize,
    pub defender_proxy: usize,
}

const BODY_BONE_COUNT: usize = 24;

/// Approximate local-space full extents for each mannequin bone (meters).
/// Bone-local Y is the bone length axis; boxes are centered on the bone.
fn bone_extents(index: usize) -> Vec3 {
    match index {
        // Hips / pelvis
        0 => vec3(0.18, 0.12, 0.12),
        // Thighs
        1 | 5 => vec3(0.10, 0.45, 0.10),
        // Calves
        2 | 6 => vec3(0.10, 0.45, 0.10),
        // Feet / toes
        3 | 4 | 7 | 8 => vec3(0.08, 0.08, 0.08),
        // Spine chain
        9 | 10 | 11 => vec3(0.18, 0.12, 0.12),
        // Shoulders (treated as upper-arm volume)
        12 | 16 => vec3(0.08, 0.35, 0.08),
        // Upper arms
        13 | 17 => vec3(0.08, 0.35, 0.08),
        // Forearms
        14 | 18 => vec3(0.08, 0.35, 0.08),
        // Hands
        15 | 19 => vec3(0.08, 0.08, 0.08),
        // Neck
        20 => vec3(0.08, 0.08, 0.08),
        // Head
        21 => vec3(0.12, 0.15, 0.14),
        // Head end / head front (minimal end-effector volumes)
        22 | 23 => vec3(0.05, 0.05, 0.05),
        _ => vec3(0.08, 0.08, 0.08),
    }
}

/// Transform an AABB by an affine matrix by corner enumeration.
/// This stays tight for rotations and non-uniform scales.
fn transform_aabb(matrix: Mat4, local: &Aabb) -> Aabb {
    let corners = [
        vec3(local.min.x, local.min.y, local.min.z),
        vec3(local.max.x, local.min.y, local.min.z),
        vec3(local.min.x, local.max.y, local.min.z),
        vec3(local.max.x, local.max.y, local.min.z),
        vec3(local.min.x, local.min.y, local.max.z),
        vec3(local.max.x, local.min.y, local.max.z),
        vec3(local.min.x, local.max.y, local.max.z),
        vec3(local.max.x, local.max.y, local.max.z),
    ];

    let mut world_min = Vec3::splat(f32::INFINITY);
    let mut world_max = Vec3::splat(f32::NEG_INFINITY);

    for c in corners {
        let p = matrix.transform_point3(c);
        world_min = world_min.min(p);
        world_max = world_max.max(p);
    }

    Aabb {
        min: world_min,
        max: world_max,
    }
}

/// Build body proxies from one frame of skinning matrices.
///
/// `skin_matrices` is a slice so callers can pass `&[pose]` where `pose` is
/// `[Mat4; 24]`; the first frame is used.
pub fn extract_body_proxies(skin_matrices: &[[Mat4; 24]]) -> Vec<HitboxProxy> {
    let matrices = skin_matrices
        .first()
        .copied()
        .unwrap_or([Mat4::IDENTITY; BODY_BONE_COUNT]);

    let mut proxies = Vec::with_capacity(BODY_BONE_COUNT);
    for i in 0..BODY_BONE_COUNT {
        let local = Aabb::from_extents(bone_extents(i));
        let world_transform = matrices[i];
        let world_aabb = transform_aabb(world_transform, &local);
        proxies.push(HitboxProxy {
            bone_index: i,
            local_aabb: local,
            world_transform,
            damage_type: DamageType::Bash,
            world_aabb,
        });
    }
    proxies
}

/// Build a weapon proxy from its world transform.
///
/// Defaults to `DamageType::Slash`. Callers that need `Bash` (e.g. Grab)
/// can mutate the returned proxy's `damage_type`.
pub fn extract_weapon_proxy(weapon_transform: &Mat4) -> HitboxProxy {
    let local = Aabb::from_extents(vec3(0.02, 0.02, 0.90));
    let world_transform = *weapon_transform;
    let world_aabb = transform_aabb(world_transform, &local);
    HitboxProxy {
        bone_index: BODY_BONE_COUNT, // weapon is not a body bone
        local_aabb: local,
        world_transform,
        damage_type: DamageType::Slash,
        world_aabb,
    }
}

/// Test a pair of world-space AABBs for overlap.
fn aabb_intersect(a: &Aabb, b: &Aabb) -> bool {
    a.min.x < b.max.x
        && a.max.x > b.min.x
        && a.min.y < b.max.y
        && a.max.y > b.min.y
        && a.min.z < b.max.z
        && a.max.z > b.min.z
}

/// Compute contact data for the first penetrating attacker/defender proxy pair.
pub fn contact(attacker: &[HitboxProxy], defender: &[HitboxProxy]) -> Option<ContactGeometry> {
    for (ai, a) in attacker.iter().enumerate() {
        for (di, d) in defender.iter().enumerate() {
            if !aabb_intersect(&a.world_aabb, &d.world_aabb) {
                continue;
            }

            let overlap_min = a.world_aabb.min.max(d.world_aabb.min);
            let overlap_max = a.world_aabb.max.min(d.world_aabb.max);
            let overlap = overlap_max - overlap_min;

            // Find the axis of minimum penetration.
            let mut axis = 0usize;
            let mut min_pen = overlap.x;
            if overlap.y < min_pen {
                axis = 1;
                min_pen = overlap.y;
            }
            if overlap.z < min_pen {
                axis = 2;
                min_pen = overlap.z;
            }

            // Direction from defender to attacker on the separating axis.
            let ca = a.world_aabb.center();
            let cd = d.world_aabb.center();
            let diff = ca - cd;
            let sign = if diff[axis] >= 0.0 { 1.0 } else { -1.0 };
            let mut normal = Vec3::ZERO;
            normal[axis] = sign;

            return Some(ContactGeometry {
                point: (overlap_min + overlap_max) * 0.5,
                normal,
                depth: min_pen,
                attacker_proxy: ai,
                defender_proxy: di,
            });
        }
    }
    None
}

/// Return the 12 world-space edges of each proxy AABB as line segments.
pub fn debug_lines(proxies: &[HitboxProxy]) -> Vec<(Vec3, Vec3)> {
    let mut lines = Vec::with_capacity(proxies.len() * 12);
    for p in proxies {
        let min = p.world_aabb.min;
        let max = p.world_aabb.max;

        let c = [
            vec3(min.x, min.y, min.z),
            vec3(max.x, min.y, min.z),
            vec3(max.x, max.y, min.z),
            vec3(min.x, max.y, min.z),
            vec3(min.x, min.y, max.z),
            vec3(max.x, min.y, max.z),
            vec3(max.x, max.y, max.z),
            vec3(min.x, max.y, max.z),
        ];

        // Bottom face
        lines.push((c[0], c[1]));
        lines.push((c[1], c[2]));
        lines.push((c[2], c[3]));
        lines.push((c[3], c[0]));
        // Top face
        lines.push((c[4], c[5]));
        lines.push((c[5], c[6]));
        lines.push((c[6], c[7]));
        lines.push((c[7], c[4]));
        // Vertical edges
        lines.push((c[0], c[4]));
        lines.push((c[1], c[5]));
        lines.push((c[2], c[6]));
        lines.push((c[3], c[7]));
    }
    lines
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn overlapping_aabbs_produce_contact() {
        let attacker = vec![HitboxProxy {
            bone_index: 0,
            local_aabb: Aabb::from_extents(Vec3::ONE),
            world_transform: Mat4::from_translation(vec3(0.0, 0.0, 0.0)),
            damage_type: DamageType::Bash,
            world_aabb: transform_aabb(Mat4::from_translation(vec3(0.0, 0.0, 0.0)), &Aabb::from_extents(Vec3::ONE)),
        }];
        let defender = vec![HitboxProxy {
            bone_index: 0,
            local_aabb: Aabb::from_extents(Vec3::ONE),
            world_transform: Mat4::from_translation(vec3(0.5, 0.0, 0.0)),
            damage_type: DamageType::Bash,
            world_aabb: transform_aabb(Mat4::from_translation(vec3(0.5, 0.0, 0.0)), &Aabb::from_extents(Vec3::ONE)),
        }];

        let c = contact(&attacker, &defender).expect("expected contact");
        assert!(c.depth > 0.0);
        // Defender is at x=0.5, attacker at x=0.0; defender -> attacker is -X.
        assert_eq!(c.normal, -Vec3::X);
        assert_eq!(c.attacker_proxy, 0);
        assert_eq!(c.defender_proxy, 0);
    }

    #[test]
    fn separated_aabbs_produce_no_contact() {
        let attacker = vec![HitboxProxy {
            bone_index: 0,
            local_aabb: Aabb::from_extents(Vec3::ONE),
            world_transform: Mat4::from_translation(vec3(0.0, 0.0, 0.0)),
            damage_type: DamageType::Bash,
            world_aabb: transform_aabb(Mat4::from_translation(vec3(0.0, 0.0, 0.0)), &Aabb::from_extents(Vec3::ONE)),
        }];
        let defender = vec![HitboxProxy {
            bone_index: 0,
            local_aabb: Aabb::from_extents(Vec3::ONE),
            world_transform: Mat4::from_translation(vec3(2.0, 0.0, 0.0)),
            damage_type: DamageType::Bash,
            world_aabb: transform_aabb(Mat4::from_translation(vec3(2.0, 0.0, 0.0)), &Aabb::from_extents(Vec3::ONE)),
        }];

        assert!(contact(&attacker, &defender).is_none());
    }

    #[test]
    fn body_proxies_from_identity_are_finite() {
        let proxies = extract_body_proxies(&[[Mat4::IDENTITY; 24]]);
        assert_eq!(proxies.len(), 24);
        for p in &proxies {
            assert!(p.world_aabb.min.is_finite());
            assert!(p.world_aabb.max.is_finite());
            assert!(p.world_aabb.min.x <= p.world_aabb.max.x);
            assert!(p.world_aabb.min.y <= p.world_aabb.max.y);
            assert!(p.world_aabb.min.z <= p.world_aabb.max.z);
        }
    }

    #[test]
    fn weapon_proxy_intersects_torso() {
        // Defender torso at origin (Hips proxy).
        let defender = extract_body_proxies(&[[Mat4::IDENTITY; 24]]);

        // Weapon held so its long axis crosses the defender's hips/torso.
        // Hand at (0.05, 0.0, 0.0), sword centered there and extending along Z.
        let hand = Mat4::from_translation(vec3(0.05, 0.0, 0.0));
        let weapon = extract_weapon_proxy(&hand);
        let attacker = vec![weapon];

        let c = contact(&attacker, &defender).expect("weapon should intersect torso");
        assert!(c.depth > 0.0);
        // Defender proxy should be a torso/hip bone.
        assert!(defender[c.defender_proxy].bone_index <= 11);
    }
}
