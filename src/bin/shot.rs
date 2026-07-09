// Headless offscreen screenshot harness: renders the current scene into an
// offscreen texture, reads it back, and writes PNGs to /tmp for self-verification.
// Run: cargo run --bin shot
// Gate 1: bind-pose mannequin orientation diagnostic — three orthogonal views +
//         mesh percentiles + bone root positions.
use glam::{Mat4, Vec3, vec3};

#[path = "../asset.rs"]
mod asset;
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

    let (w, h) = (800u32, 600u32);
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

    let mut renderer = renderer::Renderer::new(&device, &queue, &config);
    let assets_dir = concat!(env!("CARGO_MANIFEST_DIR"), "/assets");

    // ─── Mesh diagnostics: percentiles + bone root positions ──────
    if let Ok(mesh) = asset::load_skinned(&format!("{}/characters/mannequin_male.bin", assets_dir))
    {
        let mut xs = Vec::with_capacity(mesh.vertices.len());
        let mut ys = Vec::with_capacity(mesh.vertices.len());
        let mut zs = Vec::with_capacity(mesh.vertices.len());
        let mut wsum_bad = 0u32;
        for v in &mesh.vertices {
            xs.push(v.position[0]);
            ys.push(v.position[1]);
            zs.push(v.position[2]);
            let ws = v.joint_weights[0]
                + v.joint_weights[1]
                + v.joint_weights[2]
                + v.joint_weights[3];
            if (ws - 1.0).abs() > 0.01 {
                wsum_bad += 1;
            }
        }
        println!("MESH PERCENTILES:");
        println!("  X  p05={:8.3} p50={:8.3} p95={:8.3} min={:8.3} max={:8.3}",
            percentile(&xs, 0.05), percentile(&xs, 0.50), percentile(&xs, 0.95),
            xs.iter().copied().fold(f32::MAX, f32::min),
            xs.iter().copied().fold(f32::MIN, f32::max));
        println!("  Y  p05={:8.3} p50={:8.3} p95={:8.3} min={:8.3} max={:8.3}",
            percentile(&ys, 0.05), percentile(&ys, 0.50), percentile(&ys, 0.95),
            ys.iter().copied().fold(f32::MAX, f32::min),
            ys.iter().copied().fold(f32::MIN, f32::max));
        println!("  Z  p05={:8.3} p50={:8.3} p95={:8.3} min={:8.3} max={:8.3}",
            percentile(&zs, 0.05), percentile(&zs, 0.50), percentile(&zs, 0.95),
            zs.iter().copied().fold(f32::MAX, f32::min),
            zs.iter().copied().fold(f32::MIN, f32::max));
        println!("  weight_bad={}", wsum_bad);

        println!("BONE ROOT POSITIONS (world bind):");
        for (i, b) in mesh.bones.iter().enumerate() {
            // inverse_bind maps bone space → mesh space.
            // The bone's world-space origin in bind pose is:
            //   bind_world * vec4(0,0,0,1) where bind_world = inverse_bind.inverse()
            let origin = b.inverse_bind.inverse() * Vec3::ZERO.extend(1.0);
            let px = origin.x / origin.w;
            let py = origin.y / origin.w;
            let pz = origin.z / origin.w;
            if i < 8 || b.parent == -1 || i == mesh.bones.len() - 1 {
                println!(
                    "  bone[{:2}] {:16} parent={:3} root=({:7.2},{:7.2},{:7.2})",
                    i, b.name, b.parent, px, py, pz
                );
            }
        }
    }

    // ─── Three orthogonal views ───────────────────────────────────
    let views = [
        View {
            name: "front",
            eye: vec3(0.0, 1.0, 4.0),
            target: vec3(0.0, 1.0, 0.0),
            up: Vec3::Y,
        },
        View {
            name: "side",
            eye: vec3(4.0, 1.0, 0.0),
            target: vec3(0.0, 1.0, 0.0),
            up: Vec3::Y,
        },
        View {
            name: "top",
            eye: vec3(0.0, 5.0, 0.1),
            target: vec3(0.0, 1.0, 0.0),
            up: -Vec3::Z,
        },
    ];

    // Corrective transform is baked into the renderer's model matrix.
    // Bind-pose views use identity joint matrices.
    renderer.update_skin_joints(&queue, &[Mat4::IDENTITY; 24]);

    for view in &views {
        let view_mat = Mat4::look_at_lh(view.eye, view.target, view.up);
        let proj = Mat4::perspective_lh(
            std::f32::consts::FRAC_PI_4,
            w as f32 / h as f32,
            0.1,
            100.0,
        );
        let proj_view = proj * view_mat;
        renderer.update_camera(&queue, &proj_view);

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

        let mut encoder =
            device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
        {
            let mut rpass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("shot pass"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &color_view,
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
        let mut copy =
            device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
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
        let path = format!("/tmp/jd_bind_{}.png", view.name);
        img.save(&path).expect("save png");
        println!("shot: wrote {}", path);
    }

}

fn main() {
    pollster::block_on(run());
}
