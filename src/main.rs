#![allow(dead_code)]

use glam::{Mat4, Vec3, vec3};
use std::sync::Arc;
use std::sync::mpsc::{self, Receiver, TryRecvError};
use std::thread;
use std::time::Instant;
use winit::application::ApplicationHandler;
use winit::dpi::LogicalSize;
use winit::event::{ElementState, MouseButton, MouseScrollDelta, WindowEvent};
use winit::event_loop::{ActiveEventLoop, EventLoop};
use winit::keyboard::Key;
use winit::window::{Window, WindowId};

mod asset;
mod combat;
mod input;
mod motion;
mod renderer;
mod retarget;
mod skeleton;
mod telemetry;

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
            phi: 1.0, // look slightly down at the upright mannequin
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
    camera: Camera,
    start_time: Instant,
    input: input::InputState,
    // MotionBricks-driven skinning clip (24 joint matrices per frame)
    clip_frames: Vec<[Mat4; 24]>,
    clip_fps: f32,
    clip_rx: Option<Receiver<Vec<[Mat4; 24]>>>,
    // Staged startup: present a clear frame before loading the heavy scene
    first_frame_presented: bool,
    motion_started: bool,
    // Combat state
    opponent_attack_timer: f32,
    opponent_attack_active: bool,
    opponent_attack_windup_end: f32,
    opponent_attack_duration: f32,
    player_distance: f32,
    combat_log: Vec<String>,
    // Telemetry + locomotion
    telemetry: telemetry::Telemetry,
    player_pos: Vec3,
    show_debug_bones: bool,
}

impl ApplicationHandler for App {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        eprintln!("main: resumed enter");

        let window = Arc::new(
            event_loop
                .create_window(
                    Window::default_attributes()
                        .with_title("Just Dodge — Arena")
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
        // resumed() returns NOW — no Renderer::new(), no ONNX.
    }

    fn about_to_wait(&mut self, _event_loop: &ActiveEventLoop) {
        // Poll MotionBricks result if a worker thread is active.
        if let Some(rx) = &self.clip_rx {
            match rx.try_recv() {
                Ok(clip) => {
                    if !clip.is_empty() {
                        eprintln!("main: MotionBricks clip received: {} frames", clip.len());
                        self.clip_frames = clip;
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
                eprintln!("main: renderer init done");
            }

            // NOTE: MotionBricks worker + skinned mannequin are deferred until
            // the ground/sky baseline is verified. No ONNX thread spawned yet.

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
                // Reconfigure the wgpu surface and the renderer's depth buffer
                // when the window size changes.
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
                    wgpu::CurrentSurfaceTexture::Occluded
                    | wgpu::CurrentSurfaceTexture::Timeout => Err("occluded"),
                    wgpu::CurrentSurfaceTexture::Outdated | wgpu::CurrentSurfaceTexture::Lost => {
                        surface.configure(device, config);
                        Err("outdated")
                    }
                    wgpu::CurrentSurfaceTexture::Validation => Err("validation"),
                })() else {
                    // Skip this frame; about_to_wait will request a retry.
                    return;
                };

                let view = surface_texture
                    .texture
                    .create_view(&wgpu::TextureViewDescriptor::default());

                if let Some(renderer) = self.renderer.as_mut() {
                    // --- Full render pass (arena + skinned mannequin) ---
                    let aspect = config.width as f32 / config.height as f32;
                    let proj_view = self.camera.proj_view(aspect);

                    for obj in renderer.objects.iter() {
                        let mvp = proj_view * obj.model;
                        queue.write_buffer(&obj.uniform_buffer, 0, bytemuck::bytes_of(&[mvp]));
                    }
                    // Player locomotion from WASD input
                    let speed = 1.5; // m/s
                    let dt = 1.0 / self.clip_fps;
                    if self.input.forward { self.player_pos.z -= speed * dt; }
                    if self.input.back { self.player_pos.z += speed * dt; }
                    if self.input.left { self.player_pos.x -= speed * dt; }
                    if self.input.right { self.player_pos.x += speed * dt; }
                    // Write per-actor MVPs
                    let player_mvp = proj_view * Mat4::from_translation(self.player_pos);
                    queue.write_buffer(&renderer.skinned[0].uniform_buffer, 0, bytemuck::bytes_of(&[player_mvp]));
                    // Opponent: static position at z=-1
                    let opp_mvp = proj_view * renderer.skinned[1].model;
                    queue.write_buffer(&renderer.skinned[1].uniform_buffer, 0, bytemuck::bytes_of(&[opp_mvp]));

                    if !self.clip_frames.is_empty() {
                        let elapsed = self.start_time.elapsed().as_secs_f32();
                        let fc = self.clip_frames.len();
                        let fi = (elapsed * self.clip_fps) as usize % fc;
                        // Player: current frame
                        renderer.update_skin_joints_indexed(queue, 0, &self.clip_frames[fi]);
                        // Opponent: half-cycle phase shift for visual distinction
                        let opp_fi = (fi + fc / 2) % fc;
                        renderer.update_skin_joints_indexed(queue, 1, &self.clip_frames[opp_fi]);

                        // Debug bone overlay (F1 toggle)
                        if self.show_debug_bones {
                            renderer.update_debug_bones(device, queue, &self.clip_frames[fi]);
                        }

                        // Combat intent log
                        let intent = self.input.intent();
                        if intent != input::PlayerIntent::Idle {
                            eprintln!("[{:5.1}s] Intent: {:?}", elapsed, intent);
                        }
                        self.input.reset_deltas();

                        // --- Opponent attack timer & hit resolution ---
                        // Player model at z=+1, opponent at z=-1 → ~2m apart.
                        // Approximate pelvis distance as combat range.
                        self.player_distance = 2.0; // fixed for now (models are static)
                        if !self.opponent_attack_active {
                            // Start new attack every 3 seconds
                            self.opponent_attack_timer += 1.0 / self.clip_fps;
                            if self.opponent_attack_timer >= 3.0 {
                                self.opponent_attack_active = true;
                                self.opponent_attack_timer = 0.0;
                                self.opponent_attack_windup_end = elapsed + 0.5;
                                eprintln!("[{}s] OPPONENT: strike windup (0.5s)", elapsed as u32);
                            }
                        } else {
                            let attack_elapsed = elapsed - (self.opponent_attack_windup_end - 0.5);
                            if attack_elapsed >= self.opponent_attack_duration {
                                // Attack resolved at end of active window
                                let hit = self.player_distance < 1.5;
                                let zone = if hit { "Torso" } else { "WHIFF" };
                                let msg = format!("[{:5.1}s] COMBAT: {}  dist={:.2}m", elapsed, zone, self.player_distance);
                                eprintln!("{}", msg);
                                self.combat_log.push(msg);
                                self.opponent_attack_active = false;
                            }
                        }
                        // Emit telemetry
                        let phase = if self.opponent_attack_active {
                            if elapsed < self.opponent_attack_windup_end { "Telegraph" } else { "Active" }
                        } else { "Idle" };
                        let combat = self.combat_log.last().cloned();
                        self.telemetry.emit(&telemetry::TelemetryFrame {
                            t: elapsed,
                            player_pos: self.player_pos.to_array(),
                            player_intent: format!("{:?}", intent),
                            opponent_phase: phase.to_string(),
                            combat_result: combat,
                            clip_frame: fi,
                        });
                    }

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
                            depth_stencil_attachment: Some(
                                wgpu::RenderPassDepthStencilAttachment {
                                    view: &renderer.depth_view,
                                    depth_ops: Some(wgpu::Operations {
                                        load: wgpu::LoadOp::Clear(1.0),
                                        store: wgpu::StoreOp::Store,
                                    }),
                                    stencil_ops: None,
                                },
                            ),
                            timestamp_writes: None,
                            multiview_mask: None,
                            occlusion_query_set: None,
                        });
                        renderer.render(&mut rpass);
                        renderer.render_skinned(&mut rpass);
                        if self.show_debug_bones {
                            renderer.render_debug_overlay(&mut rpass);
                        }
                    }
                    queue.submit(std::iter::once(encoder.finish()));
                } else {
                    // --- Fallback clear frame: present a solid color so the
                    //     Wayland compositor maps the window before heavy init ---
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

            WindowEvent::KeyboardInput { event, .. } => {
                self.input.handle_key(&event);
                if event.state == ElementState::Pressed {
                    if let Key::Character(c) = &event.logical_key {
                        if c.as_str() == "r" {
                            self.camera = Camera::new();
                            eprintln!("Camera reset");
                        }
                        if c.as_str() == "f1" {
                            self.show_debug_bones = !self.show_debug_bones;
                            eprintln!("debug bones: {}", self.show_debug_bones);
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
}

/// Run the real MotionBricks VQVAE encoder+decoder on a synthetic idle seed and
/// return retargeted 24-bone skinning matrices per frame. The decoded motion
/// (not the seed) drives the skeleton.
fn build_motionbricks_clip() -> Vec<[Mat4; 24]> {
    let assets = std::env::var("JUSTDODGE_ASSETS").unwrap_or_else(|_| "assets".to_string());
    let mesh = match asset::load_skinned(&format!("{}/characters/mannequin_male.bin", assets)) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("Skinned mesh load failed: {e}");
            return Vec::new();
        }
    };
    let mut pipe = match motion::MotionPipeline::new(&assets) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("MotionBricks init failed: {e}");
            return Vec::new();
        }
    };
    let t = 40usize; // ~1.3s clip at 30fps
    let enc_in = pipe.build_idle_encoder_input(t);
    let g1_frames = match pipe.decode_encoder_input(&enc_in, t) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("MotionBricks decode failed: {e}");
            return Vec::new();
        }
    };
    g1_frames
        .iter()
        .map(|g1| asset::compute_skin_matrices(g1, &mesh))
        .collect()
}

fn main() {
    let telemetry_enabled = std::env::args().any(|a| a == "--telemetry");

    let event_loop = EventLoop::new().unwrap();
    let mut app = App {
        window: None,
        surface: None,
        device: None,
        queue: None,
        config: None,
        renderer: None,
        camera: Camera::new(),
        start_time: Instant::now(),
        input: input::InputState::default(),
        clip_frames: vec![[Mat4::IDENTITY; 24]],
        clip_fps: 30.0,
        clip_rx: None,
        first_frame_presented: false,
        motion_started: false,
        opponent_attack_timer: 0.0,
        opponent_attack_active: false,
        opponent_attack_windup_end: 0.0,
        opponent_attack_duration: 1.5,
        player_distance: 2.0,
        combat_log: Vec::new(),
        telemetry: telemetry::Telemetry::new(telemetry_enabled),
        player_pos: vec3(0.0, 0.0, 1.0),
        show_debug_bones: false,
    };
    if telemetry_enabled {
        eprintln!("telemetry: writing to /tmp/just_dodge_tlm.jsonl");
    }
    // Initial clip: bind pose (identity skinning matrices).
    // MotionBricks will replace this with animated frames when ready.
    app.clip_frames = vec![[Mat4::IDENTITY; 24]];
    event_loop.run_app(&mut app).unwrap();
}
