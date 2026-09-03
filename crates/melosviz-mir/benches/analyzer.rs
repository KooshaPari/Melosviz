use criterion::{criterion_group, criterion_main, Criterion};
use melosviz_mir::analyze_wav;
use std::hint::black_box;

fn bench_analyze(c: &mut Criterion) {
    // 5-second 22050Hz mono silent WAV (mirrors the unit-test fixture).
    let mut wav_bytes = Vec::new();
    let sample_rate = 22050u32;
    let num_samples = (sample_rate as usize) * 5;
    // RIFF header
    wav_bytes.extend_from_slice(b"RIFF");
    let data_size = (num_samples * 2 + 36) as u32;
    wav_bytes.extend_from_slice(&data_size.to_le_bytes());
    wav_bytes.extend_from_slice(b"WAVE");
    // fmt chunk
    wav_bytes.extend_from_slice(b"fmt ");
    wav_bytes.extend_from_slice(&16u32.to_le_bytes());
    wav_bytes.extend_from_slice(&1u16.to_le_bytes()); // PCM
    wav_bytes.extend_from_slice(&1u16.to_le_bytes()); // mono
    wav_bytes.extend_from_slice(&sample_rate.to_le_bytes());
    wav_bytes.extend_from_slice(&(sample_rate * 2).to_le_bytes()); // byte rate
    wav_bytes.extend_from_slice(&2u16.to_le_bytes()); // block align
    wav_bytes.extend_from_slice(&16u16.to_le_bytes()); // bits per sample
    // data chunk
    wav_bytes.extend_from_slice(b"data");
    wav_bytes.extend_from_slice(&(num_samples * 2).to_le_bytes());
    for _ in 0..num_samples {
        wav_bytes.extend_from_slice(&0i16.to_le_bytes());
    }

    c.bench_function("analyze_5s_mono_22k", |b| {
        b.iter(|| {
            let spec = analyze_wav(black_box(&wav_bytes), 30).expect("analyze");
            black_box(spec);
        })
    });
}

criterion_group!(benches, bench_analyze);
criterion_main!(benches);
