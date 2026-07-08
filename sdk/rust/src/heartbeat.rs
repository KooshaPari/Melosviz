//! Simple heartbeat / connectivity check.

use crate::error::{Error, SdkResult};

/// Perform a lightweight connectivity probe against an HTTP endpoint.
///
/// Returns `Ok(true)` on HTTP 200, `Ok(false)` on non-200,
/// and `Err` on connection failure.
pub fn probe(url: &str) -> SdkResult<bool> {
    let resp = reqwest::blocking::get(url)
        .map_err(|e| Error::Io(e.to_string()))?;
    Ok(resp.status().is_success())
}
