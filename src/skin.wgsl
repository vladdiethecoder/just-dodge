struct Uniforms {
    mvp: mat4x4<f32>,
};

@group(0) @binding(0)
var<uniform> uniforms: Uniforms;

@group(1) @binding(0)
var base_color: texture_2d<f32>;
@group(1) @binding(1)
var base_sampler: sampler;

// Instance-specific: per-frame skinning joint matrices (column-major).
// Array of 24 mat4. std430 layout in storage buffer: each mat4 is 64 bytes.
@group(2) @binding(0)
var<storage, read> joints: array<mat4x4<f32>>;

struct VertexInput {
    @location(0) position: vec3<f32>,
    @location(1) normal: vec3<f32>,
    @location(2) uv: vec2<f32>,
    @location(3) joint_indices: vec4<u32>,
    @location(4) joint_weights: vec4<f32>,
};

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) world_normal: vec3<f32>,
    @location(1) frag_uv: vec2<f32>,
};

@vertex
fn vs_main(input: VertexInput) -> VertexOutput {
    var output: VertexOutput;

    let j0 = joints[input.joint_indices.x];
    let j1 = joints[input.joint_indices.y];
    let j2 = joints[input.joint_indices.z];
    let j3 = joints[input.joint_indices.w];

    let skin =
        j0 * input.joint_weights.x +
        j1 * input.joint_weights.y +
        j2 * input.joint_weights.z +
        j3 * input.joint_weights.w;

    let skinned_pos = skin * vec4<f32>(input.position, 1.0);
    let skinned_nrm = (skin * vec4<f32>(input.normal, 0.0)).xyz;

    output.clip_position = uniforms.mvp * skinned_pos;
    output.world_normal = normalize(skinned_nrm);
    output.frag_uv = input.uv;
    return output;
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    let tex_color = textureSample(base_color, base_sampler, input.frag_uv);
    let light_dir = normalize(vec3<f32>(0.6, -1.0, 0.0));
    let diff = max(dot(input.world_normal, light_dir), 0.0);
    let ambient = 0.35;
    let intensity = ambient + diff * 0.65;
    return vec4<f32>(tex_color.rgb * intensity, 1.0);
}
