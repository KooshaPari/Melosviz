//! Scene runner — bridges a [`RenderSpec`] to per-frame [`FrameUniforms`]
//! for the wgpu scene layer pipeline.
//!
//! # B17 — RenderSpec v2 → ConductorScene uniform pipeline
//!
//! The [`conductor_uniforms_for_frame`] function is the canonical wiring point:
//! given a `RenderSpec` and a frame index it returns the `FrameUniforms` that
//! feed the ConductorScene WGSL shader.  The logic:
//!
//! 1. Build a [`Timeline`] from the spec's `dense_keyframes`.
//! 2. Sample the timeline at `frame_idx` to get interpolated MIR values
//!    (energy, spectral centroid, beat strength, per-stem amplitudes).
//! 3. Determine the active [`SceneSegment`] for this frame and look up its
//!    palette colour from the spec's `palette` vec.
//! 4. Inject the frame index and palette RGB into the uniforms.
//!
//! This function is pure (no IO, no GPU) so it is covered by unit tests
//! without a Metal/Vulkan adapter.

use crate::spec::RenderSpec;
use crate::timeline::Timeline;
use crate::uniforms::FrameUniforms;

/// Parse one channel (0=R, 1=G, 2=B) from a `#rrggbb` hex string → [0,1].
fn hex_channel(hex: &str, channel: usize) -> f32 {
    let clean = hex.trim().trim_start_matches('#');
    if clean.len() < 6 {
        return [0.0, 0.9, 1.0][channel.min(2)];
    }
    let offset = channel * 2;
    u8::from_str_radix(&clean[offset..offset + 2], 16).unwrap_or(0) as f32 / 255.0
}

/// Resolve the palette RGB for a given frame from the spec.
///
/// Looks up the active segment's `palette_index`; falls back to the first
/// palette entry, then to the default `(0.0, 0.9, 1.0)` if the palette is
/// empty.
fn palette_rgb_for_frame(spec: &RenderSpec, frame_idx: u32) -> (f32, f32, f32) {
    let palette_idx = spec
        .segment_for_frame(frame_idx)
        .map(|s| s.palette_index)
        .unwrap_or(0);

    let hex = spec
        .palette
        .get(palette_idx)
        .or_else(|| spec.palette.first())
        .map(|s| s.as_str())
        .unwrap_or("#00e6ff");

    (
        hex_channel(hex, 0),
        hex_channel(hex, 1),
        hex_channel(hex, 2),
    )
}

/// Build [`FrameUniforms`] for `frame_idx` from a [`RenderSpec`].
///
/// This is the canonical B17 entry point: wire `RenderSpec` v2 MIR data
/// (dense keyframes, stems, palette, segments) into the `FrameUniforms`
/// that the ConductorScene WGSL shader reads.
///
/// # Arguments
///
/// * `spec` — the full `RenderSpec` produced by the Python conductor.
/// * `frame_idx` — zero-based frame index (not time).
///
/// # Returns
///
/// Interpolated `FrameUniforms` with frame index, MIR values, and
/// segment-scoped palette RGB all populated.
pub fn conductor_uniforms_for_frame(spec: &RenderSpec, frame_idx: u32) -> FrameUniforms {
    let timeline = Timeline::from_spec(spec);
    let (palette_r, palette_g, palette_b) = palette_rgb_for_frame(spec, frame_idx);
    timeline
        .sample(frame_idx)
        .with_frame_index(frame_idx)
        .with_palette_rgb(palette_r, palette_g, palette_b)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::spec::{DenseKeyframe, RenderMetadata, SceneSegment, StemFrame};

    fn make_spec_with_keyframe(energy: f32, beat: f32, drums: f32, bass: f32) -> RenderSpec {
        RenderSpec {
            metadata: RenderMetadata {
                fps: 30,
                duration: 1.0,
                ..Default::default()
            },
            dense_keyframes: vec![DenseKeyframe {
                t: 0.0,
                energy,
                spectral_centroid: 0.5,
                beat_strength: beat,
                stems: StemFrame {
                    drums,
                    bass,
                    vocals: 0.2,
                    other: 0.1,
                },
            }],
            palette: vec!["#FF8040".to_string(), "#00E6FF".to_string()],
            ..Default::default()
        }
    }

    #[test]
    fn energy_flows_from_spec_to_uniforms() {
        let spec = make_spec_with_keyframe(0.75, 0.6, 0.4, 0.3);
        let u = conductor_uniforms_for_frame(&spec, 0);
        assert!(
            (u.energy - 0.75).abs() < 1e-5,
            "energy mismatch: {}",
            u.energy
        );
    }

    #[test]
    fn beat_strength_flows_from_spec_to_uniforms() {
        let spec = make_spec_with_keyframe(0.5, 0.9, 0.3, 0.2);
        let u = conductor_uniforms_for_frame(&spec, 0);
        assert!(
            (u.beat_strength - 0.9).abs() < 1e-5,
            "beat_strength mismatch: {}",
            u.beat_strength
        );
    }

    #[test]
    fn stems_flow_from_spec_to_uniforms() {
        let spec = make_spec_with_keyframe(0.5, 0.5, 0.8, 0.7);
        let u = conductor_uniforms_for_frame(&spec, 0);
        assert!(
            (u.stem_drums - 0.8).abs() < 1e-5,
            "stem_drums: {}",
            u.stem_drums
        );
        assert!(
            (u.stem_bass - 0.7).abs() < 1e-5,
            "stem_bass: {}",
            u.stem_bass
        );
        assert!(
            (u.stem_vocals - 0.2).abs() < 1e-5,
            "stem_vocals: {}",
            u.stem_vocals
        );
        assert!(
            (u.stem_other - 0.1).abs() < 1e-5,
            "stem_other: {}",
            u.stem_other
        );
    }

    #[test]
    fn frame_index_is_injected() {
        let spec = make_spec_with_keyframe(0.5, 0.5, 0.5, 0.5);
        let u = conductor_uniforms_for_frame(&spec, 15);
        assert!(
            (u.frame_index - 15.0).abs() < 1e-5,
            "frame_index: {}",
            u.frame_index
        );
    }

    #[test]
    fn palette_from_first_entry_when_no_segment() {
        // No scene_segments — should fall back to palette[0] = "#FF8040"
        let spec = make_spec_with_keyframe(0.5, 0.5, 0.5, 0.5);
        let u = conductor_uniforms_for_frame(&spec, 0);
        // #FF8040 → R=0xFF/255, G=0x80/255, B=0x40/255
        assert!(
            (u.palette_r - 1.0).abs() < 0.005,
            "palette_r: {}",
            u.palette_r
        );
        assert!(
            (u.palette_g - 0.5019).abs() < 0.005,
            "palette_g: {}",
            u.palette_g
        );
        assert!(
            (u.palette_b - 0.2510).abs() < 0.005,
            "palette_b: {}",
            u.palette_b
        );
    }

    #[test]
    fn palette_from_segment_palette_index() {
        // Segment at t=0 with palette_index=1 → "#00E6FF"
        let spec = RenderSpec {
            metadata: RenderMetadata {
                fps: 30,
                duration: 2.0,
                ..Default::default()
            },
            dense_keyframes: vec![DenseKeyframe {
                t: 0.0,
                energy: 0.5,
                ..Default::default()
            }],
            palette: vec!["#FF8040".to_string(), "#00E6FF".to_string()],
            scene_segments: vec![SceneSegment {
                id: "chorus".to_string(),
                label: "chorus".to_string(),
                start: 0.0,
                end: 2.0,
                palette_index: 1,
                ..Default::default()
            }],
            ..Default::default()
        };
        let u = conductor_uniforms_for_frame(&spec, 0);
        // #00E6FF → R=0, G=0xE6/255≈0.902, B=1.0
        assert!(
            (u.palette_r - 0.0).abs() < 0.005,
            "palette_r: {}",
            u.palette_r
        );
        assert!(
            (u.palette_g - 0.902).abs() < 0.005,
            "palette_g: {}",
            u.palette_g
        );
        assert!(
            (u.palette_b - 1.0).abs() < 0.005,
            "palette_b: {}",
            u.palette_b
        );
    }

    #[test]
    fn empty_spec_returns_safe_defaults() {
        let spec = RenderSpec::default();
        let u = conductor_uniforms_for_frame(&spec, 0);
        // All MIR values default to 0; palette defaults to #00e6ff fallback.
        assert_eq!(u.energy, 0.0);
        assert_eq!(u.beat_strength, 0.0);
        assert_eq!(u.stem_drums, 0.0);
    }

    #[test]
    fn interpolation_between_two_keyframes() {
        let spec = RenderSpec {
            metadata: RenderMetadata {
                fps: 10,
                duration: 1.0,
                ..Default::default()
            },
            dense_keyframes: vec![
                DenseKeyframe {
                    t: 0.0,
                    energy: 0.0,
                    ..Default::default()
                },
                DenseKeyframe {
                    t: 1.0,
                    energy: 1.0,
                    ..Default::default()
                },
            ],
            palette: vec!["#FFFFFF".to_string()],
            ..Default::default()
        };
        // frame 5 at fps=10 → t=0.5 → energy should be ~0.5
        let u = conductor_uniforms_for_frame(&spec, 5);
        assert!(
            (u.energy - 0.5).abs() < 0.05,
            "expected ~0.5 energy at midpoint, got {}",
            u.energy
        );
    }

    #[test]
    fn conductor_uniforms_round_trips_via_json_spec() {
        let json = r##"{
            "metadata": {"fps": 30, "duration": 1.0, "width": 1920, "height": 1080, "title": "test"},
            "palette": ["#FF0080"],
            "dense_keyframes": [{"t": 0.0, "energy": 0.65, "spectral_centroid": 0.4,
                                 "beat_strength": 0.8, "stems": {"drums": 0.9, "bass": 0.7,
                                                                   "vocals": 0.3, "other": 0.1}}],
            "scene_segments": [],
            "stems": null,
            "layers": [],
            "overrides": {}
        }"##;
        let spec = RenderSpec::from_json(json).expect("parse spec");
        let u = conductor_uniforms_for_frame(&spec, 0);
        assert!((u.energy - 0.65).abs() < 1e-5, "energy: {}", u.energy);
        assert!(
            (u.beat_strength - 0.8).abs() < 1e-5,
            "beat: {}",
            u.beat_strength
        );
        assert!((u.stem_drums - 0.9).abs() < 1e-5, "drums: {}", u.stem_drums);
        // #FF0080 → R=1.0, G=0.0, B=0.502
        assert!(
            (u.palette_r - 1.0).abs() < 0.005,
            "palette_r: {}",
            u.palette_r
        );
        assert!(
            (u.palette_g - 0.0).abs() < 0.005,
            "palette_g: {}",
            u.palette_g
        );
    }
}
