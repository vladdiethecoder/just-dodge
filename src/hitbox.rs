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

/// Stable physical function of a collision proxy.
///
/// This is simulation evidence, not a rendered-material label. A
/// `WeaponGuard` is a defensive interaction surface; a `Body` is damageable.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum ProxyRole {
    Body,
    WeaponEdge,
    WeaponGuard,
}

/// A single collision proxy: bone-local AABB transformed into world space.
#[derive(Debug, Clone)]
pub struct HitboxProxy {
    pub bone_index: usize,
    pub local_aabb: Aabb,
    pub world_transform: Mat4,
    pub damage_type: DamageType,
    pub role: ProxyRole,
    pub world_aabb: Aabb,
}

/// Contact manifold data for a single attacker-defender proxy pair.
#[derive(Debug, Clone)]
pub struct ContactGeometry {
    pub point: Vec3,
    pub normal: Vec3,
    pub depth: f32,
    /// Fraction through the current deterministic physics substep at first contact.
    /// Static overlap reports `0.0`.
    pub time_of_impact: f32,
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
        9..=11 => vec3(0.18, 0.12, 0.12),
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
    for (i, world_transform) in matrices.iter().copied().enumerate() {
        let local = Aabb::from_extents(bone_extents(i));
        let world_aabb = transform_aabb(world_transform, &local);
        proxies.push(HitboxProxy {
            bone_index: i,
            local_aabb: local,
            world_transform,
            damage_type: DamageType::Bash,
            role: ProxyRole::Body,
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
        role: ProxyRole::WeaponEdge,
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

fn static_contact(
    attacker: &HitboxProxy,
    defender: &HitboxProxy,
    attacker_proxy: usize,
    defender_proxy: usize,
) -> Option<ContactGeometry> {
    if !aabb_intersect(&attacker.world_aabb, &defender.world_aabb) {
        return None;
    }

    let overlap_min = attacker.world_aabb.min.max(defender.world_aabb.min);
    let overlap_max = attacker.world_aabb.max.min(defender.world_aabb.max);
    let overlap = overlap_max - overlap_min;
    let mut axis = 0usize;
    let mut min_penetration = overlap.x;
    if overlap.y < min_penetration {
        axis = 1;
        min_penetration = overlap.y;
    }
    if overlap.z < min_penetration {
        axis = 2;
        min_penetration = overlap.z;
    }

    let difference = attacker.world_aabb.center() - defender.world_aabb.center();
    let mut normal = Vec3::ZERO;
    normal[axis] = if difference[axis] >= 0.0 { 1.0 } else { -1.0 };
    Some(ContactGeometry {
        point: (overlap_min + overlap_max) * 0.5,
        normal,
        depth: min_penetration,
        time_of_impact: 0.0,
        attacker_proxy,
        defender_proxy,
    })
}

/// Compute contact data for the first penetrating attacker/defender proxy pair.
pub fn contact(attacker: &[HitboxProxy], defender: &[HitboxProxy]) -> Option<ContactGeometry> {
    for (attacker_proxy, attacker) in attacker.iter().enumerate() {
        for (defender_proxy, defender) in defender.iter().enumerate() {
            if let Some(contact) =
                static_contact(attacker, defender, attacker_proxy, defender_proxy)
            {
                return Some(contact);
            }
        }
    }
    None
}

/// Conservative continuous collision detection across one deterministic physics substep.
///
/// The attacker centre is swept from its previous to current AABB centre through
/// a defender AABB expanded by the maximum endpoint half-extents. This rejects
/// endpoint tunnelling even if a rotating/scaling proxy makes the conservative
/// swept volume wider than the exact mesh.
pub fn swept_contact(
    previous_attacker: &[HitboxProxy],
    current_attacker: &[HitboxProxy],
    defender: &[HitboxProxy],
) -> Option<ContactGeometry> {
    swept_contacts(previous_attacker, current_attacker, defender)
        .into_iter()
        .next()
}

/// Return every swept weapon/body contact from one deterministic physics substep.
///
/// The list is canonically ordered, so a shared bilateral world reducer can
/// retain simultaneous contacts instead of silently discarding all but one.
pub fn swept_contacts(
    previous_attacker: &[HitboxProxy],
    current_attacker: &[HitboxProxy],
    defender: &[HitboxProxy],
) -> Vec<ContactGeometry> {
    let mut contacts = Vec::new();
    for (attacker_proxy, current) in current_attacker.iter().enumerate() {
        let previous = previous_attacker.get(attacker_proxy).unwrap_or(current);
        for (defender_proxy, target) in defender.iter().enumerate() {
            let candidate = static_contact(previous, target, attacker_proxy, defender_proxy)
                .or_else(|| {
                    swept_pair_contact(previous, current, target, attacker_proxy, defender_proxy)
                });
            let Some(candidate) = candidate else {
                continue;
            };
            contacts.push(candidate);
        }
    }
    contacts.sort_by(|left, right| {
        left.time_of_impact
            .total_cmp(&right.time_of_impact)
            .then_with(|| left.attacker_proxy.cmp(&right.attacker_proxy))
            .then_with(|| left.defender_proxy.cmp(&right.defender_proxy))
    });
    contacts
}

fn swept_pair_contact(
    previous: &HitboxProxy,
    current: &HitboxProxy,
    target: &HitboxProxy,
    attacker_proxy: usize,
    defender_proxy: usize,
) -> Option<ContactGeometry> {
    let start = previous.world_aabb.center();
    let end = current.world_aabb.center();
    let delta = end - start;
    let half_extents = ((previous.world_aabb.max - previous.world_aabb.min)
        .max(current.world_aabb.max - current.world_aabb.min))
        * 0.5;
    let expanded_min = target.world_aabb.min - half_extents;
    let expanded_max = target.world_aabb.max + half_extents;

    let mut enter = f32::NEG_INFINITY;
    let mut exit = f32::INFINITY;
    let mut impact_axis = None;
    for axis in 0..3 {
        if delta[axis].abs() <= f32::EPSILON {
            if start[axis] < expanded_min[axis] || start[axis] > expanded_max[axis] {
                return None;
            }
            continue;
        }

        let first = (expanded_min[axis] - start[axis]) / delta[axis];
        let second = (expanded_max[axis] - start[axis]) / delta[axis];
        let axis_enter = first.min(second);
        let axis_exit = first.max(second);
        if axis_enter > enter {
            enter = axis_enter;
            impact_axis = Some(axis);
        }
        exit = exit.min(axis_exit);
        if enter > exit {
            return None;
        }
    }

    let axis = impact_axis?;
    if exit < 0.0 || enter > 1.0 {
        return None;
    }

    let time_of_impact = enter.max(0.0);
    let mut normal = Vec3::ZERO;
    normal[axis] = if delta[axis] > 0.0 { -1.0 } else { 1.0 };
    let centre = start + delta * time_of_impact;
    Some(ContactGeometry {
        point: centre - normal * half_extents[axis],
        normal,
        depth: 0.0,
        time_of_impact,
        attacker_proxy,
        defender_proxy,
    })
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

    fn proxy_at(center: Vec3, extents: Vec3) -> HitboxProxy {
        let world_transform = Mat4::from_translation(center);
        let local_aabb = Aabb::from_extents(extents);
        HitboxProxy {
            bone_index: 0,
            local_aabb,
            world_transform,
            damage_type: DamageType::Slash,
            role: ProxyRole::WeaponEdge,
            world_aabb: transform_aabb(world_transform, &local_aabb),
        }
    }

    #[test]
    fn overlapping_aabbs_produce_contact() {
        let attacker = vec![HitboxProxy {
            bone_index: 0,
            local_aabb: Aabb::from_extents(Vec3::ONE),
            world_transform: Mat4::from_translation(vec3(0.0, 0.0, 0.0)),
            damage_type: DamageType::Bash,
            role: ProxyRole::Body,
            world_aabb: transform_aabb(
                Mat4::from_translation(vec3(0.0, 0.0, 0.0)),
                &Aabb::from_extents(Vec3::ONE),
            ),
        }];
        let defender = vec![HitboxProxy {
            bone_index: 0,
            local_aabb: Aabb::from_extents(Vec3::ONE),
            world_transform: Mat4::from_translation(vec3(0.5, 0.0, 0.0)),
            damage_type: DamageType::Bash,
            role: ProxyRole::Body,
            world_aabb: transform_aabb(
                Mat4::from_translation(vec3(0.5, 0.0, 0.0)),
                &Aabb::from_extents(Vec3::ONE),
            ),
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
            role: ProxyRole::Body,
            world_aabb: transform_aabb(
                Mat4::from_translation(vec3(0.0, 0.0, 0.0)),
                &Aabb::from_extents(Vec3::ONE),
            ),
        }];
        let defender = vec![HitboxProxy {
            bone_index: 0,
            local_aabb: Aabb::from_extents(Vec3::ONE),
            world_transform: Mat4::from_translation(vec3(2.0, 0.0, 0.0)),
            damage_type: DamageType::Bash,
            role: ProxyRole::Body,
            world_aabb: transform_aabb(
                Mat4::from_translation(vec3(2.0, 0.0, 0.0)),
                &Aabb::from_extents(Vec3::ONE),
            ),
        }];

        assert!(contact(&attacker, &defender).is_none());
    }

    #[test]
    fn swept_contact_detects_a_weapon_that_tunnels_between_endpoints() {
        let previous_weapon = vec![proxy_at(vec3(-2.0, 0.0, 0.0), vec3(0.1, 0.1, 0.1))];
        let current_weapon = vec![proxy_at(vec3(2.0, 0.0, 0.0), vec3(0.1, 0.1, 0.1))];
        let defender = vec![proxy_at(Vec3::ZERO, Vec3::ONE)];

        assert!(contact(&previous_weapon, &defender).is_none());
        assert!(contact(&current_weapon, &defender).is_none());

        let impact = swept_contact(&previous_weapon, &current_weapon, &defender)
            .expect("continuous sweep must not tunnel through the defender");
        assert!((0.0..1.0).contains(&impact.time_of_impact));
        assert_eq!(impact.normal, -Vec3::X);
        assert_eq!(impact.depth, 0.0);
    }

    #[test]
    fn swept_contacts_retains_and_orders_multiple_defender_hits() {
        let previous_weapon = vec![proxy_at(vec3(-3.0, 0.0, 0.0), vec3(0.1, 0.1, 0.1))];
        let current_weapon = vec![proxy_at(vec3(3.0, 0.0, 0.0), vec3(0.1, 0.1, 0.1))];
        let defender = vec![
            proxy_at(vec3(-1.0, 0.0, 0.0), Vec3::ONE),
            proxy_at(vec3(1.0, 0.0, 0.0), Vec3::ONE),
        ];

        let contacts = swept_contacts(&previous_weapon, &current_weapon, &defender);
        assert_eq!(contacts.len(), 2);
        assert_eq!(contacts[0].defender_proxy, 0);
        assert_eq!(contacts[1].defender_proxy, 1);
        assert!(contacts[0].time_of_impact < contacts[1].time_of_impact);
    }

    #[test]
    fn swept_contact_rejects_a_weapon_passing_outside_the_defender() {
        let previous_weapon = vec![proxy_at(vec3(-2.0, 2.0, 0.0), vec3(0.1, 0.1, 0.1))];
        let current_weapon = vec![proxy_at(vec3(2.0, 2.0, 0.0), vec3(0.1, 0.1, 0.1))];
        let defender = vec![proxy_at(Vec3::ZERO, Vec3::ONE)];

        assert!(swept_contact(&previous_weapon, &current_weapon, &defender).is_none());
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
