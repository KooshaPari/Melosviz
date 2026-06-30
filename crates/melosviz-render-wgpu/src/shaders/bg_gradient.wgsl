// bg_gradient.wgsl — segment-label background colour shader
//
// Renders a full-screen gradient whose base colour is driven by the
// segment palette colour (palette_r/g/b in FrameUniforms) and whose
// brightness is modulated by overall signal energy.
//
// Visual vocabulary: matches the Blender `build_bpy_script` world
// background colour channel (segment label → HSV hue → world bg).

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

// Full-screen triangle (no vertex buffer needed).
@vertex
fn vs_main(@builtin(vertex_index) vertex_index: u32) -> VertexOutput {
    // Three vertices covering the entire clip space via a large triangle.
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

// Hue → RGB conversion (HSV with S=V=1).
fn hue_to_rgb(h: f32) -> vec3<f32> {
    let k = vec3<f32>(1.0, 2.0 / 3.0, 1.0 / 3.0);
    let p = abs(fract(vec3<f32>(h, h, h) + k) * 6.0 - vec3<f32>(3.0, 3.0, 3.0));
    return clamp(p - vec3<f32>(1.0, 1.0, 1.0), vec3<f32>(0.0, 0.0, 0.0), vec3<f32>(1.0, 1.0, 1.0));
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    // Palette colour from the current segment.
    let base_color = vec3<f32>(uniforms.palette_r, uniforms.palette_g, uniforms.palette_b);

    // Vertical gradient: darker at bottom, brighter at top.
    let gradient = mix(0.15, 0.45, in.uv.y);

    // Energy modulates overall brightness (breathe with the music).
    let brightness = gradient * (0.5 + 0.5 * uniforms.energy);

    // Subtle spectral hue shift layered over the palette colour.
    let hue_shift = hue_to_rgb(uniforms.spectral_centroid * 0.25 + 0.6);
    let color = mix(base_color, hue_shift, 0.15) * brightness;

    return vec4<f32>(color, 1.0);
}
