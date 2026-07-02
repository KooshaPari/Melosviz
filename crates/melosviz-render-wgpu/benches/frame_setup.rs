use criterion::{black_box, criterion_group, criterion_main, Criterion, BenchmarkId};
use melosviz_render_wgpu::renderer::WgpuRenderer;

fn bench_wgpu_frame_setup(c: &mut Criterion) {
    let mut group = c.benchmark_group("wgpu_frame_setup");
    group.sample_size(10); // Smaller sample size since GPU init is slow

    for (label, (width, height)) in &[
        ("720p", (1280u32, 720u32)),
        ("1080p", (1920u32, 1080u32)),
        ("4k", (3840u32, 2160u32)),
    ] {
        group.bench_with_input(
            BenchmarkId::from_parameter(label),
            &(*width, *height),
            |b, &(w, h)| {
                b.iter(|| {
                    // Use pollster::block_on to run async code synchronously in the benchmark.
                    pollster::block_on(async {
                        match WgpuRenderer::new(black_box(w), black_box(h)).await {
                            Ok(_renderer) => {
                                // Renderer created successfully.
                                // The timing above covers device init + all 4 layer pipelines.
                            }
                            Err(e) => {
                                eprintln!("GPU not available (expected on headless CI): {}", e);
                                // Skip benchmark gracefully if no GPU.
                            }
                        }
                    })
                });
            },
        );
    }

    group.finish();
}

criterion_group!(benches, bench_wgpu_frame_setup);
criterion_main!(benches);
