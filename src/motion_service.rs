// Deterministic bridge to the Python MotionBricks inference service.
use anyhow::{Context, Result};
use glam::Mat4;
use ndarray::Array4;
use pyo3::prelude::*;
use pyo3::types::PyList;

use crate::motion;

fn py_err(e: PyErr) -> anyhow::Error {
    anyhow::anyhow!("{e}")
}

pub struct MotionService;

impl MotionService {
    pub fn new() -> Result<Self> {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| {
            let sys = py.import("sys").map_err(py_err)?;
            let path = sys.getattr("path").map_err(py_err)?;
            let path = path
                .downcast::<PyList>()
                .map_err(|_| anyhow::anyhow!("sys.path is not a list"))?;
            let cwd = std::env::current_dir()?;
            path.insert(0, cwd.to_str().context("invalid cwd")?)
                .map_err(py_err)?;
            let _ = py.import("motionbricks_service").map_err(py_err)?;
            Ok(Self)
        })
    }

    fn build_context_array<'py>(
        py: Python<'py>,
        context: Option<&[[Mat4; 34]]>,
    ) -> Result<Option<Bound<'py, numpy::PyArray4<f32>>>> {
        let Some(context) = context else {
            return Ok(None);
        };
        let frames = context.len().max(1);
        let mut data = vec![0.0f32; frames * 34 * 4 * 4];
        for (f, frame) in context.iter().enumerate() {
            for (j, m) in frame.iter().enumerate() {
                let cols = m.to_cols_array();
                for (c, &v) in cols.iter().enumerate() {
                    data[((f * 34 + j) * 4 + c / 4) * 4 + c % 4] = v;
                }
            }
        }
        // If an empty context slice was provided, send a single identity frame
        // so the Python service falls back to its internal idle clip.
        if context.is_empty() {
            for j in 0..34 {
                for k in 0..4 {
                    data[(j * 4 + k) * 4 + k] = 1.0;
                }
            }
        }
        let array = Array4::from_shape_vec((frames, 34, 4, 4), data)
            .map_err(|e| anyhow::anyhow!("failed to build context array: {e}"))?;
        Ok(Some(numpy::PyArray4::from_owned_array(py, array)))
    }

    pub fn generate_clip(
        &self,
        action: &str,
        weapon: &str,
        stance: &str,
        context: Option<&[[Mat4; 34]]>,
        seed: u64,
    ) -> Result<Vec<[Mat4; 34]>> {
        Python::with_gil(|py| {
            let svc = py.import("motionbricks_service").map_err(py_err)?;
            let ctx_array = Self::build_context_array(py, context)?;
            let bytes: Vec<u8> = svc
                .getattr("generate_clip")
                .map_err(py_err)?
                .call1((action, weapon, stance, ctx_array, seed))
                .map_err(py_err)?
                .extract()
                .map_err(py_err)?;
            motion::load_g1_frames_from_bytes(&bytes)
        })
    }

    pub fn load_primitive_clip(
        &self,
        action: &str,
        weapon: &str,
        stance: &str,
    ) -> Result<Vec<[Mat4; 34]>> {
        Python::with_gil(|py| {
            let svc = py.import("motionbricks_service").map_err(py_err)?;
            let bytes: Vec<u8> = svc
                .getattr("load_primitive_clip")
                .map_err(py_err)?
                .call1((action, weapon, stance))
                .map_err(py_err)?
                .extract()
                .map_err(py_err)?;
            motion::load_g1_frames_from_bytes(&bytes)
        })
    }

    /// NVIDIA's full NavigationAgent path: official random-controller signal,
    /// qpos context, canonicalization, spring target, forced generation, then
    /// MuJoCo-to-motion conversion. This carries no fabricated combat label.
    pub fn generate_official_navigation_clip(&self, seed: u64) -> Result<Vec<[Mat4; 34]>> {
        Python::with_gil(|py| {
            let svc = py.import("motionbricks_service").map_err(py_err)?;
            let bytes: Vec<u8> = svc
                .getattr("generate_official_navigation_clip")
                .map_err(py_err)?
                .call1((seed,))
                .map_err(py_err)?
                .extract()
                .map_err(py_err)?;
            motion::load_g1_frames_from_bytes(&bytes)
        })
    }
}
