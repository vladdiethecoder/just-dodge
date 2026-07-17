//! Export exact R6K articulated C0 execution frames for ForgeLens Motion Lab.
use just_dodge::{asset, hero_strike};
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};

fn write_vec3(out: &mut BufWriter<File>, value: glam::Vec3) {
    write!(out, "[{:.9},{:.9},{:.9}]", value.x, value.y, value.z).unwrap();
}

fn main() -> anyhow::Result<()> {
    let output = std::env::args()
        .nth(1)
        .map(PathBuf::from)
        .ok_or_else(|| anyhow::anyhow!("usage: pvp005_r6k_motion_lab_export OUTPUT.json"))?;
    let assets = Path::new(env!("CARGO_MANIFEST_DIR")).join("assets");
    let mesh = asset::load_skinned(
        &assets
            .join("source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin")
            .to_string_lossy(),
    )?;
    let presentation = hero_strike::HeroStrikePresentation::load(&assets, &mesh)?;
    let file = File::create(output)?;
    let mut out = BufWriter::new(file);
    write!(
        out,
        "{{\"schema\":\"just-dodge-r6k-physics-execution-v1\",\"fps\":30,\"physicsHz\":120,\"frames\":["
    )?;
    for frame in 0..hero_strike::FRAME_COUNT {
        if frame != 0 {
            write!(out, ",")?;
        }
        let world = presentation.armored_world(frame);
        let weapon = presentation.weapon_local(frame);
        write!(out, "{{\"index\":{},\"joints\":[", frame)?;
        for (index, joint) in world.iter().enumerate() {
            if index != 0 {
                write!(out, ",")?;
            }
            write_vec3(&mut out, joint.w_axis.truncate());
        }
        write!(out, "],\"weapon\":[")?;
        for (index, value) in weapon.to_cols_array().iter().enumerate() {
            if index != 0 {
                write!(out, ",")?;
            }
            write!(out, "{value:.9}")?;
        }
        write!(out, "]}}")?;
    }
    write!(out, "]}}")?;
    out.flush()?;
    Ok(())
}
