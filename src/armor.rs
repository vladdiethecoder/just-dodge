// Armor and material response resolver.
// See docs/design/IMPLEMENTATION_PLAN_3ACTION.md for the contract.
//
// Prototype model: deterministic threshold + integrity absorption.
// No randomness, no floating-point hashing.

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Material {
    Plate,
    Leather,
    Cloth,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum BodyRegion {
    Head,
    Torso,
    LeftArm,
    RightArm,
    LeftLeg,
    RightLeg,
}

#[derive(Debug, Clone)]
pub struct ArmorPiece {
    pub region: BodyRegion,
    pub material: Material,
    pub integrity: f32, // 0.0..=1.0
    pub thickness: f32, // meters (reserved for future FEM model)
    pub coverage: f32,  // 0.0..=1.0 fraction of region covered
}

#[derive(Debug, Clone)]
pub struct Loadout {
    pub pieces: Vec<ArmorPiece>,
}

#[derive(Debug, Clone)]
pub struct ArmorState {
    pub pieces: Vec<ArmorPiece>,
}

#[derive(Debug, Clone)]
pub struct ArmorResult {
    pub residual_force: f32,
    pub penetrated_regions: Vec<BodyRegion>,
    pub integrity_deltas: Vec<(usize, f32)>,
    pub deflected: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum DamageType {
    Slash,
    Bash,
    Pierce,
}

/// Prototype material profile: threshold (raw), coverage, and material factor.
fn material_profile(material: Material) -> (f32, f32, f32) {
    match material {
        // Plate: threshold 60, bash is half-effective, coverage 0.85.
        Material::Plate => (60.0, 0.85, 1.0),
        // Leather: threshold 25, bash 0.75x, coverage 0.70.
        Material::Leather => (25.0, 0.70, 0.6),
        // Cloth: threshold 5, coverage 0.50.
        Material::Cloth => (5.0, 0.50, 0.3),
    }
}

/// Damage-type multiplier applied to the force that exceeds the threshold.
fn type_multiplier(material: Material, damage_type: DamageType) -> f32 {
    match (material, damage_type) {
        (Material::Plate, DamageType::Bash) => 0.5,
        (Material::Plate, DamageType::Slash) => 1.0,
        (Material::Plate, DamageType::Pierce) => 1.2,
        (Material::Leather, DamageType::Bash) => 0.75,
        _ => 1.0,
    }
}

/// Resolve one hit against the armor covering `region`.
///
/// Simplified deterministic rules:
/// - If `force <= threshold * material_factor`, the blow is fully deflected.
/// - Otherwise the armor absorbs up to its threshold; the remainder is scaled by
///   the damage-type multiplier and then bypasses according to `(1 - coverage)`.
/// - The absorbed portion costs integrity at 1% of the post-threshold force.
/// - When integrity reaches 0.0 the piece is destroyed and provides no future coverage.
pub fn resolve_armor(
    region: BodyRegion,
    force: f32,
    damage_type: DamageType,
    state: &mut ArmorState,
) -> ArmorResult {
    let mut residual_force = force;
    let mut penetrated_regions = Vec::new();
    let mut integrity_deltas = Vec::new();

    if let Some((idx, piece)) = state
        .pieces
        .iter_mut()
        .enumerate()
        .find(|(_, p)| p.region == region)
    {
        if piece.integrity > 0.0 {
            let (threshold, coverage, material_factor) = material_profile(piece.material);
            let effective_threshold = threshold * material_factor;

            if force > effective_threshold {
                let absorbed =
                    (force - effective_threshold) * type_multiplier(piece.material, damage_type);
                let integrity_loss = absorbed * 0.01;
                piece.integrity = (piece.integrity - integrity_loss).max(0.0);
                integrity_deltas.push((idx, -integrity_loss));

                if piece.integrity == 0.0 {
                    // Destroyed: coverage drops to zero, so all post-threshold force passes through.
                    residual_force = absorbed;
                } else {
                    let bypass = 1.0 - coverage;
                    residual_force = absorbed * bypass;
                }
            } else {
                residual_force = 0.0;
            }
        }
    }

    let deflected = residual_force == 0.0;
    if !deflected {
        penetrated_regions.push(region);
    }

    ArmorResult {
        residual_force,
        penetrated_regions,
        integrity_deltas,
        deflected,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn plate_torso() -> ArmorPiece {
        ArmorPiece {
            region: BodyRegion::Torso,
            material: Material::Plate,
            integrity: 1.0,
            thickness: 0.002,
            coverage: 0.85,
        }
    }

    #[test]
    fn armor_plate_deflects_low_force() {
        let mut state = ArmorState {
            pieces: vec![plate_torso()],
        };
        let result = resolve_armor(BodyRegion::Torso, 50.0, DamageType::Slash, &mut state);
        assert!(result.deflected);
        assert_eq!(result.residual_force, 0.0);
        assert!(result.penetrated_regions.is_empty());
        assert!(result.integrity_deltas.is_empty());
    }

    #[test]
    fn armor_plate_penetrates_high_force_and_reduces_integrity() {
        let mut state = ArmorState {
            pieces: vec![plate_torso()],
        };
        let result = resolve_armor(BodyRegion::Torso, 100.0, DamageType::Slash, &mut state);
        assert!(!result.deflected);
        // (100 - 60) * (1 - 0.85) bypass; allow small float tolerance.
        assert!((result.residual_force - 6.0).abs() < 1e-4);
        assert_eq!(result.penetrated_regions, vec![BodyRegion::Torso]);
        assert_eq!(result.integrity_deltas.len(), 1);
        let (idx, delta) = result.integrity_deltas[0];
        assert_eq!(idx, 0);
        assert!((delta - (-0.4)).abs() < 1e-4); // (100 - 60) * 0.01
        assert!((state.pieces[0].integrity - 0.6).abs() < 1e-4);
    }

    #[test]
    fn armor_bash_less_effective_than_slash_against_plate() {
        let mut slash_state = ArmorState {
            pieces: vec![plate_torso()],
        };
        let mut bash_state = ArmorState {
            pieces: vec![plate_torso()],
        };
        let slash = resolve_armor(
            BodyRegion::Torso,
            100.0,
            DamageType::Slash,
            &mut slash_state,
        );
        let bash = resolve_armor(BodyRegion::Torso, 100.0, DamageType::Bash, &mut bash_state);
        assert!(slash.residual_force > bash.residual_force);
        assert!((slash.residual_force - 6.0).abs() < 1e-4);
        assert!((bash.residual_force - 3.0).abs() < 1e-4);
    }

    #[test]
    fn armor_destroyed_piece_provides_no_coverage() {
        let mut state = ArmorState {
            pieces: vec![plate_torso()],
        };
        // Three full-strength slash hits reduce integrity to 0.
        for _ in 0..3 {
            resolve_armor(BodyRegion::Torso, 100.0, DamageType::Slash, &mut state);
        }
        assert_eq!(state.pieces[0].integrity, 0.0);

        // A destroyed piece provides no mitigation: full force passes through.
        let after = resolve_armor(BodyRegion::Torso, 100.0, DamageType::Slash, &mut state);
        assert!(!after.deflected);
        assert_eq!(after.residual_force, 100.0);
    }
}
