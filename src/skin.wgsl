struct Uniforms {
    mvp: mat4x4<f32>,
    model: mat4x4<f32>,
    camera_position: vec4<f32>,
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
    @location(2) world_position: vec3<f32>,
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
    let world_position = uniforms.model * skinned_pos;
    output.world_normal = normalize((uniforms.model * vec4<f32>(skinned_nrm, 0.0)).xyz);
    output.frag_uv = input.uv;
    output.world_position = world_position.xyz;
    return output;
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    let light_dir = normalize(vec3<f32>(-0.35, 1.0, -0.25));
    let n = normalize(input.world_normal);
    let v = normalize(uniforms.camera_position.xyz - input.world_position);
    let h = normalize(light_dir + v);
    let base = textureSample(base_color, base_sampler, input.frag_uv).rgb;
    // The accepted C0 carrier is a fully armoured plate/leather assembly. Until
    // the cooked format carries per-run ORM textures, use one explicit plate
    // response rather than the previous non-physical rim-light heuristic.
    let metallic = 0.72;
    let roughness = 0.32;
    let alpha = roughness * roughness;
    let n_dot_l = max(dot(n, light_dir), 0.0);
    let n_dot_v = max(dot(n, v), 0.001);
    let n_dot_h = max(dot(n, h), 0.0);
    let v_dot_h = max(dot(v, h), 0.0);
    let alpha2 = alpha * alpha;
    let denom = n_dot_h * n_dot_h * (alpha2 - 1.0) + 1.0;
    let distribution = alpha2 / max(3.14159265 * denom * denom, 0.0001);
    let k = (roughness + 1.0) * (roughness + 1.0) * 0.125;
    let geometry_v = n_dot_v / (n_dot_v * (1.0 - k) + k);
    let geometry_l = n_dot_l / (n_dot_l * (1.0 - k) + k);
    let f0 = mix(vec3<f32>(0.04), base, vec3<f32>(metallic));
    let fresnel = f0 + (vec3<f32>(1.0) - f0) * pow(1.0 - v_dot_h, 5.0);
    let specular = distribution * geometry_v * geometry_l * fresnel /
        max(4.0 * n_dot_v * n_dot_l, 0.001);
    let diffuse = (vec3<f32>(1.0) - fresnel) * (1.0 - metallic) * base / 3.14159265;
    let key = (diffuse + specular) * vec3<f32>(3.4, 3.25, 3.05) * n_dot_l;
    let hemisphere = base * mix(0.055, 0.16, n.y * 0.5 + 0.5);
    return vec4<f32>(key + hemisphere, 1.0);
}
