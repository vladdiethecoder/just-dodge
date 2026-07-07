// Debug overlay shader: solid-color lines (no lighting, no texture)
struct Uniforms {
    mvp: mat4x4<f32>,
}
@group(0) @binding(0) var<uniform> uniforms: Uniforms;

struct VOut {
    @builtin(position) pos: vec4<f32>,
    @location(0) color: vec4<f32>,
}

@vertex
fn vs_main(@location(0) position: vec3<f32>, @location(1) color: vec3<f32>) -> VOut {
    var out: VOut;
    out.pos = uniforms.mvp * vec4(position, 1.0);
    out.color = vec4(color, 1.0);
    return out;
}

@fragment
fn fs_main(in: VOut) -> @location(0) vec4<f32> {
    return in.color;
}
