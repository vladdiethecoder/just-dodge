#![allow(dead_code)]

use glam::{Mat4, Vec3, vec3};
use just_dodge::{m3_cleanbox, milestone3 as m3};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use winit::application::ApplicationHandler;
use winit::dpi::LogicalSize;
use winit::event::{ElementState, WindowEvent};
use winit::event_loop::{ActiveEventLoop, EventLoop};
use winit::keyboard::Key;
use winit::window::{Window, WindowId};

mod action_matrix;
mod ai;
mod armor;
mod asset;
mod cleanbox;
mod combat;
mod dodge_presentation;
mod duel_physics;
mod duel_world;
mod hitbox;
mod injury;
mod input;
mod motion;
mod motion_service;
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
        let eye = self.eye(player_root);
        let view = Mat4::look_at_lh(eye, eye + self.forward(), Vec3::Y);
        let proj = Mat4::perspective_lh(FIRST_PERSON_FOV_Y_RAD, aspect, 0.1, 100.0);
        proj * view
    }
}

struct App {
    window: Option<Arc<Window>>,
    surface: Option<wgpu::Surface<'static>>,
    device: Option<wgpu::Device>,
    queue: Option<wgpu::Queue>,
    config: Option<wgpu::SurfaceConfiguration>,
    renderer: Option<renderer::Renderer>,
    ui_renderer: Option<ui::UiRenderer>,
    camera: Camera,
    start_time: Instant,
    last_frame_time: Instant,
    fixed_step_clock: FixedStepClock,
    input: input::InputState,
    clip_fps: f32,
    first_frame_presented: bool,
    /// C0 reference-pose skinning matrices. Raw generated motion remains
    /// rejected until combat-close supplies source-valid clips.
    c0_reference_skin: Vec<Mat4>,
    /// Optional local-only C0 Dodge presentation. It cannot affect truth.
    dodge_presentation: Option<dodge_presentation::DodgePresentation>,
    // Canonical Milestone 3 simulation; rendering only consumes snapshots.
    session: m3::Session,
    cleanbox_world: m3_cleanbox::M3CleanboxWorld,
    ai: m3::SeededAi,
    replay_saved: bool,
    /// QA-only deterministic driver. It uses the same input/session path as
    /// keyboard selection; it is never the default launch mode.
    autoplay: bool,
    // Telemetry + locomotion
    telemetry: telemetry::Telemetry,
    player_pos: Vec3,
    show_debug: bool,
}

impl ApplicationHandler for App {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        eprintln!("main: resumed enter");

        let window = Arc::new(
            event_loop
                .create_window(
                    Window::default_attributes()
                        .with_title("Just Dodge — 3-Action Prototype")
                        .with_inner_size(LogicalSize::new(1280.0, 720.0)),
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
                self.renderer = Some(renderer::Renderer::new(device, queue, config, false));
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
            WindowEvent::CloseRequested => event_loop.exit(),

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
                if let Some((dx, dy)) = self.camera.record_mouse_position((position.x, position.y))
                {
                    self.input.handle_mouse_motion(dx, dy);
                }
            }

            WindowEvent::MouseWheel { delta, .. } => {
                self.input.handle_scroll(&delta);
            }

            WindowEvent::RedrawRequested => {
                self.render_frame();
            }

            WindowEvent::KeyboardInput { event, .. } => {
                self.input.handle_key(&event);
                if event.state == ElementState::Pressed {
                    if let Key::Character(c) = &event.logical_key {
                        if c.as_str() == "r" {
                            self.camera.reset();
                            if self.session.game.snapshot().phase == m3::Phase::MatchResult {
                                let next_seed = self.session.game.snapshot().seed.wrapping_add(1);
                                self.session
                                    .apply(m3::Side::Player, m3::Input::Restart { seed: next_seed })
                                    .expect("restart is valid from MatchResult");
                                self.replay_saved = false;
                                self.input.reset_plan();
                                eprintln!("Milestone 3 match restarted with seed {next_seed}");
                            } else {
                                eprintln!("First-person camera reset");
                            }
                        }
                    }
                }
            }

            _ => {}
        }
    }
}

impl App {
    fn combat_update(
        &mut self,
    ) -> Option<(
        m3::Snapshot,
        input::PlanInput,
        Vec<Mat4>,
        Vec<Mat4>,
        f32,
        input::PlayerIntent,
    )> {
        if self.renderer.is_none() {
            return None;
        }

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

        if self.session.game.snapshot().phase == m3::Phase::Plan {
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
                }
                if (self.autoplay || plan.confirmed) && player_action.is_some() {
                    self.session
                        .apply(m3::Side::Player, m3::Input::Commit)
                        .expect("selected player action commits exactly once");
                } else if plan.confirmed {
                    eprintln!("select Strike, Block, or Grab before committing");
                }
            }
            if !snap.opponent.committed {
                let action = self.ai.choose(snap.exchange);
                self.session
                    .apply(m3::Side::Opponent, m3::Input::Select(action))
                    .expect("seeded AI Plan selection is valid");
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
            self.cleanbox_world
                .submit_resolve_packet(&mut self.session, self.player_pos, vec3(0.0, 0.0, -1.0))
                .expect("M3 Resolve cleanbox packet must be valid");
            self.session.tick();
        }

        let snapshot = self.session.game.snapshot().clone();

        // Save replay once on match end.
        if snapshot.phase == m3::Phase::MatchResult && !self.replay_saved {
            self.save_replay();
            self.replay_saved = true;
        }

        let (player_joints, opponent_joints) = self.current_pose(&snapshot);
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

        let frame = surface.get_current_texture();
        let Ok(surface_texture) = (|| match frame {
            wgpu::CurrentSurfaceTexture::Success(t) => Ok(t),
            wgpu::CurrentSurfaceTexture::Suboptimal(t) => Ok(t),
            wgpu::CurrentSurfaceTexture::Occluded | wgpu::CurrentSurfaceTexture::Timeout => {
                Err("occluded")
            }
            wgpu::CurrentSurfaceTexture::Outdated | wgpu::CurrentSurfaceTexture::Lost => {
                surface.configure(device, config);
                Err("outdated")
            }
            wgpu::CurrentSurfaceTexture::Validation => Err("validation"),
        })() else {
            return;
        };

        let view = surface_texture
            .texture
            .create_view(&wgpu::TextureViewDescriptor::default());

        if self.renderer.is_some() {
            let (snapshot, plan, player_joints, opponent_joints, _elapsed, _intent) =
                combat.unwrap();

            let aspect = config.width as f32 / config.height as f32;
            let proj_view = self.camera.proj_view(aspect, self.player_pos);

            // --- Now borrow renderer and queue for GPU work ---
            let renderer = self.renderer.as_mut().unwrap();
            renderer.upload_debug_mvp(queue, &proj_view);

            for obj in renderer.objects.iter() {
                let mvp = proj_view * obj.model;
                queue.write_buffer(&obj.uniform_buffer, 0, bytemuck::bytes_of(&[mvp]));
            }
            let correct_model = renderer::skinned_correct_model();

            let player_model = Mat4::from_translation(self.player_pos) * correct_model;
            renderer.skinned[0].model = player_model;
            queue.write_buffer(
                &renderer.skinned[0].uniform_buffer,
                0,
                bytemuck::bytes_of(&[proj_view * player_model]),
            );

            let weapon_model = renderer::first_person_weapon_model(
                self.camera.eye(self.player_pos),
                self.camera.forward(),
            ) * action_weapon_presentation(&snapshot);
            renderer.update_first_person_weapon(queue, &proj_view, weapon_model);

            let opp_model = Mat4::from_translation(vec3(0.0, 0.0, -1.0)) * correct_model;
            renderer.skinned[1].model = opp_model;
            queue.write_buffer(
                &renderer.skinned[1].uniform_buffer,
                0,
                bytemuck::bytes_of(&[proj_view * opp_model]),
            );

            // --- Animation pose ---
            renderer.update_skin_joints_indexed(queue, 0, &player_joints);
            renderer.update_skin_joints_indexed(queue, 1, &opponent_joints);

            if self.show_debug {
                renderer.update_debug_bones(device, &player_joints);
            }

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
                                r: 0.55,
                                g: 0.70,
                                b: 0.92,
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
                renderer.render(&mut rpass);
                renderer.render_first_person_weapon(&mut rpass);
                renderer.render_skinned_from(&mut rpass, 1);
                if self.show_debug {
                    renderer.render_debug_overlay(&mut rpass);
                    renderer.render_hitbox_debug(&mut rpass);
                }
            }

            // UI pass: separate render pass so it draws over everything without depth.
            if let Some(ui_renderer) = self.ui_renderer.as_mut() {
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
                    &snapshot,
                    &plan,
                    queue,
                    config.width,
                    config.height,
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

    fn current_pose(&self, _snapshot: &m3::Snapshot) -> (Vec<Mat4>, Vec<Mat4>) {
        // The admitted source clip failed the ordered raw-source and C0 human
        // visual gates. Keep its optional local loader available for QA, but do
        // not promote any source-derived pose into the runtime until a source
        // selection unit proves readable Dodge semantics before C0 admission.
        (
            self.c0_reference_skin.clone(),
            self.c0_reference_skin.clone(),
        )
    }

    fn save_replay(&self) {
        let ts = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let path = PathBuf::from(format!("/tmp/just_dodge_m3_replay_{}.ron", ts));
        match self.session.replay.save(&path) {
            Ok(_) => eprintln!("Replay saved to {}", path.display()),
            Err(e) => eprintln!("Failed to save replay: {}", e),
        }
    }
}

fn opponent_dodge_presentation_tick(snapshot: &truth::TruthSnapshot) -> Option<u32> {
    if snapshot.opponent.action != Some(truth::Action::Dodge) {
        return None;
    }
    dodge_phase_tick(snapshot.phase, snapshot.phase_frame)
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
    }
}

/// Visual-only first-person weapon response. The simulation never reads this
/// transform: it is driven from a read-only canonical snapshot after replay
/// input and truth advancement have already happened.
fn action_weapon_presentation(snapshot: &m3::Snapshot) -> Mat4 {
    let action = snapshot
        .revealed
        .map(|(player, _)| player)
        .or(snapshot.player.planned);
    let active = matches!(
        snapshot.phase,
        m3::Phase::Commit | m3::Phase::Reveal | m3::Phase::Resolve
    );
    if !active {
        return Mat4::IDENTITY;
    }
    match action {
        Some(m3::Action::Strike) => {
            Mat4::from_translation(vec3(0.0, 0.06, -0.42)) * Mat4::from_rotation_x(-0.28)
        }
        Some(m3::Action::Block) => {
            Mat4::from_translation(vec3(-0.10, 0.24, -0.12)) * Mat4::from_rotation_z(0.35)
        }
        Some(m3::Action::Grab) => {
            Mat4::from_translation(vec3(-0.16, -0.10, -0.20)) * Mat4::from_rotation_y(-0.32)
        }
        None => Mat4::IDENTITY,
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

    let telemetry_enabled = arguments.iter().any(|argument| argument == "--telemetry");
    let autoplay = arguments.iter().any(|argument| argument == "--autoplay");
    let assets = std::env::var("JUSTDODGE_ASSETS").unwrap_or_else(|_| "assets".to_string());

    let c0_skin_path = std::env::var("JUST_DODGE_C0_SKIN").unwrap_or_else(|_| {
        format!("{assets}/source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin")
    });
    let c0_mesh = asset::load_skinned(&c0_skin_path).expect("C0 armored duelist required");
    assert_eq!(c0_mesh.bones.len(), 24, "C0 armored duelist bone contract");
    let c0_reference_local: Vec<Mat4> = c0_mesh.bones.iter().map(|bone| bone.rest_local).collect();
    let c0_reference_skin = asset::reference_pose_skin_matrices(&c0_mesh, &c0_reference_local)
        .expect("C0 armored duelist bind pose must produce valid skinning matrices");
    let dodge_presentation = None;

    let event_loop = EventLoop::new().unwrap();
    let mut app = App {
        window: None,
        surface: None,
        device: None,
        queue: None,
        config: None,
        renderer: None,
        ui_renderer: None,
        camera: Camera::new(),
        start_time: Instant::now(),
        last_frame_time: Instant::now(),
        fixed_step_clock: FixedStepClock::default(),
        input: input::InputState::default(),
        clip_fps: 30.0,
        first_frame_presented: false,
        c0_reference_skin,
        dodge_presentation,
        session: m3::Session::new(0x4D33_0000_0000_0000),
        cleanbox_world: m3_cleanbox::M3CleanboxWorld::new(),
        ai: m3::SeededAi::new(0x4D33_0000_0000_0000),
        replay_saved: false,
        autoplay,
        telemetry: telemetry::Telemetry::new(telemetry_enabled),
        player_pos: vec3(0.0, 0.0, 1.0),
        show_debug: false,
    };
    if telemetry_enabled {
        eprintln!("telemetry: writing to /tmp/just_dodge_tlm.jsonl");
    }
    event_loop.run_app(&mut app).unwrap();
}
