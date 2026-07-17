struct Uniforms {
    mvp: mat4x4<f32>,
    model: mat4x4<f32>,
}

@group(0) @binding(0)
var<uniform> uniforms: Uniforms;

@group(1) @binding(0)
var base_color: texture_2d<f32>;
@group(1) @binding(1)
var base_sampler: sampler;

struct VertexInput {
    @location(0) position: vec3<f32>,
    @location(1) normal: vec3<f32>,
    @location(2) uv: vec2<f32>,
}

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) world_normal: vec3<f32>,
    @location(1) frag_uv: vec2<f32>,
}

@vertex
fn vs_main(input: VertexInput) -> VertexOutput {
    var output: VertexOutput;
    output.clip_position = uniforms.mvp * vec4<f32>(input.position, 1.0);
    output.world_normal = normalize((uniforms.model * vec4<f32>(input.normal, 0.0)).xyz);
    output.frag_uv = input.uv;
    return output;
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    let tex_color = textureSample(base_color, base_sampler, input.frag_uv);
    let n = normalize(input.world_normal);
    let key = abs(dot(n, normalize(vec3<f32>(-0.35, 0.82, 0.45))));
    let hemisphere = 0.5 + 0.5 * n.y;
    let intensity = 0.70 + 0.38 * key + 0.12 * hemisphere;
    return vec4<f32>(tex_color.rgb * intensity, 1.0);
}
