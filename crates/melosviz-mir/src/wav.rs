//! WAV decoding helpers using `hound`.
//!
//! Decodes any 16- or 32-bit integer / 32-bit float WAV to a normalised
//! `Vec<f32>` mono signal.  Stereo signals are mixed down by averaging
//! left and right channels.

use anyhow::{bail, Context, Result};
use hound::{SampleFormat, WavReader};
use std::path::Path;

/// Decoded WAV file ready for MIR analysis.
pub struct WavMono {
    /// Normalised mono samples in [-1.0, 1.0].
    pub samples: Vec<f32>,
    /// Sample rate in Hz (e.g. 44100).
    pub sample_rate: u32,
    /// Number of channels in the original file.
    pub channels: u16,
    /// Duration in seconds.
    pub duration_sec: f64,
}

/// Load a WAV file from `path`, mix to mono, normalise to [-1, 1].
pub fn load_wav_mono(path: &Path) -> Result<WavMono> {
    let mut reader =
        WavReader::open(path).with_context(|| format!("opening WAV: {}", path.display()))?;
    let spec = reader.spec();
    let channels = spec.channels;
    if channels == 0 {
        bail!("WAV has 0 channels");
    }

    // Decode every sample to f32 in [-1, 1].
    let raw: Vec<f32> = match (spec.sample_format, spec.bits_per_sample) {
        (SampleFormat::Float, 32) => reader
            .samples::<f32>()
            .collect::<hound::Result<Vec<_>>>()
            .context("decoding f32 samples")?,
        (SampleFormat::Int, 16) => {
            let scale = 1.0f32 / i16::MAX as f32;
            reader
                .samples::<i16>()
                .map(|r| r.map(|s| s as f32 * scale))
                .collect::<hound::Result<Vec<_>>>()
                .context("decoding i16 samples")?
        }
        (SampleFormat::Int, 24) => {
            // hound provides i32 for 24-bit; scale by 2^23.
            let scale = 1.0f32 / (1 << 23) as f32;
            reader
                .samples::<i32>()
                .map(|r| r.map(|s| s as f32 * scale))
                .collect::<hound::Result<Vec<_>>>()
                .context("decoding i24 samples")?
        }
        (SampleFormat::Int, 32) => {
            let scale = 1.0f32 / i32::MAX as f32;
            reader
                .samples::<i32>()
                .map(|r| r.map(|s| s as f32 * scale))
                .collect::<hound::Result<Vec<_>>>()
                .context("decoding i32 samples")?
        }
        (fmt, bps) => bail!("unsupported WAV format: {:?} {}-bit", fmt, bps),
    };

    // Mix down to mono by averaging channels.
    let n_frames = raw.len() / channels as usize;
    let mut mono = Vec::with_capacity(n_frames);
    for frame in raw.chunks(channels as usize) {
        let sum: f32 = frame.iter().sum();
        mono.push(sum / channels as f32);
    }

    let duration_sec = n_frames as f64 / spec.sample_rate as f64;
    Ok(WavMono { samples: mono, sample_rate: spec.sample_rate, channels, duration_sec })
}

#[cfg(test)]
mod tests {
    use super::*;
    use hound::{SampleFormat, WavSpec, WavWriter};
    use tempfile::NamedTempFile;

    /// Generate a 440 Hz sine wave WAV at 44100 Hz, 16-bit, mono for `dur_sec` seconds.
    pub fn write_sine_wav(path: &Path, freq_hz: f32, dur_sec: f32, sample_rate: u32) {
        let spec = WavSpec {
            channels: 1,
            sample_rate,
            bits_per_sample: 16,
            sample_format: SampleFormat::Int,
        };
        let mut writer = WavWriter::create(path, spec).unwrap();
        let n = (dur_sec * sample_rate as f32) as usize;
        for i in 0..n {
            let t = i as f32 / sample_rate as f32;
            let s = (2.0 * std::f32::consts::PI * freq_hz * t).sin();
            writer.write_sample((s * i16::MAX as f32) as i16).unwrap();
        }
        writer.finalize().unwrap();
    }

    #[test]
    fn load_mono_sine() {
        let tmp = NamedTempFile::with_suffix(".wav").unwrap();
        write_sine_wav(tmp.path(), 440.0, 1.0, 44100);
        let wav = load_wav_mono(tmp.path()).unwrap();
        assert_eq!(wav.sample_rate, 44100);
        assert_eq!(wav.channels, 1);
        assert!((wav.duration_sec - 1.0).abs() < 0.01);
        // All samples should be in [-1, 1]
        for &s in &wav.samples {
            assert!(s >= -1.0 && s <= 1.0, "out of range: {}", s);
        }
    }

    #[test]
    fn load_stereo_mixdown() {
        let tmp = NamedTempFile::with_suffix(".wav").unwrap();
        // Write stereo 440 Hz; left = sine, right = -sine → mono should be ~0
        let spec = WavSpec {
            channels: 2,
            sample_rate: 44100,
            bits_per_sample: 16,
            sample_format: SampleFormat::Int,
        };
        let mut writer = WavWriter::create(tmp.path(), spec).unwrap();
        for i in 0..4410usize {
            let t = i as f32 / 44100.0;
            let s = (2.0 * std::f32::consts::PI * 440.0 * t).sin();
            writer.write_sample((s * i16::MAX as f32) as i16).unwrap(); // L
            writer.write_sample((-s * i16::MAX as f32) as i16).unwrap(); // R
        }
        writer.finalize().unwrap();
        let wav = load_wav_mono(tmp.path()).unwrap();
        assert_eq!(wav.channels, 2);
        // Mixed mono should be close to 0 (L+R cancel)
        let rms: f32 =
            (wav.samples.iter().map(|x| x * x).sum::<f32>() / wav.samples.len() as f32).sqrt();
        assert!(rms < 0.001, "stereo mixdown RMS too high: {}", rms);
    }
}
