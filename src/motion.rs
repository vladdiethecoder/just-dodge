// MotionBricks ONNX inference pipeline — ort v2 API
//
// Architecture:
//   1. VQVAE Encoder: motion_frames[B, C, T] -> quantized_features[B, 256, T/4]
//   2. Codebook: 8 heads x 10 codes x 32 dim — nearest-neighbour search in Rust
//   3. VQVAE Decoder: quantized[B, 256, T/4] -> reconstructed[B, T, out_dim]
//   4. Pose Transformer: tokens + conditions -> pose_logits[B, N, 8, 11]
//   5. Root: conditions -> pred_global_root[B, T, 5]

use anyhow::{Context, Result};
use glam::Mat4;
use ndarray::{Array, Array2, ArrayD, IxDyn};
use ort::session::Session;
use ort::value::{DynValue, Tensor};
use std::path::Path;

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

        let mut b = Session::builder()?;
        let encoder = b
            .commit_from_file(base.join("motionbricks_vqvae_encoder.onnx"))
            .context("Failed to load VQVAE encoder")?;

        let mut b = Session::builder()?;
        let decoder = b
            .commit_from_file(base.join("motionbricks_vqvae_decoder.onnx"))
            .context("Failed to load VQVAE decoder")?;

        let mut b = Session::builder()?;
        let pose_transformer = b
            .commit_from_file(base.join("motionbricks_pose_transformer.onnx"))
            .context("Failed to load pose transformer")?;

        let mut b = Session::builder()?;
        let root_shared = b
            .commit_from_file(base.join("motionbricks_root_shared.onnx"))
            .context("Failed to load root shared transformer")?;

        let root_token = {
            let p = base.join("motionbricks_root_token.onnx");
            if p.exists() {
                let mut b = Session::builder()?;
                Some(
                    b.commit_from_file(p)
                        .context("Failed to load root token transformer")?,
                )
            } else {
                None
            }
        };

        let mut b = Session::builder()?;
        let root_conv = b
            .commit_from_file(base.join("motionbricks_root_conv.onnx"))
            .context("Failed to load root conv decoder")?;

        let codebook = Self::load_npy(&base.join("motionbricks_codebook.npy"), &[8, 10, 32])?;

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
    /// quantized shape: [1, code_dim, T/4] (ONNX format)
    /// Returns reconstructed motion [1, T, 413] (GlobalRootGlobalJoints global subset).
    pub fn decode_frames(&mut self, quantized: &ArrayD<f32>) -> Result<ArrayD<f32>> {
        let t = quantized.shape()[1];
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

        let outputs = (&mut self.decoder).run(ort::inputs![q_tensor, t_tensor, e_tensor])?;
        // decoder output is a single tensor (name varies by export); take it by position
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
        let enc_out = (&mut self.encoder).run(ort::inputs![tensor])?;
        let enc_vec: Vec<DynValue> = enc_out.into_iter().map(|(_, v)| v).collect();
        // encoder outputs: [0]=quantized [1,256,T/4], [1]=indices [1,8,T/4]
        let quantized_dv = enc_vec
            .into_iter()
            .next()
            .ok_or_else(|| anyhow::anyhow!("no quantized"))?;
        let (qshape, qdata) = quantized_dv.try_extract_tensor::<f32>()?;
        let _ = qshape;
        let tt = t / 4;
        // dequantize via codebook [8,10,32]
        let mut feats = vec![0f32; 1 * 256 * tt];
        for h in 0..8usize {
            for k in 0..tt {
                // indices tensor is [1,8,tt]; we approximate by reading the flat quantized
                // channel at (h*32 .. h*32+32, k)
                for d in 0..32usize {
                    feats[k * 256 + h * 32 + d] = qdata[h * 32 + d + k * 256];
                }
            }
        }
        // indices path: we need codebook lookups, but the encoder already outputs quantized
        // continuous features (not discrete). Decode those directly.
        let q_arr =
            ArrayD::from_shape_vec(IxDyn(&[1, 256, tt]), feats).context("quantized reshape")?;
        let rec = self.decode_frames(&q_arr)?; // [1, T, 413]
        let rec_data = rec.as_standard_layout();
        let data = rec_data.as_slice().unwrap();
        let mut frames = Vec::with_capacity(t);
        for f in 0..t {
            let base = f * 413;
            let slice = &data[base..base + 413];
            frames.push(Self::parse_g1_frame(slice));
        }
        Ok(frames)
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
        let mut outputs = (&mut self.encoder).run(ort::inputs![tensor])?;
        outputs
            .remove("quantized")
            .ok_or_else(|| anyhow::anyhow!("Missing 'quantized' output"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_load_pipeline() {
        let assets = concat!(env!("CARGO_MANIFEST_DIR"), "/assets");
        let pipe = MotionPipeline::new(assets);
        assert!(pipe.is_ok(), "Failed to load pipeline: {:?}", pipe.err());
    }

    #[test]
    fn test_codebook() {
        let assets = concat!(env!("CARGO_MANIFEST_DIR"), "/assets");
        let pipe = MotionPipeline::new(assets).unwrap();
        assert_eq!(pipe.codebook.shape(), &[8, 10, 32]);
        assert_eq!(pipe.meta.num_pose_heads, 8);
        assert_eq!(pipe.meta.code_dim, 256);
    }
}
