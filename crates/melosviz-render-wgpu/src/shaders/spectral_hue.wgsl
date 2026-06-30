// spectral_hue.wgsl — HSV hue rotation driven by spectral centroid
//
// Applies a full-screen HSV hue rotation overlay blended additively.
// Higher spectral centroid (brighter / more high-frequency content) shifts
// the hue toward cyan/blue; lower centroid (bass-heavy) toward red/orange.
// Matches the Blender bpy driver's hue_shift keyframe channel.

struct FrameUniforms {
    energy:            f32,
    spectral_centroid: f32,
    beat_strength:     f32,
    stem_drums:        f32,
    stem_bass:         f32,
    stem_vocals:       f32,
    stem_other:        f32,
    frame_index:       f32,
    time:              f32,
    palette_r:         f32,
    palette_g:         f32,
    palette_b:         f32,
    _pad:              f32,
}

@group(0) @binding(0)
var<uniform> uniforms: FrameUniforms;

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) uv: vec2<f32>,
}

@vertex
fn vs_main(@builtin(vertex_index) vertex_index: u32) -> VertexOutput {
    var positions = array<vec2<f32>, 3>(
        vec2<f32>(-1.0, -1.0),
        vec2<f32>( 3.0, -1.0),
        vec2<f32>(-1.0,  3.0),
    );
    let pos = positions[vertex_index];
    var out: VertexOutput;
    out.clip_position = vec4<f32>(pos, 0.0, 1.0);
    out.uv = pos * 0.5 + 0.5;
    return out;
}

// HSV → RGB conversion.
fn hsv_to_rgb(h: f32, s: f32, v: f32) -> vec3<f32> {
    let k = vec3<f32>(1.0, 2.0 / 3.0, 1.0 / 3.0);
    let p = abs(fract(h + k) * 6.0 - vec3<f32>(3.0));
    return v * mix(vec3<f32>(1.0), clamp(p - vec3<f32>(1.0), vec3<f32>(0.0), vec3<f32>(1.0)), s);
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    // Map spectral centroid (0=bass, 1=treble) → hue range [0.55, 0.95]
    // (cyan-blue for treble, magenta for bass) — matches the warm/cool
    // palette the Blender hue node uses.
    let hue = mix(0.95, 0.55, uniforms.spectral_centroid);
    // Saturation driven by energy — more energy, more saturated.
    let sat = 0.3 + 0.6 * uniforms.energy;
    // Value (brightness) kept subtle — this layer is additive.
    let val = 0.08 + 0.12 * uniforms.energy;

    let color = hsv_to_rgb(hue, sat, val);
    // Additive blend via alpha — combined with bg_gradient and beat_pulse
    // in the compositor pass.
    return vec4<f32>(color, 0.35 * uniforms.energy);
}
