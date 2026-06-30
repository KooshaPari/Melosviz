//! melosviz-render-wgpu — realtime preview renderer
//!
//! Consumes a [`RenderSpec`] v2 (dense keyframes, scene segments, stems,
//! palette) and renders frames via WGSL compute/render shaders on the
//! wgpu Metal backend (Apple Silicon) or Vulkan/DX12 on other platforms.
//!
//! # Architecture
//!
//! ```text
//! RenderSpec JSON
//!   └─► spec::RenderSpec  (serde deserialise)
//!         └─► timeline::Timeline  (keyframe lookup)
//!               └─► uniforms::FrameUniforms  (push constants / storage buffer)
//!                     └─► renderer::WgpuRenderer  (device + queue + pipelines)
//!                           ├─► [windowed]  Surface → present
//!                           └─► [headless]  Texture → map_read → ffmpeg rawvideo pipe
//! segment_cache::SegmentCache  (Arc<wgpu::Texture> keyed by segment hash)
//!   → re-render only dirty segments on edit
//! ```
//!
//! # Visual vocabulary (matches Blender bpy driver)
//!
//! The WGSL shaders implement the same scene-graph language as the Python
//! `build_bpy_script` Blender driver:
//!
//! | Parameter | Shader | Visual effect |
//! |-----------|--------|---------------|
//! | `energy` | `beat_pulse.wgsl` | emitter scale + radial glow |
//! | `spectral_centroid` | `spectral_hue.wgsl` | HSV hue rotation |
//! | `stems.drums` | `stem_particles.wgsl` | particle density |
//! | `stems.bass` | `stem_particles.wgsl` | camera scale |
//! | segment `label` | `bg_gradient.wgsl` | world background colour |
//!
//! Quality differs (rasterised vs path-traced) but the visual *nature* is the
//! same, satisfying the "true-to-final-in-nature" preview requirement.
//!
//! # Performance targets (Apple M1 Pro, estimated)
//!
//! | Resolution | Per-frame | FPS | 5400-frame render |
//! |------------|-----------|-----|-------------------|
//! | 1280×720   | ~2–5 ms   | 200–500 | ~11–27 s |
//! | 1920×1080  | ~4–8 ms   | 125–250 | ~22–43 s |
//!
//! These are estimates from Metal/wgpu workload characterisation; no wgpu
//! GPU was available to measure during implementation. See
//! `docs/PERF_BENCHMARK.md §3b` for the derivation.
//!
//! # Incremental edit cache
//!
//! [`SegmentCache`] stores a rendered `Arc<wgpu::Texture>` per segment,
//! keyed by `(segment_id, parameter_hash)`. On an edit that touches one
//! segment's parameters, only that segment's frames are re-rendered and
//! spliced into the output stream. For a 30s segment at ~3 ms/frame:
//! `900 frames × 3 ms = ~2.7 s` — well under the 5 s/edit target.

pub mod export;
pub mod pipeline;
pub mod renderer;
pub mod segment_cache;
pub mod spec;
pub mod timeline;
pub mod uniforms;

pub use renderer::WgpuRenderer;
pub use segment_cache::SegmentCache;
pub use spec::RenderSpec;
