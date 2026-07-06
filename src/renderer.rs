use wgpu::util::DeviceExt;
use crate::asset;

pub struct Renderer {
    pub pipeline: wgpu::RenderPipeline,
    // Arena mesh
    arena_vertex: wgpu::Buffer,
    arena_index: wgpu::Buffer,
    arena_index_count: u32,
    arena_texture_bg: wgpu::BindGroup,
    // Mannequin mesh
    mannequin_vertex: wgpu::Buffer,
    mannequin_index: wgpu::Buffer,
    mannequin_index_count: u32,
    mannequin_texture_bg: wgpu::BindGroup,
    // Shared
    pub uniform_buffer: wgpu::Buffer,
    shared_bg: wgpu::BindGroup,
    pub depth_view: wgpu::TextureView,
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
    let texture_size = wgpu::Extent3d {
        width,
        height,
        depth_or_array_layers: 1,
    };

    let texture = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("Base Color Texture"),
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
        wgpu::ImageDataLayout {
            offset: 0,
            bytes_per_row: Some(4 * width),
            rows_per_image: Some(height),
        },
        texture_size,
    );

    let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
    let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
        label: Some("Texture Sampler"),
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

/// Build interleaved vertex buffer from mesh data
fn build_mesh_buffers(
    device: &wgpu::Device,
    mesh: &asset::MeshData,
    label: &str,
) -> (wgpu::Buffer, wgpu::Buffer, u32) {
    let vc = mesh.vertices.len() / 3;
    let mut interleaved = Vec::with_capacity(vc * 8);
    for i in 0..vc {
        let vi = i * 3;
        let uvi = i * 2;
        interleaved.push(mesh.vertices[vi]);
        interleaved.push(mesh.vertices[vi + 1]);
        interleaved.push(mesh.vertices[vi + 2]);
        interleaved.push(mesh.normals[vi]);
        interleaved.push(mesh.normals[vi + 1]);
        interleaved.push(mesh.normals[vi + 2]);
        interleaved.push(mesh.uvs[uvi]);
        interleaved.push(mesh.uvs[uvi + 1]);
    }
    let vb = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some(&format!("{} VB", label)),
        contents: bytemuck::cast_slice(&interleaved),
        usage: wgpu::BufferUsages::VERTEX,
    });
    let ib = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some(&format!("{} IB", label)),
        contents: bytemuck::cast_slice(&mesh.indices),
        usage: wgpu::BufferUsages::INDEX,
    });
    (vb, ib, mesh.indices.len() as u32)
}

fn build_texture_bind_group(
    device: &wgpu::Device,
    layout: &wgpu::BindGroupLayout,
    tex_view: &wgpu::TextureView,
    tex_sampler: &wgpu::Sampler,
    label: &str,
) -> wgpu::BindGroup {
    device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some(&format!("{} BG", label)),
        layout,
        entries: &[
            wgpu::BindGroupEntry {
                binding: 0,
                resource: wgpu::BindingResource::TextureView(tex_view),
            },
            wgpu::BindGroupEntry {
                binding: 1,
                resource: wgpu::BindingResource::Sampler(tex_sampler),
            },
        ],
    })
}

impl Renderer {
    pub fn new(
        device: &wgpu::Device,
        config: &wgpu::SurfaceConfiguration,
        queue: &wgpu::Queue,
    ) -> Self {
        // --- Shader ---
        let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("Shader"),
            source: wgpu::ShaderSource::Wgsl(include_str!("shader.wgsl").into()),
        });

        // --- Load meshes ---
        let assets = concat!(env!("CARGO_MANIFEST_DIR"), "/assets");

        let arena_mesh = asset::load_binary(&format!("{}/arena_rock.bin", assets))
            .expect("Failed to load arena mesh");
        let (arena_vb, arena_ib, arena_ic) = build_mesh_buffers(device, &arena_mesh, "Arena");
        println!("Arena: {} verts, {} idxs", arena_mesh.vertices.len() / 3, arena_mesh.indices.len());

        let mannequin_mesh = asset::load_binary(&format!("{}/mannequin_male.bin", assets))
            .expect("Failed to load mannequin mesh");
        let (man_vb, man_ib, man_ic) = build_mesh_buffers(device, &mannequin_mesh, "Mannequin");
        println!("Mannequin: {} verts, {} idxs", mannequin_mesh.vertices.len() / 3, mannequin_mesh.indices.len());

        // --- Uniform buffer (shared MVP) ---
        let uniform_buffer = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("Uniform Buffer"),
            size: 64,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        let uniform_bgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("Uniform BGL"),
            entries: &[wgpu::BindGroupLayoutEntry {
                binding: 0,
                visibility: wgpu::ShaderStages::VERTEX,
                ty: wgpu::BindingType::Buffer {
                    ty: wgpu::BufferBindingType::Uniform,
                    has_dynamic_offset: false,
                    min_binding_size: None,
                },
                count: None,
            }],
        });

        let shared_bg = device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("Shared Uniform BG"),
            layout: &uniform_bgl,
            entries: &[wgpu::BindGroupEntry {
                binding: 0,
                resource: uniform_buffer.as_entire_binding(),
            }],
        });

        // --- Texture bind group layout ---
        let texture_bgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("Texture BGL"),
            entries: &[
                wgpu::BindGroupLayoutEntry {
                    binding: 0,
                    visibility: wgpu::ShaderStages::FRAGMENT,
                    ty: wgpu::BindingType::Texture {
                        sample_type: wgpu::TextureSampleType::Float { filterable: true },
                        view_dimension: wgpu::TextureViewDimension::D2,
                        multisampled: false,
                    },
                    count: None,
                },
                wgpu::BindGroupLayoutEntry {
                    binding: 1,
                    visibility: wgpu::ShaderStages::FRAGMENT,
                    ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),
                    count: None,
                },
            ],
        });

        // --- Load textures ---
        let (_at, arena_tex_view, arena_sampler) = load_texture(
            device, queue,
            &format!("{}/arena_rock_0.png", assets),
        );
        let arena_texture_bg = build_texture_bind_group(device, &texture_bgl, &arena_tex_view, &arena_sampler, "ArenaTex");

        let (_mt, man_tex_view, man_sampler) = load_texture(
            device, queue,
            &format!("{}/mannequin_male_0.png", assets),
        );
        let mannequin_texture_bg = build_texture_bind_group(device, &texture_bgl, &man_tex_view, &man_sampler, "MannequinTex");

        // --- Vertex layout ---
        let vertex_layout = wgpu::VertexBufferLayout {
            array_stride: 8 * 4,
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
        };

        // --- Pipeline ---
        let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("Pipeline Layout"),
            bind_group_layouts: &[&uniform_bgl, &texture_bgl],
            push_constant_ranges: &[],
        });

        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("Pipeline"),
            cache: None,
            layout: Some(&pipeline_layout),
            vertex: wgpu::VertexState {
                module: &shader,
                entry_point: "vs_main",
                buffers: &[vertex_layout],
                compilation_options: wgpu::PipelineCompilationOptions::default(),
            },
            fragment: Some(wgpu::FragmentState {
                module: &shader,
                entry_point: "fs_main",
                targets: &[Some(wgpu::ColorTargetState {
                    format: config.format,
                    blend: Some(wgpu::BlendState::REPLACE),
                    write_mask: wgpu::ColorWrites::ALL,
                })],
                compilation_options: wgpu::PipelineCompilationOptions::default(),
            }),
            primitive: wgpu::PrimitiveState {
                topology: wgpu::PrimitiveTopology::TriangleList,
                cull_mode: Some(wgpu::Face::Back),
                front_face: wgpu::FrontFace::Ccw,
                ..Default::default()
            },
            depth_stencil: Some(wgpu::DepthStencilState {
                format: wgpu::TextureFormat::Depth32Float,
                depth_write_enabled: true,
                depth_compare: wgpu::CompareFunction::Less,
                stencil: wgpu::StencilState::default(),
                bias: wgpu::DepthBiasState::default(),
            }),
            multisample: wgpu::MultisampleState::default(),
            multiview: None,
        });

        let depth_texture = device.create_texture(&wgpu::TextureDescriptor {
            label: Some("Depth Texture"),
            size: wgpu::Extent3d {
                width: config.width,
                height: config.height,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Depth32Float,
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
            view_formats: &[],
        });
        let depth_view = depth_texture.create_view(&wgpu::TextureViewDescriptor::default());

        Self {
            pipeline,
            arena_vertex: arena_vb,
            arena_index: arena_ib,
            arena_index_count: arena_ic,
            arena_texture_bg,
            mannequin_vertex: man_vb,
            mannequin_index: man_ib,
            mannequin_index_count: man_ic,
            mannequin_texture_bg,
            uniform_buffer,
            shared_bg,
            depth_view,
        }
    }

    pub fn render_arena<'a>(&'a self, rpass: &mut wgpu::RenderPass<'a>) {
        rpass.set_pipeline(&self.pipeline);
        rpass.set_bind_group(0, &self.shared_bg, &[]);
        rpass.set_bind_group(1, &self.arena_texture_bg, &[]);
        rpass.set_vertex_buffer(0, self.arena_vertex.slice(..));
        rpass.set_index_buffer(self.arena_index.slice(..), wgpu::IndexFormat::Uint32);
        rpass.draw_indexed(0..self.arena_index_count, 0, 0..1);
    }

    pub fn render_mannequin<'a>(&'a self, rpass: &mut wgpu::RenderPass<'a>) {
        rpass.set_pipeline(&self.pipeline);
        rpass.set_bind_group(0, &self.shared_bg, &[]);
        rpass.set_bind_group(1, &self.mannequin_texture_bg, &[]);
        rpass.set_vertex_buffer(0, self.mannequin_vertex.slice(..));
        rpass.set_index_buffer(self.mannequin_index.slice(..), wgpu::IndexFormat::Uint32);
        rpass.draw_indexed(0..self.mannequin_index_count, 0, 0..1);
    }
}
