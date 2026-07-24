#![deny(missing_docs)]
//! Rust SDK for MelosViz — use the `MelosVizClient` to talk to the bridge.

pub mod client;
pub mod discovery;
pub mod error;
pub mod heartbeat;
pub mod types;

pub use client::BridgeClient as MelosVizClient;
pub use error::Error;
pub use types::{HealthStatus, RenderSpec, RenderStatus, ServiceRecord};
