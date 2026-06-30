//! Core DSP primitives: STFT, RMS envelope, onset detection, beat tracking,
//! spectral centroid, and chroma (key/mode).
//!
//! All functions operate on a normalised f32 mono signal.

use num_complex::Complex32;
use rustfft::FftPlanner;
use std::f32::consts::PI;

// ---------------------------------------------------------------------------
// STFT
// ---------------------------------------------------------------------------

/// Short-time Fourier transform (magnitude spectrum per frame).
///
/// Returns `(magnitudes, n_fft_bins, hop_length)` where `magnitudes` is a
/// column-major matrix: `magnitudes[frame * n_fft_bins + bin]`.
///
/// Uses a Hann window of length `n_fft` with `hop_length` advance per frame.
pub fn stft(
    samples: &[f32],
    n_fft: usize,
    hop_length: usize,
) -> (Vec<f32>, usize, usize) {
    let n_bins = n_fft / 2 + 1; // one-sided spectrum
    let n_frames = if samples.len() >= n_fft {
        (samples.len() - n_fft) / hop_length + 1
    } else {
        0
    };

    let mut planner = FftPlanner::<f32>::new();
    let fft = planner.plan_fft_forward(n_fft);
    let window = hann_window(n_fft);

    let mut magnitudes = vec![0.0f32; n_frames * n_bins];
    let mut buf = vec![Complex32::new(0.0, 0.0); n_fft];

    for frame in 0..n_frames {
        let start = frame * hop_length;
        // Apply Hann window and copy into FFT buffer.
        for (i, b) in buf.iter_mut().enumerate() {
            let s = if start + i < samples.len() { samples[start + i] } else { 0.0 };
            *b = Complex32::new(s * window[i], 0.0);
        }
        fft.process(&mut buf);
        // Store one-sided magnitude.
        for bin in 0..n_bins {
            magnitudes[frame * n_bins + bin] = buf[bin].norm();
        }
    }

    (magnitudes, n_bins, hop_length)
}

fn hann_window(n: usize) -> Vec<f32> {
    (0..n).map(|i| 0.5 * (1.0 - (2.0 * PI * i as f32 / (n - 1) as f32).cos())).collect()
}

// ---------------------------------------------------------------------------
// RMS energy envelope
// ---------------------------------------------------------------------------

/// Compute normalised RMS energy per frame.
///
/// Returns one value per `n_frames` linearly spanning the full signal.
pub fn rms_envelope(samples: &[f32], n_frames: usize) -> Vec<f32> {
    if samples.is_empty() || n_frames == 0 {
        return vec![0.0; n_frames];
    }
    let frame_size = (samples.len() as f64 / n_frames as f64).ceil() as usize;
    let frame_size = frame_size.max(1);
    let mut env: Vec<f32> = (0..n_frames)
        .map(|i| {
            let start = i * frame_size;
            let end = ((i + 1) * frame_size).min(samples.len());
            if start >= end {
                return 0.0;
            }
            let chunk = &samples[start..end];
            let sq_sum: f32 = chunk.iter().map(|x| x * x).sum();
            (sq_sum / chunk.len() as f32).sqrt()
        })
        .collect();
    // Normalise to [0, 1].
    let peak = env.iter().cloned().fold(0.0f32, f32::max);
    if peak > 0.0 {
        env.iter_mut().for_each(|v| *v /= peak);
    }
    env
}

// ---------------------------------------------------------------------------
// Spectral centroid
// ---------------------------------------------------------------------------

/// Spectral centroid (Hz) per STFT frame, then resampled to `n_frames`.
///
/// Returns `(centroid_hz_per_frame, centroid_hz_resampled)`.
pub fn spectral_centroid(
    magnitudes: &[f32],
    n_bins: usize,
    n_stft_frames: usize,
    sample_rate: u32,
    _n_fft: usize,
    n_frames: usize,
) -> Vec<f32> {
    let nyquist = sample_rate as f32 / 2.0;
    let bin_hz = nyquist / (n_bins - 1).max(1) as f32;

    let centroid_raw: Vec<f32> = (0..n_stft_frames)
        .map(|frame| {
            let base = frame * n_bins;
            let mag_slice = &magnitudes[base..base + n_bins];
            let total: f32 = mag_slice.iter().sum();
            if total < 1e-10 {
                return 0.0;
            }
            mag_slice.iter().enumerate().map(|(b, &m)| b as f32 * bin_hz * m).sum::<f32>()
                / total
        })
        .collect();

    linear_resample(&centroid_raw, n_frames)
}

// ---------------------------------------------------------------------------
// Onset detection (spectral flux)
// ---------------------------------------------------------------------------

/// Onset strength envelope via half-wave-rectified spectral flux.
///
/// Returns one normalised value per STFT frame, then resampled to `n_frames`.
pub fn onset_strength(
    magnitudes: &[f32],
    n_bins: usize,
    n_stft_frames: usize,
    n_frames: usize,
) -> (Vec<f32>, Vec<f32>) {
    if n_stft_frames == 0 {
        return (vec![], vec![0.0; n_frames]);
    }

    // Spectral flux: positive differences in magnitude between consecutive frames.
    let mut flux_raw = vec![0.0f32; n_stft_frames];
    for frame in 1..n_stft_frames {
        let prev = &magnitudes[(frame - 1) * n_bins..frame * n_bins];
        let curr = &magnitudes[frame * n_bins..(frame + 1) * n_bins];
        let f: f32 = curr
            .iter()
            .zip(prev)
            .map(|(c, p)| (c - p).max(0.0))
            .sum();
        flux_raw[frame] = f;
    }

    // Normalise.
    let peak = flux_raw.iter().cloned().fold(0.0f32, f32::max);
    if peak > 0.0 {
        flux_raw.iter_mut().for_each(|v| *v /= peak);
    }

    let resampled = linear_resample(&flux_raw, n_frames);
    (flux_raw, resampled)
}

/// Pick onset times (seconds) from the flux envelope using adaptive thresholding.
///
/// `hop_length` is the STFT hop in samples; `sample_rate` is Hz.
pub fn onset_times_from_flux(
    flux: &[f32],
    hop_length: usize,
    sample_rate: u32,
    min_gap_sec: f32,
) -> Vec<f32> {
    if flux.is_empty() {
        return vec![];
    }
    let hop_sec = hop_length as f32 / sample_rate as f32;
    let min_gap_frames = ((min_gap_sec / hop_sec) as usize).max(1);

    // Adaptive local mean threshold over a 1-second window.
    let window_frames = (sample_rate as f32 / hop_length as f32).ceil() as usize;
    let window_frames = window_frames.max(4);

    let mut peaks = vec![];
    let mut last_peak = 0;
    for i in 1..flux.len().saturating_sub(1) {
        if i < last_peak + min_gap_frames {
            continue;
        }
        let w_start = i.saturating_sub(window_frames / 2);
        let w_end = (i + window_frames / 2).min(flux.len());
        let local_mean: f32 = flux[w_start..w_end].iter().sum::<f32>()
            / (w_end - w_start) as f32;
        let threshold = local_mean * 1.4 + 0.02;
        if flux[i] > threshold && flux[i] >= flux[i - 1] && flux[i] >= flux[i + 1] {
            peaks.push(i as f32 * hop_sec);
            last_peak = i;
        }
    }
    peaks
}

// ---------------------------------------------------------------------------
// Beat tracking (autocorrelation-based tempo estimation)
// ---------------------------------------------------------------------------

/// Beat tracking result.
pub struct BeatResult {
    /// Estimated global tempo in BPM.
    pub tempo_bpm: f32,
    /// Beat times in seconds.
    pub beat_times: Vec<f32>,
    /// Downbeat times (every 4th beat).
    pub downbeat_times: Vec<f32>,
    /// Per-beat tempo estimates (60 / inter-beat interval).
    pub tempo_curve: Vec<f32>,
}

/// Estimate beats and BPM from the onset-strength envelope via autocorrelation.
///
/// `flux` is the per-STFT-frame onset flux, `hop_length` is STFT hop in
/// samples, `sample_rate` is Hz.
pub fn estimate_beats(
    flux: &[f32],
    hop_length: usize,
    sample_rate: u32,
) -> BeatResult {
    let hop_sec = hop_length as f32 / sample_rate as f32;
    let n = flux.len();
    if n < 4 {
        return BeatResult {
            tempo_bpm: 120.0,
            beat_times: vec![],
            downbeat_times: vec![],
            tempo_curve: vec![120.0],
        };
    }

    // Autocorrelation over a BPM-useful lag range [40, 240] BPM.
    let min_lag = (60.0 / 240.0 / hop_sec) as usize;
    let max_lag = ((60.0 / 40.0 / hop_sec) as usize).min(n / 2);
    let min_lag = min_lag.max(1);

    let mut best_lag = min_lag;
    let mut best_ac = 0.0f32;
    for lag in min_lag..=max_lag {
        let ac: f32 = flux.iter().take(n - lag).zip(flux.iter().skip(lag)).map(|(a, b)| a * b).sum();
        if ac > best_ac {
            best_ac = ac;
            best_lag = lag;
        }
    }

    let tempo_bpm = 60.0 / (best_lag as f32 * hop_sec);
    // Clamp to a musically reasonable range.
    let tempo_bpm = tempo_bpm.clamp(40.0, 240.0);
    let refined_lag = (60.0 / tempo_bpm / hop_sec) as usize;
    let refined_lag = refined_lag.max(1);

    // Pick beats by tracking the tempo grid forward from the strongest onset.
    let start_frame = flux
        .iter()
        .enumerate()
        .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap())
        .map(|(i, _)| i)
        .unwrap_or(0);

    let mut beat_times: Vec<f32> = vec![];
    // Walk forward from start.
    let mut pos = start_frame;
    while pos < n {
        beat_times.push(pos as f32 * hop_sec);
        pos += refined_lag;
    }
    // Walk backward from start.
    let mut pos = start_frame as isize - refined_lag as isize;
    while pos >= 0 {
        beat_times.push(pos as f32 * hop_sec);
        pos -= refined_lag as isize;
    }
    beat_times.sort_by(|a, b| a.partial_cmp(b).unwrap());

    let downbeat_times: Vec<f32> =
        beat_times.iter().step_by(4).cloned().collect();

    // Per-beat tempo from inter-beat intervals.
    let tempo_curve: Vec<f32> = if beat_times.len() > 1 {
        beat_times
            .windows(2)
            .map(|w| 60.0 / (w[1] - w[0]).max(1e-6))
            .collect()
    } else {
        vec![tempo_bpm]
    };

    BeatResult { tempo_bpm, beat_times, downbeat_times, tempo_curve }
}

// ---------------------------------------------------------------------------
// Beat-strength per dense frame
// ---------------------------------------------------------------------------

/// Map beat times to a per-dense-frame beat strength array.
pub fn beat_strength_array(
    beat_times: &[f32],
    n_frames: usize,
    duration_sec: f32,
) -> Vec<f32> {
    let mut arr = vec![0.0f32; n_frames];
    for &bt in beat_times {
        let fi = ((bt / duration_sec) * (n_frames - 1) as f32).round() as usize;
        if fi < n_frames {
            arr[fi] = 1.0;
        }
    }
    arr
}

// ---------------------------------------------------------------------------
// Chroma (key/mode estimation)
// ---------------------------------------------------------------------------

/// 12-bin chroma vector (C, C#, D, …, B) summed from the STFT magnitude.
///
/// Uses equal-tempered pitch mapping from bin frequency to chroma bin.
pub fn chroma_vector(
    magnitudes: &[f32],
    n_bins: usize,
    n_stft_frames: usize,
    sample_rate: u32,
    _n_fft: usize,
) -> [f32; 12] {
    let nyquist = sample_rate as f32 / 2.0;
    let bin_hz = nyquist / (n_bins - 1).max(1) as f32;
    // Reference: C4 = 261.63 Hz is pitch class 0 (C).
    // MIDI pitch class formula: pitch_class = round(12 * log2(f / C4)) mod 12
    let c4 = 261.63f32;
    let f_min = 20.0f32; // skip DC and sub-bass

    let mut chroma = [0.0f32; 12];
    for frame in 0..n_stft_frames {
        let base = frame * n_bins;
        for bin in 1..n_bins {
            let freq = bin as f32 * bin_hz;
            if freq < f_min {
                continue;
            }
            // Map frequency to chroma bin relative to C4.
            let semitones_from_c4 = 12.0 * (freq / c4).log2();
            let pitch_class = semitones_from_c4.round() as i32 % 12;
            let pitch_class = ((pitch_class % 12) + 12) as usize % 12;
            chroma[pitch_class] += magnitudes[base + bin];
        }
    }

    // Normalise.
    let total: f32 = chroma.iter().sum();
    if total > 0.0 {
        chroma.iter_mut().for_each(|v| *v /= total);
    }
    chroma
}

const NOTE_NAMES: [&str; 12] =
    ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

/// Krumhansl-Schmuckler major and minor key profiles (normalised).
///
/// Major profile: C major. Minor profile: C natural minor.
/// Reference: Krumhansl (1990) "Cognitive Foundations of Musical Pitch".
const KS_MAJOR: [f32; 12] = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                               2.52, 5.19, 2.39, 3.66, 2.29, 2.88];
const KS_MINOR: [f32; 12] = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                               2.54, 4.75, 3.98, 2.69, 3.34, 3.17];

/// Pearson correlation between two equal-length slices.
fn pearson(a: &[f32], b: &[f32]) -> f32 {
    let n = a.len() as f32;
    let a_mean = a.iter().sum::<f32>() / n;
    let b_mean = b.iter().sum::<f32>() / n;
    let num: f32 = a.iter().zip(b).map(|(x, y)| (x - a_mean) * (y - b_mean)).sum();
    let da: f32 = a.iter().map(|x| (x - a_mean).powi(2)).sum::<f32>().sqrt();
    let db: f32 = b.iter().map(|x| (x - b_mean).powi(2)).sum::<f32>().sqrt();
    if da < 1e-10 || db < 1e-10 { 0.0 } else { num / (da * db) }
}

/// Estimate musical key and mode (major/minor) via Krumhansl-Schmuckler profiles.
///
/// Matches the Python implementation: highest correlation across all 12 rotations
/// of both major and minor profiles.
pub fn estimate_key_mode(chroma: &[f32; 12]) -> (String, String) {
    let chroma_slice = chroma.as_slice();
    let mut best_corr = f32::NEG_INFINITY;
    let mut best_key = 0usize;
    let mut best_mode = "major";

    for root in 0..12usize {
        // Rotate the KS profile so it aligns with this root.
        let major_rot: Vec<f32> = (0..12).map(|i| KS_MAJOR[(i + 12 - root) % 12]).collect();
        let minor_rot: Vec<f32> = (0..12).map(|i| KS_MINOR[(i + 12 - root) % 12]).collect();
        let r_major = pearson(chroma_slice, &major_rot);
        let r_minor = pearson(chroma_slice, &minor_rot);
        if r_major > best_corr {
            best_corr = r_major;
            best_key = root;
            best_mode = "major";
        }
        if r_minor > best_corr {
            best_corr = r_minor;
            best_key = root;
            best_mode = "minor";
        }
    }
    (NOTE_NAMES[best_key].to_string(), best_mode.to_string())
}

// ---------------------------------------------------------------------------
// Spectral stem approximation (no Demucs)
// ---------------------------------------------------------------------------

/// Per-stem energy envelopes estimated from spectral bands.
///
/// Returns `(drums, bass, vocals, other)` as normalised f32 arrays of
/// length `n_frames`.
pub fn spectral_stems(
    magnitudes: &[f32],
    n_bins: usize,
    n_stft_frames: usize,
    sample_rate: u32,
    n_frames: usize,
) -> [Vec<f32>; 4] {
    let nyquist = sample_rate as f32 / 2.0;
    let bin_hz = nyquist / (n_bins - 1).max(1) as f32;

    // Frequency band definitions (approximate stem separation).
    // drums: transient energy → use onset flux proxy (handled separately)
    // bass: 20–300 Hz
    // vocals: 300–4000 Hz
    // other: 4000 Hz+
    let bin_for_hz = |hz: f32| -> usize { ((hz / bin_hz) as usize).min(n_bins - 1) };

    let bass_hi = bin_for_hz(300.0);
    let vocals_hi = bin_for_hz(4000.0);

    let mut bass_env = vec![0.0f32; n_stft_frames];
    let mut vocals_env = vec![0.0f32; n_stft_frames];
    let mut other_env = vec![0.0f32; n_stft_frames];
    let mut full_env = vec![0.0f32; n_stft_frames];

    for frame in 0..n_stft_frames {
        let base = frame * n_bins;
        let mut bass: f32 = 0.0;
        let mut vocals: f32 = 0.0;
        let mut other: f32 = 0.0;
        let mut total: f32 = 0.0;
        for bin in 1..n_bins {
            let m = magnitudes[base + bin];
            total += m;
            if bin <= bass_hi {
                bass += m;
            } else if bin <= vocals_hi {
                vocals += m;
            } else {
                other += m;
            }
        }
        bass_env[frame] = bass;
        vocals_env[frame] = vocals;
        other_env[frame] = other;
        full_env[frame] = total;
    }

    fn norm_resample(v: &[f32], n: usize) -> Vec<f32> {
        let peak = v.iter().cloned().fold(0.0f32, f32::max);
        let normed: Vec<f32> = if peak > 0.0 { v.iter().map(|x| x / peak).collect() } else { v.to_vec() };
        linear_resample(&normed, n)
    }

    // "drums" proxy: use the high-frequency spectral flux (percussive transients).
    // Build a quick onset-flux from the upper half of the spectrum.
    let hf_start = bin_for_hz(3000.0);
    let mut drums_raw = vec![0.0f32; n_stft_frames];
    for frame in 1..n_stft_frames {
        let prev = &magnitudes[(frame - 1) * n_bins..(frame - 1) * n_bins + n_bins];
        let curr = &magnitudes[frame * n_bins..frame * n_bins + n_bins];
        let flux: f32 = curr[hf_start..]
            .iter()
            .zip(prev[hf_start..].iter())
            .map(|(c, p)| (c - p).max(0.0))
            .sum();
        drums_raw[frame] = flux;
    }

    [
        norm_resample(&drums_raw, n_frames),
        norm_resample(&bass_env, n_frames),
        norm_resample(&vocals_env, n_frames),
        norm_resample(&other_env, n_frames),
    ]
}

// ---------------------------------------------------------------------------
// Utility: linear resampling
// ---------------------------------------------------------------------------

/// Linearly resample `src` to `target_len` points.
pub fn linear_resample(src: &[f32], target_len: usize) -> Vec<f32> {
    if src.is_empty() {
        return vec![0.0; target_len];
    }
    if src.len() == target_len {
        return src.to_vec();
    }
    let n = src.len() as f32 - 1.0;
    (0..target_len)
        .map(|i| {
            let t = if target_len > 1 { i as f32 * n / (target_len - 1) as f32 } else { 0.0 };
            let lo = t.floor() as usize;
            let hi = (lo + 1).min(src.len() - 1);
            let frac = t - lo as f32;
            src[lo] * (1.0 - frac) + src[hi] * frac
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f32::consts::PI;

    fn sine_samples(freq: f32, dur_sec: f32, sr: u32) -> Vec<f32> {
        let n = (dur_sec * sr as f32) as usize;
        (0..n).map(|i| (2.0 * PI * freq * i as f32 / sr as f32).sin()).collect()
    }

    #[test]
    fn spectral_centroid_440hz() {
        // A 440 Hz sine should produce a centroid ≈ 440 Hz.
        let sr = 44100u32;
        let samples = sine_samples(440.0, 0.5, sr);
        let n_fft = 2048;
        let hop = 512;
        let (mags, n_bins, _) = stft(&samples, n_fft, hop);
        let n_stft_frames = mags.len() / n_bins;
        let centroids = spectral_centroid(&mags, n_bins, n_stft_frames, sr, n_fft, 1);
        let avg = centroids[0];
        // Centroid should be close to 440 Hz (within 20%).
        assert!(
            (avg - 440.0).abs() < 100.0,
            "spectral centroid {:.1} Hz not near 440 Hz",
            avg
        );
    }

    #[test]
    fn rms_envelope_constant_signal() {
        // A constant-amplitude signal should produce a flat normalised envelope.
        let samples = vec![0.5f32; 44100];
        let env = rms_envelope(&samples, 30);
        assert_eq!(env.len(), 30);
        for v in &env {
            assert!((*v - 1.0).abs() < 0.01, "not flat: {}", v);
        }
    }

    #[test]
    fn rms_envelope_silence() {
        let samples = vec![0.0f32; 44100];
        let env = rms_envelope(&samples, 30);
        for v in &env {
            assert_eq!(*v, 0.0);
        }
    }

    #[test]
    fn beat_tracking_click_120bpm() {
        // Generate a click track at 120 BPM (one click per 0.5 s) for 10 s.
        let sr = 44100u32;
        let bpm = 120.0f32;
        let period_samples = (sr as f32 * 60.0 / bpm) as usize;
        let dur_samples = sr as usize * 10;
        let mut samples = vec![0.0f32; dur_samples];
        let mut pos = 0;
        while pos < dur_samples {
            samples[pos] = 1.0;
            pos += period_samples;
        }
        let n_fft = 2048;
        let hop = 512;
        let (mags, n_bins, _) = stft(&samples, n_fft, hop);
        let n_stft = mags.len() / n_bins;
        let (flux_raw, _) = onset_strength(&mags, n_bins, n_stft, n_stft);
        let beats = estimate_beats(&flux_raw, hop, sr);
        // Should be close to 120 BPM (allow ±20 for quantisation).
        assert!(
            (beats.tempo_bpm - 120.0).abs() < 25.0,
            "BPM {:.1} not near 120",
            beats.tempo_bpm
        );
        // Should detect at least 8 beats in 10 s.
        assert!(beats.beat_times.len() >= 8, "too few beats: {}", beats.beat_times.len());
    }

    #[test]
    fn chroma_and_key_c_major() {
        // A C major chord (C4=261.6, E4=329.6, G4=392.0) should produce key=C major.
        let sr = 44100u32;
        let dur = 0.5f32;
        let n = (dur * sr as f32) as usize;
        let samples: Vec<f32> = (0..n)
            .map(|i| {
                let t = i as f32 / sr as f32;
                (2.0 * PI * 261.6 * t).sin()
                    + (2.0 * PI * 329.6 * t).sin()
                    + (2.0 * PI * 392.0 * t).sin()
            })
            .collect();
        let n_fft = 4096;
        let hop = 1024;
        let (mags, n_bins, _) = stft(&samples, n_fft, hop);
        let n_stft = mags.len() / n_bins;
        let chroma = chroma_vector(&mags, n_bins, n_stft, sr, n_fft);
        let (key, mode) = estimate_key_mode(&chroma);
        assert_eq!(key, "C", "expected key C, got {}", key);
        assert_eq!(mode, "major", "expected major, got {}", mode);
    }

    #[test]
    fn onset_detection_click_track() {
        // A click track should produce ~N onsets.
        let sr = 44100u32;
        let period = (sr as f32 * 0.5) as usize; // 120 BPM
        let dur = sr as usize * 5;
        let mut samples = vec![0.0f32; dur];
        let n_expected = dur / period;
        let mut pos = 0;
        while pos < dur {
            samples[pos] = 1.0;
            pos += period;
        }
        let n_fft = 2048;
        let hop = 512;
        let (mags, n_bins, _) = stft(&samples, n_fft, hop);
        let n_stft = mags.len() / n_bins;
        let (flux_raw, _) = onset_strength(&mags, n_bins, n_stft, n_stft);
        let onsets = onset_times_from_flux(&flux_raw, hop, sr, 0.3);
        // Should detect most of the expected ~10 onsets (allow ±3).
        assert!(
            (onsets.len() as isize - n_expected as isize).abs() <= 3,
            "expected ~{} onsets, got {}",
            n_expected,
            onsets.len()
        );
    }

    #[test]
    fn linear_resample_identity() {
        let v = vec![1.0, 2.0, 3.0];
        assert_eq!(linear_resample(&v, 3), v);
    }

    #[test]
    fn linear_resample_upsample() {
        let v = vec![0.0, 1.0];
        let r = linear_resample(&v, 5);
        assert_eq!(r.len(), 5);
        assert!((r[0] - 0.0).abs() < 1e-5);
        assert!((r[4] - 1.0).abs() < 1e-5);
    }
}
