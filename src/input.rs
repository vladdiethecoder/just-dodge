//! Keyboard/mouse → combat intent mapping.
//!
//! Uses milestone3::Action directly — no duplicate action enum.

use winit::event::{ElementState, KeyEvent, MouseButton, MouseScrollDelta};
use winit::keyboard::Key;

pub use just_dodge::milestone3::{Action, RadialDi};

/// High-level player intent derived from input.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PlayerIntent {
    Idle,
    MoveForward,
    MoveBack,
    MoveLeft,
    MoveRight,
    Action(Action),
}

/// Plan-phase input derived from the current keyboard state.
#[derive(Debug, Clone, Default)]
pub struct PlanInput {
    pub selected_action: Option<Action>,
    pub radial_di: RadialDi,
    pub confirmed: bool,
    pub toggle_debug: bool,
    pub cycle_debug_camera: bool,
    pub toggle_hud: bool,
    pub lab_toggle_play: bool,
    pub lab_previous_frame: bool,
    pub lab_next_frame: bool,
    pub lab_toggle_presentation: bool,
}

/// One-shot commands for the presentation-only outer player flow.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct FlowInput {
    pub start: bool,
    pub replay: bool,
    pub rematch: bool,
    pub back_to_menu: bool,
    pub quit: bool,
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
    analog_radial: Option<(f32, f32)>,
    selected_action: Option<Action>,

    confirmed: bool,
    toggle_debug: bool,
    cycle_debug_camera: bool,
    toggle_hud: bool,
    lab_toggle_play: bool,
    lab_previous_frame: bool,
    lab_next_frame: bool,
    lab_toggle_presentation: bool,
    flow: FlowInput,
}

impl InputState {
    /// Process a keyboard event.
    pub fn handle_key(&mut self, event: &KeyEvent) {
        let pressed = event.state == ElementState::Pressed;
        match &event.logical_key {
            Key::Character(c) => {
                let s = c.as_str();
                match (s, pressed) {
                    ("w", _) => self.forward = pressed,
                    ("s", _) => self.back = pressed,
                    ("a", _) => self.left = pressed,
                    ("d", _) => self.right = pressed,
                    (" ", true) => {
                        self.confirmed = true;
                        self.flow.start = true;
                    }
                    ("1", true) => self.selected_action = Some(Action::Strike),
                    ("2", true) => self.selected_action = Some(Action::Block),
                    ("3", true) => self.selected_action = Some(Action::Grab),
                    ("4", true) => self.selected_action = Some(Action::Move),
                    ("f1", true) => self.toggle_debug = true,
                    ("p", true) => self.flow.replay = true,
                    ("r", true) => self.flow.rematch = true,
                    ("q", true) => self.flow.quit = true,
                    _ => {}
                }
            }
            Key::Named(winit::keyboard::NamedKey::Enter) if pressed => {
                self.confirmed = true;
                self.flow.start = true;
            }
            Key::Named(winit::keyboard::NamedKey::Space) if pressed => {
                self.confirmed = true;
                self.flow.start = true;
            }
            Key::Named(winit::keyboard::NamedKey::Escape) if pressed => {
                self.flow.back_to_menu = true;
            }
            Key::Named(winit::keyboard::NamedKey::F2) if pressed => {
                self.cycle_debug_camera = true;
            }
            Key::Named(winit::keyboard::NamedKey::F1) if pressed => {
                self.toggle_debug = true;
            }
            Key::Named(winit::keyboard::NamedKey::F3) if pressed => {
                self.toggle_hud = true;
            }
            Key::Named(winit::keyboard::NamedKey::F4) if pressed => {
                self.lab_toggle_play = true;
            }
            Key::Named(winit::keyboard::NamedKey::F5) if pressed => {
                self.lab_previous_frame = true;
            }
            Key::Named(winit::keyboard::NamedKey::F6) if pressed => {
                self.lab_next_frame = true;
            }
            Key::Named(winit::keyboard::NamedKey::F7) if pressed => {
                self.lab_toggle_presentation = true;
            }
            _ => {}
        }
    }

    /// Process a mouse button event.
    pub fn handle_mouse_button(&mut self, button: MouseButton, pressed: bool) {
        if button == MouseButton::Left && pressed {
            // Live first-person ingress selects the same M3 action that the
            // numbered Plan controls select; commit remains explicit.
            self.selected_action = Some(Action::Strike);
            self.fire_action = Some(Action::Strike);
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

    /// Direct radial-axis ingress for a gamepad backend. Combat truth receives
    /// only the normalized Q15 result from `radial_di`.
    pub fn handle_radial_axis(&mut self, right: f32, forward: f32) {
        self.analog_radial = Some((right, forward));
    }

    pub fn radial_di(&self) -> RadialDi {
        let keyboard = (
            i8::from(self.right) - i8::from(self.left),
            i8::from(self.forward) - i8::from(self.back),
        );
        let (right, forward) = self
            .analog_radial
            .filter(|(x, y)| x * x + y * y >= 0.04)
            .unwrap_or((f32::from(keyboard.0), f32::from(keyboard.1)));
        let length = (right * right + forward * forward).sqrt();
        if length <= f32::EPSILON {
            return RadialDi::ZERO;
        }
        let scale = 1.0 / length.max(1.0);
        RadialDi {
            right_q15: (right * scale * f32::from(i16::MAX)).round() as i16,
            forward_q15: (forward * scale * f32::from(i16::MAX)).round() as i16,
        }
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
            radial_di: self.radial_di(),
            confirmed: self.confirmed,
            toggle_debug: self.toggle_debug,
            cycle_debug_camera: self.cycle_debug_camera,
            toggle_hud: self.toggle_hud,
            lab_toggle_play: self.lab_toggle_play,
            lab_previous_frame: self.lab_previous_frame,
            lab_next_frame: self.lab_next_frame,
            lab_toggle_presentation: self.lab_toggle_presentation,
        }
    }

    /// Reset plan-phase one-shot state after it has been consumed.
    pub fn reset_plan(&mut self) {
        self.confirmed = false;
        self.toggle_debug = false;
        self.cycle_debug_camera = false;
        self.toggle_hud = false;
        self.lab_toggle_play = false;
        self.lab_previous_frame = false;
        self.lab_next_frame = false;
        self.lab_toggle_presentation = false;
    }

    pub const fn flow_input(&self) -> FlowInput {
        self.flow
    }

    pub fn reset_flow(&mut self) {
        self.flow = FlowInput::default();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plan_input_reflects_selection() {
        let input = InputState {
            selected_action: Some(Action::Strike),
            confirmed: true,
            toggle_debug: true,
            ..Default::default()
        };

        let plan = input.plan_input();
        assert_eq!(plan.selected_action, Some(Action::Strike));
        assert!(plan.confirmed);
        assert!(plan.toggle_debug);
    }

    #[test]
    fn left_click_selects_live_strike_without_implicit_commit() {
        let mut input = InputState::default();
        input.handle_mouse_button(MouseButton::Left, true);
        let plan = input.plan_input();
        assert_eq!(plan.selected_action, Some(Action::Strike));
        assert!(!plan.confirmed);
    }

    #[test]
    fn reset_plan_clears_one_shots() {
        let mut input = InputState {
            confirmed: true,
            toggle_debug: true,
            ..Default::default()
        };
        input.reset_plan();

        let plan = input.plan_input();
        assert!(!plan.confirmed);
        assert!(!plan.toggle_debug);
    }

    #[test]
    fn reset_plan_clears_motion_lab_one_shots() {
        let mut input = InputState {
            lab_toggle_play: true,
            lab_previous_frame: true,
            lab_next_frame: true,
            lab_toggle_presentation: true,
            ..Default::default()
        };
        let before = input.plan_input();
        assert!(before.lab_toggle_play);
        assert!(before.lab_previous_frame);
        assert!(before.lab_next_frame);
        assert!(before.lab_toggle_presentation);

        input.reset_plan();
        let after = input.plan_input();
        assert!(!after.lab_toggle_play);
        assert!(!after.lab_previous_frame);
        assert!(!after.lab_next_frame);
        assert!(!after.lab_toggle_presentation);
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
        assert_eq!(plan.radial_di.right_q15, -23_170);
        assert_eq!(plan.radial_di.forward_q15, 23_170);
        assert!(!plan.confirmed);
    }

    #[test]
    fn analog_radial_axis_is_dead_zoned_and_q15_quantized() {
        let mut input = InputState::default();
        input.handle_radial_axis(0.1, 0.1);
        assert_eq!(input.radial_di(), RadialDi::ZERO);
        input.handle_radial_axis(0.5, -0.5);
        assert_eq!(
            input.radial_di(),
            RadialDi {
                right_q15: 16_384,
                forward_q15: -16_384,
            }
        );
    }

    #[test]
    fn reset_flow_clears_only_outer_one_shots() {
        let mut input = InputState {
            selected_action: Some(Action::Block),
            flow: FlowInput {
                start: true,
                replay: true,
                rematch: true,
                back_to_menu: true,
                quit: true,
            },
            ..Default::default()
        };
        input.reset_flow();
        assert_eq!(input.flow_input(), FlowInput::default());
        assert_eq!(input.plan_input().selected_action, Some(Action::Block));
    }
}
