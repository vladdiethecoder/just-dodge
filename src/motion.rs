// MotionBricks ONNX inference pipeline — ort v2 API
//
// Architecture:
//   1. VQVAE Encoder: motion_frames[B, C, T] -> quantized_features[B, 256, T/4]
//   2. Codebook: 8 heads x 10 codes x 32 dim — nearest-neighbour search in Rust
//   3. VQVAE Decoder: quantized[B, 256, T/4] -> reconstructed[B, T, out_dim]
//   4. Pose Transformer: tokens + conditions -> pose_logits[B, N, 8, 11]
//   5. Root: conditions -> pred_global_root[B, T, 5]

use std::path::Path;
use anyhow::{Context, Result};
use ndarray::{Array, Array2, ArrayD, IxDyn};
use ort::session::Session;
use ort::value::{DynValue, Tensor};

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
        let encoder = b.commit_from_file(base.join("motionbricks_vqvae_encoder.onnx"))
            .context("Failed to load VQVAE encoder")?;

        let mut b = Session::builder()?;
        let decoder = b.commit_from_file(base.join("motionbricks_vqvae_decoder.onnx"))
            .context("Failed to load VQVAE decoder")?;

        let mut b = Session::builder()?;
        let pose_transformer = b.commit_from_file(base.join("motionbricks_pose_transformer.onnx"))
            .context("Failed to load pose transformer")?;

        let mut b = Session::builder()?;
        let root_shared = b.commit_from_file(base.join("motionbricks_root_shared.onnx"))
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
        let root_conv = b.commit_from_file(base.join("motionbricks_root_conv.onnx"))
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
        let encoded = ArrayD::from_shape_vec(
            IxDyn(&[self.meta.code_dim, t_out]),
            quantized_flat.to_vec(),
        )?;
        self.quantize(&encoded)
    }

    /// Decode quantized features to motion frames.
    /// quantized shape: [1, code_dim, T/4] (ONNX format)
    pub fn decode_frames(&mut self, quantized: &ArrayD<f32>) -> Result<ArrayD<f32>> {
        let t = quantized.shape()[1];
        let out_frames = t * 4;
        let target_cond_dim = 241;
        let external_cond_dim = 2;

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

        let mut outputs = (&mut self.decoder).run(ort::inputs![q_tensor, t_tensor, e_tensor])?;
        let output = outputs.remove("reconstructed_motion")
            .ok_or_else(|| anyhow::anyhow!("Missing output"))?;
        let (shape, data) = output.try_extract_tensor::<f32>()?;
        let shape_vec: Vec<usize> = shape.iter().map(|&d| d as usize).collect();
        ArrayD::from_shape_vec(IxDyn(&shape_vec), data.to_vec())
            .context("Failed to reshape decoder output")
    }

    /// Internal: run encoder ONNX model
    fn run_encoder(&mut self, input: &ArrayD<f32>) -> Result<DynValue> {
        let shape: Vec<i64> = input.shape().iter().map(|&d| d as i64).collect();
        let flat: Vec<f32> = input.iter().copied().collect();
        let tensor = Tensor::<f32>::from_array((ort::value::Shape::new(shape), flat))?;
        let mut outputs = (&mut self.encoder).run(ort::inputs![tensor])?;
        outputs.remove("quantized")
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
