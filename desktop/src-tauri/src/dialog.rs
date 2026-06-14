//! Native file dialog helpers for Melosviz Desktop.
//!
//! Provides `open_midi_file` and `save_mp4_file` IPC commands that wrap the OS
//! native file picker so the frontend can ask for `.mid` / `.mp4` paths.

use serde::{Deserialize, Serialize};
use tauri_plugin_dialog::DialogExt;

/// Result of a dialog operation.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct DialogResult {
    pub ok: bool,
    pub path: Option<String>,
    pub error: Option<String>,
}

/// Open a native file dialog restricted to MIDI files.
#[tauri::command]
pub async fn open_midi_file<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
) -> DialogResult {
    match app.dialog().file().add_filter("MIDI", &["mid", "midi"]).blocking_pick_file() {
        Some(path) => DialogResult {
            ok: true,
            path: Some(path.to_string()),
            error: None,
        },
        None => DialogResult {
            ok: false,
            path: None,
            error: Some("No file selected".to_string()),
        },
    }
}

/// Open a native save dialog for `.mp4` output.
#[tauri::command]
pub async fn save_mp4_file<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    default_name: String,
) -> DialogResult {
    match app.dialog().file().add_filter("MP4", &["mp4"]).set_file_name(&default_name).blocking_save_file() {
        Some(path) => DialogResult {
            ok: true,
            path: Some(path.to_string()),
            error: None,
        },
        None => DialogResult {
            ok: false,
            path: None,
            error: Some("No file selected".to_string()),
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dialog_result_ok() {
        let r = DialogResult {
            ok: true,
            path: Some("/tmp/test.mid".to_string()),
            error: None,
        };
        assert!(r.ok);
        assert_eq!(r.path, Some("/tmp/test.mid".to_string()));
    }

    #[test]
    fn test_dialog_result_cancelled() {
        let r = DialogResult {
            ok: false,
            path: None,
            error: Some("No file selected".to_string()),
        };
        assert!(!r.ok);
    }
}
