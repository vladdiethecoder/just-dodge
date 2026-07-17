//! Export the exact cooked C0 rig boundary for the offline R6K rotation bridge.
use just_dodge::asset;
use sha2::{Digest, Sha256};
use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::path::PathBuf;

fn hex(bytes: impl AsRef<[u8]>) -> String {
    bytes
        .as_ref()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn main() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let source =
        root.join("assets/source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin");
    let output = std::env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/tmp/pvp005_r6k_c0_skeleton.json"));
    let bytes = fs::read(&source).expect("read cooked C0 rig");
    let source_sha256 = hex(Sha256::digest(&bytes));
    let mesh = asset::load_skinned(source.to_str().expect("UTF-8 source path"))
        .expect("load cooked C0 rig");
    assert_eq!(mesh.bones.len(), 24, "R6K bridge requires exact 24-bone C0");
    let mut writer = BufWriter::new(File::create(&output).expect("create C0 skeleton JSON"));
    writeln!(writer, "{{").unwrap();
    writeln!(
        writer,
        "  \"schema\": \"just-dodge-pvp005-r6k-c0-skeleton-v1\","
    )
    .unwrap();
    writeln!(writer, "  \"source_path\": \"{}\",", source.display()).unwrap();
    writeln!(writer, "  \"source_sha256\": \"{source_sha256}\",").unwrap();
    writeln!(writer, "  \"coordinate_contract\": {{\"asset_up\": \"+Z\", \"asset_forward\": \"-Y\", \"asset_linear_unit\": \"centimetres under root scale 0.01\", \"runtime_up\": \"+Y\", \"runtime_forward\": \"+Z\", \"runtime_linear_unit\": \"metres\", \"asset_to_runtime_xyz\": [\"x\", \"z\", \"-y\"]}},").unwrap();
    writeln!(writer, "  \"bones\": [").unwrap();
    for (index, bone) in mesh.bones.iter().enumerate() {
        let separator = if index + 1 == mesh.bones.len() {
            ""
        } else {
            ","
        };
        let local = bone.rest_local.to_cols_array();
        let inverse_bind = bone.inverse_bind.to_cols_array();
        write!(
            writer,
            "    {{\"index\":{index},\"name\":\"{}\",\"parent\":{},\"rest_local_col_major\":[",
            bone.name, bone.parent
        )
        .unwrap();
        for (value_index, value) in local.iter().enumerate() {
            if value_index > 0 {
                write!(writer, ",").unwrap();
            }
            write!(writer, "{value:.9}").unwrap();
        }
        write!(writer, "],\"inverse_bind_col_major\":[").unwrap();
        for (value_index, value) in inverse_bind.iter().enumerate() {
            if value_index > 0 {
                write!(writer, ",").unwrap();
            }
            write!(writer, "{value:.9}").unwrap();
        }
        writeln!(writer, "]}}{separator}").unwrap();
    }
    writeln!(writer, "  ]").unwrap();
    writeln!(writer, "}}").unwrap();
    writer.flush().unwrap();
    println!(
        "PVP005_R6K_C0_EXPORT_PASS {} {}",
        output.display(),
        source_sha256
    );
}
