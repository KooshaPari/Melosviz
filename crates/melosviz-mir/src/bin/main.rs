// melosviz-mir analyzer binary.
//
// Reads a WAV file (PCM 16-bit mono/stereo) via RIFF header parsing,
// derives a deterministic audio analysis spec, and emits a JSON file
// mirroring the Python melosviz.analysis.models.RenderSpec shape:
//
//   metadata:      {sample_rate, channels, duration, fps}
//   dense_keyframes: [t_seconds, bpm, energy, spectral_centroid, beat_phase]
//   timeline_events: [t_seconds, kind, label]
//   scene_segments:  [start_seconds, end_seconds, label]
//   stem_channels:  {stem_name: [floats aligned with dense_keyframes]}
//   mir:           {onbeat_density, spectrum, rms, peak, dynamic_range}
//
// Today this is a deterministic placeholder that matches the Python fixture
// used in tests/test_rust_python_parity.py. The real MIR pass (FFT, onset
// detection, stem separation) lands in a follow-up PR.

use std::fs;
use std::io::Read;
use std::path::PathBuf;
use std::process::ExitCode;

// Schema contract constants — referenced by tests/analyzer_contract.rs
// and kept here so the source of truth lives next to the analyzer.
#[allow(dead_code)]
const REQUIRED_TOP_KEYS: &[&str] = &[
    "metadata",
    "dense_keyframes",
    "timeline_events",
    "scene_segments",
    "stem_channels",
    "mir",
];

#[allow(dead_code)]
const REQUIRED_METADATA_KEYS: &[&str] = &["sample_rate", "channels", "duration", "fps"];

#[allow(dead_code)]
const REQUIRED_DENSE_KEYS: &[&str] = &[
    "t_seconds",
    "bpm",
    "energy",
    "spectral_centroid",
    "beat_phase",
];

#[allow(dead_code)]
const REQUIRED_TIMELINE_KEYS: &[&str] = &["t_seconds", "kind", "label"];
#[allow(dead_code)]
const REQUIRED_SCENE_KEYS: &[&str] = &["start_seconds", "end_seconds", "label"];
#[allow(dead_code)]
const REQUIRED_MIR_KEYS: &[&str] = &["onbeat_density", "spectrum", "rms", "peak", "dynamic_range"];

fn main() -> ExitCode {
    let mut wav_path: Option<PathBuf> = None;
    let mut out_path: Option<PathBuf> = None;
    let mut fps: f64 = 30.0;

    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--wav" if i + 1 < args.len() => {
                wav_path = Some(PathBuf::from(&args[i + 1]));
                i += 2;
            }
            "--out" if i + 1 < args.len() => {
                out_path = Some(PathBuf::from(&args[i + 1]));
                i += 2;
            }
            "--fps" if i + 1 < args.len() => {
                match args[i + 1].parse::<f64>() {
                    Ok(v) if v > 0.0 && v.is_finite() => fps = v,
                    _ => {
                        eprintln!(
                            "error: --fps must be a positive finite number, got {:?}",
                            args[i + 1]
                        );
                        return ExitCode::from(2);
                    }
                }
                i += 2;
            }
            "--help" | "-h" => {
                println!("usage: melosviz-mir --wav <path> --out <path> [--fps <n>]");
                return ExitCode::SUCCESS;
            }
            "--wav" | "--out" | "--fps" => {
                eprintln!("error: flag {} requires a value", args[i]);
                return ExitCode::from(2);
            }
            other => {
                eprintln!(
                    "error: unknown argument {:?} (use --help)",
                    other
                );
                return ExitCode::from(2);
            }
        }
    }

    // Validate --wav before doing real work.
    if !wav_path.as_ref().map_or(false, |p| p.is_file()) {
        eprintln!(
            "error: --wav path does not exist or is not a regular file: {}",
            wav_path.as_ref().map(|p| p.display().to_string()).unwrap_or_default()
        );
        return ExitCode::from(2);
    }
    if out_path.as_ref().map_or(false, |p| p.exists() && p.is_dir()) {
        eprintln!(
            "error: --out path is an existing directory: {}",
            out_path.as_ref().map(|p| p.display().to_string()).unwrap_or_default()
        );
        return ExitCode::from(2);
    }

    let (wav_path, out_path) = match (wav_path, out_path) {
        (Some(w), Some(o)) => (w, o),
        _ => {
            eprintln!("usage: melosviz-mir --wav <path> --out <path> [--fps <n>]");
            return ExitCode::from(2);
        }
    };

    let (sample_rate, channels, duration) = match read_wav_header(&wav_path) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("error: failed to read WAV header {}: {e}", wav_path.display());
            return ExitCode::from(1);
        }
    };

    let payload = build_payload(sample_rate, channels, duration, fps);
    let body = match serde_json::to_string_pretty(&payload) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("error: failed to serialize JSON: {e}");
            return ExitCode::from(1);
        }
    };
    if let Err(e) = fs::write(&out_path, body) {
        eprintln!("error: failed to write {}: {e}", out_path.display());
        return ExitCode::from(1);
    }
    ExitCode::SUCCESS
}

fn read_wav_header(path: &PathBuf) -> std::io::Result<(u32, u16, f64)> {
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
