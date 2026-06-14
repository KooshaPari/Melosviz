//! Native notification helpers for Melosviz Desktop.
//!
//! Provides `send_notification` IPC command to fire a system notification
//! when a render is complete (or on error).

use serde::{Deserialize, Serialize};

/// Notification payload.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct NotificationPayload {
    pub title: String,
    pub body: String,
    #[serde(default)]
    pub is_critical: bool,
}

/// Send a native OS notification.
#[tauri::command]
pub async fn send_notification(
    payload: NotificationPayload,
) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        use std::process::Command;
        let sound = if payload.is_critical { "Basso" } else { "Glass" };
        let status = Command::new("osascript")
            .arg("-e")
            .arg(format!(
                "display notification \"{}\" with title \"{}\" sound name \"{}\"",
                escape_applescript(&payload.body),
                escape_applescript(&payload.title),
                sound
            ))
            .status()
            .map_err(|e| format!("Failed to send notification: {e}"))?;
        if !status.success() {
            return Err("osascript exited with failure".to_string());
        }
    }
    #[cfg(not(target_os = "macos"))]
    {
        // Fallback: log to console on non-macOS
        println!("[Notification] {}: {}", payload.title, payload.body);
    }
    Ok(())
}

/// Escape a string for AppleScript `display notification`.
fn escape_applescript(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"").replace('\'', "\\'")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_notification_payload() {
        let p = NotificationPayload {
            title: "Render complete".to_string(),
            body: "Your video is ready.".to_string(),
            is_critical: false,
        };
        assert_eq!(p.title, "Render complete");
    }

    #[test]
    fn test_escape_applescript() {
        assert_eq!(escape_applescript("hello"), "hello");
        assert_eq!(escape_applescript("hello \"world\""), "hello \\\"world\\\"");
        assert_eq!(escape_applescript("it's ok"), "it\\'s ok");
    }
}
