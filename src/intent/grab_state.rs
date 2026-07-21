//! Deterministic grab state machine with separated acquisition and secure-grab states.
//!
//! GRAB_ACQUIRE_RANGE_MM = 650 determines whether a fighter may begin/continue a grab attempt.
//! It does NOT emit, imply, or guarantee secure_grab. A secure grab is a separate physical
//! state requiring authoritative, measured, bilateral hand/forearm-to-target contact.
//!
//! The existing retargeted run with 220.9mm visible surface clearance is NOT a secure grab.
//! It is reclassified as acquisition_failed/whiff.

use serde::{Deserialize, Serialize};

/// Root-space distance at which a fighter may begin a grab attempt.
/// This is NOT the secure-grab distance. Secure grab requires physical contact.
pub const GRAB_ACQUIRE_RANGE_MM: i32 = 650;

/// Maximum deterministic root translation in one 120 Hz truth tick.
pub const ROOT_SPEED_MM_PER_TICK: i32 = 50;

/// Minimum contact duration for secure_grab (100ms at 120Hz = 12 ticks).
pub const SECURE_GRAB_MIN_CONTACT_TICKS: u32 = 12;

/// Maximum prohibited mesh penetration for any physical state.
pub const PROHIBITED_PENETRATION_MAX_UM: u32 = 500;

/// Maximum visible hand-surface clearance for secure_grab admission.
pub const SECURE_GRAB_SURFACE_CLEARANCE_MAX_UM: u32 = 15_000;

/// The eight states of the grab state machine.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum GrabState {
    /// Initial distance > GRAB_ACQUIRE_RANGE_MM. Grab cannot begin.
    OutOfRange,
    /// Distance <= GRAB_ACQUIRE_RANGE_MM. Grab may begin.
    Acquire,
    /// Fighter is closing distance toward the opponent.
    ReachOrClose,
    /// First physical contact between hand/forearm and opponent region.
    FirstPhysicalContact,
    /// Contact persists continuously (>= SECURE_GRAB_MIN_CONTACT_TICKS).
    ContactSustained,
    /// All secure_grab admission criteria met.
    SecureGrab,
    /// Consequence of the secure grab (throw, hold, etc.).
    Consequence,
    /// Grab released or failed.
    ReleaseOrRecovery,
}

/// Failure modes for a grab attempt.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum GrabFailure {
    /// Grab cannot begin (distance > GRAB_ACQUIRE_RANGE_MM).
    OutOfRange,
    /// Fighter failed to reach physical contact before window expired.
    AcquisitionFailed,
    /// Contact was too brief (< SECURE_GRAB_MIN_CONTACT_TICKS).
    ContactTooBrief,
    /// Contact surface clearance > 15mm (no physical contact).
    NoPhysicalContact,
    /// Contact events and visible contact do not overlap in time.
    TemporalMismatch,
    /// Prohibited mesh penetration > 0.5mm.
    ProhibitedPenetration,
    /// Blocked or evaded by opponent.
    BlockedOrEvaded,
}

/// Secure grab admission criteria — all must be true.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct SecureGrabAdmission {
    /// Hand/forearm proxy contacts the intended opponent region.
    pub proxy_contact: bool,
    /// Final skinned hand surface distance <= 15,000um.
    pub surface_clearance_um: u32,
    /// Contact persists continuously >= 100ms (12 ticks at 120Hz).
    pub contact_duration_ticks: u32,
    /// Contact events and visible contact overlap in time.
    pub temporal_overlap: bool,
    /// Opponent response is caused by those same physical events.
    pub causal_response: bool,
    /// Prohibited mesh penetration <= 500um.
    pub prohibited_penetration_um: u32,
    /// No arm stretching, pose snapping, or presentation-only truth override.
    pub no_presentation_override: bool,
}

impl SecureGrabAdmission {
    /// Check if all secure grab admission criteria are met.
    pub fn admits(&self) -> bool {
        self.proxy_contact
            && self.surface_clearance_um <= SECURE_GRAB_SURFACE_CLEARANCE_MAX_UM
            && self.contact_duration_ticks >= SECURE_GRAB_MIN_CONTACT_TICKS
            && self.temporal_overlap
            && self.causal_response
            && self.prohibited_penetration_um <= PROHIBITED_PENETRATION_MAX_UM
            && self.no_presentation_override
    }
}

/// A grab attempt with full state tracking.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GrabAttempt {
    /// Current state of the grab state machine.
    pub state: GrabState,
    /// The side initiating the grab.
    pub initiator: crate::truth::Side,
    /// Truth frame when the grab attempt started.
    pub started_at_frame: u64,
    /// Truth frame when physical contact was first measured.
    pub first_contact_frame: Option<u64>,
    /// Truth frame when contact was last measured.
    pub last_contact_frame: Option<u64>,
    /// Secure grab admission criteria (populated when contact is measured).
    pub admission: Option<SecureGrabAdmission>,
    /// Failure mode if the grab failed.
    pub failure: Option<GrabFailure>,
    /// Root position at grab start.
    pub start_root: crate::intent::plan_phase::RootPosition,
    /// Root position at current tick.
    pub current_root: crate::intent::plan_phase::RootPosition,
    /// Opponent root position at current tick.
    pub opponent_root: crate::intent::plan_phase::RootPosition,
    /// Canonical bilateral manifold samples at 120Hz substeps (typed contact evidence).
    #[serde(default)]
    pub contact_samples: Vec<super::grab_contact::ContactManifoldSample>,
    /// The contiguous secure interval, if one satisfied every gate.
    #[serde(default)]
    pub secure_interval: Option<super::grab_contact::IntervalVerdict>,
}

impl GrabAttempt {
    /// Create a new grab attempt.
    pub fn new(
        initiator: crate::truth::Side,
        start_root: crate::intent::plan_phase::RootPosition,
        opponent_root: crate::intent::plan_phase::RootPosition,
        frame: u64,
    ) -> Self {
        let distance = planar_distance_mm(start_root, opponent_root);
        let state = if distance > GRAB_ACQUIRE_RANGE_MM {
            GrabState::OutOfRange
        } else {
            GrabState::Acquire
        };
        Self {
            state,
            initiator,
            started_at_frame: frame,
            first_contact_frame: None,
            last_contact_frame: None,
            admission: None,
            failure: None,
            start_root,
            current_root: start_root,
            opponent_root,
            contact_samples: Vec::new(),
            secure_interval: None,
        }
    }

    /// Check if the grab can begin (distance <= GRAB_ACQUIRE_RANGE_MM).
    pub fn can_begin(&self) -> bool {
        self.state != GrabState::OutOfRange
    }

    /// Check if the grab is in progress (not failed, not secure).
    pub fn is_in_progress(&self) -> bool {
        matches!(
            self.state,
            GrabState::Acquire
                | GrabState::ReachOrClose
                | GrabState::FirstPhysicalContact
                | GrabState::ContactSustained
        )
    }

    /// Check if the grab is secure (all admission criteria met).
    pub fn is_secure(&self) -> bool {
        self.state == GrabState::SecureGrab
    }

    /// Check if the grab failed.
    pub fn is_failed(&self) -> bool {
        self.failure.is_some()
    }

    /// Update the grab state based on one canonical bilateral manifold sample
    /// at one 120 Hz physics substep. Contact distance is NEVER written into
    /// RootPosition — surface distance, proxy overlap and root transforms are
    /// separate typed values. The root positions are owned by advance_roots.
    pub fn update_contact(&mut self, sample: &super::grab_contact::ContactManifoldSample) {
        self.contact_samples.push(*sample);
        if !sample.physics_contact_active {
            return;
        }
        if self.first_contact_frame.is_none() {
            self.first_contact_frame = Some(sample.substep_id);
            self.state = GrabState::FirstPhysicalContact;
        }
        self.last_contact_frame = Some(sample.substep_id);
        // Contiguous-interval evaluation derives ContactSustained/SecureGrab.
        if let Some(v) = super::grab_contact::any_secure_interval(&self.contact_samples) {
            self.state = GrabState::SecureGrab;
            self.secure_interval = Some(v);
        } else if let Some(first) = self.first_contact_frame {
            let dur = sample.substep_id.saturating_sub(first) as u32;
            if dur >= super::grab_contact::SECURE_GRAB_MIN_SUBSTEPS {
                self.state = GrabState::ContactSustained;
            }
        }
    }

    /// Update the grab state based on whiff (no contact).
    pub fn update_whiff(&mut self, _frame: u64) {
        if self.state == GrabState::Acquire || self.state == GrabState::ReachOrClose {
            self.failure = Some(GrabFailure::AcquisitionFailed);
            self.state = GrabState::ReleaseOrRecovery;
        }
    }

    /// Admit the grab as secure if all criteria are met.
    pub fn admit_secure(&mut self, admission: SecureGrabAdmission) {
        if admission.admits() {
            self.admission = Some(admission);
            self.state = GrabState::SecureGrab;
        } else {
            // Determine which criterion failed
            if !admission.proxy_contact
                || admission.surface_clearance_um > SECURE_GRAB_SURFACE_CLEARANCE_MAX_UM
            {
                self.failure = Some(GrabFailure::NoPhysicalContact);
            } else if admission.contact_duration_ticks < SECURE_GRAB_MIN_CONTACT_TICKS {
                self.failure = Some(GrabFailure::ContactTooBrief);
            } else if !admission.temporal_overlap {
                self.failure = Some(GrabFailure::TemporalMismatch);
            } else if admission.prohibited_penetration_um > PROHIBITED_PENETRATION_MAX_UM {
                self.failure = Some(GrabFailure::ProhibitedPenetration);
            }
            self.state = GrabState::ReleaseOrRecovery;
        }
    }

    /// Check if the grab should transition to consequence.
    pub fn to_consequence(&mut self) {
        if self.state == GrabState::SecureGrab {
            self.state = GrabState::Consequence;
        }
    }

    /// Check if the grab should transition to release/recovery.
    pub fn to_release(&mut self) {
        if self.state != GrabState::OutOfRange {
            self.state = GrabState::ReleaseOrRecovery;
        }
    }
}

/// Compute planar distance between two root positions in millimetres.
pub fn planar_distance_mm(
    a: crate::intent::plan_phase::RootPosition,
    b: crate::intent::plan_phase::RootPosition,
) -> i32 {
    let dx = a.x_mm - b.x_mm;
    let dz = a.z_mm - b.z_mm;
    (dx * dx + dz * dz).isqrt()
}

/// Check if a grab can begin based on root positions.
pub fn grab_can_begin(
    fighter_root: crate::intent::plan_phase::RootPosition,
    opponent_root: crate::intent::plan_phase::RootPosition,
) -> bool {
    planar_distance_mm(fighter_root, opponent_root) <= GRAB_ACQUIRE_RANGE_MM
}

/// Compute the required closing distance for a grab.
pub fn required_closing_distance_mm(
    fighter_root: crate::intent::plan_phase::RootPosition,
    opponent_root: crate::intent::plan_phase::RootPosition,
) -> i32 {
    let current = planar_distance_mm(fighter_root, opponent_root);
    current.saturating_sub(GRAB_ACQUIRE_RANGE_MM).max(0)
}

/// Compute the maximum frames needed to close to acquire range.
pub fn max_closing_frames(
    fighter_root: crate::intent::plan_phase::RootPosition,
    opponent_root: crate::intent::plan_phase::RootPosition,
) -> u32 {
    let closing = required_closing_distance_mm(fighter_root, opponent_root);
    if closing == 0 {
        return 0;
    }
    (closing as f32 / ROOT_SPEED_MM_PER_TICK as f32).ceil() as u32
}
