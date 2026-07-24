//! SDK error type.

use core::fmt;

/// Result alias for the MelosViz SDK.
pub type SdkResult<T> = Result<T, Error>;

/// Unified error for the MelosViz Rust SDK.
#[derive(Debug)]
pub enum Error {
    /// Wrapped IO / other string error.
    Io(String),
    /// JSON serialization/deserialization error.
    Json(String),
    /// HTTP error with status code.
    Http {     /// HTTP status code from the bridge endpoint.
    status: u16,     /// Response body text (truncated if large).
    body: String },
    /// Feature not yet implemented.
    Unimplemented,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(e) => write!(f, "I/O: {e}"),
            Self::Json(e) => write!(f, "JSON: {e}"),
            Self::Http { status, body } => write!(f, "HTTP {status}: {body}"),
            Self::Unimplemented => write!(f, "not yet implemented"),
        }
    }
}

#[cfg(feature = "std")]
impl std::error::Error for Error {}

impl From<serde_json::Error> for Error {
    fn from(e: serde_json::Error) -> Self {
        Self::Json(e.to_string())
    }
}
