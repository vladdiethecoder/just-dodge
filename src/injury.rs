// Localized tissue injury and capability modifier resolver.
// See docs/design/IMPLEMENTATION_PLAN_3ACTION.md for the contract.
//
// Prototype model: deterministic trauma accumulation and capability penalties.
// No randomness.

pub use crate::armor::BodyRegion;

#[derive(Debug, Clone, Default)]
pub struct CapabilityDelta {
    pub speed_mul: f32,
    pub stamina_mul: f32,
    pub damage_mul: f32,
}

#[derive(Debug, Clone)]
pub struct RegionalInjury {
    pub region: BodyRegion,
    pub trauma: f32, // accumulated soft-tissue damage
    pub fracture: bool,
    pub capability_penalty: CapabilityDelta,
}

#[derive(Debug, Clone)]
pub struct InjuryState {
    pub regions: Vec<RegionalInjury>,
}

#[derive(Debug, Clone)]
pub struct InjuryResult {
    pub health_damage: f32,
    pub new_injury: Option<RegionalInjury>,
    pub capability_delta: CapabilityDelta,
    /// True when head or torso trauma exceeds the lethal threshold.
    pub lethal: bool,
}

fn is_limb(region: BodyRegion) -> bool {
    !matches!(region, BodyRegion::Head | BodyRegion::Torso)
}

fn identity_delta() -> CapabilityDelta {
    CapabilityDelta {
        speed_mul: 1.0,
        stamina_mul: 1.0,
        damage_mul: 1.0,
    }
}

fn new_regional_injury(region: BodyRegion) -> RegionalInjury {
    RegionalInjury {
        region,
        trauma: 0.0,
        fracture: false,
        capability_penalty: identity_delta(),
    }
}

fn apply_trauma_penalties(injury: &mut RegionalInjury) {
    if injury.trauma > 50.0 {
        injury.capability_penalty = CapabilityDelta {
            speed_mul: 0.9,
            stamina_mul: 0.9,
            damage_mul: 0.9,
        };
    }

    if injury.trauma > 100.0 && is_limb(injury.region) && !injury.fracture {
        injury.fracture = true;
        match injury.region {
            BodyRegion::LeftLeg | BodyRegion::RightLeg => {
                injury.capability_penalty.speed_mul *= 0.5;
            }
            BodyRegion::LeftArm | BodyRegion::RightArm => {
                injury.capability_penalty.damage_mul *= 0.5;
            }
            _ => {}
        }
    }
}

fn combined_capability_delta(regions: &[RegionalInjury]) -> CapabilityDelta {
    let mut combined = identity_delta();
    for r in regions {
        combined.speed_mul *= r.capability_penalty.speed_mul;
        combined.stamina_mul *= r.capability_penalty.stamina_mul;
        combined.damage_mul *= r.capability_penalty.damage_mul;
    }
    combined
}

/// Resolve residual force into localized trauma, health damage, and capability loss.
///
/// Simplified deterministic rules:
/// - `health_damage = residual_force * 0.5`.
/// - Trauma accumulates per region.
/// - Trauma above 50 applies a 0.9 multiplier to speed, stamina, and damage for that region.
/// - Limb trauma above 100 marks a fracture: legs halve speed, arms halve damage.
/// - Torso or head trauma above 80 is lethal.
/// - All regional penalties combine multiplicatively.
pub fn resolve_injury(
    region: BodyRegion,
    residual_force: f32,
    state: &mut InjuryState,
) -> InjuryResult {
    let health_damage = residual_force * 0.5;

    let existing = state.regions.iter().position(|r| r.region == region);
    let index = match existing {
        Some(idx) => idx,
        None => {
            state.regions.push(new_regional_injury(region));
            state.regions.len() - 1
        }
    };

    let (new_injury, lethal) = {
        let injury = &mut state.regions[index];
        injury.trauma += residual_force;
        apply_trauma_penalties(injury);

        let lethal = matches!(region, BodyRegion::Torso | BodyRegion::Head) && injury.trauma > 80.0;
        (injury.clone(), lethal)
    };

    let capability_delta = combined_capability_delta(&state.regions);

    InjuryResult {
        health_damage,
        new_injury: Some(new_injury),
        capability_delta,
        lethal,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn injury_accumulates_trauma_and_produces_penalties() {
        let mut state = InjuryState { regions: vec![] };
        let result = resolve_injury(BodyRegion::LeftLeg, 60.0, &mut state);
        assert_eq!(result.health_damage, 30.0);
        assert_eq!(result.new_injury.as_ref().unwrap().trauma, 60.0);
        assert_eq!(result.capability_delta.speed_mul, 0.9);
        assert_eq!(result.capability_delta.stamina_mul, 0.9);
        assert_eq!(result.capability_delta.damage_mul, 0.9);
        assert!(!result.lethal);
    }

    #[test]
    fn injury_limb_fracture_reduces_capability() {
        let mut state = InjuryState { regions: vec![] };
        resolve_injury(BodyRegion::RightArm, 60.0, &mut state);
        let result = resolve_injury(BodyRegion::RightArm, 70.0, &mut state);
        assert_eq!(result.new_injury.as_ref().unwrap().trauma, 130.0);
        assert!(result.new_injury.as_ref().unwrap().fracture);
        // 0.9 base penalty, then arm fracture halves damage: 0.9 * 0.5 = 0.45
        assert_eq!(result.capability_delta.damage_mul, 0.45);
        assert_eq!(result.capability_delta.speed_mul, 0.9);
    }

    #[test]
    fn injury_torso_trauma_above_threshold_is_lethal() {
        let mut state = InjuryState { regions: vec![] };
        let result = resolve_injury(BodyRegion::Torso, 90.0, &mut state);
        assert!(result.lethal);
        assert_eq!(result.new_injury.as_ref().unwrap().trauma, 90.0);
        assert_eq!(result.health_damage, 45.0);
    }

    #[test]
    fn injury_penalties_combine_multiplicatively() {
        let mut state = InjuryState { regions: vec![] };
        resolve_injury(BodyRegion::LeftLeg, 60.0, &mut state);
        let result = resolve_injury(BodyRegion::RightArm, 60.0, &mut state);
        assert_eq!(result.capability_delta.speed_mul, 0.9 * 0.9);
        assert_eq!(result.capability_delta.stamina_mul, 0.9 * 0.9);
        assert_eq!(result.capability_delta.damage_mul, 0.9 * 0.9);
    }
}
