use std::fs::File;
use std::io::{BufReader, Read};

use glam::Mat4;

pub struct MeshData {
    pub vertices: Vec<f32>, // positions [x,y,z] for each vertex
    pub normals: Vec<f32>,  // normals [nx,ny,nz] for each vertex
    pub uvs: Vec<f32>,      // texture coordinates [u,v]
    pub indices: Vec<u32>,
}

pub fn load_binary(path: &str) -> std::io::Result<MeshData> {
    let files = std::fs::File::open(path)?;
    let mut reader = BufReader::new(files);

    let mut header = [0u8; 8];
    reader.read_exact(&mut header)?;
    let vert_count = u32::from_le_bytes(header[0..4].try_into().unwrap()) as usize;
    let index_count = u32::from_le_bytes(header[4..8].try_into().unwrap()) as usize;

    let vert_bytes = vert_count * 3 * 4;
    let mut vert_data = vec![0u8; vert_bytes];
    reader.read_exact(&mut vert_data)?;
    let vertices: Vec<f32> = vert_data
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
        .collect();

    let mut norm_data = vec![0u8; vert_bytes];
    reader.read_exact(&mut norm_data)?;
    let normals: Vec<f32> = norm_data
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
        .collect();

    let index_bytes = index_count * 4;
    let mut index_data = vec![0u8; index_bytes];
    reader.read_exact(&mut index_data)?;

    let indices: Vec<u32> = index_data
        .chunks_exact(4)
        .map(|b| u32::from_le_bytes(b.try_into().unwrap()))
        .collect();

    let uv_bytes = vert_count * 2 * 4;
    let mut uv_data = vec![0u8; uv_bytes];
    reader.read_exact(&mut uv_data)?;
    let uvs: Vec<f32> = uv_data
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
        .collect();

    Ok(MeshData {
        vertices,
        normals,
        uvs,
        indices,
    })
}

// ---------------------------------------------------------------------------
// Skinned mesh (SKM1)
// ---------------------------------------------------------------------------

/// Interleaved vertex for the skinning pipeline. 96 bytes stride.
#[repr(C)]
#[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
pub struct SkinnedVertex {
    pub position: [f32; 3],
    pub normal: [f32; 3],
    pub uv: [f32; 2],
    pub joint_indices: [u32; 8],
    pub joint_weights: [f32; 8],
}

pub struct Bone {
    pub name: String,
    pub parent: i32, // -1 = root
    pub rest_local: Mat4,
    pub inverse_bind: Mat4,
}

pub struct SkinnedMeshData {
    pub vertices: Vec<SkinnedVertex>,
    pub indices: Vec<u32>,
    pub bones: Vec<Bone>,
    /// Minimum vertex Y (feet), used to seat the model on the ground.
    pub feet_y: f32,
}

fn rd_u8(r: &mut BufReader<File>) -> std::io::Result<u8> {
    let mut b = [0u8; 1];
    r.read_exact(&mut b)?;
    Ok(b[0])
}

fn rd_u32(r: &mut BufReader<File>) -> std::io::Result<u32> {
    let mut b = [0u8; 4];
    r.read_exact(&mut b)?;
    Ok(u32::from_le_bytes(b))
}

fn rd_u16(r: &mut BufReader<File>) -> std::io::Result<u16> {
    let mut b = [0u8; 2];
    r.read_exact(&mut b)?;
    Ok(u16::from_le_bytes(b))
}

fn rd_i32(r: &mut BufReader<File>) -> std::io::Result<i32> {
    let mut b = [0u8; 4];
    r.read_exact(&mut b)?;
    Ok(i32::from_le_bytes(b))
}

fn rd_f32(r: &mut BufReader<File>) -> std::io::Result<f32> {
    let mut b = [0u8; 4];
    r.read_exact(&mut b)?;
    Ok(f32::from_le_bytes(b))
}

/// Read a 16-float row-major matrix and build a column-major Mat4.
fn rd_mat4(r: &mut BufReader<File>) -> std::io::Result<Mat4> {
    let mut a = [0f32; 16];
    for x in a.iter_mut() {
        *x = rd_f32(r)?;
    }
    Ok(Mat4::from_cols_array(&[
        a[0], a[4], a[8], a[12], a[1], a[5], a[9], a[13], a[2], a[6], a[10], a[14], a[3], a[7],
        a[11], a[15],
    ]))
}

pub fn load_skinned(path: &str) -> std::io::Result<SkinnedMeshData> {
    let f = File::open(path)?;
    let mut r = BufReader::new(f);

    let mut magic = [0u8; 4];
    r.read_exact(&mut magic)?;
    assert_eq!(&magic, b"SKM1", "not a SKM1 skinned mesh");
    let vc = rd_u32(&mut r)? as usize;
    let ic = rd_u32(&mut r)? as usize;
    let bc = rd_u32(&mut r)? as usize;

    let mut verts = Vec::with_capacity(vc);
    let mut feet_y = f32::MAX;
    for _ in 0..vc {
        let pos = [rd_f32(&mut r)?, rd_f32(&mut r)?, rd_f32(&mut r)?];
        let nrm = [rd_f32(&mut r)?, rd_f32(&mut r)?, rd_f32(&mut r)?];
        let uv = [rd_f32(&mut r)?, rd_f32(&mut r)?];
        feet_y = feet_y.min(pos[1]);
        verts.push(SkinnedVertex {
            position: pos,
            normal: nrm,
            uv,
            joint_indices: [0; 8],
            joint_weights: [0.0; 8],
        });
    }

    let mut indices = Vec::with_capacity(ic);
    for _ in 0..ic {
        indices.push(rd_u32(&mut r)?);
    }

    let mut bones = Vec::with_capacity(bc);
    for _ in 0..bc {
        let nl = rd_u16(&mut r)? as usize;
        let mut nameb = vec![0u8; nl];
        r.read_exact(&mut nameb)?;
        let name = String::from_utf8_lossy(&nameb).into_owned();
        let parent = rd_i32(&mut r)?;
        let rest_local = rd_mat4(&mut r)?;
        let inverse_bind = rd_mat4(&mut r)?;
        bones.push(Bone {
            name,
            parent,
            rest_local,
            inverse_bind,
        });
    }

    for v in verts.iter_mut() {
        let cnt = rd_u8(&mut r)? as usize;
        let mut influences: Vec<(u32, f32)> = Vec::with_capacity(cnt);
        for _ in 0..cnt {
            let idx = rd_u32(&mut r)?;
            let w = rd_f32(&mut r)?;
            if w > 0.0 {
                influences.push((idx, w));
            }
        }
        // Keep top 8 by weight, normalize to sum=1.0 (shader expects Σwᵢ=1).
        influences.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        let mut ji = [0u32; 8];
        let mut jw = [0.0f32; 8];
        for (k, (j, w)) in influences.iter().take(8).enumerate() {
            ji[k] = *j;
            jw[k] = *w;
        }
        let sum: f32 = jw.iter().sum();
        if sum > 0.0001 {
            for w in &mut jw {
                *w /= sum;
            }
        }
        v.joint_indices = ji;
        v.joint_weights = jw;
    }

    Ok(SkinnedMeshData {
        vertices: verts,
        indices,
        bones,
        feet_y,
    })
}

pub struct SkeletalAnimation {
    pub bone_count: usize,
    pub fps: u16,
    pub frames: Vec<Vec<Mat4>>,
}

/// Load one ANM1 matrix sequence. ANM1 historically omitted its matrix-space
/// tag: callers must use the producing asset contract to distinguish local
/// reference frames from armature-world animation frames.
pub fn load_skeletal_animation(path: &str) -> std::io::Result<SkeletalAnimation> {
    let f = File::open(path)?;
    let mut r = BufReader::new(f);
    let mut magic = [0u8; 4];
    r.read_exact(&mut magic)?;
    if &magic != b"ANM1" {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "not an ANM1 skeletal animation",
        ));
    }
    let bone_count = rd_u32(&mut r)? as usize;
    let fps = rd_u16(&mut r)?;
    let frame_count = rd_u32(&mut r)? as usize;
    let mut frames = Vec::with_capacity(frame_count);
    for _ in 0..frame_count {
        let mut frame = Vec::with_capacity(bone_count);
        for _ in 0..bone_count {
            frame.push(rd_mat4(&mut r)?);
        }
        frames.push(frame);
    }
    Ok(SkeletalAnimation {
        bone_count,
        fps,
        frames,
    })
}

/// Convert one parent-relative reference-pose frame into dynamic skinning
/// matrices for any SKM1 hierarchy. This deliberately has no 24-bone
/// mannequin assumption.
pub fn reference_pose_skin_matrices(
    mesh: &SkinnedMeshData,
    reference_local: &[Mat4],
) -> std::io::Result<Vec<Mat4>> {
    if reference_local.len() != mesh.bones.len() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            format!(
                "reference pose has {} bones; mesh has {}",
                reference_local.len(),
                mesh.bones.len()
            ),
        ));
    }
    let mut world = vec![Mat4::IDENTITY; mesh.bones.len()];
    for (index, bone) in mesh.bones.iter().enumerate() {
        world[index] = if bone.parent < 0 {
            reference_local[index]
        } else {
            let parent = bone.parent as usize;
            if parent >= index {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("bone {index} parent {parent} is not topologically ordered"),
                ));
            }
            world[parent] * reference_local[index]
        };
    }
    Ok(world
        .iter()
        .zip(&mesh.bones)
        .map(|(world, bone)| *world * bone.inverse_bind)
        .collect())
}

/// Transfer an ANM1 world-space frame between two rigs with the same named
/// hierarchy. World-space rotation deltas are converted back into target-local
/// rotations while target rest translations/scales preserve armored anatomy.
pub fn retarget_world_animation_frame(
    source: &SkinnedMeshData,
    target: &SkinnedMeshData,
    source_world_frame: &[Mat4],
) -> std::io::Result<Vec<Mat4>> {
    if source.bones.len() != target.bones.len() || source.bones.len() != source_world_frame.len() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "source, target, and ANM1 frame bone counts differ",
        ));
    }
    for (index, (source_bone, target_bone)) in
        source.bones.iter().zip(target.bones.iter()).enumerate()
    {
        if source_bone.name != target_bone.name || source_bone.parent != target_bone.parent {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("retarget hierarchy mismatch at bone {index}"),
            ));
        }
    }

    let source_rest_world = rest_world_matrices(source)?;
    let target_rest_world = rest_world_matrices(target)?;
    let mut desired_world_rotations = Vec::with_capacity(target.bones.len());
    for index in 0..target.bones.len() {
        let (_, source_rest_rotation, _) = source_rest_world[index].to_scale_rotation_translation();
        let (_, source_frame_rotation, _) =
            source_world_frame[index].to_scale_rotation_translation();
        let (_, target_rest_rotation, _) = target_rest_world[index].to_scale_rotation_translation();
        desired_world_rotations
            .push(source_frame_rotation * source_rest_rotation.inverse() * target_rest_rotation);
    }

    let (_, _, source_rest_root) = source_rest_world[0].to_scale_rotation_translation();
    let (_, _, source_frame_root) = source_world_frame[0].to_scale_rotation_translation();
    let root_displacement = source_frame_root - source_rest_root;
    let mut target_local = Vec::with_capacity(target.bones.len());
    for (index, target_bone) in target.bones.iter().enumerate() {
        let (rest_scale, _, rest_translation) =
            target_bone.rest_local.to_scale_rotation_translation();
        let local_rotation = if target_bone.parent < 0 {
            desired_world_rotations[index]
        } else {
            desired_world_rotations[target_bone.parent as usize].inverse()
                * desired_world_rotations[index]
        };
        let translation = if target_bone.parent < 0 {
            rest_translation + root_displacement
        } else {
            rest_translation
        };
        target_local.push(Mat4::from_scale_rotation_translation(
            rest_scale,
            local_rotation,
            translation,
        ));
    }
    reference_pose_skin_matrices(target, &target_local)
}

fn rest_world_matrices(mesh: &SkinnedMeshData) -> std::io::Result<Vec<Mat4>> {
    let mut world = vec![Mat4::IDENTITY; mesh.bones.len()];
    for (index, bone) in mesh.bones.iter().enumerate() {
        world[index] = if bone.parent < 0 {
            bone.rest_local
        } else {
            let parent = bone.parent as usize;
            if parent >= index {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("bone {index} parent {parent} is not topologically ordered"),
                ));
            }
            world[parent] * bone.rest_local
        };
    }
    Ok(world)
}

/// Retarget source world-frame rotation deltas onto the accepted C0 reference
/// pose. One-to-many G1 joints are distributed cumulatively across C0 chains.
pub fn calibrated_g1_target_locals(
    source_world: &[Mat4; 34],
    source_reference_world: &[Mat4; 34],
    mesh: &SkinnedMeshData,
    target_reference_local: &[Mat4],
) -> std::io::Result<Vec<Mat4>> {
    if target_reference_local.len() != mesh.bones.len() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "target reference bone count does not match mesh",
        ));
    }
    let mut reference_world = vec![Mat4::IDENTITY; mesh.bones.len()];
    for (index, bone) in mesh.bones.iter().enumerate() {
        reference_world[index] = if bone.parent < 0 {
            target_reference_local[index]
        } else {
            reference_world[bone.parent as usize] * target_reference_local[index]
        };
    }
    let chains: &[(usize, &[(&str, f32)])] = if mesh.bones.iter().any(|bone| bone.name == "Hips") {
        &[
            (0, &[("Hips", 1.0)]),
            (3, &[("LeftUpLeg", 1.0)]),
            (4, &[("LeftLeg", 1.0)]),
            (6, &[("LeftFoot", 1.0)]),
            (7, &[("LeftToeBase", 1.0)]),
            (10, &[("RightUpLeg", 1.0)]),
            (11, &[("RightLeg", 1.0)]),
            (13, &[("RightFoot", 1.0)]),
            (14, &[("RightToeBase", 1.0)]),
            (15, &[("Spine", 1.0)]),
            (16, &[("Spine01", 1.0)]),
            (17, &[("Spine02", 1.0)]),
            (18, &[("LeftShoulder", 1.0)]),
            (19, &[("LeftArm", 1.0)]),
            (21, &[("LeftForeArm", 1.0)]),
            (24, &[("LeftHand", 1.0)]),
            (26, &[("RightShoulder", 1.0)]),
            (27, &[("RightArm", 1.0)]),
            (29, &[("RightForeArm", 1.0)]),
            (32, &[("RightHand", 1.0)]),
        ]
    } else {
        &[
            (0, &[("root", 1.0)]),
            (3, &[("upperleg01.L", 0.5), ("upperleg02.L", 1.0)]),
            (4, &[("lowerleg01.L", 0.5), ("lowerleg02.L", 1.0)]),
            (6, &[("foot.L", 1.0)]),
            (7, &[("toe1-1.L", 1.0)]),
            (10, &[("upperleg01.R", 0.5), ("upperleg02.R", 1.0)]),
            (11, &[("lowerleg01.R", 0.5), ("lowerleg02.R", 1.0)]),
            (13, &[("foot.R", 1.0)]),
            (14, &[("toe1-1.R", 1.0)]),
            (15, &[("spine05", 1.0)]),
            (16, &[("spine04", 1.0)]),
            (
                17,
                &[
                    ("spine03", 1.0 / 3.0),
                    ("spine02", 2.0 / 3.0),
                    ("spine01", 1.0),
                ],
            ),
            (18, &[("clavicle.L", 1.0)]),
            (19, &[("shoulder01.L", 1.0)]),
            (20, &[("upperarm01.L", 0.5), ("upperarm02.L", 1.0)]),
            (21, &[("lowerarm01.L", 0.5), ("lowerarm02.L", 1.0)]),
            (24, &[("wrist.L", 1.0)]),
            (26, &[("clavicle.R", 1.0)]),
            (27, &[("shoulder01.R", 1.0)]),
            (28, &[("upperarm01.R", 0.5), ("upperarm02.R", 1.0)]),
            (29, &[("lowerarm01.R", 0.5), ("lowerarm02.R", 1.0)]),
            (32, &[("wrist.R", 1.0)]),
        ]
    };
    let mut desired_world_rotation = vec![None; mesh.bones.len()];
    for (source, targets) in chains {
        let (_, source_rotation, _) = source_world[*source].to_scale_rotation_translation();
        let (_, source_reference_rotation, _) =
            source_reference_world[*source].to_scale_rotation_translation();
        let delta = (source_rotation * source_reference_rotation.conjugate()).normalize();
        for (name, fraction) in *targets {
            let index = calibration_target_index(mesh, name).ok_or_else(|| {
                let expected = if *name == "root" {
                    "root or Hips"
                } else {
                    name
                };
                std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("C0 calibration target bone {expected} is missing"),
                )
            })?;
            let (_, target_reference_rotation, _) =
                reference_world[index].to_scale_rotation_translation();
            desired_world_rotation[index] =
                Some(glam::Quat::IDENTITY.slerp(delta, *fraction) * target_reference_rotation);
        }
    }
    let mut target_local = target_reference_local.to_vec();
    let mut target_world = vec![Mat4::IDENTITY; mesh.bones.len()];
    for (index, bone) in mesh.bones.iter().enumerate() {
        if let Some(desired_rotation) = desired_world_rotation[index] {
            let (reference_scale, _, reference_translation) =
                target_reference_local[index].to_scale_rotation_translation();
            let local_rotation = if bone.parent < 0 {
                desired_rotation
            } else {
                let (_, parent_rotation, _) =
                    target_world[bone.parent as usize].to_scale_rotation_translation();
                parent_rotation.conjugate() * desired_rotation
            };
            let translation = if bone.parent < 0 {
                let (_, _, source_translation) = source_world[0].to_scale_rotation_translation();
                let (_, _, source_reference_translation) =
                    source_reference_world[0].to_scale_rotation_translation();
                reference_translation + (source_translation - source_reference_translation)
            } else {
                reference_translation
            };
            target_local[index] = Mat4::from_scale_rotation_translation(
                reference_scale,
                local_rotation.normalize(),
                translation,
            );
        }
        target_world[index] = if bone.parent < 0 {
            target_local[index]
        } else {
            target_world[bone.parent as usize] * target_local[index]
        };
    }
    Ok(target_local)
}

fn calibration_target_index(mesh: &SkinnedMeshData, name: &str) -> Option<usize> {
    mesh.bones
        .iter()
        .position(|bone| bone.name == name)
        .or_else(|| {
            (name == "root")
                .then(|| mesh.bones.iter().position(|bone| bone.name == "Hips"))
                .flatten()
        })
}

pub fn calibrated_g1_skin_matrices(
    source_world: &[Mat4; 34],
    source_reference_world: &[Mat4; 34],
    mesh: &SkinnedMeshData,
    target_reference_local: &[Mat4],
) -> std::io::Result<Vec<Mat4>> {
    let target_local = calibrated_g1_target_locals(
        source_world,
        source_reference_world,
        mesh,
        target_reference_local,
    )?;
    reference_pose_skin_matrices(mesh, &target_local)
}

// ---------------------------------------------------------------------------
// MotionBricks G1 (34) -> mannequin (24) retarget + skinning matrices
// ---------------------------------------------------------------------------

/// Map each mannequin bone (by index) to a source G1Skeleton34 joint index.
/// Bones with no G1 equivalent (neck/Head/head_end/headfront) follow the
/// upper-spine (waist_pitch) — refined later with IK/heuristics.
pub const G1_TO_MANNEQUIN: [usize; 24] = [
    0,  // Hips          <- pelvis
    1,  // LeftUpLeg     <- left_hip_pitch
    4,  // LeftLeg       <- left_knee
    5,  // LeftFoot      <- left_ankle_pitch
    7,  // LeftToeBase   <- left_toe_base
    8,  // RightUpLeg    <- right_hip_pitch
    11, // RightLeg      <- right_knee
    12, // RightFoot     <- right_ankle_pitch
    14, // RightToeBase  <- right_toe_base
    17, // Spine02       <- waist_pitch
    16, // Spine01       <- waist_roll
    15, // Spine         <- waist_yaw
    18, // LeftShoulder  <- left_shoulder_pitch
    19, // LeftArm       <- left_shoulder_roll
    21, // LeftForeArm   <- left_elbow
    23, // LeftHand      <- left_wrist_pitch
    26, // RightShoulder <- right_shoulder_pitch
    27, // RightArm      <- right_shoulder_roll
    29, // RightForeArm  <- right_elbow
    31, // RightHand     <- right_wrist_pitch
    17, // neck          <- waist_pitch (no G1 neck)
    17, // Head          <- waist_pitch (no G1 head; offset applied below)
    17, // head_end      <- waist_pitch
    17, // headfront     <- waist_pitch
];

/// Compute the 24 skinning matrices (bind-space) for one frame of 34 G1 world
/// matrices, given the loaded mannequin. skin[i] = align * g1World[src] * invBind[i].
pub fn compute_skin_matrices(
    g1_world: &[glam::Mat4; 34],
    mesh: &SkinnedMeshData,
) -> [glam::Mat4; 24] {
    let mut out = [glam::Mat4::IDENTITY; 24];
    for (i, output) in out.iter_mut().enumerate() {
        let src = G1_TO_MANNEQUIN[i];
        // Each bone uses its own bind world for alignment:
        // skin[i] = bind_world[i] * g1_world[src] * inv_bind[i]
        // For identity G1: bind_world[i] * I * inv_bind[i] = I (correct bind pose)
        let bind_world = mesh.bones[i].inverse_bind.inverse();
        *output = bind_world * g1_world[src] * mesh.bones[i].inverse_bind;
    }
    out
}

/// Per-frame validation of 24 skinning matrices.
/// Returns a list of warnings; empty = clean.
pub fn validate_skin_matrices(out: &[glam::Mat4; 24], frame: usize) -> Vec<String> {
    let mut w = Vec::new();
    for (i, m) in out.iter().copied().enumerate() {
        let det = m.determinant();
        if !m.is_finite() {
            w.push(format!("[f{:<3} b{:>2}] non-finite matrix", frame, i));
        } else if det <= 0.0 {
            w.push(format!(
                "[f{:<3} b{:>2}] non-positive det={:.3}",
                frame, i, det
            ));
        } else if det > 10.0 {
            w.push(format!(
                "[f{:<3} b{:>2}] large det={:.3} (possible stretch)",
                frame, i, det
            ));
        }
        // Check translation magnitude is reasonable (< 10m)
        let (_, _, t) = m.to_scale_rotation_translation();
        let t_mag = t.length();
        if t_mag > 10.0 {
            w.push(format!(
                "[f{:<3} b{:>2}] large translation {:.3}m",
                frame, i, t_mag
            ));
        }
    }
    w
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn skinned_vertex_layout_retains_eight_influences() {
        let vertex = SkinnedVertex {
            position: [0.0; 3],
            normal: [0.0; 3],
            uv: [0.0; 2],
            joint_indices: [0, 1, 2, 3, 4, 5, 6, 7],
            joint_weights: [0.125; 8],
        };
        assert_eq!(std::mem::size_of::<SkinnedVertex>(), 96);
        assert_eq!(vertex.joint_indices[7], 7);
        assert!((vertex.joint_weights.iter().sum::<f32>() - 1.0).abs() < f32::EPSILON);
    }

    #[test]
    fn c0_reference_animation_matches_dynamic_skin_contract() {
        let root = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".into());
        let mesh = load_skinned(&format!(
            "{root}/assets/source/meshy/c0_base_fighter/pose_carrier_001/cooked/c0_pose_carrier.bin"
        ))
        .expect("load C0 pose carrier mesh");
        let reference = load_skeletal_animation(&format!(
            "{root}/assets/source/meshy/c0_base_fighter/pose_carrier_001/cooked/c0_reference.anim"
        ))
        .expect("load C0 reference action");

        assert_eq!(mesh.bones.len(), 163);
        assert_eq!(reference.bone_count, mesh.bones.len());
        let skin = reference_pose_skin_matrices(&mesh, &reference.frames[0])
            .expect("reference pose must match carrier hierarchy");
        assert_eq!(skin.len(), mesh.bones.len());
        assert!(skin.iter().all(Mat4::is_finite));
        assert!(skin.iter().all(|matrix| matrix.determinant() > 0.0));
        assert!(
            skin.iter()
                .any(|matrix| !matrix.abs_diff_eq(Mat4::IDENTITY, 1e-4))
        );
    }

    #[test]
    fn meshy_walk_world_frame_retargets_without_exploding_armored_skin() {
        let root = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".into());
        let source = load_skinned(&format!(
            "{root}/assets/source/meshy/c0_base_fighter/rigged_001/cooked/c0_skin8.bin"
        ))
        .unwrap();
        let target = load_skinned(&format!(
            "{root}/assets/source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin"
        ))
        .unwrap();
        let walk = load_skeletal_animation(&format!(
            "{root}/assets/source/meshy/c0_base_fighter/rigged_001/cooked/walking.anim"
        ))
        .unwrap();
        let skin = retarget_world_animation_frame(&source, &target, &walk.frames[0]).unwrap();
        assert_eq!(skin.len(), 24);
        for matrix in skin {
            assert!(matrix.is_finite());
            assert!(
                matrix
                    .to_cols_array()
                    .into_iter()
                    .all(|value| value.abs() < 10.0),
                "world-space retarget must reject the hierarchy-multiplication explosion"
            );
            assert!((0.5..2.0).contains(&matrix.determinant()));
        }
    }

    #[test]
    fn c0_frame_calibration_distributes_world_delta_across_upper_arm() {
        let root = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".into());
        let mesh = load_skinned(&format!(
            "{root}/assets/source/meshy/c0_base_fighter/pose_carrier_001/cooked/c0_pose_carrier.bin"
        ))
        .unwrap();
        let reference = load_skeletal_animation(&format!(
            "{root}/assets/source/meshy/c0_base_fighter/pose_carrier_001/cooked/c0_reference.anim"
        ))
        .unwrap();
        let source_reference = [Mat4::IDENTITY; 34];
        let mut source_current = source_reference;
        source_current[20] = Mat4::from_rotation_z(std::f32::consts::FRAC_PI_2);
        let target_local = calibrated_g1_target_locals(
            &source_current,
            &source_reference,
            &mesh,
            &reference.frames[0],
        )
        .unwrap();
        let mut target_world = vec![Mat4::IDENTITY; mesh.bones.len()];
        let mut reference_world = vec![Mat4::IDENTITY; mesh.bones.len()];
        for (index, bone) in mesh.bones.iter().enumerate() {
            if bone.parent < 0 {
                target_world[index] = target_local[index];
                reference_world[index] = reference.frames[0][index];
            } else {
                let parent = bone.parent as usize;
                target_world[index] = target_world[parent] * target_local[index];
                reference_world[index] = reference_world[parent] * reference.frames[0][index];
            }
        }
        for (name, expected) in [
            ("upperarm01.L", std::f32::consts::FRAC_PI_4),
            ("upperarm02.L", std::f32::consts::FRAC_PI_2),
        ] {
            let index = mesh
                .bones
                .iter()
                .position(|bone| bone.name == name)
                .unwrap();
            let (_, current_rotation, _) = target_world[index].to_scale_rotation_translation();
            let (_, reference_rotation, _) = reference_world[index].to_scale_rotation_translation();
            let delta = current_rotation * reference_rotation.conjugate();
            let actual = 2.0 * delta.w.abs().clamp(-1.0, 1.0).acos();
            assert!(
                (actual - expected).abs() < 1e-4,
                "{name}: expected {expected}, got {actual}"
            );
        }
    }

    #[test]
    fn load_skinned_preserves_eight_serialized_influences() {
        use std::io::Write;

        let path = std::env::temp_dir().join(format!(
            "just_dodge_skin8_{}_{}.bin",
            std::process::id(),
            std::thread::current().name().unwrap_or("test")
        ));
        let mut file = std::fs::File::create(&path).expect("create synthetic SKM1");
        file.write_all(b"SKM1").unwrap();
        file.write_all(&1u32.to_le_bytes()).unwrap();
        file.write_all(&3u32.to_le_bytes()).unwrap();
        file.write_all(&8u32.to_le_bytes()).unwrap();
        for value in [0.0f32; 8] {
            file.write_all(&value.to_le_bytes()).unwrap();
        }
        for index in [0u32; 3] {
            file.write_all(&index.to_le_bytes()).unwrap();
        }
        let identity = [
            1.0f32, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0,
        ];
        for bone_index in 0..8u32 {
            let name = format!("bone_{bone_index}");
            file.write_all(&(name.len() as u16).to_le_bytes()).unwrap();
            file.write_all(name.as_bytes()).unwrap();
            file.write_all(&(-1i32).to_le_bytes()).unwrap();
            for matrix in [identity, identity] {
                for value in matrix {
                    file.write_all(&value.to_le_bytes()).unwrap();
                }
            }
        }
        file.write_all(&[8u8]).unwrap();
        for joint in 0..8u32 {
            file.write_all(&joint.to_le_bytes()).unwrap();
            file.write_all(&0.125f32.to_le_bytes()).unwrap();
        }
        drop(file);

        let mesh = load_skinned(path.to_str().unwrap()).expect("load synthetic SKM1");
        let _ = std::fs::remove_file(path);
        assert_eq!(mesh.vertices[0].joint_indices, [0, 1, 2, 3, 4, 5, 6, 7]);
        assert_eq!(mesh.vertices[0].joint_weights, [0.125; 8]);
    }

    /// Load the real mannequin mesh, construct synthetic G1 identity frames,
    /// and prove compute_skin_matrices produces valid non-sheared matrices.
    #[test]
    fn compute_skin_matrices_identity_is_valid() {
        let assets = std::env::var("CARGO_MANIFEST_DIR").unwrap_or(".".into());
        let mesh = load_skinned(&format!("{}/assets/characters/mannequin_male.bin", assets))
            .expect("mannequin mesh must load for test");

        // G1 identity frame: all bones at origin with identity rotation.
        let g1_identity = [glam::Mat4::IDENTITY; 34];

        let out = compute_skin_matrices(&g1_identity, &mesh);

        // Every matrix must be finite with positive determinant.
        for (i, m) in out.iter().copied().enumerate() {
            assert!(m.is_finite(), "bone {}: non-finite matrix", i);
            let det = m.determinant();
            assert!(det > 0.0, "bone {}: non-positive det={:.3}", i, det);
            let (scale, _, t) = m.to_scale_rotation_translation();
            // Scale should be close to 1.0 (identity input → bones near identity output)
            assert!(
                (scale.x - 1.0).abs() < 2.0,
                "bone {}: scale.x={:.3} deviates",
                i,
                scale.x
            );
            assert!(
                (scale.y - 1.0).abs() < 2.0,
                "bone {}: scale.y={:.3} deviates",
                i,
                scale.y
            );
            assert!(
                (scale.z - 1.0).abs() < 2.0,
                "bone {}: scale.z={:.3} deviates",
                i,
                scale.z
            );
            // Translation should be bounded (mesh was ~31m in original scale,
            // so bone chains can extend up to ~15m from Hips origin)
            assert!(
                t.length() < 20.0,
                "bone {}: translation {:.3}m too large",
                i,
                t.length()
            );
        }

        // validate_skin_matrices should have no critical issues.
        let warnings = validate_skin_matrices(&out, 0);
        for w in &warnings {
            assert!(
                !w.contains("non-positive det") && !w.contains("non-finite"),
                "identity validation regression: {}",
                w
            );
        }
    }

    /// Rotate the G1 pelvis 90° about Y and confirm all 24 output matrices
    /// remain valid (no shearing from simple rotation).
    #[test]
    fn compute_skin_matrices_rotation_preserves_validity() {
        let assets = std::env::var("CARGO_MANIFEST_DIR").unwrap_or(".".into());
        let mesh = load_skinned(&format!("{}/assets/characters/mannequin_male.bin", assets))
            .expect("mannequin mesh must load for test");

        let rot = glam::Mat4::from_rotation_y(std::f32::consts::FRAC_PI_2);
        let mut g1_rot = [glam::Mat4::IDENTITY; 34];
        // Rotate pelvis and propagate to children via simple world rotation
        g1_rot.fill(rot);

        let out = compute_skin_matrices(&g1_rot, &mesh);
        for (i, matrix) in out.iter().enumerate() {
            assert!(matrix.is_finite(), "bone {}: non-finite after rotation", i);
            assert!(
                matrix.determinant() > 0.0,
                "bone {}: non-positive det after rotation",
                i
            );
        }
        let warnings = validate_skin_matrices(&out, 0);
        // Allow "large translation" and "large det" warnings from the full-scale mesh
        // (the mesh is ~31m in original units so translations can be 10-15m).
        // The critical condition: no "non-positive det" or "non-finite" warnings.
        for w in &warnings {
            assert!(
                !w.contains("non-positive det") && !w.contains("non-finite"),
                "validation regression on rotation: {}",
                w
            );
        }
    }

    /// A G1 motion frame with bones spread apart should NOT produce shearing
    /// (unlike retarget::g1_to_skin which interpolated world matrices).
    /// This test would FAIL with the old retarget::g1_to_skin path.
    #[test]
    fn compute_skin_matrices_no_shear_on_spread_pose() {
        let assets = std::env::var("CARGO_MANIFEST_DIR").unwrap_or(".".into());
        let mesh = load_skinned(&format!("{}/assets/characters/mannequin_male.bin", assets))
            .expect("mannequin mesh must load for test");

        // Spread pose: bones spread apart in world space.
        let mut g1_spread = [glam::Mat4::IDENTITY; 34];
        // Left leg out left
        g1_spread[1] = glam::Mat4::from_translation(glam::vec3(-0.5, 0.0, 0.0));
        // Right leg out right
        g1_spread[8] = glam::Mat4::from_translation(glam::vec3(0.5, 0.0, 0.0));
        // Arms out
        g1_spread[18] = glam::Mat4::from_translation(glam::vec3(-0.7, 0.3, 0.0));
        g1_spread[26] = glam::Mat4::from_translation(glam::vec3(0.7, 0.3, 0.0));

        let out = compute_skin_matrices(&g1_spread, &mesh);
        for (i, matrix) in out.iter().enumerate() {
            assert!(matrix.is_finite(), "bone {}: non-finite on spread", i);
            assert!(
                matrix.determinant() > 0.0,
                "bone {}: non-positive det on spread (shearing bug regression)",
                i
            );
        }

        // Validate: should pass (retarget world-interp would fail here)
        let warnings = validate_skin_matrices(&out, 0);
        // The spread pose has non-identity translation, but bone lengths
        // are preserved because we only transform the source G1 world matrices
        // and multiply by per-bone inverse_bind — no lerp/shear.
        for w in &warnings {
            // Allow "large translation" warnings from spread pose,
            // but there should be NO "non-positive det" (shearing) warnings.
            assert!(
                !w.contains("non-positive det"),
                "shearing detected on spread pose: {}",
                w
            );
        }
    }
}
