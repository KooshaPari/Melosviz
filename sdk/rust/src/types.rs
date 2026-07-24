//! Shared types for the MelosViz Rust SDK.

/// Audio spec to render, following the RenderSpec v2 format.
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct RenderSpec {
    /// Unique identifier for this render job.
    pub spec_id: String,
    /// Path or URL to the source audio file.
    pub audio_source: String,
    /// Target duration in seconds.
    pub duration_s: f64,
    /// Mood category (e.g. "epic", "dreamy", "industrial").
    pub mood: String,
    /// Optional budget in USD for external processing.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub budget_usd: Option<f64>,
}

/// Brief status response from the bridge.
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct RenderStatus {
    /// The spec's unique identifier.
    pub spec_id: String,
    /// Current status string.
    pub status: String,
    /// Progress 0.0 .. 1.0.
    pub progress: f64,
    /// Estimated seconds remaining, if known.
    pub eta_s: Option<f64>,
    /// Error message if failed.
    pub error: Option<String>,
}

/// Health of a single bridge subsystem.
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub enum HealthStatus {
    /// Responding normally.
    Ok,
    /// Degraded but functional.
    Degraded(String),
    /// Not available.
    Down(String),
}

/// A discovered service (adapter, plugin, etc.).
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct ServiceRecord {
    /// Name of the service.
    pub name: String,
    /// Semantic version.
    pub version: String,
    /// Source (e.g. "in-tree", "user-plugins").
    pub source: String,
    /// Whether it's enabled.
    pub enabled: bool,
}
