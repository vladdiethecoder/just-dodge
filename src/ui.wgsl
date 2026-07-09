struct UiUniforms {
    screen_size: vec2<f32>,
};

@group(0) @binding(0)
var<uniform> uniforms: UiUniforms;

@group(1) @binding(0)
var font_tex: texture_2d<f32>;
@group(1) @binding(1)
var font_sampler: sampler;

struct VertexInput {
    @location(0) position: vec2<f32>,
    @location(1) uv: vec2<f32>,
    @location(2) color: vec4<f32>,
    @location(3) mode: u32,
};

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) uv: vec2<f32>,
    @location(1) color: vec4<f32>,
    @location(2) @interpolate(flat) mode: u32,
};

@vertex
fn vs_main(input: VertexInput) -> VertexOutput {
    var output: VertexOutput;
    let ndc = vec2<f32>(
        input.position.x / uniforms.screen_size.x * 2.0 - 1.0,
        1.0 - input.position.y / uniforms.screen_size.y * 2.0,
    );
    output.clip_position = vec4<f32>(ndc, 0.0, 1.0);
    output.uv = input.uv;
    output.color = input.color;
    output.mode = input.mode;
    return output;
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    if (input.mode == 0u) {
        return input.color;
    }
    let alpha = textureSample(font_tex, font_sampler, input.uv).r;
    return vec4<f32>(input.color.rgb, input.color.a * alpha);
}
