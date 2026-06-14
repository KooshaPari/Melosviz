//! Melosviz Desktop Tauri library.
//!
//! Re-exports all IPC handlers, menu builder, and shared types from
//! submodules so the binary can access them via `melosviz_desktop_lib::*`.

pub mod commands;
pub mod menu;
pub mod dialog;
pub mod notify;
pub mod deeplink;
pub mod updater;

pub use commands::*;
