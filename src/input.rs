//! Keyboard/mouse → combat intent mapping.
//!
//! Uses combat::Action directly — no duplicate enum.

use winit::event::{ElementState, KeyEvent, MouseButton, MouseScrollDelta};
use winit::keyboard::Key;

use crate::combat;

/// High-level player intent derived from input.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PlayerIntent {
    Idle,
    MoveForward,
    MoveBack,
    MoveLeft,
    MoveRight,
    Action(combat::Action),
    Dodge,
}

/// Accumulated input state across multiple events.
#[derive(Debug, Default, Clone)]
pub struct InputState {
    pub forward: bool,
    pub back: bool,
    pub left: bool,
    pub right: bool,
    pub dodge: bool,
    pub fire_action: Option<combat::Action>,
    pub mouse_delta: (f32, f32),
    pub scroll: f32,
}

impl InputState {
    /// Process a keyboard event. Returns the new InputState.
    pub fn handle_key(&mut self, event: &KeyEvent) {
        let pressed = event.state == ElementState::Pressed;
        match &event.logical_key {
            Key::Character(c) => match c.as_str() {
                "w" => self.forward = pressed,
                "s" => self.back = pressed,
                "a" => self.left = pressed,
                "d" => self.right = pressed,
                " " => self.dodge = pressed,
                _ => {}
            },
            _ => {}
        }
    }

    /// Process a mouse button event.
    pub fn handle_mouse_button(&mut self, button: MouseButton, pressed: bool) {
        if pressed && button == MouseButton::Left {
            self.fire_action = Some(combat::Action::Strike);
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
    pub fn take_action(&mut self) -> Option<combat::Action> {
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
}
