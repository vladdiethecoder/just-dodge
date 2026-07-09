// Deterministic AI opponent controller.
// See docs/design/IMPLEMENTATION_PLAN_3ACTION.md for the contract.

use rand::SeedableRng;
use rand_xoshiro::Xoshiro256PlusPlus;

pub use crate::truth::{Action, Side, Stance};

/// Tunable personality knobs for the AI.
#[derive(Debug, Clone, Copy)]
pub struct AiPersonality {
    pub aggressiveness: f32, // 0.0..=1.0
    pub predictability: f32, // 0.0..=1.0
}

impl Default for AiPersonality {
    fn default() -> Self {
        Self {
            aggressiveness: 0.5,
            predictability: 0.5,
        }
    }
}

/// Seeded deterministic RNG wrapper.
/// Uses xoshiro256++ so replay bytes are stable across runs and platforms.
pub struct DeterministicRng {
    inner: Xoshiro256PlusPlus,
}

impl DeterministicRng {
    pub fn new(seed: u64) -> Self {
        Self {
            inner: Xoshiro256PlusPlus::seed_from_u64(seed),
        }
    }

    fn next_f32(&mut self) -> f32 {
        use rand::Rng;
        self.inner.r#gen()
    }

    fn next_bool(&mut self, probability: f32) -> bool {
        self.next_f32() < probability.clamp(0.0, 1.0)
    }

    fn next_u32(&mut self, range: std::ops::Range<u32>) -> u32 {
        use rand::Rng;
        self.inner.gen_range(range)
    }
}

/// Committed action + stance returned by the AI.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ActionCommit {
    pub action: Action,
    pub stance: Stance,
}

/// Observable combat state the AI is allowed to reason about.
#[derive(Debug, Clone)]
pub struct AiSnapshot {
    pub phase: String,
    pub my_health: f32,
    pub my_stamina: f32,
    pub opponent_health: f32,
    pub opponent_stamina: f32,
    /// Only available after reveal; must be None during Plan.
    pub last_player_action: Option<Action>,
    /// Only available after reveal; must be None during Plan.
    pub last_player_stance: Option<Stance>,
}

impl AiSnapshot {
    /// Convenience constructor for tests and callers.
    pub fn new(phase: impl Into<String>, my_health: f32, opponent_health: f32) -> Self {
        Self {
            phase: phase.into(),
            my_health,
            my_stamina: 1.0,
            opponent_health,
            opponent_stamina: 1.0,
            last_player_action: None,
            last_player_stance: None,
        }
    }
}

pub struct AiController {
    pub side: Side,
    pub personality: AiPersonality,
    pub rng: DeterministicRng,
}

impl AiController {
    pub fn new(side: Side, personality: AiPersonality, seed: u64) -> Self {
        Self {
            side,
            personality,
            rng: DeterministicRng::new(seed),
        }
    }

    /// Select an action and stance for the current frame.
    ///
    /// Determinism: identical sequence of `snapshot` inputs with the same seed
    /// produces identical outputs.
    ///
    /// Canon: during Plan phase the AI never reads the player's hidden intent,
    /// even if `last_player_action`/`last_player_stance` are accidentally populated.
    pub fn select_action(&mut self, snapshot: &AiSnapshot) -> ActionCommit {
        let action = self.pick_action(snapshot);
        let stance = self.pick_stance(snapshot);
        ActionCommit { action, stance }
    }

    fn pick_action(&mut self, snapshot: &AiSnapshot) -> Action {
        let in_plan = snapshot.phase.eq_ignore_ascii_case("plan");

        // Counter the revealed player action when available (post-reveal only).
        if !in_plan {
            if let Some(last) = snapshot.last_player_action {
                if self.rng.next_bool(0.5) {
                    return counter(last);
                }
            }
        }

        // Base weights: 40% Strike, 30% Block, 30% Grab.
        let mut weights = [0.4f32, 0.3f32, 0.3f32];

        // Health-driven biases.
        if snapshot.opponent_health < 0.30 {
            weights[0] += 0.2; // bias toward Strike
            weights[1] -= 0.1;
            weights[2] -= 0.1;
        }
        if snapshot.my_health < 0.30 {
            weights[1] += 0.2; // bias toward Block
            weights[0] -= 0.1;
            weights[2] -= 0.1;
        }

        // Clamp and renormalize so probabilities stay valid even when both
        // fighters are low on health.
        for w in &mut weights {
            *w = w.max(0.0);
        }
        let total: f32 = weights.iter().sum();
        if total > 0.0 {
            let scale = 1.0 / total;
            for w in &mut weights {
                *w *= scale;
            }
        }

        let r = self.rng.next_f32();
        if r < weights[0] {
            Action::Strike
        } else if r < weights[0] + weights[1] {
            Action::Block
        } else {
            Action::Grab
        }
    }

    fn pick_stance(&mut self, snapshot: &AiSnapshot) -> Stance {
        let in_plan = snapshot.phase.eq_ignore_ascii_case("plan");

        if !in_plan {
            if let Some(last_stance) = snapshot.last_player_stance {
                if self.rng.next_bool(0.3) {
                    return last_stance;
                }
            }
        }

        match self.rng.next_u32(0..3) {
            0 => Stance::Top,
            1 => Stance::Left,
            2 => Stance::Right,
            _ => unreachable!(),
        }
    }
}

/// Counter relationship: Strike beats Grab, Block beats Strike, Grab beats Block.
fn counter(action: Action) -> Action {
    match action {
        Action::Strike => Action::Block,
        Action::Block => Action::Grab,
        Action::Grab => Action::Strike,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ai_deterministic_same_seed() {
        let personality = AiPersonality::default();
        let mut a = AiController::new(Side::Opponent, personality, 12345);
        let mut b = AiController::new(Side::Opponent, personality, 12345);
        let snap = AiSnapshot::new("Plan", 1.0, 1.0);

        for _ in 0..100 {
            let ca = a.select_action(&snap);
            let cb = b.select_action(&snap);
            assert_eq!(ca.action, cb.action);
            assert_eq!(ca.stance, cb.stance);
        }
    }

    #[test]
    fn ai_different_seed_different_sequence() {
        let personality = AiPersonality::default();
        let mut a = AiController::new(Side::Opponent, personality, 1);
        let mut b = AiController::new(Side::Opponent, personality, 2);
        let snap = AiSnapshot::new("Plan", 1.0, 1.0);

        let seq_a: Vec<_> = (0..20).map(|_| a.select_action(&snap)).collect();
        let seq_b: Vec<_> = (0..20).map(|_| b.select_action(&snap)).collect();
        // The sequences should differ with overwhelming probability.
        assert_ne!(seq_a, seq_b);
    }

    #[test]
    fn ai_never_selects_invalid_action() {
        let personality = AiPersonality::default();
        let mut ai = AiController::new(Side::Opponent, personality, 7);

        let phases = ["Plan", "Reveal", "Resolve", "Observe"];
        for phase in phases {
            let mut snap = AiSnapshot::new(phase, 1.0, 1.0);
            snap.last_player_action = Some(Action::Strike);
            snap.last_player_stance = Some(Stance::Top);
            for _ in 0..200 {
                let commit = ai.select_action(&snap);
                // Stance is always one of the three valid variants.
                assert!(matches!(commit.stance, Stance::Top | Stance::Left | Stance::Right));
                // Action is always one of the three valid variants.
                assert!(matches!(commit.action, Action::Strike | Action::Block | Action::Grab));
            }
        }
    }

    #[test]
    fn ai_ignores_hidden_intent_during_plan() {
        let personality = AiPersonality::default();
        let mut ai = AiController::new(Side::Opponent, personality, 99);

        let mut plan_snap = AiSnapshot::new("Plan", 1.0, 1.0);
        plan_snap.last_player_action = Some(Action::Grab);
        plan_snap.last_player_stance = Some(Stance::Right);

        let reveal_snap = AiSnapshot::new("Reveal", 1.0, 1.0);
        // reveal_snap has no last action/stance, so it should only use base weights.

        let plan_commits: Vec<_> = (0..50).map(|_| ai.select_action(&plan_snap)).collect();
        let mut ai2 = AiController::new(Side::Opponent, personality, 99);
        let reveal_commits: Vec<_> = (0..50).map(|_| ai2.select_action(&reveal_snap)).collect();

        // Both sequences consume the same number of RNG draws with the same
        // seed because Plan ignores the hidden intent rather than using it.
        assert_eq!(plan_commits, reveal_commits);
    }

    #[test]
    fn ai_counters_revealed_action() {
        let personality = AiPersonality::default();
        // Sweep seeds to find at least one counter.
        for seed in 0..100 {
            let mut ai = AiController::new(Side::Opponent, personality, seed);
            let mut snap = AiSnapshot::new("Reveal", 1.0, 1.0);
            snap.last_player_action = Some(Action::Strike);
            let commit = ai.select_action(&snap);
            if commit.action == Action::Block {
                return;
            }
        }
        panic!("AI never countered a revealed Strike in 100 seeds");
    }
}
