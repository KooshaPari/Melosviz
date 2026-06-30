//! RenderSpec v2 data model — mirrors melosviz Python `RenderSpec` exactly.
//!
//! All fields match the Python `RenderSpec` / `SceneSegment` / `DenseKeyframe`
//! dataclasses.  Unknown JSON keys are ignored so the Rust crate is forward-
//! compatible with Python-side additions.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Top-level RenderSpec v2 — the canonical timeline JSON produced by the
/// Python conductor (`viz build` / `analyze_wav_rich`).
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct RenderSpec {
    /// Render metadata: width, height, fps, duration, etc.
    pub metadata: RenderMetadata,
    /// HSV/hex palette colours (cycle used by shaders for hue base).
    pub palette: Vec<String>,
    /// Dense per-frame keyframes (one per `1/fps` second of audio).
    pub dense_keyframes: Vec<DenseKeyframe>,
    /// Coarse scene segments (sections: verse, chorus, drop, bridge, …).
    pub scene_segments: Vec<SceneSegment>,
    /// Per-stem amplitude envelopes (drums, bass, vocals, other).
    pub stems: Option<StemEnvelopes>,
    /// Layer stack (from the conductor's scene graph).
    pub layers: Vec<serde_json::Value>,
    /// Free-form override map (from `overrides.yaml` round-trip).
    pub overrides: HashMap<String, serde_json::Value>,
}

/// Render metadata — dimensions, frame rate, duration.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct RenderMetadata {
    pub width: u32,
    pub height: u32,
    pub fps: u32,
    pub duration: f32,
    pub title: String,
}

impl Default for RenderMetadata {
    fn default() -> Self {
        Self {
            width: 1280,
            height: 720,
            fps: 30,
            duration: 0.0,
            title: String::new(),
        }
    }
}

/// A single dense keyframe — one per rendered frame.
///
/// All float fields are normalised to [0, 1] unless noted.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct DenseKeyframe {
    /// Time in seconds from the start of the audio.
    pub t: f32,
    /// Overall signal energy (RMS amplitude, normalised 0–1).
    pub energy: f32,
    /// Spectral centroid normalised to [0, 1] across the Nyquist range.
    pub spectral_centroid: f32,
    /// Beat strength at this frame (0 = no beat, 1 = strong onset).
    pub beat_strength: f32,
    /// Per-stem amplitude at this frame.
    pub stems: StemFrame,
}

/// Instantaneous per-stem amplitude at one keyframe.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct StemFrame {
    pub drums: f32,
    pub bass: f32,
    pub vocals: f32,
    pub other: f32,
}

/// A coarse scene segment (verse, chorus, drop, bridge, intro, outro, …).
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct SceneSegment {
    /// Unique id (e.g. "segment_0").
    pub id: String,
    /// Semantic label (e.g. "verse", "chorus", "drop").
    pub label: String,
    /// Start time in seconds.
    pub start: f32,
    /// End time in seconds.
    pub end: f32,
    /// Scene type hint (e.g. "beat_reactive", "ambient").
    pub scene_type: String,
    /// Dominant palette colour index for this segment.
    pub palette_index: usize,
}

/// Full-track per-stem amplitude envelopes (one sample per dense keyframe).
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct StemEnvelopes {
    pub drums: Vec<f32>,
    pub bass: Vec<f32>,
    pub vocals: Vec<f32>,
    pub other: Vec<f32>,
}

impl RenderSpec {
    /// Parse a `RenderSpec` from a JSON string.
    ///
    /// # Errors
    /// Returns a `serde_json::Error` if the JSON is malformed.
    pub fn from_json(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }

    /// Return the frame count for this spec (`fps * duration`, rounded).
    pub fn total_frames(&self) -> u32 {
        let n = (self.metadata.fps as f32 * self.metadata.duration).round() as u32;
        n.max(1)
    }

    /// Return the segment that contains frame `frame_idx`, or `None`.
    pub fn segment_for_frame(&self, frame_idx: u32) -> Option<&SceneSegment> {
        let t = frame_idx as f32 / self.metadata.fps.max(1) as f32;
        self.scene_segments.iter().find(|s| t >= s.start && t < s.end)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_render_spec_from_json_empty_object() {
        let spec: RenderSpec = serde_json::from_str("{}").expect("empty object should deserialise");
        assert_eq!(spec.metadata.width, 1280);
        assert_eq!(spec.metadata.fps, 30);
        assert!(spec.dense_keyframes.is_empty());
    }

    #[test]
    fn test_render_spec_total_frames() {
        let spec = RenderSpec {
            metadata: RenderMetadata {
                fps: 30,
                duration: 3.0,
                ..Default::default()
            },
            ..Default::default()
        };
        assert_eq!(spec.total_frames(), 90);
    }

    #[test]
    fn test_render_spec_total_frames_min_one() {
        let spec = RenderSpec {
            metadata: RenderMetadata { fps: 30, duration: 0.0, ..Default::default() },
            ..Default::default()
        };
        assert_eq!(spec.total_frames(), 1);
    }

    #[test]
    fn test_segment_for_frame_found() {
        let spec = RenderSpec {
            metadata: RenderMetadata { fps: 30, duration: 10.0, ..Default::default() },
            scene_segments: vec![
                SceneSegment { id: "s0".into(), label: "intro".into(), start: 0.0, end: 5.0, ..Default::default() },
                SceneSegment { id: "s1".into(), label: "verse".into(), start: 5.0, end: 10.0, ..Default::default() },
            ],
            ..Default::default()
        };
        // Frame 60 = t=2.0 → segment 0 (intro)
        assert_eq!(spec.segment_for_frame(60).map(|s| s.label.as_str()), Some("intro"));
        // Frame 180 = t=6.0 → segment 1 (verse)
        assert_eq!(spec.segment_for_frame(180).map(|s| s.label.as_str()), Some("verse"));
    }

    #[test]
    fn test_segment_for_frame_none_beyond_end() {
        let spec = RenderSpec {
            metadata: RenderMetadata { fps: 30, duration: 3.0, ..Default::default() },
            scene_segments: vec![
                SceneSegment { id: "s0".into(), label: "verse".into(), start: 0.0, end: 3.0, ..Default::default() },
            ],
            ..Default::default()
        };
        // Frame 90 = t=3.0 → end is exclusive; no segment
        assert!(spec.segment_for_frame(90).is_none());
    }

    #[test]
    fn test_dense_keyframe_defaults() {
        let kf: DenseKeyframe = serde_json::from_str("{}").expect("empty");
        assert_eq!(kf.energy, 0.0);
        assert_eq!(kf.spectral_centroid, 0.0);
        assert_eq!(kf.beat_strength, 0.0);
        assert_eq!(kf.stems.drums, 0.0);
    }

    #[test]
    fn test_render_spec_from_json_round_trip() {
        let spec = RenderSpec {
            metadata: RenderMetadata {
                width: 1920,
                height: 1080,
                fps: 60,
                duration: 10.0,
                title: "test".into(),
            },
            palette: vec!["#00f5ff".into(), "#ff2fd5".into()],
            dense_keyframes: vec![DenseKeyframe {
                t: 0.0,
                energy: 0.8,
                spectral_centroid: 0.5,
                beat_strength: 1.0,
                stems: StemFrame { drums: 0.9, bass: 0.7, vocals: 0.3, other: 0.1 },
            }],
            ..Default::default()
        };
        let json = serde_json::to_string(&spec).expect("serialise");
        let back: RenderSpec = serde_json::from_str(&json).expect("deserialise");
        assert_eq!(back.metadata.width, 1920);
        assert_eq!(back.palette.len(), 2);
        assert_eq!(back.dense_keyframes.len(), 1);
        assert!((back.dense_keyframes[0].energy - 0.8).abs() < 1e-5);
    }
}
