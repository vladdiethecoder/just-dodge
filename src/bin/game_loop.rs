//! Game-first debug-mannequin loop.
//!
//! The renderer is deliberately presentation-only: `PlanPhase` owns fixed-point
//! roots, action timing, contact, clinch, air state, and the displayed hash.
//! Run `cargo run --locked --bin game_loop` for the window or use
//! `--smoke N` for a deterministic, headless truth-only receipt.

use std::{
    sync::Arc,
    time::{Duration, Instant},
};

use glam::{Mat4, Quat, Vec3, Vec3Swizzles, vec3};
use just_dodge::{
    asset::{self, SkeletalAnimation, SkinnedMeshData},
    intent::{Intent, MoveDirection, PlanPhase, PlanSnapshot, PlanStatus, StrikeVariant},
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
        Self {
            walk_skins: animation_skins(&mesh, &walk),
            run_skins: animation_skins(&mesh, &run),
            mesh,
            reference_skin,
        }
    }

    fn skin_for(&self, intent: Option<Intent>, truth_frame: u64) -> Vec<Mat4> {
        match intent {
            Some(Intent::Move { .. }) => sample_skin(&self.walk_skins, truth_frame)
                .unwrap_or_else(|| self.reference_skin.clone()),
            Some(Intent::Dodge { .. }) => sample_skin(&self.run_skins, truth_frame)
                .unwrap_or_else(|| self.reference_skin.clone()),
            Some(intent) => placeholder_skin(&self.mesh, intent),
            None => self.reference_skin.clone(),
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
        Intent::Idle | Intent::Move { .. } | Intent::Dodge { .. } => {}
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

fn scripted_opponent(phase_number: u64) -> Intent {
    use MoveDirection::{Approach, CircleClockwise, LateralLeft, Retreat};
    match phase_number % 8 {
        0 | 4 => Intent::move_standard(Approach),
        1 => Intent::move_standard(LateralLeft),
        2 => Intent::Block,
        3 => Intent::Strike {
            variant: StrikeVariant::Thrust,
        },
        5 => Intent::Dodge {
            dir: CircleClockwise,
        },
        6 => Intent::move_standard(Retreat),
        _ => Intent::Strike {
            variant: StrikeVariant::Slash,
        },
    }
}

fn lock_next_phase(phase: &mut PlanPhase, player: Intent, opponent_phase: u64) {
    if phase.status() != PlanStatus::Planning {
        return;
    }
    let opponent = scripted_opponent(opponent_phase);
    let _ = phase.submit_intent(Side::Player, player);
    let _ = phase.submit_intent(Side::Opponent, opponent);
    // A speculative Grab can be correctly re-prompted by M1. The presentation
    // loop keeps running by deterministically selecting Idle rather than faking
    // a whiff or mutating authority state.
    if phase.status() == PlanStatus::Planning {
        let _ = phase.submit_intent(Side::Player, Intent::Idle);
        let _ = phase.submit_intent(Side::Opponent, Intent::Idle);
    }
}

fn run_smoke(ticks: u64) {
    let mut phase = PlanPhase::new();
    let mut player_phase = 0_u64;
    for _ in 0..ticks {
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
        );
        phase
            .step_truth_tick()
            .expect("smoke must always advance an M1 truth tick");
        if phase.status() == PlanStatus::Planning {
            player_phase = player_phase.saturating_add(1);
        }
    }
    let snapshot = phase.snapshot();
    println!(
        "GAME_LOOP_SMOKE ticks={ticks} truth_frame={} truth_hash={:016x}",
        snapshot.truth_frame,
        phase.truth_hash()
    );
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
    phase: PlanPhase,
    selected: Intent,
    opponent_phase: u64,
    next_truth: Instant,
    camera: CameraMode,
    observer_yaw: f32,
    show_skeleton: bool,
    show_dev: bool,
    first_frame_presented: bool,
}

impl GameLoopApp {
    fn new(assets_root: String) -> Self {
        Self {
            assets_root,
            window: None,
            surface: None,
            device: None,
            queue: None,
            config: None,
            renderer: None,
            presentation: None,
            phase: PlanPhase::new(),
            selected: Intent::Idle,
            opponent_phase: 0,
            next_truth: Instant::now(),
            camera: CameraMode::FirstPerson,
            observer_yaw: 0.0,
            show_skeleton: true,
            show_dev: false,
            first_frame_presented: false,
        }
    }

    fn advance_truth(&mut self) {
        let now = Instant::now();
        let mut stepped = 0_u8;
        while now >= self.next_truth && stepped < 4 {
            lock_next_phase(&mut self.phase, self.selected, self.opponent_phase);
            self.phase
                .step_truth_tick()
                .expect("window loop must only step locked PlanPhase truth");
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
            _ => {}
        }
    }

    fn update_title(&self, snapshot: &PlanSnapshot) {
        let Some(window) = self.window.as_ref() else {
            return;
        };
        let title = if self.show_dev {
            format!(
                "Just Dodge M2 | DEV frame={} dist={:.2}m hash={:016x} contact={} OBB=ON",
                snapshot.truth_frame,
                planar_distance_m(snapshot),
                self.phase.truth_hash(),
                snapshot.last_contact_observed,
            )
        } else {
            format!(
                "Just Dodge M2 | {} | spacing {:.2}m | C camera B skeleton F3 dev",
                self.camera.label(),
                planar_distance_m(snapshot),
            )
        };
        window.set_title(&title);
    }

    fn render_frame(&mut self) {
        self.advance_truth();
        let snapshot = self.phase.snapshot();
        self.update_title(&snapshot);
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
        let player_skin = presentation.skin_for(snapshot.locked[0], snapshot.truth_frame);
        let opponent_skin = presentation.skin_for(snapshot.locked[1], snapshot.truth_frame);
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
        renderer.update_debug_segments(device, &marker_segments);
        let obb_lines = if self.show_dev {
            let mut lines = obb_proxy_lines(player_root);
            lines.extend(obb_proxy_lines(opponent_root));
            lines
        } else {
            Vec::new()
        };
        renderer.update_hitbox_debug(device, &obb_lines);
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
                false,
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

fn run_shot(ticks: u64, out_dir: &str) {
    // Drive the truth loop forward so the shot captures a mid-exchange pose.
    let mut phase = PlanPhase::new();
    let mut player_phase = 0_u64;
    for _ in 0..ticks {
        lock_next_phase(
            &mut phase,
            Intent::Strike {
                variant: StrikeVariant::Slash,
            },
            player_phase,
        );
        phase
            .step_truth_tick()
            .expect("shot must advance an M1 truth tick");
        if phase.status() == PlanStatus::Planning {
            player_phase = player_phase.saturating_add(1);
        }
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
        false,
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
    let player_skin = presentation.skin_for(snapshot.locked[0], snapshot.truth_frame);
    let opponent_skin = presentation.skin_for(snapshot.locked[1], snapshot.truth_frame);
    let aspect = w as f32 / h as f32;

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
        renderer.update_debug_segments(&device, &marker_segments);

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
