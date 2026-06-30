// beat_pulse.wgsl — emitter scale + radial glow driven by beat energy
//
// Renders a radial glow centred at the screen mid-point whose radius and
// brightness scale with `energy` and `beat_strength`.  On strong beats
// the glow blooms outward, matching the Blender bpy driver's emitter
// scale keyframe channel (energy → MeshObject.scale).

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

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    // Distance from centre (aspect-corrected for 16:9).
    let centre = vec2<f32>(0.5, 0.5);
    let aspect_uv = vec2<f32>((in.uv.x - 0.5) * 1.7778, in.uv.y - 0.5);
    let dist = length(aspect_uv);

    // Emitter radius scales with energy + beat_strength.
    let emitter_radius = 0.05 + 0.20 * uniforms.energy + 0.15 * uniforms.beat_strength;
    // Glow falloff — smooth exponential from emitter edge.
    let glow_falloff = exp(-max(dist - emitter_radius, 0.0) * 6.0);

    // Palette-coloured glow tinted by spectral centroid.
    let base = vec3<f32>(uniforms.palette_r, uniforms.palette_g, uniforms.palette_b);
    // Inner emitter: hot white-blue core on beat.
    let core_brightness = smoothstep(emitter_radius, emitter_radius * 0.3, dist)
        * uniforms.beat_strength;
    let core = vec3<f32>(0.8, 0.95, 1.0) * core_brightness;

    let color = base * glow_falloff + core;
    let alpha = clamp(glow_falloff + core_brightness, 0.0, 1.0);

    return vec4<f32>(color, alpha);
}
