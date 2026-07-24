//! Adapter / plugin discovery (stub — delegates to BridgeClient::discover_services).

use crate::error::{Error, SdkResult};
use crate::types::ServiceRecord;

/// In-process adapter discovery (offline mode — reads local adapter registrations).
///
/// For full remote discovery, use [`BridgeClient::discover_services`].
pub fn discover() -> SdkResult<Vec<ServiceRecord>> {
    Err(Error::Unimplemented)
}
