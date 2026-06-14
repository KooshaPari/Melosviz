//! Melosviz Desktop Tauri library.
//!
//! Re-exports all IPC handlers, menu builder, and shared types from
//! submodules so the binary can access them via `melosviz_desktop_lib::*`.

pub mod commands;
pub mod menu;

pub use commands::*;
