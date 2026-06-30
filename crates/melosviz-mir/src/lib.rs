//! `melosviz-mir` — Rust-native Music Information Retrieval.
//!
//! Replaces the Python `analyze_wav_rich` / `spec_from_wav_rich` path.
//! Uses `rustfft` for STFT and `hound` for WAV decoding.
//!
//! Output shape matches the Python `RenderSpec v2` JSON contract exactly.
//!
//! Performance target: analyse a 180 s / 44100 Hz mono WAV in < 15 s
//! (projected 1–3 s on Apple M1 Pro).

pub mod dsp;
pub mod mir;
pub mod spec;
pub mod wav;

pub use mir::analyze;
pub use spec::RenderSpec;
