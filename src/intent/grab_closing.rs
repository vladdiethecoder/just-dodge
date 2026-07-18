//! MotionBricks opponent-conditioned closing solution for grab acquisition.
//!
//! The closing solution generates a physically plausible motion phrase that closes
//! distance through locomotion, not just arm reach. The full motion phrase may:
//! - Step-in/lunge toward the opponent
//! - Rotate the torso to face the target
//! - Acquire grip with hand/forearm
//! - Recover if the grab fails
//!
//! The solver must achieve contact within balance, joint-limit, collision and timing
//! constraints. If it cannot, the attempt honestly whiffs.

use serde::{Deserialize, Serialize};

use crate::intent::plan_phase::RootPosition;
use crate::truth::Side;

/// The closing motion phrase for a grab attempt.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GrabClosingSolution {
    /// The side initiating the grab.
    pub initiator: Side,
    /// The root trajectory (step-in/lunge) over the closing phase.
    pub root_trajectory: Vec<RootPosition>,
    /// The torso rotation at each step (degrees from facing direction).
    pub torso_rotation: Vec<f32>,
    /// The hand/forearm positions at each step (world space, millimetres).
    pub hand_positions: Vec<[i32; 3]>,
    /// The target opponent region at each step.
    pub target_region: Vec<[i32; 3]>,
    /// Whether the closing solution achieves contact.
    pub achieves_contact: bool,
    /// The estimated contact frame (if contact is achieved).
    pub contact_frame: Option<u32>,
    /// The estimated contact duration (if contact is achieved).
    pub contact_duration_ticks: Option<u32>,
}

impl GrabClosingSolution {
    /// Generate a closing solution for a grab attempt.
    ///
    /// The solver must close distance through locomotion, not just arm reach.
    /// The full motion phrase may step-in/lunge, rotate torso, acquire grip, and recover.
    pub fn generate(
        initiator: Side,
        start_root: RootPosition,
        opponent_root: RootPosition,
        grab_range_mm: i32,
        max_frames: u32,
        root_speed_mm_per_tick: i32,
    ) -> Self {
        let distance = planar_distance_mm(start_root, opponent_root);
        let closing_needed = distance.saturating_sub(grab_range_mm).max(0_i32);

        if closing_needed == 0 {
            // Already within range: no closing needed
            return Self {
                initiator,
                root_trajectory: vec![start_root],
                torso_rotation: vec![0.0],
                hand_positions: vec![[0, 0, 0]],
                target_region: vec![[opponent_root.x_mm, opponent_root.y_mm, opponent_root.z_mm]],
                achieves_contact: false,
                contact_frame: None,
                contact_duration_ticks: None,
            };
        }

        // Compute closing trajectory
        let frames_needed = (closing_needed as f32 / root_speed_mm_per_tick as f32).ceil() as u32;
        if frames_needed > max_frames {
            // Cannot close within time budget: honest whiff
            return Self {
                initiator,
                root_trajectory: vec![start_root],
                torso_rotation: vec![0.0],
                hand_positions: vec![[0, 0, 0]],
                target_region: vec![[opponent_root.x_mm, opponent_root.y_mm, opponent_root.z_mm]],
                achieves_contact: false,
                contact_frame: None,
                contact_duration_ticks: None,
            };
        }

        // Generate step-in/lunge trajectory
        let mut root_trajectory = Vec::with_capacity(frames_needed as usize + 1);
        let mut torso_rotation = Vec::with_capacity(frames_needed as usize + 1);
        let mut hand_positions = Vec::with_capacity(frames_needed as usize + 1);
        let mut target_region = Vec::with_capacity(frames_needed as usize + 1);

        root_trajectory.push(start_root);
        torso_rotation.push(0.0);
        hand_positions.push([start_root.x_mm, start_root.y_mm, start_root.z_mm]);
        target_region.push([opponent_root.x_mm, opponent_root.y_mm, opponent_root.z_mm]);

        let dx = opponent_root.x_mm - start_root.x_mm;
        let dz = opponent_root.z_mm - start_root.z_mm;
        let total_distance = (dx * dx + dz * dz).isqrt();

        if total_distance == 0 {
            return Self {
                initiator,
                root_trajectory,
                torso_rotation,
                hand_positions,
                target_region,
                achieves_contact: false,
                contact_frame: None,
                contact_duration_ticks: None,
            };
        }

        // Step toward opponent
        for frame in 1..=frames_needed {
            let t = frame as f32 / frames_needed as f32;
            let step = (closing_needed as f32 * t) as i32;
            let step = step.min(closing_needed);

            let new_x = start_root.x_mm + (dx * step) / total_distance;
            let new_z = start_root.z_mm + (dz * step) / total_distance;
            let new_root = RootPosition::new(new_x, start_root.y_mm, new_z);
            root_trajectory.push(new_root);

            // Torso rotation: face the target (simplified)
            let target_angle = (dz as f32).atan2(dx as f32).to_degrees();
            torso_rotation.push(target_angle * t);

            // Hand position: reach toward target
            let hand_reach = 400; // 400mm hand reach
            let hand_x = new_x + (dx * hand_reach) / total_distance;
            let hand_z = new_z + (dz * hand_reach) / total_distance;
            hand_positions.push([hand_x, start_root.y_mm, hand_z]);

            // Target region: opponent position
            target_region.push([opponent_root.x_mm, opponent_root.y_mm, opponent_root.z_mm]);
        }

        // Check if contact is achieved
        let final_distance = planar_distance_mm(*root_trajectory.last().unwrap(), opponent_root);
        let achieves_contact = final_distance <= grab_range_mm;
        let contact_frame = if achieves_contact {
            Some(frames_needed)
        } else {
            None
        };
        let contact_duration_ticks = if achieves_contact {
            Some(12) // 100ms at 120Hz
        } else {
            None
        };

        Self {
            initiator,
            root_trajectory,
            torso_rotation,
            hand_positions,
            target_region,
            achieves_contact,
            contact_frame,
            contact_duration_ticks,
        }
    }

    /// Check if the closing solution is feasible (within balance, joint-limit, collision, timing).
    pub fn is_feasible(&self) -> bool {
        // Check if the trajectory is within reasonable bounds
        if self.root_trajectory.len() > 120 {
            return false; // Too long (over 1 second at 120Hz)
        }

        // Check if the torso rotation is within reasonable bounds
        for &rotation in &self.torso_rotation {
            if rotation.abs() > 180.0 {
                return false; // Torso rotation > 180 degrees is infeasible
            }
        }

        // Check if the hand positions are within reasonable bounds
        for hand in &self.hand_positions {
            let distance = (hand[0] * hand[0] + hand[2] * hand[2]).isqrt();
            if distance > 2000 {
                return false; // Hand reach > 2m is infeasible
            }
        }

        true
    }
}

/// Compute planar distance between two root positions in millimetres.
pub fn planar_distance_mm(a: RootPosition, b: RootPosition) -> i32 {
    let dx = a.x_mm - b.x_mm;
    let dz = a.z_mm - b.z_mm;
    (dx * dx + dz * dz).isqrt()
}

/// ARDY (Adversarial Robust Dynamics) full-body feasibility validation.
///
/// Validates that a closing solution is physically plausible and achievable
/// within the fighter's balance, joint-limit, collision, and timing constraints.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArdyFeasibility {
    /// Whether the closing solution is feasible.
    pub feasible: bool,
    /// Reason for infeasibility (if any).
    pub reason: Option<String>,
    /// Balance score (0.0 = unstable, 1.0 = fully balanced).
    pub balance_score: f32,
    /// Joint limit violation count.
    pub joint_limit_violations: u32,
    /// Collision risk score (0.0 = no risk, 1.0 = high risk).
    pub collision_risk: f32,
    /// Timing margin (0.0 = no margin, 1.0 = ample margin).
    pub timing_margin: f32,
}

impl ArdyFeasibility {
    /// Validate a closing solution for full-body feasibility.
    pub fn validate(solution: &GrabClosingSolution) -> Self {
        let mut feasible = true;
        let mut reason = None;
        let mut balance_score = 1.0;
        let mut joint_limit_violations = 0;
        let mut collision_risk = 0.0;
        let mut timing_margin = 1.0;

        // Check balance: the root trajectory should not require extreme leaning
        for i in 1..solution.root_trajectory.len() {
            let prev = solution.root_trajectory[i - 1];
            let curr = solution.root_trajectory[i];
            let dx = curr.x_mm - prev.x_mm;
            let dz = curr.z_mm - prev.z_mm;
            let step = (dx * dx + dz * dz).isqrt();

            // Large steps (> 100mm per tick) may be unstable
            if step > 100 {
                balance_score -= 0.1;
            }

            // Very large steps (> 200mm per tick) are infeasible
            if step > 200 {
                feasible = false;
                reason = Some("Step size exceeds balance limit (200mm/tick)".to_string());
            }
        }

        // Check joint limits: torso rotation should be within human range
        for &rotation in &solution.torso_rotation {
            if rotation.abs() > 90.0 {
                joint_limit_violations += 1;
            }
        }

        if joint_limit_violations > 3 {
            feasible = false;
            reason = Some(format!(
                "Too many joint limit violations: {}",
                joint_limit_violations
            ));
        }

        // Check collision risk: hand should not penetrate opponent body
        for (i, hand) in solution.hand_positions.iter().enumerate() {
            let target = solution.target_region[i];
            let dx = hand[0] - target[0];
            let dz = hand[2] - target[2];
            let distance = (dx * dx + dz * dz).isqrt();

            // Very close (< 100mm) may indicate penetration
            if distance < 100 {
                collision_risk = 1.0;
                feasible = false;
                reason = Some("Hand-to-target distance indicates penetration risk".to_string());
            }
        }

        // Check timing: the closing should not take too long
        if solution.root_trajectory.len() > 60 {
            timing_margin = 0.0;
            feasible = false;
            reason = Some("Closing takes too long (> 500ms)".to_string());
        }

        // Clamp scores to [0, 1] using f32::clamp (Rust 1.79+)
        let balance_score = f32::clamp(balance_score, 0.0, 1.0);
        let collision_risk = f32::clamp(collision_risk, 0.0, 1.0);
        let timing_margin = f32::clamp(timing_margin, 0.0, 1.0);

        Self {
            feasible,
            reason,
            balance_score,
            joint_limit_violations,
            collision_risk,
            timing_margin,
        }
    }
}

/// The full grab closing pipeline: MotionBricks generates the solution, ARDY validates it.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GrabClosingPipeline {
    /// The closing solution (MotionBricks).
    pub solution: GrabClosingSolution,
    /// The feasibility validation (ARDY).
    pub feasibility: ArdyFeasibility,
}

impl GrabClosingPipeline {
    /// Generate and validate a grab closing solution.
    pub fn generate_and_validate(
        initiator: Side,
        start_root: RootPosition,
        opponent_root: RootPosition,
        grab_range_mm: i32,
        max_frames: u32,
        root_speed_mm_per_tick: i32,
    ) -> Self {
        let solution = GrabClosingSolution::generate(
            initiator,
            start_root,
            opponent_root,
            grab_range_mm,
            max_frames,
            root_speed_mm_per_tick,
        );
        let feasibility = ArdyFeasibility::validate(&solution);
        Self {
            solution,
            feasibility,
        }
    }
}
