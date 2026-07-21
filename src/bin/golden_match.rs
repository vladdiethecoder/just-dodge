//! Headless M6 golden-match generator and verifier.
//!
//! Usage:
//!   golden_match --generate OUT_DIR
//!   golden_match --verify OUT_DIR
//!   golden_match --print-hashes

use std::path::Path;

use just_dodge::golden_replay::{
    GoldenScenario, assert_one_hundred_identical, verify_golden_set, write_golden_set,
};

fn usage() -> ! {
    eprintln!("usage: golden_match [--generate OUT_DIR | --verify OUT_DIR | --print-hashes]");
    std::process::exit(2);
}

fn print_results(label: &str, results: Vec<(GoldenScenario, u64)>) {
    for (scenario, truth_hash) in results {
        println!(
            "golden_match scenario={} final_truth_hash={truth_hash:016x} {label}",
            scenario.name()
        );
    }
}

fn print_hashes() -> Result<(), String> {
    let mut results = Vec::new();
    for scenario in GoldenScenario::ALL {
        let hash = assert_one_hundred_identical(scenario).map_err(|error| error.to_string())?;
        results.push((scenario, hash));
    }
    print_results("runs=100 identical=true", results);
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.as_slice() {
        [flag, output] if flag == "--generate" => {
            let results = write_golden_set(Path::new(output))?;
            print_results("generated=true", results);
            print_hashes().map_err(std::io::Error::other)?;
            println!("golden_match manifest={}/MANIFEST.sha256", output);
        }
        [flag, output] if flag == "--verify" => {
            let results = verify_golden_set(Path::new(output)).map_err(std::io::Error::other)?;
            print_results("verified=true runs=100 identical=true", results);
        }
        [flag] if flag == "--print-hashes" => {
            print_hashes().map_err(std::io::Error::other)?;
        }
        _ => usage(),
    }
    Ok(())
}
