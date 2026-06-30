//! Keyframe timeline — frame index → interpolated `FrameUniforms`.
//!
//! The `dense_keyframes` array in a RenderSpec v2 has one entry per
//! rendered frame (one per `1/fps` second).  This module provides a
//! simple binary-search lookup that interpolates between the two nearest
//! keyframes, matching the Python animator's behaviour.

use crate::spec::{DenseKeyframe, RenderSpec};
use crate::uniforms::FrameUniforms;

/// Pre-indexed keyframe timeline built from a [`RenderSpec`].
///
/// Holds a reference-counted slice of [`DenseKeyframe`]s and exposes a
/// fast `sample(frame_idx)` method that linear-interpolates between the
/// two bracketing keyframes.
pub struct Timeline {
    keyframes: Vec<DenseKeyframe>,
    fps: f32,
}

impl Timeline {
    /// Build a `Timeline` from a [`RenderSpec`].
    pub fn from_spec(spec: &RenderSpec) -> Self {
        Self {
            keyframes: spec.dense_keyframes.clone(),
            fps: spec.metadata.fps.max(1) as f32,
        }
    }

    /// Sample the timeline at `frame_idx`, returning interpolated uniforms.
    ///
    /// If `dense_keyframes` is empty, returns a default zero-energy frame
    /// (safe for smoke tests / pre-analysis renders).
    pub fn sample(&self, frame_idx: u32) -> FrameUniforms {
        if self.keyframes.is_empty() {
            return FrameUniforms::default();
        }
        let t = frame_idx as f32 / self.fps;
        // Find the two bracketing keyframes by time.
        let idx = self
            .keyframes
            .partition_point(|kf| kf.t <= t)
            .saturating_sub(1);
        let lo = &self.keyframes[idx];
        if idx + 1 >= self.keyframes.len() {
            return FrameUniforms::from_keyframe(lo);
        }
        let hi = &self.keyframes[idx + 1];
        let dt = hi.t - lo.t;
        let alpha = if dt > 1e-6 { (t - lo.t) / dt } else { 0.0 };
        FrameUniforms::lerp(lo, hi, alpha)
    }

    /// Number of keyframes in the timeline.
    pub fn len(&self) -> usize {
        self.keyframes.len()
    }

    /// True if the timeline has no keyframes.
    pub fn is_empty(&self) -> bool {
        self.keyframes.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::spec::{DenseKeyframe, RenderMetadata, RenderSpec, StemFrame};

    fn make_spec(keyframes: Vec<DenseKeyframe>) -> RenderSpec {
        RenderSpec {
            metadata: RenderMetadata { fps: 30, duration: 10.0, ..Default::default() },
            dense_keyframes: keyframes,
            ..Default::default()
        }
    }

    #[test]
    fn test_empty_timeline_returns_default() {
        let spec = make_spec(vec![]);
        let tl = Timeline::from_spec(&spec);
        let u = tl.sample(0);
        assert_eq!(u.energy, 0.0);
        assert_eq!(u.spectral_centroid, 0.0);
    }

    #[test]
    fn test_single_keyframe_no_interpolation() {
        let spec = make_spec(vec![DenseKeyframe {
            t: 0.0,
            energy: 0.75,
            spectral_centroid: 0.5,
            beat_strength: 1.0,
            stems: StemFrame { drums: 0.9, bass: 0.0, vocals: 0.0, other: 0.0 },
        }]);
        let tl = Timeline::from_spec(&spec);
        let u = tl.sample(0);
        assert!((u.energy - 0.75).abs() < 1e-5);
        assert!((u.spectral_centroid - 0.5).abs() < 1e-5);
    }

    #[test]
    fn test_two_keyframes_midpoint_interpolation() {
        let spec = make_spec(vec![
            DenseKeyframe {
                t: 0.0,
                energy: 0.0,
                spectral_centroid: 0.0,
                beat_strength: 0.0,
                stems: StemFrame::default(),
            },
            DenseKeyframe {
                t: 1.0,
                energy: 1.0,
                spectral_centroid: 1.0,
                beat_strength: 1.0,
                stems: StemFrame { drums: 1.0, ..Default::default() },
            },
        ]);
        let tl = Timeline::from_spec(&spec);
        // Frame 15 = t=0.5 → midpoint between the two keyframes
        let u = tl.sample(15);
        assert!((u.energy - 0.5).abs() < 1e-4, "energy should be 0.5, got {}", u.energy);
        assert!((u.spectral_centroid - 0.5).abs() < 1e-4);
        assert!((u.stem_drums - 0.5).abs() < 1e-4);
    }

    #[test]
    fn test_sample_beyond_last_keyframe_clamps() {
        let spec = make_spec(vec![
            DenseKeyframe { t: 0.0, energy: 0.0, ..Default::default() },
            DenseKeyframe { t: 1.0, energy: 1.0, ..Default::default() },
        ]);
        let tl = Timeline::from_spec(&spec);
        // Frame 9999 well beyond last kf → should use last keyframe value
        let u = tl.sample(9999);
        assert!((u.energy - 1.0).abs() < 1e-5);
    }

    #[test]
    fn test_timeline_len() {
        let spec = make_spec(vec![
            DenseKeyframe::default(),
            DenseKeyframe::default(),
            DenseKeyframe::default(),
        ]);
        let tl = Timeline::from_spec(&spec);
        assert_eq!(tl.len(), 3);
        assert!(!tl.is_empty());
    }
}
