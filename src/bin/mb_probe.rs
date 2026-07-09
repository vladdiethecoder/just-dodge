// MotionBricks offline probe: loads the ONNX pipeline, decodes an idle clip,
// and prints frame counts + duration at each step.  If it hangs, we know exactly
// which step is stuck.  Run: cargo run --bin mb_probe
use std::time::Instant;

#[path = "../asset.rs"]
mod asset;
#[path = "../motion.rs"]
mod motion;
#[path = "../motion_service.rs"]
mod motion_service;
#[path = "../retarget.rs"]
mod retarget;
#[path = "../skeleton.rs"]
mod skeleton;

fn step(name: &str) -> Instant {
    eprintln!("[mb_probe] {}", name);
    Instant::now()
}

fn done(name: &str, t0: Instant) {
    eprintln!("[mb_probe] {} done in {:.2}s", name, t0.elapsed().as_secs_f32());
}

fn main() {
    let assets = std::env::var("JUSTDODGE_ASSETS").unwrap_or_else(|_| "assets".to_string());

    let t0 = step("load skinned mesh");
    let mesh = match asset::load_skinned(&format!("{}/characters/mannequin_male.bin", assets)) {
        Ok(m) => { eprintln!("[mb_probe]   {} verts, {} bones", m.vertices.len(), m.bones.len()); m }
        Err(e) => { eprintln!("FAIL: {e}"); return; }
    };
    done("load skinned mesh", t0);

    let t0 = step("MotionPipeline::new (loads 5 ONNX models)");
    let mut pipe = match motion::MotionPipeline::new(&assets) {
        Ok(p) => p,
        Err(e) => { eprintln!("FAIL: {e}"); return; }
    };
    done("MotionPipeline::new", t0);

    let t = 40usize;
    let t0 = step("build_mesh_rest_input");
    let ib: Vec<_> = mesh.bones.iter().map(|b| b.inverse_bind).collect();
    let enc_in = pipe.build_mesh_rest_input(t, &asset::G1_TO_MANNEQUIN, &ib);
    done("build_mesh_rest_input", t0);

    let t0 = step("decode_encoder_input (ONNX inference, 40 frames)");
    let g1_frames = match pipe.decode_encoder_input(&enc_in, t) {
        Ok(f) => f,
        Err(e) => { eprintln!("FAIL: {e}"); return; }
    };
    done("decode_encoder_input", t0);

    let t0 = step("compute_skin_matrices (retarget G1->mannequin)");
    let skin_frames: Vec<[glam::Mat4; 24]> = g1_frames
        .iter()
        .map(|g1| asset::compute_skin_matrices(g1, &mesh))
        .collect();
    done("compute_skin_matrices", t0);

    eprintln!("[mb_probe] SUCCESS: {} G1 frames, {} skin frames", g1_frames.len(), skin_frames.len());
}
