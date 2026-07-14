struct Uniforms {
    mvp: mat4x4<f32>,
};

@group(0) @binding(0)
var<uniform> uniforms: Uniforms;

@group(1) @binding(0)
var base_color: texture_2d<f32>;
@group(1) @binding(1)
var base_sampler: sampler;

@group(2) @binding(0)
var<storage, read> joints: array<mat4x4<f32>>;

struct RigidInput {
    @location(0) position: vec3<f32>,
    @location(1) normal: vec3<f32>,
    @location(2) uv: vec2<f32>,
};

struct SkinInput {
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
    @location(0) normal: vec3<f32>,
    @location(1) uv: vec2<f32>,
};

struct FragmentOutput {
    @location(0) beauty: vec4<f32>,
    @location(1) object_id: vec4<f32>,
    @location(2) normals: vec4<f32>,
    @location(3) linear_depth: vec4<f32>,
};

@vertex
fn rigid_vs(input: RigidInput) -> VertexOutput {
    var output: VertexOutput;
    output.clip_position = uniforms.mvp * vec4<f32>(input.position, 1.0);
    output.normal = normalize(input.normal);
    output.uv = input.uv;
    return output;
}

@vertex
fn skin_vs(input: SkinInput) -> VertexOutput {
    var output: VertexOutput;
    let skin =
        joints[input.joint_indices_0.x] * input.joint_weights_0.x +
        joints[input.joint_indices_0.y] * input.joint_weights_0.y +
        joints[input.joint_indices_0.z] * input.joint_weights_0.z +
        joints[input.joint_indices_0.w] * input.joint_weights_0.w +
        joints[input.joint_indices_1.x] * input.joint_weights_1.x +
        joints[input.joint_indices_1.y] * input.joint_weights_1.y +
        joints[input.joint_indices_1.z] * input.joint_weights_1.z +
        joints[input.joint_indices_1.w] * input.joint_weights_1.w;
    output.clip_position = uniforms.mvp * skin * vec4<f32>(input.position, 1.0);
    output.normal = normalize((skin * vec4<f32>(input.normal, 0.0)).xyz);
    output.uv = input.uv;
    return output;
}

fn lit_beauty(input: VertexOutput) -> vec3<f32> {
    let n = normalize(input.normal);
    let key = max(dot(n, normalize(vec3<f32>(0.45, 0.8, 0.38))), 0.0) * 0.38;
    let fill = max(dot(n, normalize(vec3<f32>(-0.65, 0.35, 0.3))), 0.0) * 0.12;
    let rim = max(dot(n, normalize(vec3<f32>(0.2, 0.25, -0.95))), 0.0) * 0.18;
    let base = textureSample(base_color, base_sampler, input.uv).rgb;
    return base * (0.42 + key + fill + rim);
}

fn outputs(input: VertexOutput, id: vec3<f32>) -> FragmentOutput {
    var output: FragmentOutput;
    output.beauty = vec4<f32>(lit_beauty(input), 1.0);
    output.object_id = vec4<f32>(id, 1.0);
    output.normals = vec4<f32>(normalize(input.normal) * 0.5 + 0.5, 1.0);
    let depth = clamp(input.clip_position.z, 0.0, 1.0);
    output.linear_depth = vec4<f32>(depth, depth, depth, 1.0);
    return output;
}

@fragment
fn actor_fs(input: VertexOutput) -> FragmentOutput {
    return outputs(input, vec3<f32>(1.0, 0.0, 0.0));
}

@fragment
fn weapon_fs(input: VertexOutput) -> FragmentOutput {
    return outputs(input, vec3<f32>(0.0, 1.0, 0.0));
}
