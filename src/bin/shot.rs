// Headless offscreen screenshot harness: renders a SINGLE mannequin in bind pose
// into an offscreen texture for high-contrast visual QA. Removes all arena clutter,
// keeps one model, and writes PNGs to qa_runs/ for deformity/artifact inspection.
// Run: cargo run --bin shot
use glam::{Mat4, Vec3, vec3};

#[path = "../asset.rs"]
mod asset;
#[path = "../dodge_presentation.rs"]
mod dodge_presentation;
#[path = "../renderer.rs"]
mod renderer;

struct View {
    name: &'static str,
    eye: Vec3,
    target: Vec3,
    up: Vec3,
}

fn percentile(data: &[f32], p: f32) -> f32 {
    if data.is_empty() {
        return 0.0;
    }
    let mut sorted: Vec<f32> = data.iter().copied().collect();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let idx = ((sorted.len() - 1) as f32 * p).round() as usize;
    sorted[idx.min(sorted.len() - 1)]
}

async fn run() {
    let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
        backends: wgpu::Backends::VULKAN,
        flags: wgpu::InstanceFlags::default(),
        memory_budget_thresholds: wgpu::MemoryBudgetThresholds::default(),
        backend_options: wgpu::BackendOptions::default(),
        display: None,
    });
    let adapter = instance
        .request_adapter(&wgpu::RequestAdapterOptions {
            compatible_surface: None,
            ..Default::default()
        })
        .await
        .expect("No adapter");
    let (device, queue) = adapter
        .request_device(&wgpu::DeviceDescriptor::default())
        .await
        .expect("No device");

    // High-resolution single-model focus render for visual QA/debugging.
    let (w, h) = (2048u32, 2048u32);
    let format = wgpu::TextureFormat::Rgba8UnormSrgb;

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

    let mut renderer = renderer::Renderer::new(&device, &queue, &config, false);
    let assets_dir = concat!(env!("CARGO_MANIFEST_DIR"), "/assets");

    // ─── C0 contract diagnostics ────────────────────────────────────
    let c0_root = format!("{assets_dir}/source/meshy/c0_base_fighter/pose_carrier_001/cooked");
    let c0_mesh = asset::load_skinned(&format!("{c0_root}/c0_pose_carrier.bin"))
        .expect("load C0 pose carrier");
    let c0_reference = asset::load_skeletal_animation(&format!("{c0_root}/c0_reference.anim"))
        .expect("load C0 reference action");
    assert_eq!(c0_mesh.bones.len(), 163);
    let c0_skin = asset::reference_pose_skin_matrices(&c0_mesh, &c0_reference.frames[0])
        .expect("C0 reference skinning");
    assert_eq!(c0_skin.len(), c0_mesh.bones.len());
    println!(
        "C0 CONTRACT: {} verts, {} indices, {} bones, {} reference matrices",
        c0_mesh.vertices.len(),
        c0_mesh.indices.len(),
        c0_mesh.bones.len(),
        c0_skin.len()
    );
    let dodge_presentation = std::env::var_os("JUST_DODGE_DODGE_F413").map(|path| {
        println!("shot: loading Dodge source {}", path.to_string_lossy());
        dodge_presentation::DodgePresentation::load(
            std::path::Path::new(&path),
            &c0_mesh,
            &c0_reference.frames[0],
        )
        .expect("JUST_DODGE_DODGE_F413 must be a validated local [N,413] source stream")
    });
    let dodge_tick = std::env::var("JUST_DODGE_DODGE_TICK").ok().map(|value| {
        value
            .parse::<u32>()
            .expect("JUST_DODGE_DODGE_TICK must be an unsigned presentation tick")
    });
    let full_body_dodge_skin = dodge_tick.map(|tick| {
        println!("shot: rendering full-body Dodge presentation tick {tick}");
        dodge_presentation
            .as_ref()
            .expect("JUST_DODGE_DODGE_TICK requires JUST_DODGE_DODGE_F413")
            .skin_for_tick(tick)
    });

    // ─── Three orthogonal close-up views of one C0 carrier ────
    // Center the camera on the first skinned model's bind-pose root.
    let model_center = renderer
        .skinned
        .first()
        .map(|s| Vec3::new(s.model.w_axis.x, s.model.w_axis.y, s.model.w_axis.z))
        .unwrap_or(Vec3::Y);
    let look_at = model_center + Vec3::Y * 0.9; // aim at chest height
    let cam_dist = 3.2f32; // full-body C0 framing, including feet and fingertips
    let views = [
        View {
            name: "front",
            eye: look_at + vec3(0.0, 0.0, cam_dist),
            target: look_at,
            up: Vec3::Y,
        },
        View {
            name: "side",
            eye: look_at + vec3(cam_dist, 0.0, 0.0),
            target: look_at,
            up: Vec3::Y,
        },
        View {
            name: "top",
            eye: look_at + vec3(0.0, cam_dist, 0.01),
            target: look_at,
            up: -Vec3::Z,
        },
        View {
            name: "first_person_duel",
            eye: model_center + Vec3::Y * 1.62,
            target: model_center + Vec3::Y * 1.62 - Vec3::Z,
            up: Vec3::Y,
        },
    ];

    for view in &views {
        let primary_skin = full_body_dodge_skin.unwrap_or(&c0_skin);
        renderer.update_skin_joints_indexed(&queue, 0, primary_skin);
        let opponent_skin = full_body_dodge_skin.unwrap_or_else(|| {
            dodge_presentation
                .as_ref()
                .map(|presentation| presentation.skin_for_tick(20))
                .unwrap_or(&c0_skin)
        });
        renderer.update_skin_joints_indexed(&queue, 1, opponent_skin);
        let view_mat = Mat4::look_at_lh(view.eye, view.target, view.up);
        let fov = if view.name == "first_person_duel" {
            70.0_f32.to_radians()
        } else {
            std::f32::consts::FRAC_PI_4
        };
        let proj = Mat4::perspective_lh(fov, w as f32 / h as f32, 0.1, 100.0);
        let proj_view = proj * view_mat;
        renderer.update_camera(&queue, &proj_view);
        let weapon_model =
            renderer::first_person_weapon_model(view.eye, (view.target - view.eye).normalize());
        renderer.update_first_person_weapon(&queue, &proj_view, weapon_model);
        renderer.upload_debug_mvp(&queue, &proj_view);

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

        let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
        {
            let mut rpass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("shot pass"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &color_view,
                    resolve_target: None,
                    depth_slice: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color {
                            r: 0.02,
                            g: 0.02,
                            b: 0.02,
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
            // The first-person view hides the player's full carrier, matching
            // the runtime self-occlusion rule; all other QA views inspect player 0.
            let skinned = if view.name == "first_person_duel" {
                &renderer.skinned[1..]
            } else {
                &renderer.skinned[..1]
            };
            for s in skinned {
                rpass.set_pipeline(&renderer.skin_pipeline);
                rpass.set_bind_group(0, &s.uniform_bind_group, &[]);
                rpass.set_bind_group(1, &s.texture_bind_group, &[]);
                rpass.set_bind_group(2, &s.joint_bind_group, &[]);
                rpass.set_vertex_buffer(0, s.vertex_buffer.slice(..));
                rpass.set_index_buffer(s.index_buffer.slice(..), wgpu::IndexFormat::Uint32);
                rpass.draw_indexed(0..s.index_count, 0, 0..1);
            }
            if view.name == "first_person_duel" {
                renderer.render_first_person_weapon(&mut rpass);
            }
            // Overlay bind-pose skeleton so bone-vs-mesh alignment is visible.
            renderer.render_debug_overlay(&mut rpass);
        }
        queue.submit(std::iter::once(encoder.finish()));

        let bytes_per_row = (w * 4).next_multiple_of(256);
        let buf_size = bytes_per_row * h;
        let read_buf = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("shot readback"),
            size: buf_size as u64,
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
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        let out_dir = format!("{}/qa_runs/bind_pose_{}", env!("CARGO_MANIFEST_DIR"), stamp);
        std::fs::create_dir_all(&out_dir).expect("create qa dir");
        let label = dodge_tick
            .map(|tick| format!("jd_dodge_tick_{tick}"))
            .unwrap_or_else(|| "jd_bind".to_string());
        let path = format!("{out_dir}/{label}_{}.png", view.name);
        img.save(&path).expect("save png");
        println!("shot: wrote {}", path);
    }
}

fn main() {
    pollster::block_on(run());
}
