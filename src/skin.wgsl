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
// Runtime buffer length is the loaded carrier bone count.
@group(2) @binding(0)
var<storage, read> joints: array<mat4x4<f32>>;

struct VertexInput {
    @location(0) position: vec3<f32>,
    @location(1) normal: vec3<f32>,
    @location(2) uv: vec2<f32>,
    @location(3) joint_indices_0: vec4<u32>,
    @location(4) joint_indices_1: vec4<u32>,
    @location(5) joint_weights_0: vec4<f32>,
    @location(6) joint_weights_1: vec4<f32>,
};

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) world_normal: vec3<f32>,
    @location(1) frag_uv: vec2<f32>,
};

@vertex
fn vs_main(input: VertexInput) -> VertexOutput {
    var output: VertexOutput;

    let j0 = joints[input.joint_indices_0.x];
    let j1 = joints[input.joint_indices_0.y];
    let j2 = joints[input.joint_indices_0.z];
    let j3 = joints[input.joint_indices_0.w];
    let j4 = joints[input.joint_indices_1.x];
    let j5 = joints[input.joint_indices_1.y];
    let j6 = joints[input.joint_indices_1.z];
    let j7 = joints[input.joint_indices_1.w];

    let skin =
        j0 * input.joint_weights_0.x +
        j1 * input.joint_weights_0.y +
        j2 * input.joint_weights_0.z +
        j3 * input.joint_weights_0.w +
        j4 * input.joint_weights_1.x +
        j5 * input.joint_weights_1.y +
        j6 * input.joint_weights_1.z +
        j7 * input.joint_weights_1.w;

    let skinned_pos = skin * vec4<f32>(input.position, 1.0);
    let skinned_nrm = (skin * vec4<f32>(input.normal, 0.0)).xyz;

    output.clip_position = uniforms.mvp * skinned_pos;
    output.world_normal = normalize(skinned_nrm);
    output.frag_uv = input.uv;
    return output;
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    let light_dir = normalize(vec3<f32>(0.4, 1.0, 0.3));
    let n = normalize(input.world_normal);
    let diff = max(dot(n, light_dir), 0.0);
    let ambient = 0.55;
    // The C0 carrier binds an explicit 1x1 neutral fallback until its PBR
    // texture contract is accepted. Textured assets use this same sampled path.
    let base = textureSample(base_color, base_sampler, input.frag_uv).rgb;
    let intensity = ambient + diff * 0.45;
    return vec4<f32>(base * intensity, 1.0);
}
