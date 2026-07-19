//! Game-first deterministic intent/truth core.
//!
//! This is a clean module beside milestone3. It owns simultaneous intent locks,
//! fixed-point root goals, clinch and combo state, and forwards measured contact
//! through `DuelWorld` at 120 Hz physics / 60 Hz truth cadence.

pub mod clinch;
pub mod combo;
pub mod forecast;
pub mod grab_closing;
pub mod grab_contact;
pub mod grab_state;
#[allow(clippy::module_inception)]
pub mod intent;
pub mod plan_phase;

pub use clinch::{ClinchIntent, ClinchResolution, ClinchState};
pub use combo::{AirState, ComboState, GRAVITY_MM_PER_TICK_SQUARED, LAUNCH_VELOCITY_MM_PER_TICK};
pub use forecast::{ForecastOutcome, PredictedOutcome, forecast, predicted_outcome};
pub use grab_state::{
    GRAB_ACQUIRE_RANGE_MM, GrabAttempt, GrabFailure, GrabState, SecureGrabAdmission,
};
pub use intent::{
    Hitbox, Intent, MoveDirection, MoveParameters, State, StrikeVariant, TargetEligibility,
};
pub use plan_phase::{
    ActionabilityReason, CANCEL_PENALTY_FRAMES, InterruptOfferReason, PlanError, PlanEvent,
    PlanPhase, PlanSnapshot, PlanStatus, REPROMPT_OPTIONS, ROOT_SPEED_MM_PER_TICK, RepromptOption,
    RepromptReason, RootPosition,
};
