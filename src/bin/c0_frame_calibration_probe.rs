//! QA-only measured C0 world-frame retarget calibration probe.
use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::path::PathBuf;

#[path = "../asset.rs"]
mod asset;
#[path = "../motion.rs"]
mod motion;
#[path = "../motion_service.rs"]
mod motion_service;

const C0_SCALE: f32 = 0.918_949_96;
const G1_PARENTS: [i32; 34] = [
    -1, 0, 1, 2, 3, 4, 5, 6, 0, 8, 9, 10, 11, 12, 13, 0, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
    17, 26, 27, 28, 29, 30, 31, 32,
];

fn cpu_positions(mesh: &asset::SkinnedMeshData, skin: &[glam::Mat4]) -> Vec<glam::Vec3> {
    mesh.vertices
        .iter()
        .map(|vertex| {
            let source = glam::Vec3::from_array(vertex.position).extend(1.0);
            let mut result = glam::Vec4::ZERO;
            for influence in 0..8 {
                let weight = vertex.joint_weights[influence];
                if weight > 0.0 {
                    result += skin[vertex.joint_indices[influence] as usize] * source * weight;
                }
            }
            result.truncate() * C0_SCALE
        })
        .collect()
}

fn bbox(positions: &[glam::Vec3]) -> (glam::Vec3, glam::Vec3) {
    positions.iter().fold(
        (
            glam::Vec3::splat(f32::INFINITY),
            glam::Vec3::splat(f32::NEG_INFINITY),
        ),
        |(lo, hi), position| (lo.min(*position), hi.max(*position)),
    )
}

fn write_obj(path: &PathBuf, mesh: &asset::SkinnedMeshData, positions: &[glam::Vec3]) {
    let mut file = BufWriter::new(File::create(path).expect("create OBJ"));
    let floor = positions
        .iter()
        .map(|position| position.y)
        .fold(f32::INFINITY, f32::min);
    for position in positions {
        writeln!(
            file,
            "v {:.8} {:.8} {:.8}",
            position.x,
            -position.z,
            position.y - floor
        )
        .unwrap();
    }
    for triangle in mesh.indices.chunks_exact(3) {
        writeln!(
            file,
            "f {} {} {}",
            triangle[0] + 1,
            triangle[1] + 1,
            triangle[2] + 1
        )
        .unwrap();
    }
}

fn main() {
    let root = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".into());
    let output = PathBuf::from(
        std::env::var("C0_QA_OUT").unwrap_or_else(|_| "/tmp/c0_frame_calibration_qa".into()),
    );
    fs::create_dir_all(&output).expect("create output");
    let mesh = asset::load_skinned(&format!(
        "{root}/assets/source/meshy/c0_base_fighter/pose_carrier_001/cooked/c0_pose_carrier.bin"
    ))
    .expect("load C0 mesh");
    let reference = asset::load_skeletal_animation(&format!(
        "{root}/assets/source/meshy/c0_base_fighter/pose_carrier_001/cooked/c0_reference.anim"
    ))
    .expect("load C0 reference");
    let service = motion_service::MotionService::new().expect("initialize MotionBricks");
    let idle = service
        .load_primitive_clip("idle", "longsword", "top")
        .expect("load measured idle primitive");
    let strike = service
        .load_primitive_clip("strike", "longsword", "top")
        .expect("load measured strike primitive");
    assert!(!strike.is_empty());
    let source_reference = &strike[0];
    let target_reference = &reference.frames[0];
    let reference_skin = asset::reference_pose_skin_matrices(&mesh, target_reference).unwrap();
    let reference_positions = cpu_positions(&mesh, &reference_skin);
    let (reference_lo, reference_hi) = bbox(&reference_positions);
    let reference_size = reference_hi - reference_lo;
    write_obj(&output.join("reference.obj"), &mesh, &reference_positions);

    let mut sampled = Vec::new();
    let mut sampled_source = Vec::new();
    let mut min_det = f32::INFINITY;
    let mut max_det = f32::NEG_INFINITY;
    let mut min_axis_scale = f32::INFINITY;
    let mut max_axis_scale = f32::NEG_INFINITY;
    let mut max_height_pump = 0.0f32;
    let mut max_width_pump = 0.0f32;
    let mut max_local_length_error = 0.0f32;
    let source_reference_lengths: [f32; 34] = std::array::from_fn(|index| {
        if G1_PARENTS[index] < 0 {
            0.0
        } else {
            (strike[0][index].w_axis.truncate()
                - strike[0][G1_PARENTS[index] as usize].w_axis.truncate())
            .length()
        }
    });
    let mut max_source_length_error = 0.0f32;
    let step = (strike.len() / 8).max(1);
    for (frame_index, frame) in strike.iter().enumerate() {
        for index in 1..34 {
            let length = (frame[index].w_axis.truncate()
                - frame[G1_PARENTS[index] as usize].w_axis.truncate())
            .length();
            max_source_length_error =
                max_source_length_error.max((length - source_reference_lengths[index]).abs());
        }
        let target_local =
            asset::calibrated_g1_target_locals(frame, source_reference, &mesh, target_reference)
                .expect("calibrate frame");
        for (index, matrix) in target_local.iter().enumerate() {
            if mesh.bones[index].parent >= 0 {
                let (_, _, current_translation) = matrix.to_scale_rotation_translation();
                let (_, _, reference_translation) =
                    target_reference[index].to_scale_rotation_translation();
                max_local_length_error = max_local_length_error
                    .max((current_translation.length() - reference_translation.length()).abs());
            }
        }
        let skin = asset::reference_pose_skin_matrices(&mesh, &target_local).unwrap();
        for matrix in &skin {
            min_det = min_det.min(matrix.determinant());
            max_det = max_det.max(matrix.determinant());
            for scale in [
                matrix.x_axis.truncate().length(),
                matrix.y_axis.truncate().length(),
                matrix.z_axis.truncate().length(),
            ] {
                min_axis_scale = min_axis_scale.min(scale);
                max_axis_scale = max_axis_scale.max(scale);
            }
        }
        let positions = cpu_positions(&mesh, &skin);
        let (lo, hi) = bbox(&positions);
        let size = hi - lo;
        max_height_pump = max_height_pump.max((size.y - reference_size.y).abs());
        max_width_pump = max_width_pump.max((size.x - reference_size.x).abs());
        if frame_index % step == 0 || frame_index + 1 == strike.len() {
            let name = format!("frame_{frame_index:04}.obj");
            write_obj(&output.join(&name), &mesh, &positions);
            sampled.push(name);
            sampled_source.push((frame_index, *frame));
        }
    }
    assert!(min_det > 0.0);
    assert!(min_axis_scale > 0.1 && max_axis_scale < 10.0);
    assert!(max_local_length_error < 1e-5);
    assert!(max_source_length_error < 1e-4);
    let report = format!(
        concat!(
            "{{\n  \"idle_frames\": {},\n  \"strike_frames\": {},\n",
            "  \"bones\": {},\n  \"vertices\": {},\n",
            "  \"min_determinant\": {:.9},\n  \"max_determinant\": {:.9},\n",
            "  \"min_axis_scale\": {:.9},\n  \"max_axis_scale\": {:.9},\n",
            "  \"max_local_length_error_m\": {:.9},\n",
            "  \"max_source_length_error_m\": {:.9},\n",
            "  \"max_height_pump_m\": {:.9},\n  \"max_width_pump_m\": {:.9},\n",
            "  \"sampled_objs\": [{}]\n}}\n"
        ),
        idle.len(),
        strike.len(),
        mesh.bones.len(),
        mesh.vertices.len(),
        min_det,
        max_det,
        min_axis_scale,
        max_axis_scale,
        max_local_length_error,
        max_source_length_error,
        max_height_pump,
        max_width_pump,
        sampled
            .iter()
            .map(|name| format!("\"{name}\""))
            .collect::<Vec<_>>()
            .join(", ")
    );
    fs::write(output.join("report.json"), report).unwrap();
    let mut source_json = String::from("{\n  \"parents\": [");
    source_json.push_str(
        &G1_PARENTS
            .iter()
            .map(i32::to_string)
            .collect::<Vec<_>>()
            .join(", "),
    );
    source_json.push_str("],\n  \"frames\": [\n");
    for (sample_index, (frame_index, frame)) in sampled_source.iter().enumerate() {
        source_json.push_str(&format!("    {{\"frame\": {frame_index}, \"positions\": ["));
        source_json.push_str(
            &frame
                .iter()
                .map(|matrix| {
                    let position = matrix.w_axis.truncate();
                    format!("[{:.8}, {:.8}, {:.8}]", position.x, position.y, position.z)
                })
                .collect::<Vec<_>>()
                .join(", "),
        );
        source_json.push_str(if sample_index + 1 == sampled_source.len() {
            "]}\n"
        } else {
            "]},\n"
        });
    }
    source_json.push_str("  ]\n}\n");
    fs::write(output.join("g1_samples.json"), source_json).unwrap();
    eprintln!(
        "C0_FRAME_CAL_PASS {} frames -> {}",
        strike.len(),
        output.display()
    );
}
