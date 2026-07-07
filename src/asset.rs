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
// Skinned mesh (SKM1) + baked animation (ANM1)
// ---------------------------------------------------------------------------

/// Interleaved vertex for the skinning pipeline. 64 bytes stride.
#[repr(C)]
#[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
pub struct SkinnedVertex {
    pub position: [f32; 3],
    pub normal: [f32; 3],
    pub uv: [f32; 2],
    pub joint_indices: [u32; 4],
    pub joint_weights: [f32; 4],
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

pub struct AnimData {
    pub bone_count: u32,
    pub fps: u16,
    pub frame_count: u32,
    /// frames[f][bone] = parent-relative local matrix (column-major Mat4)
    pub frames: Vec<Vec<Mat4>>,
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
            joint_indices: [0; 4],
            joint_weights: [0.0; 4],
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
        // Keep top 4 by weight, normalize to sum=1.0 (shader expects Σwᵢ=1).
        influences.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        let mut ji = [0u32; 4];
        let mut jw = [0.0f32; 4];
        for (k, (j, w)) in influences.iter().take(4).enumerate() {
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

pub fn load_anim(path: &str) -> std::io::Result<AnimData> {
    let f = File::open(path)?;
    let mut r = BufReader::new(f);

    let mut magic = [0u8; 4];
    r.read_exact(&mut magic)?;
    assert_eq!(&magic, b"ANM1", "not an ANM1 animation");
    let bone_count = rd_u32(&mut r)?;
    let fps = rd_u16(&mut r)?;
    let frame_count = rd_u32(&mut r)?;

    let mut frames = Vec::with_capacity(frame_count as usize);
    for _ in 0..frame_count {
        let mut fm = Vec::with_capacity(bone_count as usize);
        for _ in 0..bone_count {
            fm.push(rd_mat4(&mut r)?);
        }
        frames.push(fm);
    }

    Ok(AnimData {
        bone_count,
        fps,
        frame_count,
        frames,
    })
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
    // align: map G1 pelvis world -> mannequin Hips bind world.
    let g1_pelvis = g1_world[0];
    let hips_bind = mesh.bones[0].inverse_bind.inverse(); // Hips bind world (mesh space)
    let align = hips_bind * g1_pelvis.inverse();
    let mut out = [glam::Mat4::IDENTITY; 24];
    for i in 0..24 {
        let src = G1_TO_MANNEQUIN[i];
        let g1_in_mesh = align * g1_world[src];
        out[i] = g1_in_mesh * mesh.bones[i].inverse_bind;
    }
    out
}
