// MotionBricks ONNX inference pipeline — ort v2 API
//
// Architecture:
//   1. VQVAE Encoder: motion_frames[B, C, T] -> quantized_features[B, 256, T/4]
//   2. Codebook: 8 heads x 10 codes x 32 dim — nearest-neighbour search in Rust
//   3. VQVAE Decoder: quantized[B, 256, T/4] -> reconstructed[B, T, out_dim]
//   4. Pose Transformer: tokens + conditions -> pose_logits[B, N, 8, 11]
//   5. Root: conditions -> pred_global_root[B, T, 5]

use anyhow::{Context, Result};
use crate::asset::SkinnedMeshData;
use glam::Mat4;
use ndarray::{Array, Array2, ArrayD, IxDyn};
use ort::session::Session;
use ort::value::{DynValue, Tensor};
use std::path::{Path, PathBuf};

/// Combat action used to condition MotionBricks generation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Action {
    Strike,
    Block,
    Grab,
    Idle,
}

/// High-level stance/side for the action.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Stance {
    Top,
    Left,
    Right,
}

/// Full condition describing the desired action clip.
#[derive(Debug, Clone)]
pub struct ActionCondition {
    pub action: Action,
    pub stance: Stance,
    pub from_pose: [Mat4; 34],
}

/// Full MotionBricks inference pipeline
pub struct MotionPipeline {
    encoder: Session,
    decoder: Session,
    _pose_transformer: Session,
    _root_shared: Session,
    _root_token: Option<Session>,
    _root_conv: Session,
    /// Codebook: [num_heads=8, num_codes=10, code_dim=32]
    codebook: ArrayD<f32>,
    pub meta: MotionMeta,
    /// Directory from which the ONNX/NPY artifacts were loaded.
    /// Used to give clear error messages if artifacts are missing at runtime.
    assets_path: Option<PathBuf>,
}

/// Metadata describing model dimensions
pub struct MotionMeta {
    pub num_pose_heads: usize,
    pub num_codes_per_head: usize,
    pub code_dim: usize,
    pub code_dim_per_head: usize,
    pub down_t: usize,
    pub num_frames_per_token: usize,
    pub encoder_in_channels: usize,
    pub decoder_out_channels: usize,
}

impl MotionPipeline {
    /// Load all models from the assets directory
    pub fn new(assets_path: &str) -> Result<Self> {
        let base = Path::new(assets_path);

        let t0 = std::time::Instant::now();
        let mut b = Session::builder()?;
        let encoder = b
            .commit_from_file(base.join("motionbricks_vqvae_encoder.onnx"))
            .context("Failed to load VQVAE encoder")?;
        eprintln!("[MotionPipeline] encoder loaded in {:.2}s", t0.elapsed().as_secs_f32());

        let t0 = std::time::Instant::now();
        let mut b = Session::builder()?;
        let decoder = b
            .commit_from_file(base.join("motionbricks_vqvae_decoder.fixed.onnx"))
            .context("Failed to load VQVAE decoder")?;
        eprintln!("[MotionPipeline] decoder loaded in {:.2}s", t0.elapsed().as_secs_f32());

        let mut b = Session::builder()?;
        let t0 = std::time::Instant::now();
        let pose_transformer = b
            .commit_from_file(base.join("motionbricks_pose_transformer.onnx"))
            .context("Failed to load pose transformer")?;
        eprintln!("[MotionPipeline] pose_transformer loaded in {:.2}s", t0.elapsed().as_secs_f32());

        let mut b = Session::builder()?;
        let t0 = std::time::Instant::now();
        let root_shared = b
            .commit_from_file(base.join("motionbricks_root_shared.onnx"))
            .context("Failed to load root shared transformer")?;
        eprintln!("[MotionPipeline] root_shared loaded in {:.2}s", t0.elapsed().as_secs_f32());

        let root_token = {
            let p = base.join("motionbricks_root_token.onnx");
            if p.exists() {
                let t0 = std::time::Instant::now();
                let mut b = Session::builder()?;
                let rt = b.commit_from_file(p)
                    .context("Failed to load root token transformer")?;
                eprintln!("[MotionPipeline] root_token loaded in {:.2}s", t0.elapsed().as_secs_f32());
                Some(rt)
            } else {
                None
            }
        };

        let t0 = std::time::Instant::now();
        let mut b = Session::builder()?;
        let root_conv = b
            .commit_from_file(base.join("motionbricks_root_conv.onnx"))
            .context("Failed to load root conv decoder")?;
        eprintln!("[MotionPipeline] root_conv loaded in {:.2}s", t0.elapsed().as_secs_f32());

        let t0 = std::time::Instant::now();
        let codebook = Self::load_npy(&base.join("motionbricks_codebook.npy"), &[8, 10, 32])?;
        eprintln!("[MotionPipeline] codebook loaded in {:.2}s", t0.elapsed().as_secs_f32());

        Ok(Self {
            encoder,
            decoder,
            _pose_transformer: pose_transformer,
            _root_shared: root_shared,
            _root_token: root_token,
            _root_conv: root_conv,
            codebook,
            meta: MotionMeta {
                num_pose_heads: 8,
                num_codes_per_head: 10,
                code_dim: 256,
                code_dim_per_head: 32,
                down_t: 2,
                num_frames_per_token: 4,
                encoder_in_channels: 304,
                decoder_out_channels: 413,
            },
            assets_path: Some(base.to_path_buf()),
        })
    }

    /// Load an N-dimensional f32 numpy array
    fn load_npy(path: &Path, shape: &[usize]) -> Result<ArrayD<f32>> {
        let bytes = std::fs::read(path)?;
        if bytes.len() < 10 || &bytes[0..6] != b"\x93NUMPY" {
            anyhow::bail!("Not a valid .npy file");
        }
        let header_len = u16::from_le_bytes([bytes[8], bytes[9]]) as usize;
        let data_start = 10 + header_len;
        let total: usize = shape.iter().product();
        let mut data = vec![0.0f32; total];
        let f32_bytes = &bytes[data_start..];
        for (i, chunk) in f32_bytes.chunks_exact(4).take(total).enumerate() {
            data[i] = f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]);
        }
        let shape_vec: Vec<usize> = shape.to_vec();
        Array::from_shape_vec(IxDyn(&shape_vec), data).map_err(Into::into)
    }

    /// Quantize encoded features using the codebook.
    /// encoded shape: [code_dim=256, time_steps]
    /// Returns indices shape: [num_heads=8, time_steps]
    pub fn quantize(&self, encoded: &ArrayD<f32>) -> Result<Array2<u32>> {
        let time_steps = encoded.shape()[1];
        let num_heads = self.meta.num_pose_heads;
        let cdph = self.meta.code_dim_per_head;
        let num_codes = self.meta.num_codes_per_head;

        let mut indices = Array2::<u32>::zeros((num_heads, time_steps));

        for h in 0..num_heads {
            let base = h * cdph;
            for t in 0..time_steps {
                let mut best_code = 0u32;
                let mut best_dist = f32::MAX;
                for c in 0..num_codes {
                    let mut dist = 0.0f32;
                    for d in 0..cdph {
                        let diff = encoded[[base + d, t]] - self.codebook[[h, c, d]];
                        dist += diff * diff;
                    }
                    if dist < best_dist {
                        best_dist = dist;
                        best_code = c as u32;
                    }
                }
                indices[[h, t]] = best_code;
            }
        }
        Ok(indices)
    }

    /// Dequantize indices to continuous features.
    pub fn dequantize(&self, indices: &Array2<u32>) -> Result<ArrayD<f32>> {
        let (num_heads, time_steps) = (indices.shape()[0], indices.shape()[1]);
        let cdph = self.meta.code_dim_per_head;
        let code_dim = num_heads * cdph;

        let mut features = ArrayD::<f32>::zeros(IxDyn(&[code_dim, time_steps]));
        for h in 0..num_heads {
            for t in 0..time_steps {
                let idx = indices[[h, t]] as usize;
                for d in 0..cdph {
                    features[[h * cdph + d, t]] = self.codebook[[h, idx, d]];
                }
            }
        }
        Ok(features)
    }

    /// Encode motion frames to token indices.
    /// frames shape: [1, encoder_in_channels, n_frames] (ONNX input: 1 batch, C, T)
    pub fn encode_frames(&mut self, frames: &ArrayD<f32>) -> Result<Array2<u32>> {
        let output = self.run_encoder(frames)?;
        let (_, quantized_flat) = output.try_extract_tensor::<f32>()?;

        // Reshape quantized: [1, code_dim, T/4]
        let t_out = quantized_flat.len() / self.meta.code_dim;
        let encoded =
            ArrayD::from_shape_vec(IxDyn(&[self.meta.code_dim, t_out]), quantized_flat.to_vec())?;
        self.quantize(&encoded)
    }

    /// Decode quantized features to motion frames.
    /// quantized shape: [1, code_dim, T/4] (ONNX format — channels-first)
    /// Returns reconstructed motion [1, T, 413] (GlobalRootGlobalJoints global subset).
    pub fn decode_frames(&mut self, quantized: &ArrayD<f32>) -> Result<ArrayD<f32>> {
        let t = quantized.shape()[2];
        let out_frames = t * 4;
        let target_cond_dim = 304usize;
        let external_cond_dim = 2usize;

        let target_cond = ArrayD::<f32>::zeros(IxDyn(&[1, out_frames, target_cond_dim]));
        let external_cond = ArrayD::<f32>::zeros(IxDyn(&[1, out_frames, external_cond_dim]));

        let q_shape: Vec<i64> = quantized.shape().iter().map(|&d| d as i64).collect();
        let t_shape: Vec<i64> = target_cond.shape().iter().map(|&d| d as i64).collect();
        let e_shape: Vec<i64> = external_cond.shape().iter().map(|&d| d as i64).collect();

        let q_flat = quantized.iter().copied().collect::<Vec<f32>>();
        let t_flat = target_cond.iter().copied().collect::<Vec<f32>>();
        let e_flat = external_cond.iter().copied().collect::<Vec<f32>>();

        let q_tensor = Tensor::<f32>::from_array((ort::value::Shape::new(q_shape), q_flat))?;
        let t_tensor = Tensor::<f32>::from_array((ort::value::Shape::new(t_shape), t_flat))?;
        let e_tensor = Tensor::<f32>::from_array((ort::value::Shape::new(e_shape), e_flat))?;

        // Named inputs — decoder graph matches tensors by name, not position.
        let outputs = (&mut self.decoder).run(ort::inputs![
            "quantized" => q_tensor,
            "target_cond" => t_tensor,
            "external_cond" => e_tensor,
        ])?;
        let out_vec: Vec<DynValue> = outputs.into_iter().map(|(_, v)| v).collect();
        let output = out_vec
            .into_iter()
            .next()
            .ok_or_else(|| anyhow::anyhow!("Missing decoder output"))?;
        let (shape, data) = output.try_extract_tensor::<f32>()?;
        let shape_vec: Vec<usize> = shape.iter().map(|&d| d as usize).collect();
        ArrayD::from_shape_vec(IxDyn(&shape_vec), data.to_vec())
            .context("Failed to reshape decoder output")
    }

    /// Convert a continuous 6D rotation vector [x0,y0,z0,x1,y1,z1] to a Mat4 (rotation only).
    pub fn cont6d_to_matrix(v: [f32; 6]) -> Mat4 {
        let v0 = glam::Vec3::new(v[0], v[1], v[2]);
        let v1 = glam::Vec3::new(v[3], v[4], v[5]);
        let v0n = v0.normalize();
        let v1p = v1 - v0n * v0n.dot(v1);
        let v1n = v1p.normalize();
        let v2 = v0n.cross(v1n);
        Mat4::from_cols_array(&[
            v0n.x, v0n.y, v0n.z, 0.0, v1n.x, v1n.y, v1n.z, 0.0, v2.x, v2.y, v2.z, 0.0, 0.0, 0.0,
            0.0, 1.0,
        ])
    }

    /// G1Skeleton34 joint count and parent indices (from motionbricks G1Skeleton34).
    pub const G1_NB: usize = 34;
    pub const G1_PARENTS: [i32; 34] = [
        -1, 0, 1, 2, 3, 4, 5, 6, 0, 8, 9, 10, 11, 12, 13, 0, 15, 16, 17, 18, 19, 20, 21, 22, 23,
        24, 17, 26, 27, 28, 29, 30, 31, 32,
    ];

    /// Parse one decoded GlobalRootGlobalJoints frame [413] into 34 world-space joint Mat4.
    /// Layout (authoritative, from motionbricks source):
    ///   [0,2]   global_root_pos (xyz)
    ///   [3,4]   global_root_heading (cos, sin)
    ///   [5,103] ric_data  (33*3 root-relative joint positions, joints 1..33)
    ///   [104,307] global_rot_data (34*6D global joint rotations)
    ///   [308,409] local_vel (unused)
    ///   [410,413] foot_contacts (unused)
    pub fn parse_g1_frame(rec: &[f32]) -> [Mat4; 34] {
        let mut mats = [Mat4::IDENTITY; 34];
        let root = glam::Vec3::new(rec[0], rec[1], rec[2]);
        let gr = &rec[104..308];
        let ric = &rec[5..104];
        for j in 0..34 {
            let r6 = [
                gr[j * 6],
                gr[j * 6 + 1],
                gr[j * 6 + 2],
                gr[j * 6 + 3],
                gr[j * 6 + 4],
                gr[j * 6 + 5],
            ];
            let rot = Self::cont6d_to_matrix(r6);
            let pos = if j == 0 {
                root
            } else {
                let b = (j - 1) * 3;
                root + glam::Vec3::new(ric[b], ric[b + 1], ric[b + 2])
            };
            let mut m = rot;
            m.w_axis = glam::Vec4::new(pos.x, pos.y, pos.z, 1.0);
            mats[j] = m;
        }
        mats
    }

    /// Run the MotionBricks VQVAE autoencode on an encoder input [1,304,T] and return
    /// one decoded 34-joint world-matrix frame per time step.
    pub fn decode_encoder_input(&mut self, enc_in: &[f32], t: usize) -> Result<Vec<[Mat4; 34]>> {
        let shape: Vec<i64> = vec![1, 304, t as i64];
        let flat: Vec<f32> = enc_in.to_vec();
        let tensor = Tensor::<f32>::from_array((ort::value::Shape::new(shape), flat))?;
        let mut enc_out = (&mut self.encoder).run(ort::inputs!["input_frames" => tensor])?;
        // Use indices output + codebook dequantization (avoids ORT version mismatch on quantized)
        let indices_val = enc_out
            .remove("indices")
            .ok_or_else(|| anyhow::anyhow!("no indices output"))?;
        let (idx_shape, idx_data) = indices_val.try_extract_tensor::<i64>()?;
        let idx_owned: Vec<i64> = idx_data.iter().copied().collect();
        let idx_shape_v: Vec<usize> = idx_shape.iter().map(|&d| d as usize).collect();
        drop(idx_data);
        drop(indices_val);
        drop(enc_out);
        // Dequantize: for each head+time, look up codebook entry
        let nh = idx_shape_v[1];
        let tt = idx_shape_v[2];
        let cd = self.meta.code_dim; // 256
        let cdph = self.meta.code_dim_per_head; // 32
        let mut feats = vec![0f32; cd * tt];
        for h in 0..nh {
            for t2 in 0..tt {
                let code = idx_owned[t2 + h * tt] as usize;
                for d in 0..cdph {
                    feats[t2 * cd + h * cdph + d] = self.codebook[[h, code, d]];
                }
            }
        }
        let q_arr = ArrayD::from_shape_vec(IxDyn(&[1, cd, tt]), feats)
            .context("quantized dequantized")?;
        let rec = self.decode_frames(&q_arr)?; // [1, out_frames, 413]
        let rec_data = rec.as_standard_layout();
        let data = rec_data.as_slice().unwrap();
        let out_frames = rec.shape()[1];
        let mut frames = Vec::with_capacity(out_frames);
        for f in 0..out_frames {
            let base = f * 413;
            let slice = &data[base..base + 413];
            frames.push(Self::parse_g1_frame(slice));
        }
        Ok(frames)
    }

    /// Run encoder on a tensor, return (shape, flat owned data) of quantized output.
    fn encode_to_vec(encoder: &mut Session, tensor: Tensor<f32>) -> Result<(Vec<i64>, Vec<f32>)> {
        let mut enc_out = encoder.run(ort::inputs!["input_frames" => tensor])?;
        let quantized = enc_out
            .remove("quantized")
            .ok_or_else(|| anyhow::anyhow!("no quantized"))?;
        let (shape, view) = quantized.try_extract_tensor::<f32>()?;
        let data = view.to_vec();
        Ok((shape.to_vec(), data))
    }

    /// Build a rest-pose encoder input from the mannequin mesh's bind data.
    /// Uses actual bone world positions from the SKM1 inverse_bind matrices,
    /// producing a much more realistic seed for the VQVAE encoder+decoder.
    /// Channels-first layout matching build_idle_encoder_input.
    pub fn build_mesh_rest_input(&self, t: usize, g1_to_mannequin: &[usize; 24], mesh_bone_ib: &[Mat4]) -> Vec<f32> {
        // Compute mannequin bone world positions from inverse_bind
        let mut mann_world = vec![glam::Vec3::ZERO; mesh_bone_ib.len()];
        for i in 0..mesh_bone_ib.len() {
            let w = mesh_bone_ib[i].inverse();
            mann_world[i] = w.w_axis.truncate();
        }

        // Compute G1 bone root-relative positions from mannequin positions
        // via G1_TO_MANNEQUIN mapping
        let g1_nb = Self::G1_NB;
        let g1_parents = Self::G1_PARENTS;

        let mut g1_world = [glam::Vec3::ZERO; 34];
        for i in 0..34 {
            // Try to find a mannequin bone that maps to this G1 bone
            let mut found = false;
            for mi in 0..24.min(g1_to_mannequin.len()) {
                if g1_to_mannequin[mi] == i {
                    if mi < mann_world.len() {
                        g1_world[i] = mann_world[mi];
                        found = true;
                    }
                    break;
                }
            }
            if !found {
                // Not mapped: interpolate from parent
                let p = g1_parents[i] as usize;
                if p < i && p != usize::MAX {
                    g1_world[i] = g1_world[p] + glam::vec3(0.0, 0.12, 0.0);
                } else {
                    g1_world[i] = mann_world[0]; // fallback to Hips
                }
            }
        }

        let pelvis_y = g1_world[0].y;
        let mut buf = vec![0f32; 1 * 304 * t];
        for f in 0..t {
            let phase = 2.0 * std::f32::consts::PI * (f as f32) / (t as f32);
            let breathe = 0.02 * (phase * 0.5).sin();
            let sway = 0.01 * phase.sin();

            // Rotations: identity 6D for all bones (cont6d: [1,0,0,0,1,0])
            for j in 0..g1_nb {
                let gr_base = f * 304 + j * 6;
                buf[gr_base + 0] = 1.0;
                buf[gr_base + 1] = 0.0;
                buf[gr_base + 2] = 0.0;
                buf[gr_base + 3] = 0.0;
                buf[gr_base + 4] = 1.0;
                buf[gr_base + 5] = 0.0;
            }

            // Positions: root-relative, with subtle idle perturbations
            for j in 0..g1_nb {
                let mut p = g1_world[j];
                // Subtle breathing: Y oscillation
                p.y += breathe;
                // Subtle sway: X oscillation for upper body
                if j >= 15 && j <= 17 { // spine bones
                    p.x += sway;
                }
                let ric = if j == 0 {
                    p // root position (hip height)
                } else {
                    p - g1_world[0] // root-relative
                };
                if j == 0 {
                    buf[f * 304 + 303] = ric.y; // hip height
                } else {
                    let ric_base = f * 304 + 204 + (j - 1) * 3;
                    buf[ric_base + 0] = ric.x;
                    buf[ric_base + 1] = ric.y;
                    buf[ric_base + 2] = ric.z;
                }
            }
        }
        buf
    }

    /// Build a synthetic idle/feedback clip as MotionBricks encoder input [1,304,T].
    /// This is a procedural seed fed through the real MotionBricks VQVAE encoder+decoder;
    /// the decoded output (not this seed) drives the skeleton. Channels-first layout:
    ///   [0..204]   global_rot_data  (34 * 6D global joint rotations)
    ///   [204..303] ric_data         (33 * 3 root-relative joint positions)
    ///   [303]      hip height (pelvis Y)
    pub fn build_idle_encoder_input(&self, t: usize) -> Vec<f32> {
        let mut buf = vec![0f32; 1 * 304 * t];
        let nb = Self::G1_NB;
        let parents = Self::G1_PARENTS;
        for f in 0..t {
            let phase = 2.0 * std::f32::consts::PI * (f as f32) / (t as f32);
            let knee = 0.5 * phase.sin();
            let elbow = 0.4 * (phase * 0.5).sin();
            let hip_y = 0.9 + 0.02 * (phase * 2.0).sin();
            // world rotations: identity except knee/elbow bends about X
            let mut rot = [[0f32; 6]; 34];
            for j in 0..nb {
                // identity 6D rotation
                rot[j] = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0];
            }
            let (s, c) = knee.sin_cos();
            rot[4] = [1.0, 0.0, 0.0, 0.0, c, -s]; // left knee about X
            let (se, ce) = elbow.sin_cos();
            rot[21] = [1.0, 0.0, 0.0, 0.0, ce, -se]; // left elbow about X
            rot[29] = [1.0, 0.0, 0.0, 0.0, ce, -se]; // right elbow about X
            // root-relative positions: simple downward chain from pelvis
            let mut pos = [[0f32; 3]; 34];
            pos[0] = [0.0, hip_y, 0.0];
            for j in 1..nb {
                let p = parents[j] as usize;
                let off = if j % 2 == 0 {
                    [0.0, -0.12, 0.0]
                } else {
                    [0.0, -0.10, 0.0]
                };
                pos[j] = [pos[p][0] + off[0], pos[p][1] + off[1], pos[p][2] + off[2]];
            }
            // write channels-first
            for j in 0..nb {
                let gr_base = f * 304 + j * 6;
                for d in 0..6 {
                    buf[gr_base + d] = rot[j][d];
                }
            }
            for j in 1..nb {
                let ric_base = f * 304 + 204 + (j - 1) * 3;
                buf[ric_base + 0] = pos[j][0] - pos[0][0];
                buf[ric_base + 1] = pos[j][1] - pos[0][1];
                buf[ric_base + 2] = pos[j][2] - pos[0][2];
            }
            buf[f * 304 + 303] = hip_y;
        }
        buf
    }

    fn run_encoder(&mut self, input: &ArrayD<f32>) -> Result<DynValue> {
        let shape: Vec<i64> = input.shape().iter().map(|&d| d as i64).collect();
        let flat: Vec<f32> = input.iter().copied().collect();
        let tensor = Tensor::<f32>::from_array((ort::value::Shape::new(shape), flat))?;
        let mut outputs = (&mut self.encoder).run(ort::inputs!["input_frames" => tensor])?;
        outputs
            .remove("quantized")
            .ok_or_else(|| anyhow::anyhow!("Missing 'quantized' output"))
    }
}

/// Build procedural G1 frames directly (no ONNX VQVAE dependency).
/// Uses mannequin mesh rest-pose positions with subtle idle motion
/// (breathing, knee bend, arm sway). Returns Vec<[Mat4; 34]> ready for
/// compute_skin_matrices.
pub fn build_procedural_g1_clip(
    frame_count: usize,
    mesh: &SkinnedMeshData,
    g1_to_mannequin: &[usize; 24],
) -> Vec<[Mat4; 34]> {
    // Compute G1 bone rest-pose world positions from mannequin inverse_bind
    let nb = 34usize;
    let parents = MotionPipeline::G1_PARENTS;
    let mut g1_world = [glam::Vec3::ZERO; 34];
    for i in 0..nb {
        let mut found = false;
        for mi in 0..24.min(g1_to_mannequin.len()) {
            if g1_to_mannequin[mi] == i && mi < mesh.bones.len() {
                let w = mesh.bones[mi].inverse_bind.inverse();
                g1_world[i] = w.w_axis.truncate();
                found = true;
                break;
            }
        }
        if !found {
            let p = parents[i] as usize;
            if p < i && p != usize::MAX {
                g1_world[i] = g1_world[p] + glam::vec3(0.0, 0.12, 0.0);
            } else {
                g1_world[i] = g1_world[0].max(g1_world[0] + glam::vec3(0.0, 0.02, 0.0));
            }
        }
    }

    let mut frames = Vec::with_capacity(frame_count);
    for f in 0..frame_count {
        let phase = 2.0 * std::f32::consts::PI * (f as f32) / (frame_count as f32);
        let breathe = (phase * 0.5).sin() * 0.015;
        let knee_angle = phase.sin() * 0.15;
        let elbow_angle = (phase * 0.5).sin() * 0.1;
        let hip_sway = phase.sin() * 0.05;

        let mut frame = [Mat4::IDENTITY; 34];

        // Root (pelvis): translate with breathing
        frame[0] = Mat4::from_translation(g1_world[0] + glam::vec3(0.0, breathe, 0.0));

        for i in 1..nb {
            let pos = g1_world[i];
            let p = parents[i] as usize;

            // Determine rotation based on bone type
            let bend = match i {
                // Left knee
                4 => Mat4::from_rotation_x(knee_angle),
                // Right knee
                11 => Mat4::from_rotation_x(knee_angle),
                // Left/right elbow
                21 | 29 => Mat4::from_rotation_x(elbow_angle),
                // Left hip
                1 => Mat4::from_rotation_z(hip_sway * 0.5),
                // Right hip
                8 => Mat4::from_rotation_z(-hip_sway * 0.5),
                // Spine: waist_yaw, waist_roll, waist_pitch - slight torso sway
                15 => Mat4::from_rotation_z(hip_sway * 0.3),
                16 => Mat4::IDENTITY,
                17 => Mat4::from_rotation_x(hip_sway * 0.2),
                // Shoulders follow spine
                _ => Mat4::IDENTITY,
            };

            // World matrix = parent_world * local_matrix
            // local_matrix = bend * translation_to_parent
            let parent_pos = g1_world[p];
            let to_parent = pos - parent_pos;
            frame[i] = frame[p] * bend * Mat4::from_translation(to_parent);
        }
        frames.push(frame);
    }
    frames
}

/// Parse G1 frames from raw float32 bytes (same layout as .g1 files).
pub fn load_g1_frames_from_bytes(data: &[u8]) -> Result<Vec<[Mat4; 34]>> {
    if data.len() % (413 * 4) != 0 {
        anyhow::bail!(
            "G1 byte length {} not a multiple of frame size {}",
            data.len(),
            413 * 4
        );
    }
    let frame_count = data.len() / (413 * 4);
    let floats = bytemuck::cast_slice::<u8, f32>(data);
    let mut frames = Vec::with_capacity(frame_count);
    for f in 0..frame_count {
        let base = f * 413;
        frames.push(MotionPipeline::parse_g1_frame(&floats[base..base + 413]));
    }
    Ok(frames)
}

/// Load G1 frames from a binary file exported by the MotionBricks Python pipeline.
/// Format: raw float32 data, each frame = 413 floats (same as parse_g1_frame layout).
/// Returns Vec<[Mat4; 34]> ready for compute_skin_matrices.
pub fn load_g1_frames(path: &str) -> Result<Vec<[Mat4; 34]>> {
    let data = std::fs::read(path).map_err(|e| anyhow::anyhow!("Failed to read {path}: {e}"))?;
    load_g1_frames_from_bytes(&data)
}


// ---------------------------------------------------------------------------
// Action-conditioned MotionBricks generation
// ---------------------------------------------------------------------------

/// G1Skeleton34 joint indices used for action seed authoring.
const LEFT_SHOULDER: usize = 18;
const LEFT_UPPER_ARM: usize = 19;
const LEFT_ELBOW: usize = 21;
const LEFT_WRIST: usize = 23;
const RIGHT_SHOULDER: usize = 26;
const RIGHT_UPPER_ARM: usize = 27;
const RIGHT_ELBOW: usize = 29;
const RIGHT_WRIST: usize = 31;
const WAIST_YAW: usize = 15;
const WAIST_PITCH: usize = 17;

/// Inverse of `MotionPipeline::cont6d_to_matrix`: extract the first two
/// orthonormal columns of a rotation matrix as a 6D continuous rotation.
fn matrix_to_cont6d(m: Mat4) -> [f32; 6] {
    let mut a = m.x_axis.truncate();
    let mut b = m.y_axis.truncate();
    if a.length_squared() < 1e-6 {
        a = glam::Vec3::X;
    } else {
        a = a.normalize();
    }
    b = b - a * a.dot(b);
    if b.length_squared() < 1e-6 {
        b = glam::Vec3::Y;
    } else {
        b = b.normalize();
    }
    [a.x, a.y, a.z, b.x, b.y, b.z]
}

/// Write a 6D global rotation for `joint` into a single encoder-input frame.
fn write_rot6d(frame: &mut [f32], joint: usize, rot: Mat4) {
    let gr = matrix_to_cont6d(rot);
    let base = joint * 6;
    frame[base..base + 6].copy_from_slice(&gr);
}

/// Build the encoder input [1, 304, T] for an action condition.
/// Uses `from_pose` as the base and overwrites key joint rotations to encode
/// the desired action intent.
fn build_action_encoder_input(condition: &ActionCondition, frames: usize) -> Vec<f32> {
    let mut buf = vec![0f32; 1 * 304 * frames];

    // Pre-compute base rotations and positions from the current pose.
    let mut base_rot6d = [[0f32; 6]; 34];
    let mut base_pos = [glam::Vec3::ZERO; 34];
    let root_pos = condition.from_pose[0].w_axis.truncate();
    for j in 0..34 {
        base_rot6d[j] = matrix_to_cont6d(condition.from_pose[j]);
        base_pos[j] = condition.from_pose[j].w_axis.truncate();
    }

    for f in 0..frames {
        let frame_base = f * 304;
        let frame = &mut buf[frame_base..frame_base + 304];

        // Global 6D rotations (channels [0, 204)).
        for j in 0..34 {
            let base_idx = j * 6;
            frame[base_idx..base_idx + 6].copy_from_slice(&base_rot6d[j]);
        }

        // Root-relative joint positions (channels [204, 303)).
        for j in 1..34 {
            let ric = base_pos[j] - root_pos;
            let ric_base = 204 + (j - 1) * 3;
            frame[ric_base..ric_base + 3].copy_from_slice(&[ric.x, ric.y, ric.z]);
        }

        // Pelvis height (channel 303).
        frame[303] = root_pos.y;

        // Overwrite key joint rotations with the action/stance seed.
        apply_action_seed(frame, condition);
    }

    buf
}

/// Forward-pointing arm orientation used for strikes, blocks, and grabs.
/// `side` is -1.0 for left, 1.0 for right. `raise` tilts the arm upward/outward.
fn arm_forward(side: f32, raise: f32) -> Mat4 {
    Mat4::from_rotation_z(side * raise) * Mat4::from_rotation_x(-std::f32::consts::FRAC_PI_2)
}

/// Overwrite encoder-input frame rotations to encode the action intent.
fn apply_action_seed(frame: &mut [f32], condition: &ActionCondition) {
    match condition.action {
        Action::Strike => {
            // Dominant side: Left/Right stance uses that arm; Top defaults to right
            // with a slightly raised arm (like an overhead/chop strike).
            let (side, raise) = match condition.stance {
                Stance::Left => (-1.0f32, 0.2f32),
                Stance::Right => (1.0f32, 0.2f32),
                Stance::Top => (1.0f32, 0.6f32),
            };
            let shoulder = arm_forward(side, raise);
            let elbow = shoulder; // extended arm
            let wrist = shoulder;
            if side < 0.0 {
                write_rot6d(frame, LEFT_SHOULDER, shoulder);
                write_rot6d(frame, LEFT_UPPER_ARM, shoulder);
                write_rot6d(frame, LEFT_ELBOW, elbow);
                write_rot6d(frame, LEFT_WRIST, wrist);
            } else {
                write_rot6d(frame, RIGHT_SHOULDER, shoulder);
                write_rot6d(frame, RIGHT_UPPER_ARM, shoulder);
                write_rot6d(frame, RIGHT_ELBOW, elbow);
                write_rot6d(frame, RIGHT_WRIST, wrist);
            }
            // Slight forward commitment.
            write_rot6d(frame, WAIST_PITCH, Mat4::from_rotation_x(0.15));
        }
        Action::Block => {
            // Both arms raised in front of the torso, stable lower body.
            for (side, shoulder_idx, upper_arm_idx, elbow_idx, wrist_idx) in [
                (-1.0f32, LEFT_SHOULDER, LEFT_UPPER_ARM, LEFT_ELBOW, LEFT_WRIST),
                (1.0f32, RIGHT_SHOULDER, RIGHT_UPPER_ARM, RIGHT_ELBOW, RIGHT_WRIST),
            ] {
                let shoulder = arm_forward(side, 0.5);
                let elbow = shoulder * Mat4::from_rotation_x(-0.9); // forearm up
                let wrist = elbow;
                write_rot6d(frame, shoulder_idx, shoulder);
                write_rot6d(frame, upper_arm_idx, shoulder);
                write_rot6d(frame, elbow_idx, elbow);
                write_rot6d(frame, wrist_idx, wrist);
            }
            write_rot6d(frame, WAIST_PITCH, Mat4::from_rotation_x(0.05));
        }
        Action::Grab => {
            // Both arms reaching straight forward, body lunging.
            for (side, shoulder_idx, upper_arm_idx, elbow_idx, wrist_idx) in [
                (-1.0f32, LEFT_SHOULDER, LEFT_UPPER_ARM, LEFT_ELBOW, LEFT_WRIST),
                (1.0f32, RIGHT_SHOULDER, RIGHT_UPPER_ARM, RIGHT_ELBOW, RIGHT_WRIST),
            ] {
                let shoulder = arm_forward(side, 0.1);
                let elbow = shoulder; // straight
                let wrist = shoulder;
                write_rot6d(frame, shoulder_idx, shoulder);
                write_rot6d(frame, upper_arm_idx, shoulder);
                write_rot6d(frame, elbow_idx, elbow);
                write_rot6d(frame, wrist_idx, wrist);
            }
            write_rot6d(frame, WAIST_PITCH, Mat4::from_rotation_x(0.25));
            write_rot6d(frame, WAIST_YAW, Mat4::from_rotation_y(0.05));
            // Drop the pelvis slightly to suggest a lunge.
            frame[303] -= 0.08;
        }
        Action::Idle => {
            // Neutral standing pose: keep the incoming from_pose as-is.
            // No action-specific joint overrides are needed for a rest idle.
        }
    }
}

/// Return the authored frame count for each action.
///
/// These values are multiples of the VQVAE token stride (4 frames) so the
/// decoder outputs the requested number of frames without truncation.
fn action_frame_count(action: Action) -> usize {
    match action {
        Action::Strike => 28,
        Action::Block => 44,
        Action::Grab => 32,
        Action::Idle => 60,
    }
}

#[cfg(test)]
fn generate_action_clip_legacy(
    condition: &ActionCondition,
    pipeline: &mut MotionPipeline,
) -> Result<Vec<[Mat4; 34]>, anyhow::Error> {
    if let Some(base) = pipeline.assets_path.as_ref() {
        let required = [
            "motionbricks_vqvae_encoder.onnx",
            "motionbricks_vqvae_decoder.fixed.onnx",
            "motionbricks_pose_transformer.onnx",
            "motionbricks_root_shared.onnx",
            "motionbricks_root_conv.onnx",
            "motionbricks_codebook.npy",
        ];
        for name in &required {
            let p = base.join(name);
            if !p.exists() {
                anyhow::bail!(
                    "Missing MotionBricks artifact '{}'. \
                     Export it from the GR00T repo with tools/export_motionbricks_onnx.py \
                     and place it under {}.",
                    p.display(),
                    base.display()
                );
            }
        }
    }

    let frames = action_frame_count(condition.action);
    let input = build_action_encoder_input(condition, frames);
    pipeline.decode_encoder_input(&input, frames)
}

/// Generate a deterministic MotionBricks action clip for `condition`.
///
/// This is the runtime path: it requests a clip from the Python MotionBricks
/// inference service and returns 34-joint world-space matrices. There is no
/// procedural fallback and no prebaked clip.
pub fn generate_action_clip(
    condition: &ActionCondition,
    service: &crate::motion_service::MotionService,
) -> Result<Vec<[Mat4; 34]>, anyhow::Error> {
    let action_name = format!("{:?}", condition.action);
    let stance_name = format!("{:?}", condition.stance);
    // Weapon is not part of ActionCondition yet; default to Longsword for Phase 2.
    service.generate_clip(&action_name, "Longsword", &stance_name, &[condition.from_pose], 0)
}

#[cfg(test)]
impl MotionPipeline {
    /// Test-only hook to override the artifact directory for error-path tests.
    fn set_assets_path_for_test(&mut self, path: PathBuf) {
        self.assets_path = Some(path);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn heavy_tests_enabled() -> bool {
        std::env::var("JUSTDODGE_HEAVY_TESTS").is_ok_and(|v| !v.is_empty())
    }

    fn assets_dir() -> &'static str {
        concat!(env!("CARGO_MANIFEST_DIR"), "/assets")
    }

    fn try_load_pipeline() -> Option<MotionPipeline> {
        let assets = assets_dir();
        match MotionPipeline::new(assets) {
            Ok(p) => Some(p),
            Err(e) => {
                eprintln!("MotionBricks artifacts not available, skipping test: {e}");
                None
            }
        }
    }

    fn neutral_g1_pose() -> [Mat4; 34] {
        let mesh = crate::asset::load_skinned(&format!(
            "{}/characters/mannequin_male.bin",
            assets_dir()
        ))
        .expect("mannequin mesh must load for neutral pose");
        let clip = build_procedural_g1_clip(1, &mesh, &crate::asset::G1_TO_MANNEQUIN);
        clip.into_iter()
            .next()
            .expect("procedural neutral clip must contain at least one frame")
    }

    #[test]
    fn test_load_pipeline() {
        if !heavy_tests_enabled() {
            eprintln!("skipping heavy ONNX test; set JUSTDODGE_HEAVY_TESTS=1 to run");
            return;
        }
        let pipe = MotionPipeline::new(assets_dir());
        assert!(pipe.is_ok(), "Failed to load pipeline: {:?}", pipe.err());
    }

    #[test]
    fn test_codebook() {
        if !heavy_tests_enabled() {
            eprintln!("skipping heavy ONNX test; set JUSTDODGE_HEAVY_TESTS=1 to run");
            return;
        }
        let pipe = MotionPipeline::new(assets_dir()).unwrap();
        assert_eq!(pipe.codebook.shape(), &[8, 10, 32]);
        assert_eq!(pipe.meta.num_pose_heads, 8);
        assert_eq!(pipe.meta.code_dim, 256);
    }

    #[test]
    fn test_generate_action_clip_lengths() {
        if !heavy_tests_enabled() {
            eprintln!("skipping heavy ONNX test; set JUSTDODGE_HEAVY_TESTS=1 to run");
            return;
        }
        let Some(mut pipeline) = try_load_pipeline() else { return };
        let pose = neutral_g1_pose();

        let cases = [
            (Action::Strike, Stance::Left, 28),
            (Action::Strike, Stance::Top, 28),
            (Action::Strike, Stance::Right, 28),
            (Action::Block, Stance::Top, 44),
            (Action::Grab, Stance::Right, 32),
        ];

        for (action, stance, expected) in cases {
            let condition = ActionCondition {
                action,
                stance,
                from_pose: pose,
            };
            let clip = generate_action_clip_legacy(&condition, &mut pipeline)
                .expect("generate_action_clip should succeed when artifacts are present");
            assert_eq!(
                clip.len(),
                expected,
                "{action:?}/{stance:?} should produce {expected} frames"
            );
            assert!(!clip.is_empty(), "clip should not be empty");
        }
    }

    #[test]
    fn test_generate_action_clip_finite() {
        if !heavy_tests_enabled() {
            eprintln!("skipping heavy ONNX test; set JUSTDODGE_HEAVY_TESTS=1 to run");
            return;
        }
        let Some(mut pipeline) = try_load_pipeline() else { return };
        let pose = neutral_g1_pose();

        for action in [Action::Strike, Action::Block, Action::Grab] {
            let condition = ActionCondition {
                action,
                stance: Stance::Top,
                from_pose: pose,
            };
            let clip = generate_action_clip_legacy(&condition, &mut pipeline)
                .expect("generate_action_clip should succeed when artifacts are present");
            for (fi, frame) in clip.iter().enumerate() {
                for (ji, m) in frame.iter().enumerate() {
                    assert!(
                        m.is_finite(),
                        "non-finite matrix at frame {fi} joint {ji} for {action:?}"
                    );
                }
            }
        }
    }

    #[test]
    fn test_generate_action_clip_deterministic() {
        if !heavy_tests_enabled() {
            eprintln!("skipping heavy ONNX test; set JUSTDODGE_HEAVY_TESTS=1 to run");
            return;
        }
        let Some(mut pipeline) = try_load_pipeline() else { return };
        let pose = neutral_g1_pose();

        let condition = ActionCondition {
            action: Action::Grab,
            stance: Stance::Left,
            from_pose: pose,
        };

        let first = generate_action_clip_legacy(&condition, &mut pipeline)
            .expect("generate_action_clip should succeed when artifacts are present");
        let second = generate_action_clip_legacy(&condition, &mut pipeline)
            .expect("generate_action_clip should be repeatable");

        assert_eq!(first.len(), second.len());
        for (a, b) in first.iter().zip(second.iter()) {
            assert_eq!(a, b, "identical inputs produced different frames");
        }
    }

    #[test]
    fn test_generate_action_clip_missing_onnx_returns_error() {
        if !heavy_tests_enabled() {
            eprintln!("skipping heavy ONNX test; set JUSTDODGE_HEAVY_TESTS=1 to run");
            return;
        }
        let Some(mut pipeline) = try_load_pipeline() else { return };

        // Point the pipeline at an empty directory so the artifact check fails.
        let empty_dir = concat!(env!("CARGO_MANIFEST_DIR"), "/target/test_missing_onnx");
        std::fs::create_dir_all(empty_dir).expect("failed to create test dir");
        pipeline.set_assets_path_for_test(PathBuf::from(empty_dir));

        let pose = neutral_g1_pose();
        let condition = ActionCondition {
            action: Action::Strike,
            stance: Stance::Right,
            from_pose: pose,
        };

        let result = generate_action_clip_legacy(&condition, &mut pipeline);
        assert!(
            result.is_err(),
            "missing ONNX artifacts must produce an error, not an empty clip"
        );
        let msg = result.unwrap_err().to_string();
        assert!(
            msg.contains("Missing MotionBricks artifact"),
            "error should name the missing artifact: {msg}"
        );
    }
}