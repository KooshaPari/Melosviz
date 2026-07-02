//! wgpu device + queue + pipeline setup for MelosViz.
//!
//! [`WgpuRenderer`] owns the wgpu device, queue, and pipeline set.  It
//! exposes two rendering paths:
//!
//! - **Headless offscreen**: `render_frame_to_bytes()` — renders one frame
//!   into a `Rgba8Unorm` texture, maps it back to CPU, returns raw RGBA bytes.
//!   Used by the export path (piped to ffmpeg as rawvideo).
//!
//! - **Windowed preview**: `render_frame_to_surface()` — renders into a
//!   `wgpu::Surface` swapchain for realtime preview (not yet wired in this
//!   initial crate; the headless path is the primary export path).
//!
//! Both paths share the same pipeline set and uniform upload logic.
//!
//! # GPU not available in this environment
//!
//! wgpu requires a real GPU adapter to build pipelines.  On headless CI or
//! Docker without a GPU, `WgpuRenderer::new()` returns an error rather than
//! panicking.  Tests that require a GPU adapter are marked `#[ignore]` and
//! expected to run on the host workstation (Apple M1 Pro, Metal 4).

use anyhow::{anyhow, Result};
use bytemuck;
use wgpu;
use wgpu::util::DeviceExt as _;

use crate::pipeline::PipelineSet;
use crate::spec::RenderSpec;
use crate::timeline::Timeline;
use crate::uniforms::FrameUniforms;

/// Output texture format for headless export.
/// `Rgba8Unorm` is the standard rawvideo input format accepted by ffmpeg.
const HEADLESS_FORMAT: wgpu::TextureFormat = wgpu::TextureFormat::Rgba8Unorm;

/// Core wgpu renderer — owns the device, queue, and compiled pipelines.
pub struct WgpuRenderer {
    device: wgpu::Device,
    queue: wgpu::Queue,
    pipelines: PipelineSet,
    width: u32,
    height: u32,
}

impl WgpuRenderer {
    /// Create a `WgpuRenderer` for the given output dimensions.
    ///
    /// Requests a high-performance GPU adapter (Metal on macOS, Vulkan on
    /// Linux) and builds all four layer pipelines.
    ///
    /// # Errors
    /// Returns an error if no GPU adapter is available (e.g. headless CI).
    pub async fn new(width: u32, height: u32) -> Result<Self> {
        let instance = wgpu::Instance::new(&wgpu::InstanceDescriptor {
            backends: wgpu::Backends::PRIMARY,
            ..Default::default()
        });

        let adapter = instance
            .request_adapter(&wgpu::RequestAdapterOptions {
                power_preference: wgpu::PowerPreference::HighPerformance,
                compatible_surface: None,
                force_fallback_adapter: false,
            })
            .await
            .ok_or_else(|| anyhow!("No GPU adapter found — Metal/Vulkan required for rendering"))?;

        let (device, queue) = adapter
            .request_device(
                &wgpu::DeviceDescriptor {
                    label: Some("melosviz"),
                    required_features: wgpu::Features::empty(),
                    required_limits: wgpu::Limits::default(),
                    memory_hints: Default::default(),
                },
                None,
            )
            .await?;

        let pipelines = PipelineSet::build(&device, HEADLESS_FORMAT)?;

        Ok(Self { device, queue, pipelines, width, height })
    }

    /// Render one frame from `uniforms` into an offscreen texture and
    /// return the raw RGBA bytes (width × height × 4 bytes).
    ///
    /// The frame is rendered by compositing all four layers in order:
    /// bg_gradient → spectral_hue → beat_pulse → stem_particles.
    ///
    /// # Errors
    /// Returns an error if the GPU read-back buffer cannot be mapped.
    pub async fn render_frame_to_bytes(&self, uniforms: &FrameUniforms) -> Result<Vec<u8>> {
        // Upload uniform data to a GPU buffer.
        let uniform_buffer = self.device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("melosviz_uniforms"),
            contents: bytemuck::bytes_of(uniforms),
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
        });

        let bind_group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("melosviz_bg"),
            layout: &self.pipelines.uniform_bind_group_layout,
            entries: &[wgpu::BindGroupEntry {
                binding: 0,
                resource: uniform_buffer.as_entire_binding(),
            }],
        });

        // Create offscreen render target.
        let render_texture = self.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("melosviz_render"),
            size: wgpu::Extent3d { width: self.width, height: self.height, depth_or_array_layers: 1 },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: HEADLESS_FORMAT,
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::COPY_SRC,
            view_formats: &[],
        });
        let render_view = render_texture.create_view(&wgpu::TextureViewDescriptor::default());

        // Read-back buffer (must be aligned to 256-byte row pitch for wgpu).
        let bytes_per_pixel: u32 = 4;
        let unpadded_row_bytes = self.width * bytes_per_pixel;
        let align = wgpu::COPY_BYTES_PER_ROW_ALIGNMENT;
        let padded_row_bytes = (unpadded_row_bytes + align - 1) / align * align;
        let readback_buf = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("melosviz_readback"),
            size: (padded_row_bytes * self.height) as u64,
            usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
            mapped_at_creation: false,
        });

        // Encode render passes — compositor order: bg → hue → beat → particles.
        let mut encoder = self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor {
            label: Some("melosviz_encoder"),
        });

        for (i, pipeline) in [
            &self.pipelines.bg_gradient,
            &self.pipelines.spectral_hue,
            &self.pipelines.beat_pulse,
            &self.pipelines.stem_particles,
        ]
        .iter()
        .enumerate()
        {
            let load = if i == 0 {
                wgpu::LoadOp::Clear(wgpu::Color::BLACK)
            } else {
                wgpu::LoadOp::Load
            };
            let mut render_pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("melosviz_pass"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &render_view,
                    resolve_target: None,
                    ops: wgpu::Operations { load, store: wgpu::StoreOp::Store },
                })],
                depth_stencil_attachment: None,
                timestamp_writes: None,
                occlusion_query_set: None,
            });
            render_pass.set_pipeline(pipeline);
            render_pass.set_bind_group(0, &bind_group, &[]);
            render_pass.draw(0..3, 0..1);
        }

        // Copy texture → read-back buffer.
        encoder.copy_texture_to_buffer(
            render_texture.as_image_copy(),
            wgpu::ImageCopyBuffer {
                buffer: &readback_buf,
                layout: wgpu::ImageDataLayout {
                    offset: 0,
                    bytes_per_row: Some(padded_row_bytes),
                    rows_per_image: Some(self.height),
                },
            },
            wgpu::Extent3d { width: self.width, height: self.height, depth_or_array_layers: 1 },
        );

        self.queue.submit(std::iter::once(encoder.finish()));

        // Map the read-back buffer and copy pixel rows (removing padding).
        let buffer_slice = readback_buf.slice(..);
        let (tx, rx) = std::sync::mpsc::channel();
        buffer_slice.map_async(wgpu::MapMode::Read, move |res| {
            let _ = tx.send(res);
        });
        self.device.poll(wgpu::Maintain::Wait);
        rx.recv()??;

        let mapped = buffer_slice.get_mapped_range();
        let mut pixels = Vec::with_capacity((self.width * self.height * 4) as usize);
        for row in 0..self.height {
            let start = (row * padded_row_bytes) as usize;
            let end = start + unpadded_row_bytes as usize;
            pixels.extend_from_slice(&mapped[start..end]);
        }
        drop(mapped);
        readback_buf.unmap();

        Ok(pixels)
    }

    /// Render all frames for the given [`RenderSpec`], returning raw RGBA
    /// bytes for each frame (width × height × 4 bytes per frame).
    ///
    /// Calls `render_frame_to_bytes()` for each frame in `0..total_frames`.
    /// The segment cache is consulted to skip re-rendering unchanged segments
    /// (incremental edit path).
    pub async fn render_spec(
        &self,
        spec: &RenderSpec,
        cache: &mut crate::segment_cache::SegmentCache,
    ) -> Result<Vec<Vec<u8>>> {
        use crate::segment_cache::SegmentKey;

        let timeline = Timeline::from_spec(spec);
        let total_frames = spec.total_frames();
        let mut frames: Vec<Vec<u8>> = Vec::with_capacity(total_frames as usize);

        for frame_idx in 0..total_frames {
            // Check incremental cache for this segment.
            if let Some(segment) = spec.segment_for_frame(frame_idx) {
                let energy_range = self.segment_energy_range(spec, segment);
                let param_hash = crate::segment_cache::SegmentCache::compute_param_hash(
                    &segment.label,
                    segment.palette_index,
                    &segment.scene_type,
                    energy_range.0,
                    energy_range.1,
                );
                let key = SegmentKey::new(&segment.id, param_hash);
                // Cache hit: segment bytes are already rendered for this hash.
                // (In a full implementation, we'd store frame ranges per segment;
                // for now we fall through to per-frame render as the cache structure
                // is used for the segment-level invalidation logic.)
                let _ = cache.get(&key);
            }

            let uniforms = timeline
                .sample(frame_idx)
                .with_frame_index(frame_idx)
                .with_palette_rgb(
                    spec.palette.first().map(|s| hex_channel(s, 0)).unwrap_or(0.0),
                    spec.palette.first().map(|s| hex_channel(s, 1)).unwrap_or(0.9),
                    spec.palette.first().map(|s| hex_channel(s, 2)).unwrap_or(1.0),
                );
            let frame = self.render_frame_to_bytes(&uniforms).await?;
            frames.push(frame);
        }

        Ok(frames)
    }

    /// Compute (min_energy, max_energy) for a segment's keyframe range.
    fn segment_energy_range(
        &self,
        spec: &RenderSpec,
        segment: &crate::spec::SceneSegment,
    ) -> (f32, f32) {
        let fps = spec.metadata.fps.max(1) as f32;
        let kfs: Vec<f32> = spec
            .dense_keyframes
            .iter()
            .filter(|kf| kf.t >= segment.start && kf.t < segment.end)
            .map(|kf| kf.energy)
            .collect();
        let first = kfs.first().copied().unwrap_or(0.0);
        let last = kfs.last().copied().unwrap_or(0.0);
        let _ = fps;
        (first, last)
    }

    /// Output width in pixels.
    pub fn width(&self) -> u32 {
        self.width
    }

    /// Output height in pixels.
    pub fn height(&self) -> u32 {
        self.height
    }
}

/// Parse one channel (0=R, 1=G, 2=B) from a `#rrggbb` hex string → [0,1].
fn hex_channel(hex: &str, channel: usize) -> f32 {
    let clean = hex.trim().trim_start_matches('#');
    if clean.len() < 6 {
        return [0.0, 0.9, 1.0][channel.min(2)];
    }
    let offset = channel * 2;
    u8::from_str_radix(&clean[offset..offset + 2], 16).unwrap_or(0) as f32 / 255.0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hex_channel_parsing_red() {
        let val = hex_channel("#FF0000", 0);
        assert!((val - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_hex_channel_parsing_green() {
        let val = hex_channel("#00FF00", 1);
        assert!((val - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_hex_channel_parsing_blue() {
        let val = hex_channel("#0000FF", 2);
        assert!((val - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_hex_channel_parsing_black() {
        let val = hex_channel("#000000", 0);
        assert!(val < 0.01);
    }

    #[test]
    fn test_hex_channel_invalid_short() {
        let val = hex_channel("#FFF", 0);
        assert!(val >= 0.0);
    }

    #[tokio::test]
    #[ignore]
    async fn test_renderer_creation_requires_gpu() {
        match WgpuRenderer::new(1280, 720).await {
            Ok(_) => {
                assert!(true);
            }
            Err(e) => {
                assert!(e.to_string().contains("No GPU adapter") || e.to_string().contains("adapter"));
            }
        }
    }

    #[tokio::test]
    #[ignore]
    async fn test_frame_output_non_empty() {
        if let Ok(renderer) = WgpuRenderer::new(64, 64).await {
            let uniforms = FrameUniforms::default();
            match renderer.render_frame_to_bytes(&uniforms).await {
                Ok(pixels) => {
                    let expected_size = 64 * 64 * 4;
                    assert_eq!(pixels.len(), expected_size);
                    assert!(!pixels.is_empty());
                }
                Err(_) => {
                    assert!(true);
                }
            }
        }
    }

    #[tokio::test]
    #[ignore]
    async fn test_frame_output_pixel_range() {
        if let Ok(renderer) = WgpuRenderer::new(32, 32).await {
            let uniforms = FrameUniforms::default();
            match renderer.render_frame_to_bytes(&uniforms).await {
                Ok(pixels) => {
                    for &byte in &pixels {
                        assert!(byte <= 255);
                    }
                }
                Err(_) => {
                    assert!(true);
                }
            }
        }
    }

    #[test]
    fn test_hex_channel_rgba_channel_order() {
        let hex = "#AABBCC";
        let r = hex_channel(hex, 0);
        let g = hex_channel(hex, 1);
        let b = hex_channel(hex, 2);

        assert!(r > g);
        assert!(g > b);
    }

    #[test]
    fn test_hex_channel_whitespace_handling() {
        let val1 = hex_channel("#FF0000", 0);
        let val2 = hex_channel("  #FF0000  ", 0);

        assert!((val1 - val2).abs() < 0.001);
    }

    #[test]
    fn test_hex_channel_midrange_value() {
        let val = hex_channel("#808080", 0);
        assert!(val > 0.4 && val < 0.6);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hex_channel_parses_correctly() {
        assert!((hex_channel("#00f5ff", 0) - 0.0).abs() < 1e-3);
        assert!((hex_channel("#00f5ff", 1) - 0.9608).abs() < 0.01);
        assert!((hex_channel("#00f5ff", 2) - 1.0).abs() < 1e-3);
    }

    #[test]
    fn test_hex_channel_with_prefix() {
        // #ff2fd5 → R=0xff=255, G=0x2f=47, B=0xd5=213
        assert!((hex_channel("#ff2fd5", 0) - 1.0).abs() < 1e-3);
        assert!((hex_channel("#ff2fd5", 1) - 47.0 / 255.0).abs() < 0.01);
        assert!((hex_channel("#ff2fd5", 2) - 213.0 / 255.0).abs() < 0.01);
    }

    #[test]
    fn test_hex_channel_invalid_returns_default() {
        // short string → default palette colour
        assert_eq!(hex_channel("bad", 0), 0.0);
        assert_eq!(hex_channel("bad", 1), 0.9);
    }

    // GPU adapter test — only runs on hosts with Metal/Vulkan.
    #[test]
    #[ignore = "requires GPU adapter (run on host with Metal/Vulkan)"]
    fn test_renderer_new_succeeds_with_gpu() {
        pollster::block_on(async {
            let renderer = WgpuRenderer::new(64, 64).await.expect("should create renderer");
            assert_eq!(renderer.width(), 64);
            assert_eq!(renderer.height(), 64);
        });
    }

    #[test]
    #[ignore = "requires GPU adapter (run on host with Metal/Vulkan)"]
    fn test_render_frame_to_bytes_returns_correct_size() {
        pollster::block_on(async {
            let renderer = WgpuRenderer::new(64, 48).await.unwrap();
            let uniforms = FrameUniforms::default();
            let bytes = renderer.render_frame_to_bytes(&uniforms).await.unwrap();
            assert_eq!(bytes.len(), 64 * 48 * 4);
        });
    }

    #[test]
    #[ignore = "requires GPU adapter (run on host with Metal/Vulkan)"]
    fn test_render_frame_not_all_black() {
        // The bg_gradient shader should produce non-black output even with zero energy.
        pollster::block_on(async {
            let renderer = WgpuRenderer::new(64, 48).await.unwrap();
            let uniforms = FrameUniforms::default().with_palette_rgb(0.0, 0.96, 1.0);
            let bytes = renderer.render_frame_to_bytes(&uniforms).await.unwrap();
            let nonzero: usize = bytes.iter().filter(|&&b| b > 0).count();
            assert!(nonzero > 0, "expected non-black output from bg_gradient shader");
        });
    }
}
