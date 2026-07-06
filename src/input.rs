use winit::event::ElementState;
use winit::keyboard::Key;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Action {
    Strike,
    Block,
    Grab,
}

// Returns the action corresponding to a key press, if any
pub fn handle_key(event: &winit::event::KeyEvent) -> Option<Action> {
    if event.state != ElementState::Pressed {
        return None;
    }
    match &event.logical_key {
        Key::Character(c) if c.as_str() == "z" => Some(Action::Strike),
        Key::Character(c) if c.as_str() == "x" => Some(Action::Block),
        Key::Character(c) if c.as_str() == "c" => Some(Action::Grab),
        _ => None,
    }
}
