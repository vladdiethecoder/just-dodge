//! QA-only direct BONES-SEED G1 → C0 world-frame calibration probe.
//!
//! The input is the ignored `*.413.f32` artifact emitted by
//! `tools/qa/validate_bones_seed_g1.py`. This binary deliberately has no
//! renderer, gameplay, truth, or replay dependency.

use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};

use glam::{Mat4, Vec3, Vec4};
use just_dodge::asset;

const C0_SCALE: f32 = 0.918_949_96;
const FRAME_FLOATS: usize = 413;
const G1_JOINTS: usize = 34;
const G1_PARENTS: [i32; G1_JOINTS] = [
    -1, 0, 1, 2, 3, 4, 5, 6, 0, 8, 9, 10, 11, 12, 13, 0, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
    17, 26, 27, 28, 29, 30, 31, 32,
];

fn parse_f32_frames(path: &Path) -> std::io::Result<Vec<[Mat4; G1_JOINTS]>> {
    let bytes = fs::read(path)?;
    let frame_bytes = FRAME_FLOATS * std::mem::size_of::<f32>();
    if bytes.is_empty() || bytes.len() % frame_bytes != 0 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            format!(
                "expected non-empty f32 frame stream divisible by {frame_bytes} bytes, got {}",
                bytes.len()
            ),
        ));
    }
    bytes
        .chunks_exact(frame_bytes)
        .map(|chunk| {
            let values = chunk
                .chunks_exact(4)
                .map(|item| f32::from_le_bytes(item.try_into().expect("four bytes")))
                .collect::<Vec<_>>();
            decode_g1_world(&values)
        })
        .collect()
}

fn decode_g1_world(values: &[f32]) -> std::io::Result<[Mat4; G1_JOINTS]> {
    if values.len() != FRAME_FLOATS || values.iter().any(|value| !value.is_finite()) {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "non-finite or malformed [413] source frame",
        ));
    }
    let root = Vec3::from_slice(&values[0..3]);
    let mut output = [Mat4::IDENTITY; G1_JOINTS];
    for (joint, target) in output.iter_mut().enumerate() {
        let position = if joint == 0 {
            root
        } else {
            root + Vec3::from_slice(&values[5 + (joint - 1) * 3..8 + (joint - 1) * 3])
        };
        let rotation_offset = 104 + joint * 6;
        let x = Vec3::from_slice(&values[rotation_offset..rotation_offset + 3]);
        let y = Vec3::from_slice(&values[rotation_offset + 3..rotation_offset + 6]);
        let x = x.normalize_or_zero();
        let y = (y - x * x.dot(y)).normalize_or_zero();
        let z = x.cross(y).normalize_or_zero();
        if x.length_squared() < 0.999 || y.length_squared() < 0.999 || z.length_squared() < 0.999 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("source joint {joint} has degenerate 6D rotation"),
            ));
        }
        *target = Mat4::from_cols(
            x.extend(0.0),
            y.extend(0.0),
            z.extend(0.0),
            position.extend(1.0),
        );
    }
    Ok(output)
}

fn cpu_positions(mesh: &asset::SkinnedMeshData, skin: &[Mat4]) -> Vec<Vec3> {
    mesh.vertices
        .iter()
        .map(|vertex| {
            let source = Vec3::from_array(vertex.position).extend(1.0);
            let mut result = Vec4::ZERO;
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

fn bounds(positions: &[Vec3]) -> (Vec3, Vec3) {
    positions.iter().fold(
        (Vec3::splat(f32::INFINITY), Vec3::splat(f32::NEG_INFINITY)),
        |(lo, hi), position| (lo.min(*position), hi.max(*position)),
    )
}

fn write_obj(
    path: &Path,
    mesh: &asset::SkinnedMeshData,
    positions: &[Vec3],
) -> std::io::Result<()> {
    let file = File::create(path)?;
    let mut output = BufWriter::new(file);
    let floor = positions
        .iter()
        .map(|position| position.y)
        .fold(f32::INFINITY, f32::min);
    for position in positions {
        writeln!(
            output,
            "v {:.8} {:.8} {:.8}",
            position.x,
            -position.z,
            position.y - floor
        )?;
    }
    for triangle in mesh.indices.chunks_exact(3) {
        writeln!(
            output,
            "f {} {} {}",
            triangle[0] + 1,
            triangle[1] + 1,
            triangle[2] + 1
        )?;
    }
    Ok(())
}

fn main() -> std::io::Result<()> {
    let root = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".into());
    let input = PathBuf::from(
        std::env::var("C0_DODGE_F413")
            .expect("C0_DODGE_F413 must name ignored direct source frames"),
    );
    let output = PathBuf::from(
        std::env::var("C0_QA_OUT").unwrap_or_else(|_| "/tmp/c0_bones_dodge_calibration_qa".into()),
    );
    fs::create_dir_all(&output)?;

    let source_frames = parse_f32_frames(&input)?;
    let mesh = asset::load_skinned(&format!(
        "{root}/assets/source/meshy/c0_base_fighter/pose_carrier_001/cooked/c0_pose_carrier.bin"
    ))?;
    let reference = asset::load_skeletal_animation(&format!(
        "{root}/assets/source/meshy/c0_base_fighter/pose_carrier_001/cooked/c0_reference.anim"
    ))?;
    if reference.frames.is_empty() || reference.frames[0].len() != mesh.bones.len() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "C0 reference pose does not match mesh bones",
        ));
    }
    let source_reference = source_frames[0];
    let target_reference = &reference.frames[0];
    let reference_skin = asset::reference_pose_skin_matrices(&mesh, target_reference)?;
    let reference_positions = cpu_positions(&mesh, &reference_skin);
    let (reference_lo, reference_hi) = bounds(&reference_positions);
    let reference_size = reference_hi - reference_lo;
    write_obj(&output.join("reference.obj"), &mesh, &reference_positions)?;

    let sample_indices = [
        0,
        source_frames.len() / 4,
        source_frames.len() / 2,
        source_frames.len() * 3 / 4,
        source_frames.len() - 1,
    ];
    let mut min_det = f32::INFINITY;
    let mut max_det = f32::NEG_INFINITY;
    let mut min_axis_scale = f32::INFINITY;
    let mut max_axis_scale = f32::NEG_INFINITY;
    let mut max_local_length_error = 0.0f32;
    let mut max_source_length_error = 0.0f32;
    let mut max_height_pump = 0.0f32;
    let mut max_width_pump = 0.0f32;
    let source_reference_lengths: [f32; G1_JOINTS] = std::array::from_fn(|index| {
        if G1_PARENTS[index] < 0 {
            0.0
        } else {
            (source_reference[index].w_axis.truncate()
                - source_reference[G1_PARENTS[index] as usize]
                    .w_axis
                    .truncate())
            .length()
        }
    });

    for (frame_index, source_world) in source_frames.iter().enumerate() {
        for index in 1..G1_JOINTS {
            let length = (source_world[index].w_axis.truncate()
                - source_world[G1_PARENTS[index] as usize].w_axis.truncate())
            .length();
            max_source_length_error =
                max_source_length_error.max((length - source_reference_lengths[index]).abs());
        }
        let target_local = asset::calibrated_g1_target_locals(
            source_world,
            &source_reference,
            &mesh,
            target_reference,
        )?;
        for (index, matrix) in target_local.iter().enumerate() {
            if mesh.bones[index].parent >= 0 {
                let (_, _, current_translation) = matrix.to_scale_rotation_translation();
                let (_, _, reference_translation) =
                    target_reference[index].to_scale_rotation_translation();
                max_local_length_error = max_local_length_error
                    .max((current_translation.length() - reference_translation.length()).abs());
            }
        }
        let skin = asset::reference_pose_skin_matrices(&mesh, &target_local)?;
        for matrix in &skin {
            if !matrix.is_finite() || matrix.determinant() <= 0.0 {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    format!("frame {frame_index} has non-finite or inverted skin transform"),
                ));
            }
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
        let (lo, hi) = bounds(&positions);
        let size = hi - lo;
        max_height_pump = max_height_pump.max((size.y - reference_size.y).abs());
        max_width_pump = max_width_pump.max((size.x - reference_size.x).abs());
        if sample_indices.contains(&frame_index) {
            write_obj(
                &output.join(format!("frame_{frame_index:04}.obj")),
                &mesh,
                &positions,
            )?;
        }
    }
    if max_local_length_error > 1e-5 || max_source_length_error > 1e-4 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            format!(
                "local/source length invariant failed: {max_local_length_error:.9}/{max_source_length_error:.9}"
            ),
        ));
    }
    fs::write(
        output.join("report.json"),
        format!(
            concat!(
                "{{\n  \"source_frames\": {},\n  \"c0_bones\": {},\n",
                "  \"vertices\": {},\n  \"min_determinant\": {:.9},\n",
                "  \"max_determinant\": {:.9},\n  \"min_axis_scale\": {:.9},\n",
                "  \"max_axis_scale\": {:.9},\n  \"max_local_length_error_m\": {:.9},\n",
                "  \"max_source_length_error_m\": {:.9},\n  \"max_height_pump_m\": {:.9},\n",
                "  \"max_width_pump_m\": {:.9}\n}}\n"
            ),
            source_frames.len(),
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
        ),
    )?;
    eprintln!(
        "C0_BONES_DODGE_CAL_PASS {} source frames -> {}",
        source_frames.len(),
        output.display()
    );
    Ok(())
}
