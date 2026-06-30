//! GPU uniform buffer types — RenderSpec keyframe data → wgpu push constants.
//!
//! [`FrameUniforms`] is the per-frame uniform struct pushed to the GPU as
//! either a push-constant block (for pipelines that support it) or a small
//! uniform buffer (for compatibility).  The layout must match the WGSL
//! struct `FrameUniforms` in each shader.
//!
//! # WGSL layout
//!
//! ```wgsl
//! struct FrameUniforms {
//!     energy:             f32,
//!     spectral_centroid:  f32,
//!     beat_strength:      f32,
//!     stem_drums:         f32,
//!     stem_bass:          f32,
//!     stem_vocals:        f32,
//!     stem_other:         f32,
//!     frame_index:        u32,
//!     time:               f32,
//!     palette_r:          f32,
//!     palette_g:          f32,
//!     palette_b:          f32,
//!     _pad:               f32,  // align to 16 bytes
//! }
//! ```
//!
//! `bytemuck::Pod` + `bytemuck::Zeroable` are derived so the struct can be
//! written directly into a `wgpu::Buffer` with `queue.write_buffer`.

use bytemuck::{Pod, Zeroable};
use crate::spec::DenseKeyframe;

/// Per-frame uniform data uploaded to the GPU before each render pass.
///
/// All fields are `f32` to keep alignment simple.  `frame_index` is cast
/// to `u32` at the WGSL layer via bitcast.
#[repr(C)]
#[derive(Debug, Clone, Copy, Default, Pod, Zeroable)]
pub struct FrameUniforms {
    /// Overall signal energy (RMS, 0–1).
    pub energy: f32,
    /// Spectral centroid normalised 0–1 → controls HSV hue rotation.
    pub spectral_centroid: f32,
    /// Beat onset strength (0–1).
    pub beat_strength: f32,
    /// Drum stem amplitude (0–1) → particle density.
    pub stem_drums: f32,
    /// Bass stem amplitude (0–1) → camera scale.
    pub stem_bass: f32,
    /// Vocals stem amplitude (0–1) → emit-colour brightness.
    pub stem_vocals: f32,
    /// Other stem amplitude (0–1).
    pub stem_other: f32,
    /// Frame index (cast to u32 in WGSL via bitcast).
    pub frame_index: f32,
    /// Time in seconds.
    pub time: f32,
    /// Palette colour R (0–1).
    pub palette_r: f32,
    /// Palette colour G (0–1).
    pub palette_g: f32,
    /// Palette colour B (0–1).
    pub palette_b: f32,
    /// Padding to maintain 16-byte (vec4) alignment (4 words to reach 64 bytes).
    pub _pad0: f32,
    pub _pad1: f32,
    pub _pad2: f32,
    pub _pad3: f32,
}

impl FrameUniforms {
    /// Build `FrameUniforms` from a single [`DenseKeyframe`] (no interpolation).
    pub fn from_keyframe(kf: &DenseKeyframe) -> Self {
        Self {
            energy: kf.energy,
            spectral_centroid: kf.spectral_centroid,
            beat_strength: kf.beat_strength,
            stem_drums: kf.stems.drums,
            stem_bass: kf.stems.bass,
            stem_vocals: kf.stems.vocals,
            stem_other: kf.stems.other,
            frame_index: 0.0,
            time: kf.t,
            palette_r: 0.0,
            palette_g: 0.9,
            palette_b: 1.0,
            _pad0: 0.0, _pad1: 0.0, _pad2: 0.0, _pad3: 0.0,
        }
    }

    /// Linear-interpolate between two keyframes by `alpha` ∈ [0, 1].
    pub fn lerp(lo: &DenseKeyframe, hi: &DenseKeyframe, alpha: f32) -> Self {
        let lerp_f = |a: f32, b: f32| a + (b - a) * alpha;
        Self {
            energy: lerp_f(lo.energy, hi.energy),
            spectral_centroid: lerp_f(lo.spectral_centroid, hi.spectral_centroid),
            beat_strength: lerp_f(lo.beat_strength, hi.beat_strength),
            stem_drums: lerp_f(lo.stems.drums, hi.stems.drums),
            stem_bass: lerp_f(lo.stems.bass, hi.stems.bass),
            stem_vocals: lerp_f(lo.stems.vocals, hi.stems.vocals),
            stem_other: lerp_f(lo.stems.other, hi.stems.other),
            frame_index: 0.0,
            time: lerp_f(lo.t, hi.t),
            palette_r: 0.0,
            palette_g: 0.9,
            palette_b: 1.0,
            _pad0: 0.0, _pad1: 0.0, _pad2: 0.0, _pad3: 0.0,
        }
    }

    /// Set the frame index field (cast from u32 to f32 for WGSL bitcast).
    pub fn with_frame_index(mut self, idx: u32) -> Self {
        self.frame_index = idx as f32;
        self
    }

    /// Override the palette colour (pre-parsed from hex).
    pub fn with_palette_rgb(mut self, r: f32, g: f32, b: f32) -> Self {
        self.palette_r = r;
        self.palette_g = g;
        self.palette_b = b;
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::spec::{DenseKeyframe, StemFrame};

    fn kf(energy: f32, sc: f32, beat: f32, drums: f32, bass: f32) -> DenseKeyframe {
        DenseKeyframe {
            t: energy,  // reuse energy as time for simplicity
            energy,
            spectral_centroid: sc,
            beat_strength: beat,
            stems: StemFrame { drums, bass, vocals: 0.0, other: 0.0 },
        }
    }

    #[test]
    fn test_frame_uniforms_size_is_multiple_of_16() {
        // wgpu requires uniform buffers to be aligned to 16 bytes.
        let size = std::mem::size_of::<FrameUniforms>();
        assert_eq!(size % 16, 0, "FrameUniforms must be 16-byte aligned; size={size}");
    }

    #[test]
    fn test_from_keyframe_maps_fields() {
        let k = kf(0.8, 0.6, 0.9, 0.7, 0.5);
        let u = FrameUniforms::from_keyframe(&k);
        assert!((u.energy - 0.8).abs() < 1e-6);
        assert!((u.spectral_centroid - 0.6).abs() < 1e-6);
        assert!((u.beat_strength - 0.9).abs() < 1e-6);
        assert!((u.stem_drums - 0.7).abs() < 1e-6);
        assert!((u.stem_bass - 0.5).abs() < 1e-6);
    }

    #[test]
    fn test_lerp_midpoint() {
        let lo = kf(0.0, 0.0, 0.0, 0.0, 0.0);
        let hi = kf(1.0, 1.0, 1.0, 1.0, 1.0);
        let u = FrameUniforms::lerp(&lo, &hi, 0.5);
        assert!((u.energy - 0.5).abs() < 1e-5);
        assert!((u.spectral_centroid - 0.5).abs() < 1e-5);
        assert!((u.stem_drums - 0.5).abs() < 1e-5);
    }

    #[test]
    fn test_lerp_alpha_zero_equals_lo() {
        let lo = kf(0.2, 0.3, 0.4, 0.5, 0.6);
        let hi = kf(1.0, 1.0, 1.0, 1.0, 1.0);
        let u = FrameUniforms::lerp(&lo, &hi, 0.0);
        assert!((u.energy - 0.2).abs() < 1e-5);
    }

    #[test]
    fn test_lerp_alpha_one_equals_hi() {
        let lo = kf(0.0, 0.0, 0.0, 0.0, 0.0);
        let hi = kf(0.9, 0.8, 0.7, 0.6, 0.5);
        let u = FrameUniforms::lerp(&lo, &hi, 1.0);
        assert!((u.energy - 0.9).abs() < 1e-5);
        assert!((u.spectral_centroid - 0.8).abs() < 1e-5);
    }

    #[test]
    fn test_with_frame_index() {
        let u = FrameUniforms::default().with_frame_index(42);
        assert!((u.frame_index - 42.0).abs() < 1e-5);
    }

    #[test]
    fn test_with_palette_rgb() {
        let u = FrameUniforms::default().with_palette_rgb(0.1, 0.2, 0.3);
        assert!((u.palette_r - 0.1).abs() < 1e-5);
        assert!((u.palette_g - 0.2).abs() < 1e-5);
        assert!((u.palette_b - 0.3).abs() < 1e-5);
    }

    #[test]
    fn test_bytemuck_pod_cast() {
        // Verify Pod allows safe byte-slice cast (required for wgpu buffer writes).
        let u = FrameUniforms { energy: 0.5, ..Default::default() };
        let bytes: &[u8] = bytemuck::bytes_of(&u);
        assert_eq!(bytes.len(), std::mem::size_of::<FrameUniforms>());
    }
}
