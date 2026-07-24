//! HTTP client for the MelosViz bridge API.

use crate::error::{Error, SdkResult};
use crate::types::{HealthStatus, RenderSpec, RenderStatus, ServiceRecord};

/// Client for communicating with the MelosViz bridge over HTTP.
pub struct BridgeClient {
    base_url: String,
    api_key: Option<String>,
    client: reqwest::blocking::Client,
}

impl BridgeClient {
    /// Create a new client targeting the given bridge base URL.
    ///
    /// The `api_key` is passed via `Authorization: Bearer <key>` header.
    pub fn new(base_url: &str, api_key: Option<String>) -> Self {
        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            api_key,
            client: reqwest::blocking::Client::new(),
        }
    }

    fn headers(&self) -> reqwest::header::HeaderMap {
        let mut h = reqwest::header::HeaderMap::new();
        if let Some(ref key) = self.api_key {
            let val = format!("Bearer {key}");
            if let Ok(v) = reqwest::header::HeaderValue::from_str(&val) {
                h.insert(reqwest::header::AUTHORIZATION, v);
            }
        }
        h
    }

    /// Submit a render spec and return the response status.
    pub fn submit_render(&self, spec: &RenderSpec) -> SdkResult<RenderStatus> {
        let resp = self
            .client
            .post(format!("{}/render", self.base_url))
            .headers(self.headers())
            .json(spec)
            .send()
            .map_err(|e| Error::Io(e.to_string()))?;

        let status = resp.status().as_u16();
        let body = resp.text().unwrap_or_default();

        if status != 200 {
            return Err(Error::Http { status, body });
        }

        serde_json::from_str(&body).map_err(Into::into)
    }

    /// Fetch current render status for a spec_id.
    pub fn get_render_status(&self, spec_id: &str) -> SdkResult<RenderStatus> {
        let resp = self
            .client
            .get(format!("{}/render/{spec_id}", self.base_url))
            .headers(self.headers())
            .send()
            .map_err(|e| Error::Io(e.to_string()))?;

        let status = resp.status().as_u16();
        let body = resp.text().unwrap_or_default();

        if status != 200 {
            return Err(Error::Http { status, body });
        }

        serde_json::from_str(&body).map_err(Into::into)
    }

    /// Probe bridge health.
    pub fn health(&self) -> SdkResult<HealthStatus> {
        let resp = self
            .client
            .get(format!("{}/health", self.base_url))
            .headers(self.headers())
            .send()
            .map_err(|e| Error::Io(e.to_string()))?;

        let status = resp.status().as_u16();
        let body = resp.text().unwrap_or_default();

        if status == 200 {
            if body.contains("ok") || body.contains("healthy") {
                return Ok(HealthStatus::Ok);
            }
            return Ok(HealthStatus::Degraded(body));
        }

        Ok(HealthStatus::Down(format!("HTTP {status}: {body}")))
    }

    /// List discovered adapters/plugins.
    pub fn discover_services(&self) -> SdkResult<Vec<ServiceRecord>> {
        Err(Error::Unimplemented)
    }
}
