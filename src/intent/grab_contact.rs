//! Canonical secure-grab contact evidence and interval evaluation.
//!
//! Repairs for PVP005-UNIT2-EVIDENCE-INTEGRITY-RESET-001:
//! - Contact duration measured in 120 Hz physics-substep IDs (integer), never
//!   inferred from 60 Hz PlanPhase truth frames. The clock domain is explicit.
//! - A secure grab requires ONE contiguous interval satisfying every gate.
//! - Root transforms, surface distance, and proxy overlap are separate typed
//!   values. Contact distance is never written into RootPosition.
//! - temporal_overlap, causal_response and no_presentation_override are derived
//!   from runtime evidence — never hard-coded.

use serde::{Deserialize, Serialize};

/// Physics substeps per second. The DuelWorld runs 120 Hz physics substeps.
pub const PHYSICS_SUBSTEP_HZ: u32 = 120;
/// Minimum contiguous contact for secure_grab: 100ms = 12 substeps at 120Hz.
pub const SECURE_GRAB_MIN_SUBSTEPS: u32 = 12;
/// Maximum allowed hand-surface clearance for secure_grab admission.
pub const SECURE_GRAB_SURFACE_MAX_UM: u32 = 15_000;
/// Maximum prohibited mesh penetration.
pub const PROHIBITED_PENETRATION_MAX_UM: u32 = 500;

/// One authoritative bilateral contact manifold sample at one physics substep.
/// This is the ONLY contact evidence admitted to GrabAttempt. All values are
/// typed separately — no scalar is ever repurposed as another quantity.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct ContactManifoldSample {
    /// Physics substep ID at 120Hz (integer clock domain).
    pub substep_id: u64,
    /// Manifold identity (stable across substeps for one contact pair).
    pub manifold_id: u64,
    /// Skinned hand/forearm surface to declared opponent surface distance (um).
    pub surface_distance_um: u32,
    /// Contact-proxy overlap depth (um). Negative = separation.
    pub proxy_overlap_um: i32,
    /// Prohibited mesh penetration depth (um). Must stay <= 500.
    pub prohibited_penetration_um: u32,
    /// The authoritative physics event reports contact this substep.
    pub physics_contact_active: bool,
    /// The visible/rendered contact overlaps this substep in time.
    pub visible_contact_active: bool,
    /// The opponent's response this substep is caused by this manifold.
    pub opponent_response_causal: bool,
    /// A presentation-only override fabricated this sample (must be false).
    pub presentation_override: bool,
}

/// Evaluation of one contiguous contact interval against every gate.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IntervalVerdict {
    pub manifold_id: u64,
    pub start_substep: u64,
    pub end_substep: u64,
    pub duration_substeps: u32,
    pub duration_us: u32,
    pub contiguous: bool,
    pub surface_ok: bool,
    pub penetration_ok: bool,
    pub temporal_overlap_ok: bool,
    pub causal_response_ok: bool,
    pub no_override_ok: bool,
    pub duration_ok: bool,
    /// All gates pass for this one contiguous interval.
    pub secure: bool,
}

/// Extract maximal contiguous runs of `physics_contact_active` per manifold and
/// evaluate each against the full gate set. Duration uses integer substep IDs;
/// a run is contiguous iff substep IDs are consecutive (no interruption).
pub fn evaluate_intervals(samples: &[ContactManifoldSample]) -> Vec<IntervalVerdict> {
    let mut verdicts = Vec::new();
    let mut i = 0;
    while i < samples.len() {
        if !samples[i].physics_contact_active {
            i += 1;
            continue;
        }
        let manifold = samples[i].manifold_id;
        let start = i;
        let mut end = i;
        // Extend while same manifold, contact active, and substep IDs consecutive.
        while end + 1 < samples.len()
            && samples[end + 1].physics_contact_active
            && samples[end + 1].manifold_id == manifold
            && samples[end + 1].substep_id == samples[end].substep_id + 1
        {
            end += 1;
        }
        let run = &samples[start..=end];
        let contiguous = run
            .windows(2)
            .all(|w| w[1].substep_id == w[0].substep_id + 1);
        let duration_substeps = run.len() as u32;
        let duration_us = duration_substeps.saturating_mul(1_000_000) / PHYSICS_SUBSTEP_HZ;

        // Every gate value comes from THIS contiguous interval only.
        let surface_ok = run
            .iter()
            .all(|s| s.surface_distance_um <= SECURE_GRAB_SURFACE_MAX_UM);
        let penetration_ok = run
            .iter()
            .all(|s| s.prohibited_penetration_um <= PROHIBITED_PENETRATION_MAX_UM);
        let temporal_overlap_ok = run.iter().all(|s| s.visible_contact_active);
        let causal_response_ok = run.iter().any(|s| s.opponent_response_causal);
        let no_override_ok = run.iter().all(|s| !s.presentation_override);
        let duration_ok = duration_substeps >= SECURE_GRAB_MIN_SUBSTEPS;

        let secure = contiguous
            && surface_ok
            && penetration_ok
            && temporal_overlap_ok
            && causal_response_ok
            && no_override_ok
            && duration_ok;

        verdicts.push(IntervalVerdict {
            manifold_id: manifold,
            start_substep: run[0].substep_id,
            end_substep: run[run.len() - 1].substep_id,
            duration_substeps,
            duration_us,
            contiguous,
            surface_ok,
            penetration_ok,
            temporal_overlap_ok,
            causal_response_ok,
            no_override_ok,
            duration_ok,
            secure,
        });
        i = end + 1;
    }
    verdicts
}

/// GrabSecure is emitted only when ONE contiguous interval satisfies every gate.
pub fn any_secure_interval(samples: &[ContactManifoldSample]) -> Option<IntervalVerdict> {
    evaluate_intervals(samples).into_iter().find(|v| v.secure)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ok_sample(substep_id: u64, manifold_id: u64) -> ContactManifoldSample {
        ContactManifoldSample {
            substep_id,
            manifold_id,
            surface_distance_um: 5_000,
            proxy_overlap_um: 1_000,
            prohibited_penetration_um: 0,
            physics_contact_active: true,
            visible_contact_active: true,
            opponent_response_causal: substep_id == 0,
            presentation_override: false,
        }
    }

    fn with(
        base: ContactManifoldSample,
        surface_um: u32,
        penetration_um: u32,
        physics: bool,
        visible: bool,
        causal: bool,
        override_: bool,
    ) -> ContactManifoldSample {
        ContactManifoldSample {
            surface_distance_um: surface_um,
            prohibited_penetration_um: penetration_um,
            physics_contact_active: physics,
            visible_contact_active: visible,
            opponent_response_causal: causal,
            presentation_override: override_,
            ..base
        }
    }

    // Fixture (a): valid contiguous 100ms contact -> SECURE.
    #[test]
    fn fixture_a_valid_contiguous_100ms_secure() {
        let samples: Vec<_> = (0..12)
            .map(|i| with(ok_sample(i, 1), 5_000, 0, true, true, i == 0, false))
            .collect();
        let v = any_secure_interval(&samples);
        assert!(v.is_some(), "valid contiguous 100ms contact must be secure");
        assert_eq!(v.unwrap().duration_substeps, 12);
    }

    // Fixture (b): two short disjoint contacts (combined > 100ms) -> NOT secure.
    #[test]
    fn fixture_b_disjoint_contacts_not_secure() {
        let mut samples: Vec<_> = (0..7)
            .map(|i| with(ok_sample(i, 1), 5_000, 0, true, true, i == 0, false))
            .collect();
        // Gap (interruption) at substep 7-8 (no samples), then 7 more.
        samples.extend((9..16).map(|i| with(ok_sample(i, 1), 5_000, 0, true, true, false, false)));
        assert!(
            any_secure_interval(&samples).is_none(),
            "disjoint contacts must not combine into a secure interval"
        );
    }

    // Fixture (c): close surface without manifold contact -> NOT secure.
    #[test]
    fn fixture_c_close_surface_no_manifold_not_secure() {
        let samples: Vec<_> = (0..12)
            .map(|i| with(ok_sample(i, 1), 5_000, 0, false, true, false, false))
            .collect();
        assert!(any_secure_interval(&samples).is_none());
    }

    // Fixture (d): proxy contact without visible surface contact -> NOT secure.
    #[test]
    fn fixture_d_proxy_without_visible_not_secure() {
        let samples: Vec<_> = (0..12)
            .map(|i| with(ok_sample(i, 1), 5_000, 0, true, false, i == 0, false))
            .collect();
        assert!(any_secure_interval(&samples).is_none());
    }

    // Fixture (e): contact without causal response -> NOT secure.
    #[test]
    fn fixture_e_no_causal_response_not_secure() {
        let samples: Vec<_> = (0..12)
            .map(|i| with(ok_sample(i, 1), 5_000, 0, true, true, false, false))
            .collect();
        assert!(any_secure_interval(&samples).is_none());
    }

    // Fixture (f): excessive penetration -> NOT secure.
    #[test]
    fn fixture_f_excessive_penetration_not_secure() {
        let samples: Vec<_> = (0..12)
            .map(|i| with(ok_sample(i, 1), 5_000, 700, true, true, i == 0, false))
            .collect();
        assert!(any_secure_interval(&samples).is_none());
    }

    // Fixture (g): presentation-only override -> NOT secure.
    #[test]
    fn fixture_g_presentation_override_not_secure() {
        let samples: Vec<_> = (0..12)
            .map(|i| with(ok_sample(i, 1), 5_000, 0, true, true, i == 0, true))
            .collect();
        assert!(any_secure_interval(&samples).is_none());
    }

    // Clock-domain proof: 11 substeps (~91.7ms) is not enough; 12 (100ms) is.
    #[test]
    fn duration_boundary_100ms_exact() {
        let short: Vec<_> = (0..11)
            .map(|i| with(ok_sample(i, 1), 5_000, 0, true, true, i == 0, false))
            .collect();
        assert!(any_secure_interval(&short).is_none());
        let exact: Vec<_> = (0..12)
            .map(|i| with(ok_sample(i, 1), 5_000, 0, true, true, i == 0, false))
            .collect();
        assert!(any_secure_interval(&exact).is_some());
    }

    #[test]
    fn contact_sample_schema_is_integer_truth() {
        fn assert_eq_sample<T: Eq>() {}
        assert_eq_sample::<ContactManifoldSample>();
        assert_eq_sample::<crate::intent::grab_state::SecureGrabAdmission>();
        let sample = ContactManifoldSample {
            substep_id: 1,
            manifold_id: 2,
            surface_distance_um: 15_000,
            proxy_overlap_um: 1_000,
            prohibited_penetration_um: 500,
            physics_contact_active: true,
            visible_contact_active: true,
            opponent_response_causal: true,
            presentation_override: false,
        };
        let json = serde_json::to_value(sample).unwrap();
        assert_eq!(json["surface_distance_um"], 15_000);
        assert!(json.get("surface_distance_mm").is_none());

        let admission = crate::intent::grab_state::SecureGrabAdmission {
            proxy_contact: true,
            surface_clearance_um: 15_000,
            contact_duration_ticks: 12,
            temporal_overlap: true,
            causal_response: true,
            prohibited_penetration_um: 500,
            no_presentation_override: true,
        };
        assert!(admission.admits());
        let json = serde_json::to_value(admission).unwrap();
        assert!(json.get("surface_clearance_mm").is_none());
        assert!(json.get("prohibited_penetration_mm").is_none());
    }
}
