#![allow(dead_code)]

use glam::{Mat4, Vec3, vec3};
use just_dodge::{milestone3 as m3, runtime_flow};
use std::path::PathBuf;
use std::process::Command;
use std::sync::Arc;
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use winit::application::ApplicationHandler;
use winit::dpi::LogicalSize;
use winit::event::{ElementState, WindowEvent};
use winit::event_loop::{ActiveEventLoop, EventLoop};
use winit::window::{CursorGrabMode, Window, WindowId};

mod action_matrix;
mod active_ragdoll;
mod ai;
mod armor;
mod asset;

mod cleanbox;
mod combat;
mod dodge_presentation;
mod duel_physics;
mod duel_world;
mod g1_articulation;
mod g1_hinge_adapter;
mod hero_strike;
mod hinge_projection;
mod hitbox;
mod injury;
mod input;
mod m3_cleanbox;
mod milestone3 {
    pub use just_dodge::milestone3::*;
}
mod motion;
mod motion_frontier_lab;
mod motion_plan;
mod motion_retarget;
#[cfg(feature = "motion-inference")]
mod motion_service;
mod neural_plan;
mod renderer;
mod replay;
mod retarget;
mod skeleton;
mod telemetry;
mod truth;
mod ui;

const TRUTH_TICKS_PER_SECOND: u128 = 60;
const TICK_CREDIT_PER_SECOND: u128 = 1_000_000_000;
const MAX_CATCH_UP_TICKS: u32 = 8;

/// Converts elapsed wall time into exact 60 Hz simulation ticks without
/// rounding each redraw independently. Fractional tick credit is retained.
#[derive(Debug, Default)]
struct FixedStepClock {
    tick_credit: u128,
}

impl FixedStepClock {
    fn push_elapsed(&mut self, elapsed: Duration) -> u32 {
        let added = elapsed.as_nanos().saturating_mul(TRUTH_TICKS_PER_SECOND);
        self.tick_credit = self.tick_credit.saturating_add(added);

        let available = self.tick_credit / TICK_CREDIT_PER_SECOND;
        let ticks = available.min(MAX_CATCH_UP_TICKS as u128) as u32;
        self.tick_credit -= u128::from(ticks) * TICK_CREDIT_PER_SECOND;
        ticks
    }
}

const FIRST_PERSON_EYE_HEIGHT: f32 = 1.62;
const FIRST_PERSON_FOV_Y_RAD: f32 = 70.0_f32.to_radians();
const FIRST_PERSON_MOUSE_SENSITIVITY: f32 = 0.005;
const FIRST_PERSON_MAX_PITCH_RAD: f32 = 80.0_f32.to_radians();

/// Presentation-only player-head camera. It never feeds combat truth, cleanbox,
/// replay, or player movement; all geometry remains driven by authoritative roots.
struct Camera {
    yaw: f32,
    pitch: f32,
    last_mouse: Option<(f64, f64)>,
}

impl Camera {
    fn new() -> Self {
        Self {
            // yaw=0 faces the locked opponent axis (-Z) from the player root.
            yaw: 0.0,
            pitch: 0.0,
            last_mouse: None,
        }
    }

    fn reset(&mut self) {
        *self = Self::new();
    }

    fn record_mouse_position(&mut self, position: (f64, f64)) -> Option<(f32, f32)> {
        let previous = self.last_mouse.replace(position)?;
        let delta = (
            (position.0 - previous.0) as f32,
            (position.1 - previous.1) as f32,
        );
        self.yaw -= delta.0 * FIRST_PERSON_MOUSE_SENSITIVITY;
        self.pitch = (self.pitch - delta.1 * FIRST_PERSON_MOUSE_SENSITIVITY)
            .clamp(-FIRST_PERSON_MAX_PITCH_RAD, FIRST_PERSON_MAX_PITCH_RAD);
        Some(delta)
    }

    fn eye(&self, player_root: Vec3) -> Vec3 {
        player_root + Vec3::Y * FIRST_PERSON_EYE_HEIGHT
    }

    fn forward(&self) -> Vec3 {
        vec3(
            self.yaw.sin() * self.pitch.cos(),
            self.pitch.sin(),
            -self.yaw.cos() * self.pitch.cos(),
        )
    }

    fn proj_view(&self, aspect: f32, player_root: Vec3) -> Mat4 {
        self.proj_view_with_offset(aspect, player_root, Vec3::ZERO)
    }

    fn proj_view_with_offset(&self, aspect: f32, player_root: Vec3, eye_offset: Vec3) -> Mat4 {
        let eye = self.eye(player_root);
        let view = Mat4::look_at_lh(eye + eye_offset, eye + self.forward(), Vec3::Y);
        let proj = Mat4::perspective_lh(FIRST_PERSON_FOV_Y_RAD, aspect, 0.1, 100.0);
        proj * view
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum DevelopmentCamera {
    FirstPerson,
    BirdsEye,
    LeftQuarter,
    RightQuarter,
}

impl DevelopmentCamera {
    const fn next(self) -> Self {
        match self {
            Self::FirstPerson => Self::BirdsEye,
            Self::BirdsEye => Self::LeftQuarter,
            Self::LeftQuarter => Self::RightQuarter,
            Self::RightQuarter => Self::FirstPerson,
        }
    }

    const fn label(self) -> &'static str {
        match self {
            Self::FirstPerson => "FIRST PERSON",
            Self::BirdsEye => "BIRD'S EYE",
            Self::LeftQuarter => "LEFT 3/4",
            Self::RightQuarter => "RIGHT 3/4",
        }
    }

    fn proj_view(
        self,
        camera: &Camera,
        aspect: f32,
        player_root: Vec3,
        opponent_root: Vec3,
    ) -> Mat4 {
        if self == Self::FirstPerson {
            return camera.proj_view(aspect, player_root);
        }
        let center = (player_root + opponent_root) * 0.5 + Vec3::Y * 0.85;
        let (eye, up) = match self {
            Self::BirdsEye => (center + Vec3::Y * 5.8, Vec3::NEG_Z),
            Self::LeftQuarter => (center + vec3(-4.2, 2.5, 3.8), Vec3::Y),
            Self::RightQuarter => (center + vec3(4.2, 2.5, 3.8), Vec3::Y),
            Self::FirstPerson => unreachable!(),
        };
        let view = Mat4::look_at_lh(eye, center, up);
        let proj = Mat4::perspective_lh(55.0_f32.to_radians(), aspect, 0.1, 100.0);
        proj * view
    }
}

fn motion_frontier_lab_actor_model(actor_root: Vec3) -> Mat4 {
    hero_actor_model(duel_physics::Fighter::Player, actor_root)
}

fn motion_frontier_lab_proj_view(aspect: f32, actor_root: Vec3) -> Mat4 {
    let actor_model = motion_frontier_lab_actor_model(actor_root);
    let forward = actor_model.transform_vector3(Vec3::Z).normalize();
    let right = Vec3::Y.cross(forward).normalize();
    let center = actor_root + Vec3::Y * 0.92;
    let eye = center + forward * 2.65 + right * 0.50 + Vec3::Y * 0.48;
    let view = Mat4::look_at_lh(eye, center, Vec3::Y);
    Mat4::perspective_lh(48.0_f32.to_radians(), aspect, 0.1, 100.0) * view
}

struct App {
    window: Option<Arc<Window>>,
    surface: Option<wgpu::Surface<'static>>,
    device: Option<wgpu::Device>,
    queue: Option<wgpu::Queue>,
    config: Option<wgpu::SurfaceConfiguration>,
    renderer: Option<renderer::Renderer>,
    ui_renderer: Option<ui::UiRenderer>,
    runtime_assets: PathBuf,
    lifecycle_qa_mesh: Option<asset::SkinnedMeshData>,
    camera: Camera,
    development_camera: DevelopmentCamera,
    start_time: Instant,
    last_frame_time: Instant,
    fixed_step_clock: FixedStepClock,
    input: input::InputState,
    clip_fps: f32,
    first_frame_presented: bool,
    /// C0 reference-pose skinning matrices retained as the last geometrically
    /// safe pose while the replacement articulated pipeline is built.
    c0_reference_skin: Vec<Mat4>,
    /// Verified world-space ANM1 transfer for C0 idle staging and radial Move.
    c0_walk_skins: Vec<Vec<Mat4>>,
    /// Immutable R6 Strike presentation shared by the live runtime and QA lab.
    /// It remains presentation-only and can only feed cleanbox through the
    /// measured target boundary.
    hero_strike: hero_strike::HeroStrikePresentation,
    /// Built-in read-only falsification view for the current motion stack.
    motion_frontier_lab: Option<motion_frontier_lab::MotionFrontierLab>,
    /// Exact truth snapshot captured before the lab starts; any mutation fails closed.
    motion_lab_truth_baseline: Option<m3::Snapshot>,
    /// Optional local-only C0 Dodge presentation. It cannot affect truth.
    dodge_presentation: Option<dodge_presentation::DodgePresentation>,
    // Canonical Milestone 3 simulation; rendering only consumes snapshots.
    session: m3::Session,
    cleanbox_world: m3_cleanbox::M3CleanboxWorld,
    ai: m3::SeededAi,
    flow: runtime_flow::RuntimeFlow,
    cursor_captured: bool,
    replay_saved: bool,
    replay_verified: bool,
    /// QA-only deterministic driver. It uses the same input/session path as
    /// keyboard selection; it is never the default launch mode.
    autoplay: bool,
    verify: bool,
    journey_limit: Option<usize>,
    journeys_completed: usize,
    // Telemetry + locomotion
    telemetry: telemetry::Telemetry,
    player_pos: Vec3,
    show_debug: bool,
    show_hud: bool,
    window_size: (u32, u32),
    benchmark_frame_limit: Option<usize>,
    benchmark_frame_ms: Vec<f64>,
}

type CombatUpdate = (
    m3::Snapshot,
    input::PlanInput,
    Vec<Mat4>,
    Vec<Mat4>,
    f32,
    input::PlayerIntent,
);

fn fresh_match_authorities(seed: u64) -> (m3::Session, m3_cleanbox::M3CleanboxWorld, m3::SeededAi) {
    (
        m3::Session::new(seed),
        m3_cleanbox::M3CleanboxWorld::new(),
        m3::SeededAi::new(seed),
    )
}

impl ApplicationHandler for App {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        eprintln!("main: resumed enter");

        let window = Arc::new(
            event_loop
                .create_window(
                    Window::default_attributes()
                        .with_title(if self.motion_frontier_lab.is_some() {
                            "Just Dodge — Motion Frontier Lab"
                        } else {
                            "Just Dodge — Physical Combat Prototype"
                        })
                        .with_inner_size(LogicalSize::new(
                            f64::from(self.window_size.0),
                            f64::from(self.window_size.1),
                        )),
                )
                .unwrap(),
        );
        eprintln!("main: window created");

        let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
            backends: wgpu::Backends::VULKAN,
            flags: wgpu::InstanceFlags::default(),
            memory_budget_thresholds: wgpu::MemoryBudgetThresholds::default(),
            backend_options: wgpu::BackendOptions::default(),
            display: None,
        });
        let surface = instance.create_surface(Arc::clone(&window)).unwrap();
        let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            compatible_surface: Some(&surface),
            ..Default::default()
        }))
        .expect("No suitable GPU adapter found");
        let (device, queue) =
            pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor::default()))
                .expect("Failed to create device");

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
        eprintln!("main: surface configured");

        self.window = Some(window);
        self.surface = Some(surface);
        self.device = Some(device);
        self.queue = Some(queue);
        self.config = Some(config);

        eprintln!("main: window/device ready, requesting redraw");
        self.window.as_ref().unwrap().request_redraw();
    }

    fn about_to_wait(&mut self, _event_loop: &ActiveEventLoop) {
        // Defer heavy Renderer::new() until after the first clear frame was
        // actually presented — this is what lets the Wayland compositor map the
        // window before the app loads 209K+ verts.
        if self.first_frame_presented && self.renderer.is_none() {
            if let (Some(device), Some(queue), Some(config)) = (
                self.device.as_ref(),
                self.queue.as_ref(),
                self.config.as_ref(),
            ) {
                eprintln!("main: starting renderer init after first present");
                self.renderer = Some(if self.journey_limit.is_some() {
                    renderer::Renderer::new_lifecycle_qa(
                        device,
                        queue,
                        config,
                        &self.runtime_assets,
                        self.lifecycle_qa_mesh
                            .as_ref()
                            .expect("journey mode owns its procedural carrier"),
                    )
                } else {
                    renderer::Renderer::new(
                        device,
                        queue,
                        config,
                        renderer::SceneProfile::Duel,
                        &self.runtime_assets,
                    )
                });
                self.ui_renderer = Some(ui::UiRenderer::new(device, queue, config));
                self.last_frame_time = Instant::now();
                self.fixed_step_clock = FixedStepClock::default();
                eprintln!("main: renderer + UI init done");
            }

            if let Some(w) = self.window.as_ref() {
                w.request_redraw();
            }
        }

        // Keep animation ticking.
        if let Some(w) = self.window.as_ref() {
            w.request_redraw();
        }
    }

    fn window_event(
        &mut self,
        event_loop: &ActiveEventLoop,
        _window_id: WindowId,
        event: WindowEvent,
    ) {
        match event {
            WindowEvent::CloseRequested => {
                if let Some(limit) = self.journey_limit
                    && self.journeys_completed < limit
                {
                    eprintln!(
                        "SG02_LIVE_JOURNEYS=FAIL reason=window_closed completed={} required={limit}",
                        self.journeys_completed
                    );
                    std::process::exit(1);
                }
                event_loop.exit();
            }

            WindowEvent::Resized(physical) => {
                let Some(device) = self.device.as_ref() else {
                    return;
                };
                let Some(config) = self.config.as_mut() else {
                    return;
                };
                let Some(surface) = self.surface.as_ref() else {
                    return;
                };

                config.width = physical.width.max(1);
                config.height = physical.height.max(1);
                surface.configure(device, config);

                if let Some(renderer) = self.renderer.as_mut() {
                    renderer.resize(device, config);
                }

                if let Some(w) = self.window.as_ref() {
                    w.request_redraw();
                }
            }

            WindowEvent::MouseInput { state, button, .. } => {
                self.input
                    .handle_mouse_button(button, state == ElementState::Pressed);
            }

            WindowEvent::CursorMoved { position, .. } => {
                let stage = self.flow.stage(self.session.game.snapshot());
                if stage.captures_cursor() {
                    if let Some((dx, dy)) =
                        self.camera.record_mouse_position((position.x, position.y))
                    {
                        self.input.handle_mouse_motion(dx, dy);
                    }
                } else {
                    self.camera.last_mouse = None;
                }
            }

            WindowEvent::MouseWheel { delta, .. } => {
                self.input.handle_scroll(&delta);
            }

            WindowEvent::RedrawRequested => {
                let benchmark_start = Instant::now();
                let renderer_ready = self.renderer.is_some();
                self.render_frame();
                if renderer_ready && self.benchmark_frame_limit.is_some() {
                    self.benchmark_frame_ms
                        .push(benchmark_start.elapsed().as_secs_f64() * 1_000.0);
                }
                if let Some(limit) = self.benchmark_frame_limit
                    && self.benchmark_frame_ms.len() >= limit
                {
                    let mut sorted = self.benchmark_frame_ms.clone();
                    sorted.sort_by(f64::total_cmp);
                    let p95_index = ((sorted.len() * 95).div_ceil(100)).saturating_sub(1);
                    let p95_ms = sorted[p95_index];
                    let mean_ms = sorted.iter().sum::<f64>() / sorted.len() as f64;
                    eprintln!(
                        "P4_BENCHMARK width={} height={} frames={} mean_ms={mean_ms:.3} p95_ms={p95_ms:.3}",
                        self.window_size.0,
                        self.window_size.1,
                        sorted.len()
                    );
                    if let Some(lab) = self.motion_frontier_lab.as_ref() {
                        let metrics = self.hero_strike.motion_lab_metrics(lab.frame());
                        assert_eq!(
                            Some(self.session.game.snapshot()),
                            self.motion_lab_truth_baseline.as_ref(),
                            "Motion Frontier Lab mutated deterministic combat truth"
                        );
                        eprintln!(
                            "MOTION_FRONTIER_LAB_RECEIPT frame={} max_target_error_m={:.9} mean_target_error_m={:.9} planted_foot_drift_m={:.9} grip_error_m={:.9} truth_frame={} presentation_off={} runtime_admission=false",
                            lab.frame(),
                            metrics.max_target_error_m,
                            metrics.mean_target_error_m,
                            metrics.planted_foot_drift_m,
                            metrics.grip_error_m,
                            self.session.game.snapshot().frame,
                            lab.presentation_off(),
                        );
                    }
                    event_loop.exit();
                    return;
                }
                if self.verify
                    && self.replay_saved
                    && self.session.game.snapshot().phase == m3::Phase::MatchResult
                {
                    if !self.replay_verified {
                        eprintln!(
                            "--verify failed: saved replay did not reproduce the live truth hash"
                        );
                        std::process::exit(1);
                    }
                    if let Some(limit) = self.journey_limit {
                        self.journeys_completed += 1;
                        eprintln!(
                            "SG02_LIVE_JOURNEY index={} seed={} terminal_hash={:016x} replay_verified=true",
                            self.journeys_completed,
                            self.session.game.snapshot().seed,
                            self.session.game.truth_hash()
                        );
                        if self.journeys_completed >= limit {
                            eprintln!(
                                "SG02_LIVE_JOURNEYS=PASS count={} no_developer_control=true",
                                self.journeys_completed
                            );
                            event_loop.exit();
                        } else {
                            let next_seed = self.session.game.snapshot().seed.wrapping_add(1);
                            assert!(self.flow.begin_rematch(self.session.game.snapshot()));
                            self.reset_match(next_seed);
                        }
                        return;
                    }
                    event_loop.exit();
                }
            }

            WindowEvent::KeyboardInput { event, .. } => {
                self.input.handle_key(&event);
                self.handle_flow_commands(event_loop);
            }

            _ => {}
        }
    }
}

impl App {
    fn handle_flow_commands(&mut self, event_loop: &ActiveEventLoop) {
        let command = self.input.flow_input();
        let stage = self.flow.stage(self.session.game.snapshot());

        if command.quit {
            assert!(self.flow.request_quit());
            event_loop.exit();
            self.input.reset_flow();
            return;
        }
        if command.pause {
            if self.flow.toggle_pause(self.session.game.snapshot()) {
                let stage = self.flow.stage(self.session.game.snapshot());
                self.sync_cursor_capture(stage);
                eprintln!("Player flow: {stage:?}");
            }
            self.input.reset_flow();
            return;
        }
        if command.back_to_menu {
            self.flow.back_to_menu();
            self.camera.reset();
            self.sync_cursor_capture(runtime_flow::FlowStage::Menu);
            self.input.reset_flow();
            return;
        }
        if command.start && stage == runtime_flow::FlowStage::Menu {
            let current = self.session.game.snapshot();
            let seed = if current.frame == 0 {
                current.seed
            } else {
                current.seed.wrapping_add(1)
            };
            self.reset_match(seed);
            assert!(self.flow.start_match());
            eprintln!("Player flow: Match Setup, seed {seed}");
        } else if command.replay && stage == runtime_flow::FlowStage::Result {
            let snapshot = self.session.game.snapshot().clone();
            match self
                .flow
                .enter_replay(&snapshot, self.session.replay.clone())
            {
                Ok(()) => eprintln!("Player flow: Replay"),
                Err(error) => eprintln!("Replay refused: {error}"),
            }
        } else if command.rematch
            && matches!(
                stage,
                runtime_flow::FlowStage::Result | runtime_flow::FlowStage::Replay
            )
        {
            let next_seed = self.session.game.snapshot().seed.wrapping_add(1);
            assert!(self.flow.begin_rematch(self.session.game.snapshot()));
            self.reset_match(next_seed);
            eprintln!("Player flow: rematch Match Setup, seed {next_seed}");
        } else if command.rematch && stage.captures_cursor() {
            self.camera.reset();
            eprintln!("First-person camera reset");
        }
        self.input.reset_flow();
    }

    fn reset_match(&mut self, seed: u64) {
        (self.session, self.cleanbox_world, self.ai) = fresh_match_authorities(seed);
        self.replay_saved = false;
        self.replay_verified = false;
        self.fixed_step_clock = FixedStepClock::default();
        self.last_frame_time = Instant::now();
        self.input = input::InputState::default();
        self.camera.reset();

        debug_assert_eq!(
            self.session.game.truth_hash(),
            m3::Match::new(seed).truth_hash()
        );
        debug_assert_eq!(self.session.replay.hash_trace.len(), 1);
        debug_assert_eq!(self.cleanbox_world.next_physics_tick(), 0);
        debug_assert_eq!(self.ai, m3::SeededAi::new(seed));
        debug_assert!(!self.replay_saved && !self.replay_verified);
        debug_assert_eq!(self.fixed_step_clock.tick_credit, 0);
        debug_assert_eq!(self.camera.yaw, 0.0);
        debug_assert_eq!(self.camera.pitch, 0.0);
        debug_assert!(self.camera.last_mouse.is_none());
    }

    fn sync_cursor_capture(&mut self, stage: runtime_flow::FlowStage) {
        let desired = stage.captures_cursor();
        if desired == self.cursor_captured {
            return;
        }
        let Some(window) = self.window.as_ref() else {
            return;
        };
        if desired {
            let locked = window
                .set_cursor_grab(CursorGrabMode::Locked)
                .or_else(|_| window.set_cursor_grab(CursorGrabMode::Confined));
            if let Err(error) = locked {
                eprintln!("Cursor capture unavailable: {error}");
                return;
            }
            window.set_cursor_visible(false);
            self.camera.last_mouse = None;
        } else {
            if let Err(error) = window.set_cursor_grab(CursorGrabMode::None) {
                eprintln!("Cursor release failed: {error}");
            }
            window.set_cursor_visible(true);
            self.camera.last_mouse = None;
        }
        self.cursor_captured = desired;
        eprintln!("Cursor captured: {desired}");
    }

    fn combat_update(&mut self) -> Option<CombatUpdate> {
        self.renderer.as_ref()?;

        // --- Fixed-step combat update (before borrowing renderer) ---
        let now = Instant::now();
        let real_dt = now.duration_since(self.last_frame_time);
        self.last_frame_time = now;

        // Presentation only creates canonical inputs; it never mutates game state directly.
        let plan = self.input.plan_input();
        if plan.toggle_debug {
            self.show_debug = !self.show_debug;
            eprintln!("debug overlay: {}", self.show_debug);
        }
        if plan.cycle_debug_camera {
            self.development_camera = self.development_camera.next();
            eprintln!("development camera: {}", self.development_camera.label());
        }
        if plan.toggle_hud {
            self.show_hud = !self.show_hud;
            eprintln!("HUD visible: {}", self.show_hud);
        }

        if let Some(lab) = self.motion_frontier_lab.as_mut() {
            if plan.lab_toggle_play {
                lab.toggle_playing();
            }
            if plan.lab_previous_frame {
                lab.step_previous();
            }
            if plan.lab_next_frame {
                lab.step_next();
            }
            if plan.lab_toggle_presentation {
                lab.toggle_presentation();
            }
            lab.advance(real_dt);
            let frame = lab.frame();
            let snapshot = self.session.game.snapshot().clone();
            assert_eq!(
                Some(&snapshot),
                self.motion_lab_truth_baseline.as_ref(),
                "Motion Frontier Lab mutated deterministic combat truth"
            );
            self.input.reset_plan();
            let player_joints = self.hero_strike.armored_skin(frame).to_vec();
            return Some((
                snapshot,
                plan,
                player_joints,
                self.c0_reference_skin.clone(),
                0.0,
                input::PlayerIntent::Idle,
            ));
        }

        if self.flow.stage(self.session.game.snapshot()) == runtime_flow::FlowStage::Plan {
            let snap = self.session.game.snapshot().clone();
            if !snap.player.committed {
                let player_action = if self.autoplay {
                    Some(counter_action(self.ai.choose(snap.exchange)))
                } else {
                    plan.selected_action
                };
                if let Some(action) = player_action {
                    self.session
                        .apply(m3::Side::Player, m3::Input::Select(action))
                        .expect("Plan accepts one player action selection");
                    if action == m3::Action::Move {
                        let radial_di = if self.autoplay {
                            self.ai.move_di(snap.exchange)
                        } else {
                            plan.radial_di
                        };
                        if !radial_di.is_zero() {
                            self.session
                                .apply(m3::Side::Player, m3::Input::SetRadialDi(radial_di))
                                .expect("Plan accepts one radial movement direction");
                        }
                    }
                }
                let move_ready = player_action != Some(m3::Action::Move)
                    || !self.session.game.snapshot().player.radial_di.is_zero();
                if (self.autoplay || plan.confirmed) && player_action.is_some() && move_ready {
                    self.session
                        .apply(m3::Side::Player, m3::Input::Commit)
                        .expect("selected player action commits exactly once");
                } else if plan.confirmed {
                    eprintln!("select Strike, Block, Grab, or Move with radial direction");
                }
            }
            if !snap.opponent.committed {
                let action = self.ai.choose(snap.exchange);
                self.session
                    .apply(m3::Side::Opponent, m3::Input::Select(action))
                    .expect("seeded AI Plan selection is valid");
                if action == m3::Action::Move {
                    self.session
                        .apply(
                            m3::Side::Opponent,
                            m3::Input::SetRadialDi(self.ai.move_di(snap.exchange)),
                        )
                        .expect("seeded AI movement direction is valid");
                }
                self.session
                    .apply(m3::Side::Opponent, m3::Input::Commit)
                    .expect("seeded AI commits exactly once");
            }
        }
        self.input.reset_plan();

        // Advance and hash-record exactly once per authoritative 60 Hz tick.
        // A redraw can run zero or multiple ticks; fractional time is retained.
        let ticks = self.fixed_step_clock.push_elapsed(real_dt);
        for _ in 0..ticks {
            let stage = self.flow.stage(self.session.game.snapshot());
            match stage {
                runtime_flow::FlowStage::MatchSetup | runtime_flow::FlowStage::Countdown => {
                    self.flow.tick_establishing();
                }
                runtime_flow::FlowStage::Replay => {
                    self.flow
                        .advance_replay()
                        .expect("validated replay playback must remain deterministic");
                }
                runtime_flow::FlowStage::Boot
                | runtime_flow::FlowStage::Menu
                | runtime_flow::FlowStage::Result
                | runtime_flow::FlowStage::Paused
                | runtime_flow::FlowStage::Quit => {}
                _ => {
                    debug_assert!(
                        self.flow.truth_ticks_allowed(self.session.game.snapshot()),
                        "only live duel stages may advance combat truth"
                    );
                    let roots = self.session.game.snapshot();
                    if roots.phase == m3::Phase::Resolve {
                        let Some((player_action, opponent_action)) = roots.revealed else {
                            eprintln!(
                                "Resolve has no revealed actions; refusing to fabricate a measured packet"
                            );
                            self.session.tick();
                            continue;
                        };
                        let player_root = fighter_root(roots, m3::Side::Player);
                        let opponent_root = fighter_root(roots, m3::Side::Opponent);
                        let player_strike_frame = hero_strike_frame(roots, m3::Side::Player)
                            .unwrap_or(hero_strike::CONTACT_FRAME);
                        let opponent_strike_frame = hero_strike_frame(roots, m3::Side::Opponent)
                            .unwrap_or(hero_strike::CONTACT_FRAME);
                        // The two physics targets are adjacent R6 frames, so the
                        // cleanbox CCD observes the same contact transition the
                        // renderer displays at the second (contact) frame.
                        let player_first = measured_fighter_frame(
                            &self.hero_strike,
                            duel_physics::Fighter::Player,
                            player_action,
                            player_root,
                            player_strike_frame.saturating_sub(1),
                            0,
                        );
                        let player_second = measured_fighter_frame(
                            &self.hero_strike,
                            duel_physics::Fighter::Player,
                            player_action,
                            player_root,
                            player_strike_frame,
                            1,
                        );
                        let opponent_first = measured_fighter_frame(
                            &self.hero_strike,
                            duel_physics::Fighter::Opponent,
                            opponent_action,
                            opponent_root,
                            opponent_strike_frame.saturating_sub(1),
                            0,
                        );
                        let opponent_second = measured_fighter_frame(
                            &self.hero_strike,
                            duel_physics::Fighter::Opponent,
                            opponent_action,
                            opponent_root,
                            opponent_strike_frame,
                            1,
                        );
                        self.cleanbox_world
                            .submit_measured_resolve_packet(
                                &mut self.session,
                                duel_world::DuelWorldTarget {
                                    player: player_first.as_target(),
                                    opponent: opponent_first.as_target(),
                                },
                                duel_world::DuelWorldTarget {
                                    player: player_second.as_target(),
                                    opponent: opponent_second.as_target(),
                                },
                            )
                            .expect("M3 Resolve measured presentation packet must be valid");
                    }
                    self.session.tick();
                }
            }
        }

        let live_snapshot = self.session.game.snapshot().clone();
        self.player_pos = fighter_root(&live_snapshot, m3::Side::Player);

        // Save replay once on match end.
        if live_snapshot.phase == m3::Phase::MatchResult && !self.replay_saved {
            self.replay_verified = self.save_replay();
            self.replay_saved = true;
            eprintln!("Player flow: Result");
        }

        let stage = self.flow.stage(&live_snapshot);
        self.sync_cursor_capture(stage);
        let snapshot = self
            .flow
            .replay_snapshot()
            .cloned()
            .unwrap_or(live_snapshot);
        trigger_contact_audio(&snapshot, &self.runtime_assets);

        let cinematic_replay = stage == runtime_flow::FlowStage::Replay;
        let (player_joints, opponent_joints) = self.current_pose(&snapshot, cinematic_replay);
        let elapsed = self.start_time.elapsed().as_secs_f32();
        let intent = self.input.intent();

        // --- Telemetry ---
        self.telemetry.emit(&telemetry::TelemetryFrame {
            t: elapsed,
            player_pos: self.player_pos.to_array(),
            player_intent: format!("{:?}", intent),
            opponent_phase: format!("{:?}", snapshot.phase),
            combat_result: snapshot
                .last_outcome
                .map(|outcome| format!("{:?}", outcome)),
            clip_frame: snapshot.frame as usize,
        });
        self.input.reset_deltas();

        Some((
            snapshot,
            plan,
            player_joints,
            opponent_joints,
            elapsed,
            intent,
        ))
    }

    fn render_frame(&mut self) {
        let combat = self.combat_update();
        let Some(surface) = self.surface.as_ref() else {
            return;
        };
        let Some(device) = self.device.as_ref() else {
            return;
        };
        let Some(queue) = self.queue.as_ref() else {
            return;
        };
        let Some(config) = self.config.as_ref() else {
            return;
        };

        let surface_texture = match surface.get_current_texture() {
            wgpu::CurrentSurfaceTexture::Success(texture)
            | wgpu::CurrentSurfaceTexture::Suboptimal(texture) => texture,
            wgpu::CurrentSurfaceTexture::Occluded | wgpu::CurrentSurfaceTexture::Timeout => {
                return;
            }
            wgpu::CurrentSurfaceTexture::Outdated | wgpu::CurrentSurfaceTexture::Lost => {
                surface.configure(device, config);
                return;
            }
            wgpu::CurrentSurfaceTexture::Validation => return,
        };

        let view = surface_texture
            .texture
            .create_view(&wgpu::TextureViewDescriptor::default());
        let motion_lab_frame = self.motion_frontier_lab.as_ref().map(|lab| lab.frame());
        let motion_lab_presentation_off = self
            .motion_frontier_lab
            .as_ref()
            .is_some_and(|lab| lab.presentation_off());
        let motion_lab_panel = self.motion_frontier_lab.as_ref().map(|lab| {
            let metrics = self.hero_strike.motion_lab_metrics(lab.frame());
            ui::MotionLabPanel {
                frame: lab.frame(),
                frame_count: motion_frontier_lab::LAB_FRAME_COUNT,
                playing: lab.playing(),
                presentation_off: lab.presentation_off(),
                max_target_error_m: metrics.max_target_error_m,
                mean_target_error_m: metrics.mean_target_error_m,
                worst_joint: metrics.worst_joint,
                planted_foot_drift_m: metrics.planted_foot_drift_m,
                grip_error_m: metrics.grip_error_m,
            }
        });

        if let Some(renderer) = self.renderer.as_mut() {
            let Some((snapshot, plan, player_joints, opponent_joints, _elapsed, _intent)) = combat
            else {
                return;
            };

            let flow_stage = self.flow.stage(self.session.game.snapshot());
            let cinematic_replay = flow_stage == runtime_flow::FlowStage::Replay;
            let aspect = config.width as f32 / config.height as f32;
            let player_root = fighter_root(&snapshot, m3::Side::Player);
            let opponent_root = fighter_root(&snapshot, m3::Side::Opponent);
            let first_person_strike_frame =
                if !cinematic_replay && self.development_camera == DevelopmentCamera::FirstPerson {
                    hero_strike_frame(&snapshot, m3::Side::Player)
                } else {
                    None
                };
            let proj_view = if motion_lab_frame.is_some() {
                motion_frontier_lab_proj_view(aspect, player_root)
            } else if cinematic_replay {
                cinematic_replay_proj_view(&snapshot, aspect)
            } else if self.development_camera == DevelopmentCamera::FirstPerson {
                self.camera.proj_view_with_offset(
                    aspect,
                    player_root,
                    impact_camera_offset(&snapshot),
                )
            } else {
                self.development_camera
                    .proj_view(&self.camera, aspect, player_root, opponent_root)
            };

            // --- Now borrow renderer and queue for GPU work ---
            renderer.upload_debug_mvp(queue, &proj_view);
            renderer.update_camera(queue, &proj_view);
            renderer.update_contact_shadows(queue, &proj_view, player_root, opponent_root);
            let correct_model = renderer::skinned_correct_model();

            let player_model = if motion_lab_frame.is_some() {
                motion_frontier_lab_actor_model(player_root)
            } else if cinematic_replay {
                hero_actor_model(duel_physics::Fighter::Player, player_root)
            } else if first_person_strike_frame.is_some() {
                first_person_actor_model(&self.camera, player_root)
            } else {
                Mat4::from_translation(player_root) * correct_model
            };
            renderer.update_skinned_model(queue, 0, &proj_view, player_model);

            let weapon_frame = if let Some(frame) = motion_lab_frame {
                frame
            } else if cinematic_replay {
                cinematic_action_frame(&snapshot, m3::Side::Player).unwrap_or(0)
            } else {
                hero_strike_frame(&snapshot, m3::Side::Player).unwrap_or(0)
            };
            let weapon_actor_model = if cinematic_replay || first_person_strike_frame.is_some() {
                player_model
            } else {
                hero_actor_model(duel_physics::Fighter::Player, player_root)
            };
            let weapon_model = self
                .hero_strike
                .sample(weapon_frame, weapon_actor_model)
                .weapon_transform;
            renderer.update_first_person_weapon(queue, &proj_view, weapon_model);

            let opp_model = if cinematic_replay {
                hero_actor_model(duel_physics::Fighter::Opponent, opponent_root)
            } else {
                Mat4::from_translation(opponent_root) * correct_model
            };
            renderer.update_skinned_model(queue, 1, &proj_view, opp_model);
            let opponent_weapon_frame = if cinematic_replay {
                cinematic_action_frame(&snapshot, m3::Side::Opponent).unwrap_or(0)
            } else {
                hero_strike_frame(&snapshot, m3::Side::Opponent).unwrap_or(0)
            };
            let opponent_weapon_model = self
                .hero_strike
                .sample(opponent_weapon_frame, opp_model)
                .weapon_transform;
            renderer.update_opponent_weapon(queue, &proj_view, opponent_weapon_model);

            // --- Animation pose ---
            renderer.update_skin_joints_indexed(queue, 0, &player_joints);
            renderer.update_skin_joints_indexed(queue, 1, &opponent_joints);

            if let Some(frame) = motion_lab_frame {
                let lab_model = motion_frontier_lab_actor_model(player_root);
                let segments = self.hero_strike.motion_lab_segments(frame, lab_model);
                renderer.update_debug_segments(device, &segments);
            } else if self.show_debug {
                renderer.update_debug_bones(device, &player_joints);
            }
            let impact_lines = if motion_lab_frame.is_some() {
                Vec::new()
            } else {
                impact_burst_lines(&snapshot)
            };
            renderer.update_effect_lines(
                device,
                &impact_lines,
                [1.0, 0.95, 0.72],
                [1.0, 0.30, 0.08],
            );

            // --- Render ---
            let mut encoder =
                device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
            {
                let mut rpass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                    label: None,
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
                    multiview_mask: None,
                    occlusion_query_set: None,
                });
                if !motion_lab_presentation_off {
                    renderer.render(&mut rpass);
                    renderer.render_first_person_weapon(&mut rpass);
                    if motion_lab_frame.is_some() {
                        renderer.render_skinned_index(&mut rpass, 0);
                    } else {
                        renderer.render_opponent_weapon(&mut rpass);
                        renderer.render_skinned_from(
                            &mut rpass,
                            usize::from(
                                !cinematic_replay
                                    && self.development_camera == DevelopmentCamera::FirstPerson,
                            ),
                        );
                    }
                }
                if motion_lab_frame.is_some() || self.show_debug {
                    renderer.render_debug_overlay(&mut rpass);
                }
                if motion_lab_frame.is_none() && (self.show_debug || !impact_lines.is_empty()) {
                    renderer.render_hitbox_debug(&mut rpass);
                }
            }

            // UI pass: separate render pass so it draws over everything without depth.
            if self.show_hud
                && let Some(ui_renderer) = self.ui_renderer.as_mut()
            {
                let mut rpass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                    label: Some("ui pass"),
                    color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                        view: &view,
                        resolve_target: None,
                        depth_slice: None,
                        ops: wgpu::Operations {
                            load: wgpu::LoadOp::Load,
                            store: wgpu::StoreOp::Store,
                        },
                    })],
                    depth_stencil_attachment: None,
                    timestamp_writes: None,
                    multiview_mask: None,
                    occlusion_query_set: None,
                });
                ui_renderer.render(
                    &mut rpass,
                    ui::UiFrame {
                        snapshot: &snapshot,
                        plan: &plan,
                        flow_stage,
                        establishing_remaining: self.flow.establishing_remaining(),
                        camera_label: if cinematic_replay {
                            "FIGHT FILM"
                        } else {
                            self.development_camera.label()
                        },
                        replay_total_exchanges: self.flow.replay_total_exchanges(),
                        replay_finished: self.flow.replay_finished(),
                        motion_lab: motion_lab_panel,
                        width: config.width,
                        height: config.height,
                    },
                    queue,
                );
            }

            queue.submit(std::iter::once(encoder.finish()));
        } else {
            // Fallback clear frame.
            let mut encoder =
                device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
            {
                let _rpass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                    label: Some("initial clear"),
                    color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                        view: &view,
                        resolve_target: None,
                        depth_slice: None,
                        ops: wgpu::Operations {
                            load: wgpu::LoadOp::Clear(wgpu::Color {
                                r: 0.02,
                                g: 0.02,
                                b: 0.05,
                                a: 1.0,
                            }),
                            store: wgpu::StoreOp::Store,
                        },
                    })],
                    depth_stencil_attachment: None,
                    timestamp_writes: None,
                    multiview_mask: None,
                    occlusion_query_set: None,
                });
            }
            queue.submit(std::iter::once(encoder.finish()));

            if !self.first_frame_presented {
                self.first_frame_presented = true;
                eprintln!("main: first clear frame presented");
            }
        }

        queue.present(surface_texture);
    }

    fn current_pose(
        &self,
        snapshot: &m3::Snapshot,
        cinematic_replay: bool,
    ) -> (Vec<Mat4>, Vec<Mat4>) {
        let sample = |side| {
            if cinematic_replay && let Some(frame) = cinematic_action_frame(snapshot, side) {
                return self.hero_strike.sample(frame, Mat4::IDENTITY).skin.to_vec();
            }
            if let Some(frame) = hero_strike_frame(snapshot, side) {
                return self.hero_strike.sample(frame, Mat4::IDENTITY).skin.to_vec();
            }
            let action = snapshot.revealed.map(|revealed| match side {
                m3::Side::Player => revealed.0,
                m3::Side::Opponent => revealed.1,
            });
            let phase_tick = match snapshot.phase {
                m3::Phase::Reveal => Some(snapshot.phase_frame),
                m3::Phase::Resolve => Some(12 + snapshot.phase_frame),
                m3::Phase::Consequence => Some(13 + snapshot.phase_frame),
                _ => None,
            };
            if action == Some(m3::Action::Move) {
                let index = phase_tick
                    .map(|tick| usize::from(tick) % self.c0_walk_skins.len())
                    .unwrap_or(3);
                self.c0_walk_skins
                    .get(index)
                    .cloned()
                    .unwrap_or_else(|| self.c0_reference_skin.clone())
            } else {
                self.c0_reference_skin.clone()
            }
        };
        (sample(m3::Side::Player), sample(m3::Side::Opponent))
    }

    fn save_replay(&self) -> bool {
        let ts = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let path = PathBuf::from(format!("/tmp/just_dodge_m3_replay_{ts}.ron"));
        match self.session.replay.save(&path) {
            Ok(()) => match m3::verify_replay_file(&path) {
                Ok(verification)
                    if verification.final_frame == self.session.game.snapshot().frame
                        && verification.truth_hash == self.session.game.truth_hash() =>
                {
                    eprintln!(
                        "RUNTIME_REPLAY_HASH_VERIFIED replay={} hashes={} frame={} hash={:016x}",
                        path.display(),
                        verification.frames,
                        verification.final_frame,
                        verification.truth_hash,
                    );
                    true
                }
                Ok(verification) => {
                    eprintln!(
                        "Replay parity failure replay={} expected_frame={} actual_frame={} expected_hash={:016x} actual_hash={:016x}",
                        path.display(),
                        self.session.game.snapshot().frame,
                        verification.final_frame,
                        self.session.game.truth_hash(),
                        verification.truth_hash,
                    );
                    false
                }
                Err(error) => {
                    eprintln!(
                        "Replay hash verification failed {}: {error}",
                        path.display()
                    );
                    false
                }
            },
            Err(error) => {
                eprintln!("Failed to save replay {}: {error}", path.display());
                false
            }
        }
    }
}

fn opponent_dodge_presentation_tick(snapshot: &truth::TruthSnapshot) -> Option<u32> {
    if snapshot.opponent.action != Some(truth::Action::Dodge) {
        return None;
    }
    dodge_phase_tick(snapshot.phase, snapshot.phase_frame)
}

fn hero_strike_frame(snapshot: &m3::Snapshot, side: m3::Side) -> Option<usize> {
    let action = snapshot.revealed.map(|revealed| match side {
        m3::Side::Player => revealed.0,
        m3::Side::Opponent => revealed.1,
    });
    (action == Some(m3::Action::Strike))
        .then(|| hero_strike_phase_frame_index(snapshot.phase, snapshot.phase_frame))
        .flatten()
}

fn cinematic_action_frame(snapshot: &m3::Snapshot, side: m3::Side) -> Option<usize> {
    let action = snapshot
        .revealed
        .map(|revealed| match side {
            m3::Side::Player => revealed.0,
            m3::Side::Opponent => revealed.1,
        })
        .or(match side {
            m3::Side::Player => snapshot.player.planned,
            m3::Side::Opponent => snapshot.opponent.planned,
        })?;
    if action == m3::Action::Move {
        return None;
    }
    if action == m3::Action::Strike {
        return hero_strike_phase_frame_index(snapshot.phase, snapshot.phase_frame)
            .or(Some(hero_strike::CONTACT_FRAME));
    }

    let (ready, active) = match action {
        m3::Action::Block => (8, 18),
        m3::Action::Grab => (6, 26),
        m3::Action::Strike | m3::Action::Move => unreachable!(),
    };
    match snapshot.phase {
        m3::Phase::Commit => Some(scale_clip_frame(snapshot.phase_frame.min(1), 1, 0, ready)),
        m3::Phase::Reveal => Some(scale_clip_frame(
            snapshot.phase_frame.min(11),
            11,
            ready,
            active,
        )),
        m3::Phase::Resolve => Some(active),
        m3::Phase::Consequence => Some(scale_clip_frame_reverse(
            snapshot.phase_frame.min(17),
            17,
            active,
        )),
        m3::Phase::MatchResult => Some(active),
        m3::Phase::Observe | m3::Phase::Plan => None,
    }
}

fn cinematic_replay_proj_view(snapshot: &m3::Snapshot, aspect: f32) -> Mat4 {
    let player_root = fighter_root(snapshot, m3::Side::Player);
    let opponent_root = fighter_root(snapshot, m3::Side::Opponent);
    let center = (player_root + opponent_root) * 0.5;
    let actions = snapshot
        .revealed
        .or_else(|| Some((snapshot.player.planned?, snapshot.opponent.planned?)));
    let focus = match actions {
        Some((m3::Action::Strike | m3::Action::Grab, _)) => m3::Side::Player,
        Some((_, m3::Action::Strike | m3::Action::Grab)) => m3::Side::Opponent,
        _ if snapshot.exchange.is_multiple_of(2) => m3::Side::Player,
        _ => m3::Side::Opponent,
    };
    let cut_sign = if snapshot.exchange.is_multiple_of(2) {
        1.0
    } else {
        -1.0
    };
    let base_angle = match focus {
        m3::Side::Player => std::f32::consts::FRAC_PI_2 - 0.16,
        m3::Side::Opponent => -std::f32::consts::FRAC_PI_2 + 0.16,
    };
    let phase_progress = match snapshot.phase {
        m3::Phase::Commit => snapshot.phase_frame as f32 / 1.0,
        m3::Phase::Reveal => snapshot.phase_frame as f32 / 11.0,
        m3::Phase::Resolve => 1.0,
        m3::Phase::Consequence => snapshot.phase_frame as f32 / 17.0,
        m3::Phase::MatchResult => 1.0,
        m3::Phase::Observe | m3::Phase::Plan => 0.0,
    }
    .clamp(0.0, 1.0);
    let eased = phase_progress * phase_progress * (3.0 - 2.0 * phase_progress);
    let (angle, radius, height) = match snapshot.phase {
        m3::Phase::Commit => (base_angle - 0.28 * cut_sign, 5.2 - 0.45 * eased, 2.3),
        m3::Phase::Reveal => (
            base_angle + cut_sign * (-0.26 + 0.52 * eased),
            4.4 - 0.65 * eased,
            1.8 + 0.16 * (phase_progress * std::f32::consts::PI).sin(),
        ),
        m3::Phase::Resolve => (base_angle + 0.42 * cut_sign, 3.35, 1.55),
        m3::Phase::Consequence => (
            base_angle + cut_sign * (0.42 - 0.16 * eased),
            3.35 + 1.15 * eased,
            1.55 + 0.55 * eased,
        ),
        m3::Phase::MatchResult => (base_angle - 0.46 * cut_sign, 5.35, 2.8),
        m3::Phase::Observe | m3::Phase::Plan => (base_angle, 5.0, 2.3),
    };
    let (sin_angle, cos_angle) = angle.sin_cos();
    let mut eye = center + vec3(sin_angle * radius, height, cos_angle * radius);
    if matches!(snapshot.phase, m3::Phase::Resolve | m3::Phase::Consequence)
        && snapshot.phase_frame <= 5
        && snapshot.last_contact.is_some()
    {
        let impulse = 0.025 * (6 - snapshot.phase_frame) as f32 / 6.0;
        eye += vec3(cut_sign * impulse, -impulse * 0.35, 0.0);
    }
    let target = snapshot
        .last_contact
        .map_or(center + Vec3::Y * 1.02, |contact| {
            let defender = fighter_root(snapshot, contact.attacker.other());
            let height = match contact.region {
                m3::BodyRegion::Head => 1.62,
                m3::BodyRegion::Torso => 1.14,
                m3::BodyRegion::Arms => 1.28,
            };
            defender + Vec3::Y * height
        });
    let view = Mat4::look_at_lh(eye, target, Vec3::Y);
    Mat4::perspective_lh(48.0_f32.to_radians(), aspect, 0.1, 100.0) * view
}

fn measured_fighter_frame(
    hero: &hero_strike::HeroStrikePresentation,
    fighter: duel_physics::Fighter,
    action: m3::Action,
    root: Vec3,
    hero_frame: usize,
    substep: usize,
) -> cleanbox::FighterFrame {
    if action != m3::Action::Strike {
        return cleanbox::action_frame(fighter, m3_cleanbox::target_action(action), root, substep);
    }
    let actor_model = hero_actor_model(fighter, root);
    let sample = hero.sample(hero_frame, actor_model);
    cleanbox::FighterFrame::measured(sample.weapon_transform, Vec::new(), sample.body_proxies())
}

fn hero_actor_model(fighter: duel_physics::Fighter, root: Vec3) -> Mat4 {
    let facing = match fighter {
        duel_physics::Fighter::Player => Mat4::from_rotation_y(std::f32::consts::PI),
        duel_physics::Fighter::Opponent => Mat4::IDENTITY,
    };
    Mat4::from_translation(root)
        * facing
        * Mat4::from_scale_rotation_translation(
            Vec3::splat(0.9189),
            glam::Quat::from_rotation_y(-0.47),
            Vec3::ZERO,
        )
}

fn first_person_actor_model(camera: &Camera, player_root: Vec3) -> Mat4 {
    let forward = camera.forward();
    let right = Vec3::Y.cross(forward).normalize();
    Mat4::from_translation(forward * 0.55 + right * 0.10 - Vec3::Y * 0.12)
        * hero_actor_model(duel_physics::Fighter::Player, player_root)
}

fn impact_camera_offset(snapshot: &m3::Snapshot) -> Vec3 {
    if snapshot.phase != m3::Phase::Consequence
        || snapshot.phase_frame > 5
        || snapshot.last_contact.is_none()
    {
        return Vec3::ZERO;
    }
    let strength = 0.032 * (6 - snapshot.phase_frame) as f32 / 6.0;
    let direction = match snapshot.phase_frame % 4 {
        0 => vec3(1.0, 0.35, 0.0),
        1 => vec3(-0.65, -0.25, 0.0),
        2 => vec3(0.35, -0.5, 0.0),
        _ => vec3(-0.2, 0.15, 0.0),
    };
    direction * strength
}

static LAST_AUDIO_EXCHANGE: AtomicU32 = AtomicU32::new(u32::MAX);

fn trigger_contact_audio(snapshot: &m3::Snapshot, assets: &std::path::Path) {
    if snapshot.phase != m3::Phase::Consequence
        || snapshot.phase_frame != 0
        || snapshot.last_contact.is_none()
    {
        return;
    }
    let exchange = snapshot.exchange;
    if LAST_AUDIO_EXCHANGE.swap(exchange, Ordering::SeqCst) == exchange {
        return;
    }
    let clip = assets.join("audio/r6k_strike_contact.wav");
    if let Err(error) = Command::new("pw-play").arg(&clip).spawn() {
        eprintln!("contact audio {} failed: {error}", clip.display());
    }
}

fn impact_burst_lines(snapshot: &m3::Snapshot) -> Vec<(Vec3, Vec3)> {
    if snapshot.phase != m3::Phase::Consequence || snapshot.phase_frame > 8 {
        return Vec::new();
    }
    let Some(contact) = snapshot.last_contact else {
        return Vec::new();
    };
    let target_side = match contact.attacker {
        m3::Side::Player => m3::Side::Opponent,
        m3::Side::Opponent => m3::Side::Player,
    };
    let root = fighter_root(snapshot, target_side);
    let local = match contact.region {
        m3::BodyRegion::Head => vec3(0.0, 1.62, 0.0),
        m3::BodyRegion::Torso => vec3(0.0, 1.14, 0.0),
        m3::BodyRegion::Arms => vec3(0.32, 1.26, 0.0),
    };
    let center = root + local;
    let radius = 0.34 * (9 - snapshot.phase_frame) as f32 / 9.0;
    [
        vec3(1.0, 0.0, 0.0),
        vec3(-1.0, 0.0, 0.0),
        vec3(0.0, 1.0, 0.0),
        vec3(0.0, -1.0, 0.0),
        vec3(0.7, 0.7, 0.2),
        vec3(-0.7, 0.7, -0.2),
        vec3(0.55, -0.35, 0.75),
        vec3(-0.55, -0.35, 0.75),
    ]
    .into_iter()
    .map(|direction| {
        let direction = direction.normalize();
        (center + direction * 0.035, center + direction * radius)
    })
    .collect()
}

/// Map 60 Hz M3 action phases onto the complete 25 Hz 52-frame clip.
fn hero_strike_phase_frame_index(phase: m3::Phase, phase_frame: u16) -> Option<usize> {
    match phase {
        m3::Phase::Commit => Some(scale_clip_frame(phase_frame.min(1), 1, 0, 3)),
        m3::Phase::Reveal => Some(scale_clip_frame(phase_frame.min(11), 11, 4, 26)),
        m3::Phase::Resolve => Some(hero_strike::CONTACT_FRAME),
        m3::Phase::Consequence if phase_frame <= 2 => Some(hero_strike::CONTACT_FRAME),
        m3::Phase::Consequence => Some(scale_clip_frame(phase_frame.min(17) - 3, 14, 28, 51)),
        m3::Phase::Observe | m3::Phase::Plan | m3::Phase::MatchResult => None,
    }
}

const fn scale_clip_frame(value: u16, denominator: u16, first: usize, last: usize) -> usize {
    let span = last - first;
    first + (value as usize * span + denominator as usize / 2) / denominator as usize
}

const fn scale_clip_frame_reverse(value: u16, denominator: u16, first: usize) -> usize {
    first - (value as usize * first + denominator as usize / 2) / denominator as usize
}

fn dodge_phase_tick(phase: truth::Phase, phase_frame: u32) -> Option<u32> {
    let offset = match phase {
        truth::Phase::Commit => 0,
        truth::Phase::Reveal => 5,
        truth::Phase::Resolve => 20,
        truth::Phase::Consequence => 50,
        truth::Phase::Observe | truth::Phase::Plan => return None,
    };
    Some((offset + phase_frame).min(dodge_presentation::DODGE_PRESENTATION_TICKS - 1))
}

const fn counter_action(action: m3::Action) -> m3::Action {
    match action {
        m3::Action::Strike => m3::Action::Block,
        m3::Action::Block => m3::Action::Grab,
        m3::Action::Grab => m3::Action::Strike,
        m3::Action::Move => m3::Action::Strike,
    }
}

fn fighter_root(snapshot: &m3::Snapshot, side: m3::Side) -> Vec3 {
    let fighter = match side {
        m3::Side::Player => snapshot.player,
        m3::Side::Opponent => snapshot.opponent,
    };
    let right_m = fighter.displacement_mm[0] as f32 / 1_000.0;
    let forward_m = fighter.displacement_mm[1] as f32 / 1_000.0;
    match side {
        m3::Side::Player => vec3(right_m, 0.0, 1.0 - forward_m),
        m3::Side::Opponent => vec3(-right_m, 0.0, -1.0 + forward_m),
    }
}

#[cfg(test)]
mod dodge_presentation_phase_tests {
    use super::*;

    #[test]
    fn dodge_presentation_phase_mapping_is_commit_through_consequence_only() {
        assert_eq!(dodge_phase_tick(truth::Phase::Observe, 0), None);
        assert_eq!(dodge_phase_tick(truth::Phase::Plan, 0), None);
        assert_eq!(dodge_phase_tick(truth::Phase::Commit, 4), Some(4));
        assert_eq!(dodge_phase_tick(truth::Phase::Reveal, 0), Some(5));
        assert_eq!(dodge_phase_tick(truth::Phase::Resolve, 0), Some(20));
        assert_eq!(dodge_phase_tick(truth::Phase::Consequence, 29), Some(79));
        assert_eq!(dodge_phase_tick(truth::Phase::Consequence, 100), Some(79));
    }

    #[test]
    fn only_revealed_strike_selects_the_r6_pose_stream() {
        let mut game = m3::Match::new(7);
        while game.snapshot().phase != m3::Phase::Plan {
            game.tick();
        }
        game.apply(m3::Side::Player, m3::Input::Select(m3::Action::Strike))
            .unwrap();
        game.apply(m3::Side::Opponent, m3::Input::Select(m3::Action::Block))
            .unwrap();
        game.apply(m3::Side::Player, m3::Input::Commit).unwrap();
        game.apply(m3::Side::Opponent, m3::Input::Commit).unwrap();
        while game.snapshot().phase != m3::Phase::Reveal {
            game.tick();
        }
        assert_eq!(
            hero_strike_frame(game.snapshot(), m3::Side::Player),
            Some(4)
        );
        assert_eq!(hero_strike_frame(game.snapshot(), m3::Side::Opponent), None);
    }

    #[test]
    fn cinematic_replay_animates_counters_and_uses_finite_directed_cuts() {
        let mut game = m3::Match::new(11);
        while game.snapshot().phase != m3::Phase::Plan {
            game.tick();
        }
        game.apply(m3::Side::Player, m3::Input::Select(m3::Action::Strike))
            .unwrap();
        game.apply(m3::Side::Opponent, m3::Input::Select(m3::Action::Block))
            .unwrap();
        game.apply(m3::Side::Player, m3::Input::Commit).unwrap();
        game.apply(m3::Side::Opponent, m3::Input::Commit).unwrap();
        game.tick();
        let commit = game.snapshot().clone();
        assert_eq!(commit.phase, m3::Phase::Commit);
        assert!(cinematic_action_frame(&commit, m3::Side::Opponent).is_some());

        while game.snapshot().phase != m3::Phase::Reveal {
            game.tick();
        }
        let reveal = game.snapshot().clone();
        let wide = cinematic_replay_proj_view(&commit, 16.0 / 9.0);
        let track = cinematic_replay_proj_view(&reveal, 16.0 / 9.0);
        assert!(wide.is_finite());
        assert!(track.is_finite());
        assert_ne!(wide.to_cols_array(), track.to_cols_array());
        assert_ne!(
            cinematic_action_frame(&commit, m3::Side::Opponent),
            cinematic_action_frame(&reveal, m3::Side::Opponent)
        );
    }
}

fn ai_snapshot_from_truth(snapshot: &truth::TruthSnapshot, side: truth::Side) -> ai::AiSnapshot {
    let (mine, theirs) = match side {
        truth::Side::Player => (&snapshot.player, &snapshot.opponent),
        truth::Side::Opponent => (&snapshot.opponent, &snapshot.player),
    };
    ai::AiSnapshot {
        phase: snapshot.phase.name().to_string(),
        my_health: mine.health / 100.0,
        my_stamina: mine.stamina / 100.0,
        opponent_health: theirs.health / 100.0,
        opponent_stamina: theirs.stamina / 100.0,
        last_player_action: None,
        last_player_stance: None,
    }
}

fn last_result_text(snapshot: &truth::TruthSnapshot) -> Option<String> {
    snapshot.last_contact.map(|_| {
        let pa = snapshot
            .player
            .action
            .map(|a| format!("{:?}", a))
            .unwrap_or_default();
        let oa = snapshot
            .opponent
            .action
            .map(|a| format!("{:?}", a))
            .unwrap_or_default();
        format!("{} vs {}", pa, oa)
    })
}

#[cfg(test)]
mod fixed_step_tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn fresh_match_authorities_reset_truth_physics_and_ai() {
        let old_seed = 0x4d33_0200;
        let (mut old_session, mut old_world, _) = fresh_match_authorities(old_seed);
        while old_session.game.snapshot().phase != m3::Phase::Plan {
            old_session.tick();
        }
        old_session
            .apply(m3::Side::Player, m3::Input::Select(m3::Action::Strike))
            .unwrap();
        old_session
            .apply(m3::Side::Opponent, m3::Input::Select(m3::Action::Block))
            .unwrap();
        old_session
            .apply(m3::Side::Player, m3::Input::Commit)
            .unwrap();
        old_session
            .apply(m3::Side::Opponent, m3::Input::Commit)
            .unwrap();
        while old_session.game.snapshot().phase != m3::Phase::Resolve {
            old_session.tick();
        }
        old_world
            .submit_resolve_packet(&mut old_session, vec3(0.0, 0.0, 1.0), vec3(0.0, 0.0, -1.0))
            .unwrap();
        assert_eq!(old_world.next_physics_tick(), 2);

        let new_seed = old_seed + 1;
        let (session, world, ai) = fresh_match_authorities(new_seed);
        let canonical = m3::Match::new(new_seed);
        assert_eq!(session.game.snapshot(), canonical.snapshot());
        assert_eq!(session.game.truth_hash(), canonical.truth_hash());
        assert_eq!(session.replay.hash_trace, vec![canonical.truth_hash()]);
        assert_eq!(world.next_physics_tick(), 0);
        assert_eq!(ai, m3::SeededAi::new(new_seed));
    }

    #[test]
    fn ten_consecutive_autoplay_journeys_replay_and_rematch_canonically() {
        let mut seed = 0x4d33_0210;
        let (mut session, mut world, mut ai) = fresh_match_authorities(seed);
        let mut flow = runtime_flow::RuntimeFlow::menu();

        for journey in 0..10 {
            if journey == 0 {
                assert!(flow.start_match());
            }
            for _ in 0..runtime_flow::ESTABLISHING_TICKS {
                flow.tick_establishing();
            }
            assert_eq!(
                flow.stage(session.game.snapshot()),
                runtime_flow::FlowStage::Observe
            );

            let mut ticks = 0_u32;
            while session.game.snapshot().phase != m3::Phase::MatchResult {
                ticks += 1;
                assert!(ticks <= 20_000, "journey {journey} did not terminate");
                let snapshot = session.game.snapshot().clone();
                if snapshot.phase == m3::Phase::Plan {
                    let opponent = ai.choose(snapshot.exchange);
                    let player = counter_action(opponent);
                    session
                        .apply(m3::Side::Player, m3::Input::Select(player))
                        .unwrap();
                    if player == m3::Action::Move {
                        session
                            .apply(
                                m3::Side::Player,
                                m3::Input::SetRadialDi(ai.move_di(snapshot.exchange)),
                            )
                            .unwrap();
                    }
                    session.apply(m3::Side::Player, m3::Input::Commit).unwrap();
                    session
                        .apply(m3::Side::Opponent, m3::Input::Select(opponent))
                        .unwrap();
                    if opponent == m3::Action::Move {
                        session
                            .apply(
                                m3::Side::Opponent,
                                m3::Input::SetRadialDi(ai.move_di(snapshot.exchange)),
                            )
                            .unwrap();
                    }
                    session
                        .apply(m3::Side::Opponent, m3::Input::Commit)
                        .unwrap();
                }
                if session.game.snapshot().phase == m3::Phase::Resolve {
                    let snapshot = session.game.snapshot();
                    let player_root = fighter_root(snapshot, m3::Side::Player);
                    let opponent_root = fighter_root(snapshot, m3::Side::Opponent);
                    world
                        .submit_resolve_packet(&mut session, player_root, opponent_root)
                        .unwrap();
                }
                session.tick();
            }

            let terminal_hash = session.game.truth_hash();
            let replay = session.replay.clone();
            let reconstructed = m3::replay(&replay).unwrap();
            assert_eq!(reconstructed.truth_hash(), terminal_hash);
            assert_eq!(reconstructed.snapshot(), session.game.snapshot());
            flow.enter_replay(session.game.snapshot(), replay).unwrap();
            while flow.advance_replay().unwrap() {}
            assert_eq!(
                flow.replay_snapshot().unwrap(),
                session.game.snapshot(),
                "journey {journey} replay diverged"
            );

            if journey < 9 {
                assert!(flow.begin_rematch(session.game.snapshot()));
                seed = seed.wrapping_add(1);
                (session, world, ai) = fresh_match_authorities(seed);
                let canonical = m3::Session::new(seed);
                assert_eq!(session.game.truth_hash(), canonical.game.truth_hash());
                assert_eq!(session.replay, canonical.replay);
                assert_eq!(world.next_physics_tick(), 0);
                assert_eq!(ai, m3::SeededAi::new(seed));
            }
        }
    }

    fn hashes_at_render_rate(render_hz: u32) -> (Vec<u64>, Vec<replay::MatchEvent>) {
        let mut clock = FixedStepClock::default();
        let mut truth = truth::CombatTruth::new();
        let mut duel_world = duel_world::DuelWorld::new();
        let mut replay = replay::ReplayRecorder::new(0);
        let mut hashes = Vec::new();
        let mut previous = Duration::ZERO;

        for render_frame in 1..=(render_hz * 3) {
            let absolute = Duration::from_secs_f64(render_frame as f64 / render_hz as f64);
            let elapsed = absolute - previous;
            previous = absolute;

            for _ in 0..clock.push_elapsed(elapsed) {
                if truth.snapshot().frame == 30 {
                    truth.apply_input(
                        truth::Side::Player,
                        truth::PlayerInput::SelectAction(truth::Action::Thrust),
                    );
                    truth.apply_input(
                        truth::Side::Player,
                        truth::PlayerInput::SelectStance(truth::Stance::Top),
                    );
                    truth.apply_input(truth::Side::Player, truth::PlayerInput::Commit);
                    truth.apply_input(
                        truth::Side::Opponent,
                        truth::PlayerInput::SelectAction(truth::Action::Block),
                    );
                    truth.apply_input(
                        truth::Side::Opponent,
                        truth::PlayerInput::SelectStance(truth::Stance::Top),
                    );
                    truth.apply_input(truth::Side::Opponent, truth::PlayerInput::Commit);
                }

                let before_tick = truth.snapshot().clone();
                let resolve_packet = cleanbox::submit_resolve_packet(
                    &mut truth,
                    &mut duel_world,
                    vec3(0.0, 0.0, 1.0),
                    vec3(0.0, 0.0, -1.0),
                )
                .unwrap();
                truth.tick();
                let truth_hash = truth.truth_hash();
                if let Some(packet) = resolve_packet {
                    replay.record_resolve_packet(
                        &before_tick,
                        truth.snapshot(),
                        &packet,
                        truth_hash,
                    );
                }
                hashes.push(truth_hash);
            }
        }

        assert_eq!(truth.snapshot().frame, 180);
        (hashes, replay.events)
    }

    #[test]
    fn fixed_step_clock_is_render_rate_independent() {
        let expected = hashes_at_render_rate(60);
        let resolve_packets = expected
            .1
            .iter()
            .filter(|event| matches!(event.kind, replay::EventKind::ResolvePacket { .. }))
            .count();
        assert_eq!(resolve_packets, 1);
        for render_hz in [30, 144, 240] {
            assert_eq!(hashes_at_render_rate(render_hz), expected, "{render_hz} Hz");
        }
    }

    #[test]
    fn first_person_camera_is_root_relative_and_faces_locked_opponent_axis() {
        let camera = Camera::new();
        let root = vec3(2.0, 0.25, 4.0);
        assert_eq!(camera.eye(root), root + Vec3::Y * FIRST_PERSON_EYE_HEIGHT);
        assert!(camera.forward().abs_diff_eq(-Vec3::Z, 1e-6));
        assert!(camera.proj_view(16.0 / 9.0, root).is_finite());
    }

    #[test]
    fn first_person_camera_look_ignores_initial_sample_and_clamps_pitch() {
        let mut camera = Camera::new();
        assert_eq!(camera.record_mouse_position((100.0, 100.0)), None);
        assert_eq!(camera.yaw, 0.0);
        assert_eq!(camera.pitch, 0.0);

        let delta = camera.record_mouse_position((200.0, 100_000.0)).unwrap();
        assert_eq!(delta.0, 100.0);
        assert!(camera.yaw < 0.0);
        assert_eq!(camera.pitch, -FIRST_PERSON_MAX_PITCH_RAD);
        assert!(camera.forward().is_finite());
    }

    #[test]
    fn fixed_step_clock_bounds_catch_up_without_dropping_time() {
        let mut clock = FixedStepClock::default();
        let mut ticks = Vec::new();

        ticks.push(clock.push_elapsed(Duration::from_secs(1)));
        for _ in 0..7 {
            ticks.push(clock.push_elapsed(Duration::ZERO));
        }

        assert_eq!(ticks, vec![8, 8, 8, 8, 8, 8, 8, 4]);
        assert_eq!(clock.push_elapsed(Duration::ZERO), 0);
    }
}

fn main() {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    if arguments
        .first()
        .is_some_and(|argument| argument == "--reduce-replay")
    {
        if arguments.len() != 2 {
            eprintln!("usage: just-dodge --reduce-replay <path.jdrp>");
            std::process::exit(2);
        }
        match replay::ReplayRecorder::reduce_file(std::path::Path::new(&arguments[1])) {
            Ok(report) => print!("{report}"),
            Err(error) => {
                eprintln!("replay reduction failed: {error:#}");
                std::process::exit(1);
            }
        }
        return;
    }

    let motion_lab_frame = arguments
        .windows(2)
        .find(|pair| pair[0] == "--motion-frontier-lab-frame")
        .map(|pair| {
            pair[1]
                .parse::<usize>()
                .expect("--motion-frontier-lab-frame must be an integer from 0 to 63")
        });
    let motion_lab_context = arguments
        .iter()
        .any(|argument| argument == "--motion-frontier-lab-context");
    let motion_lab_enabled = arguments
        .iter()
        .any(|argument| argument == "--motion-frontier-lab")
        || motion_lab_frame.is_some()
        || motion_lab_context;
    let motion_lab_frame = motion_lab_frame.unwrap_or(0);
    assert!(
        motion_lab_frame < motion_frontier_lab::LAB_FRAME_COUNT,
        "--motion-frontier-lab-frame must be from 0 to 63"
    );
    let telemetry_enabled = arguments.iter().any(|argument| argument == "--telemetry");
    let benchmark_frame_limit = arguments
        .windows(2)
        .find(|pair| pair[0] == "--benchmark-frames")
        .map(|pair| {
            pair[1]
                .parse::<usize>()
                .expect("--benchmark-frames must be a positive integer")
        });
    let journey_limit = arguments
        .windows(2)
        .find(|pair| pair[0] == "--journeys")
        .map(|pair| {
            let count = pair[1]
                .parse::<usize>()
                .expect("--journeys must be a positive integer");
            assert!(count > 0, "--journeys must be a positive integer");
            count
        });
    let window_size = arguments
        .windows(2)
        .find(|pair| pair[0] == "--resolution")
        .map(|pair| {
            let (width, height) = pair[1]
                .split_once('x')
                .expect("--resolution must use WIDTHxHEIGHT");
            (
                width.parse::<u32>().expect("invalid resolution width"),
                height.parse::<u32>().expect("invalid resolution height"),
            )
        })
        .unwrap_or((1280, 720));
    let autoplay = !motion_lab_enabled
        && (arguments.iter().any(|argument| argument == "--autoplay")
            || benchmark_frame_limit.is_some()
            || journey_limit.is_some());
    let verify = arguments.iter().any(|argument| argument == "--verify") || journey_limit.is_some();
    let assets = std::env::var("JUSTDODGE_ASSETS").unwrap_or_else(|_| "assets".to_string());

    let (c0_mesh, c0_walk_skins, hero_strike) = if journey_limit.is_some() {
        eprintln!(
            "LIFECYCLE_QA_PRESENTATION=QUARANTINED authority=none promotion=false source=procedural"
        );
        let mesh = asset::lifecycle_qa_mesh();
        let reference_local: Vec<Mat4> = mesh.bones.iter().map(|bone| bone.rest_local).collect();
        let reference_skin = asset::reference_pose_skin_matrices(&mesh, &reference_local)
            .expect("lifecycle QA carrier bind pose must be valid");
        let presentation = hero_strike::HeroStrikePresentation::lifecycle_qa(&mesh)
            .expect("lifecycle QA presentation must be valid");
        (mesh, vec![reference_skin], presentation)
    } else {
        let c0_skin_path = std::env::var("JUST_DODGE_C0_SKIN").unwrap_or_else(|_| {
            format!("{assets}/source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin")
        });
        let mesh = asset::load_skinned(&c0_skin_path).expect("C0 armored duelist required");
        assert_eq!(mesh.bones.len(), 24, "C0 armored duelist bone contract");
        let source = asset::load_skinned(&format!(
            "{assets}/source/meshy/c0_base_fighter/rigged_001/cooked/c0_skin8.bin"
        ))
        .expect("C0 source rig required for staging and radial Move");
        let walk = asset::load_skeletal_animation(&format!(
            "{assets}/source/meshy/c0_base_fighter/rigged_001/cooked/walking.anim"
        ))
        .expect("C0 world-space walking clip required for radial Move");
        let walk_skins = walk
            .frames
            .iter()
            .map(|frame| asset::retarget_world_animation_frame(&source, &mesh, frame))
            .collect::<std::io::Result<Vec<_>>>()
            .expect("C0 world-space walking clip must retarget without geometry explosion");
        let presentation =
            hero_strike::HeroStrikePresentation::load(&PathBuf::from(&assets), &mesh)
                .expect("PVP005-R6 hero Strike must load before live match start");
        (mesh, walk_skins, presentation)
    };
    let c0_reference_local: Vec<Mat4> = c0_mesh.bones.iter().map(|bone| bone.rest_local).collect();
    let c0_reference_skin = asset::reference_pose_skin_matrices(&c0_mesh, &c0_reference_local)
        .expect("C0 carrier bind pose must produce valid skinning matrices");
    let lifecycle_qa_mesh = if journey_limit.is_some() {
        Some(c0_mesh)
    } else {
        None
    };
    let dodge_presentation = None;
    let initial_seed = 0x4D33_0000_0000_0000;
    let (session, cleanbox_world, ai) = fresh_match_authorities(initial_seed);
    let motion_lab_truth_baseline = motion_lab_enabled.then(|| session.game.snapshot().clone());
    if motion_lab_enabled {
        let metrics = hero_strike.motion_lab_metrics(motion_lab_frame);
        eprintln!(
            "MOTION_FRONTIER_LAB_START frame={} max_target_error_m={:.9} mean_target_error_m={:.9} planted_foot_drift_m={:.9} grip_error_m={:.9} truth_frame={} requested=unavailable ardy=unavailable target=available tracker=available runtime_admission=false",
            motion_lab_frame,
            metrics.max_target_error_m,
            metrics.mean_target_error_m,
            metrics.planted_foot_drift_m,
            metrics.grip_error_m,
            session.game.snapshot().frame,
        );
    }

    let event_loop = EventLoop::new().unwrap();
    let mut app = App {
        window: None,
        surface: None,
        device: None,
        queue: None,
        config: None,
        renderer: None,
        ui_renderer: None,
        runtime_assets: PathBuf::from(assets),
        lifecycle_qa_mesh,
        camera: Camera::new(),
        development_camera: if motion_lab_enabled {
            DevelopmentCamera::LeftQuarter
        } else {
            DevelopmentCamera::FirstPerson
        },
        start_time: Instant::now(),
        last_frame_time: Instant::now(),
        fixed_step_clock: FixedStepClock::default(),
        input: input::InputState::default(),
        clip_fps: 30.0,
        first_frame_presented: false,
        c0_reference_skin,
        c0_walk_skins,
        hero_strike,
        motion_frontier_lab: motion_lab_enabled.then(|| {
            let mut lab = motion_frontier_lab::MotionFrontierLab::new(motion_lab_frame);
            if motion_lab_context {
                lab.toggle_presentation();
            }
            lab
        }),
        motion_lab_truth_baseline,
        dodge_presentation,
        session,
        cleanbox_world,
        ai,
        flow: if autoplay {
            runtime_flow::RuntimeFlow::autoplay()
        } else {
            runtime_flow::RuntimeFlow::menu()
        },
        cursor_captured: false,
        replay_saved: false,
        replay_verified: false,
        autoplay,
        verify,
        journey_limit,
        journeys_completed: 0,
        telemetry: telemetry::Telemetry::new(telemetry_enabled),
        player_pos: vec3(0.0, 0.0, 1.0),
        show_debug: false,
        show_hud: true,
        window_size,
        benchmark_frame_limit,
        benchmark_frame_ms: Vec::new(),
    };
    if telemetry_enabled {
        eprintln!("telemetry: writing to /tmp/just_dodge_tlm.jsonl");
    }
    event_loop.run_app(&mut app).unwrap();
}
