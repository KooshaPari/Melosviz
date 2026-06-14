//! Melosviz Desktop IPC command handlers.
//!
//! Provides `tauri::command` functions that bridge the frontend to the
//! Python FastAPI backend running on localhost:8000.
//!
//! Commands:
//! - `upload_audio` — send a file to /v1/audio/analyze
//! - `render_visualization` — request a visualization spec from /v1/audio/visualize
//! - `playback_control` — start/stop/pause playback (local state)
//! - `get_presets` — fetch theme presets from /v1/presets
//! - `health_check` — ping the backend /v1/health

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Backend base URL (configurable at runtime).
const BACKEND_URL: &str = "http://localhost:8000";

/// Result wrapper for IPC commands.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct IpcResult<T> {
    pub ok: bool,
    pub data: Option<T>,
    pub error: Option<String>,
}

impl<T> IpcResult<T> {
    pub fn success(data: T) -> Self {
        Self {
            ok: true,
            data: Some(data),
            error: None,
        }
    }

    pub fn err(msg: impl Into<String>) -> Self {
        Self {
            ok: false,
            data: None,
            error: Some(msg.into()),
        }
    }
}

/// Request payload for audio analysis.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct AnalyzeRequest {
    pub file_path: String,
    pub analysis_types: Vec<String>,
}

/// Response payload for audio analysis.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct AnalyzeResponse {
    pub status: String,
    pub note_set: Vec<String>,
    pub chord_set: Vec<String>,
    pub scale_set: Vec<String>,
    pub tempo: Option<f64>,
    pub key: Option<String>,
}

/// Request payload for visualization rendering.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct RenderRequest {
    pub file_path: String,
    pub theme: String,
    pub fps: u32,
    pub width: u32,
    pub height: u32,
    pub duration_sec: f64,
    pub export_format: String,
    pub seed: u32,
}

/// Response payload for visualization rendering.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct RenderResponse {
    pub status: String,
    pub message: String,
    pub frame_count: usize,
    pub duration_sec: f64,
    pub render_spec: serde_json::Value,
}

/// Playback state.
#[derive(Serialize, Deserialize, Debug, Clone, Default)]
pub struct PlaybackState {
    pub is_playing: bool,
    pub is_paused: bool,
    pub current_time_ms: u64,
    pub total_duration_ms: u64,
}

/// Playback control action.
#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "snake_case")]
pub enum PlaybackAction {
    Play,
    Pause,
    Stop,
    Seek { position_ms: u64 },
}

// ====================================================================
// IPC Commands
// ====================================================================

/// Upload an audio file to the backend for analysis.
#[tauri::command]
pub async fn upload_audio(request: AnalyzeRequest) -> IpcResult<AnalyzeResponse> {
    let client = reqwest::Client::new();

    let file_path = PathBuf::from(&request.file_path);
    if !file_path.exists() {
        return IpcResult::err(format!("File not found: {}", request.file_path));
    }

    let file_bytes = match tokio::fs::read(&file_path).await {
        Ok(b) => b,
        Err(e) => return IpcResult::err(format!("Failed to read file: {e}")),
    };

    let file_name = file_path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("audio.wav")
        .to_string();

    let form = reqwest::multipart::Form::new()
        .part(
            "file",
            reqwest::multipart::Part::bytes(file_bytes)
                .file_name(file_name)
                .mime_str("audio/wav")
                .unwrap_or_else(|_| reqwest::multipart::Part::bytes(vec![])),
        )
        .text(
            "request",
            serde_json::json!({
                "analysis": request.analysis_types,
                "source_file": request.file_path,
            })
            .to_string(),
        );

    let url = format!("{BACKEND_URL}/v1/audio/analyze");
    let response = match client.post(&url).multipart(form).send().await {
        Ok(r) => r,
        Err(e) => return IpcResult::err(format!("Backend request failed: {e}")),
    };

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return IpcResult::err(format!("Backend error {status}: {body}"));
    }

    match response.json::<serde_json::Value>().await {
        Ok(json) => {
            let resp = AnalyzeResponse {
                status: json
                    .get("status")
                    .and_then(|v| v.as_str())
                    .unwrap_or("ok")
                    .to_string(),
                note_set: extract_string_array(&json, "note_set"),
                chord_set: extract_string_array(&json, "chord_set"),
                scale_set: extract_string_array(&json, "scale_set"),
                tempo: json.get("tempo").and_then(|v| v.as_f64()),
                key: json
                    .get("key")
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string()),
            };
            IpcResult::success(resp)
        }
        Err(e) => IpcResult::err(format!("Failed to parse response: {e}")),
    }
}

/// Request a visualization render from the backend.
#[tauri::command]
pub async fn render_visualization(request: RenderRequest) -> IpcResult<RenderResponse> {
    let client = reqwest::Client::new();

    let file_path = PathBuf::from(&request.file_path);
    if !file_path.exists() {
        return IpcResult::err(format!("File not found: {}", request.file_path));
    }

    let file_bytes = match tokio::fs::read(&file_path).await {
        Ok(b) => b,
        Err(e) => return IpcResult::err(format!("Failed to read file: {e}")),
    };

    let file_name = file_path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("audio.wav")
        .to_string();

    let form = reqwest::multipart::Form::new()
        .part(
            "file",
            reqwest::multipart::Part::bytes(file_bytes)
                .file_name(file_name)
                .mime_str("audio/wav")
                .unwrap_or_else(|_| reqwest::multipart::Part::bytes(vec![])),
        )
        .text(
            "payload",
            serde_json::json!({
                "style": { "type": "default" },
                "fps": request.fps,
                "width": request.width,
                "height": request.height,
                "duration_sec": request.duration_sec,
                "export_format": request.export_format,
                "seed": request.seed,
            })
            .to_string(),
        )
        .text("theme", request.theme)
        .text("analysis", "full")
        .text("fps", request.fps.to_string())
        .text("width", request.width.to_string())
        .text("height", request.height.to_string())
        .text("duration_sec", request.duration_sec.to_string())
        .text("export_format", request.export_format)
        .text("seed", request.seed.to_string());

    let url = format!("{BACKEND_URL}/v1/audio/visualize");
    let response = match client.post(&url).multipart(form).send().await {
        Ok(r) => r,
        Err(e) => return IpcResult::err(format!("Backend request failed: {e}")),
    };

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return IpcResult::err(format!("Backend error {status}: {body}"));
    }

    match response.json::<serde_json::Value>().await {
        Ok(json) => {
            let resp = RenderResponse {
                status: json
                    .get("status")
                    .and_then(|v| v.as_str())
                    .unwrap_or("ok")
                    .to_string(),
                message: json
                    .get("message")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string(),
                frame_count: json
                    .get("frame_count")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0) as usize,
                duration_sec: request.duration_sec,
                render_spec: json
                    .get("render")
                    .cloned()
                    .unwrap_or(serde_json::Value::Null),
            };
            IpcResult::success(resp)
        }
        Err(e) => IpcResult::err(format!("Failed to parse response: {e}")),
    }
}

/// Control playback state (local only; no backend call).
#[tauri::command]
pub fn playback_control(
    action: PlaybackAction,
    state: tauri::State<'_, std::sync::Mutex<PlaybackState>>,
) -> IpcResult<PlaybackState> {
    playback_control_inner(action, state.inner())
}

/// Inner logic for playback control, usable in tests.
pub fn playback_control_inner(
    action: PlaybackAction,
    state: &std::sync::Mutex<PlaybackState>,
) -> IpcResult<PlaybackState> {
    let mut state = match state.lock() {
        Ok(s) => s,
        Err(e) => return IpcResult::err(format!("State lock poisoned: {e}")),
    };

    match action {
        PlaybackAction::Play => {
            state.is_playing = true;
            state.is_paused = false;
        }
        PlaybackAction::Pause => {
            state.is_paused = true;
        }
        PlaybackAction::Stop => {
            state.is_playing = false;
            state.is_paused = false;
            state.current_time_ms = 0;
        }
        PlaybackAction::Seek { position_ms } => {
            state.current_time_ms = position_ms;
        }
    }

    IpcResult::success(state.clone())
}

/// Fetch all available theme presets from the backend.
#[tauri::command]
pub async fn get_presets() -> IpcResult<Vec<serde_json::Value>> {
    let client = reqwest::Client::new();
    let url = format!("{BACKEND_URL}/v1/presets");

    let response = match client.get(&url).send().await {
        Ok(r) => r,
        Err(e) => return IpcResult::err(format!("Backend request failed: {e}")),
    };

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return IpcResult::err(format!("Backend error {status}: {body}"));
    }

    match response.json::<Vec<serde_json::Value>>().await {
        Ok(presets) => IpcResult::success(presets),
        Err(e) => IpcResult::err(format!("Failed to parse presets: {e}")),
    }
}

/// Check backend health.
#[tauri::command]
pub async fn health_check() -> IpcResult<String> {
    let client = reqwest::Client::new();
    let url = format!("{BACKEND_URL}/v1/health");

    match client.get(&url).send().await {
        Ok(r) if r.status().is_success() => IpcResult::success("ok".to_string()),
        Ok(r) => IpcResult::err(format!("Backend unhealthy: {}", r.status())),
        Err(e) => IpcResult::err(format!("Backend unreachable: {e}")),
    }
}

// ====================================================================
// Helpers
// ====================================================================

pub fn extract_string_array(value: &serde_json::Value, key: &str) -> Vec<String> {
    value
        .get(key)
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ipc_result_success() {
        let r: IpcResult<i32> = IpcResult::success(42);
        assert!(r.ok);
        assert_eq!(r.data, Some(42));
        assert!(r.error.is_none());
    }

    #[test]
    fn test_ipc_result_err() {
        let r: IpcResult<i32> = IpcResult::err("something went wrong");
        assert!(!r.ok);
        assert!(r.data.is_none());
        assert_eq!(r.error, Some("something went wrong".to_string()));
    }

    #[test]
    fn test_playback_control_play() {
        let state = std::sync::Mutex::new(PlaybackState::default());
        let result = playback_control_inner(PlaybackAction::Play, &state);
        assert!(result.ok);
        let data = result.data.unwrap();
        assert!(data.is_playing);
        assert!(!data.is_paused);
    }

    #[test]
    fn test_playback_control_pause() {
        let state = std::sync::Mutex::new(PlaybackState {
            is_playing: true,
            ..Default::default()
        });
        let result = playback_control_inner(PlaybackAction::Pause, &state);
        assert!(result.ok);
        let data = result.data.unwrap();
        assert!(data.is_paused);
    }

    #[test]
    fn test_playback_control_seek() {
        let state = std::sync::Mutex::new(PlaybackState::default());
        let result = playback_control_inner(PlaybackAction::Seek { position_ms: 5000 }, &state);
        assert!(result.ok);
        let data = result.data.unwrap();
        assert_eq!(data.current_time_ms, 5000);
    }

    #[test]
    fn test_extract_string_array() {
        let json = serde_json::json!({
            "note_set": ["C", "D", "E"],
            "empty": [],
            "missing": null,
        });
        assert_eq!(extract_string_array(&json, "note_set"), vec!["C", "D", "E"]);
        assert!(extract_string_array(&json, "empty").is_empty());
        assert!(extract_string_array(&json, "missing").is_empty());
        assert!(extract_string_array(&json, "nonexistent").is_empty());
    }
}
