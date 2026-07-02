use criterion::{black_box, criterion_group, criterion_main, Criterion};
use pollster::block_on;
use wgpu::Instance;

fn benchmark_wgpu_device_setup(c: &mut Criterion) {
	c.bench_function("wgpu_instance_creation", |b| {
		b.iter(|| {
			let _instance = black_box(Instance::new(&wgpu::InstanceDescriptor {
				backends: wgpu::Backends::PRIMARY,
				..Default::default()
			}));
		});
	});

	c.bench_function("wgpu_adapter_request", |b| {
		b.iter(|| {
			let instance = black_box(Instance::new(&wgpu::InstanceDescriptor {
				backends: wgpu::Backends::PRIMARY,
				..Default::default()
			}));

			block_on(async {
				let _adapter = instance.request_adapter(&wgpu::RequestAdapterOptions {
					power_preference: wgpu::PowerPreference::HighPerformance,
					compatible_surface: None,
					force_fallback_adapter: false,
				});
			});
		});
	});

	c.bench_function("wgpu_device_queue_setup", |b| {
		b.iter(|| {
			let instance = black_box(Instance::new(&wgpu::InstanceDescriptor {
				backends: wgpu::Backends::PRIMARY,
				..Default::default()
			}));

			block_on(async {
				if let Some(adapter) = instance.request_adapter(&wgpu::RequestAdapterOptions {
					power_preference: wgpu::PowerPreference::HighPerformance,
					compatible_surface: None,
					force_fallback_adapter: false,
				}).await {
					let _ = adapter
						.request_device(&wgpu::DeviceDescriptor {
							label: None,
							required_features: wgpu::Features::empty(),
							required_limits: wgpu::Limits::downlevel_defaults(),
							memory_hints: wgpu::MemoryHints::default(),
						}, None)
						.await;
				}
			});
		});
	});
}

criterion_group!(benches, benchmark_wgpu_device_setup);
criterion_main!(benches);
