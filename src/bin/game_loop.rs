//! Game-first debug-mannequin loop.
//!
//! The renderer is deliberately presentation-only: `PlanPhase` owns fixed-point
//! roots, action timing, contact, clinch, air state, and the displayed hash.
//! Run `cargo run --locked --bin game_loop` for the window or use
//! `--smoke N` for a deterministic, headless truth-only receipt.

use std::{
    path::Path,
    sync::Arc,
    time::{Duration, Instant},
};

use glam::{Mat4, Quat, Vec3, Vec3Swizzles, vec3};
use just_dodge::{
    asset::{self, SkeletalAnimation, SkinnedMeshData},
    hero_strike::{CONTACT_FRAME, FRAME_COUNT, HeroStrikePresentation},
    hud,
    intent::{
        ForecastOutcome, Intent, MoveDirection, PlanPhase, PlanSnapshot, PlanStatus, StrikeVariant,
        forecast, predicted_outcome,
    },
    renderer,
    truth::Side,
};
use winit::{
    application::ApplicationHandler,
    dpi::LogicalSize,
    event::{ElementState, WindowEvent},
    event_loop::{ActiveEventLoop, EventLoop},
    keyboard::{KeyCode, PhysicalKey},
    window::{Window, WindowId},
};

const TRUTH_STEP: Duration = Duration::from_nanos(1_000_000_000 / 60);
const MANNEQUIN_SKIN: &str = "source/meshy/c0_base_fighter/rigged_001/cooked/c0_skin8.bin";
const WALK_ANIMATION: &str = "source/meshy/c0_base_fighter/rigged_001/cooked/walking.anim";
const RUN_ANIMATION: &str = "source/meshy/c0_base_fighter/rigged_001/cooked/running.anim";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum AnimationClip {
    Reference,
    Walk,
    Run,
    HeroStrike,
}

fn animation_for_intent(intent: Option<Intent>) -> AnimationClip {
    match intent {
        Some(Intent::Move { .. }) => AnimationClip::Walk,
        Some(Intent::Dodge { .. }) => AnimationClip::Run,
        Some(Intent::Strike { .. }) => AnimationClip::HeroStrike,
        _ => AnimationClip::Reference,
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum CameraMode {
    FirstPerson,
    Observer,
}

impl CameraMode {
    const fn label(self) -> &'static str {
        match self {
            Self::FirstPerson => "FIRST PERSON",
            Self::Observer => "OBSERVER",
        }
    }

    const fn toggled(self) -> Self {
        match self {
            Self::FirstPerson => Self::Observer,
            Self::Observer => Self::FirstPerson,
        }
    }
}

struct PresentationAssets {
    mesh: SkinnedMeshData,
    reference_skin: Vec<Mat4>,
    walk_skins: Vec<Vec<Mat4>>,
    run_skins: Vec<Vec<Mat4>>,
    hero_strike: HeroStrikePresentation,
}

impl PresentationAssets {
    fn load(assets_root: &str) -> Self {
        let mesh = asset::load_skinned(&format!("{assets_root}/{MANNEQUIN_SKIN}"))
            .expect("M2 requires c0_base_fighter c0_skin8.bin");
        assert_eq!(
            mesh.bones.len(),
            24,
            "M2 debug mannequin must retain the C0 24-bone rig"
        );
        let reference_local: Vec<Mat4> = mesh.bones.iter().map(|bone| bone.rest_local).collect();
        let reference_skin = asset::reference_pose_skin_matrices(&mesh, &reference_local)
            .expect("base-fighter reference pose must skin");
        let walk = asset::load_skeletal_animation(&format!("{assets_root}/{WALK_ANIMATION}"))
            .expect("M2 requires c0 base-fighter walking.anim");
        let run = asset::load_skeletal_animation(&format!("{assets_root}/{RUN_ANIMATION}"))
            .expect("M2 requires c0 base-fighter running.anim");
        let hero_strike = HeroStrikePresentation::load(Path::new(assets_root), &mesh)
            .expect("M2 requires the admitted PVP005-R6 hero Strike clip");
        Self {
            walk_skins: animation_skins(&mesh, &walk),
            run_skins: animation_skins(&mesh, &run),
            mesh,
            reference_skin,
            hero_strike,
        }
    }

    fn skin_for(&self, intent: Option<Intent>, animation_tick: u64, action_tick: u16) -> Vec<Mat4> {
        match animation_for_intent(intent) {
            AnimationClip::Walk => sample_skin(&self.walk_skins, animation_tick)
                .unwrap_or_else(|| self.reference_skin.clone()),
            AnimationClip::Run => sample_skin(&self.run_skins, animation_tick)
                .unwrap_or_else(|| self.reference_skin.clone()),
            AnimationClip::HeroStrike => {
                let intent = intent.expect("HeroStrike clip requires a Strike intent");
                let frame = hero_strike_frame_for_tick(intent, action_tick);
                self.hero_strike.sample(frame, Mat4::IDENTITY).skin.to_vec()
            }
            AnimationClip::Reference => intent
                .map(|intent| placeholder_skin(&self.mesh, intent))
                .unwrap_or_else(|| self.reference_skin.clone()),
        }
    }
}

const MATCH_SETUP_TICKS: u64 = 60;
const MATCH_COUNTDOWN_TICKS: u64 = 30;
const MATCH_EXCHANGES: u8 = 3;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum MatchStage {
    Boot,
    MatchSetup,
    Countdown,
    Fight,
    Result,
}

impl MatchStage {
    const fn label(self) -> &'static str {
        match self {
            Self::Boot => "Boot",
            Self::MatchSetup => "MatchSetup",
            Self::Countdown => "Countdown",
            Self::Fight => "Fight",
            Self::Result => "Result",
        }
    }
}

/// Presentation-only automated match driver. It submits ordinary `PlanPhase`
/// intents and advances its existing truth tick; it owns no combat state and
/// does not alter the resolution rules.
#[derive(Debug)]
struct MatchLoop {
    stage: MatchStage,
    stage_tick: u64,
    exchanges_started: u8,
    finish_after_boundary: bool,
}

impl MatchLoop {
    const fn new() -> Self {
        Self {
            stage: MatchStage::Boot,
            stage_tick: 0,
            exchanges_started: 0,
            finish_after_boundary: false,
        }
    }

    fn stage(&self) -> MatchStage {
        self.stage
    }

    fn presentation_intents(&self, snapshot: &PlanSnapshot) -> [Option<Intent>; 2] {
        match self.stage {
            // Setup is a presentation runway: the PlanPhase mapping is reused
            // with a Move intent, while authoritative roots remain untouched.
            MatchStage::MatchSetup => [
                Some(Intent::move_standard(MoveDirection::Approach)),
                Some(Intent::move_standard(MoveDirection::Approach)),
            ],
            MatchStage::Fight => snapshot.locked,
            MatchStage::Boot | MatchStage::Countdown | MatchStage::Result => [None, None],
        }
    }

    fn animation_ticks(&self, snapshot: &PlanSnapshot) -> [u64; 2] {
        match self.stage {
            MatchStage::MatchSetup => [self.stage_tick; 2],
            _ => [
                u64::from(snapshot.action_ticks[0]),
                u64::from(snapshot.action_ticks[1]),
            ],
        }
    }

    fn step(&mut self, phase: &mut PlanPhase) {
        match self.stage {
            MatchStage::Boot => {
                self.stage = MatchStage::MatchSetup;
                self.stage_tick = 0;
            }
            MatchStage::MatchSetup => {
                self.stage_tick = self.stage_tick.saturating_add(1);
                if self.stage_tick >= MATCH_SETUP_TICKS {
                    self.stage = MatchStage::Countdown;
                    self.stage_tick = 0;
                }
            }
            MatchStage::Countdown => {
                self.stage_tick = self.stage_tick.saturating_add(1);
                if self.stage_tick >= MATCH_COUNTDOWN_TICKS {
                    self.stage = MatchStage::Fight;
                    self.stage_tick = 0;
                }
            }
            MatchStage::Fight => self.step_fight(phase),
            MatchStage::Result => {
                self.stage_tick = self.stage_tick.saturating_add(1);
            }
        }
    }

    fn step_fight(&mut self, phase: &mut PlanPhase) {
        if phase.status() == PlanStatus::Planning {
            if self.finish_after_boundary {
                self.stage = MatchStage::Result;
                self.stage_tick = 0;
                return;
            }
            let (player, opponent) = match self.exchanges_started {
                0 => (
                    Intent::move_standard(MoveDirection::Approach),
                    Intent::move_standard(MoveDirection::Approach),
                ),
                1 => (
                    Intent::Dodge {
                        dir: MoveDirection::LateralLeft,
                    },
                    Intent::Strike {
                        variant: StrikeVariant::Slash,
                    },
                ),
                _ => (
                    Intent::Strike {
                        variant: StrikeVariant::Slash,
                    },
                    Intent::Dodge {
                        dir: MoveDirection::LateralRight,
                    },
                ),
            };
            for (side, intent) in [(Side::Player, player), (Side::Opponent, opponent)] {
                if phase.can_submit_intent(side) {
                    phase
                        .submit_intent(side, intent)
                        .expect("automated match intents must be admissible");
                }
            }
            assert_eq!(
                phase.status(),
                PlanStatus::Executing {
                    frames_remaining: u16::MAX
                },
                "automated match must lock both PlanPhase sides"
            );
            self.exchanges_started = self.exchanges_started.saturating_add(1);
            self.finish_after_boundary = self.exchanges_started >= MATCH_EXCHANGES;
        } else {
            phase
                .step_truth_tick()
                .expect("automated match must advance a locked PlanPhase tick");
        }
    }
}

fn animation_skins(mesh: &SkinnedMeshData, animation: &SkeletalAnimation) -> Vec<Vec<Mat4>> {
    assert_eq!(
        animation.bone_count,
        mesh.bones.len(),
        "ANM1 bone count mismatch"
    );
    animation
        .frames
        .iter()
        .map(|frame| {
            let mut root_locked = frame.clone();
            // The animation clip's root displacement is intentionally discarded:
            // PlanPhase's integer root is the only locomotion authority.
            root_locked[0].w_axis = mesh.bones[0].rest_local.w_axis;
            asset::retarget_world_animation_frame(mesh, mesh, &root_locked)
                .expect("base fighter animation must retarget to itself")
        })
        .collect()
}

fn sample_skin(frames: &[Vec<Mat4>], truth_frame: u64) -> Option<Vec<Mat4>> {
    (!frames.is_empty()).then(|| frames[truth_frame as usize % frames.len()].clone())
}

/// Map a 60 Hz authoritative Strike action onto the 64-frame source clip.
///
/// The source clip has no trusted FPS metadata, so timing is driven by the
/// intent-owned startup/active/IASA windows rather than wall-clock seconds:
/// wind-up ends at the first hitbox tick, contact occupies the hitbox window,
/// follow-through ends at IASA, and the remaining source frames are recovery.
fn hero_strike_frame_for_tick(intent: Intent, action_tick: u16) -> usize {
    let Intent::Strike { .. } = intent else {
        return 0;
    };
    let state = intent.state();
    let last_tick = state.anim_length.saturating_sub(1);
    let hitbox = intent
        .hitboxes()
        .first()
        .copied()
        .expect("Strike presentation requires a hitbox timing row");
    let contact_tick = hitbox.start_tick.min(last_tick);
    let active_end_tick = contact_tick
        .saturating_add(hitbox.active_ticks.saturating_sub(1))
        .min(last_tick);
    let recovery_start_tick = state.iasa_at.min(last_tick).max(active_end_tick);
    let tick = action_tick.min(last_tick);
    let active_end_frame = (CONTACT_FRAME + 8).min(FRAME_COUNT - 1);
    let follow_through_end_frame = FRAME_COUNT - 9;

    if tick <= contact_tick {
        scale_clip_frame(tick, 0, contact_tick, 0, CONTACT_FRAME)
    } else if tick <= active_end_tick {
        scale_clip_frame(
            tick,
            contact_tick,
            active_end_tick,
            CONTACT_FRAME,
            active_end_frame,
        )
    } else if tick <= recovery_start_tick {
        scale_clip_frame(
            tick,
            active_end_tick,
            recovery_start_tick,
            active_end_frame,
            follow_through_end_frame,
        )
    } else {
        scale_clip_frame(
            tick,
            recovery_start_tick,
            last_tick,
            follow_through_end_frame,
            FRAME_COUNT - 1,
        )
    }
}

fn scale_clip_frame(
    tick: u16,
    first_tick: u16,
    last_tick: u16,
    first_frame: usize,
    last_frame: usize,
) -> usize {
    if tick <= first_tick || first_tick >= last_tick {
        return first_frame;
    }
    if tick >= last_tick {
        return last_frame;
    }
    let tick_span = usize::from(last_tick - first_tick);
    first_frame
        + (usize::from(tick - first_tick) * (last_frame - first_frame) + tick_span / 2) / tick_span
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hero_strike_timeline_follows_authoritative_slash_windows() {
        let intent = Intent::Strike {
            variant: StrikeVariant::Slash,
        };
        let frames: Vec<usize> = (0..=intent.state().anim_length)
            .map(|tick| hero_strike_frame_for_tick(intent, tick))
            .collect();
        assert_eq!(frames[0], 0);
        assert_eq!(frames[4], CONTACT_FRAME, "slash contact starts at tick 4");
        assert!(
            frames[4] < frames[9],
            "active contact advances the source clip"
        );
        assert!(
            frames[9] < frames[17],
            "follow-through advances before IASA"
        );
        assert_eq!(
            frames[21],
            FRAME_COUNT - 1,
            "recovery reaches the clip tail"
        );
        assert!(frames.windows(2).all(|pair| pair[0] <= pair[1]));
    }

    #[test]
    fn hero_strike_timeline_uses_thrust_hitbox_start() {
        let intent = Intent::Strike {
            variant: StrikeVariant::Thrust,
        };
        assert_eq!(hero_strike_frame_for_tick(intent, 3), CONTACT_FRAME);
        assert_eq!(
            hero_strike_frame_for_tick(intent, intent.state().anim_length - 1),
            FRAME_COUNT - 1
        );
    }
}

fn placeholder_skin(mesh: &SkinnedMeshData, intent: Intent) -> Vec<Mat4> {
    let mut local: Vec<Mat4> = mesh.bones.iter().map(|bone| bone.rest_local).collect();
    let (left_arm, right_arm, spine) = match (
        bone_index(mesh, "LeftArm"),
        bone_index(mesh, "RightArm"),
        bone_index(mesh, "Spine"),
    ) {
        (Some(left), Some(right), Some(spine)) => (left, right, spine),
        _ => return asset::reference_pose_skin_matrices(mesh, &local).expect("reference skin"),
    };
    match intent {
        Intent::Strike { .. } => {
            rotate_local(&mut local, right_arm, Quat::from_rotation_x(-0.95));
            rotate_local(&mut local, left_arm, Quat::from_rotation_x(0.30));
            rotate_local(&mut local, spine, Quat::from_rotation_y(0.20));
        }
        Intent::Block => {
            rotate_local(&mut local, left_arm, Quat::from_rotation_x(-1.05));
            rotate_local(&mut local, right_arm, Quat::from_rotation_x(-1.05));
        }
        Intent::Grab | Intent::Clinch { .. } => {
            rotate_local(&mut local, left_arm, Quat::from_rotation_x(-0.72));
            rotate_local(&mut local, right_arm, Quat::from_rotation_x(-0.72));
        }
        Intent::Feint => rotate_local(&mut local, right_arm, Quat::from_rotation_x(-0.42)),
        Intent::Cancel => rotate_local(&mut local, spine, Quat::from_rotation_y(-0.18)),
        Intent::Idle
        | Intent::Move { .. }
        | Intent::Dodge { .. }
        | Intent::Draw
        | Intent::Sheath => {}
    }
    asset::reference_pose_skin_matrices(mesh, &local).expect("placeholder pose must skin")
}

fn rotate_local(local: &mut [Mat4], index: usize, delta: Quat) {
    let (scale, rotation, translation) = local[index].to_scale_rotation_translation();
    local[index] =
        Mat4::from_scale_rotation_translation(scale, (rotation * delta).normalize(), translation);
}

fn bone_index(mesh: &SkinnedMeshData, name: &str) -> Option<usize> {
    mesh.bones.iter().position(|bone| bone.name == name)
}

fn root_vec(snapshot: &PlanSnapshot, side: Side) -> Vec3 {
    let root = snapshot.roots[side_index(side)];
    vec3(
        root.x_mm as f32 / 1000.0,
        root.y_mm as f32 / 1000.0,
        root.z_mm as f32 / 1000.0,
    )
}

const fn side_index(side: Side) -> usize {
    match side {
        Side::Player => 0,
        Side::Opponent => 1,
    }
}

fn planar_distance_m(snapshot: &PlanSnapshot) -> f32 {
    let left = root_vec(snapshot, Side::Player);
    let right = root_vec(snapshot, Side::Opponent);
    (left.x - right.x).hypot(left.z - right.z)
}

/// F-006 reactive AI opponent: adapts to player distance, stance, and
/// recent action history rather than cycling a fixed script.
fn reactive_opponent(snapshot: &PlanSnapshot, opponent_history: &[Intent]) -> Intent {
    use MoveDirection::{Approach, CircleClockwise, LateralLeft, Retreat};

    let player_root = &snapshot.roots[0];
    let opp_root = &snapshot.roots[1];
    let dx = (player_root.x_mm - opp_root.x_mm) as f32 / 1000.0;
    let dz = (player_root.z_mm - opp_root.z_mm) as f32 / 1000.0;
    let distance = (dx * dx + dz * dz).sqrt();
    let player_action = snapshot.locked[0]
        .map(|a| format!("{a:?}"))
        .unwrap_or_default();
    let opponent_burst = snapshot.burst[1];
    let opponent_tempo = snapshot.tempo[1];

    // Close range (< 1.0m): react to player's likely action
    if distance < 1.0 {
        if player_action.contains("Strike") || player_action.contains("Thrust") {
            // Player attacking — block or dodge based on tempo
            if opponent_tempo > 40 && opponent_burst > 30 {
                return Intent::Block;
            }
            return Intent::Dodge { dir: LateralLeft };
        }
        if player_action.contains("Grab") {
            // Player grabbing — strike to counter or retreat
            if opponent_burst > 50 {
                return Intent::Strike {
                    variant: StrikeVariant::Slash,
                };
            }
            return Intent::move_standard(Retreat);
        }
        // Player passive or moving — press the advantage
        if opponent_burst > 60 {
            return Intent::Strike {
                variant: StrikeVariant::Slash,
            };
        }
        return Intent::Grab;
    }

    // Mid range (1.0-2.0m): approach or circle, occasionally attack
    if distance < 2.0 {
        match opponent_history.len() % 4 {
            0 => Intent::move_standard(Approach),
            1 => Intent::move_standard(CircleClockwise),
            2 => {
                if opponent_burst > 70 {
                    Intent::Strike {
                        variant: StrikeVariant::Slash,
                    }
                } else {
                    Intent::move_standard(Approach)
                }
            }
            _ => Intent::Block,
        }
    } else {
        // Long range (> 2.0m): close distance
        match opponent_history.len() % 3 {
            0 | 1 => Intent::move_standard(Approach),
            _ => Intent::move_standard(LateralLeft),
        }
    }
}

fn lock_next_phase(
    phase: &mut PlanPhase,
    player: Intent,
    _opponent_phase: u64,
    auto_player: bool,
    opponent_history: &[Intent],
) {
    if phase.status() != PlanStatus::Planning {
        return;
    }
    // While clinched, only Clinch intents are feasible. A submitted Clinch
    // intent passes through (interactive clinch sub-menu); anything else is
    // coerced to Hold so the demo/smoke paths keep running deterministically.
    if phase.clinch().is_some() {
        let player_clinch = match player {
            Intent::Clinch { .. } => player,
            _ => Intent::Clinch {
                sub: just_dodge::intent::ClinchIntent::Hold,
            },
        };
        if auto_player {
            let _ = phase.submit_intent(Side::Player, player_clinch);
        }
        let _ = phase.submit_intent(
            Side::Opponent,
            Intent::Clinch {
                sub: just_dodge::intent::ClinchIntent::Hold,
            },
        );
        return;
    }
    let opponent = reactive_opponent(&phase.snapshot(), opponent_history);
    // Interactive mode: the game freezes at the player's actionability
    // boundary until the player locks (forecast/ghost preview is live during
    // the freeze). Scripted paths (shot/smoke) auto-lock the player.
    if auto_player {
        let _ = phase.submit_intent(Side::Player, player);
    }
    let _ = phase.submit_intent(Side::Opponent, opponent);
    if auto_player && phase.status() == PlanStatus::Planning {
        // A speculative Grab can be correctly re-prompted; the scripted loop
        // keeps running by deterministically selecting Idle rather than faking
        // a whiff or mutating authority state.
        let _ = phase.submit_intent(Side::Player, Intent::Idle);
        let _ = phase.submit_intent(Side::Opponent, Intent::Idle);
    }
}

fn run_smoke(ticks: u64) {
    let mut phase = PlanPhase::new();
    let mut player_phase = 0_u64;
    // F-021 dev lane: JUSTDODGE_MOTION=generative drives the async buffered
    // plan service with the MotionBricks generative provider. Presentation-
    // only: the truth hash must be identical with or without the flag.
    let generative = std::env::var("JUSTDODGE_MOTION").ok().as_deref() == Some("generative");
    let mut motion = generative.then(|| {
        let service = just_dodge::motion_service_async::MotionPlanService::new(
            just_dodge::motion_service_async::GenerativeMotionProvider::new(
                std::env::var("JUSTDODGE_ASSETS").unwrap_or_else(|_| "assets".to_string()),
            ),
        );
        let adapter = just_dodge::motion_service_async::PlanPhaseMotionAdapter::new(
            [glam::Mat4::IDENTITY; just_dodge::motion::G1_NB],
            [glam::Mat4::IDENTITY; just_dodge::motion::G1_NB],
        );
        (service, adapter)
    });
    let mut motion_submits = 0_u32;
    let mut motion_ready = 0_u32;
    let mut motion_rejected = 0_u32;
    for _ in 0..ticks {
        let was_planning = phase.status() == PlanStatus::Planning;
        lock_next_phase(
            &mut phase,
            match player_phase % 6 {
                0 => Intent::move_standard(MoveDirection::Approach),
                1 => Intent::move_standard(MoveDirection::LateralRight),
                2 => Intent::Block,
                3 => Intent::Strike {
                    variant: StrikeVariant::Slash,
                },
                4 => Intent::Dodge {
                    dir: MoveDirection::CircleCounterClockwise,
                },
                _ => Intent::Idle,
            },
            player_phase,
            true,
            &[],
        );
        if let Some((service, adapter)) = motion.as_mut() {
            // Submit only on a fresh lock (a Planning boundary that just
            // locked), not every tick.
            if was_planning {
                motion_submits += adapter
                    .submit_locked(&phase, service)
                    .map(|receipts| receipts.len() as u32)
                    .unwrap_or(0);
            }
            let _ = adapter.step_truth_tick(&mut phase, service);
            let sample = adapter.poll_presentation(service, phase.snapshot().truth_frame);
            for receipt in sample.receipts.into_iter().flatten() {
                let _ = receipt;
                motion_ready += 1;
            }
            motion_rejected += sample.rejected.iter().filter(|r| **r).count() as u32;
        } else {
            phase
                .step_truth_tick()
                .expect("smoke must always advance an M1 truth tick");
        }
        if phase.status() == PlanStatus::Planning {
            player_phase = player_phase.saturating_add(1);
        }
    }
    if let Some((service, adapter)) = motion.as_mut() {
        // Dev-lane measurement: drain up to 90s for inference completions
        // (first request carries model-load latency).
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(90);
        while std::time::Instant::now() < deadline {
            let sample = adapter.poll_presentation(service, phase.snapshot().truth_frame);
            motion_ready += sample.receipts.into_iter().flatten().count() as u32;
            motion_rejected += sample.rejected.iter().filter(|r| **r).count() as u32;
            if motion_ready + motion_rejected >= motion_submits {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
        adapter.cancel_all(service);
    }
    let snapshot = phase.snapshot();
    println!(
        "GAME_LOOP_SMOKE ticks={ticks} truth_frame={} truth_hash={:016x}",
        snapshot.truth_frame,
        phase.truth_hash()
    );
    if generative {
        println!(
            "GAME_LOOP_MOTION provider=GenerativeKeyframeInbetweening submits={motion_submits} ready={motion_ready} rejected={motion_rejected}"
        );
        // Dev-lane probe: in-flight MotionBricks Python worker threads crash
        // pyo3 teardown at exit; cancel is issued above and the OS reaps the
        // workers. Skipping destructors keeps the probe exit deterministic.
        std::process::exit(0);
    }
}

struct GameLoopApp {
    assets_root: String,
    window: Option<Arc<Window>>,
    surface: Option<wgpu::Surface<'static>>,
    device: Option<wgpu::Device>,
    queue: Option<wgpu::Queue>,
    config: Option<wgpu::SurfaceConfiguration>,
    renderer: Option<renderer::Renderer>,
    presentation: Option<PresentationAssets>,
    /// F-022 generative ship lane: live MotionBricks clips drive the skinned
    /// fighters when JUSTDODGE_MOTION=generative.
    motion: Option<(
        just_dodge::motion_service_async::MotionPlanService,
        just_dodge::motion_service_async::PlanPhaseMotionAdapter,
    )>,
    phase: PlanPhase,
    selected: Intent,
    opponent_phase: u64,
    next_truth: Instant,
    camera: CameraMode,
    observer_yaw: f32,
    show_skeleton: bool,
    show_dev: bool,
    show_ghosts: bool,
    show_hud: bool,
    whatif_index: usize,
    first_frame_presented: bool,
}

impl GameLoopApp {
    fn new(assets_root: String) -> Self {
        let motion = (std::env::var("JUSTDODGE_MOTION").ok().as_deref() == Some("generative"))
            .then(|| {
                let service = just_dodge::motion_service_async::MotionPlanService::new(
                    just_dodge::motion_service_async::GenerativeMotionProvider::new(
                        assets_root.clone(),
                    ),
                );
                let adapter = just_dodge::motion_service_async::PlanPhaseMotionAdapter::new(
                    [glam::Mat4::IDENTITY; just_dodge::motion::G1_NB],
                    [glam::Mat4::IDENTITY; just_dodge::motion::G1_NB],
                );
                (service, adapter)
            });
        Self {
            assets_root,
            window: None,
            surface: None,
            device: None,
            queue: None,
            config: None,
            renderer: None,
            presentation: None,
            motion,
            phase: PlanPhase::new(),
            selected: Intent::Idle,
            opponent_phase: 0,
            next_truth: Instant::now(),
            camera: CameraMode::FirstPerson,
            observer_yaw: 0.0,
            show_skeleton: true,
            show_dev: false,
            show_ghosts: true,
            show_hud: true,
            whatif_index: 0,
            first_frame_presented: false,
        }
    }

    /// Hypothetical opponent intent for the forecast/ghost preview, cycled
    /// with N/M (F-111 full-information tactics preview).
    fn whatif_intent(&self) -> Intent {
        const CYCLE: &[fn() -> Intent] = &[
            || Intent::Strike {
                variant: StrikeVariant::Slash,
            },
            || Intent::Strike {
                variant: StrikeVariant::Thrust,
            },
            || Intent::Block,
            || Intent::Grab,
            || Intent::Dodge {
                dir: MoveDirection::LateralLeft,
            },
            || Intent::move_standard(MoveDirection::Approach),
            || Intent::move_standard(MoveDirection::LateralLeft),
            || Intent::Feint,
            || Intent::Cancel,
            || Intent::Idle,
        ];
        CYCLE[self.whatif_index % CYCLE.len()]()
    }

    /// Forecast the current hypothetical lock (player selection vs what-if
    /// opponent) from the live planning boundary. None when not planning.
    fn current_forecast(&self) -> Option<ForecastOutcome> {
        if self.phase.status() != PlanStatus::Planning {
            return None;
        }
        forecast(&self.phase, self.selected, self.whatif_intent())
            .ok()
            .flatten()
    }

    fn advance_truth(&mut self) {
        let now = Instant::now();
        let mut stepped = 0_u8;
        while now >= self.next_truth && stepped < 4 {
            let was_planning = self.phase.status() == PlanStatus::Planning;
            lock_next_phase(
                &mut self.phase,
                self.selected,
                self.opponent_phase,
                false,
                &[],
            );
            // Interactive freeze: the player's selection is still open — wait
            // for a key-locked intent instead of stepping without both locks.
            if self.phase.status() == PlanStatus::Planning
                && self.phase.can_submit_intent(Side::Player)
            {
                self.next_truth = now + TRUTH_STEP;
                return;
            }
            if let Some((service, adapter)) = self.motion.as_mut() {
                if was_planning {
                    let _ = adapter.submit_locked(&self.phase, service);
                }
                let _ = adapter.step_truth_tick(&mut self.phase, service);
                let _ = adapter.poll_presentation(service, self.phase.snapshot().truth_frame);
            } else {
                self.phase
                    .step_truth_tick()
                    .expect("window loop must only step locked PlanPhase truth");
            }
            if self.phase.status() == PlanStatus::Planning {
                self.opponent_phase = self.opponent_phase.saturating_add(1);
            }
            self.next_truth += TRUTH_STEP;
            stepped = stepped.saturating_add(1);
        }
        if stepped == 4 && now >= self.next_truth {
            self.next_truth = now + TRUTH_STEP;
        }
    }

    fn set_intent(&mut self, intent: Intent) {
        self.selected = intent;
        // During the planning freeze a key-press IS the lock (design receipt:
        // lock-intent-button). Submit immediately so the freeze ends.
        if self.phase.status() == PlanStatus::Planning && self.phase.can_submit_intent(Side::Player)
        {
            let _ = self.phase.submit_intent(Side::Player, intent);
        }
    }

    fn handle_key(&mut self, event_loop: &ActiveEventLoop, event: &winit::event::KeyEvent) {
        if event.state != ElementState::Pressed || event.repeat {
            return;
        }
        match event.physical_key {
            PhysicalKey::Code(KeyCode::Escape) => event_loop.exit(),
            PhysicalKey::Code(KeyCode::KeyC) => self.camera = self.camera.toggled(),
            PhysicalKey::Code(KeyCode::KeyB) => self.show_skeleton = !self.show_skeleton,
            PhysicalKey::Code(KeyCode::F3) => self.show_dev = !self.show_dev,
            PhysicalKey::Code(KeyCode::Tab) => self.show_ghosts = !self.show_ghosts,
            PhysicalKey::Code(KeyCode::KeyH) => self.show_hud = !self.show_hud,
            PhysicalKey::Code(KeyCode::KeyZ) => {
                // F-003 stance cycling (costs tempo between exchanges).
                let next = match self.phase.snapshot().stances[0] {
                    just_dodge::intent::Stance::Neutral => just_dodge::intent::Stance::High,
                    just_dodge::intent::Stance::High => just_dodge::intent::Stance::Low,
                    just_dodge::intent::Stance::Low => just_dodge::intent::Stance::Neutral,
                };
                let _ = self.phase.set_stance(Side::Player, next);
            }
            PhysicalKey::Code(KeyCode::KeyN) => {
                self.whatif_index = self.whatif_index.saturating_add(1);
            }
            PhysicalKey::Code(KeyCode::KeyM) => {
                self.whatif_index = self.whatif_index.saturating_sub(1);
            }
            PhysicalKey::Code(KeyCode::KeyJ) => self.observer_yaw -= 0.12,
            PhysicalKey::Code(KeyCode::KeyL) => self.observer_yaw += 0.12,
            PhysicalKey::Code(KeyCode::KeyW) => {
                self.set_intent(Intent::move_standard(MoveDirection::Approach))
            }
            PhysicalKey::Code(KeyCode::KeyS) => {
                self.set_intent(Intent::move_standard(MoveDirection::Retreat))
            }
            PhysicalKey::Code(KeyCode::KeyA) => {
                self.set_intent(Intent::move_standard(MoveDirection::LateralLeft))
            }
            PhysicalKey::Code(KeyCode::KeyD) => {
                self.set_intent(Intent::move_standard(MoveDirection::LateralRight))
            }
            PhysicalKey::Code(KeyCode::KeyQ) => {
                self.set_intent(Intent::move_standard(MoveDirection::CircleCounterClockwise))
            }
            PhysicalKey::Code(KeyCode::KeyE) => {
                self.set_intent(Intent::move_standard(MoveDirection::CircleClockwise))
            }
            PhysicalKey::Code(KeyCode::Digit1) => self.set_intent(Intent::Strike {
                variant: StrikeVariant::Slash,
            }),
            PhysicalKey::Code(KeyCode::Digit2) => self.set_intent(Intent::Block),
            PhysicalKey::Code(KeyCode::Digit3) => self.set_intent(Intent::Grab),
            PhysicalKey::Code(KeyCode::Digit4) => self.set_intent(Intent::Dodge {
                dir: MoveDirection::LateralLeft,
            }),
            PhysicalKey::Code(KeyCode::Digit5) => self.set_intent(Intent::Feint),
            PhysicalKey::Code(KeyCode::Digit6) => self.set_intent(Intent::Cancel),
            PhysicalKey::Code(KeyCode::Digit0) => self.set_intent(Intent::Idle),
            PhysicalKey::Code(KeyCode::Space) => self.set_intent(self.selected),
            _ => {}
        }
    }

    fn update_title(&self, snapshot: &PlanSnapshot, forecast_outcome: Option<&ForecastOutcome>) {
        let Some(window) = self.window.as_ref() else {
            return;
        };
        let forecast_text = forecast_outcome.map_or_else(
            || "forecast: busy".to_string(),
            |outcome| {
                format!(
                    "what-if {:?} → {:?} in {}f",
                    self.whatif_intent(),
                    predicted_outcome(outcome),
                    outcome.ticks
                )
            },
        );
        let title = if self.show_dev {
            format!(
                "Just Dodge M2 | DEV frame={} dist={:.2}m hash={:016x} contact={} OBB=ON | {}",
                snapshot.truth_frame,
                planar_distance_m(snapshot),
                self.phase.truth_hash(),
                snapshot.last_contact_observed,
                forecast_text,
            )
        } else {
            format!(
                "Just Dodge M2 | {} | spacing {:.2}m | {} | C camera B skeleton Tab ghosts N/M what-if F3 dev",
                self.camera.label(),
                planar_distance_m(snapshot),
                forecast_text,
            )
        };
        window.set_title(&title);
    }

    fn render_frame(&mut self) {
        self.advance_truth();
        let snapshot = self.phase.snapshot();
        let forecast_outcome = if self.show_ghosts {
            self.current_forecast()
        } else {
            None
        };
        self.update_title(&snapshot, forecast_outcome.as_ref());
        let (Some(surface), Some(device), Some(queue), Some(config)) = (
            self.surface.as_ref(),
            self.device.as_ref(),
            self.queue.as_ref(),
            self.config.as_ref(),
        ) else {
            return;
        };
        let surface_texture = match surface.get_current_texture() {
            wgpu::CurrentSurfaceTexture::Success(texture)
            | wgpu::CurrentSurfaceTexture::Suboptimal(texture) => texture,
            wgpu::CurrentSurfaceTexture::Occluded | wgpu::CurrentSurfaceTexture::Timeout => return,
            wgpu::CurrentSurfaceTexture::Outdated | wgpu::CurrentSurfaceTexture::Lost => {
                surface.configure(device, config);
                return;
            }
            wgpu::CurrentSurfaceTexture::Validation => return,
        };
        let view = surface_texture
            .texture
            .create_view(&wgpu::TextureViewDescriptor::default());
        let (Some(renderer), Some(presentation)) =
            (self.renderer.as_mut(), self.presentation.as_ref())
        else {
            let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("M2 initial map encoder"),
            });
            {
                let _clear = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                    label: Some("M2 initial map pass"),
                    color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                        view: &view,
                        resolve_target: None,
                        depth_slice: None,
                        ops: wgpu::Operations {
                            load: wgpu::LoadOp::Clear(wgpu::Color {
                                r: 0.025,
                                g: 0.035,
                                b: 0.055,
                                a: 1.0,
                            }),
                            store: wgpu::StoreOp::Store,
                        },
                    })],
                    depth_stencil_attachment: None,
                    timestamp_writes: None,
                    occlusion_query_set: None,
                    multiview_mask: None,
                });
            }
            queue.submit(std::iter::once(encoder.finish()));
            queue.present(surface_texture);
            self.first_frame_presented = true;
            return;
        };
        let player_root = root_vec(&snapshot, Side::Player);
        let opponent_root = root_vec(&snapshot, Side::Opponent);
        let aspect = config.width as f32 / config.height as f32;
        let proj_view = camera_proj_view(
            self.camera,
            self.observer_yaw,
            aspect,
            player_root,
            opponent_root,
        );
        let player_model = fighter_model(player_root, opponent_root);
        let opponent_model = fighter_model(opponent_root, player_root);
        let player_skin = if let Some((_, adapter)) = self.motion.as_ref() {
            asset::compute_skin_matrices(
                &adapter.playback_pose(Side::Player, snapshot.truth_frame),
                &presentation.mesh,
            )
            .to_vec()
        } else {
            presentation.skin_for(
                snapshot.locked[0],
                snapshot.truth_frame,
                snapshot.action_ticks[0],
            )
        };
        let opponent_skin = if let Some((_, adapter)) = self.motion.as_ref() {
            asset::compute_skin_matrices(
                &adapter.playback_pose(Side::Opponent, snapshot.truth_frame),
                &presentation.mesh,
            )
            .to_vec()
        } else {
            presentation.skin_for(
                snapshot.locked[1],
                snapshot.truth_frame,
                snapshot.action_ticks[1],
            )
        };
        renderer.update_camera(queue, &proj_view);
        renderer.upload_debug_mvp(queue, &proj_view);
        renderer.update_contact_shadows(queue, &proj_view, player_root, opponent_root);
        renderer.update_skinned_model(queue, 0, &proj_view, player_model);
        renderer.update_skinned_model(queue, 1, &proj_view, opponent_model);
        renderer.update_skin_joints_indexed(queue, 0, &player_skin);
        renderer.update_skin_joints_indexed(queue, 1, &opponent_skin);
        let mut marker_segments = arena_marker_segments();
        if self.show_skeleton {
            marker_segments.extend(skeleton_segments(
                &presentation.mesh,
                &player_skin,
                player_model,
                [0.25, 0.95, 1.0],
            ));
            marker_segments.extend(skeleton_segments(
                &presentation.mesh,
                &opponent_skin,
                opponent_model,
                [1.0, 0.35, 0.45],
            ));
        }
        // F-111 what-if ghosts: forecast root trails + end-of-window ghost
        // skeletons for both fighters (presentation-only, never feeds truth).
        if let Some(outcome) = &forecast_outcome {
            marker_segments.extend(ghost_segments(&presentation.mesh, presentation, outcome));
        }
        renderer.update_debug_segments(device, &marker_segments);
        let obb_lines = if self.show_dev {
            let mut lines = obb_proxy_lines(player_root);
            lines.extend(obb_proxy_lines(opponent_root));
            lines
        } else {
            Vec::new()
        };
        renderer.update_hitbox_debug(device, &obb_lines);
        // F-110/F-112 stroke-font HUD (design receipt canvas-c602d5588727 r4).
        let hud_segments = if self.show_hud {
            let availability: Vec<bool> = hud::SELECTABLE
                .iter()
                .map(|intent| self.phase.intent_available(Side::Player, *intent))
                .collect();
            let opp_availability: Vec<bool> = hud::SELECTABLE
                .iter()
                .map(|intent| self.phase.intent_available(Side::Opponent, *intent))
                .collect();
            hud::build_hud(
                &snapshot,
                forecast_outcome.as_ref(),
                &availability,
                &opp_availability,
                aspect,
            )
        } else {
            Vec::new()
        };
        renderer.update_hud_segments(device, &hud_segments);
        let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
            label: Some("M2 game loop encoder"),
        });
        {
            let mut rpass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("M2 debug mannequin pass"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &view,
                    resolve_target: None,
                    depth_slice: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color {
                            r: 0.025,
                            g: 0.035,
                            b: 0.055,
                            a: 1.0,
                        }),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: Some(wgpu::RenderPassDepthStencilAttachment {
                    view: &renderer.depth_view,
                    depth_ops: Some(wgpu::Operations {
                        load: wgpu::LoadOp::Clear(1.0),
                        store: wgpu::StoreOp::Store,
                    }),
                    stencil_ops: None,
                }),
                timestamp_writes: None,
                occlusion_query_set: None,
                multiview_mask: None,
            });
            renderer.render(&mut rpass);
            if self.camera == CameraMode::FirstPerson {
                renderer.render_skinned_from(&mut rpass, 1);
            } else {
                renderer.render_skinned_from(&mut rpass, 0);
            }
            renderer.render_debug_overlay(&mut rpass);
            if self.show_dev {
                renderer.render_hitbox_debug(&mut rpass);
            }
            renderer.render_hud_overlay(queue, &mut rpass);
        }
        queue.submit(std::iter::once(encoder.finish()));
        queue.present(surface_texture);
    }
}

impl ApplicationHandler for GameLoopApp {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        let window = Arc::new(
            event_loop
                .create_window(
                    Window::default_attributes()
                        .with_title("Just Dodge M2 — loading debug mannequins")
                        .with_inner_size(LogicalSize::new(1280.0, 720.0)),
                )
                .expect("create M2 window"),
        );
        let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
            backends: wgpu::Backends::VULKAN,
            flags: wgpu::InstanceFlags::default(),
            memory_budget_thresholds: wgpu::MemoryBudgetThresholds::default(),
            backend_options: wgpu::BackendOptions::default(),
            display: None,
        });
        let surface = instance
            .create_surface(Arc::clone(&window))
            .expect("create M2 surface");
        let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            compatible_surface: Some(&surface),
            ..Default::default()
        }))
        .expect("M2 needs a compatible GPU adapter");
        let (device, queue) =
            pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor::default()))
                .expect("M2 request wgpu device");
        let size = window.inner_size();
        let config = wgpu::SurfaceConfiguration {
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
            format: surface.get_capabilities(&adapter).formats[0],
            width: size.width.max(1),
            height: size.height.max(1),
            present_mode: wgpu::PresentMode::Fifo,
            alpha_mode: wgpu::CompositeAlphaMode::Auto,
            view_formats: vec![],
            color_space: wgpu::SurfaceColorSpace::Auto,
            desired_maximum_frame_latency: 2,
        };
        surface.configure(&device, &config);
        self.window = Some(window);
        self.surface = Some(surface);
        self.device = Some(device);
        self.queue = Some(queue);
        self.config = Some(config);
        self.window.as_ref().expect("window set").request_redraw();
    }

    fn about_to_wait(&mut self, _event_loop: &ActiveEventLoop) {
        if self.first_frame_presented && self.renderer.is_none() {
            let (Some(device), Some(queue), Some(config)) = (
                self.device.as_ref(),
                self.queue.as_ref(),
                self.config.as_ref(),
            ) else {
                return;
            };
            let mannequin_path = format!("{}/{MANNEQUIN_SKIN}", self.assets_root);
            // This process is single-threaded at renderer construction. The
            // renderer reads these legacy configuration variables only in `new`.
            unsafe {
                std::env::set_var("JUST_DODGE_C0_SKIN", mannequin_path);
                std::env::set_var("JUST_DODGE_C0_FLAT_COLOR", "1");
            }
            self.presentation = Some(PresentationAssets::load(&self.assets_root));
            self.renderer = Some(renderer::Renderer::new(
                device,
                queue,
                config,
                renderer::SceneProfile::FlatArena,
                std::path::Path::new(&self.assets_root),
            ));
        }
        if let Some(window) = self.window.as_ref() {
            window.request_redraw();
        }
    }

    fn window_event(
        &mut self,
        event_loop: &ActiveEventLoop,
        _window_id: WindowId,
        event: WindowEvent,
    ) {
        match event {
            WindowEvent::CloseRequested => event_loop.exit(),
            WindowEvent::Resized(size) => {
                if let (Some(surface), Some(device), Some(config)) = (
                    self.surface.as_ref(),
                    self.device.as_ref(),
                    self.config.as_mut(),
                ) {
                    config.width = size.width.max(1);
                    config.height = size.height.max(1);
                    surface.configure(device, config);
                    if let Some(renderer) = self.renderer.as_mut() {
                        renderer.resize(device, config);
                    }
                }
            }
            WindowEvent::KeyboardInput { event, .. } => self.handle_key(event_loop, &event),
            WindowEvent::RedrawRequested => self.render_frame(),
            _ => {}
        }
    }
}

fn fighter_model(root: Vec3, opponent: Vec3) -> Mat4 {
    let facing = (opponent - root).xz().normalize_or_zero();
    let yaw = facing.x.atan2(facing.y);
    Mat4::from_translation(root) * Mat4::from_rotation_y(yaw) * renderer::skinned_correct_model()
}

fn camera_proj_view(
    mode: CameraMode,
    observer_yaw: f32,
    aspect: f32,
    player: Vec3,
    opponent: Vec3,
) -> Mat4 {
    let (eye, target) = match mode {
        CameraMode::FirstPerson => (player + Vec3::Y * 1.62, opponent + Vec3::Y * 1.25),
        CameraMode::Observer => {
            let midpoint = (player + opponent) * 0.5 + Vec3::Y * 0.8;
            let orbit = vec3(observer_yaw.sin() * 5.4, 3.2, observer_yaw.cos() * 5.4);
            (midpoint + orbit, midpoint + Vec3::Y * 0.25)
        }
    };
    Mat4::perspective_lh(62.0_f32.to_radians(), aspect, 0.1, 100.0)
        * Mat4::look_at_lh(eye, target, Vec3::Y)
}

fn root_pos_vec(root: just_dodge::intent::RootPosition) -> Vec3 {
    vec3(
        root.x_mm as f32 / 1000.0,
        root.y_mm as f32 / 1000.0,
        root.z_mm as f32 / 1000.0,
    )
}

/// F-111 what-if ghost segments: per-side forecast root trails plus a ghost
/// skeleton at each fighter's end-of-window root. Dim cyan/red distinguishes
/// ghosts from the live skeletons (bright cyan/red).
fn ghost_segments(
    mesh: &SkinnedMeshData,
    presentation: &PresentationAssets,
    outcome: &ForecastOutcome,
) -> Vec<(Vec3, Vec3, [f32; 3])> {
    const GHOST_COLORS: [[f32; 3]; 2] = [[0.12, 0.55, 0.65], [0.65, 0.18, 0.22]];
    let mut segments = Vec::new();
    for (side, color) in GHOST_COLORS.iter().enumerate() {
        for pair in outcome.root_track[side].windows(2) {
            let lift = vec3(0.0, 0.02, 0.0);
            segments.push((
                root_pos_vec(pair[0]) + lift,
                root_pos_vec(pair[1]) + lift,
                *color,
            ));
        }
    }
    let ends = [
        outcome.root_track[0].last().copied(),
        outcome.root_track[1].last().copied(),
    ];
    if let (Some(player_end), Some(opponent_end)) = (ends[0], ends[1]) {
        let roots = [root_pos_vec(player_end), root_pos_vec(opponent_end)];
        for side in 0..2 {
            let model = fighter_model(roots[side], roots[1 - side]);
            let skin = presentation.skin_for(
                outcome.locked[side],
                outcome.end_snapshot.truth_frame,
                outcome.end_snapshot.action_ticks[side],
            );
            segments.extend(skeleton_segments(mesh, &skin, model, GHOST_COLORS[side]));
        }
    }
    segments
}

fn skeleton_segments(
    mesh: &SkinnedMeshData,
    skin: &[Mat4],
    model: Mat4,
    color: [f32; 3],
) -> Vec<(Vec3, Vec3, [f32; 3])> {
    mesh.bones
        .iter()
        .enumerate()
        .filter(|(_, bone)| bone.parent >= 0)
        .map(|(index, bone)| {
            let child = (model * skin[index] * bone.inverse_bind.inverse())
                .w_axis
                .truncate();
            let parent_index = bone.parent as usize;
            let parent =
                (model * skin[parent_index] * mesh.bones[parent_index].inverse_bind.inverse())
                    .w_axis
                    .truncate();
            (parent, child, color)
        })
        .collect()
}

fn arena_marker_segments() -> Vec<(Vec3, Vec3, [f32; 3])> {
    let mut lines = Vec::new();
    let color = [0.14, 0.30, 0.40];
    for meter in -6..=6 {
        let m = meter as f32;
        lines.push((vec3(m, 0.005, -6.0), vec3(m, 0.005, 6.0), color));
        lines.push((vec3(-6.0, 0.005, m), vec3(6.0, 0.005, m), color));
    }
    lines.push((
        vec3(-6.0, 0.012, 0.0),
        vec3(6.0, 0.012, 0.0),
        [0.25, 0.75, 0.95],
    ));
    lines.push((
        vec3(0.0, 0.012, -6.0),
        vec3(0.0, 0.012, 6.0),
        [0.25, 0.75, 0.95],
    ));
    lines
}

fn obb_proxy_lines(root: Vec3) -> Vec<(Vec3, Vec3)> {
    let center = root + Vec3::Y * 0.95;
    let half = vec3(0.34, 0.95, 0.24);
    let corners = [
        center + vec3(-half.x, -half.y, -half.z),
        center + vec3(half.x, -half.y, -half.z),
        center + vec3(half.x, -half.y, half.z),
        center + vec3(-half.x, -half.y, half.z),
        center + vec3(-half.x, half.y, -half.z),
        center + vec3(half.x, half.y, -half.z),
        center + vec3(half.x, half.y, half.z),
        center + vec3(-half.x, half.y, half.z),
    ];
    const EDGES: [(usize, usize); 12] = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    ];
    EDGES
        .into_iter()
        .map(|(left, right)| (corners[left], corners[right]))
        .collect()
}

fn smoke_ticks_from_args() -> Option<u64> {
    let args: Vec<String> = std::env::args().collect();
    args.windows(2)
        .find(|pair| pair[0] == "--smoke")
        .map(|pair| {
            pair[1]
                .parse::<u64>()
                .expect("--smoke requires a non-negative integer")
        })
}

/// Headless offscreen visual check: render the two debug mannequins (observer +
/// first-person, skeleton overlay) into a COPY_SRC texture and save PNGs. This
/// is the reliable visual QA path on a compositor that blocks window capture.
/// Usage: `--shot TICKS OUT_DIR`.
fn shot_args() -> Option<(u64, String)> {
    let args: Vec<String> = std::env::args().collect();
    let pos = args.iter().position(|arg| arg == "--shot")?;
    let ticks = args
        .get(pos + 1)
        .and_then(|value| value.parse::<u64>().ok())
        .expect("--shot requires a tick count");
    let out_dir = args
        .get(pos + 2)
        .cloned()
        .unwrap_or_else(|| "qa_runs/game_loop_shot".to_owned());
    Some((ticks, out_dir))
}

fn match_requested() -> bool {
    std::env::args().any(|arg| arg == "--match")
}

fn pose_fingerprint(skin: &[Mat4]) -> u64 {
    let mut hash = 0xcbf2_9ce4_8422_2325_u64;
    for matrix in skin {
        for value in matrix.to_cols_array() {
            hash ^= u64::from(value.to_bits());
            hash = hash.wrapping_mul(0x1000_0000_01b3);
        }
    }
    hash
}

fn run_match() {
    let assets_root = std::env::var("JUSTDODGE_ASSETS").unwrap_or_else(|_| "assets".to_owned());
    let mannequin_path = format!("{assets_root}/{MANNEQUIN_SKIN}");
    unsafe {
        std::env::set_var("JUSTDODGE_C0_SKIN", mannequin_path);
        std::env::set_var("JUSTDODGE_C0_FLAT_COLOR", "1");
    }
    let presentation = PresentationAssets::load(&assets_root);
    let mut phase = PlanPhase::new();
    let mut match_loop = MatchLoop::new();
    let mut stage_seen = [false; 5];
    let mut clip_seen = [[false; 4]; 2];
    let mut pose_changes = [0_u32; 2];
    let mut last_pose = [None; 2];

    for _ in 0..4096 {
        let stage = match_loop.stage();
        stage_seen[match stage {
            MatchStage::Boot => 0,
            MatchStage::MatchSetup => 1,
            MatchStage::Countdown => 2,
            MatchStage::Fight => 3,
            MatchStage::Result => 4,
        }] = true;
        let snapshot = phase.snapshot();
        let intents = match_loop.presentation_intents(&snapshot);
        let animation_ticks = match_loop.animation_ticks(&snapshot);
        for side in 0..2 {
            let skin = presentation.skin_for(
                intents[side],
                animation_ticks[side],
                snapshot.action_ticks[side],
            );
            let pose = pose_fingerprint(&skin);
            if last_pose[side].is_some_and(|previous| previous != pose) {
                pose_changes[side] = pose_changes[side].saturating_add(1);
            }
            last_pose[side] = Some(pose);
            let clip_index = match animation_for_intent(intents[side]) {
                AnimationClip::Reference => 0,
                AnimationClip::Walk => 1,
                AnimationClip::Run => 2,
                AnimationClip::HeroStrike => 3,
            };
            clip_seen[side][clip_index] = true;
        }
        match_loop.step(&mut phase);
        if match_loop.stage() == MatchStage::Result && match_loop.stage_tick >= 2 {
            break;
        }
    }

    assert!(
        stage_seen.into_iter().all(|seen| seen),
        "match must visit every stage"
    );
    assert!(
        clip_seen
            .iter()
            .all(|clips| clips[1] && clips[2] && clips[3]),
        "both fighters must select walk, run, and hero_strike clips"
    );
    assert!(
        pose_changes.into_iter().all(|changes| changes > 0),
        "both fighters must change rendered poses across match ticks"
    );
    assert_eq!(match_loop.stage(), MatchStage::Result);
    println!(
        "GAME_LOOP_MATCH stages=Boot>MatchSetup>Countdown>Fight>Result truth_frame={} exchanges={} p1_pose_changes={} p2_pose_changes={} clips=walk,run,hero_strike",
        phase.snapshot().truth_frame,
        match_loop.exchanges_started,
        pose_changes[0],
        pose_changes[1],
    );
}

fn run_shot(ticks: u64, out_dir: &str) {
    // Drive the truth loop forward so the shot captures a mid-exchange pose.
    // Shot mode defaults to a Move intent so the walk clip is exercised by the
    // presentation path instead of only rendering a static action placeholder.
    let mut phase = PlanPhase::new();
    let mut player_phase = 0_u64;
    for _ in 0..ticks {
        lock_next_phase(
            &mut phase,
            Intent::move_standard(MoveDirection::Approach),
            player_phase,
            true,
            &[],
        );
        phase
            .step_truth_tick()
            .expect("shot must advance an M1 truth tick");
        if phase.status() == PlanStatus::Planning {
            player_phase = player_phase.saturating_add(1);
        }
    }
    // Capture at a planning boundary so the what-if ghost forecast is live.
    while phase.status() != PlanStatus::Planning {
        phase
            .step_truth_tick()
            .expect("shot must reach a planning boundary");
    }
    let snapshot = phase.snapshot();

    let assets_root = std::env::var("JUSTDODGE_ASSETS").unwrap_or_else(|_| "assets".to_owned());
    let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
        backends: wgpu::Backends::VULKAN,
        flags: wgpu::InstanceFlags::default(),
        memory_budget_thresholds: wgpu::MemoryBudgetThresholds::default(),
        backend_options: wgpu::BackendOptions::default(),
        display: None,
    });
    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
        compatible_surface: None,
        ..Default::default()
    }))
    .expect("shot needs a GPU adapter");
    let (device, queue) =
        pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor::default()))
            .expect("shot request device");

    let (w, h) = (1280_u32, 720_u32);
    let format = wgpu::TextureFormat::Bgra8UnormSrgb;
    let config = wgpu::SurfaceConfiguration {
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
        format,
        width: w,
        height: h,
        present_mode: wgpu::PresentMode::Fifo,
        alpha_mode: wgpu::CompositeAlphaMode::Auto,
        view_formats: vec![],
        color_space: wgpu::SurfaceColorSpace::Auto,
        desired_maximum_frame_latency: 2,
    };
    let mannequin_path = format!("{assets_root}/{MANNEQUIN_SKIN}");
    unsafe {
        std::env::set_var("JUST_DODGE_C0_SKIN", mannequin_path);
        std::env::set_var("JUST_DODGE_C0_FLAT_COLOR", "1");
    }
    let presentation = PresentationAssets::load(&assets_root);
    let mut renderer = renderer::Renderer::new(
        &device,
        &queue,
        &config,
        renderer::SceneProfile::FlatArena,
        std::path::Path::new(&assets_root),
    );

    let color_tex = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("shot color"),
        size: wgpu::Extent3d {
            width: w,
            height: h,
            depth_or_array_layers: 1,
        },
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format,
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::COPY_SRC,
        view_formats: &[],
    });
    let color_view = color_tex.create_view(&wgpu::TextureViewDescriptor::default());

    std::fs::create_dir_all(out_dir).expect("create shot out dir");
    let player_root = root_vec(&snapshot, Side::Player);
    let opponent_root = root_vec(&snapshot, Side::Opponent);
    let player_model = fighter_model(player_root, opponent_root);
    let opponent_model = fighter_model(opponent_root, player_root);
    // The truth loop is advanced to the planning boundary for the forecast, so
    // its final truth frame is the same for short and long shot requests. Keep
    // the requested tick as the presentation clock so --shot 1 and --shot 5
    // sample different walk/run frames.
    let player_skin = presentation.skin_for(snapshot.locked[0], ticks, snapshot.action_ticks[0]);
    let opponent_skin = presentation.skin_for(snapshot.locked[1], ticks, snapshot.action_ticks[1]);
    let aspect = w as f32 / h as f32;

    // F-111/F-112: forecast + HUD for the frozen boundary capture.
    let shot_forecast = forecast(
        &phase,
        Intent::Strike {
            variant: StrikeVariant::Slash,
        },
        reactive_opponent(&phase.snapshot(), &[]),
    )
    .ok()
    .flatten();
    let availability: Vec<bool> = hud::SELECTABLE
        .iter()
        .map(|intent| phase.intent_available(Side::Player, *intent))
        .collect();
    let opp_availability: Vec<bool> = hud::SELECTABLE
        .iter()
        .map(|intent| phase.intent_available(Side::Opponent, *intent))
        .collect();
    let hud_segments = hud::build_hud(
        &snapshot,
        shot_forecast.as_ref(),
        &availability,
        &opp_availability,
        aspect,
    );

    for (name, mode, render_index) in [
        ("observer", CameraMode::Observer, 0_usize),
        ("first_person", CameraMode::FirstPerson, 1_usize),
    ] {
        let proj_view = camera_proj_view(mode, 0.9, aspect, player_root, opponent_root);
        renderer.update_camera(&queue, &proj_view);
        renderer.upload_debug_mvp(&queue, &proj_view);
        renderer.update_contact_shadows(&queue, &proj_view, player_root, opponent_root);
        renderer.update_skinned_model(&queue, 0, &proj_view, player_model);
        renderer.update_skinned_model(&queue, 1, &proj_view, opponent_model);
        renderer.update_skin_joints_indexed(&queue, 0, &player_skin);
        renderer.update_skin_joints_indexed(&queue, 1, &opponent_skin);
        let mut marker_segments = arena_marker_segments();
        marker_segments.extend(skeleton_segments(
            &presentation.mesh,
            &player_skin,
            player_model,
            [0.25, 0.95, 1.0],
        ));
        marker_segments.extend(skeleton_segments(
            &presentation.mesh,
            &opponent_skin,
            opponent_model,
            [1.0, 0.35, 0.45],
        ));
        // F-111 ghosts in shot captures when the loop froze at a boundary.
        if let Some(outcome) = &shot_forecast {
            marker_segments.extend(ghost_segments(&presentation.mesh, &presentation, outcome));
        }
        renderer.update_debug_segments(&device, &marker_segments);
        renderer.update_hud_segments(&device, &hud_segments);

        let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
            label: Some("shot encoder"),
        });
        {
            let mut rpass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("shot pass"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &color_view,
                    resolve_target: None,
                    depth_slice: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color {
                            r: 0.025,
                            g: 0.035,
                            b: 0.055,
                            a: 1.0,
                        }),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: Some(wgpu::RenderPassDepthStencilAttachment {
                    view: &renderer.depth_view,
                    depth_ops: Some(wgpu::Operations {
                        load: wgpu::LoadOp::Clear(1.0),
                        store: wgpu::StoreOp::Store,
                    }),
                    stencil_ops: None,
                }),
                timestamp_writes: None,
                occlusion_query_set: None,
                multiview_mask: None,
            });
            renderer.render(&mut rpass);
            renderer.render_skinned_from(&mut rpass, render_index);
            renderer.render_debug_overlay(&mut rpass);
            renderer.render_hud_overlay(&queue, &mut rpass);
        }
        queue.submit(std::iter::once(encoder.finish()));

        let bytes_per_row = (w * 4).next_multiple_of(256);
        let read_buf = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("shot readback"),
            size: (bytes_per_row * h) as u64,
            usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
            mapped_at_creation: false,
        });
        let mut copy = device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
        copy.copy_texture_to_buffer(
            wgpu::TexelCopyTextureInfo {
                texture: &color_tex,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            wgpu::TexelCopyBufferInfo {
                buffer: &read_buf,
                layout: wgpu::TexelCopyBufferLayout {
                    offset: 0,
                    bytes_per_row: Some(bytes_per_row),
                    rows_per_image: Some(h),
                },
            },
            wgpu::Extent3d {
                width: w,
                height: h,
                depth_or_array_layers: 1,
            },
        );
        queue.submit(std::iter::once(copy.finish()));
        let slice = read_buf.slice(..);
        slice.map_async(wgpu::MapMode::Read, |_| {});
        device.poll(wgpu::PollType::wait_indefinitely()).unwrap();
        let data = slice.get_mapped_range().unwrap();
        let mut img = image::ImageBuffer::<image::Rgba<u8>, Vec<u8>>::new(w, h);
        for y in 0..h {
            for x in 0..w {
                let src = (y * bytes_per_row + x * 4) as usize;
                img.put_pixel(
                    x,
                    y,
                    image::Rgba([data[src], data[src + 1], data[src + 2], data[src + 3]]),
                );
            }
        }
        drop(data);
        read_buf.unmap();
        let path = format!("{out_dir}/game_loop_{name}.png");
        img.save(&path).expect("save shot png");
        println!("shot: wrote {path}");
    }
    println!(
        "GAME_LOOP_SHOT ticks={ticks} truth_frame={} truth_hash={:016x}",
        snapshot.truth_frame,
        phase.truth_hash()
    );
}

fn main() {
    if match_requested() {
        run_match();
        return;
    }
    if let Some(ticks) = smoke_ticks_from_args() {
        run_smoke(ticks);
        return;
    }
    if let Some((ticks, out_dir)) = shot_args() {
        run_shot(ticks, &out_dir);
        return;
    }
    env_logger::init();
    let assets = std::env::var("JUSTDODGE_ASSETS").unwrap_or_else(|_| "assets".to_owned());
    let event_loop = EventLoop::new().expect("create event loop");
    let mut app = GameLoopApp::new(assets);
    event_loop.run_app(&mut app).expect("run M2 game loop");
}
