//! Keyboard/mouse → combat intent mapping.
//!
//! Uses truth::Action and truth::Stance directly — no duplicate enums.

use winit::event::{ElementState, KeyEvent, MouseButton, MouseScrollDelta};
use winit::keyboard::Key;

pub use crate::truth::{Action, Stance};

/// High-level player intent derived from input.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PlayerIntent {
    Idle,
    MoveForward,
    MoveBack,
    MoveLeft,
    MoveRight,
    Action(Action),
    Dodge,
}

/// Plan-phase input derived from the current keyboard state.
#[derive(Debug, Clone, Default)]
pub struct PlanInput {
    pub selected_action: Option<Action>,
    pub selected_stance: Option<Stance>,
    pub confirmed: bool,
    pub toggle_debug: bool,
}

/// Accumulated input state across multiple events.
#[derive(Debug, Default, Clone)]
pub struct InputState {
    pub forward: bool,
    pub back: bool,
    pub left: bool,
    pub right: bool,
    pub dodge: bool,
    pub fire_action: Option<Action>,
    pub mouse_delta: (f32, f32),
    pub scroll: f32,
    selected_action: Option<Action>,
    selected_stance: Option<Stance>,
    confirmed: bool,
    toggle_debug: bool,
}

impl InputState {
    /// Process a keyboard event.
    pub fn handle_key(&mut self, event: &KeyEvent) {
        let pressed = event.state == ElementState::Pressed;
        match &event.logical_key {
            Key::Character(c) => {
                let s = c.as_str();
                match s {
                    "w" => {
                        self.forward = pressed;
                        if pressed {
                            self.selected_stance = Some(Stance::Top);
                        }
                    }
                    "s" => self.back = pressed,
                    "a" => self.left = pressed,
                    "d" => self.right = pressed,
                    " " => {
                        if pressed {
                            self.confirmed = true;
                        }
                    }
                    "1" => {
                        if pressed {
                            self.selected_action = Some(Action::Thrust);
                        }
                    }
                    "2" => {
                        if pressed {
                            self.selected_action = Some(Action::Block);
                        }
                    }
                    "3" => {
                        if pressed {
                            self.selected_action = Some(Action::Dodge);
                        }
                    }

                    "f1" => {
                        if pressed {
                            self.toggle_debug = true;
                        }
                    }
                    _ => {}
                }
            }
            Key::Named(n) => match n {
                winit::keyboard::NamedKey::Enter => {
                    if pressed {
                        self.confirmed = true;
                    }
                }
                _ => {}
            },
            _ => {}
        }
    }

    /// Process a mouse button event.
    pub fn handle_mouse_button(&mut self, button: MouseButton, pressed: bool) {
        if button == MouseButton::Left && pressed {
            self.fire_action = Some(Action::Thrust);
        }
    }

    /// Process mouse motion.
    pub fn handle_mouse_motion(&mut self, dx: f32, dy: f32) {
        self.mouse_delta = (dx, dy);
    }

    /// Process scroll.
    pub fn handle_scroll(&mut self, delta: &MouseScrollDelta) {
        self.scroll = match delta {
            MouseScrollDelta::LineDelta(_, y) => *y,
            MouseScrollDelta::PixelDelta(d) => d.y as f32 * 0.1,
        };
    }

    /// Consume the one-shot action trigger.
    pub fn take_action(&mut self) -> Option<Action> {
        self.fire_action.take()
    }

    /// Convert accumulated input state to a PlayerIntent.
    pub fn intent(&self) -> PlayerIntent {
        if let Some(action) = self.fire_action {
            return PlayerIntent::Action(action);
        }
        if self.dodge {
            return PlayerIntent::Dodge;
        }
        if self.forward {
            return PlayerIntent::MoveForward;
        }
        if self.back {
            return PlayerIntent::MoveBack;
        }
        if self.left {
            return PlayerIntent::MoveLeft;
        }
        if self.right {
            return PlayerIntent::MoveRight;
        }
        PlayerIntent::Idle
    }

    /// Reset per-frame deltas.
    pub fn reset_deltas(&mut self) {
        self.mouse_delta = (0.0, 0.0);
        self.scroll = 0.0;
        self.fire_action = None;
    }

    /// Build the current plan-phase input snapshot for the combat truth.
    pub fn plan_input(&self) -> PlanInput {
        PlanInput {
            selected_action: self.selected_action,
            selected_stance: self.selected_stance,
            confirmed: self.confirmed,
            toggle_debug: self.toggle_debug,
        }
    }

    /// Reset plan-phase one-shot state after it has been consumed.
    pub fn reset_plan(&mut self) {
        self.confirmed = false;
        self.toggle_debug = false;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plan_input_reflects_selection() {
        let mut input = InputState::default();
        input.selected_action = Some(Action::Thrust);
        input.selected_stance = Some(Stance::Top);
        input.confirmed = true;
        input.toggle_debug = true;

        let plan = input.plan_input();
        assert_eq!(plan.selected_action, Some(Action::Thrust));
        assert_eq!(plan.selected_stance, Some(Stance::Top));
        assert!(plan.confirmed);
        assert!(plan.toggle_debug);
    }

    #[test]
    fn reset_plan_clears_one_shots() {
        let mut input = InputState::default();
        input.confirmed = true;
        input.toggle_debug = true;
        input.reset_plan();

        let plan = input.plan_input();
        assert!(!plan.confirmed);
        assert!(!plan.toggle_debug);
    }

    #[test]
    fn movement_keys_do_not_affect_plan() {
        let input = InputState {
            forward: true,
            left: true,
            ..Default::default()
        };
        let plan = input.plan_input();
        assert!(plan.selected_action.is_none());
        assert!(plan.selected_stance.is_none());
        assert!(!plan.confirmed);
    }
}
