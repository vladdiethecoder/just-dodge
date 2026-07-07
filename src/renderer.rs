// Arena renderer: rigid textured meshes (rock, gate, pillar, ground) + a
// skinned mannequin driven by MotionBricks-decoded joint matrices.
// Camera: orbital with mouse drag + scroll zoom.

use crate::asset;
use glam::Mat4;
use wgpu::util::DeviceExt;

pub struct MeshObject {
    pub vertex_buffer: wgpu::Buffer,
    pub index_buffer: wgpu::Buffer,
    pub index_count: u32,
    pub uniform_buffer: wgpu::Buffer,
    pub uniform_bind_group: wgpu::BindGroup,
    pub texture_bind_group: wgpu::BindGroup,
    pub model: Mat4,
}

pub struct SkinnedObject {
    pub vertex_buffer: wgpu::Buffer,
    pub index_buffer: wgpu::Buffer,
    pub index_count: u32,
    pub uniform_buffer: wgpu::Buffer,
    pub uniform_bind_group: wgpu::BindGroup,
    pub texture_bind_group: wgpu::BindGroup,
    pub joint_buffer: wgpu::Buffer,
    pub joint_bind_group: wgpu::BindGroup,
    pub model: Mat4,
}

pub struct Renderer {
    pub pipeline: wgpu::RenderPipeline,
    pub skin_pipeline: wgpu::RenderPipeline,
    pub debug_pipeline: wgpu::RenderPipeline,
    pub objects: Vec<MeshObject>,
    pub skinned: Vec<SkinnedObject>,
    pub depth_view: wgpu::TextureView,
    proj_view: Mat4,
    debug_ub: wgpu::Buffer,
    debug_ubg: wgpu::BindGroup,
    debug_vb: Option<wgpu::Buffer>,
    debug_line_count: u32,
    /// Parent index (-1 = root) for each of the 24 mannequin bones.
    pub bone_parents: Vec<i32>,
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
        wgpu::TexelCopyTextureInfo {
            texture: &texture,
            mip_level: 0,
            origin: wgpu::Origin3d::ZERO,
            aspect: wgpu::TextureAspect::All,
        },
        &img,
        wgpu::TexelCopyBufferLayout {
            offset: 0,
            bytes_per_row: Some(4 * width),
            rows_per_image: Some(height),
        },
        texture_size,
    );

    let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
    let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
        address_mode_u: wgpu::AddressMode::Repeat,
        address_mode_v: wgpu::AddressMode::Repeat,
        address_mode_w: wgpu::AddressMode::Repeat,
        mag_filter: wgpu::FilterMode::Linear,
        min_filter: wgpu::FilterMode::Linear,
        mipmap_filter: wgpu::MipmapFilterMode::Linear,
        ..Default::default()
    });
    (texture, view, sampler)
}

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
        interleaved.extend_from_slice(&[
            mesh.vertices[vi],
            mesh.vertices[vi + 1],
            mesh.vertices[vi + 2],
        ]);
        interleaved.extend_from_slice(&[
            mesh.normals[vi],
            mesh.normals[vi + 1],
            mesh.normals[vi + 2],
        ]);
        interleaved.extend_from_slice(&[mesh.uvs[uvi], mesh.uvs[uvi + 1]]);
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
    let s = 10.0f32;
    let vertices: [f32; 8 * 4] = [
        // pos(x,y,z)          normal(0,1,0)    uv
        -s, 0.0, -s, 0.0, 1.0, 0.0, 0.0, 20.0, s, 0.0, -s, 0.0, 1.0, 0.0, 20.0, 20.0, s, 0.0, s,
        0.0, 1.0, 0.0, 20.0, 0.0, -s, 0.0, s, 0.0, 1.0, 0.0, 0.0, 0.0,
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

fn build_ground_texture(
    device: &wgpu::Device,
    queue: &wgpu::Queue,
) -> (wgpu::TextureView, wgpu::Sampler) {
    // Procedural checkerboard ground texture (256x256)
    let size = 256u32;
    let mut pixels = vec![0u8; (size * size * 4) as usize];
    for y in 0..size {
        for x in 0..size {
            let i = ((y * size + x) * 4) as usize;
            let checker = ((x / 32 + y / 32) % 2) == 0;
            if checker {
                pixels[i] = 150;
                pixels[i + 1] = 140;
                pixels[i + 2] = 120;
                pixels[i + 3] = 255;
            } else {
                pixels[i] = 110;
                pixels[i + 1] = 100;
                pixels[i + 2] = 85;
                pixels[i + 3] = 255;
            }
        }
    }
    let tex = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("Ground Tex"),
        size: wgpu::Extent3d {
            width: size,
            height: size,
            depth_or_array_layers: 1,
        },
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Rgba8UnormSrgb,
        usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
        view_formats: &[],
    });
    queue.write_texture(
        wgpu::TexelCopyTextureInfo {
            texture: &tex,
            mip_level: 0,
            origin: wgpu::Origin3d::ZERO,
            aspect: wgpu::TextureAspect::All,
        },
        &pixels,
        wgpu::TexelCopyBufferLayout {
            offset: 0,
            bytes_per_row: Some(4 * size),
            rows_per_image: Some(size),
        },
        wgpu::Extent3d {
            width: size,
            height: size,
            depth_or_array_layers: 1,
        },
    );
    let view = tex.create_view(&wgpu::TextureViewDescriptor::default());
    let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
        address_mode_u: wgpu::AddressMode::Repeat,
        address_mode_v: wgpu::AddressMode::Repeat,
        address_mode_w: wgpu::AddressMode::Repeat,
        mag_filter: wgpu::FilterMode::Linear,
        min_filter: wgpu::FilterMode::Linear,
        mipmap_filter: wgpu::MipmapFilterMode::Linear,
        ..Default::default()
    });
    (view, sampler)
}

impl Renderer {
    pub fn new(
        device: &wgpu::Device,
        queue: &wgpu::Queue,
        config: &wgpu::SurfaceConfiguration,
    ) -> Self {
        let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("Shader"),
            source: wgpu::ShaderSource::Wgsl(include_str!("shader.wgsl").into()),
        });

        let assets = concat!(env!("CARGO_MANIFEST_DIR"), "/assets");

        // Bind group layouts
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

        // --- Pipeline ---
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

        let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("Pipeline Layout"),
            bind_group_layouts: &[Some(&uniform_bgl), Some(&texture_bgl)],
            immediate_size: 0,
        });

        let vertex_layouts = vec![Some(vertex_layout)];
        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("Pipeline"),
            cache: None,
            layout: Some(&pipeline_layout),
            vertex: wgpu::VertexState {
                module: &shader,
                entry_point: Some("vs_main"),
                buffers: &vertex_layouts,
                compilation_options: wgpu::PipelineCompilationOptions::default(),
            },
            fragment: Some(wgpu::FragmentState {
                module: &shader,
                entry_point: Some("fs_main"),
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
                depth_write_enabled: Some(true),
                depth_compare: Some(wgpu::CompareFunction::Less),
                stencil: wgpu::StencilState::default(),
                bias: wgpu::DepthBiasState::default(),
            }),
            multisample: wgpu::MultisampleState::default(),
            multiview_mask: None,
        });

        // --- Skinned pipeline (skin.wgsl) ---
        let skin_shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("Skin Shader"),
            source: wgpu::ShaderSource::Wgsl(include_str!("skin.wgsl").into()),
        });
        // group(2) = storage buffer of joint matrices (read in vertex shader)
        let joint_bgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("Joint BGL"),
            entries: &[wgpu::BindGroupLayoutEntry {
                binding: 0,
                visibility: wgpu::ShaderStages::VERTEX,
                ty: wgpu::BindingType::Buffer {
                    ty: wgpu::BufferBindingType::Storage { read_only: true },
                    has_dynamic_offset: false,
                    min_binding_size: None,
                },
                count: None,
            }],
        });
        let skin_vertex_layout = wgpu::VertexBufferLayout {
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
                    format: wgpu::VertexFormat::Float32x4,
                    offset: 48,
                    shader_location: 4,
                },
            ],
        };
        let skin_pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("Skin Pipeline Layout"),
            bind_group_layouts: &[Some(&uniform_bgl), Some(&texture_bgl), Some(&joint_bgl)],
            immediate_size: 0,
        });
        let skin_vertex_layouts = vec![Some(skin_vertex_layout)];
        let skin_pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("Skin Pipeline"),
            cache: None,
            layout: Some(&skin_pipeline_layout),
            vertex: wgpu::VertexState {
                module: &skin_shader,
                entry_point: Some("vs_main"),
                buffers: &skin_vertex_layouts,
                compilation_options: wgpu::PipelineCompilationOptions::default(),
            },
            fragment: Some(wgpu::FragmentState {
                module: &skin_shader,
                entry_point: Some("fs_main"),
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
                depth_write_enabled: Some(true),
                depth_compare: Some(wgpu::CompareFunction::Less),
                stencil: wgpu::StencilState::default(),
                bias: wgpu::DepthBiasState::default(),
            }),
            multisample: wgpu::MultisampleState::default(),
            multiview_mask: None,
        });

        // --- Debug bone overlay pipeline (solid-color lines) ---
        let debug_shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("Debug Shader"),
            source: wgpu::ShaderSource::Wgsl(include_str!("debug.wgsl").into()),
        });
        let debug_vl = wgpu::VertexBufferLayout {
            array_stride: 24,
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
            ],
        };
        let debug_pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("Debug Pipeline Layout"),
            bind_group_layouts: &[Some(&uniform_bgl)],
            immediate_size: 0,
        });
        let debug_pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("Debug Pipeline"),
            cache: None,
            layout: Some(&debug_pipeline_layout),
            vertex: wgpu::VertexState {
                module: &debug_shader,
                entry_point: Some("vs_main"),
                buffers: &[Some(debug_vl)],
                compilation_options: wgpu::PipelineCompilationOptions::default(),
            },
            fragment: Some(wgpu::FragmentState {
                module: &debug_shader,
                entry_point: Some("fs_main"),
                targets: &[Some(wgpu::ColorTargetState {
                    format: config.format,
                    blend: Some(wgpu::BlendState::ALPHA_BLENDING),
                    write_mask: wgpu::ColorWrites::ALL,
                })],
                compilation_options: wgpu::PipelineCompilationOptions::default(),
            }),
            primitive: wgpu::PrimitiveState {
                topology: wgpu::PrimitiveTopology::LineList,
                cull_mode: None,
                front_face: wgpu::FrontFace::Ccw,
                ..Default::default()
            },
            depth_stencil: Some(wgpu::DepthStencilState {
                format: wgpu::TextureFormat::Depth32Float,
                depth_write_enabled: Some(false),
                depth_compare: Some(wgpu::CompareFunction::Less),
                stencil: wgpu::StencilState::default(),
                bias: wgpu::DepthBiasState::default(),
            }),
            multisample: wgpu::MultisampleState::default(),
            multiview_mask: None,
        });
        let debug_ub = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("Debug UB"),
            size: 64,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let debug_ubg = device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("Debug UBG"),
            layout: &uniform_bgl,
            entries: &[wgpu::BindGroupEntry {
                binding: 0,
                resource: debug_ub.as_entire_binding(),
            }],
        });

        // --- Depth texture ---
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

        // --- Build all rigid objects ---
        let mut objects = Vec::new();

        // Arena layout (circular, ~3m radius):
        //   Rock at (0,0,-3), Gate at (2.6,0,1.5), Pillar at (-2.6,0,1.5)
        // Mannequin at center (0,0,0)
        struct ObjCfg {
            bin: &'static str,
            tex: &'static str,
            model: Mat4,
        }
        // Arena assets stripped for baseline: ground + sky only.
        let cfgs = [
            ObjCfg {
                bin: "arena_rock.bin",
                tex: "arena_rock_0.png",
                model: Mat4::from_translation(glam::vec3(0.0, -0.2, -3.0)),
            },
            ObjCfg {
                bin: "lintel_gate.bin",
                tex: "lintel_gate_0.jpg",
                model: Mat4::from_translation(glam::vec3(2.6, -0.1, 1.5)),
            },
            ObjCfg {
                bin: "rune_pillar.bin",
                tex: "rune_pillar_0.jpg",
                model: Mat4::from_translation(glam::vec3(-2.6, 0.0, 1.5)),
            },
        ];

        for cfg in cfgs {
            let mesh = asset::load_binary(&format!("{}/{}", assets, cfg.bin))
                .unwrap_or_else(|e| panic!("Failed to load {}: {e}", cfg.bin));
            let (vb, ib, ic) = build_mesh_buffers(device, &mesh, cfg.bin);
            println!(
                "  {}: {} verts, {} idxs",
                cfg.bin,
                mesh.vertices.len() / 3,
                mesh.indices.len()
            );

            // Per-object uniform (MVP = proj_view * model, updated each frame)
            let ub = device.create_buffer(&wgpu::BufferDescriptor {
                label: Some(&format!("UB {}", cfg.bin)),
                size: 64,
                usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
            let ubg = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some(&format!("UBG {}", cfg.bin)),
                layout: &uniform_bgl,
                entries: &[wgpu::BindGroupEntry {
                    binding: 0,
                    resource: ub.as_entire_binding(),
                }],
            });

            let (_t, tv, ts) = load_texture(device, queue, &format!("{}/{}", assets, cfg.tex));
            let tbg = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some(&format!("TBG {}", cfg.bin)),
                layout: &texture_bgl,
                entries: &[
                    wgpu::BindGroupEntry {
                        binding: 0,
                        resource: wgpu::BindingResource::TextureView(&tv),
                    },
                    wgpu::BindGroupEntry {
                        binding: 1,
                        resource: wgpu::BindingResource::Sampler(&ts),
                    },
                ],
            });

            objects.push(MeshObject {
                vertex_buffer: vb,
                index_buffer: ib,
                index_count: ic,
                uniform_buffer: ub,
                uniform_bind_group: ubg,
                texture_bind_group: tbg,
                model: cfg.model,
            });
        }

        // --- Ground plane ---
        {
            let (gv, gi, gc) = build_procedural_ground(device);
            let (gtv, gts) = build_ground_texture(device, queue);
            let g_model = Mat4::IDENTITY;
            let ub = device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("UB Ground"),
                size: 64,
                usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
            let ubg = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("UBG Ground"),
                layout: &uniform_bgl,
                entries: &[wgpu::BindGroupEntry {
                    binding: 0,
                    resource: ub.as_entire_binding(),
                }],
            });
            let tbg = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("TBG Ground"),
                layout: &texture_bgl,
                entries: &[
                    wgpu::BindGroupEntry {
                        binding: 0,
                        resource: wgpu::BindingResource::TextureView(&gtv),
                    },
                    wgpu::BindGroupEntry {
                        binding: 1,
                        resource: wgpu::BindingResource::Sampler(&gts),
                    },
                ],
            });
            objects.push(MeshObject {
                vertex_buffer: gv,
                index_buffer: gi,
                index_count: gc,
                uniform_buffer: ub,
                uniform_bind_group: ubg,
                texture_bind_group: tbg,
                model: g_model,
            });
        }

        // --- Skinned characters ---
        let mut skinned: Vec<SkinnedObject> = Vec::new();

        let mut bone_parents: Vec<i32> = Vec::new();

        for (bin_name, tex_name, pos) in [
            ("mannequin_male.bin", "mannequin_male_0.png", glam::vec3(0.0, 0.0, 1.0)),
            ("mannequin_female.bin", "mannequin_female_0.png", glam::vec3(0.0, 0.0, -1.0)),
        ] {
            let skin_path = format!("{}/characters/{}", assets, bin_name);
            if let Ok(mesh) = asset::load_skinned(&skin_path) {
                if bone_parents.is_empty() {
                    bone_parents = mesh.bones.iter().map(|b| b.parent).collect();
                }
                let vc = mesh.vertices.len();
            let mut interleaved: Vec<u8> =
                Vec::with_capacity(vc * std::mem::size_of::<asset::SkinnedVertex>());
            for v in &mesh.vertices {
                interleaved.extend_from_slice(bytemuck::bytes_of(&v.position));
                interleaved.extend_from_slice(bytemuck::bytes_of(&v.normal));
                interleaved.extend_from_slice(bytemuck::bytes_of(&v.uv));
                interleaved.extend_from_slice(bytemuck::bytes_of(&v.joint_indices));
                interleaved.extend_from_slice(bytemuck::bytes_of(&v.joint_weights));
            }
            let svb = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("Skin VB"),
                contents: &interleaved,
                usage: wgpu::BufferUsages::VERTEX,
            });
            let sib = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("Skin IB"),
                contents: bytemuck::cast_slice(&mesh.indices),
                usage: wgpu::BufferUsages::INDEX,
            });
            let sub = device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("Skin UB"),
                size: 64,
                usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
            let subg = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("Skin UBG"),
                layout: &uniform_bgl,
                entries: &[wgpu::BindGroupEntry {
                    binding: 0,
                    resource: sub.as_entire_binding(),
                }],
            });
            let (_st, stv, sts) =
                load_texture(device, queue, &format!("{}/{}", assets, tex_name));
            let stbg = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("Skin TBG"),
                layout: &texture_bgl,
                entries: &[
                    wgpu::BindGroupEntry {
                        binding: 0,
                        resource: wgpu::BindingResource::TextureView(&stv),
                    },
                    wgpu::BindGroupEntry {
                        binding: 1,
                        resource: wgpu::BindingResource::Sampler(&sts),
                    },
                ],
            });
            // joint storage buffer: 24 mat4x4<f32>
            let joint_buffer = device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("Joint Buffer"),
                size: (24 * std::mem::size_of::<glam::Mat4>()) as u64,
                usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
            let joint_bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("Joint BG"),
                layout: &joint_bgl,
                entries: &[wgpu::BindGroupEntry {
                    binding: 0,
                    resource: joint_buffer.as_entire_binding(),
                }],
            });
            println!(
                "  skinned mannequin: {} verts, {} idxs",
                vc,
                mesh.indices.len()
            );
            skinned.push(SkinnedObject {
                vertex_buffer: svb,
                index_buffer: sib,
                index_count: mesh.indices.len() as u32,
                uniform_buffer: sub,
                uniform_bind_group: subg,
                texture_bind_group: stbg,
                joint_buffer,
                joint_bind_group,
                model: Mat4::from_translation(pos),
            });
            }
        }

        Self {
            pipeline,
            skin_pipeline,
            debug_pipeline,
            objects,
            skinned,
            depth_view,
            proj_view: Mat4::IDENTITY,
            debug_ub,
            debug_ubg,
            debug_vb: None,
            debug_line_count: 0,
            bone_parents,
        }
    }

    /// Upload bone line vertices from a frame of 24 skinning matrices.
    pub fn update_debug_bones(&mut self, device: &wgpu::Device, queue: &wgpu::Queue, joints: &[Mat4; 24]) {
        // Extract joint world positions (translation component of each matrix)
        let mut pos = [glam::Vec3::ZERO; 24];
        for i in 0..24 {
            pos[i] = joints[i].w_axis.truncate();
        }
        // Build line vertices: each parent-child pair = 2 vertices
        let mut verts: Vec<f32> = Vec::with_capacity(24 * 2 * 6);
        for i in 0..24 {
            let p = if i < self.bone_parents.len() { self.bone_parents[i] } else { -1 };
            if p >= 0 && (p as usize) < 24 {
                // From child (red) to parent (white)
                verts.extend_from_slice(pos[i].to_array().as_ref()); // position
                verts.extend_from_slice(&[1.0, 0.2, 0.2]); // red
                verts.extend_from_slice(pos[p as usize].to_array().as_ref()); // position
                verts.extend_from_slice(&[1.0, 1.0, 1.0]); // white
            }
        }
        self.debug_line_count = (verts.len() / 6) as u32;
        if self.debug_line_count == 0 { return; }
        let vb = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("Debug VB"),
            contents: bytemuck::cast_slice(&verts),
            usage: wgpu::BufferUsages::VERTEX,
        });
        self.debug_vb = Some(vb);
    }

    /// Draw the bone overlay (call after render_skinned).
    pub fn render_debug_overlay<'a>(&'a self, rpass: &mut wgpu::RenderPass<'a>) {
        let Some(ref vb) = self.debug_vb else { return };
        if self.debug_line_count == 0 { return; }
        let mvp = self.proj_view;
        // Upload MVP (can't use queue in render pass; use write_buffer before calling this)
        // Instead, we write MVP in the update method. For now, the overlay uses
        // the same proj_view as everything else.
        rpass.set_pipeline(&self.debug_pipeline);
        rpass.set_bind_group(0, &self.debug_ubg, &[]);
        rpass.set_vertex_buffer(0, vb.slice(..));
        rpass.draw(0..self.debug_line_count, 0..1);
    }

    /// Write a frame's 24 skinning matrices into the joint storage buffer.
    pub fn update_skin_joints(&self, queue: &wgpu::Queue, joints: &[Mat4; 24]) {
        for s in &self.skinned {
            // Column-major f32 array of 24 mat4 (each 16 f32).
            let mut data = Vec::with_capacity(24 * 16);
            for m in joints.iter() {
                data.extend_from_slice(&m.to_cols_array());
            }
            queue.write_buffer(&s.joint_buffer, 0, bytemuck::cast_slice(&data));
        }
    }

    /// Write skinning matrices to a specific skinned object by index.
    pub fn update_skin_joints_indexed(&self, queue: &wgpu::Queue, idx: usize, joints: &[Mat4; 24]) {
        if let Some(s) = self.skinned.get(idx) {
            let mut data = Vec::with_capacity(24 * 16);
            for m in joints.iter() {
                data.extend_from_slice(&m.to_cols_array());
            }
            queue.write_buffer(&s.joint_buffer, 0, bytemuck::cast_slice(&data));
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
        // Mannequin uniform (identity model; skinning happens in the vertex shader)
        for s in &self.skinned {
            let mvp = self.proj_view * s.model;
            queue.write_buffer(&s.uniform_buffer, 0, bytemuck::bytes_of(&[mvp]));
        }
    }

    /// Render all rigid objects
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

    /// Render the skinned mannequin (no-op if mesh failed to load)
    pub fn render_skinned<'a>(&'a self, rpass: &mut wgpu::RenderPass<'a>) {
        for s in &self.skinned {
            rpass.set_pipeline(&self.skin_pipeline);
            rpass.set_bind_group(0, &s.uniform_bind_group, &[]);
            rpass.set_bind_group(1, &s.texture_bind_group, &[]);
            rpass.set_bind_group(2, &s.joint_bind_group, &[]);
            rpass.set_vertex_buffer(0, s.vertex_buffer.slice(..));
            rpass.set_index_buffer(s.index_buffer.slice(..), wgpu::IndexFormat::Uint32);
            rpass.draw_indexed(0..s.index_count, 0, 0..1);
        }
    }

    /// Recreate the depth buffer after a window resize.
    pub fn resize(&mut self, device: &wgpu::Device, config: &wgpu::SurfaceConfiguration) {
        let depth_texture = device.create_texture(&wgpu::TextureDescriptor {
            label: Some("Depth Texture"),
            size: wgpu::Extent3d {
                width: config.width.max(1),
                height: config.height.max(1),
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::Depth32Float,
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
            view_formats: &[],
        });
        self.depth_view = depth_texture.create_view(&wgpu::TextureViewDescriptor::default());
    }
}
