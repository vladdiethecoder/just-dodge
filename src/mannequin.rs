// Procedural mannequin mesh with skeleton skinning
// Generates a simplified humanoid from geometric primitives
// (capsules for limbs, sphere for head, box for feet).
// Each vertex is weighted to its nearest joint.

use glam::{Vec3, Mat4};

// ---------------------------------------------------------------------------
// Skeleton definition: 34 joints, absolute rest positions
// ---------------------------------------------------------------------------

pub const NUM_JOINTS: usize = 35;

/// Parent index for each joint, or usize::MAX for root
pub const JOINT_PARENTS: [usize; NUM_JOINTS] = [
    34, 0, 1, 2, 3, 4, 3, 6, 7, 8, 3, 10, 11, 12, 0, 14, 15, 16, 2, 18, 19, 0, 21, 22, 23,
    9, 9, 9, 9, 9, 13, 13, 13, 13, 13,
];
// 34 = root sentinel (no parent)

/// Absolute rest positions in Y-up space
pub const G1_REST: [[f32; 3]; NUM_JOINTS] = [
    [0.0, 0.0, 0.0],     // 0: pelvis
    [0.0, 0.10, 0.0],    // 1: spine_01
    [0.0, 0.25, 0.0],    // 2: spine_02
    [0.0, 0.45, 0.0],    // 3: spine_03
    [0.0, 0.60, 0.0],    // 4: neck_01
    [0.0, 0.72, 0.0],    // 5: head
    [0.06, 0.43, 0.0],   // 6: clavicle_l
    [0.21, 0.43, 0.0],   // 7: upperarm_l
    [0.46, 0.43, 0.0],   // 8: lowerarm_l
    [0.68, 0.43, 0.0],   // 9: hand_l
    [-0.06, 0.43, 0.0],  // 10: clavicle_r
    [-0.21, 0.43, 0.0],  // 11: upperarm_r
    [-0.46, 0.43, 0.0],  // 12: lowerarm_r
    [-0.68, 0.43, 0.0],  // 13: hand_r
    [0.08, -0.05, 0.0],  // 14: thigh_l
    [0.08, -0.45, 0.0],  // 15: calf_l
    [0.08, -0.83, 0.0],  // 16: foot_l
    [0.08, -0.83, 0.10], // 17: ball_l
    [0.0, 0.30, 0.0],    // 18: spine_04
    [0.0, 0.35, 0.0],    // 19: spine_05
    [0.0, 0.40, 0.0],    // 20: spine_06
    [-0.08, -0.05, 0.0], // 21: thigh_r
    [-0.08, -0.45, 0.0], // 22: calf_r
    [-0.08, -0.83, 0.0], // 23: foot_r
    [-0.08, -0.83, 0.10],// 24: ball_r
    [0.71, 0.43, 0.02],  // 25: thumb_01_l
    [0.72, 0.43, -0.01], // 26: index_01_l
    [0.73, 0.43, -0.02], // 27: middle_01_l
    [0.72, 0.43, -0.04], // 28: ring_01_l
    [0.71, 0.43, -0.05], // 29: pinky_01_l
    [-0.71, 0.43, 0.02], // 30: thumb_01_r
    [-0.72, 0.43, -0.01],// 31: index_01_r
    [-0.73, 0.43, -0.02],// 32: middle_01_r
    [-0.72, 0.43, -0.04],// 33: ring_01_r
    [-0.71, 0.43, -0.05],// 34: pinky_01_r
];

/// Compute global rest-pose transforms for all joints
pub fn compute_rest_transforms() -> [Mat4; NUM_JOINTS] {
    let mut xforms = [Mat4::IDENTITY; NUM_JOINTS];
    for i in 0..NUM_JOINTS {
        let local = Mat4::from_translation(Vec3::from_array(G1_REST[i]));
        let parent = JOINT_PARENTS[i];
        xforms[i] = if parent < NUM_JOINTS { xforms[parent] * local } else { local };
    }
    xforms
}

/// Get the absolute rest position of a joint
pub fn joint_rest_pos(idx: usize) -> Vec3 {
    Vec3::from_array(G1_REST[idx])
}

// ---------------------------------------------------------------------------
// Procedural Mannequin Mesh
// ---------------------------------------------------------------------------

#[repr(C)]
#[derive(Debug, Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
pub struct SkinnedVertex {
    pub position: [f32; 3],
    pub normal: [f32; 3],
    pub uv: [f32; 2],
    pub joint_indices: [u32; 4],
    pub joint_weights: [f32; 4],
}

pub struct MannequinMesh {
    pub vertices: Vec<SkinnedVertex>,
    pub indices: Vec<u32>,
    pub joint_transforms: [Mat4; NUM_JOINTS],
}

impl Default for MannequinMesh {
    fn default() -> Self { Self::new() }
}

impl MannequinMesh {
    pub fn new() -> Self {
        let mut vertices = Vec::new();
        let mut indices = Vec::new();

        // Bone segments: (parent, child, radius)
        let segments: &[(usize, usize, f32)] = &[
            (0, 1, 0.06), (1, 2, 0.06), (2, 3, 0.06), (3, 4, 0.04), (4, 5, 0.06),
            (3, 6, 0.04), (6, 7, 0.04), (7, 8, 0.03), (8, 9, 0.025),
            (3, 10, 0.04), (10, 11, 0.04), (11, 12, 0.03), (12, 13, 0.025),
            (0, 14, 0.06), (14, 15, 0.05), (15, 16, 0.04),
            (0, 21, 0.06), (21, 22, 0.05), (22, 23, 0.04),
        ];

        add_sphere(&mut vertices, &mut indices, Vec3::new(0.0, 0.72, 0.0), 0.10, 5);
        add_sphere(&mut vertices, &mut indices, Vec3::new(0.68, 0.43, 0.0), 0.025, 9);
        add_sphere(&mut vertices, &mut indices, Vec3::new(-0.68, 0.43, 0.0), 0.025, 13);
        add_box(&mut vertices, &mut indices, Vec3::new(0.08, -0.83, 0.05), Vec3::new(0.08, -0.83, -0.05), 17, 0.03);
        add_box(&mut vertices, &mut indices, Vec3::new(-0.08, -0.83, 0.05), Vec3::new(-0.08, -0.83, -0.05), 24, 0.03);

        for &(parent, child, radius) in segments {
            add_capsule(&mut vertices, &mut indices,
                Vec3::from_array(G1_REST[parent]),
                Vec3::from_array(G1_REST[child]),
                parent, child, radius);
        }

        Self { vertices, indices, joint_transforms: [Mat4::IDENTITY; NUM_JOINTS] }
    }

    pub fn update_transforms(&mut self, transforms: &[Mat4; NUM_JOINTS]) {
        self.joint_transforms = *transforms;
    }
}

fn add_capsule(v: &mut Vec<SkinnedVertex>, i: &mut Vec<u32>,
    a: Vec3, b: Vec3, ja: usize, jb: usize, radius: f32)
{
    let segs = 8; let rings = 4; let base = v.len() as u32;
    let dir = (b - a).normalize();
    let up = if dir.abs().y < 0.99 { Vec3::Y } else { Vec3::X };
    let right = dir.cross(up).normalize();
    let fwd = right.cross(dir).normalize();
    let len = (b - a).length();

    for ring in 0..=rings {
        let t = ring as f32 / rings as f32;
        let ctr = a + dir * (t * len);
        for seg in 0..segs {
            let angle = seg as f32 / segs as f32 * std::f32::consts::TAU;
            let off = right * angle.cos() * radius + fwd * angle.sin() * radius;
            let pos = ctr + off;
            v.push(SkinnedVertex {
                position: pos.to_array(),
                normal: off.normalize().to_array(),
                uv: [seg as f32 / segs as f32, t],
                joint_indices: [ja as u32, jb as u32, 0, 0],
                joint_weights: [1.0 - t, t, 0.0, 0.0],
            });
        }
    }
    for ring in 0..rings {
        for seg in 0..segs {
            let a = base + ring as u32 * segs as u32 + seg as u32;
            let b = base + ring as u32 * segs as u32 + ((seg + 1) % segs) as u32;
            let c = base + (ring + 1) as u32 * segs as u32 + seg as u32;
            let d = base + (ring + 1) as u32 * segs as u32 + ((seg + 1) % segs) as u32;
            i.extend_from_slice(&[a, b, c, b, d, c]);
        }
    }
}

fn add_sphere(v: &mut Vec<SkinnedVertex>, i: &mut Vec<u32>, center: Vec3, radius: f32, joint: usize) {
    let segs = 8; let rings = 4; let base = v.len() as u32;
    for ring in 0..=rings {
        let phi = ring as f32 / rings as f32 * std::f32::consts::PI;
        let y = phi.cos() * radius;
        let r = phi.sin() * radius;
        for seg in 0..segs {
            let theta = seg as f32 / segs as f32 * std::f32::consts::TAU;
            let x = theta.cos() * r;
            let z = theta.sin() * r;
            let pos = center + Vec3::new(x, y, z);
            v.push(SkinnedVertex {
                position: pos.to_array(),
                normal: Vec3::new(x, y, z).normalize().to_array(),
                uv: [seg as f32 / segs as f32, ring as f32 / rings as f32],
                joint_indices: [joint as u32, 0, 0, 0],
                joint_weights: [1.0, 0.0, 0.0, 0.0],
            });
        }
    }
    for ring in 0..rings {
        for seg in 0..segs {
            let a = base + ring as u32 * segs as u32 + seg as u32;
            let b = base + ring as u32 * segs as u32 + ((seg + 1) % segs) as u32;
            let c = base + (ring + 1) as u32 * segs as u32 + seg as u32;
            let d = base + (ring + 1) as u32 * segs as u32 + ((seg + 1) % segs) as u32;
            i.extend_from_slice(&[a, b, c, b, d, c]);
        }
    }
}

fn add_box(v: &mut Vec<SkinnedVertex>, i: &mut Vec<u32>, a: Vec3, b: Vec3, joint: usize, size: f32) {
    let base = v.len() as u32;
    let dir = (b - a).normalize();
    let up = if dir.abs().y < 0.99 { Vec3::Y } else { Vec3::X };
    let right = dir.cross(up).normalize();
    let fwd = right.cross(dir).normalize();
    let corners = [
        a + right * size + fwd * size,
        a + right * size - fwd * size,
        a - right * size - fwd * size,
        a - right * size + fwd * size,
        b + right * size + fwd * size,
        b + right * size - fwd * size,
        b - right * size - fwd * size,
        b - right * size + fwd * size,
    ];
    for corner in &corners {
        v.push(SkinnedVertex {
            position: corner.to_array(),
            normal: [0.0, 0.0, 0.0],
            uv: [0.0, 0.0],
            joint_indices: [joint as u32, 0, 0, 0],
            joint_weights: [1.0, 0.0, 0.0, 0.0],
        });
    }
    let faces: &[[u32; 4]] = &[[0,1,2,3],[4,7,6,5],[0,4,5,1],[3,2,6,7],[0,3,7,4],[1,5,6,2]];
    for &[a,b,c,d] in faces {
        i.extend_from_slice(&[base+a, base+b, base+c, base+d, base+a, base+c]);
    }
}
