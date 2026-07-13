// Arena renderer: rigid textured meshes (rock, gate, pillar, ground) + a
// skinned C0 pose carrier driven by per-actor skinning matrices.
// Camera: deterministic player-head first-person view.

use crate::asset;
use glam::{Mat4, Vec3};
use wgpu::util::DeviceExt;

/// Canonical model transform for C0-POSE-CARRIER-001. The cooked carrier is
/// already Y-up; its reference-pose authority supplies this uniform scale.
pub fn skinned_correct_model() -> Mat4 {
    Mat4::from_scale(glam::Vec3::splat(0.918_949_97))
}

/// Pure presentation transform for the W0 sword. The hilt is placed in the
/// lower-right first-person frame; no combat or cleanbox state is read here.
pub fn first_person_weapon_model(eye: Vec3, forward: Vec3) -> Mat4 {
    let forward = forward.normalize();
    // `look_at_lh` maps this basis direction to visual screen-right.
    let screen_right = Vec3::Y.cross(forward).normalize();
    let blade = (forward * 0.78 + Vec3::Y * 0.62).normalize();
    let thickness = blade.cross(screen_right).normalize();
    // Keep the source-metric hilt in frame rather than scaling the accepted mesh.
    let hilt = eye + forward * 0.72 + screen_right * 0.24 - Vec3::Y * 0.35;
    Mat4::from_cols(
        screen_right.extend(0.0),
        thickness.extend(0.0),
        blade.extend(0.0),
        hilt.extend(1.0),
    )
}

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
    pub bone_count: usize,
    pub model: Mat4,
}

pub struct Renderer {
    pub pipeline: wgpu::RenderPipeline,
    pub skin_pipeline: wgpu::RenderPipeline,
    pub debug_pipeline: wgpu::RenderPipeline,
    pub objects: Vec<MeshObject>,
    /// Accepted W0 longsword, rendered only through the first-person path.
    pub first_person_weapon: MeshObject,
    pub skinned: Vec<SkinnedObject>,
    pub depth_view: wgpu::TextureView,
    proj_view: Mat4,
    debug_ub: wgpu::Buffer,
    debug_ubg: wgpu::BindGroup,
    debug_vb: Option<wgpu::Buffer>,
    debug_line_count: u32,
    hitbox_vb: Option<wgpu::Buffer>,
    hitbox_line_count: u32,
    /// Parent index (-1 = root) for the active skinned carrier hierarchy.
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

fn build_solid_mesh_object(
    device: &wgpu::Device,
    queue: &wgpu::Queue,
    uniform_bgl: &wgpu::BindGroupLayout,
    texture_bgl: &wgpu::BindGroupLayout,
    mesh_path: &str,
    label: &str,
    rgba: [u8; 4],
) -> MeshObject {
    let mesh = asset::load_binary(mesh_path)
        .unwrap_or_else(|error| panic!("failed to load {label} mesh {mesh_path}: {error}"));
    let (vertex_buffer, index_buffer, index_count) = build_mesh_buffers(device, &mesh, label);
    let uniform_buffer = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some(&format!("{label} UB")),
        size: 64,
        usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });
    let uniform_bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some(&format!("{label} UBG")),
        layout: uniform_bgl,
        entries: &[wgpu::BindGroupEntry {
            binding: 0,
            resource: uniform_buffer.as_entire_binding(),
        }],
    });
    let (texture_view, sampler) = build_solid_texture(device, queue, rgba);
    let texture_bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some(&format!("{label} TBG")),
        layout: texture_bgl,
        entries: &[
            wgpu::BindGroupEntry {
                binding: 0,
                resource: wgpu::BindingResource::TextureView(&texture_view),
            },
            wgpu::BindGroupEntry {
                binding: 1,
                resource: wgpu::BindingResource::Sampler(&sampler),
            },
        ],
    });
    MeshObject {
        vertex_buffer,
        index_buffer,
        index_count,
        uniform_buffer,
        uniform_bind_group,
        texture_bind_group,
        model: Mat4::IDENTITY,
    }
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

/// Explicit untextured-carrier fallback. C0 currently has no accepted PBR
/// texture contract, so this is a declared solid color rather than a disguised
/// substitute texture.
fn build_solid_texture(
    device: &wgpu::Device,
    queue: &wgpu::Queue,
    rgba: [u8; 4],
) -> (wgpu::TextureView, wgpu::Sampler) {
    let texture = device.create_texture(&wgpu::TextureDescriptor {
        label: Some("C0 carrier fallback texture"),
        size: wgpu::Extent3d {
            width: 1,
            height: 1,
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
            texture: &texture,
            mip_level: 0,
            origin: wgpu::Origin3d::ZERO,
            aspect: wgpu::TextureAspect::All,
        },
        &rgba,
        wgpu::TexelCopyBufferLayout {
            offset: 0,
            bytes_per_row: Some(4),
            rows_per_image: Some(1),
        },
        wgpu::Extent3d {
            width: 1,
            height: 1,
            depth_or_array_layers: 1,
        },
    );
    let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
    let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
        mag_filter: wgpu::FilterMode::Linear,
        min_filter: wgpu::FilterMode::Linear,
        mipmap_filter: wgpu::MipmapFilterMode::Nearest,
        ..Default::default()
    });
    (view, sampler)
}

impl Renderer {
    pub fn new(
        device: &wgpu::Device,
        queue: &wgpu::Queue,
        config: &wgpu::SurfaceConfiguration,
        minimal_scene: bool,
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
        let debug_pipeline_layout =
            device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
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

        if !minimal_scene {
            // Arena layout (circular, ~3m radius):
            //   Rock at (0,0,-3), Gate at (2.6,0,1.5), Pillar at (-2.6,0,1.5)
            // Mannequin at center (0,0,0)
            struct ObjCfg {
                bin: &'static str,
                tex: &'static str,
                model: Mat4,
            }
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
        }

        // --- Ground plane ---
        if !minimal_scene {
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
        }

        // --- Skinned C0 pose carriers ---
        let mut skinned: Vec<SkinnedObject> = Vec::new();
        let skin_path = format!(
            "{assets}/source/meshy/c0_base_fighter/pose_carrier_001/cooked/c0_pose_carrier.bin"
        );
        let mesh = asset::load_skinned(&skin_path)
            .unwrap_or_else(|error| panic!("failed to load C0 pose carrier {skin_path}: {error}"));
        assert_eq!(
            mesh.bones.len(),
            163,
            "C0-POSE-CARRIER-001 must preserve its 163-bone contract"
        );
        let bone_parents = mesh.bones.iter().map(|bone| bone.parent).collect();
        let positions: Vec<glam::Vec3> = if minimal_scene {
            vec![glam::Vec3::ZERO]
        } else {
            vec![glam::vec3(0.0, 0.0, 1.0), glam::vec3(0.0, 0.0, -1.0)]
        };
        let correct_model = skinned_correct_model();
        let vc = mesh.vertices.len();
        let mut interleaved = Vec::with_capacity(vc * std::mem::size_of::<asset::SkinnedVertex>());
        for vertex in &mesh.vertices {
            interleaved.extend_from_slice(bytemuck::bytes_of(&vertex.position));
            interleaved.extend_from_slice(bytemuck::bytes_of(&vertex.normal));
            interleaved.extend_from_slice(bytemuck::bytes_of(&vertex.uv));
            interleaved.extend_from_slice(bytemuck::bytes_of(&vertex.joint_indices));
            interleaved.extend_from_slice(bytemuck::bytes_of(&vertex.joint_weights));
        }
        for pos in positions {
            let svb = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("C0 Skin VB"),
                contents: &interleaved,
                usage: wgpu::BufferUsages::VERTEX,
            });
            let sib = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("C0 Skin IB"),
                contents: bytemuck::cast_slice(&mesh.indices),
                usage: wgpu::BufferUsages::INDEX,
            });
            let sub = device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("C0 Skin UB"),
                size: 64,
                usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
            let subg = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("C0 Skin UBG"),
                layout: &uniform_bgl,
                entries: &[wgpu::BindGroupEntry {
                    binding: 0,
                    resource: sub.as_entire_binding(),
                }],
            });
            let (stv, sts) = build_solid_texture(device, queue, [176, 163, 154, 255]);
            let stbg = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("C0 carrier fallback TBG"),
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
            let joint_buffer = device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("C0 Joint Buffer"),
                size: (mesh.bones.len() * std::mem::size_of::<glam::Mat4>()) as u64,
                usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
            let joint_bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
                label: Some("C0 Joint BG"),
                layout: &joint_bgl,
                entries: &[wgpu::BindGroupEntry {
                    binding: 0,
                    resource: joint_buffer.as_entire_binding(),
                }],
            });
            skinned.push(SkinnedObject {
                vertex_buffer: svb,
                index_buffer: sib,
                index_count: mesh.indices.len() as u32,
                uniform_buffer: sub,
                uniform_bind_group: subg,
                texture_bind_group: stbg,
                joint_buffer,
                joint_bind_group,
                bone_count: mesh.bones.len(),
                model: Mat4::from_translation(pos) * correct_model,
            });
        }
        println!(
            "  C0 pose carrier: {} verts, {} idxs, {} bones",
            vc,
            mesh.indices.len(),
            mesh.bones.len()
        );

        let first_person_weapon = build_solid_mesh_object(
            device,
            queue,
            &uniform_bgl,
            &texture_bgl,
            &format!("{assets}/weapons/w0_sword_assembled.bin"),
            "W0 first-person longsword",
            [48, 56, 64, 255],
        );

        Self {
            pipeline,
            skin_pipeline,
            debug_pipeline,
            objects,
            first_person_weapon,
            skinned,
            depth_view,
            proj_view: Mat4::IDENTITY,
            debug_ub,
            debug_ubg,
            debug_vb: None,
            debug_line_count: 0,
            hitbox_vb: None,
            hitbox_line_count: 0,
            bone_parents,
        }
    }

    /// Upload bone line vertices from one carrier skinning frame.
    pub fn update_debug_bones(&mut self, device: &wgpu::Device, joints: &[Mat4]) {
        assert_eq!(
            joints.len(),
            self.bone_parents.len(),
            "debug skeleton must match the active carrier hierarchy"
        );
        // Extract joint world positions (translation component of each matrix)
        let pos: Vec<glam::Vec3> = joints.iter().map(|joint| joint.w_axis.truncate()).collect();
        // Build line vertices: each parent-child pair = 2 vertices
        let mut verts: Vec<f32> = Vec::with_capacity(joints.len() * 2 * 6);
        for (i, parent) in self.bone_parents.iter().copied().enumerate() {
            if parent >= 0 && (parent as usize) < joints.len() {
                // From child (red) to parent (white)
                verts.extend_from_slice(pos[i].to_array().as_ref()); // position
                verts.extend_from_slice(&[1.0, 0.2, 0.2]); // red
                verts.extend_from_slice(pos[parent as usize].to_array().as_ref()); // position
                verts.extend_from_slice(&[1.0, 1.0, 1.0]); // white
            }
        }
        self.debug_line_count = (verts.len() / 6) as u32;
        if self.debug_line_count == 0 {
            return;
        }
        let vb = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("Debug VB"),
            contents: bytemuck::cast_slice(&verts),
            usage: wgpu::BufferUsages::VERTEX,
        });
        self.debug_vb = Some(vb);
    }

    /// Upload the MVP used by all debug line overlays.
    pub fn upload_debug_mvp(&self, queue: &wgpu::Queue, proj_view: &Mat4) {
        queue.write_buffer(&self.debug_ub, 0, bytemuck::bytes_of(&[*proj_view]));
    }

    /// Draw the bone overlay (call after render_skinned).
    pub fn render_debug_overlay<'a>(&'a self, rpass: &mut wgpu::RenderPass<'a>) {
        let Some(ref vb) = self.debug_vb else { return };
        if self.debug_line_count == 0 {
            return;
        };
        rpass.set_pipeline(&self.debug_pipeline);
        rpass.set_bind_group(0, &self.debug_ubg, &[]);
        rpass.set_vertex_buffer(0, vb.slice(..));
        rpass.draw(0..self.debug_line_count, 0..1);
    }

    /// Upload hitbox debug line vertices.
    pub fn update_hitbox_debug(
        &mut self,
        device: &wgpu::Device,
        lines: &[(glam::Vec3, glam::Vec3)],
    ) {
        if lines.is_empty() {
            self.hitbox_vb = None;
            self.hitbox_line_count = 0;
            return;
        }
        let mut verts: Vec<f32> = Vec::with_capacity(lines.len() * 2 * 6);
        for (a, b) in lines {
            // a: yellow, b: cyan
            verts.extend_from_slice(a.to_array().as_ref());
            verts.extend_from_slice(&[1.0, 1.0, 0.0]);
            verts.extend_from_slice(b.to_array().as_ref());
            verts.extend_from_slice(&[0.0, 1.0, 1.0]);
        }
        self.hitbox_line_count = (verts.len() / 6) as u32;
        let vb = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("Hitbox Debug VB"),
            contents: bytemuck::cast_slice(&verts),
            usage: wgpu::BufferUsages::VERTEX,
        });
        self.hitbox_vb = Some(vb);
    }

    /// Draw hitbox debug lines.
    pub fn render_hitbox_debug<'a>(&'a self, rpass: &mut wgpu::RenderPass<'a>) {
        let Some(ref vb) = self.hitbox_vb else { return };
        if self.hitbox_line_count == 0 {
            return;
        };
        rpass.set_pipeline(&self.debug_pipeline);
        rpass.set_bind_group(0, &self.debug_ubg, &[]);
        rpass.set_vertex_buffer(0, vb.slice(..));
        rpass.draw(0..self.hitbox_line_count, 0..1);
    }

    /// Write one skinning frame into every compatible skinned object.
    pub fn update_skin_joints(&self, queue: &wgpu::Queue, joints: &[Mat4]) {
        for s in &self.skinned {
            self.write_skin_joints(queue, s, joints);
        }
    }

    /// Write skinning matrices to a specific skinned object by index.
    pub fn update_skin_joints_indexed(&self, queue: &wgpu::Queue, idx: usize, joints: &[Mat4]) {
        if let Some(s) = self.skinned.get(idx) {
            self.write_skin_joints(queue, s, joints);
        }
    }

    fn write_skin_joints(&self, queue: &wgpu::Queue, skinned: &SkinnedObject, joints: &[Mat4]) {
        assert_eq!(
            joints.len(),
            skinned.bone_count,
            "skinning frame has {} joints but carrier requires {}",
            joints.len(),
            skinned.bone_count
        );
        let mut data = Vec::with_capacity(joints.len() * 16);
        for joint in joints {
            data.extend_from_slice(&joint.to_cols_array());
        }
        queue.write_buffer(&skinned.joint_buffer, 0, bytemuck::cast_slice(&data));
    }

    /// Update camera projection * view matrix (call each frame)
    pub fn update_camera(&mut self, queue: &wgpu::Queue, proj_view: &Mat4) {
        self.proj_view = *proj_view;
        // Compute MVP per object and upload
        for obj in &self.objects {
            let mvp = self.proj_view * obj.model;
            queue.write_buffer(&obj.uniform_buffer, 0, bytemuck::bytes_of(&[mvp]));
        }
        // Carrier model uniforms; skinning happens in the vertex shader.
        for s in &self.skinned {
            let mvp = self.proj_view * s.model;
            queue.write_buffer(&s.uniform_buffer, 0, bytemuck::bytes_of(&[mvp]));
        }
    }

    /// Upload the visual-only W0 sword transform for the current first-person frame.
    pub fn update_first_person_weapon(
        &mut self,
        queue: &wgpu::Queue,
        proj_view: &Mat4,
        model: Mat4,
    ) {
        self.first_person_weapon.model = model;
        let mvp = *proj_view * model;
        queue.write_buffer(
            &self.first_person_weapon.uniform_buffer,
            0,
            bytemuck::bytes_of(&[mvp]),
        );
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

    /// Render the accepted W0 weapon after arena geometry and before skinned actors.
    pub fn render_first_person_weapon<'a>(&'a self, rpass: &mut wgpu::RenderPass<'a>) {
        let weapon = &self.first_person_weapon;
        rpass.set_pipeline(&self.pipeline);
        rpass.set_bind_group(0, &weapon.uniform_bind_group, &[]);
        rpass.set_bind_group(1, &weapon.texture_bind_group, &[]);
        rpass.set_vertex_buffer(0, weapon.vertex_buffer.slice(..));
        rpass.set_index_buffer(weapon.index_buffer.slice(..), wgpu::IndexFormat::Uint32);
        rpass.draw_indexed(0..weapon.index_count, 0, 0..1);
    }

    /// Render skinned C0 carriers beginning at `first_instance`.
    ///
    /// First-person presentation omits the camera owner's full carrier to avoid
    /// head/interior self-occlusion; the visual weapon path will be supplied by
    /// the later source-valid motion/weapon unit.
    pub fn render_skinned_from<'a>(
        &'a self,
        rpass: &mut wgpu::RenderPass<'a>,
        first_instance: usize,
    ) {
        for s in self.skinned.iter().skip(first_instance) {
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

#[cfg(test)]
mod tests {
    use glam::{Vec3, vec3};

    use super::first_person_weapon_model;

    #[test]
    fn first_person_weapon_transform_is_finite_rigid_and_camera_relative() {
        let eye = vec3(2.0, 1.62, 4.0);
        let model = first_person_weapon_model(eye, Vec3::NEG_Z);

        assert!(model.is_finite());
        assert!((model.determinant() - 1.0).abs() < 1.0e-4);
        assert!(
            model.w_axis.x < eye.x,
            "screen-right is world -X at zero yaw"
        );
        assert!(model.w_axis.y < eye.y, "hilt stays below the camera eye");
        assert!(
            model.w_axis.z < eye.z,
            "hilt stays forward of the camera eye"
        );
    }
}
