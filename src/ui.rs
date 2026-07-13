//! Immediate-mode wgpu UI for the 3-action prototype.
//!
//! Uses a built-in 5x7 bitmap font so the prototype needs no external font
//! files or text crates. The renderer builds a dynamic vertex buffer each
//! frame from colored rectangles and textured glyph quads.

use crate::input::{Action, PlanInput};
use bytemuck::{Pod, Zeroable};
use glam::Vec2;
use just_dodge::milestone3::{Phase, Side, Snapshot};

const GLYPH_W: f32 = 5.0;
const GLYPH_H: f32 = 7.0;
const GLYPH_ADV: f32 = 6.0;
const LINE_H: f32 = 10.0;
const ATLAS_COLS: u32 = 16;
const ATLAS_CELL: u32 = 8;

#[repr(C)]
#[derive(Clone, Copy, Pod, Zeroable)]
struct UiVertex {
    position: [f32; 2],
    uv: [f32; 2],
    color: [f32; 4],
    mode: u32,
}

impl UiVertex {
    fn new(pos: Vec2, uv: Vec2, color: [f32; 4], mode: u32) -> Self {
        Self {
            position: pos.into(),
            uv: uv.into(),
            color,
            mode,
        }
    }
}

pub struct UiRenderer {
    pipeline: wgpu::RenderPipeline,
    bind_group: wgpu::BindGroup,
    texture_bind_group: wgpu::BindGroup,
    screen_ub: wgpu::Buffer,
    vertex_buffer: wgpu::Buffer,
    vertices: Vec<UiVertex>,
    screen_size: (u32, u32),
}

fn build_font_atlas() -> Vec<u8> {
    // 5x7 bitmap font. Each glyph = 5 columns, LSB at top.
    let glyphs: &[(char, [u8; 5])] = &[
        (' ', [0x00, 0x00, 0x00, 0x00, 0x00]),
        ('!', [0x00, 0x00, 0x5F, 0x00, 0x00]),
        ('-', [0x00, 0x08, 0x08, 0x08, 0x00]),
        (':', [0x00, 0x24, 0x00, 0x24, 0x00]),
        ('0', [0x3E, 0x51, 0x49, 0x45, 0x3E]),
        ('1', [0x00, 0x42, 0x7F, 0x40, 0x00]),
        ('2', [0x42, 0x61, 0x51, 0x49, 0x46]),
        ('3', [0x21, 0x41, 0x45, 0x4B, 0x31]),
        ('4', [0x18, 0x14, 0x12, 0x7F, 0x10]),
        ('5', [0x27, 0x45, 0x45, 0x45, 0x39]),
        ('6', [0x3C, 0x4A, 0x49, 0x49, 0x30]),
        ('7', [0x01, 0x71, 0x09, 0x05, 0x03]),
        ('8', [0x36, 0x49, 0x49, 0x49, 0x36]),
        ('9', [0x06, 0x49, 0x49, 0x29, 0x1E]),
        ('A', [0x7E, 0x11, 0x11, 0x11, 0x7E]),
        ('B', [0x7F, 0x49, 0x49, 0x49, 0x36]),
        ('C', [0x3E, 0x41, 0x41, 0x41, 0x22]),
        ('D', [0x7F, 0x41, 0x41, 0x22, 0x1C]),
        ('E', [0x7F, 0x49, 0x49, 0x49, 0x41]),
        ('F', [0x7F, 0x09, 0x09, 0x09, 0x01]),
        ('G', [0x3E, 0x41, 0x49, 0x49, 0x7A]),
        ('H', [0x7F, 0x08, 0x08, 0x08, 0x7F]),
        ('I', [0x00, 0x41, 0x7F, 0x41, 0x00]),
        ('J', [0x20, 0x40, 0x41, 0x3F, 0x01]),
        ('K', [0x7F, 0x08, 0x14, 0x22, 0x41]),
        ('L', [0x7F, 0x40, 0x40, 0x40, 0x40]),
        ('M', [0x7F, 0x02, 0x0C, 0x02, 0x7F]),
        ('N', [0x7F, 0x04, 0x08, 0x10, 0x7F]),
        ('O', [0x3E, 0x41, 0x41, 0x41, 0x3E]),
        ('P', [0x7F, 0x09, 0x09, 0x09, 0x06]),
        ('Q', [0x3E, 0x41, 0x51, 0x21, 0x5E]),
        ('R', [0x7F, 0x09, 0x19, 0x29, 0x46]),
        ('S', [0x46, 0x49, 0x49, 0x49, 0x31]),
        ('T', [0x01, 0x01, 0x7F, 0x01, 0x01]),
        ('U', [0x3F, 0x40, 0x40, 0x40, 0x3F]),
        ('V', [0x1F, 0x20, 0x40, 0x20, 0x1F]),
        ('W', [0x3F, 0x40, 0x38, 0x40, 0x3F]),
        ('X', [0x63, 0x14, 0x08, 0x14, 0x63]),
        ('Y', [0x07, 0x08, 0x70, 0x08, 0x07]),
        ('Z', [0x61, 0x51, 0x49, 0x45, 0x43]),
        ('a', [0x20, 0x54, 0x54, 0x54, 0x78]),
        ('b', [0x7F, 0x48, 0x44, 0x44, 0x38]),
        ('c', [0x38, 0x44, 0x44, 0x44, 0x20]),
        ('d', [0x38, 0x44, 0x44, 0x48, 0x7F]),
        ('e', [0x38, 0x54, 0x54, 0x54, 0x18]),
        ('f', [0x00, 0x08, 0x7E, 0x09, 0x02]),
        ('g', [0x18, 0xA4, 0xA4, 0xA4, 0x7C]),
        ('h', [0x7F, 0x08, 0x04, 0x04, 0x78]),
        ('i', [0x00, 0x44, 0x7D, 0x40, 0x00]),
        ('j', [0x20, 0x40, 0x44, 0x3D, 0x00]),
        ('k', [0x7F, 0x10, 0x28, 0x44, 0x00]),
        ('l', [0x00, 0x41, 0x7F, 0x40, 0x00]),
        ('m', [0x7C, 0x04, 0x18, 0x04, 0x78]),
        ('n', [0x7C, 0x08, 0x04, 0x04, 0x78]),
        ('o', [0x38, 0x44, 0x44, 0x44, 0x38]),
        ('p', [0xFC, 0x24, 0x24, 0x24, 0x18]),
        ('q', [0x18, 0x24, 0x24, 0x18, 0xFC]),
        ('r', [0x7C, 0x08, 0x04, 0x04, 0x08]),
        ('s', [0x48, 0x54, 0x54, 0x54, 0x20]),
        ('t', [0x04, 0x3F, 0x44, 0x40, 0x20]),
        ('u', [0x3C, 0x40, 0x40, 0x20, 0x7C]),
        ('v', [0x1C, 0x20, 0x40, 0x20, 0x1C]),
        ('w', [0x3C, 0x40, 0x30, 0x40, 0x3C]),
        ('x', [0x44, 0x28, 0x10, 0x28, 0x44]),
        ('y', [0x0C, 0x50, 0x50, 0x50, 0x3C]),
        ('z', [0x44, 0x64, 0x54, 0x4C, 0x44]),
    ];

    let atlas_w = ATLAS_COLS * ATLAS_CELL;
    let atlas_h = 6 * ATLAS_CELL;
    let mut pixels = vec![0u8; (atlas_w * atlas_h) as usize];
    for (ch, cols) in glyphs {
        let idx = (*ch as u8).saturating_sub(32) as u32;
        let cx = idx % ATLAS_COLS;
        let cy = idx / ATLAS_COLS;
        for (col, byte) in cols.iter().enumerate() {
            for row in 0..7 {
                if (byte >> row) & 1 != 0 {
                    let x = (cx * ATLAS_CELL + col as u32 + 1) as usize;
                    let y = (cy * ATLAS_CELL + row as u32 + 1) as usize;
                    if x < atlas_w as usize && y < atlas_h as usize {
                        pixels[y * atlas_w as usize + x] = 255;
                    }
                }
            }
        }
    }
    pixels
}

fn char_uv(c: char) -> Option<(Vec2, Vec2)> {
    let idx = (c as u32).saturating_sub(32);
    if idx >= 96 {
        return None;
    }
    let cx = idx % ATLAS_COLS;
    let cy = idx / ATLAS_COLS;
    let atlas_w = (ATLAS_COLS * ATLAS_CELL) as f32;
    let atlas_h = (6 * ATLAS_CELL) as f32;
    let u0 = (cx * ATLAS_CELL) as f32 / atlas_w;
    let v0 = (cy * ATLAS_CELL) as f32 / atlas_h;
    let u1 = ((cx + 1) * ATLAS_CELL) as f32 / atlas_w;
    let v1 = ((cy + 1) * ATLAS_CELL) as f32 / atlas_h;
    Some((Vec2::new(u0, v0), Vec2::new(u1, v1)))
}

impl UiRenderer {
    pub fn new(
        device: &wgpu::Device,
        _queue: &wgpu::Queue,
        config: &wgpu::SurfaceConfiguration,
    ) -> Self {
        let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("UI Shader"),
            source: wgpu::ShaderSource::Wgsl(include_str!("ui.wgsl").into()),
        });

        let uniform_bgl = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
            label: Some("UI Uniform BGL"),
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
            label: Some("UI Texture BGL"),
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

        let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("UI Pipeline Layout"),
            bind_group_layouts: &[Some(&uniform_bgl), Some(&texture_bgl)],
            immediate_size: 0,
        });

        let vertex_layout = wgpu::VertexBufferLayout {
            array_stride: std::mem::size_of::<UiVertex>() as u64,
            step_mode: wgpu::VertexStepMode::Vertex,
            attributes: &[
                wgpu::VertexAttribute {
                    format: wgpu::VertexFormat::Float32x2,
                    offset: 0,
                    shader_location: 0,
                },
                wgpu::VertexAttribute {
                    format: wgpu::VertexFormat::Float32x2,
                    offset: 8,
                    shader_location: 1,
                },
                wgpu::VertexAttribute {
                    format: wgpu::VertexFormat::Float32x4,
                    offset: 16,
                    shader_location: 2,
                },
                wgpu::VertexAttribute {
                    format: wgpu::VertexFormat::Uint32,
                    offset: 32,
                    shader_location: 3,
                },
            ],
        };

        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("UI Pipeline"),
            cache: None,
            layout: Some(&pipeline_layout),
            vertex: wgpu::VertexState {
                module: &shader,
                entry_point: Some("vs_main"),
                buffers: &[Some(vertex_layout)],
                compilation_options: wgpu::PipelineCompilationOptions::default(),
            },
            fragment: Some(wgpu::FragmentState {
                module: &shader,
                entry_point: Some("fs_main"),
                targets: &[Some(wgpu::ColorTargetState {
                    format: config.format,
                    blend: Some(wgpu::BlendState::ALPHA_BLENDING),
                    write_mask: wgpu::ColorWrites::ALL,
                })],
                compilation_options: wgpu::PipelineCompilationOptions::default(),
            }),
            primitive: wgpu::PrimitiveState {
                topology: wgpu::PrimitiveTopology::TriangleList,
                cull_mode: None,
                front_face: wgpu::FrontFace::Ccw,
                ..Default::default()
            },
            depth_stencil: None,
            multisample: wgpu::MultisampleState::default(),
            multiview_mask: None,
        });

        let screen_ub = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("UI Screen UB"),
            size: 8,
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        let atlas_pixels = build_font_atlas();
        let atlas_w = ATLAS_COLS * ATLAS_CELL;
        let atlas_h = 6 * ATLAS_CELL;
        let texture = device.create_texture(&wgpu::TextureDescriptor {
            label: Some("UI Font Atlas"),
            size: wgpu::Extent3d {
                width: atlas_w,
                height: atlas_h,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::R8Unorm,
            usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
            view_formats: &[],
        });
        _queue.write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            &atlas_pixels,
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(atlas_w),
                rows_per_image: Some(atlas_h),
            },
            wgpu::Extent3d {
                width: atlas_w,
                height: atlas_h,
                depth_or_array_layers: 1,
            },
        );
        let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
        let sampler = device.create_sampler(&wgpu::SamplerDescriptor {
            address_mode_u: wgpu::AddressMode::ClampToEdge,
            address_mode_v: wgpu::AddressMode::ClampToEdge,
            mag_filter: wgpu::FilterMode::Nearest,
            min_filter: wgpu::FilterMode::Nearest,
            ..Default::default()
        });

        let bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("UI Bind Group"),
            layout: &uniform_bgl,
            entries: &[wgpu::BindGroupEntry {
                binding: 0,
                resource: screen_ub.as_entire_binding(),
            }],
        });

        let texture_bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("UI Texture Bind Group"),
            layout: &texture_bgl,
            entries: &[
                wgpu::BindGroupEntry {
                    binding: 0,
                    resource: wgpu::BindingResource::TextureView(&view),
                },
                wgpu::BindGroupEntry {
                    binding: 1,
                    resource: wgpu::BindingResource::Sampler(&sampler),
                },
            ],
        });

        let vertex_buffer = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("UI Vertex Buffer"),
            size: (1024 * std::mem::size_of::<UiVertex>()) as u64,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        Self {
            pipeline,
            bind_group,
            texture_bind_group,
            screen_ub,
            vertex_buffer,
            vertices: Vec::with_capacity(1024),
            screen_size: (config.width, config.height),
        }
    }

    fn quad(&mut self, a: Vec2, b: Vec2, c: Vec2, d: Vec2, color: [f32; 4], mode: u32) {
        self.vertices
            .push(UiVertex::new(a, Vec2::ZERO, color, mode));
        self.vertices
            .push(UiVertex::new(b, Vec2::ZERO, color, mode));
        self.vertices
            .push(UiVertex::new(c, Vec2::ZERO, color, mode));
        self.vertices
            .push(UiVertex::new(a, Vec2::ZERO, color, mode));
        self.vertices
            .push(UiVertex::new(c, Vec2::ZERO, color, mode));
        self.vertices
            .push(UiVertex::new(d, Vec2::ZERO, color, mode));
    }

    fn rect(&mut self, pos: Vec2, size: Vec2, color: [f32; 4]) {
        let a = pos;
        let b = pos + Vec2::new(size.x, 0.0);
        let c = pos + size;
        let d = pos + Vec2::new(0.0, size.y);
        self.quad(a, b, c, d, color, 0);
    }

    fn rect_outline(&mut self, pos: Vec2, size: Vec2, color: [f32; 4], thickness: f32) {
        // Top
        self.rect(pos, Vec2::new(size.x, thickness), color);
        // Bottom
        self.rect(
            pos + Vec2::new(0.0, size.y - thickness),
            Vec2::new(size.x, thickness),
            color,
        );
        // Left
        self.rect(pos, Vec2::new(thickness, size.y), color);
        // Right
        self.rect(
            pos + Vec2::new(size.x - thickness, 0.0),
            Vec2::new(thickness, size.y),
            color,
        );
    }

    fn glyph(&mut self, pos: Vec2, c: char, scale: f32, color: [f32; 4]) {
        let Some((uv0, uv1)) = char_uv(c) else {
            // Unknown char: render a small block.
            self.rect(
                pos,
                Vec2::new(GLYPH_W * scale, GLYPH_H * scale),
                [0.5, 0.5, 0.5, color[3]],
            );
            return;
        };
        let size = Vec2::new(GLYPH_W * scale, GLYPH_H * scale);
        let a = pos;
        let b = pos + Vec2::new(size.x, 0.0);
        let c = pos + size;
        let d = pos + Vec2::new(0.0, size.y);
        self.vertices.push(UiVertex::new(a, uv0, color, 1));
        self.vertices
            .push(UiVertex::new(b, Vec2::new(uv1.x, uv0.y), color, 1));
        self.vertices.push(UiVertex::new(c, uv1, color, 1));
        self.vertices.push(UiVertex::new(a, uv0, color, 1));
        self.vertices.push(UiVertex::new(c, uv1, color, 1));
        self.vertices
            .push(UiVertex::new(d, Vec2::new(uv0.x, uv1.y), color, 1));
    }

    fn text(&mut self, mut pos: Vec2, s: &str, scale: f32, color: [f32; 4]) {
        for c in s.chars() {
            if c == '\n' {
                pos.x = 0.0; // x reset expected to be managed by caller; newline advances y
                pos.y += LINE_H * scale;
                continue;
            }
            self.glyph(pos, c, scale, color);
            pos.x += GLYPH_ADV * scale;
        }
    }

    fn bar(&mut self, pos: Vec2, size: Vec2, fill: f32, bg: [f32; 4], fg: [f32; 4]) {
        self.rect(pos, size, bg);
        let fill_w = size.x * fill.clamp(0.0, 1.0);
        if fill_w > 0.0 {
            self.rect(pos, Vec2::new(fill_w, size.y), fg);
        }
    }

    pub fn render(
        &mut self,
        rpass: &mut wgpu::RenderPass,
        snapshot: &Snapshot,
        plan: &PlanInput,
        queue: &wgpu::Queue,
        width: u32,
        height: u32,
    ) {
        self.vertices.clear();
        if width != self.screen_size.0 || height != self.screen_size.1 {
            self.screen_size = (width, height);
        }
        queue.write_buffer(
            &self.screen_ub,
            0,
            bytemuck::bytes_of(&[width as f32, height as f32]),
        );

        let w = width as f32;
        let h = height as f32;
        let pad = 12.0;

        // --- Phase banner ---
        let phase_color = match snapshot.phase {
            Phase::Plan => [0.2, 0.5, 0.9, 1.0],
            Phase::Reveal => [0.9, 0.6, 0.2, 1.0],
            Phase::Resolve => [0.9, 0.2, 0.2, 1.0],
            Phase::MatchResult => [0.25, 0.15, 0.05, 1.0],
            _ => [0.2, 0.2, 0.2, 0.9],
        };
        self.rect(Vec2::new(0.0, 0.0), Vec2::new(w, 28.0), phase_color);
        let phase_duration = phase_duration_frames(snapshot.phase);
        let remaining =
            (phase_duration.saturating_sub(u32::from(snapshot.phase_frame))) as f32 / 60.0;
        let phase_label = format!("{:?}  {:.1}s", snapshot.phase, remaining);
        let label_w = phase_label.len() as f32 * GLYPH_ADV * 2.0;
        self.text(
            Vec2::new((w - label_w) / 2.0, 8.0),
            &phase_label,
            2.0,
            [1.0, 1.0, 1.0, 1.0],
        );

        // --- Localized-injury bars ---
        let bar_w = 180.0;
        let bar_h = 16.0;
        // Player (left)
        self.text(Vec2::new(pad, 40.0), "OK", 1.5, [1.0, 1.0, 1.0, 1.0]);
        self.bar(
            Vec2::new(pad + 30.0, 40.0),
            Vec2::new(bar_w, bar_h),
            1.0 - snapshot.player.total_injury() as f32 / 5.0,
            [0.2, 0.1, 0.1, 1.0],
            [0.9, 0.2, 0.2, 1.0],
        );
        self.text(Vec2::new(pad, 62.0), "INJ", 1.5, [1.0, 1.0, 1.0, 1.0]);
        self.bar(
            Vec2::new(pad + 30.0, 62.0),
            Vec2::new(bar_w, bar_h),
            snapshot.player.total_injury() as f32 / 5.0,
            [0.1, 0.2, 0.1, 1.0],
            [0.2, 0.8, 0.2, 1.0],
        );

        // Opponent (right)
        let opp_x = w - pad - bar_w - 30.0;
        self.text(Vec2::new(opp_x, 40.0), "OK", 1.5, [1.0, 1.0, 1.0, 1.0]);
        self.bar(
            Vec2::new(opp_x + 30.0, 40.0),
            Vec2::new(bar_w, bar_h),
            1.0 - snapshot.opponent.total_injury() as f32 / 5.0,
            [0.2, 0.1, 0.1, 1.0],
            [0.9, 0.2, 0.2, 1.0],
        );
        self.text(Vec2::new(opp_x, 62.0), "INJ", 1.5, [1.0, 1.0, 1.0, 1.0]);
        self.bar(
            Vec2::new(opp_x + 30.0, 62.0),
            Vec2::new(bar_w, bar_h),
            snapshot.opponent.total_injury() as f32 / 5.0,
            [0.1, 0.2, 0.1, 1.0],
            [0.2, 0.8, 0.2, 1.0],
        );

        // --- Action menu (bottom) ---
        let actions = [
            ("1 Strike", Action::Strike, [0.9, 0.2, 0.2, 0.9]),
            ("2 Block", Action::Block, [0.2, 0.6, 0.9, 0.9]),
            ("3 Grab", Action::Grab, [0.3, 0.9, 0.5, 0.9]),
        ];
        let btn_w = 140.0;
        let btn_h = 36.0;
        let gap = 16.0;
        let total_w = actions.len() as f32 * btn_w + (actions.len() as f32 - 1.0) * gap;
        let start_x = (w - total_w) / 2.0;
        let y = h - 90.0;
        for (i, (label, action, color)) in actions.iter().enumerate() {
            let x = start_x + i as f32 * (btn_w + gap);
            let selected = plan.selected_action == Some(*action);
            self.rect(Vec2::new(x, y), Vec2::new(btn_w, btn_h), *color);
            if selected {
                self.rect_outline(
                    Vec2::new(x, y),
                    Vec2::new(btn_w, btn_h),
                    [1.0, 1.0, 1.0, 1.0],
                    3.0,
                );
            }
            let tx = x + (btn_w - label.len() as f32 * GLYPH_ADV * 1.5) / 2.0;
            self.text(Vec2::new(tx, y + 10.0), label, 1.5, [1.0, 1.0, 1.0, 1.0]);
        }

        // --- Plan / commit prompts ---
        if snapshot.phase == Phase::Plan {
            if !snapshot.player.committed {
                let prompt = "Choose 1 Strike 2 Block 3 Grab  Space/Enter confirm";
                let pw = prompt.len() as f32 * GLYPH_ADV * 1.5;
                self.text(
                    Vec2::new((w - pw) / 2.0, h - 28.0),
                    prompt,
                    1.5,
                    [0.9, 0.9, 0.9, 1.0],
                );
            } else {
                let prompt = "Locked in";
                let pw = prompt.len() as f32 * GLYPH_ADV * 1.5;
                self.text(
                    Vec2::new((w - pw) / 2.0, h - 28.0),
                    prompt,
                    1.5,
                    [0.4, 0.9, 0.4, 1.0],
                );
            }
        }

        // --- Result text (during Reveal/Resolve/Consequence) ---
        if let Some((player_action, opponent_action)) = snapshot.revealed {
            let result = format!("{:?} vs {:?}", player_action, opponent_action);
            let rw = result.len() as f32 * GLYPH_ADV * 3.0;
            self.text(
                Vec2::new((w - rw) / 2.0, h / 2.0 - 20.0),
                &result,
                3.0,
                [1.0, 0.9, 0.2, 1.0],
            );
        }

        // --- Match over overlay ---
        if snapshot.phase == Phase::MatchResult {
            self.rect(Vec2::new(0.0, 0.0), Vec2::new(w, h), [0.0, 0.0, 0.0, 0.75]);
            let winner = snapshot
                .winner
                .map(|s| match s {
                    Side::Player => "You Win!",
                    Side::Opponent => "Opponent Wins",
                })
                .unwrap_or("Match Result");
            let mw = winner.len() as f32 * GLYPH_ADV * 4.0;
            self.text(
                Vec2::new((w - mw) / 2.0, h / 2.0 - 20.0),
                winner,
                4.0,
                [1.0, 0.8, 0.2, 1.0],
            );
        }

        // Upload and draw
        let bytes = bytemuck::cast_slice(&self.vertices);
        if bytes.len() as u64 > self.vertex_buffer.size() {
            // Should not happen with the current UI; if it does, clamp.
            return;
        }
        queue.write_buffer(&self.vertex_buffer, 0, bytes);

        rpass.set_pipeline(&self.pipeline);
        rpass.set_bind_group(0, &self.bind_group, &[]);
        rpass.set_bind_group(1, &self.texture_bind_group, &[]);
        rpass.set_vertex_buffer(0, self.vertex_buffer.slice(0..bytes.len() as u64));
        rpass.draw(0..self.vertices.len() as u32, 0..1);
    }
}

fn phase_duration_frames(phase: Phase) -> u32 {
    match phase {
        Phase::Observe => 6,
        Phase::Plan | Phase::MatchResult => 0,
        Phase::Commit => 2,
        Phase::Reveal => 12,
        Phase::Resolve => 1,
        Phase::Consequence => 18,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn font_atlas_builds_without_crash() {
        let atlas = build_font_atlas();
        assert_eq!(
            atlas.len(),
            (ATLAS_COLS * ATLAS_CELL * 6 * ATLAS_CELL) as usize
        );
        // At least some glyph pixels should be non-zero.
        assert!(atlas.iter().any(|&p| p > 0));
    }

    #[test]
    fn char_uv_maps_printable_ascii() {
        assert!(char_uv('A').is_some());
        assert!(char_uv('z').is_some());
        assert!(char_uv('9').is_some());
        assert!(char_uv(' ').is_some());
        // Out-of-range char returns None and will render as a block.
        assert!(char_uv('☃').is_none());
    }
}
