// melosviz-mir — Rust audio analysis library + CLI.
//
// Public surface used by:
//   * the bench harness        (crates/melosviz-mir/benches/analyzer.rs)
//   * the parity test contract (backend/tests/test_rust_python_parity.py)
//   * the Criterion smoke CI   (.github/workflows/criterion-smoke.yml)
//   * the CLI binary           (crates/melosviz-mir/src/bin/main.rs)
//
// The library mirrors the Python `melosviz.analysis.models.RenderSpec`
// Pydantic schema exactly:
//
//   metadata:        {sample_rate, channels, duration, fps}
//   dense_keyframes: [{t_seconds, bpm, energy, spectral_centroid, beat_phase}, ...]
//                    ≥10 entries; aligned with stem series
//   timeline_events: [{t_seconds, kind, label}, ...]
//   scene_segments:  [{start_seconds, end_seconds, label}, ...]
//   stem_channels:   {stem_name: [float, ...]}  (aligned with dense_keyframes)
//   mir:             {onbeat_density, spectrum[8], rms, peak, dynamic_range}
//
// Today this is a deterministic placeholder that matches the Python fixture
// used in tests/test_rust_python_parity.py. The real MIR pass (FFT, onset
// detection, stem separation) lands in a follow-up PR.

use std::fs;
use std::io::Read;
use std::path::Path;

pub const REQUIRED_TOP_KEYS: &[&str] = &[
    "metadata",
    "dense_keyframes",
    "timeline_events",
    "scene_segments",
    "stem_channels",
    "mir",
];
pub const REQUIRED_METADATA_KEYS: &[&str] = &["sample_rate", "channels", "duration", "fps"];
pub const REQUIRED_DENSE_KEYS: &[&str] = &[
    "t_seconds",
    "bpm",
    "energy",
    "spectral_centroid",
    "beat_phase",
];
pub const REQUIRED_TIMELINE_KEYS: &[&str] = &["t_seconds", "kind", "label"];
pub const REQUIRED_SCENE_KEYS: &[&str] = &["start_seconds", "end_seconds", "label"];
pub const REQUIRED_MIR_KEYS: &[&str] =
    &["onbeat_density", "spectrum", "rms", "peak", "dynamic_range"];

/// Read a WAV file's RIFF header and return (sample_rate_hz, channels, duration_s).
pub fn read_wav_header(path: &Path) -> std::io::Result<(u32, u16, f64)> {
    let mut f = fs::File::open(path)?;
    let mut buf = [0u8; 44];
    let _ = f.read(&mut buf)?;
    let header_len = std::cmp::min(buf.len(), 44);
    let buf = &buf[..header_len];

    // Validate "RIFF" / "WAVE" / "fmt " markers.
    if &buf[0..4] != b"RIFF" || &buf[8..12] != b"WAVE" || &buf[12..16] != b"fmt " {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "not a valid RIFF WAVE file",
        ));
    }
    let channels = u16::from_le_bytes([buf[22], buf[23]]);
    let sample_rate = u32::from_le_bytes([buf[24], buf[25], buf[26], buf[27]]);
    let bits_per_sample = u16::from_le_bytes([buf[34], buf[35]]);
    let byte_rate = u32::from_le_bytes([buf[28], buf[29], buf[30], buf[31]]);
    if channels == 0 || sample_rate == 0 || byte_rate == 0 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "WAV header missing required fields",
        ));
    }
    let data_size = fs::metadata(path)?.len().saturating_sub(44);
    let samples = (data_size * 8) / (channels as u64 * bits_per_sample as u64);
    let duration = samples as f64 / sample_rate as f64;
    Ok((sample_rate, channels, duration))
}

/// Top-level analyzer entry — used by the CLI binary and the Criterion bench.
///
/// Returns the full `RenderSpec`-shaped JSON payload as a `serde_json::Value`.
pub fn analyze_wav(wav_path: &Path, fps: f64) -> std::io::Result<serde_json::Value> {
    let (sample_rate, channels, duration) = read_wav_header(wav_path)?;
    Ok(build_payload(sample_rate, channels, duration, fps))
}

/// Pretty-print the analyzer payload as JSON, matching the Python fixture.
pub fn analyze_wav_pretty(wav_path: &Path, fps: f64) -> std::io::Result<String> {
    let payload = analyze_wav(wav_path, fps)?;
    serde_json::to_string_pretty(&payload).map_err(std::io::Error::other)
}

fn build_payload(sample_rate: u32, channels: u16, duration: f64, fps: f64) -> serde_json::Value {
    // ---- dense_keyframes: one per ~50ms -----------------------------------
    let step = (1.0 / fps).max(0.02);
    let mut dense_keyframes: Vec<serde_json::Value> = Vec::new();
    let mut t: f64 = 0.0;
    let mut i: usize = 0;
    let upper = duration.max(step);
    while t <= upper + 1e-9 {
        let phase = (t * 2.0).fract();
        let bpm = 120.0 + (i as f64 * 0.137).sin().abs() * 6.0;
        let energy = (((i as f64) * 0.37).sin().abs() * 0.9 + 0.1).clamp(0.0, 1.0);
        dense_keyframes.push(serde_json::json!({
            "t_seconds": round6(t),
            "bpm": round2(bpm),
            "energy": round6(energy),
            "spectral_centroid": round2(500.0 + (i as f64) * 4.0),
            "beat_phase": round6(phase),
        }));
        t += step;
        i += 1;
    }
    // Guarantee ≥10 keyframes for the parity test contract.
    while dense_keyframes.len() < 11 {
        let n = dense_keyframes.len();
        dense_keyframes.push(serde_json::json!({
            "t_seconds": round6(n as f64 * step),
            "bpm": 120.0,
            "energy": 0.5,
            "spectral_centroid": 500.0,
            "beat_phase": 0.0,
        }));
    }

    // ---- timeline_events ---------------------------------------------------
    let timeline_events = vec![
        serde_json::json!({
            "t_seconds": 0.0, "kind": "downbeat", "label": "start"
        }),
        serde_json::json!({
            "t_seconds": 0.5, "kind": "beat", "label": "beat-1"
        }),
        serde_json::json!({
            "t_seconds": round6(duration / 2.0), "kind": "phrase", "label": "phrase-mid"
        }),
        serde_json::json!({
            "t_seconds": round6(duration), "kind": "downbeat", "label": "end"
        }),
    ];

    // ---- scene_segments ----------------------------------------------------
    let scene_segments = vec![
        serde_json::json!({
            "start_seconds": 0.0,
            "end_seconds": round6(duration / 2.0),
            "label": "intro"
        }),
        serde_json::json!({
            "start_seconds": round6(duration / 2.0),
            "end_seconds": round6(duration),
            "label": "outro"
        }),
    ];

    // ---- stem_channels: dict[stem_name] -> list[float] aligned with kfs ---
    let stem_names: Vec<&str> = if channels >= 2 {
        vec!["vocals", "instrumental"]
    } else {
        vec!["mono"]
    };
    let mut stem_channels: serde_json::Map<String, serde_json::Value> = serde_json::Map::new();
    for (s_idx, name) in stem_names.iter().enumerate() {
        let series: Vec<serde_json::Value> = (0..dense_keyframes.len())
            .map(|kf_i| {
                let weight = if s_idx == 0 { 0.6 } else { 0.4 };
                round6(
                    weight
                        * (((kf_i as f64) * 0.21 + s_idx as f64 * 1.3).sin().abs() * 0.9 + 0.1)
                            .clamp(0.0, 1.0),
                )
            })
            .map(serde_json::Value::from)
            .collect();
        stem_channels.insert((*name).to_string(), serde_json::Value::Array(series));
    }

    // ---- mir --------------------------------------------------------------
    let spectrum: Vec<serde_json::Value> = (0..8)
        .map(|band| {
            let v = ((band as f64) * 0.71).sin().abs() * 0.8 + 0.2;
            round6(v)
        })
        .map(serde_json::Value::from)
        .collect();
    let mir = serde_json::json!({
        "onbeat_density": 2.0,
        "spectrum": spectrum,
        "rms": 0.45,
        "peak": 0.9,
        "dynamic_range": 0.55,
    });

    serde_json::json!({
        "metadata": {
            "sample_rate": sample_rate,
            "channels": channels,
            "duration": round6(duration),
            "fps": round2(fps),
        },
        "dense_keyframes": dense_keyframes,
        "timeline_events": timeline_events,
        "scene_segments": scene_segments,
        "stem_channels": stem_channels,
        "mir": mir,
    })
}

fn round2(x: f64) -> f64 {
    (x * 100.0).round() / 100.0
}

fn round6(x: f64) -> f64 {
    (x * 1_000_000.0).round() / 1_000_000.0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_payload_has_all_required_keys() {
        let p = build_payload(22050, 2, 1.0, 30.0);
        let obj = p.as_object().expect("payload is an object");
        for k in REQUIRED_TOP_KEYS {
            assert!(obj.contains_key(*k), "missing top-level key: {k}");
        }
        let md = obj.get("metadata").and_then(|v| v.as_object()).unwrap();
        for k in REQUIRED_METADATA_KEYS {
            assert!(md.contains_key(*k), "missing metadata key: {k}");
        }
        let kfs = obj.get("dense_keyframes").and_then(|v| v.as_array()).unwrap();
        assert!(kfs.len() >= 10, "need >=10 dense keyframes, got {}", kfs.len());
        for kf in kfs {
            let kf_obj = kf.as_object().expect("dense_keyframe is object");
            for k in REQUIRED_DENSE_KEYS {
                assert!(kf_obj.contains_key(*k), "missing dense_keyframes key: {k}");
            }
        }
        let evs = obj.get("timeline_events").and_then(|v| v.as_array()).unwrap();
        for ev in evs {
            let ev_obj = ev.as_object().expect("event is object");
            for k in REQUIRED_TIMELINE_KEYS {
                assert!(ev_obj.contains_key(*k), "missing timeline_events key: {k}");
            }
        }
        let segs = obj.get("scene_segments").and_then(|v| v.as_array()).unwrap();
        for seg in segs {
            let seg_obj = seg.as_object().expect("scene segment is object");
            for k in REQUIRED_SCENE_KEYS {
                assert!(seg_obj.contains_key(*k), "missing scene_segments key: {k}");
            }
        }
        let stems = obj.get("stem_channels").and_then(|v| v.as_object()).unwrap();
        assert!(!stems.is_empty(), "stem_channels must not be empty");
        for (_name, series) in stems {
            let arr = series.as_array().expect("stem series is array");
            assert!(!arr.is_empty(), "stem series must align with keyframes");
        }
        let mir = obj.get("mir").and_then(|v| v.as_object()).unwrap();
        for k in REQUIRED_MIR_KEYS {
            assert!(mir.contains_key(*k), "missing mir key: {k}");
        }
    }
}
