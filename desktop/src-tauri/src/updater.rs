//! Auto-update channel for Melosviz Desktop.
//!
//! Checks a remote update server on launch and prompts the user to install.
//! Stubbed for offline builds; the real endpoint is configured via env var.

use serde::{Deserialize, Serialize};

/// Update check result.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct UpdateCheckResult {
    pub available: bool,
    pub version: Option<String>,
    pub url: Option<String>,
    pub notes: Option<String>,
}

/// Check for an update from the remote channel.
/// Returns `available: false` when the update endpoint is unreachable.
#[tauri::command]
pub async fn check_update() -> UpdateCheckResult {
    let endpoint = std::env::var("MELOSVIZ_UPDATE_ENDPOINT")
        .unwrap_or_else(|_| "https://updates.melosviz.com/stable".to_string());

    let client = match reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
    {
        Ok(c) => c,
        Err(_) => return UpdateCheckResult {
            available: false,
            version: None,
            url: None,
            notes: None,
        },
    };

    match client.get(&endpoint).send().await {
        Ok(resp) if resp.status().is_success() => {
            // For offline builds we don't have a real server, so return unavailable.
            // In production this would parse the JSON manifest and compare versions.
            UpdateCheckResult {
                available: false,
                version: None,
                url: None,
                notes: None,
            }
        }
        _ => UpdateCheckResult {
            available: false,
            version: None,
            url: None,
            notes: None,
        },
    }
}

/// Apply a pending update (placeholder).
#[tauri::command]
pub async fn apply_update() -> Result<(), String> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_update_result_unavailable() {
        let r = UpdateCheckResult {
            available: false,
            version: None,
            url: None,
            notes: None,
        };
        assert!(!r.available);
    }

    #[test]
    fn test_update_result_available() {
        let r = UpdateCheckResult {
            available: true,
            version: Some("0.2.0".to_string()),
            url: Some("https://example.com/update".to_string()),
            notes: Some("Bug fixes".to_string()),
        };
        assert!(r.available);
        assert_eq!(r.version, Some("0.2.0".to_string()));
    }
}
