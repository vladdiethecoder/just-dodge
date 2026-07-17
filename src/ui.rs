//! Immediate-mode wgpu UI for the 3-action prototype.
//!
//! Uses a built-in 5x7 bitmap font so the prototype needs no external font
//! files or text crates. The renderer builds a dynamic vertex buffer each
//! frame from colored rectangles and textured glyph quads.

use crate::input::{Action, PlanInput};
use bytemuck::{Pod, Zeroable};
use glam::Vec2;
use just_dodge::milestone3::{BodyRegion, ContactSurface, Phase, Side, Snapshot};
use just_dodge::runtime_flow::{ESTABLISHING_TICKS, FlowStage};

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

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct MotionLabPanel {
    pub frame: usize,
    pub frame_count: usize,
    pub playing: bool,
    pub presentation_off: bool,
    pub max_target_error_m: f32,
    pub mean_target_error_m: f32,
    pub worst_joint: usize,
    pub planted_foot_drift_m: f32,
    pub grip_error_m: f32,
}

pub struct UiFrame<'a> {
    pub snapshot: &'a Snapshot,
    pub plan: &'a PlanInput,
    pub flow_stage: FlowStage,
    pub establishing_remaining: u16,
    pub camera_label: &'a str,
    pub replay_total_exchanges: Option<u16>,
    pub replay_finished: bool,
    pub motion_lab: Option<MotionLabPanel>,
    pub width: u32,
    pub height: u32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum FeedbackTone {
    Reveal,
    Whiff,
    Guard,
    PlayerHit,
    OpponentHit,
}

impl FeedbackTone {
    const fn color(self) -> [f32; 4] {
        match self {
            Self::Reveal => [1.0, 0.82, 0.24, 1.0],
            Self::Whiff => [0.78, 0.82, 0.9, 1.0],
            Self::Guard => [0.25, 0.72, 1.0, 1.0],
            Self::PlayerHit => [0.35, 1.0, 0.48, 1.0],
            Self::OpponentHit => [1.0, 0.3, 0.25, 1.0],
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ExchangeFeedback {
    matchup: String,
    headline: String,
    detail: String,
    tone: FeedbackTone,
}

fn action_label(action: Action) -> &'static str {
    match action {
        Action::Strike => "STRIKE",
        Action::Block => "BLOCK",
        Action::Grab => "GRAB",
        Action::Move => "MOVE",
    }
}

fn region_label(region: BodyRegion) -> &'static str {
    match region {
        BodyRegion::Head => "HEAD",
        BodyRegion::Torso => "TORSO",
        BodyRegion::Arms => "ARMS",
    }
}

fn phase_banner_text(
    snapshot: &Snapshot,
    flow_stage: FlowStage,
    establishing_remaining: u16,
) -> String {
    let phase_duration = phase_duration_frames(snapshot.phase);
    let remaining = (phase_duration.saturating_sub(u32::from(snapshot.phase_frame))) as f32 / 60.0;
    match flow_stage {
        FlowStage::Menu => "Menu".to_string(),
        FlowStage::Establishing => {
            format!("Establishing  {:.1}s", establishing_remaining as f32 / 60.0)
        }
        FlowStage::Plan => "Plan  Choose your action".to_string(),
        FlowStage::Replan => format!("Replan  {remaining:.1}s"),
        FlowStage::Result => "Result".to_string(),
        FlowStage::Replay => format!("Replay  frame {}", snapshot.frame),
        _ => format!("{flow_stage:?}  {remaining:.1}s"),
    }
}

fn should_show_plan_prompt(snapshot: &Snapshot, flow_stage: FlowStage) -> bool {
    snapshot.phase == Phase::Plan && flow_stage == FlowStage::Plan
}

fn exchange_feedback(snapshot: &Snapshot, flow_stage: FlowStage) -> Option<ExchangeFeedback> {
    let (player_action, opponent_action) = snapshot.revealed?;
    let matchup = format!(
        "YOU {}  /  OPPONENT {}",
        action_label(player_action),
        action_label(opponent_action)
    );
    let reveal_pending = matches!(flow_stage, FlowStage::Reveal | FlowStage::Resolve)
        || (flow_stage == FlowStage::Replay
            && matches!(snapshot.phase, Phase::Reveal | Phase::Resolve));
    if reveal_pending {
        return Some(ExchangeFeedback {
            matchup,
            headline: "ACTIONS REVEALED".to_string(),
            detail: "PHYSICAL CONTACT PENDING".to_string(),
            tone: FeedbackTone::Reveal,
        });
    }

    let resolved = matches!(flow_stage, FlowStage::Consequence | FlowStage::Result)
        || (flow_stage == FlowStage::Replay
            && matches!(snapshot.phase, Phase::Consequence | Phase::MatchResult));
    if !resolved {
        return None;
    }

    let Some(contact) = snapshot.last_contact else {
        return Some(ExchangeFeedback {
            matchup,
            headline: "WHIFF".to_string(),
            detail: "NO CONTACT".to_string(),
            tone: FeedbackTone::Whiff,
        });
    };
    if contact.surface == ContactSurface::Guard {
        return Some(ExchangeFeedback {
            matchup,
            headline: "GUARD CONTACT".to_string(),
            detail: "NO INJURY".to_string(),
            tone: FeedbackTone::Guard,
        });
    }

    let (headline, tone) = match contact.attacker {
        Side::Player => ("YOU HIT OPPONENT", FeedbackTone::PlayerHit),
        Side::Opponent => ("OPPONENT HIT YOU", FeedbackTone::OpponentHit),
    };
    let expected_defender = contact.attacker.other();
    let detail = snapshot
        .last_injury
        .filter(|(defender, injury)| {
            *defender == expected_defender
                && injury.region == contact.region
                && injury.severity == contact.severity
        })
        .map_or_else(
            || "BODY CONTACT CONFIRMED".to_string(),
            |(_, injury)| {
                format!(
                    "{} INJURY +{}",
                    region_label(injury.region),
                    injury.severity
                )
            },
        );
    Some(ExchangeFeedback {
        matchup,
        headline: headline.to_string(),
        detail,
        tone,
    })
}

fn build_font_atlas() -> Vec<u8> {
    // 5x7 bitmap font. Each glyph = 5 columns, LSB at top.
    let glyphs: &[(char, [u8; 5])] = &[
        (' ', [0x00, 0x00, 0x00, 0x00, 0x00]),
        ('!', [0x00, 0x00, 0x5F, 0x00, 0x00]),
        ('-', [0x00, 0x08, 0x08, 0x08, 0x00]),
        ('/', [0x20, 0x10, 0x08, 0x04, 0x02]),
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
            size: (4096 * std::mem::size_of::<UiVertex>()) as u64,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        Self {
            pipeline,
            bind_group,
            texture_bind_group,
            screen_ub,
            vertex_buffer,
            vertices: Vec::with_capacity(4096),
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

    fn flush(&self, rpass: &mut wgpu::RenderPass, queue: &wgpu::Queue) {
        let bytes = bytemuck::cast_slice(&self.vertices);
        if bytes.len() as u64 > self.vertex_buffer.size() {
            return;
        }
        queue.write_buffer(&self.vertex_buffer, 0, bytes);
        rpass.set_pipeline(&self.pipeline);
        rpass.set_bind_group(0, &self.bind_group, &[]);
        rpass.set_bind_group(1, &self.texture_bind_group, &[]);
        rpass.set_vertex_buffer(0, self.vertex_buffer.slice(0..bytes.len() as u64));
        rpass.draw(0..self.vertices.len() as u32, 0..1);
    }

    fn motion_frontier_lab_overlay(&mut self, panel: MotionLabPanel, w: f32, h: f32) {
        self.rect(Vec2::ZERO, Vec2::new(w, 54.0), [0.006, 0.010, 0.020, 0.96]);
        self.text(
            Vec2::new(20.0, 18.0),
            "MOTION FRONTIER LAB",
            2.15,
            [0.94, 0.96, 1.0, 1.0],
        );
        let frame_status = format!(
            "FRAME {:02}/{:02}  {}  {}",
            panel.frame,
            panel.frame_count - 1,
            if panel.playing { "PLAYING" } else { "PAUSED" },
            if panel.presentation_off {
                "TRUTH VIEW"
            } else {
                "CONTEXT VIEW"
            }
        );
        self.text(
            Vec2::new(
                w - frame_status.len() as f32 * GLYPH_ADV * 1.45 - 20.0,
                20.0,
            ),
            &frame_status,
            1.45,
            [0.70, 0.80, 0.92, 1.0],
        );

        let panel_pos = Vec2::new(18.0, 72.0);
        let panel_size = Vec2::new(520.0, 292.0);
        self.rect(panel_pos, panel_size, [0.008, 0.014, 0.026, 0.93]);
        self.rect_outline(panel_pos, panel_size, [0.18, 0.24, 0.34, 1.0], 1.0);
        self.text(
            panel_pos + Vec2::new(16.0, 16.0),
            "VISIBLE LAYERS",
            1.45,
            [0.78, 0.84, 0.92, 1.0],
        );
        self.text(
            panel_pos + Vec2::new(16.0, 45.0),
            "REQUESTED CONSTRAINTS     UNAVAILABLE",
            1.30,
            [0.42, 0.46, 0.54, 1.0],
        );
        self.text(
            panel_pos + Vec2::new(16.0, 67.0),
            "ARDY GENERATED PROPOSAL   UNAVAILABLE",
            1.30,
            [0.42, 0.46, 0.54, 1.0],
        );
        self.text(
            panel_pos + Vec2::new(16.0, 89.0),
            "MOTIONBRICKS TARGET",
            1.35,
            [1.0, 0.20, 0.82, 1.0],
        );
        self.text(
            panel_pos + Vec2::new(16.0, 111.0),
            "COUPLED TRACKER OUTPUT",
            1.35,
            [0.10, 0.88, 1.0, 1.0],
        );
        self.text(
            panel_pos + Vec2::new(16.0, 133.0),
            "TARGET TO OUTPUT RESIDUAL",
            1.35,
            [1.0, 0.72, 0.08, 1.0],
        );
        let metrics = [
            format!(
                "MAX TARGET ERROR    {:7.2} MM  JOINT {:02}",
                panel.max_target_error_m * 1000.0,
                panel.worst_joint
            ),
            format!(
                "MEAN TARGET ERROR   {:7.2} MM",
                panel.mean_target_error_m * 1000.0
            ),
            format!(
                "PLANTED FOOT DRIFT  {:7.2} MM",
                panel.planted_foot_drift_m * 1000.0
            ),
            format!("GRIP ERROR          {:7.2} MM", panel.grip_error_m * 1000.0),
        ];
        for (row, metric) in metrics.iter().enumerate() {
            self.text(
                panel_pos + Vec2::new(16.0, 171.0 + row as f32 * 22.0),
                metric,
                1.28,
                [0.82, 0.86, 0.92, 1.0],
            );
        }
        self.text(
            panel_pos + Vec2::new(16.0, 270.0),
            "NOT PHYSICS TRUTH   RUNTIME ADMISSION FALSE",
            1.20,
            [1.0, 0.42, 0.24, 1.0],
        );

        let controls = "F4 PLAY/PAUSE   F5 PREV FRAME   F6 NEXT FRAME   F7 PRESENTATION";
        self.rect(
            Vec2::new(0.0, h - 48.0),
            Vec2::new(w, 48.0),
            [0.006, 0.010, 0.020, 0.96],
        );
        self.text(
            Vec2::new(20.0, h - 29.0),
            controls,
            1.45,
            [0.72, 0.80, 0.90, 1.0],
        );
    }

    fn cinematic_overlay(
        &mut self,
        snapshot: &Snapshot,
        total_exchanges: u16,
        finished: bool,
        w: f32,
        h: f32,
    ) {
        self.rect(Vec2::ZERO, Vec2::new(w, 52.0), [0.0, 0.0, 0.0, 0.92]);
        self.rect(
            Vec2::new(0.0, h - 64.0),
            Vec2::new(w, 64.0),
            [0.0, 0.0, 0.0, 0.92],
        );
        self.text(
            Vec2::new(22.0, 19.0),
            "FIGHT FILM",
            2.0,
            [0.95, 0.78, 0.24, 1.0],
        );
        let exchange = snapshot
            .exchange
            .saturating_add(1)
            .min(u32::from(total_exchanges));
        self.text(
            Vec2::new(w - 214.0, 20.0),
            &format!("EXCHANGE {exchange}/{total_exchanges}"),
            1.55,
            [0.82, 0.88, 0.96, 1.0],
        );
        let cut = match snapshot.phase {
            Phase::Commit => "WIDE",
            Phase::Reveal => "TRACK",
            Phase::Resolve => "IMPACT",
            Phase::Consequence => "FOLLOW THROUGH",
            Phase::MatchResult => "FINAL FRAME",
            Phase::Observe | Phase::Plan => "CUT",
        };
        self.text(Vec2::new(22.0, h - 50.0), cut, 1.35, [0.42, 0.82, 1.0, 1.0]);
        if let Some((player, opponent)) = snapshot
            .revealed
            .or_else(|| Some((snapshot.player.planned?, snapshot.opponent.planned?)))
        {
            self.text(
                Vec2::new(22.0, h - 28.0),
                &format!(
                    "YOU {}  /  RIVAL {}",
                    action_label(player),
                    action_label(opponent)
                ),
                1.55,
                [0.94, 0.95, 0.98, 1.0],
            );
        }
        let controls = if finished {
            "FILM COMPLETE   R REMATCH   ESC MENU"
        } else {
            "R REMATCH   ESC MENU"
        };
        let controls_w = controls.len() as f32 * GLYPH_ADV * 1.35;
        self.text(
            Vec2::new(w - controls_w - 22.0, h - 28.0),
            controls,
            1.35,
            [0.74, 0.78, 0.84, 1.0],
        );
    }

    pub fn render(
        &mut self,
        rpass: &mut wgpu::RenderPass,
        frame: UiFrame<'_>,
        queue: &wgpu::Queue,
    ) {
        let UiFrame {
            snapshot,
            plan,
            flow_stage,
            establishing_remaining,
            camera_label,
            replay_total_exchanges,
            replay_finished,
            motion_lab,
            width,
            height,
        } = frame;
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

        if let Some(panel) = motion_lab {
            self.motion_frontier_lab_overlay(panel, w, h);
            self.flush(rpass, queue);
            return;
        }

        if flow_stage == FlowStage::Replay {
            self.cinematic_overlay(
                snapshot,
                replay_total_exchanges.unwrap_or(1),
                replay_finished,
                w,
                h,
            );
            self.flush(rpass, queue);
            return;
        }

        // --- Compact phase + condition rail. Keep the duel visible. ---
        let phase_label = phase_banner_text(snapshot, flow_stage, establishing_remaining);
        let phase_w = 292.0;
        let phase_x = (w - phase_w) * 0.5;
        self.rect(
            Vec2::new(phase_x, 12.0),
            Vec2::new(phase_w, 32.0),
            [0.018, 0.026, 0.04, 0.92],
        );
        self.rect(
            Vec2::new(phase_x, 42.0),
            Vec2::new(phase_w, 2.0),
            match snapshot.phase {
                Phase::Plan => [0.22, 0.78, 0.95, 1.0],
                Phase::Reveal => [1.0, 0.72, 0.22, 1.0],
                Phase::Resolve | Phase::Consequence => [1.0, 0.32, 0.24, 1.0],
                _ => [0.52, 0.58, 0.68, 1.0],
            },
        );
        let label_w = phase_label.len() as f32 * GLYPH_ADV * 1.55;
        self.text(
            Vec2::new((w - label_w) / 2.0, 21.0),
            &phase_label,
            1.55,
            [0.9, 0.93, 0.98, 1.0],
        );

        if camera_label != "FIRST PERSON" {
            self.rect(
                Vec2::new(12.0, h - 116.0),
                Vec2::new(196.0, 28.0),
                [0.02, 0.03, 0.05, 0.86],
            );
            self.text(
                Vec2::new(22.0, h - 108.0),
                &format!("F2 CAMERA  {camera_label}"),
                1.5,
                [0.62, 0.82, 1.0, 1.0],
            );
        }

        // --- Localized condition meters ---
        let bar_w = 170.0;
        let bar_h = 7.0;
        self.rect(
            Vec2::new(pad, 12.0),
            Vec2::new(232.0, 44.0),
            [0.018, 0.026, 0.04, 0.9],
        );
        self.text(
            Vec2::new(pad + 10.0, 21.0),
            "YOU",
            1.7,
            [0.24, 0.82, 1.0, 1.0],
        );
        self.text(
            Vec2::new(pad + 174.0, 21.0),
            &format!("INJ {}", snapshot.player.total_injury()),
            1.3,
            [0.9, 0.93, 0.98, 1.0],
        );
        self.bar(
            Vec2::new(pad + 10.0, 44.0),
            Vec2::new(bar_w, bar_h),
            1.0 - snapshot.player.total_injury() as f32 / 5.0,
            [0.18, 0.07, 0.07, 1.0],
            [0.24, 0.82, 1.0, 1.0],
        );

        let opp_x = w - pad - 232.0;
        self.rect(
            Vec2::new(opp_x, 12.0),
            Vec2::new(232.0, 44.0),
            [0.018, 0.026, 0.04, 0.9],
        );
        self.text(
            Vec2::new(opp_x + 10.0, 21.0),
            "RIVAL",
            1.7,
            [1.0, 0.62, 0.22, 1.0],
        );
        self.text(
            Vec2::new(opp_x + 174.0, 21.0),
            &format!("INJ {}", snapshot.opponent.total_injury()),
            1.3,
            [0.9, 0.93, 0.98, 1.0],
        );
        self.bar(
            Vec2::new(opp_x + 52.0, 44.0),
            Vec2::new(bar_w, bar_h),
            1.0 - snapshot.opponent.total_injury() as f32 / 5.0,
            [0.18, 0.07, 0.07, 1.0],
            [1.0, 0.62, 0.22, 1.0],
        );

        if flow_stage == FlowStage::Plan {
            // --- Brutalist action rail (bottom) ---
            let actions = [
                ("1  STRIKE", Action::Strike),
                ("2  BLOCK", Action::Block),
                ("3  GRAB", Action::Grab),
                ("4  MOVE", Action::Move),
            ];
            let btn_w = 152.0;
            let btn_h = 48.0;
            let gap = 8.0;
            let total_w = actions.len() as f32 * btn_w + (actions.len() as f32 - 1.0) * gap;
            let start_x = (w - total_w) / 2.0;
            let y = h - 106.0;
            self.rect(
                Vec2::new(start_x - 12.0, y - 12.0),
                Vec2::new(total_w + 24.0, btn_h + 24.0),
                [0.012, 0.019, 0.03, 0.88],
            );
            for (i, (label, action)) in actions.iter().enumerate() {
                let x = start_x + i as f32 * (btn_w + gap);
                let selected = plan.selected_action == Some(*action);
                self.rect(
                    Vec2::new(x, y),
                    Vec2::new(btn_w, btn_h),
                    if selected {
                        [0.035, 0.18, 0.24, 0.96]
                    } else {
                        [0.025, 0.036, 0.055, 0.96]
                    },
                );
                self.rect_outline(
                    Vec2::new(x, y),
                    Vec2::new(btn_w, btn_h),
                    if selected {
                        [0.24, 0.82, 1.0, 1.0]
                    } else {
                        [0.24, 0.29, 0.36, 1.0]
                    },
                    if selected { 2.0 } else { 1.0 },
                );
                let tx = x + (btn_w - label.len() as f32 * GLYPH_ADV * 1.6) / 2.0;
                self.text(
                    Vec2::new(tx, y + 17.0),
                    label,
                    1.6,
                    if selected {
                        [0.9, 0.97, 1.0, 1.0]
                    } else {
                        [0.68, 0.73, 0.8, 1.0]
                    },
                );
            }
            if plan.selected_action == Some(Action::Move) {
                let center = Vec2::new(w * 0.5, y - 72.0);
                self.rect(
                    center - Vec2::new(84.0, 60.0),
                    Vec2::new(168.0, 120.0),
                    [0.012, 0.019, 0.03, 0.88],
                );
                for direction in [
                    Vec2::new(0.0, -1.0),
                    Vec2::new(0.707, -0.707),
                    Vec2::new(1.0, 0.0),
                    Vec2::new(0.707, 0.707),
                    Vec2::new(0.0, 1.0),
                    Vec2::new(-0.707, 0.707),
                    Vec2::new(-1.0, 0.0),
                    Vec2::new(-0.707, -0.707),
                ] {
                    self.rect(
                        center + direction * 42.0 - Vec2::splat(4.0),
                        Vec2::splat(8.0),
                        [0.30, 0.38, 0.48, 0.94],
                    );
                }
                let radial = Vec2::new(
                    plan.radial_di.right_q15 as f32 / f32::from(i16::MAX),
                    -(plan.radial_di.forward_q15 as f32 / f32::from(i16::MAX)),
                );
                self.rect(
                    center + radial * 42.0 - Vec2::splat(7.0),
                    Vec2::splat(14.0),
                    [0.24, 0.82, 1.0, 1.0],
                );
                self.text(
                    center + Vec2::new(-39.0, 50.0),
                    "DIRECTION",
                    1.2,
                    [0.62, 0.82, 0.94, 1.0],
                );
            }
        }

        // --- Plan / commit prompts ---
        if should_show_plan_prompt(snapshot, flow_stage) {
            if !snapshot.player.committed {
                let prompt = if plan.selected_action == Some(Action::Move) {
                    "MOVE: WASD / STICK    ENTER CONFIRM"
                } else {
                    "ENTER CONFIRM"
                };
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

        // --- Match over overlay ---
        if flow_stage == FlowStage::Result {
            self.rect(Vec2::new(0.0, 0.0), Vec2::new(w, h), [0.0, 0.0, 0.0, 0.84]);
            let winner = snapshot
                .winner
                .map(|s| match s {
                    Side::Player => "You Win!",
                    Side::Opponent => "Opponent Wins",
                })
                .unwrap_or("Match Result");
            let mw = winner.len() as f32 * GLYPH_ADV * 4.0;
            self.text(
                Vec2::new((w - mw) / 2.0, h / 2.0 - 118.0),
                winner,
                4.0,
                [1.0, 0.8, 0.2, 1.0],
            );
            let prompt = "P Replay   R Rematch   Esc Menu   Q Quit";
            let prompt_w = prompt.len() as f32 * GLYPH_ADV * 1.6;
            self.text(
                Vec2::new((w - prompt_w) / 2.0, h / 2.0 + 92.0),
                prompt,
                1.6,
                [0.9, 0.9, 0.9, 1.0],
            );
        }

        // --- Public, truth-derived exchange feedback ---
        if let Some(feedback) = exchange_feedback(snapshot, flow_stage) {
            let reveal = snapshot.phase == Phase::Reveal;
            let panel_w = if reveal { 500.0 } else { 392.0 };
            let panel_h = if reveal { 76.0 } else { 94.0 };
            let panel = if reveal {
                Vec2::new((w - panel_w) * 0.5, 62.0)
            } else {
                Vec2::new(w - panel_w - 20.0, 72.0)
            };
            self.rect(
                panel,
                Vec2::new(panel_w, panel_h),
                [0.008, 0.014, 0.024, 0.9],
            );
            self.rect(panel, Vec2::new(3.0, panel_h), feedback.tone.color());

            let matchup_scale = 1.15;
            self.text(
                Vec2::new(panel.x + 16.0, panel.y + 10.0),
                &feedback.matchup,
                matchup_scale,
                [0.58, 0.66, 0.76, 1.0],
            );

            let headline_scale = if reveal { 2.0 } else { 2.25 };
            self.text(
                Vec2::new(panel.x + 16.0, panel.y + 32.0),
                &feedback.headline,
                headline_scale,
                feedback.tone.color(),
            );

            let detail_scale = 1.25;
            self.text(
                Vec2::new(panel.x + 16.0, panel.y + panel_h - 19.0),
                &feedback.detail,
                detail_scale,
                [0.72, 0.78, 0.86, 1.0],
            );
        }

        if snapshot.phase == Phase::Consequence
            && snapshot.phase_frame <= 8
            && snapshot.last_contact.is_some()
        {
            let alpha = 0.72 - snapshot.phase_frame as f32 * 0.065;
            let color = [1.0, 0.34, 0.16, alpha];
            let edge = 5.0;
            self.rect(Vec2::ZERO, Vec2::new(w, edge), color);
            self.rect(Vec2::new(0.0, h - edge), Vec2::new(w, edge), color);
            self.rect(Vec2::ZERO, Vec2::new(edge, h), color);
            self.rect(Vec2::new(w - edge, 0.0), Vec2::new(edge, h), color);
            let center = Vec2::new(w * 0.5, h * 0.58);
            let radius = 42.0 - snapshot.phase_frame as f32 * 3.5;
            self.rect(
                center - Vec2::new(radius, 1.5),
                Vec2::new(radius * 2.0, 3.0),
                color,
            );
            self.rect(
                center - Vec2::new(1.5, radius),
                Vec2::new(3.0, radius * 2.0),
                color,
            );
            for offset in [
                Vec2::new(0.7, 0.7),
                Vec2::new(-0.7, 0.7),
                Vec2::new(0.7, -0.7),
                Vec2::new(-0.7, -0.7),
            ] {
                self.rect(
                    center + offset * radius - Vec2::splat(3.0),
                    Vec2::splat(6.0),
                    color,
                );
            }
        }

        match flow_stage {
            FlowStage::Menu => {
                self.rect(Vec2::ZERO, Vec2::new(w, h), [0.015, 0.02, 0.035, 1.0]);
                let title = "JUST DODGE";
                let title_w = title.len() as f32 * GLYPH_ADV * 5.0;
                self.text(
                    Vec2::new((w - title_w) / 2.0, h * 0.36),
                    title,
                    5.0,
                    [0.95, 0.78, 0.24, 1.0],
                );
                let subtitle = "A deterministic three-action duel";
                let subtitle_w = subtitle.len() as f32 * GLYPH_ADV * 1.8;
                self.text(
                    Vec2::new((w - subtitle_w) / 2.0, h * 0.48),
                    subtitle,
                    1.8,
                    [0.78, 0.82, 0.9, 1.0],
                );
                let prompt = "Enter or Space to begin   Q Quit";
                let prompt_w = prompt.len() as f32 * GLYPH_ADV * 1.8;
                self.text(
                    Vec2::new((w - prompt_w) / 2.0, h * 0.62),
                    prompt,
                    1.8,
                    [1.0, 1.0, 1.0, 1.0],
                );
            }
            FlowStage::Establishing => {
                self.rect(Vec2::ZERO, Vec2::new(w, h), [0.02, 0.025, 0.04, 0.82]);
                let title = "ESTABLISHING";
                let title_w = title.len() as f32 * GLYPH_ADV * 3.2;
                self.text(
                    Vec2::new((w - title_w) / 2.0, h * 0.43),
                    title,
                    3.2,
                    [0.95, 0.78, 0.24, 1.0],
                );
                let elapsed = ESTABLISHING_TICKS.saturating_sub(establishing_remaining);
                let progress = elapsed as f32 / ESTABLISHING_TICKS as f32;
                self.bar(
                    Vec2::new(w * 0.3, h * 0.54),
                    Vec2::new(w * 0.4, 10.0),
                    progress,
                    [0.15, 0.15, 0.18, 1.0],
                    [0.95, 0.62, 0.18, 1.0],
                );
            }
            FlowStage::Replay => {
                let prompt = "REPLAY   R Rematch   Esc Menu   Q Quit";
                self.rect(
                    Vec2::new(0.0, h - 34.0),
                    Vec2::new(w, 34.0),
                    [0.0, 0.0, 0.0, 0.82],
                );
                let prompt_w = prompt.len() as f32 * GLYPH_ADV * 1.5;
                self.text(
                    Vec2::new((w - prompt_w) / 2.0, h - 24.0),
                    prompt,
                    1.5,
                    [0.95, 0.9, 0.65, 1.0],
                );
            }
            _ => {}
        }

        self.flush(rpass, queue);
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
    use just_dodge::milestone3::{
        Action as M3Action, BodyRegion, ContactSurface, Fighter, Injury, Outcome, PhysicalContact,
    };

    fn snapshot(phase: Phase) -> Snapshot {
        Snapshot {
            seed: 7,
            frame: 20,
            exchange: 1,
            phase,
            phase_frame: 0,
            player: Fighter::fresh(),
            opponent: Fighter::fresh(),
            revealed: None,
            last_contact: None,
            last_outcome: None,
            last_injury: None,
            winner: None,
        }
    }

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

    #[test]
    fn plan_banner_is_untimed_and_hides_stale_exchange_truth() {
        let mut value = snapshot(Phase::Plan);
        value.revealed = Some((M3Action::Strike, M3Action::Grab));
        value.last_contact = Some(PhysicalContact {
            attacker: Side::Opponent,
            surface: ContactSurface::Body,
            region: BodyRegion::Head,
            severity: 2,
        });
        value.last_outcome = Some(Outcome::OpponentWins);

        assert_eq!(
            phase_banner_text(&value, FlowStage::Plan, 0),
            "Plan  Choose your action"
        );
        assert_eq!(exchange_feedback(&value, FlowStage::Plan), None);
        assert!(should_show_plan_prompt(&value, FlowStage::Plan));
        assert!(!should_show_plan_prompt(&value, FlowStage::Replay));
    }

    #[test]
    fn reveal_reports_public_actions_without_reusing_stale_contact() {
        let mut value = snapshot(Phase::Reveal);
        value.revealed = Some((M3Action::Strike, M3Action::Grab));
        value.last_contact = Some(PhysicalContact {
            attacker: Side::Opponent,
            surface: ContactSurface::Body,
            region: BodyRegion::Head,
            severity: 2,
        });
        value.last_outcome = Some(Outcome::OpponentWins);

        assert_eq!(
            exchange_feedback(&value, FlowStage::Reveal),
            Some(ExchangeFeedback {
                matchup: "YOU STRIKE  /  OPPONENT GRAB".to_string(),
                headline: "ACTIONS REVEALED".to_string(),
                detail: "PHYSICAL CONTACT PENDING".to_string(),
                tone: FeedbackTone::Reveal,
            })
        );
    }

    #[test]
    fn consequence_calls_missing_measured_contact_a_whiff() {
        let mut value = snapshot(Phase::Consequence);
        value.revealed = Some((M3Action::Strike, M3Action::Grab));
        value.last_outcome = Some(Outcome::Clash);

        let feedback = exchange_feedback(&value, FlowStage::Consequence).unwrap();
        assert_eq!(feedback.headline, "WHIFF");
        assert_eq!(feedback.detail, "NO CONTACT");
        assert_eq!(feedback.tone, FeedbackTone::Whiff);
    }

    #[test]
    fn guard_role_overrides_action_labels_in_feedback() {
        let mut value = snapshot(Phase::Consequence);
        value.revealed = Some((M3Action::Strike, M3Action::Grab));
        value.last_contact = Some(PhysicalContact {
            attacker: Side::Player,
            surface: ContactSurface::Guard,
            region: BodyRegion::Torso,
            severity: 2,
        });
        value.last_outcome = Some(Outcome::Clash);

        let feedback = exchange_feedback(&value, FlowStage::Consequence).unwrap();
        assert_eq!(feedback.headline, "GUARD CONTACT");
        assert_eq!(feedback.detail, "NO INJURY");
        assert_eq!(feedback.tone, FeedbackTone::Guard);
    }

    #[test]
    fn body_role_reports_attacker_region_and_measured_injury() {
        let mut value = snapshot(Phase::Consequence);
        value.revealed = Some((M3Action::Strike, M3Action::Grab));
        value.last_contact = Some(PhysicalContact {
            attacker: Side::Player,
            surface: ContactSurface::Body,
            region: BodyRegion::Torso,
            severity: 2,
        });
        value.last_outcome = Some(Outcome::PlayerWins);
        value.last_injury = Some((
            Side::Opponent,
            Injury {
                region: BodyRegion::Torso,
                severity: 2,
            },
        ));

        let feedback = exchange_feedback(&value, FlowStage::Consequence).unwrap();
        assert_eq!(feedback.headline, "YOU HIT OPPONENT");
        assert_eq!(feedback.detail, "TORSO INJURY +2");
        assert_eq!(feedback.tone, FeedbackTone::PlayerHit);
    }

    #[test]
    fn body_feedback_does_not_invent_injury_from_an_inconsistent_snapshot() {
        let mut value = snapshot(Phase::Consequence);
        value.revealed = Some((M3Action::Grab, M3Action::Strike));
        value.last_contact = Some(PhysicalContact {
            attacker: Side::Opponent,
            surface: ContactSurface::Body,
            region: BodyRegion::Arms,
            severity: 1,
        });
        value.last_outcome = Some(Outcome::OpponentWins);
        value.last_injury = Some((
            Side::Opponent,
            Injury {
                region: BodyRegion::Arms,
                severity: 1,
            },
        ));

        let feedback = exchange_feedback(&value, FlowStage::Consequence).unwrap();
        assert_eq!(feedback.headline, "OPPONENT HIT YOU");
        assert_eq!(feedback.detail, "BODY CONTACT CONFIRMED");
        assert_eq!(feedback.tone, FeedbackTone::OpponentHit);
    }
}
