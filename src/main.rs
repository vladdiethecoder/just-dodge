#![allow(dead_code)]

use glam::{Mat4, Vec3, vec3};
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::mpsc::{self, Receiver, TryRecvError};
use std::thread;
use std::time::{Instant, SystemTime, UNIX_EPOCH};
use winit::application::ApplicationHandler;
use winit::dpi::LogicalSize;
use winit::event::{ElementState, MouseButton, MouseScrollDelta, WindowEvent};
use winit::event_loop::{ActiveEventLoop, EventLoop};
use winit::keyboard::Key;
use winit::window::{Window, WindowId};

mod action_matrix;
mod ai;
mod armor;
mod asset;
mod combat;
mod hitbox;
mod input;
mod injury;
mod motion;
mod motion_service;
mod renderer;
mod replay;
mod retarget;
mod skeleton;
mod telemetry;
mod truth;
mod ui;

struct Camera {
    theta: f32,
    phi: f32,
    radius: f32,
    dragging: bool,
    last_mouse: (f64, f64),
}

impl Camera {
    fn new() -> Self {
        Self {
            theta: 0.6,
            phi: 1.0,
            radius: 12.0,
            dragging: false,
            last_mouse: (0.0, 0.0),
        }
    }

    fn proj_view(&self, aspect: f32) -> Mat4 {
        let eye = vec3(
            self.radius * self.phi.sin() * self.theta.sin(),
            self.radius * self.phi.cos(),
            self.radius * self.phi.sin() * self.theta.cos(),
        );
        let view = Mat4::look_at_lh(eye, Vec3::ZERO, Vec3::Y);
        let proj = Mat4::perspective_lh(std::f32::consts::FRAC_PI_4, aspect, 0.1, 100.0);
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
    input: input::InputState,
    // Per-actor MotionBricks-driven skinning clips.
    actor_clips: Vec<Vec<[Mat4; 24]>>,
    clip_fps: f32,
    clip_rx: Option<Receiver<Vec<[Mat4; 24]>>>,
    first_frame_presented: bool,
    motion_started: bool,
    // Python MotionBrains bridge.
    motion_service: motion_service::MotionService,
    skinned_mesh: asset::SkinnedMeshData,
    neutral_g1_pose: [Mat4; 34],
    player_clip: Option<Vec<[Mat4; 24]>>,
    opponent_clip: Option<Vec<[Mat4; 24]>>,
    // Combat systems
    truth: truth::CombatTruth,
    ai: ai::AiController,
    replay: replay::ReplayRecorder,
    replay_saved: bool,
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
        // Poll MotionBricks result if a worker thread is active.
        if let Some(rx) = &self.clip_rx {
            match rx.try_recv() {
                Ok(clip) => {
                    if !clip.is_empty() {
                        eprintln!("main: MotionBricks clip received: {} frames", clip.len());
                        // Both actors share the idle clip; phase shift applied at render time.
                        self.actor_clips = vec![clip.clone(), clip];
                    }
                    self.clip_rx = None;
                    if let Some(w) = self.window.as_ref() {
                        w.request_redraw();
                    }
                }
                Err(TryRecvError::Empty) => { /* keep polling */ }
                Err(TryRecvError::Disconnected) => {
                    eprintln!("main: MotionBricks worker disconnected");
                    self.clip_rx = None;
                }
            }
        }

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
                self.renderer = Some(renderer::Renderer::new(device, queue, config));
                self.ui_renderer = Some(ui::UiRenderer::new(device, queue, config));
                eprintln!("main: renderer + UI init done");
            }

            if let Some(w) = self.window.as_ref() {
                w.request_redraw();
            }

            // Spawn MotionBricks after renderer is ready.
            if self.renderer.is_some() {
                self.spawn_motion_worker();
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
                if button == MouseButton::Left {
                    self.camera.dragging = state == ElementState::Pressed;
                }
            }

            WindowEvent::CursorMoved { position, .. } => {
                if self.camera.dragging {
                    let dx = position.x - self.camera.last_mouse.0;
                    let dy = position.y - self.camera.last_mouse.1;
                    self.camera.theta -= dx as f32 * 0.005;
                    self.camera.phi = (self.camera.phi - dy as f32 * 0.005)
                        .clamp(0.1, std::f32::consts::PI - 0.1);
                }
                self.camera.last_mouse = (position.x, position.y);
            }

            WindowEvent::MouseWheel { delta, .. } => {
                let scroll = match delta {
                    MouseScrollDelta::LineDelta(_, y) => y,
                    MouseScrollDelta::PixelDelta(p) => p.y as f32 * 0.1,
                };
                self.camera.radius = (self.camera.radius - scroll * 0.5).clamp(1.0, 20.0);
            }

            WindowEvent::RedrawRequested => {
                self.render_frame();
            }

            WindowEvent::KeyboardInput { event, .. } => {
                self.input.handle_key(&event);
                if event.state == ElementState::Pressed {
                    if let Key::Character(c) = &event.logical_key {
                        if c.as_str() == "r" {
                            self.camera = Camera::new();
                            eprintln!("Camera reset");
                        }
                    }
                }
            }

            _ => {}
        }
    }
}

impl App {
    fn spawn_motion_worker(&mut self) {
        if self.motion_started {
            return;
        }
        self.motion_started = true;
        eprintln!("main: spawning MotionBricks worker");
        let (tx, rx) = mpsc::channel();
        self.clip_rx = Some(rx);
        thread::spawn(move || {
            eprintln!("[MotionBricks worker] start");
            let started = Instant::now();
            let clip = build_motionbricks_clip();
            eprintln!(
                "[MotionBricks worker] done: {} frames in {:.2}s",
                clip.len(),
                started.elapsed().as_secs_f32()
            );
            let _ = tx.send(clip);
        });
    }

    fn render_frame(&mut self) {
        let Some(surface) = self.surface.as_ref() else { return };
        let Some(device) = self.device.as_ref() else { return };
        let Some(queue) = self.queue.as_ref() else { return };
        let Some(config) = self.config.as_ref() else { return };

        let frame = surface.get_current_texture();
        let Ok(surface_texture) = (|| match frame {
            wgpu::CurrentSurfaceTexture::Success(t) => Ok(t),
            wgpu::CurrentSurfaceTexture::Suboptimal(t) => Ok(t),
            wgpu::CurrentSurfaceTexture::Occluded
            | wgpu::CurrentSurfaceTexture::Timeout => Err("occluded"),
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
            // --- Fixed-step combat update (before borrowing renderer) ---
            let now = Instant::now();
            let real_dt = now.duration_since(self.last_frame_time).as_secs_f32();
            self.last_frame_time = now;

            // Presentation never mutates truth: read snapshot, apply inputs through truth API.
            let plan = self.input.plan_input();
            if plan.toggle_debug {
                self.show_debug = !self.show_debug;
                eprintln!("debug overlay: {}", self.show_debug);
            }

            if self.truth.phase() == truth::Phase::Plan {
                let snap = self.truth.snapshot().clone();
                if !snap.player.committed {
                    if let Some(action) = plan.selected_action {
                        self.truth.apply_input(
                            truth::Side::Player,
                            truth::PlayerInput::SelectAction(action),
                        );
                    }
                    if let Some(stance) = plan.selected_stance {
                        self.truth.apply_input(
                            truth::Side::Player,
                            truth::PlayerInput::SelectStance(stance),
                        );
                    }
                    if plan.confirmed {
                        self.truth.apply_input(truth::Side::Player, truth::PlayerInput::Commit);
                    }
                }
                if !snap.opponent.committed {
                    let ai_snap = ai_snapshot_from_truth(&snap, self.ai.side);
                    let commit = self.ai.select_action(&ai_snap);
                    self.truth.apply_input(
                        truth::Side::Opponent,
                        truth::PlayerInput::SelectAction(commit.action),
                    );
                    self.truth.apply_input(
                        truth::Side::Opponent,
                        truth::PlayerInput::SelectStance(commit.stance),
                    );
                    self.truth.apply_input(truth::Side::Opponent, truth::PlayerInput::Commit);
                }
            }
            self.input.reset_plan();

            // Step the authoritative truth at 60 Hz.
            self.truth.fixed_tick(real_dt);

            // Record snapshot and events for replay.
            let snapshot = self.truth.snapshot().clone();
            let replay_snap = replay::ReplaySnapshot {
                frame: snapshot.frame,
                phase: snapshot.phase.name().to_string(),
                player_health: (snapshot.player.health * 10.0).max(0.0) as u32,
                opponent_health: (snapshot.opponent.health * 10.0).max(0.0) as u32,
                player_stamina: (snapshot.player.stamina * 10.0).max(0.0) as u32,
                opponent_stamina: (snapshot.opponent.stamina * 10.0).max(0.0) as u32,
            };
            self.replay
                .record_frame(snapshot.frame, self.truth.truth_hash(), &replay_snap);

            // Save replay once on match end.
            if snapshot.match_over && !self.replay_saved {
                self.save_replay();
                self.replay_saved = true;
            }

            // Generate MotionBrains clips once both sides are committed and truth reveals.
            if snapshot.phase == truth::Phase::Reveal {
                if self.player_clip.is_none() {
                    if let Some(action) = snapshot.player.action {
                        let condition = motion::ActionCondition {
                            action: map_truth_action(action),
                            stance: map_truth_stance(snapshot.player.stance),
                            from_pose: self.neutral_g1_pose,
                        };
                        match motion::generate_action_clip(&condition, &self.motion_service) {
                            Ok(g1_clip) => {
                                self.player_clip = Some(
                                    g1_clip
                                        .iter()
                                        .map(|g1| asset::compute_skin_matrices(g1, &self.skinned_mesh))
                                        .collect(),
                                );
                                eprintln!("main: generated player Strike clip: {} frames", g1_clip.len());
                            }
                            Err(e) => {
                                eprintln!("main: failed to generate player clip: {e}");
                            }
                        }
                    }
                }
                if self.opponent_clip.is_none() {
                    if let Some(action) = snapshot.opponent.action {
                        let condition = motion::ActionCondition {
                            action: map_truth_action(action),
                            stance: map_truth_stance(snapshot.opponent.stance),
                            from_pose: self.neutral_g1_pose,
                        };
                        match motion::generate_action_clip(&condition, &self.motion_service) {
                            Ok(g1_clip) => {
                                self.opponent_clip = Some(
                                    g1_clip
                                        .iter()
                                        .map(|g1| asset::compute_skin_matrices(g1, &self.skinned_mesh))
                                        .collect(),
                                );
                                eprintln!("main: generated opponent clip: {} frames", g1_clip.len());
                            }
                            Err(e) => {
                                eprintln!("main: failed to generate opponent clip: {e}");
                            }
                        }
                    }
                }
            } else {
                // Clear combat clips when the exchange resolves so the next exchange regenerates.
                self.player_clip = None;
                self.opponent_clip = None;
            }

            let (player_joints, opponent_joints) = self.current_pose();
            let aspect = config.width as f32 / config.height as f32;
            let proj_view = self.camera.proj_view(aspect);
            let elapsed = self.start_time.elapsed().as_secs_f32();
            let intent = self.input.intent();

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

            let opp_model = Mat4::from_translation(vec3(0.0, 0.0, -1.0)) * correct_model;
            renderer.skinned[1].model = opp_model;
            queue.write_buffer(
                &renderer.skinned[1].uniform_buffer,
                0,
                bytemuck::bytes_of(&[proj_view * opp_model]),
            );

            // --- Animation pose ---
            // For the prototype, action clips from Agent 2 are not yet wired.
            // Render the idle clip for all phases (or bind pose if clip absent).
            renderer.update_skin_joints_indexed(queue, 0, &player_joints);
            renderer.update_skin_joints_indexed(queue, 1, &opponent_joints);

            if self.show_debug {
                renderer.update_debug_bones(device, queue, &player_joints);
                let proxies = hitbox::extract_body_proxies(&[player_joints]);
                let lines = hitbox::debug_lines(&proxies);
                renderer.update_hitbox_debug(device, &lines);
            }

            // --- Telemetry ---
            self.telemetry.emit(&telemetry::TelemetryFrame {
                t: elapsed,
                player_pos: self.player_pos.to_array(),
                player_intent: format!("{:?}", intent),
                opponent_phase: snapshot.phase.name().to_string(),
                combat_result: last_result_text(&snapshot),
                clip_frame: 0,
            });
            self.input.reset_deltas();

            // --- Render ---
            let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
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
                renderer.render_skinned(&mut rpass);
                if self.show_debug {
                    renderer.render_debug_overlay(&mut rpass);
                    renderer.render_hitbox_debug(&mut rpass);
                }
            }

            // UI pass: separate render pass so it draws over everything without depth.
            if let Some(ui_renderer) = self.ui_renderer.as_mut() {
                let plan = self.input.plan_input();
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
            let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
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

    fn current_pose(&self) -> ([Mat4; 24], [Mat4; 24]) {
        let identity = [Mat4::IDENTITY; 24];
        let elapsed = self.start_time.elapsed().as_secs_f32();
        let tick = (elapsed * self.clip_fps) as usize;

        // Prefer generated combat clips; fall back to idle clip (also MotionBrains-generated).
        let player = self
            .player_clip
            .as_ref()
            .and_then(|clip| {
                let fc = clip.len();
                if fc == 0 { None } else { Some(clip[tick % fc]) }
            })
            .or_else(|| {
                if self.actor_clips.len() >= 2 && !self.actor_clips[0].is_empty() {
                    Some(self.actor_clips[0][tick % self.actor_clips[0].len()])
                } else {
                    None
                }
            })
            .unwrap_or(identity);

        let opponent = self
            .opponent_clip
            .as_ref()
            .and_then(|clip| {
                let fc = clip.len();
                if fc == 0 { None } else { Some(clip[tick % fc]) }
            })
            .or_else(|| {
                if self.actor_clips.len() >= 2 && !self.actor_clips[1].is_empty() {
                    let fc = self.actor_clips[1].len();
                    Some(self.actor_clips[1][(tick + fc / 2) % fc])
                } else {
                    None
                }
            })
            .unwrap_or(identity);

        (player, opponent)
    }

    fn save_replay(&self) {
        let ts = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let path = PathBuf::from(format!("/tmp/just_dodge_replay_{}.jdrp", ts));
        match self.replay.save(&path) {
            Ok(_) => eprintln!("Replay saved to {}", path.display()),
            Err(e) => eprintln!("Failed to save replay: {}", e),
        }
    }
}

fn map_truth_action(action: truth::Action) -> motion::Action {
    match action {
        truth::Action::Strike => motion::Action::Strike,
        truth::Action::Block => motion::Action::Block,
        truth::Action::Grab => motion::Action::Grab,
    }
}

fn map_truth_stance(stance: truth::Stance) -> motion::Stance {
    match stance {
        truth::Stance::Top => motion::Stance::Top,
        truth::Stance::Left => motion::Stance::Left,
        truth::Stance::Right => motion::Stance::Right,
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
        let pa = snapshot.player.action.map(|a| format!("{:?}", a)).unwrap_or_default();
        let oa = snapshot.opponent.action.map(|a| format!("{:?}", a)).unwrap_or_default();
        format!("{} vs {}", pa, oa)
    })
}

/// Load MotionBricks-exported G1 frames from MB_CLIP env or assets/mb_idle.g1.
/// No fallbacks — game requires real motion data.
fn build_motionbricks_clip() -> Vec<[Mat4; 24]> {
    let assets = std::env::var("JUSTDODGE_ASSETS").unwrap_or_else(|_| "assets".to_string());
    let mesh = match asset::load_skinned(&format!("{}/characters/mannequin_male.bin", assets)) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("FATAL: Skinned mesh load failed: {e}");
            return Vec::new();
        }
    };

    let g1_path = std::env::var("MB_CLIP").unwrap_or_else(|_| format!("{}/mb_idle.g1", assets));
    match motion::load_g1_frames(&g1_path) {
        Ok(frames) => {
            eprintln!("[MotionBricks] loaded {} frames from {}", frames.len(), g1_path);
            frames.iter().map(|g1| asset::compute_skin_matrices(g1, &mesh)).collect()
        }
        Err(e) => {
            eprintln!(
                "FATAL: No animation clip found. Export from GR00T repo:\n  \
                 cd /run/media/vdubrov/Bulk-SSD/GR00T-WholeBodyControl/motionbricks && \\\n  \
                 DISPLAY=:0 python3 scripts/export_motion.py --style idle --output {}\n  \
                 Error: {e}",
                g1_path
            );
            Vec::new()
        }
    }
}

fn main() {
    let telemetry_enabled = std::env::args().any(|a| a == "--telemetry");
    let assets = std::env::var("JUSTDODGE_ASSETS").unwrap_or_else(|_| "assets".to_string());

    let motion_service = motion_service::MotionService::new().expect("MotionBrains service required");
    let skinned_mesh = asset::load_skinned(&format!("{}/characters/mannequin_male.bin", assets))
        .expect("required skinned mesh missing");
    let neutral_g1_pose = motion::load_g1_frames(&format!("{}/mb_idle.g1", assets))
        .map(|frames| frames[0])
        .unwrap_or([Mat4::IDENTITY; 34]);

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
        input: input::InputState::default(),
        actor_clips: vec![vec![[Mat4::IDENTITY; 24]], vec![[Mat4::IDENTITY; 24]]],
        clip_fps: 30.0,
        clip_rx: None,
        first_frame_presented: false,
        motion_started: false,
        motion_service,
        skinned_mesh,
        neutral_g1_pose,
        player_clip: None,
        opponent_clip: None,
        truth: truth::CombatTruth::new(),
        ai: ai::AiController::new(
            truth::Side::Opponent,
            ai::AiPersonality::default(),
            0x3A_C1_00_00_00_00_00_01,
        ),
        replay: replay::ReplayRecorder::new(0xDEAD_BEEF_CAFE_BABE),
        replay_saved: false,
        telemetry: telemetry::Telemetry::new(telemetry_enabled),
        player_pos: vec3(0.0, 0.0, 1.0),
        show_debug: false,
    };
    if telemetry_enabled {
        eprintln!("telemetry: writing to /tmp/just_dodge_tlm.jsonl");
    }
    event_loop.run_app(&mut app).unwrap();
}
