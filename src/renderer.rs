// Multi-mesh renderer with per-object transforms + ground plane
// Arena layout: rock, gate, pillar in circular arrangement around center.
// Camera: orbital with mouse drag + scroll zoom.

use wgpu::util::DeviceExt;
use crate::asset;
use glam::Mat4;

pub struct MeshObject {
    pub vertex_buffer: wgpu::Buffer,
    pub index_buffer: wgpu::Buffer,
    pub index_count: u32,
    pub uniform_buffer: wgpu::Buffer,
    pub uniform_bind_group: wgpu::BindGroup,
    pub texture_bind_group: wgpu::BindGroup,
    /// Local-to-world transform
    pub model: Mat4,
}

pub struct Renderer {
    pub pipeline: wgpu::RenderPipeline,
    pub objects: Vec<MeshObject>,
    pub depth_view: wgpu::TextureView,
    // Camera state (separate from per-object uniform)
    pub proj_view: Mat4,
}

fn load_texture(
    device: &wgpu::Device,
    queue: &wgpu::Queue,
    path: &str,
) -> (wgpu::Texture, wgpu::TextureView, wgpu::Sampler) {
    let img = image::open(path)
        .expect("Failed to load texture")
        .to_rgba8();
    let (width, height) = img.dimensions();
    let texture_size = wgpu::Extent3d { width, height, depth_or_array_layers: 1 };

    let texture = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("Texture"),
        size: texture_size,
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Rgba8UnormSrgb,
        usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
        view_formats: &[],
    });

    queue.write_texture(
        wgpu::ImageCopyTexture {
            texture: &texture,
            mip_level: 0,
            origin: wgpu::Origin3d::ZERO,
            aspect: wgpu::TextureAspect::All,
        },
        &img,
        wgpu::ImageDataLayout { offset: 0, bytes_per_row: Some(4 * width), rows_per_image: Some(height) },
        texture_size,
    );

    let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
    let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
        address_mode_u: wgpu::AddressMode::Repeat,
        address_mode_v: wgpu::AddressMode::Repeat,
        address_mode_w: wgpu::AddressMode::Repeat,
        mag_filter: wgpu::FilterMode::Linear,
        min_filter: wgpu::FilterMode::Linear,
        mipmap_filter: wgpu::FilterMode::Linear,
        ..Default::default()
    });
    (texture, view, sampler)
}

fn build_mesh_buffers(
    device: &wgpu::Device, mesh: &asset::MeshData, label: &str,
) -> (wgpu::Buffer, wgpu::Buffer, u32) {
    let vc = mesh.vertices.len() / 3;
    let mut interleaved = Vec::with_capacity(vc * 8);
    for i in 0..vc {
        let vi = i * 3; let uvi = i * 2;
        interleaved.extend_from_slice(&[mesh.vertices[vi], mesh.vertices[vi+1], mesh.vertices[vi+2]]);
        interleaved.extend_from_slice(&[mesh.normals[vi], mesh.normals[vi+1], mesh.normals[vi+2]]);
        interleaved.extend_from_slice(&[mesh.uvs[uvi], mesh.uvs[uvi+1]]);
    }
    let vb = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some(&format!("{label} VB")),
        contents: bytemuck::cast_slice(&interleaved),
        usage: wgpu::BufferUsages::VERTEX,
    });
    let ib = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some(&format!("{label} IB")),
        contents: bytemuck::cast_slice(&mesh.indices),
        usage: wgpu::BufferUsages::INDEX,
    });
    (vb, ib, mesh.indices.len() as u32)
}

fn build_procedural_ground(device: &wgpu::Device) -> (wgpu::Buffer, wgpu::Buffer, u32) {
    // Large quad: 20x20, centered at origin, Y=0
    let s = 10.0f32;
    let vertices: [f32; 8 * 4] = [
        // pos(x,y,z)          normal(0,1,0)    uv
        -s, 0.0, -s,    0.0, 1.0, 0.0,    0.0, 20.0,
        s, 0.0, -s,    0.0, 1.0, 0.0,    20.0, 20.0,
        s, 0.0,  s,    0.0, 1.0, 0.0,    20.0, 0.0,
        -s, 0.0,  s,    0.0, 1.0, 0.0,    0.0, 0.0,
    ];
    let indices: [u32; 6] = [0, 1, 2, 0, 2, 3];
    let vb = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("Ground VB"),
        contents: bytemuck::cast_slice(&vertices),
        usage: wgpu::BufferUsages::VERTEX,
    });
    let ib = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("Ground IB"),
        contents: bytemuck::cast_slice(&indices),
        usage: wgpu::BufferUsages::INDEX,
    });
    (vb, ib, 6)
}

fn build_ground_texture(device: &wgpu::Device, queue: &wgpu::Queue) -> (wgpu::TextureView, wgpu::Sampler) {
    // Procedural checkerboard ground texture (256x256)
    let size = 256u32;
    let mut pixels = vec![0u8; (size * size * 4) as usize];
    for y in 0..size {
        for x in 0..size {
            let i = ((y * size + x) * 4) as usize;
            let checker = ((x / 16 + y / 16) % 2) == 0;
            if checker {
                pixels[i] = 60; pixels[i+1] = 50; pixels[i+2] = 40; pixels[i+3] = 255;
            } else {
                pixels[i] = 40; pixels[i+1] = 35; pixels[i+2] = 30; pixels[i+3] = 255;
            }
        }
    }
    let tex = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("Ground Tex"),
        size: wgpu::Extent3d { width: size, height: size, depth_or_array_layers: 1 },
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Rgba8UnormSrgb,
        usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
        view_formats: &[],
    });
    queue.write_texture(
        wgpu::ImageCopyTexture { texture: &tex, mip_level: 0, origin: wgpu::Origin3d::ZERO, aspect: wgpu::TextureAspect::All },
        &pixels,
        wgpu::ImageDataLayout { offset: 0, bytes_per_row: Some(4 * size), rows_per_image: Some(size) },
        wgpu::Extent3d { width: size, height: size, depth_or_array_layers: 1 },
    );
    let view = tex.create_view(&wgpu::TextureViewDescriptor::default());
    let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
        address_mode_u: wgpu::AddressMode::Repeat,
        address_mode_v: wgpu::AddressMode::Repeat,
        address_mode_w: wgpu::AddressMode::Repeat,
        mag_filter: wgpu::FilterMode::Linear,
        min_filter: wgpu::FilterMode::Linear,
        mipmap_filter: wgpu::FilterMode::Linear,
        ..Default::default()
    });
    (view, sampler)
}

impl Renderer {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        device: &wgpu::Device,
        config: &wgpu::SurfaceConfiguration,
        queue: &wgpu::Queue,
    ) -> Self {
        let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("Shader"),
            source: wgpu::ShaderSource::Wgsl(include_str!("shader.wgsl").into()),
        });

        let assets = concat!(env!("CARGO_MANIFEST_DIR"), "/assets");

        // Bind group layout: group(0) = MVP uniform
        let uniform_bgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("Uniform BGL"),
            entries: &[wgpu::BindGroupLayoutEntry {
                binding: 0, visibility: wgpu::ShaderStages::VERTEX,
                ty: wgpu::BindingType::Buffer {
                    ty: wgpu::BufferBindingType::Uniform,
                    has_dynamic_offset: false, min_binding_size: None,
                },
                count: None,
            }],
        });

        // Bind group layout: group(1) = texture + sampler
        let texture_bgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("Texture BGL"),
            entries: &[
                wgpu::BindGroupLayoutEntry {
                    binding: 0, visibility: wgpu::ShaderStages::FRAGMENT,
                    ty: wgpu::BindingType::Texture {
                        sample_type: wgpu::TextureSampleType::Float { filterable: true },
                        view_dimension: wgpu::TextureViewDimension::D2, multisampled: false,
                    },
                    count: None,
                },
                wgpu::BindGroupLayoutEntry {
                    binding: 1, visibility: wgpu::ShaderStages::FRAGMENT,
                    ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),
                    count: None,
                },
            ],
        });

        // --- Pipeline ---
        let vertex_layout = wgpu::VertexBufferLayout {
            array_stride: 8 * 4, step_mode: wgpu::VertexStepMode::Vertex,
            attributes: &[
                wgpu::VertexAttribute { format: wgpu::VertexFormat::Float32x3, offset: 0, shader_location: 0 },
                wgpu::VertexAttribute { format: wgpu::VertexFormat::Float32x3, offset: 12, shader_location: 1 },
                wgpu::VertexAttribute { format: wgpu::VertexFormat::Float32x2, offset: 24, shader_location: 2 },
            ],
        };

        let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("Pipeline Layout"),
            bind_group_layouts: &[&uniform_bgl, &texture_bgl],
            push_constant_ranges: &[],
        });

        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("Pipeline"), cache: None, layout: Some(&pipeline_layout),
            vertex: wgpu::VertexState {
                module: &shader, entry_point: "vs_main", buffers: &[vertex_layout],
                compilation_options: wgpu::PipelineCompilationOptions::default(),
            },
            fragment: Some(wgpu::FragmentState {
                module: &shader, entry_point: "fs_main",
                targets: &[Some(wgpu::ColorTargetState {
                    format: config.format,
                    blend: Some(wgpu::BlendState::REPLACE),
                    write_mask: wgpu::ColorWrites::ALL,
                })],
                compilation_options: wgpu::PipelineCompilationOptions::default(),
            }),
            primitive: wgpu::PrimitiveState {
                topology: wgpu::PrimitiveTopology::TriangleList,
                cull_mode: Some(wgpu::Face::Back), front_face: wgpu::FrontFace::Ccw,
                ..Default::default()
            },
            depth_stencil: Some(wgpu::DepthStencilState {
                format: wgpu::TextureFormat::Depth32Float,
                depth_write_enabled: true, depth_compare: wgpu::CompareFunction::Less,
                stencil: wgpu::StencilState::default(), bias: wgpu::DepthBiasState::default(),
            }),
            multisample: wgpu::MultisampleState::default(), multiview: None,
        });

        // --- Depth texture ---
        let depth_texture = device.create_texture(&wgpu::TextureDescriptor {
            label: Some("Depth Texture"),
            size: wgpu::Extent3d { width: config.width, height: config.height, depth_or_array_layers: 1 },
            mip_level_count: 1, sample_count: 1, dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Depth32Float,
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT, view_formats: &[],
        });
        let depth_view = depth_texture.create_view(&wgpu::TextureViewDescriptor::default());

        // --- Build all objects ---
        let mut objects = Vec::new();

        // Arena layout (circular, ~3m radius):
        //   Rock at (0,0,-3), Gate at (2.6,0,1.5), Pillar at (-2.6,0,1.5)
        // Mannequin at center (0,0,0)
        struct ObjCfg { bin: &'static str, tex: &'static str, model: Mat4 }
        let cfgs = [
            ObjCfg { bin: "arena_rock.bin", tex: "arena_rock_0.png",
                model: Mat4::from_translation(glam::vec3(0.0, -0.2, -3.0)) },
            ObjCfg { bin: "lintel_gate.bin", tex: "lintel_gate_0.jpg",
                model: Mat4::from_translation(glam::vec3(2.6, -0.1, 1.5)) },
            ObjCfg { bin: "rune_pillar.bin", tex: "rune_pillar_0.jpg",
                model: Mat4::from_translation(glam::vec3(-2.6, 0.0, 1.5)) },
            ObjCfg { bin: "mannequin_male.bin", tex: "mannequin_male_0.png",
                model: Mat4::from_scale(glam::vec3(1.8, 1.8, 1.8)) * Mat4::from_translation(glam::vec3(0.0, 0.0, 0.0)) },
        ];

        for cfg in cfgs {
            let mesh = asset::load_binary(&format!("{}/{}", assets, cfg.bin))
                .unwrap_or_else(|e| panic!("Failed to load {}: {e}", cfg.bin));
            let (vb, ib, ic) = build_mesh_buffers(device, &mesh, cfg.bin);
            println!("  {}: {} verts, {} idxs", cfg.bin, mesh.vertices.len() / 3, mesh.indices.len());

            // Per-object uniform (MVP = proj_view * model, updated each frame)
            let ub = device.create_buffer(&wgpu::BufferDescriptor {
                label: Some(&format!("UB {}", cfg.bin)),
                size: 64, usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
            let ubg = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some(&format!("UBG {}", cfg.bin)),
                layout: &uniform_bgl,
                entries: &[wgpu::BindGroupEntry { binding: 0, resource: ub.as_entire_binding() }],
            });

            let (_t, tv, ts) = load_texture(device, queue, &format!("{}/{}", assets, cfg.tex));
            let tbg = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some(&format!("TBG {}", cfg.bin)),
                layout: &texture_bgl,
                entries: &[
                    wgpu::BindGroupEntry { binding: 0, resource: wgpu::BindingResource::TextureView(&tv) },
                    wgpu::BindGroupEntry { binding: 1, resource: wgpu::BindingResource::Sampler(&ts) },
                ],
            });

            objects.push(MeshObject {
                vertex_buffer: vb, index_buffer: ib, index_count: ic,
                uniform_buffer: ub, uniform_bind_group: ubg,
                texture_bind_group: tbg, model: cfg.model,
            });
        }

        // --- Ground plane ---
        {
            let (gv, gi, gc) = build_procedural_ground(device);
            let (gtv, gts) = build_ground_texture(device, queue);
            let g_model = Mat4::IDENTITY;
            let ub = device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("UB Ground"), size: 64,
                usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
            let ubg = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("UBG Ground"), layout: &uniform_bgl,
                entries: &[wgpu::BindGroupEntry { binding: 0, resource: ub.as_entire_binding() }],
            });
            let tbg = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("TBG Ground"), layout: &texture_bgl,
                entries: &[
                    wgpu::BindGroupEntry { binding: 0, resource: wgpu::BindingResource::TextureView(&gtv) },
                    wgpu::BindGroupEntry { binding: 1, resource: wgpu::BindingResource::Sampler(&gts) },
                ],
            });
            objects.push(MeshObject {
                vertex_buffer: gv, index_buffer: gi, index_count: gc,
                uniform_buffer: ub, uniform_bind_group: ubg,
                texture_bind_group: tbg, model: g_model,
            });
        }

        Self {
            pipeline,
            objects,
            depth_view,
            proj_view: Mat4::IDENTITY,
        }
    }

    /// Update camera projection * view matrix (call each frame)
    pub fn update_camera(&mut self, queue: &wgpu::Queue, proj_view: &Mat4) {
        self.proj_view = *proj_view;
        // Compute MVP per object and upload
        for obj in &self.objects {
            let mvp = self.proj_view * obj.model;
            queue.write_buffer(&obj.uniform_buffer, 0, bytemuck::bytes_of(&[mvp]));
        }
    }

    /// Render all objects
    pub fn render<'a>(&'a self, rpass: &mut wgpu::RenderPass<'a>) {
        rpass.set_pipeline(&self.pipeline);
        for obj in &self.objects {
            rpass.set_bind_group(0, &obj.uniform_bind_group, &[]);
            rpass.set_bind_group(1, &obj.texture_bind_group, &[]);
            rpass.set_vertex_buffer(0, obj.vertex_buffer.slice(..));
            rpass.set_index_buffer(obj.index_buffer.slice(..), wgpu::IndexFormat::Uint32);
            rpass.draw_indexed(0..obj.index_count, 0, 0..1);
        }
    }
}
