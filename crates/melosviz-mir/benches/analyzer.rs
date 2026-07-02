use criterion::{black_box, criterion_group, criterion_main, Criterion, BenchmarkId};
use melosviz_mir::{analyze, wav::load_wav_mono, mir::MirParams};
use std::path::Path;
use tempfile::NamedTempFile;
use hound::WavWriter;

/// Generate a synthetic 180-second WAV file for benchmarking.
fn generate_test_wav(duration_sec: f32) -> NamedTempFile {
    let sample_rate = 44100;
    let num_samples = (sample_rate as f32 * duration_sec) as u32;
    let mut temp = NamedTempFile::new().expect("temp file");

    let spec = hound::WavSpec {
        channels: 1,
        sample_rate,
        bits_per_sample: 16,
        sample_format: hound::SampleFormat::Int,
    };

    let mut writer = WavWriter::new(temp.as_file_mut(), spec).expect("wav writer");

    for i in 0..num_samples {
        let t = i as f32 / sample_rate as f32;
        // Sine wave at 440 Hz
        let sample = (2.0 * std::f32::consts::PI * 440.0 * t).sin();
        let int_sample = (sample * 0.8 * 32767.0) as i16;
        writer.write_sample(int_sample).expect("write sample");
    }

    writer.finalize().expect("finalize");
    temp
}

fn analyzer_benchmark(c: &mut Criterion) {
    let mut group = c.benchmark_group("mir_analyzer");
    group.sample_size(10);

    // 180-second baseline (common case)
    group.bench_function(BenchmarkId::from_parameter("180s"), |b| {
        let temp = generate_test_wav(180.0);
        let path = temp.path();
        b.iter(|| {
            let wav = load_wav_mono(black_box(path)).expect("load wav");
            analyze(&wav, black_box(MirParams {
                n_dense_fps: 15,
                n_fft: 2048,
                hop_length: 512,
            }))
        });
    });

    // 60-second case (quick preview)
    group.bench_function(BenchmarkId::from_parameter("60s"), |b| {
        let temp = generate_test_wav(60.0);
        let path = temp.path();
        b.iter(|| {
            let wav = load_wav_mono(black_box(path)).expect("load wav");
            analyze(&wav, black_box(MirParams {
                n_dense_fps: 15,
                n_fft: 2048,
                hop_length: 512,
            }))
        });
    });

    group.finish();
}

criterion_group!(benches, analyzer_benchmark);
criterion_main!(benches);
