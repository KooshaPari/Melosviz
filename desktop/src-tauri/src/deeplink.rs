//! Deep-link handler for Melosviz Desktop.
//!
//! Registers a custom `melosviz://` URL scheme so external links like
//! `melosviz://job/123` open the app and navigate to the referenced job.

use serde::{Deserialize, Serialize};
use tauri::Emitter;

/// Parsed deep-link payload.
#[derive(Serialize, Deserialize, Debug, Clone, Default)]
pub struct DeepLinkPayload {
    pub scheme: String,
    pub host: String,
    pub path: String,
    pub job_id: Option<String>,
}

/// Parse a melosviz:// URL into a structured payload.
#[tauri::command]
pub fn parse_deep_link(url: String) -> Result<DeepLinkPayload, String> {
    let url = url.trim();
    if !url.starts_with("melosviz://") {
        return Err("Invalid scheme: expected melosviz://".to_string());
    }

    let rest = &url["melosviz://".len()..];
    let (host, path) = match rest.split_once('/') {
        Some((h, p)) => (h.to_string(), format!("/{}" , p)),
        None => (rest.to_string(), "/".to_string()),
    };

    let job_id = if host == "job" && path.len() > 1 {
        Some(path[1..].to_string())
    } else {
        None
    };

    Ok(DeepLinkPayload {
        scheme: "melosviz".to_string(),
        host,
        path,
        job_id,
    })
}

/// Emit a deep-link event to the frontend.
pub fn emit_deep_link<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    url: String,
) -> Result<(), String> {
    let payload = parse_deep_link(url.clone())?;
    app.emit("deep-link", payload)
        .map_err(|e| format!("Failed to emit deep-link event: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_job_link() {
        let result = parse_deep_link("melosviz://job/123".to_string()).unwrap();
        assert_eq!(result.scheme, "melosviz");
        assert_eq!(result.host, "job");
        assert_eq!(result.path, "/123");
        assert_eq!(result.job_id, Some("123".to_string()));
    }

    #[test]
    fn test_parse_root_link() {
        let result = parse_deep_link("melosviz://open".to_string()).unwrap();
        assert_eq!(result.host, "open");
        assert_eq!(result.path, "/");
        assert_eq!(result.job_id, None);
    }

    #[test]
    fn test_parse_invalid_scheme() {
        let result = parse_deep_link("https://example.com".to_string());
        assert!(result.is_err());
    }
}
