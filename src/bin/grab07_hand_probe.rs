//! Narrow deterministic inspection tool for Grab-07 G1→C0 retarget hand reach.

use std::path::PathBuf;

use glam::Vec3;
use just_dodge::{asset, motion, motion_retarget};

const SKIN: &str = "source/meshy/c0_base_fighter/rigged_001/cooked/c0_skin8.bin";
const MOTION: &str = "motion/pvp005_candidates/grab/grab_07.413.f32";

fn position(mesh: &asset::SkinnedMeshData, skin: &[glam::Mat4], name: &str) -> Vec3 {
    let index = mesh
        .bones
        .iter()
        .position(|bone| bone.name == name)
        .unwrap_or_else(|| panic!("missing {name}"));
    (skin[index] * mesh.bones[index].inverse_bind.inverse())
        .w_axis
        .truncate()
}

fn main() {
    let assets = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("assets");
    let mesh = asset::load_skinned(&assets.join(SKIN).to_string_lossy()).expect("load C0 skin");
    let frames =
        motion::load_g1_frames(&assets.join(MOTION).to_string_lossy()).expect("load grab clip");
    for (index, frame) in frames.iter().enumerate() {
        let skin = motion_retarget::retarget_g1_frame_to_armored_skin(&mesh, &frames[0], frame)
            .expect("retarget grab frame");
        let left = position(&mesh, &skin, "LeftHand");
        let right = position(&mesh, &skin, "RightHand");
        println!(
            "{index},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9}",
            left.x, left.y, left.z, right.x, right.y, right.z
        );
    }
}
