//! Fixed, replayable scripted intent policy for the game-first combat loop.
//!
//! This deliberately has no runtime RNG. A seed only selects a stable starting
//! offset in a readable script table, and that seed is recorded by the match.
//! It drives M1's public `Intent` at its simultaneous-lock boundary.

pub use crate::intent::{ClinchIntent, Intent, MoveDirection, StrikeVariant};

/// Stable text used by the golden JSON bytes and hash serializer.
pub const fn intent_name(intent: Intent) -> &'static str {
    match intent {
        Intent::Strike {
            variant: StrikeVariant::Thrust,
        } => "Strike(Thrust)",
        Intent::Strike {
            variant: StrikeVariant::Slash,
        } => "Strike(Slash)",
        Intent::Block => "Block",
        Intent::Grab => "Grab",
        Intent::Move { .. } => "Move",
        Intent::Dodge { .. } => "Dodge",
        Intent::Feint => "Feint",
        Intent::Cancel => "Cancel",
        Intent::Idle => "Idle",
        Intent::Clinch {
            sub: ClinchIntent::Hold,
        } => "Clinch(Hold)",
        Intent::Clinch {
            sub: ClinchIntent::Tech,
        } => "Clinch(Tech)",
        Intent::Clinch {
            sub: ClinchIntent::Throw,
        } => "Clinch(Throw)",
        Intent::Clinch {
            sub: ClinchIntent::Break,
        } => "Clinch(Break)",
        Intent::Clinch {
            sub: ClinchIntent::Knee,
        } => "Clinch(Knee)",
    }
}

/// The three shipped deterministic opponent personalities.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ScriptKind {
    Aggressive,
    Defensive,
    Mixed,
}

impl ScriptKind {
    pub const fn name(self) -> &'static str {
        match self {
            Self::Aggressive => "aggressive",
            Self::Defensive => "defensive",
            Self::Mixed => "mixed",
        }
    }
}

const AGGRESSIVE: [Intent; 10] = [
    Intent::Move {
        dir: MoveDirection::Approach,
    },
    Intent::Grab,
    Intent::Strike {
        variant: StrikeVariant::Thrust,
    },
    Intent::Cancel,
    Intent::Strike {
        variant: StrikeVariant::Slash,
    },
    Intent::Clinch {
        sub: ClinchIntent::Hold,
    },
    Intent::Block,
    Intent::Feint,
    Intent::Dodge {
        dir: MoveDirection::Retreat,
    },
    Intent::Idle,
];

const DEFENSIVE: [Intent; 10] = [
    Intent::Block,
    Intent::Clinch {
        sub: ClinchIntent::Tech,
    },
    Intent::Move {
        dir: MoveDirection::Retreat,
    },
    Intent::Idle,
    Intent::Feint,
    Intent::Clinch {
        sub: ClinchIntent::Hold,
    },
    Intent::Block,
    Intent::Grab,
    Intent::Cancel,
    Intent::Strike {
        variant: StrikeVariant::Thrust,
    },
];

const MIXED: [Intent; 10] = [
    Intent::Feint,
    Intent::Strike {
        variant: StrikeVariant::Slash,
    },
    Intent::Move {
        dir: MoveDirection::LateralLeft,
    },
    Intent::Block,
    Intent::Grab,
    Intent::Dodge {
        dir: MoveDirection::LateralRight,
    },
    Intent::Cancel,
    Intent::Clinch {
        sub: ClinchIntent::Break,
    },
    Intent::Idle,
    Intent::Strike {
        variant: StrikeVariant::Thrust,
    },
];

/// A deterministic source of an opponent choice at one M1 PlanPhase lock.
pub trait PlanIntentPolicy {
    fn intent_for_plan(&self, plan_phase: u32) -> Intent;
}

/// Fixed script policy. `seed` is committed at match start; it cannot change
/// after construction and only rotates the script table.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ScriptedAi {
    seed: u64,
    kind: ScriptKind,
}

impl ScriptedAi {
    pub const fn new(kind: ScriptKind, seed: u64) -> Self {
        Self { seed, kind }
    }

    pub const fn kind(self) -> ScriptKind {
        self.kind
    }

    pub const fn seed(self) -> u64 {
        self.seed
    }

    pub const fn script(self) -> &'static [Intent] {
        match self.kind {
            ScriptKind::Aggressive => &AGGRESSIVE,
            ScriptKind::Defensive => &DEFENSIVE,
            ScriptKind::Mixed => &MIXED,
        }
    }
}

impl PlanIntentPolicy for ScriptedAi {
    fn intent_for_plan(&self, plan_phase: u32) -> Intent {
        let script = self.script();
        // This bounded integer arithmetic is platform-independent and avoids
        // consuming hidden mutable random state during replay.
        let offset = (self.seed % script.len() as u64) as usize;
        script[(offset + plan_phase as usize) % script.len()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_seed_and_plan_phase_always_choose_the_same_intent() {
        let a = ScriptedAi::new(ScriptKind::Mixed, 0xA11CE);
        let b = ScriptedAi::new(ScriptKind::Mixed, 0xA11CE);
        for phase in 0..1000 {
            assert_eq!(a.intent_for_plan(phase), b.intent_for_plan(phase));
        }
    }

    #[test]
    fn canned_tables_cover_the_full_public_intent_surface() {
        let mut names = Vec::new();
        for kind in [
            ScriptKind::Aggressive,
            ScriptKind::Defensive,
            ScriptKind::Mixed,
        ] {
            names.extend(
                ScriptedAi::new(kind, 0)
                    .script()
                    .iter()
                    .map(|intent| intent_name(*intent)),
            );
        }
        for required in [
            "Strike(Thrust)",
            "Strike(Slash)",
            "Block",
            "Grab",
            "Move",
            "Dodge",
            "Feint",
            "Cancel",
            "Idle",
            "Clinch(Hold)",
            "Clinch(Tech)",
        ] {
            assert!(names.contains(&required), "missing {required}");
        }
    }
}
