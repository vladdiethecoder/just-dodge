// Deterministic bridge to the Python MotionBricks inference service.
use anyhow::{Context, Result};
use glam::Mat4;
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
            let path = path.downcast::<PyList>().map_err(|_| anyhow::anyhow!("sys.path is not a list"))?;
            let cwd = std::env::current_dir()?;
            path.insert(0, cwd.to_str().context("invalid cwd")?)
                .map_err(py_err)?;
            let _ = py.import("motionbricks_service").map_err(py_err)?;
            Ok(Self)
        })
    }

    pub fn generate_clip(
        &self,
        action: &str,
        weapon: &str,
        stance: &str,
        context: &[[Mat4; 34]],
        seed: u64,
    ) -> Result<Vec<[Mat4; 34]>> {
        Python::with_gil(|py| {
            let svc = py.import("motionbricks_service").map_err(py_err)?;
            let ctx_list = PyList::empty(py);
            for frame in context {
                let flat: Vec<f32> = frame.iter().flat_map(|m| m.to_cols_array()).collect();
                let arr = numpy::PyArray1::from_vec(py, flat);
                ctx_list.append(arr).map_err(py_err)?;
            }
            let bytes: Vec<u8> = svc
                .getattr("generate_clip")
                .map_err(py_err)?
                .call1((action, weapon, stance, ctx_list, seed))
                .map_err(py_err)?
                .extract()
                .map_err(py_err)?;
            motion::load_g1_frames_from_bytes(&bytes)
        })
    }
}
