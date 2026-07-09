// Combat actions → MotionBricks primitives
//
// Per MotionBricks Section 3.1: constraint schema T = {T1, T2, T3}
//   T1: local root constraints (velocity, angular velocity, height)
//   T2: global root constraints (position, heading)
//   T3: pose constraints (joint positions/rotations)
//
// Context keyframes (indices 0..3): current pose state, always present
// Target keyframes (indices 4..7): desired end pose, vary by action
//
// Shape prototype: actions mapped to authored keyframe profiles.
// Reference clips from MotionBricks dataset to be integrated later.

use glam::Vec3;

// ---------------------------------------------------------------------------
// Keyframe constraint structures (matching T1/T2/T3 schema)
// ---------------------------------------------------------------------------

/// Local root constraint: root-relative motion features (4 dims)
#[derive(Debug, Clone, Copy)]
pub struct LocalRootConstraint {
    pub rot_vel: f32,         // angular velocity around Y
    pub lin_vel_xz: [f32; 2], // forward/lateral velocity
    pub root_y: f32,          // height above ground
}

/// Global root constraint: world-frame root state (5 dims)
#[derive(Debug, Clone, Copy)]
pub struct GlobalRootConstraint {
    pub pos_xz: [f32; 2],    // world X, Z
    pub heading: (f32, f32), // (cos, sin)
    pub pelvis_height: f32,
}

/// A keyframe set for one token (4 frames)
#[derive(Debug, Clone)]
pub struct Keyframe {
    pub local_root: LocalRootConstraint,
    pub global_root: GlobalRootConstraint,
    /// Whether this keyframe is a hard constraint (tau=0) or soft (tau>0)
    pub tau: u8, // 0 = hard, >0 = may advance early
    pub drop_frame: bool,
}

// ---------------------------------------------------------------------------
// Action definitions
// ---------------------------------------------------------------------------

/// Combat actions map to distinct keyframe profiles
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Action {
    Strike,
    Block,
    Grab,
}

/// The profile that defines what an action looks like in constraint space
#[derive(Debug, Clone)]
pub struct ActionProfile {
    pub action: Action,
    /// Target keyframes: the desired end state (indices 4..7 in constraint T)
    pub target_keyframes: [Keyframe; 4],
    /// Number of tokens for this action (6..16 range, 4 frames each)
    pub duration_tokens: u8,
    /// Root trajectory: displacement over the action duration
    pub root_displacement: Vec3, // world-space delta over the full motion
    /// Heading change: delta in radians
    pub heading_delta: f32,
    /// Base movement speed multiplier
    pub speed_multiplier: f32,
}

impl Action {
    /// Get the action profile for this action.
    /// Shape prototype: authored keyframes; later replaced by reference clip extraction.
    pub fn profile(&self) -> ActionProfile {
        match self {
            Action::Strike => strike_profile(),
            Action::Block => block_profile(),
            Action::Grab => grab_profile(),
        }
    }
}

// ---------------------------------------------------------------------------
// Action profiles — shape prototype authored keyframes
//
// These are rough estimates of what each action looks like in the
// constraint space. Real data from reference clips replaces these later.
// Values are in the normalized MotionBricks feature space (0-1 range
// for most features after normalization).
// ---------------------------------------------------------------------------

fn neutral_local_root() -> LocalRootConstraint {
    LocalRootConstraint {
        rot_vel: 0.0,
        lin_vel_xz: [0.0, 0.0],
        root_y: 0.0, // neutral height
    }
}

fn neutral_global_root() -> GlobalRootConstraint {
    GlobalRootConstraint {
        pos_xz: [0.0, 0.0],
        heading: (1.0, 0.0), // facing +Z
        pelvis_height: 0.0,
    }
}

fn neutral_keyframe() -> Keyframe {
    Keyframe {
        local_root: neutral_local_root(),
        global_root: neutral_global_root(),
        tau: 0, // hard constraint
        drop_frame: false,
    }
}

fn strike_profile() -> ActionProfile {
    // Strike: forward step + arm extension
    // Root: move forward ~0.5m, slight heading rock
    // Target state: aggressive forward lean, right arm forward
    let mut kf = neutral_keyframe();
    kf.local_root = LocalRootConstraint {
        rot_vel: 0.0,
        lin_vel_xz: [0.8, 0.0], // forward velocity
        root_y: -0.02,          // slight crouch
    };
    ActionProfile {
        action: Action::Strike,
        target_keyframes: [kf.clone(), kf.clone(), kf.clone(), kf.clone()],
        duration_tokens: 8,                          // 32 frames ≈ 1.07s at 30fps
        root_displacement: Vec3::new(0.0, 0.0, 0.5), // 0.5m forward
        heading_delta: 0.0,
        speed_multiplier: 1.0,
    }
}

fn block_profile() -> ActionProfile {
    // Block: hold ground, arms up, slight backward weight shift
    let mut kf = neutral_keyframe();
    kf.local_root = LocalRootConstraint {
        rot_vel: 0.0,
        lin_vel_xz: [0.0, 0.0], // stationary
        root_y: -0.04,          // deeper crouch for stability
    };
    ActionProfile {
        action: Action::Block,
        target_keyframes: [kf.clone(), kf.clone(), kf.clone(), kf.clone()],
        duration_tokens: 6,                            // 24 frames ≈ 0.8s
        root_displacement: Vec3::new(0.0, 0.0, -0.05), // slight backstep
        heading_delta: 0.0,
        speed_multiplier: 1.0,
    }
}

fn grab_profile() -> ActionProfile {
    // Grab: lunge forward, both arms extended, fast movement
    let mut kf = neutral_keyframe();
    kf.local_root = LocalRootConstraint {
        rot_vel: 0.0,
        lin_vel_xz: [1.2, 0.0], // fast forward
        root_y: -0.03,
    };
    ActionProfile {
        action: Action::Grab,
        target_keyframes: [kf.clone(), kf.clone(), kf.clone(), kf.clone()],
        duration_tokens: 10,                         // 40 frames ≈ 1.33s
        root_displacement: Vec3::new(0.0, 0.0, 1.0), // 1m lunge
        heading_delta: 0.0,
        speed_multiplier: 1.5,
    }
}

// ---------------------------------------------------------------------------
// Replanning coordination
//
// Per Appendix C: replan every 3-9 frames, instantly on command change.
// The combat module tracks the current action state.
// ---------------------------------------------------------------------------

/// Current state of an ongoing combat action
pub struct ActionState {
    pub action: Action,
    pub elapsed_frames: u32,
    pub total_frames: u32,
    /// Buffer of generated frames remaining
    pub frames_remaining: u32,
    /// Whether the action has completed
    pub complete: bool,
}

impl ActionState {
    pub fn from_action(action: Action) -> Self {
        let profile = action.profile();
        let total_frames = profile.duration_tokens as u32 * 4;
        Self {
            action,
            elapsed_frames: 0,
            total_frames,
            frames_remaining: total_frames,
            complete: false,
        }
    }

    /// Advance one frame. Returns true if action just completed.
    pub fn tick(&mut self) -> bool {
        self.elapsed_frames += 1;
        self.frames_remaining = self.frames_remaining.saturating_sub(1);
        if self.elapsed_frames >= self.total_frames && !self.complete {
            self.complete = true;
            true
        } else {
            false
        }
    }

    /// Check if replanning should trigger this frame.
    /// Per Appendix C: every 3-9 frames or when command changes.
    pub fn should_replan(&self, command_changed: bool) -> bool {
        if command_changed {
            return true;
        }
        self.frames_remaining <= 3 || self.elapsed_frames % 6 == 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_action_profiles_exist() {
        for action in &[Action::Strike, Action::Block, Action::Grab] {
            let profile = action.profile();
            assert_eq!(profile.action, *action);
            assert!(profile.duration_tokens >= 6 && profile.duration_tokens <= 16);
        }
    }

    #[test]
    fn test_action_state_lifecycle() {
        let mut state = ActionState::from_action(Action::Strike);
        assert_eq!(state.total_frames, 32); // 8 tokens * 4
        assert!(!state.complete);

        // Tick through all frames
        for i in 1..=32 {
            let completed = state.tick();
            if i < 32 {
                assert!(!completed);
            } else {
                assert!(completed);
            }
        }
        assert!(state.complete);
    }

    #[test]
    fn test_replanning_triggers() {
        let state = ActionState::from_action(Action::Block);
        // Low buffer should trigger replan
        assert!(state.should_replan(false)); // frames_remaining <= 3 triggers

        let new_state = ActionState::from_action(Action::Block);
        assert!(new_state.should_replan(true)); // command changed triggers
    }
}
