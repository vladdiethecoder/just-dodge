//! Presentation-only state for the built-in Motion Frontier Lab.
//!
//! The lab owns no combat, replay, contact, injury, or outcome state. It only
//! selects an immutable diagnostic frame and presentation layers.

use std::time::Duration;

pub const LAB_FPS: u128 = 30;
pub const LAB_FRAME_COUNT: usize = 64;
const NANOS_PER_SECOND: u128 = 1_000_000_000;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MotionFrontierLab {
    frame: usize,
    playing: bool,
    presentation_off: bool,
    frame_credit: u128,
}

impl MotionFrontierLab {
    pub fn new(frame: usize) -> Self {
        Self {
            frame: frame % LAB_FRAME_COUNT,
            playing: false,
            presentation_off: true,
            frame_credit: 0,
        }
    }

    pub const fn frame(&self) -> usize {
        self.frame
    }

    pub const fn playing(&self) -> bool {
        self.playing
    }

    pub const fn presentation_off(&self) -> bool {
        self.presentation_off
    }

    pub fn toggle_playing(&mut self) {
        self.playing = !self.playing;
        self.frame_credit = 0;
    }

    pub fn toggle_presentation(&mut self) {
        self.presentation_off = !self.presentation_off;
    }

    pub fn step_previous(&mut self) {
        self.playing = false;
        self.frame_credit = 0;
        self.frame = self.frame.checked_sub(1).unwrap_or(LAB_FRAME_COUNT - 1);
    }

    pub fn step_next(&mut self) {
        self.playing = false;
        self.frame_credit = 0;
        self.frame = (self.frame + 1) % LAB_FRAME_COUNT;
    }

    /// Advances the diagnostic cursor at exactly 30 frames per elapsed second.
    /// This is presentation timing only; explicit frame stepping remains exact.
    pub fn advance(&mut self, elapsed: Duration) {
        if !self.playing {
            return;
        }
        self.frame_credit = self
            .frame_credit
            .saturating_add(elapsed.as_nanos().saturating_mul(LAB_FPS));
        let frames = self.frame_credit / NANOS_PER_SECOND;
        self.frame_credit %= NANOS_PER_SECOND;
        self.frame = (self.frame + frames as usize) % LAB_FRAME_COUNT;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn starts_paused_on_exact_wrapped_frame_in_truth_view() {
        let lab = MotionFrontierLab::new(LAB_FRAME_COUNT + 7);
        assert_eq!(lab.frame(), 7);
        assert!(!lab.playing());
        assert!(lab.presentation_off());
    }

    #[test]
    fn exact_steps_pause_and_wrap_without_touching_time() {
        let mut lab = MotionFrontierLab::new(0);
        lab.toggle_playing();
        lab.step_previous();
        assert_eq!(lab.frame(), LAB_FRAME_COUNT - 1);
        assert!(!lab.playing());
        lab.step_next();
        assert_eq!(lab.frame(), 0);
    }

    #[test]
    fn playing_uses_integer_frame_credit() {
        let mut lab = MotionFrontierLab::new(3);
        lab.advance(Duration::from_secs(1));
        assert_eq!(lab.frame(), 3, "paused lab must not advance");

        lab.toggle_playing();
        lab.advance(Duration::from_millis(16));
        assert_eq!(lab.frame(), 3);
        lab.advance(Duration::from_millis(18));
        assert_eq!(lab.frame(), 4);
        lab.advance(Duration::from_secs(2));
        assert_eq!(lab.frame(), 0);
    }

    #[test]
    fn presentation_toggle_changes_only_visual_state() {
        let mut lab = MotionFrontierLab::new(11);
        lab.toggle_presentation();
        assert!(!lab.presentation_off());
        assert_eq!(lab.frame(), 11);
        assert!(!lab.playing());
    }
}
