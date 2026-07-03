// conductor.wgsl — B10 conductor scene
//
// Renders a conductor figure coordinating instrument sections:
//   • Center figure + animated baton: beat_strength and energy.
//   • Left percussion section: drum stem.
//   • Lower strings/bass section: bass stem.
//   • Upper vocal section: vocal stem.
//   • Right harmony/other section: other stem.

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

fn sd_circle(p: vec2<f32>, center: vec2<f32>, radius: f32) -> f32 {
    return length(p - center) - radius;
}

fn sd_segment(p: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> f32 {
    let pa = p - a;
    let ba = b - a;
    let h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
    return length(pa - ba * h);
}

fn soft_shape(distance: f32, width: f32) -> f32 {
    return 1.0 - smoothstep(0.0, width, distance);
}

fn section_arc(
    uv: vec2<f32>,
    center: vec2<f32>,
    radius: f32,
    width: f32,
    angle_center: f32,
    angle_width: f32,
) -> f32 {
    let p = uv - center;
    let r = length(p);
    let angle = atan2(p.y, p.x);
    let angle_delta = abs(atan2(sin(angle - angle_center), cos(angle - angle_center)));
    let band = 1.0 - smoothstep(width, width + 0.018, abs(r - radius));
    let wedge = 1.0 - smoothstep(angle_width, angle_width + 0.18, angle_delta);
    return band * wedge;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let uv = in.uv;
    let aspect_uv = vec2<f32>((uv.x - 0.5) * 1.35 + 0.5, uv.y);
    let stage_center = vec2<f32>(0.5, 0.47);
    let palette = vec3<f32>(uniforms.palette_r, uniforms.palette_g, uniforms.palette_b);

    let gesture = 0.12 + 0.08 * uniforms.energy;
    let beat = uniforms.beat_strength;
    let baton_phase = sin(uniforms.time * 7.0 + beat * 2.5);

    // Conductor body.
    let head = soft_shape(sd_circle(aspect_uv, vec2<f32>(0.5, 0.37), 0.035), 0.012);
    let torso = soft_shape(sd_segment(aspect_uv, vec2<f32>(0.5, 0.41), vec2<f32>(0.5, 0.58)), 0.05);
    let left_arm = soft_shape(
        sd_segment(
            aspect_uv,
            vec2<f32>(0.48, 0.46),
            vec2<f32>(0.39 - gesture * 0.35, 0.44 + 0.04 * baton_phase),
        ),
        0.018,
    );
    let baton_start = vec2<f32>(0.52, 0.45);
    let baton_end = vec2<f32>(0.62 + gesture * 0.35, 0.36 + 0.08 * baton_phase);
    let right_arm = soft_shape(sd_segment(aspect_uv, baton_start, baton_end), 0.017);
    let baton = soft_shape(sd_segment(aspect_uv, baton_end, baton_end + vec2<f32>(0.085, -0.065)), 0.006);
    let baton_glow = soft_shape(sd_circle(aspect_uv, baton_end, 0.03 + 0.03 * beat), 0.055) * beat;

    let conductor_mask = clamp(head + torso + left_arm + right_arm + baton, 0.0, 1.0);
    let conductor_color = mix(vec3<f32>(0.86, 0.88, 0.92), palette + vec3<f32>(0.25), 0.25);

    // Instrument sections arranged around the conductor.
    let drums = section_arc(aspect_uv, stage_center, 0.34, 0.035, 2.72, 0.36);
    let bass = section_arc(aspect_uv, stage_center, 0.38, 0.04, -1.78, 0.46);
    let vocals = section_arc(aspect_uv, stage_center, 0.31, 0.032, 1.55, 0.42);
    let other = section_arc(aspect_uv, stage_center, 0.34, 0.035, 0.42, 0.38);

    let pulse = 0.18 + 0.55 * uniforms.energy + 0.45 * beat;
    let drum_color = vec3<f32>(1.0, 0.30, 0.18) * (0.25 + pulse * uniforms.stem_drums);
    let bass_color = vec3<f32>(0.28, 0.78, 1.0) * (0.22 + pulse * uniforms.stem_bass);
    let vocal_color = vec3<f32>(1.0, 0.55, 0.92) * (0.22 + pulse * uniforms.stem_vocals);
    let other_color = vec3<f32>(0.80, 1.0, 0.34) * (0.20 + pulse * uniforms.stem_other);

    var color = vec3<f32>(0.0);
    color += drum_color * drums;
    color += bass_color * bass;
    color += vocal_color * vocals;
    color += other_color * other;
    color += conductor_color * conductor_mask;
    color += mix(palette, vec3<f32>(1.0, 0.94, 0.55), 0.6) * baton_glow;

    let podium = soft_shape(sd_segment(aspect_uv, vec2<f32>(0.42, 0.64), vec2<f32>(0.58, 0.64)), 0.025);
    color += vec3<f32>(0.18, 0.20, 0.24) * podium;

    let alpha = clamp(
        conductor_mask + baton_glow * 0.85 + drums + bass + vocals + other + podium * 0.8,
        0.0,
        0.92,
    );
    return vec4<f32>(color, alpha);
}
