//! Top-level MIR analysis — the Rust equivalent of `analyze_wav_rich`.
//!
//! Takes a decoded mono WAV and returns a fully-populated `RenderSpec v2`.

use crate::dsp::{
    beat_strength_array, chroma_vector, estimate_beats, estimate_key_mode, linear_resample,
    onset_strength, onset_times_from_flux, rms_envelope, spectral_centroid, spectral_stems, stft,
};
use crate::spec::{
    DenseKeyframe, MirSummary, MoodVector, RenderMetadata, RenderSpec, SceneSegment, StemFrame,
    TimelineEvent,
};
use crate::wav::WavMono;
use std::collections::HashMap;

/// MIR analysis parameters.
pub struct MirParams {
    /// Dense keyframe rate (frames per second). Clamped to [10, 30].
    pub n_dense_fps: u32,
    /// STFT window size in samples.
    pub n_fft: usize,
    /// STFT hop size in samples.
    pub hop_length: usize,
}

impl Default for MirParams {
    fn default() -> Self {
        Self {
            n_dense_fps: 15,
            n_fft: 2048,
            hop_length: 512,
        }
    }
}

/// Run the full MIR analysis pipeline on a decoded WAV.
///
/// Returns a `RenderSpec v2` matching the Python `analyze_wav_rich` output.
pub fn analyze(wav: &WavMono, params: MirParams) -> RenderSpec {
    let n_dense_fps = params.n_dense_fps.clamp(10, 30);
    let duration_sec = wav.duration_sec as f32;
    let n_dense_frames = ((duration_sec * n_dense_fps as f32) as usize).max(1);
    let n_fft = params.n_fft;
    let hop = params.hop_length;

    // --- 1. STFT -----------------------------------------------------------
    let (mags, n_bins, _) = stft(&wav.samples, n_fft, hop);
    let n_stft_frames = mags.len().checked_div(n_bins).unwrap_or(0);

    // --- 2. RMS energy envelope --------------------------------------------
    let energy_arr = rms_envelope(&wav.samples, n_dense_frames);
    // Per-second energy trajectory.
    let n_secs = (duration_sec.ceil() as usize).max(1);
    let energy_per_sec = rms_envelope(&wav.samples, n_secs);

    // --- 3. Spectral centroid ----------------------------------------------
    let sc_hz = if n_stft_frames > 0 {
        spectral_centroid(&mags, n_bins, n_stft_frames, wav.sample_rate, n_fft, n_dense_frames)
    } else {
        vec![0.0; n_dense_frames]
    };
    let sc_max = sc_hz.iter().cloned().fold(0.0f32, f32::max).max(1.0);
    let brightness_arr: Vec<f32> = sc_hz.iter().map(|v| v / sc_max).collect();
    let brightness_per_sec: Vec<f32> = linear_resample(&brightness_arr, n_secs);

    // --- 4. Onset detection ------------------------------------------------
    let (flux_raw, onset_arr) = if n_stft_frames > 0 {
        onset_strength(&mags, n_bins, n_stft_frames, n_dense_frames)
    } else {
        (vec![], vec![0.0; n_dense_frames])
    };
    let onset_times = if !flux_raw.is_empty() {
        onset_times_from_flux(&flux_raw, hop, wav.sample_rate, 0.1)
    } else {
        vec![]
    };

    // --- 5. Beat tracking --------------------------------------------------
    let beats = if !flux_raw.is_empty() {
        estimate_beats(&flux_raw, hop, wav.sample_rate)
    } else {
        crate::dsp::BeatResult {
            tempo_bpm: 120.0,
            beat_times: vec![],
            downbeat_times: vec![],
            tempo_curve: vec![120.0],
        }
    };
    let beat_arr =
        beat_strength_array(&beats.beat_times, n_dense_frames, duration_sec.max(0.001));

    // --- 6. Chroma / key / mode --------------------------------------------
    let (key, mode) = if n_stft_frames > 0 {
        let chroma = chroma_vector(&mags, n_bins, n_stft_frames, wav.sample_rate, n_fft);
        estimate_key_mode(&chroma)
    } else {
        ("C".to_string(), "major".to_string())
    };

    // --- 7. Spectral stem approximation ------------------------------------
    let [drums, bass, vocals, other] = if n_stft_frames > 0 {
        spectral_stems(&mags, n_bins, n_stft_frames, wav.sample_rate, n_dense_frames)
    } else {
        [
            vec![0.0; n_dense_frames],
            vec![0.0; n_dense_frames],
            vec![0.0; n_dense_frames],
            vec![0.0; n_dense_frames],
        ]
    };

    // --- 8. Valence / arousal (heuristic) ----------------------------------
    // Valence proxy: spectral brightness (brighter → higher valence).
    let valence_arr = brightness_arr.clone();
    let arousal_arr = energy_arr.clone();
    let valence_per_sec = brightness_per_sec.clone();
    let arousal_per_sec = energy_per_sec.clone();

    // --- 9. Dense keyframes -----------------------------------------------
    let dense_keyframes: Vec<DenseKeyframe> = (0..n_dense_frames)
        .map(|i| {
            let t = if n_dense_frames > 1 {
                i as f32 * duration_sec / (n_dense_frames - 1) as f32
            } else {
                0.0
            };
            let energy = energy_arr[i];
            let prev_energy = if i > 0 { energy_arr[i - 1] } else { 0.0 };
            let delta = energy - prev_energy;
            let easing = if delta > 0.15 {
                "ease_in"
            } else if delta < -0.15 {
                "ease_out"
            } else {
                "ease_in_out"
            };
            DenseKeyframe {
                t: round4(t),
                energy: round4(energy),
                brightness: round4(brightness_arr[i]),
                valence: round4(valence_arr[i]),
                arousal: round4(arousal_arr[i]),
                beat_strength: round4(beat_arr[i]),
                onset_strength: round4(onset_arr[i]),
                spectral_centroid: round2(sc_hz[i]),
                stems: StemFrame {
                    drums: round4(drums[i]),
                    bass: round4(bass[i]),
                    vocals: round4(vocals[i]),
                    other: round4(other[i]),
                },
                easing: easing.to_string(),
            }
        })
        .collect();

    // --- 10. Timeline events ----------------------------------------------
    let mut timeline_events: Vec<TimelineEvent> = vec![];
    for &bt in &beats.beat_times {
        timeline_events.push(TimelineEvent {
            t: round4(bt),
            event_type: "beat".into(),
            strength: 1.0,
            bar: None,
            label: None,
            segment_index: None,
        });
    }
    for (bar_i, &db) in beats.downbeat_times.iter().enumerate() {
        timeline_events.push(TimelineEvent {
            t: round4(db),
            event_type: "downbeat".into(),
            strength: 1.0,
            bar: Some(bar_i as u32 + 1),
            label: None,
            segment_index: None,
        });
    }
    for &ot in &onset_times {
        timeline_events.push(TimelineEvent {
            t: round4(ot),
            event_type: "onset".into(),
            strength: 0.7,
            bar: None,
            label: None,
            segment_index: None,
        });
    }
    timeline_events.sort_by(|a, b| a.t.partial_cmp(&b.t).unwrap());

    // --- 11. Scene segments -----------------------------------------------
    let n_segments = (4.max((duration_sec / 30.0) as usize)).min(8);
    let step = duration_sec / n_segments as f32;
    let scene_segments: Vec<SceneSegment> = (0..n_segments)
        .map(|idx| {
            let start = idx as f32 * step;
            let end = ((idx + 1) as f32 * step).min(duration_sec);
            let em = mean_in_range(&energy_per_sec, start, end, duration_sec);
            let bm = mean_in_range(&brightness_per_sec, start, end, duration_sec);
            let vm = mean_in_range(&valence_per_sec, start, end, duration_sec);
            let am = mean_in_range(&arousal_per_sec, start, end, duration_sec);
            let label = classify_label(idx, n_segments, em, bm);
            // Dominant stem by average energy in this segment's frame range.
            let fi_start = ((start / duration_sec) * n_dense_frames as f32) as usize;
            let fi_end = (((end / duration_sec) * n_dense_frames as f32) as usize)
                .min(n_dense_frames)
                .max(fi_start + 1);
            let stem_means = [
                mean_slice(&drums, fi_start, fi_end),
                mean_slice(&bass, fi_start, fi_end),
                mean_slice(&vocals, fi_start, fi_end),
                mean_slice(&other, fi_start, fi_end),
            ];
            let stem_names = ["drums", "bass", "vocals", "other"];
            let dom = stem_means
                .iter()
                .enumerate()
                .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap())
                .map(|(i, _)| stem_names[i])
                .unwrap_or("other");

            let seg = SceneSegment {
                index: idx,
                label: label.clone(),
                start: round3(start),
                end: round3(end),
                energy_mean: round4(em),
                brightness_mean: round4(bm),
                mood: MoodVector { valence: round4(vm), arousal: round4(am) },
                dominant_stem: dom.to_string(),
            };
            // Emit section timeline event.
            (seg, TimelineEvent {
                t: round4(start),
                event_type: "section".into(),
                strength: 1.0,
                bar: None,
                label: Some(label),
                segment_index: Some(idx),
            })
        })
        .map(|(seg, ev)| {
            timeline_events.push(ev);
            seg
        })
        .collect();
    timeline_events.sort_by(|a, b| a.t.partial_cmp(&b.t).unwrap());

    // --- 12. Stem channels (aligned with dense_keyframes) -----------------
    let mut stem_channels: HashMap<String, Vec<f32>> = HashMap::new();
    stem_channels.insert("drums".into(), drums.iter().map(|v| round4(*v)).collect());
    stem_channels.insert("bass".into(), bass.iter().map(|v| round4(*v)).collect());
    stem_channels.insert("vocals".into(), vocals.iter().map(|v| round4(*v)).collect());
    stem_channels.insert("other".into(), other.iter().map(|v| round4(*v)).collect());

    // --- 13. Danceability heuristic ---------------------------------------
    let beat_regularity = if beats.beat_times.len() > 2 {
        let ibis: Vec<f32> =
            beats.beat_times.windows(2).map(|w| w[1] - w[0]).collect();
        let mean_ibi = ibis.iter().sum::<f32>() / ibis.len() as f32;
        let variance =
            ibis.iter().map(|x| (x - mean_ibi).powi(2)).sum::<f32>() / ibis.len() as f32;
        let std = variance.sqrt();
        (1.0 - std / mean_ibi.max(1e-6)).max(0.0)
    } else {
        1.0
    };
    let mean_energy = energy_per_sec.iter().sum::<f32>() / energy_per_sec.len().max(1) as f32;
    let danceability = (0.5 * mean_energy + 0.5 * beat_regularity).min(1.0);

    // --- 14. Amplitude envelope (120-bucket legacy) -----------------------
    let amplitude_envelope = rms_envelope(&wav.samples, 120);
    let peak_rms = wav.samples.iter().map(|x| x.abs()).fold(0.0f32, f32::max);

    // --- 15. MIR summary --------------------------------------------------
    let mir = MirSummary {
        tempo_bpm: Some(round2(beats.tempo_bpm)),
        tempo_curve: beats.tempo_curve.iter().map(|v| round2(*v)).collect(),
        danceability: Some(round4(danceability)),
        energy_trajectory: energy_per_sec.iter().map(|v| round4(*v)).collect(),
        brightness_trajectory: brightness_per_sec.iter().map(|v| round4(*v)).collect(),
        valence_trajectory: valence_per_sec.iter().map(|v| round4(*v)).collect(),
        arousal_trajectory: arousal_per_sec.iter().map(|v| round4(*v)).collect(),
        key: Some(key),
        mode: Some(mode),
        chord_sequence: vec![],
    };

    RenderSpec {
        metadata: RenderMetadata {
            source_audio: String::new(), // filled in by caller
            sample_rate: wav.sample_rate,
            channels: wav.channels,
            duration: wav.duration_sec,
            fps: 30,
            width: 1280,
            height: 720,
            analysis_peak_rms: round4(peak_rms),
            estimated_bpm: Some(round2(beats.tempo_bpm)),
            amplitude_envelope,
            render_spec_version: 2,
            n_dense_frames,
            n_dense_fps,
        },
        palette: vec![],
        layers: vec![],
        keyframes: vec![],
        timeline: vec![],
        dense_keyframes,
        timeline_events,
        scene_segments,
        stem_channels,
        mir,
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn round4(v: f32) -> f32 {
    (v * 10000.0).round() / 10000.0
}

fn round3(v: f32) -> f32 {
    (v * 1000.0).round() / 1000.0
}

fn round2(v: f32) -> f32 {
    (v * 100.0).round() / 100.0
}

fn mean_slice(arr: &[f32], start: usize, end: usize) -> f32 {
    let end = end.min(arr.len());
    if start >= end {
        return 0.0;
    }
    arr[start..end].iter().sum::<f32>() / (end - start) as f32
}

fn mean_in_range(arr: &[f32], start_sec: f32, end_sec: f32, total_sec: f32) -> f32 {
    if arr.is_empty() || total_sec <= 0.0 {
        return 0.0;
    }
    let n = arr.len();
    let i0 = ((start_sec / total_sec) * n as f32) as usize;
    let i1 = ((end_sec / total_sec) * n as f32) as usize;
    let i1 = i1.max(i0 + 1).min(n);
    mean_slice(arr, i0, i1)
}

fn classify_label(idx: usize, n: usize, energy: f32, brightness: f32) -> String {
    if idx == 0 {
        return "intro".into();
    }
    if idx == n - 1 {
        return "outro".into();
    }
    if energy > 0.7 && brightness > 0.6 {
        return "drop".into();
    }
    if energy > 0.5 {
        return "chorus".into();
    }
    let frac = idx as f32 / (n - 1).max(1) as f32;
    if frac < 0.25 {
        "verse".into()
    } else if frac > 0.75 {
        "breakdown".into()
    } else {
        "verse".into()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::wav::WavMono;
    use std::f32::consts::PI;

    fn make_sine_wav(freq: f32, dur_sec: f32, sr: u32) -> WavMono {
        let n = (dur_sec * sr as f32) as usize;
        let samples: Vec<f32> =
            (0..n).map(|i| (2.0 * PI * freq * i as f32 / sr as f32).sin()).collect();
        WavMono { samples, sample_rate: sr, channels: 1, duration_sec: dur_sec as f64 }
    }

    #[test]
    fn analyze_returns_v2_spec() {
        let wav = make_sine_wav(440.0, 5.0, 44100);
        let spec = analyze(&wav, MirParams::default());
        // Dense keyframes: 5 s × 15 fps = 75 frames.
        assert_eq!(spec.dense_keyframes.len(), 75);
        assert_eq!(spec.metadata.render_spec_version, 2);
        assert!(spec.mir.tempo_bpm.is_some());
        assert!(spec.mir.key.is_some());
        assert_eq!(spec.stem_channels.len(), 4);
    }

    #[test]
    fn analyze_spectral_centroid_440hz() {
        let wav = make_sine_wav(440.0, 1.0, 44100);
        let spec = analyze(&wav, MirParams::default());
        // Average spectral_centroid should be near 440 Hz.
        let avg_sc: f32 = spec.dense_keyframes.iter().map(|kf| kf.spectral_centroid).sum::<f32>()
            / spec.dense_keyframes.len() as f32;
        assert!(
            (avg_sc - 440.0).abs() < 120.0,
            "centroid {:.1} Hz not near 440 Hz",
            avg_sc
        );
    }

    #[test]
    fn analyze_key_detection() {
        // C major chord.
        let sr = 44100u32;
        let n = sr as usize * 2;
        let samples: Vec<f32> = (0..n)
            .map(|i| {
                let t = i as f32 / sr as f32;
                (2.0 * PI * 261.6 * t).sin()
                    + (2.0 * PI * 329.6 * t).sin()
                    + (2.0 * PI * 392.0 * t).sin()
            })
            .collect();
        let wav = WavMono { samples, sample_rate: sr, channels: 1, duration_sec: 2.0 };
        let spec = analyze(&wav, MirParams::default());
        assert_eq!(spec.mir.key.as_deref(), Some("C"));
        assert_eq!(spec.mir.mode.as_deref(), Some("major"));
    }

    #[test]
    fn analyze_amplitude_envelope_120_buckets() {
        let wav = make_sine_wav(440.0, 3.0, 44100);
        let spec = analyze(&wav, MirParams::default());
        assert_eq!(spec.metadata.amplitude_envelope.len(), 120);
    }

    #[test]
    fn analyze_scene_segments_present() {
        // 180 s audio → 6 segments (180/30=6).
        let wav = make_sine_wav(440.0, 180.0, 44100);
        let spec = analyze(&wav, MirParams::default());
        assert!(!spec.scene_segments.is_empty());
        // First segment should be "intro".
        assert_eq!(spec.scene_segments[0].label, "intro");
        // Last segment should be "outro".
        let last = spec.scene_segments.last().unwrap();
        assert_eq!(last.label, "outro");
    }

    #[test]
    fn analyze_empty_signal() {
        let wav = WavMono {
            samples: vec![],
            sample_rate: 44100,
            channels: 1,
            duration_sec: 0.0,
        };
        let spec = analyze(&wav, MirParams::default());
        // Should not panic; spec should be valid
        assert_eq!(spec.metadata.duration, 0.0);
    }

    #[test]
    fn analyze_single_sample() {
        let wav = WavMono {
            samples: vec![0.5],
            sample_rate: 44100,
            channels: 1,
            duration_sec: 1.0 / 44100.0,
        };
        let spec = analyze(&wav, MirParams::default());
        // Should handle gracefully
        assert_eq!(spec.metadata.duration, 1.0 / 44100.0);
    }

    #[test]
    fn analyze_silence() {
        let n = 44100; // 1 second
        let wav = WavMono {
            samples: vec![0.0; n],
            sample_rate: 44100,
            channels: 1,
            duration_sec: 1.0,
        };
        let spec = analyze(&wav, MirParams::default());
        // All values should be finite, no NaN or panic
        for kf in &spec.dense_keyframes {
            assert!(kf.spectral_centroid.is_finite());
            assert!(kf.energy.is_finite());
            assert!(kf.onset_strength.is_finite());
        }
    }

    #[test]
    fn analyze_extreme_frequency_ultrasonic() {
        // 25 kHz ultrasonic (above Nyquist at 44.1 kHz)
        let wav = make_sine_wav(25000.0, 1.0, 44100);
        let spec = analyze(&wav, MirParams::default());
        // Should complete without panic
        assert_eq!(spec.metadata.sample_rate, 44100);
    }

    #[test]
    fn analyze_very_low_frequency() {
        // 0.5 Hz infrasound
        let wav = make_sine_wav(0.5, 5.0, 44100);
        let spec = analyze(&wav, MirParams::default());
        // Should not divide by zero or panic
        assert!(spec.mir.tempo_bpm.is_some());
    }

    #[test]
    fn analyze_high_amplitude_no_overflow() {
        let sr = 44100u32;
        let n = sr as usize;
        // Samples at full scale (would overflow if not careful)
        let samples: Vec<f32> = vec![1.0; n];
        let wav = WavMono { samples, sample_rate: sr, channels: 1, duration_sec: 1.0 };
        let spec = analyze(&wav, MirParams::default());
        // Should not overflow; all values should be finite
        for kf in &spec.dense_keyframes {
            assert!(kf.energy.is_finite(), "energy overflowed: {}", kf.energy);
            assert!(kf.spectral_centroid.is_finite());
        }
    }

    #[test]
    fn stft_zero_length_input() {
        let mags = crate::dsp::stft(&[], 2048, 512);
        assert_eq!(mags.1, 1025, "n_bins should be n_fft/2+1");
        assert_eq!(mags.0.len(), 0, "magnitude vector should be empty for empty input");
    }

    #[test]
    fn stft_single_frame() {
        let samples: Vec<f32> = vec![0.5; 2048];
        let (mags, n_bins, hop) = crate::dsp::stft(&samples, 2048, 512);
        assert_eq!(n_bins, 1025);
        assert_eq!(hop, 512);
        // Should produce 1 frame
        assert_eq!(mags.len(), 1025);
        // All magnitude values should be finite
        for &m in &mags {
            assert!(m.is_finite() && m >= 0.0, "invalid magnitude: {}", m);
        }
    }

    #[test]
    fn stft_non_power_of_two() {
        // 1234 samples with 1000-sample FFT (not power of 2)
        let samples: Vec<f32> = vec![0.1; 1234];
        let (mags, n_bins, _) = crate::dsp::stft(&samples, 1000, 250);
        // Should still work (rustfft handles non-power-of-2)
        assert!(n_bins > 0);
        assert!(mags.len() > 0);
    }

    #[test]
    fn rms_envelope_empty() {
        let env = crate::dsp::rms_envelope(&[], 10);
        assert_eq!(env.len(), 10);
        for &e in &env {
            assert_eq!(e, 0.0);
        }
    }

    #[test]
    fn rms_envelope_single_frame() {
        let samples = vec![0.5; 100];
        let env = crate::dsp::rms_envelope(&samples, 1);
        assert_eq!(env.len(), 1);
        assert!(env[0] > 0.0 && env[0] <= 1.0);
    }

    #[test]
    fn spectral_centroid_silence() {
        let mags = vec![0.0; 1000];
        let centroid = crate::dsp::spectral_centroid(&mags, 500, 2, 44100, 1000, 10);
        // Should not panic, return valid values
        assert_eq!(centroid.len(), 10);
        for &c in &centroid {
            assert!(c.is_finite());
        }
    }

    #[test]
    fn mir_params_fpsbound_clamping() {
        // Test that n_dense_fps is clamped [10, 30]
        let params = MirParams {
            n_dense_fps: 5, // Too low
            n_fft: 2048,
            hop_length: 512,
        };
        let wav = make_sine_wav(440.0, 1.0, 44100);
        let spec = analyze(&wav, params);
        // FPS is clamped, so dense_keyframes should respect bounds
        assert!(spec.metadata.n_dense_fps >= 10 && spec.metadata.n_dense_fps <= 30);
    }

    #[test]
    fn analyze_no_nans_or_infs() {
        let wav = make_sine_wav(440.0, 2.0, 44100);
        let spec = analyze(&wav, MirParams::default());
        // All numeric fields should be finite
        for kf in &spec.dense_keyframes {
            assert!(
                kf.energy.is_finite()
                    && kf.spectral_centroid.is_finite()
                    && kf.onset_strength.is_finite(),
                "keyframe contains NaN/Inf"
            );
        }
        // Metadata
        assert!(spec.metadata.analysis_peak_rms.is_finite());
        for env_val in &spec.metadata.amplitude_envelope {
            assert!(env_val.is_finite());
        }
    }
}
