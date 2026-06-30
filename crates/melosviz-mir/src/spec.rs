//! RenderSpec v2 output types — mirrors the Python `models.py` contract.
//!
//! This is the *output* schema produced by `melosviz-mir` for consumption
//! by the Python conductor (or directly by the wgpu renderer).  The field
//! names and JSON keys match the Python pydantic models exactly.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// Sub-models
// ---------------------------------------------------------------------------

/// Per-stem energy values at one dense keyframe.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct StemFrame {
    pub drums: f32,
    pub bass: f32,
    pub vocals: f32,
    pub other: f32,
}

/// A single dense keyframe (one per 1/fps second of audio).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DenseKeyframe {
    /// Time offset in seconds.
    pub t: f32,
    /// Normalised RMS energy [0, 1].
    pub energy: f32,
    /// Spectral centroid normalised to [0, 1].
    pub brightness: f32,
    /// Estimated valence [0, 1].
    pub valence: f32,
    /// Estimated arousal [0, 1].
    pub arousal: f32,
    /// Beat confidence at this frame [0, 1].
    pub beat_strength: f32,
    /// Onset detection strength [0, 1].
    pub onset_strength: f32,
    /// Raw spectral centroid in Hz.
    pub spectral_centroid: f32,
    /// Per-stem amplitude at this frame.
    pub stems: StemFrame,
    /// Easing hint for the following interval.
    pub easing: String,
}

/// A discrete musical event on the timeline.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimelineEvent {
    pub t: f32,
    #[serde(rename = "type")]
    pub event_type: String,
    pub strength: f32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bar: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub label: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub segment_index: Option<usize>,
}

/// Mood vector (valence + arousal) for a segment.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct MoodVector {
    pub valence: f32,
    pub arousal: f32,
}

/// A semantically-classified scene segment.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SceneSegment {
    pub index: usize,
    pub label: String,
    pub start: f32,
    pub end: f32,
    pub energy_mean: f32,
    pub brightness_mean: f32,
    pub mood: MoodVector,
    pub dominant_stem: String,
}

/// Music Information Retrieval summary for the full track.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct MirSummary {
    pub tempo_bpm: Option<f32>,
    pub tempo_curve: Vec<f32>,
    pub danceability: Option<f32>,
    pub energy_trajectory: Vec<f32>,
    pub brightness_trajectory: Vec<f32>,
    pub valence_trajectory: Vec<f32>,
    pub arousal_trajectory: Vec<f32>,
    pub key: Option<String>,
    pub mode: Option<String>,
    pub chord_sequence: Vec<serde_json::Value>,
}

// ---------------------------------------------------------------------------
// Top-level RenderSpec v2
// ---------------------------------------------------------------------------

/// Metadata block inside RenderSpec (mirrors Python `metadata` dict).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RenderMetadata {
    pub source_audio: String,
    pub sample_rate: u32,
    pub channels: u16,
    pub duration: f64,
    pub fps: u32,
    pub width: u32,
    pub height: u32,
    pub analysis_peak_rms: f32,
    pub estimated_bpm: Option<f32>,
    pub amplitude_envelope: Vec<f32>,
    pub render_spec_version: u32,
    pub n_dense_frames: usize,
    pub n_dense_fps: u32,
}

/// Full RenderSpec v2 — matches the Python `RenderSpec` pydantic model.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RenderSpec {
    pub metadata: RenderMetadata,
    #[serde(default)]
    pub palette: Vec<String>,
    #[serde(default)]
    pub layers: Vec<serde_json::Value>,
    #[serde(default)]
    pub keyframes: Vec<serde_json::Value>,
    #[serde(default)]
    pub timeline: Vec<serde_json::Value>,
    pub dense_keyframes: Vec<DenseKeyframe>,
    pub timeline_events: Vec<TimelineEvent>,
    pub scene_segments: Vec<SceneSegment>,
    pub stem_channels: HashMap<String, Vec<f32>>,
    pub mir: MirSummary,
}
