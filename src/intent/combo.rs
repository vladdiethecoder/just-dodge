//! Combo cancellation rules and integer-only airborne/juggle state.

use serde::{Deserialize, Serialize};

use super::intent::{Intent, StrikeVariant};

/// Gravity in millimetres per 60 Hz truth tick squared.
pub const GRAVITY_MM_PER_TICK_SQUARED: i32 = 3;
/// Launch speed used by throws and successful juggle strikes.
pub const LAUNCH_VELOCITY_MM_PER_TICK: i32 = 105;

/// Deterministic vertical combat state. Root positions are quantized to whole
/// millimetres before this state is advanced or serialized.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AirState {
    Grounded,
    Launched { vertical_velocity_mm_per_tick: i32 },
    GroundBounce { vertical_velocity_mm_per_tick: i32 },
    Wakeup { frames_remaining: u16 },
}

impl AirState {
    pub const fn is_airborne(self) -> bool {
        matches!(self, Self::Launched { .. } | Self::GroundBounce { .. })
    }
}

/// Combo state needed to gate a free phase-boundary chain.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ComboState {
    pub last_intent: Option<Intent>,
    pub cancel_window_frames: u16,
    pub air: AirState,
}

impl Default for ComboState {
    fn default() -> Self {
        Self {
            last_intent: None,
            cancel_window_frames: 0,
            air: AirState::Grounded,
        }
    }
}

impl ComboState {
    /// Cancel rules are data-like and action-family based. A boundary chain
    /// costs no additional setup frame; explicit `Cancel` supplies its penalty.
    pub const fn can_cancel_into(&self, next: Intent) -> bool {
        if self.cancel_window_frames == 0 {
            return false;
        }
        matches!(
            (self.last_intent, next),
            (
                Some(Intent::Strike { .. }),
                Intent::Strike { .. }
                    | Intent::Grab
                    | Intent::Move { .. }
                    | Intent::Dodge { .. }
                    | Intent::Feint
                    | Intent::Cancel
            )
        )
    }

    pub fn lock(&mut self, intent: Intent) {
        self.last_intent = Some(intent);
        self.cancel_window_frames = match intent {
            Intent::Strike {
                variant: StrikeVariant::Thrust,
            } => 8,
            Intent::Strike {
                variant: StrikeVariant::Slash,
            } => 10,
            _ => 0,
        };
    }

    pub fn tick(&mut self, root_y_mm: &mut i32) {
        self.cancel_window_frames = self.cancel_window_frames.saturating_sub(1);
        self.air = match self.air {
            AirState::Grounded => AirState::Grounded,
            AirState::Wakeup { frames_remaining } if frames_remaining > 1 => AirState::Wakeup {
                frames_remaining: frames_remaining - 1,
            },
            AirState::Wakeup { .. } => AirState::Grounded,
            AirState::Launched {
                vertical_velocity_mm_per_tick,
            }
            | AirState::GroundBounce {
                vertical_velocity_mm_per_tick,
            } => {
                let velocity = vertical_velocity_mm_per_tick - GRAVITY_MM_PER_TICK_SQUARED;
                *root_y_mm = root_y_mm.saturating_add(velocity);
                if *root_y_mm > 0 {
                    AirState::Launched {
                        vertical_velocity_mm_per_tick: velocity,
                    }
                } else if velocity < -12 {
                    *root_y_mm = 0;
                    AirState::GroundBounce {
                        vertical_velocity_mm_per_tick: (-velocity / 3).max(12),
                    }
                } else {
                    *root_y_mm = 0;
                    AirState::Wakeup {
                        frames_remaining: 18,
                    }
                }
            }
        };
    }

    pub const fn launch(&mut self) {
        self.air = AirState::Launched {
            vertical_velocity_mm_per_tick: LAUNCH_VELOCITY_MM_PER_TICK,
        };
    }
}
