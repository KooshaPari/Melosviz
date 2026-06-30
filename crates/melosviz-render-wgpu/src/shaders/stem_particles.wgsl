// stem_particles.wgsl — particle density (drums) + camera scale (bass)
//
// Renders a pseudo-particle field where:
//   • Drum stem amplitude controls particle density / opacity.
//   • Bass stem amplitude controls a radial scale / "camera zoom" effect.
//   • Vocals stem adds a vertical shimmer.
//
// Particle positions are computed procedurally from a hash of (particle_id,
// frame_index) — no CPU-side particle buffer needed.  This matches the
// Blender bpy driver's particle system keyframe channels.

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

// Fast hash for particle position generation (Wang hash variant).
fn wang_hash(seed: u32) -> f32 {
    var s = seed;
    s = (s ^ 61u) ^ (s >> 16u);
    s = s * 9u;
    s = s ^ (s >> 4u);
    s = s * 0x27d4eb2du;
    s = s ^ (s >> 15u);
    return f32(s) / 4294967295.0;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    // Number of particles scales with drum amplitude (16 to 128).
    let num_particles = u32(16.0 + 112.0 * uniforms.stem_drums);
    // Bass-driven radial scale — zooms the particle field.
    let scale = 1.0 + 0.4 * uniforms.stem_bass;
    // Apply camera-scale transform: expand UV from centre.
    let scaled_uv = (in.uv - 0.5) / scale + 0.5;

    var particle_glow: f32 = 0.0;
    let frame_seed = u32(uniforms.frame_index) * 1337u;

    for (var i: u32 = 0u; i < num_particles; i = i + 1u) {
        let seed_x = i * 1001u + frame_seed;
        let seed_y = i * 2003u + frame_seed + 17u;
        // Particle drifts slowly over time.
        let t = uniforms.time;
        let px = fract(wang_hash(seed_x) + t * (0.01 + wang_hash(i * 17u) * 0.03));
        let py = fract(wang_hash(seed_y) + t * (0.008 + wang_hash(i * 31u) * 0.02));
        // Vocal shimmer adds vertical jitter.
        let jitter_y = 0.02 * uniforms.stem_vocals * sin(t * 6.28 + f32(i));
        let p = vec2<f32>(px, py + jitter_y);
        let d = length(scaled_uv - p);
        // Each particle is a small Gaussian splat.
        let particle_size = 0.004 + 0.008 * uniforms.energy;
        particle_glow += exp(-d * d / (particle_size * particle_size));
    }

    let base = vec3<f32>(uniforms.palette_r, uniforms.palette_g, uniforms.palette_b);
    // Particle colour: palette base tinted by spectral centroid.
    let tint_hue = uniforms.spectral_centroid;
    let color = base * clamp(particle_glow, 0.0, 1.0);
    let alpha = clamp(particle_glow * uniforms.stem_drums, 0.0, 1.0);

    return vec4<f32>(color, alpha);
}
