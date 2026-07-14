//! Deterministic PVP-005 candidate capture: clean beauty plus object-ID,
//! normal, and depth MRT outputs from the pinned WGPU/Vulkan path.
//!
//! This binary is intentionally candidate-only. Admission and live-runtime
//! capture must be added as separate fail-closed scopes before PVP-005 passes.

use glam::{Mat4, Vec3, vec3};
use image::{ImageBuffer, Rgba, RgbaImage};
use just_dodge::{asset, motion, motion_retarget, renderer};
use std::path::{Path, PathBuf};

const TILE: u32 = 512;
const SHEET: u32 = 2048;
const VIEWS: usize = 16;
const REVEAL_FRAMES: usize = 8;
const SOURCE_FPS: f32 = 25.0;
const SHIPPING_FPS: f32 = 60.0;

#[derive(Clone, Copy)]
struct Background {
    name: &'static str,
    rgba: [u8; 4],
}

const BACKGROUNDS: [Background; 2] = [
    Background {
        name: "charcoal",
        rgba: [11, 13, 18, 255],
    },
    Background {
        name: "offwhite",
        rgba: [244, 241, 232, 255],
    },
];

struct Targets {
    textures: [wgpu::Texture; 4],
    views: [wgpu::TextureView; 4],
}

fn create_targets(device: &wgpu::Device) -> Targets {
    let formats = [
        wgpu::TextureFormat::Rgba8UnormSrgb,
        wgpu::TextureFormat::Rgba8Unorm,
        wgpu::TextureFormat::Rgba8Unorm,
        wgpu::TextureFormat::Rgba8Unorm,
    ];
    let textures = formats.map(|format| {
        device.create_texture(&wgpu::TextureDescriptor {
            label: Some("PVP005 MRT target"),
            size: wgpu::Extent3d {
                width: TILE,
                height: TILE,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format,
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::COPY_SRC,
            view_formats: &[],
        })
    });
    let views = textures
        .each_ref()
        .map(|texture| texture.create_view(&wgpu::TextureViewDescriptor::default()));
    Targets { textures, views }
}

fn target_states() -> [Option<wgpu::ColorTargetState>; 4] {
    [
        wgpu::TextureFormat::Rgba8UnormSrgb,
        wgpu::TextureFormat::Rgba8Unorm,
        wgpu::TextureFormat::Rgba8Unorm,
        wgpu::TextureFormat::Rgba8Unorm,
    ]
    .map(|format| {
        Some(wgpu::ColorTargetState {
            format,
            blend: Some(wgpu::BlendState::REPLACE),
            write_mask: wgpu::ColorWrites::ALL,
        })
    })
}

fn rigid_layout() -> wgpu::VertexBufferLayout<'static> {
    wgpu::VertexBufferLayout {
        array_stride: 32,
        step_mode: wgpu::VertexStepMode::Vertex,
        attributes: &[
            wgpu::VertexAttribute {
                format: wgpu::VertexFormat::Float32x3,
                offset: 0,
                shader_location: 0,
            },
            wgpu::VertexAttribute {
                format: wgpu::VertexFormat::Float32x3,
                offset: 12,
                shader_location: 1,
            },
            wgpu::VertexAttribute {
                format: wgpu::VertexFormat::Float32x2,
                offset: 24,
                shader_location: 2,
            },
        ],
    }
}

fn skin_layout() -> wgpu::VertexBufferLayout<'static> {
    wgpu::VertexBufferLayout {
        array_stride: std::mem::size_of::<asset::SkinnedVertex>() as u64,
        step_mode: wgpu::VertexStepMode::Vertex,
        attributes: &[
            wgpu::VertexAttribute {
                format: wgpu::VertexFormat::Float32x3,
                offset: 0,
                shader_location: 0,
            },
            wgpu::VertexAttribute {
                format: wgpu::VertexFormat::Float32x3,
                offset: 12,
                shader_location: 1,
            },
            wgpu::VertexAttribute {
                format: wgpu::VertexFormat::Float32x2,
                offset: 24,
                shader_location: 2,
            },
            wgpu::VertexAttribute {
                format: wgpu::VertexFormat::Uint32x4,
                offset: 32,
                shader_location: 3,
            },
            wgpu::VertexAttribute {
                format: wgpu::VertexFormat::Uint32x4,
                offset: 48,
                shader_location: 4,
            },
            wgpu::VertexAttribute {
                format: wgpu::VertexFormat::Float32x4,
                offset: 64,
                shader_location: 5,
            },
            wgpu::VertexAttribute {
                format: wgpu::VertexFormat::Float32x4,
                offset: 80,
                shader_location: 6,
            },
        ],
    }
}

fn create_pipeline(
    device: &wgpu::Device,
    shader: &wgpu::ShaderModule,
    layouts: &[&wgpu::BindGroupLayout],
    vertex_entry: &'static str,
    fragment_entry: &'static str,
    vertex_layout: wgpu::VertexBufferLayout<'static>,
) -> wgpu::RenderPipeline {
    let layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: Some("PVP005 MRT layout"),
        bind_group_layouts: &layouts.iter().copied().map(Some).collect::<Vec<_>>(),
        immediate_size: 0,
    });
    device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: Some("PVP005 MRT pipeline"),
        cache: None,
        layout: Some(&layout),
        vertex: wgpu::VertexState {
            module: shader,
            entry_point: Some(vertex_entry),
            buffers: &[Some(vertex_layout)],
            compilation_options: wgpu::PipelineCompilationOptions::default(),
        },
        fragment: Some(wgpu::FragmentState {
            module: shader,
            entry_point: Some(fragment_entry),
            targets: &target_states(),
            compilation_options: wgpu::PipelineCompilationOptions::default(),
        }),
        primitive: wgpu::PrimitiveState {
            topology: wgpu::PrimitiveTopology::TriangleList,
            front_face: wgpu::FrontFace::Ccw,
            cull_mode: Some(wgpu::Face::Back),
            ..Default::default()
        },
        depth_stencil: Some(wgpu::DepthStencilState {
            format: wgpu::TextureFormat::Depth32Float,
            depth_write_enabled: Some(true),
            depth_compare: Some(wgpu::CompareFunction::Less),
            stencil: wgpu::StencilState::default(),
            bias: wgpu::DepthBiasState::default(),
        }),
        multisample: wgpu::MultisampleState::default(),
        multiview_mask: None,
    })
}

fn interpolate_frame(a: &[Mat4; 34], b: &[Mat4; 34], alpha: f32) -> [Mat4; 34] {
    std::array::from_fn(|joint| {
        let (_, qa, ta) = a[joint].to_scale_rotation_translation();
        let (_, qb, tb) = b[joint].to_scale_rotation_translation();
        Mat4::from_rotation_translation(qa.slerp(qb, alpha).normalize(), ta.lerp(tb, alpha))
    })
}

fn socket_model(mesh: &asset::SkinnedMeshData, skin: &[Mat4], actor_model: Mat4) -> Mat4 {
    let index = |name: &str| {
        mesh.bones
            .iter()
            .position(|bone| bone.name == name)
            .unwrap_or_else(|| panic!("missing required socket bone {name}"))
    };
    let forearm_index = index("RightForeArm");
    let hand_index = index("RightHand");
    let posed = |joint: usize| actor_model * skin[joint] * mesh.bones[joint].inverse_bind.inverse();
    let forearm = posed(forearm_index).to_scale_rotation_translation().2;
    let hand = posed(hand_index).to_scale_rotation_translation().2;
    let blade = (hand - forearm).normalize();
    let mut lateral = Vec3::Z.cross(blade);
    if lateral.length_squared() < 1.0e-6 {
        lateral = Vec3::X.cross(blade);
    }
    lateral = lateral.normalize();
    let thickness = blade.cross(lateral).normalize();
    Mat4::from_cols(
        lateral.extend(0.0),
        thickness.extend(0.0),
        blade.extend(0.0),
        hand.extend(1.0),
    )
}

fn read_texture(device: &wgpu::Device, queue: &wgpu::Queue, texture: &wgpu::Texture) -> RgbaImage {
    let row = (TILE * 4).next_multiple_of(256);
    let buffer = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("PVP005 readback"),
        size: (row * TILE) as u64,
        usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
        mapped_at_creation: false,
    });
    let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
    encoder.copy_texture_to_buffer(
        wgpu::TexelCopyTextureInfo {
            texture,
            mip_level: 0,
            origin: wgpu::Origin3d::ZERO,
            aspect: wgpu::TextureAspect::All,
        },
        wgpu::TexelCopyBufferInfo {
            buffer: &buffer,
            layout: wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(row),
                rows_per_image: Some(TILE),
            },
        },
        wgpu::Extent3d {
            width: TILE,
            height: TILE,
            depth_or_array_layers: 1,
        },
    );
    queue.submit([encoder.finish()]);
    buffer.slice(..).map_async(wgpu::MapMode::Read, |_| {});
    device
        .poll(wgpu::PollType::wait_indefinitely())
        .expect("PVP005 readback poll");
    let mapped = buffer
        .slice(..)
        .get_mapped_range()
        .expect("PVP005 mapped readback");
    let mut image = RgbaImage::new(TILE, TILE);
    for y in 0..TILE {
        let start = (y * row) as usize;
        let end = start + (TILE * 4) as usize;
        image.as_mut()[(y * TILE * 4) as usize..((y + 1) * TILE * 4) as usize]
            .copy_from_slice(&mapped[start..end]);
    }
    drop(mapped);
    buffer.unmap();
    image
}

fn paste(sheet: &mut RgbaImage, tile: &RgbaImage, view_index: usize) {
    let x0 = (view_index as u32 % 4) * TILE;
    let y0 = (view_index as u32 / 4) * TILE;
    for (x, y, pixel) in tile.enumerate_pixels() {
        sheet.put_pixel(x0 + x, y0 + y, *pixel);
    }
}

fn paste_strip(strip: &mut RgbaImage, tile: &RgbaImage, frame_index: usize) {
    let x0 = frame_index as u32 * TILE;
    for (x, y, pixel) in tile.enumerate_pixels() {
        strip.put_pixel(x0 + x, y, *pixel);
    }
}

fn id_metrics(ids: &RgbaImage) -> (usize, usize, usize) {
    let mut actor_pixels = 0usize;
    let mut weapon_pixels = 0usize;
    let mut edge_pixels = 0usize;
    for (x, y, pixel) in ids.enumerate_pixels() {
        let actor = pixel.0 == [255, 0, 0, 255];
        let weapon = pixel.0 == [0, 255, 0, 255];
        actor_pixels += usize::from(actor);
        weapon_pixels += usize::from(weapon);
        if (actor || weapon) && (x < 8 || y < 8 || x >= TILE - 8 || y >= TILE - 8) {
            edge_pixels += 1;
        }
    }
    (actor_pixels, weapon_pixels, edge_pixels)
}

fn silhouette(ids: &RgbaImage) -> RgbaImage {
    ImageBuffer::from_fn(ids.width(), ids.height(), |x, y| {
        let pixel = ids.get_pixel(x, y);
        if pixel.0 == [255, 0, 0, 255] || pixel.0 == [0, 255, 0, 255] {
            Rgba([255, 255, 255, 255])
        } else {
            Rgba([0, 0, 0, 255])
        }
    })
}

fn render_tile(
    device: &wgpu::Device,
    queue: &wgpu::Queue,
    renderer: &renderer::Renderer,
    targets: &Targets,
    actor_pipeline: &wgpu::RenderPipeline,
    weapon_pipeline: &wgpu::RenderPipeline,
    background: Background,
) {
    let linear = |value: u8| {
        let encoded = value as f64 / 255.0;
        if encoded <= 0.04045 {
            encoded / 12.92
        } else {
            ((encoded + 0.055) / 1.055).powf(2.4)
        }
    };
    let clear = wgpu::Color {
        // Clear colors are expressed in linear space even for an sRGB target.
        // Convert the versioned palette so PNG edge pixels are byte-exact.
        r: linear(background.rgba[0]),
        g: linear(background.rgba[1]),
        b: linear(background.rgba[2]),
        a: 1.0,
    };
    let mut encoder = device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
    {
        let attachments = [
            Some(wgpu::RenderPassColorAttachment {
                view: &targets.views[0],
                resolve_target: None,
                depth_slice: None,
                ops: wgpu::Operations {
                    load: wgpu::LoadOp::Clear(clear),
                    store: wgpu::StoreOp::Store,
                },
            }),
            Some(wgpu::RenderPassColorAttachment {
                view: &targets.views[1],
                resolve_target: None,
                depth_slice: None,
                ops: wgpu::Operations {
                    load: wgpu::LoadOp::Clear(wgpu::Color::BLACK),
                    store: wgpu::StoreOp::Store,
                },
            }),
            Some(wgpu::RenderPassColorAttachment {
                view: &targets.views[2],
                resolve_target: None,
                depth_slice: None,
                ops: wgpu::Operations {
                    load: wgpu::LoadOp::Clear(wgpu::Color::BLACK),
                    store: wgpu::StoreOp::Store,
                },
            }),
            Some(wgpu::RenderPassColorAttachment {
                view: &targets.views[3],
                resolve_target: None,
                depth_slice: None,
                ops: wgpu::Operations {
                    load: wgpu::LoadOp::Clear(wgpu::Color::WHITE),
                    store: wgpu::StoreOp::Store,
                },
            }),
        ];
        let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
            label: Some("PVP005 MRT pass"),
            color_attachments: &attachments,
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
        let actor = &renderer.skinned[0];
        pass.set_pipeline(actor_pipeline);
        pass.set_bind_group(0, &actor.uniform_bind_group, &[]);
        pass.set_bind_group(1, &actor.texture_bind_group, &[]);
        pass.set_bind_group(2, &actor.joint_bind_group, &[]);
        pass.set_vertex_buffer(0, actor.vertex_buffer.slice(..));
        pass.set_index_buffer(actor.index_buffer.slice(..), wgpu::IndexFormat::Uint32);
        pass.draw_indexed(0..actor.index_count, 0, 0..1);
        let weapon = &renderer.first_person_weapon;
        pass.set_pipeline(weapon_pipeline);
        pass.set_bind_group(0, &weapon.uniform_bind_group, &[]);
        pass.set_bind_group(1, &weapon.texture_bind_group, &[]);
        pass.set_vertex_buffer(0, weapon.vertex_buffer.slice(..));
        pass.set_index_buffer(weapon.index_buffer.slice(..), wgpu::IndexFormat::Uint32);
        pass.draw_indexed(0..weapon.index_count, 0, 0..1);
    }
    queue.submit([encoder.finish()]);
}

async fn run() {
    let action = std::env::var("PVP005_ACTION").expect("PVP005_ACTION is required");
    let source_path = PathBuf::from(std::env::var("PVP005_F413").expect("PVP005_F413 is required"));
    let tell_start: usize = std::env::var("PVP005_TELL_START")
        .expect("PVP005_TELL_START is required")
        .parse()
        .expect("integer PVP005_TELL_START");
    let output =
        PathBuf::from(std::env::var("PVP005_OUTPUT_DIR").expect("PVP005_OUTPUT_DIR is required"));
    assert!(
        !output.exists(),
        "refusing to overwrite PVP005 output {}",
        output.display()
    );
    std::fs::create_dir_all(&output).expect("create PVP005 output");

    let frames = motion::load_g1_frames(source_path.to_str().expect("UTF-8 source path"))
        .expect("valid candidate F413");
    assert!(
        tell_start + 4 < frames.len(),
        "candidate tell window cannot supply 60 Hz samples"
    );
    let assets = Path::new(env!("CARGO_MANIFEST_DIR")).join("assets");
    let mesh = asset::load_skinned(
        &assets
            .join("source/meshy/c0_armored_duelist_001/cooked/c0_armored_duelist.bin")
            .to_string_lossy(),
    )
    .expect("load C0 carrier");

    let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
        backends: wgpu::Backends::VULKAN,
        flags: wgpu::InstanceFlags::default(),
        memory_budget_thresholds: wgpu::MemoryBudgetThresholds::default(),
        backend_options: wgpu::BackendOptions::default(),
        display: None,
    });
    let adapter = instance
        .request_adapter(&wgpu::RequestAdapterOptions::default())
        .await
        .expect("Vulkan adapter required");
    let info = adapter.get_info();
    let (device, queue) = adapter
        .request_device(&wgpu::DeviceDescriptor::default())
        .await
        .expect("WGPU device");
    let config = wgpu::SurfaceConfiguration {
        usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
        format: wgpu::TextureFormat::Rgba8UnormSrgb,
        width: TILE,
        height: TILE,
        present_mode: wgpu::PresentMode::Fifo,
        alpha_mode: wgpu::CompositeAlphaMode::Auto,
        view_formats: vec![],
        color_space: wgpu::SurfaceColorSpace::Auto,
        desired_maximum_frame_latency: 2,
    };
    let mut renderer = renderer::Renderer::new(&device, &queue, &config, true, &assets);
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("PVP005 QA MRT shader"),
        source: wgpu::ShaderSource::Wgsl(include_str!("../pvp005_qa.wgsl").into()),
    });
    let skin_bgls = [
        renderer.skin_pipeline.get_bind_group_layout(0),
        renderer.skin_pipeline.get_bind_group_layout(1),
        renderer.skin_pipeline.get_bind_group_layout(2),
    ];
    let rigid_bgls = [
        renderer.pipeline.get_bind_group_layout(0),
        renderer.pipeline.get_bind_group_layout(1),
    ];
    let actor_pipeline = create_pipeline(
        &device,
        &shader,
        &skin_bgls.iter().collect::<Vec<_>>(),
        "skin_vs",
        "actor_fs",
        skin_layout(),
    );
    let weapon_pipeline = create_pipeline(
        &device,
        &shader,
        &rigid_bgls.iter().collect::<Vec<_>>(),
        "rigid_vs",
        "weapon_fs",
        rigid_layout(),
    );
    let targets = create_targets(&device);
    let layer_names = ["beauty", "object_id", "normals", "depth"];
    let mut first_person_strips: [[RgbaImage; 4]; 2] = std::array::from_fn(|_| {
        std::array::from_fn(|_| {
            ImageBuffer::from_pixel(TILE * REVEAL_FRAMES as u32, TILE, Rgba([0, 0, 0, 255]))
        })
    });
    let mut view_metrics = Vec::new();
    let mut first_person_metrics = Vec::new();
    let mut crop_failures = 0usize;
    let mut visibility_failures = 0usize;
    let mut first_person_crop_failures = 0usize;
    let mut first_person_visibility_failures = 0usize;

    for reveal in 0..REVEAL_FRAMES {
        let source_time = tell_start as f32 + reveal as f32 * SOURCE_FPS / SHIPPING_FPS;
        let lo = source_time.floor() as usize;
        let hi = (lo + 1).min(frames.len() - 1);
        let source = interpolate_frame(&frames[lo], &frames[hi], source_time - lo as f32);
        let skin = motion_retarget::retarget_g1_frame_to_armored_skin(&mesh, &frames[0], &source)
            .expect("candidate retarget");
        renderer.update_skin_joints_indexed(&queue, 0, &skin);
        for background in BACKGROUNDS {
            let mut sheets: [RgbaImage; 4] = std::array::from_fn(|_| {
                ImageBuffer::from_pixel(SHEET, SHEET, Rgba([0, 0, 0, 255]))
            });
            for view_index in 0..VIEWS {
                let azimuth = view_index as f32 * 22.5_f32.to_radians();
                let aim = vec3(0.0, 0.9, 0.0);
                let eye = aim + vec3(azimuth.sin() * 3.2, 0.0, azimuth.cos() * 3.2);
                let view = Mat4::look_at_lh(eye, aim, Vec3::Y);
                let projection = Mat4::perspective_lh(45.0_f32.to_radians(), 1.0, 0.1, 100.0);
                let pv = projection * view;
                renderer.skinned[0].model = renderer::skinned_correct_model();
                renderer.update_camera(&queue, &pv);
                let weapon_model = socket_model(&mesh, &skin, renderer.skinned[0].model);
                renderer.update_first_person_weapon(&queue, &pv, weapon_model);
                render_tile(
                    &device,
                    &queue,
                    &renderer,
                    &targets,
                    &actor_pipeline,
                    &weapon_pipeline,
                    background,
                );
                let tiles: [RgbaImage; 4] = std::array::from_fn(|layer| {
                    read_texture(&device, &queue, &targets.textures[layer])
                });
                let (actor_pixels, weapon_pixels, edge_pixels) = id_metrics(&tiles[1]);
                crop_failures += usize::from(edge_pixels > 0);
                visibility_failures += usize::from(actor_pixels == 0 || weapon_pixels == 0);
                view_metrics.push(format!(
                    "    {{\"frame\":{reveal},\"background\":\"{}\",\"view\":{view_index},\"azimuth_degrees\":{},\"actor_pixels\":{actor_pixels},\"weapon_pixels\":{weapon_pixels},\"edge_pixels\":{edge_pixels},\"crop_pass\":{},\"visibility_pass\":{}}}",
                    background.name,
                    view_index as f32 * 22.5,
                    edge_pixels == 0,
                    actor_pixels > 0 && weapon_pixels > 0,
                ));
                for layer in 0..4 {
                    paste(&mut sheets[layer], &tiles[layer], view_index);
                }
            }
            for (layer, sheet) in layer_names.iter().zip(sheets.iter()) {
                let path = output.join(format!(
                    "{action}_candidate_f{reveal:02}_{background}_{layer}.png",
                    background = background.name
                ));
                sheet.save(&path).expect("save PVP005 sheet");
            }
            silhouette(&sheets[1])
                .save(output.join(format!(
                    "{action}_candidate_f{reveal:02}_{background}_silhouette.png",
                    background = background.name
                )))
                .expect("save PVP005 silhouette sheet");

            let eye = vec3(0.0, 1.62, 1.0);
            let view = Mat4::look_at_lh(eye, eye - Vec3::Z, Vec3::Y);
            let projection = Mat4::perspective_lh(70.0_f32.to_radians(), 1.0, 0.1, 100.0);
            let pv = projection * view;
            renderer.skinned[0].model =
                Mat4::from_translation(vec3(0.0, 0.0, -1.0)) * renderer::skinned_correct_model();
            renderer.update_camera(&queue, &pv);
            let weapon_model = socket_model(&mesh, &skin, renderer.skinned[0].model);
            renderer.update_first_person_weapon(&queue, &pv, weapon_model);
            render_tile(
                &device,
                &queue,
                &renderer,
                &targets,
                &actor_pipeline,
                &weapon_pipeline,
                background,
            );
            let tiles: [RgbaImage; 4] = std::array::from_fn(|layer| {
                read_texture(&device, &queue, &targets.textures[layer])
            });
            let (actor_pixels, weapon_pixels, edge_pixels) = id_metrics(&tiles[1]);
            first_person_crop_failures += usize::from(edge_pixels > 0);
            first_person_visibility_failures +=
                usize::from(actor_pixels == 0 || weapon_pixels == 0);
            let background_index = usize::from(background.name == "offwhite");
            for layer in 0..4 {
                paste_strip(
                    &mut first_person_strips[background_index][layer],
                    &tiles[layer],
                    reveal,
                );
            }
            first_person_metrics.push(format!(
                "    {{\"frame\":{reveal},\"background\":\"{}\",\"actor_pixels\":{actor_pixels},\"weapon_pixels\":{weapon_pixels},\"edge_pixels\":{edge_pixels},\"crop_pass\":{},\"visibility_pass\":{}}}",
                background.name,
                edge_pixels == 0,
                actor_pixels > 0 && weapon_pixels > 0,
            ));
        }
    }
    for (background_index, background) in BACKGROUNDS.iter().enumerate() {
        for (layer, strip) in layer_names
            .iter()
            .zip(first_person_strips[background_index].iter())
        {
            strip
                .save(output.join(format!(
                    "{action}_candidate_first_person_8f_{}_{}.png",
                    background.name, layer
                )))
                .expect("save PVP005 first-person strip");
        }
        silhouette(&first_person_strips[background_index][1])
            .save(output.join(format!(
                "{action}_candidate_first_person_8f_{}_silhouette.png",
                background.name
            )))
            .expect("save PVP005 first-person silhouette strip");
    }
    let pass = crop_failures == 0
        && visibility_failures == 0
        && first_person_crop_failures == 0
        && first_person_visibility_failures == 0;
    let report = format!(
        concat!(
            "{{\n  \"schema\": \"just-dodge-pvp005-candidate-mrt-v1\",\n",
            "  \"action\": \"{action}\",\n",
            "  \"source\": \"{}\",\n",
            "  \"tell_start\": {tell_start},\n",
            "  \"source_fps\": 25,\n  \"shipping_fps\": 60,\n",
            "  \"frames\": 8,\n  \"views_per_sheet\": 16,\n",
            "  \"azimuth_step_degrees\": 22.5,\n",
            "  \"layers\": [\"beauty\", \"silhouette\", \"object_id\", \"normals\", \"depth\"],\n",
            "  \"backgrounds\": [\"charcoal\", \"offwhite\"],\n",
            "  \"first_person_camera\": {{\"eye_m\":[0.0,1.62,1.0],\"aim_direction\":[0.0,0.0,-1.0],\"opponent_root_m\":[0.0,0.0,-1.0],\"vertical_fov_degrees\":70.0}},\n",
            "  \"adapter_backend\": \"{:?}\",\n  \"adapter_name\": \"{}\",\n",
            "  \"scope\": \"candidate\",\n  \"crop_margin_px\": 8,\n",
            "  \"crop_failures\": {crop_failures},\n",
            "  \"visibility_failures\": {visibility_failures},\n",
            "  \"first_person_crop_failures\": {first_person_crop_failures},\n",
            "  \"first_person_visibility_failures\": {first_person_visibility_failures},\n",
            "  \"pass\": {pass},\n  \"view_metrics\": [\n{}\n  ],\n",
            "  \"first_person_metrics\": [\n{}\n  ]\n}}\n"
        ),
        source_path.display(),
        info.backend,
        info.name.replace('"', "'"),
        view_metrics.join(",\n"),
        first_person_metrics.join(",\n"),
        action = action,
        tell_start = tell_start,
        crop_failures = crop_failures,
        visibility_failures = visibility_failures,
        first_person_crop_failures = first_person_crop_failures,
        first_person_visibility_failures = first_person_visibility_failures,
        pass = pass,
    );
    std::fs::write(output.join("capture.json"), report).expect("write PVP005 capture report");
    println!(
        "PVP005_CANDIDATE_MRT=COMPLETE action={action} crop_failures={crop_failures} visibility_failures={visibility_failures} first_person_crop_failures={first_person_crop_failures} first_person_visibility_failures={first_person_visibility_failures} output={}",
        output.display()
    );
}

fn main() {
    pollster::block_on(run());
}

#[cfg(test)]
mod tests {
    use super::*;
    use glam::Quat;

    #[test]
    fn shipping_sample_interpolation_is_finite_and_deterministic() {
        let mut a = [Mat4::IDENTITY; 34];
        let mut b = [Mat4::IDENTITY; 34];
        for joint in 0..34 {
            a[joint] = Mat4::from_translation(vec3(joint as f32, 0.0, 0.0));
            b[joint] = Mat4::from_rotation_translation(
                Quat::from_rotation_y(0.5),
                vec3(joint as f32, 2.0, 0.0),
            );
        }
        let first = interpolate_frame(&a, &b, 0.25);
        let second = interpolate_frame(&a, &b, 0.25);
        assert_eq!(
            first.map(|matrix| matrix.to_cols_array()),
            second.map(|matrix| matrix.to_cols_array())
        );
        assert!(first.iter().all(Mat4::is_finite));
        assert!((first[0].w_axis.y - 0.5).abs() < 1.0e-6);
    }

    #[test]
    fn silhouette_combines_actor_and_weapon_ids_only() {
        let mut ids = RgbaImage::new(3, 1);
        ids.put_pixel(0, 0, Rgba([255, 0, 0, 255]));
        ids.put_pixel(1, 0, Rgba([0, 255, 0, 255]));
        ids.put_pixel(2, 0, Rgba([0, 0, 0, 255]));
        let mask = silhouette(&ids);
        assert_eq!(mask.get_pixel(0, 0).0, [255, 255, 255, 255]);
        assert_eq!(mask.get_pixel(1, 0).0, [255, 255, 255, 255]);
        assert_eq!(mask.get_pixel(2, 0).0, [0, 0, 0, 255]);
    }
}
