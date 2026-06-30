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
//! # Tier-1 (primary): wgpu realtime — performance targets (Apple M1 Pro)
//!
//! | Resolution | Per-frame | FPS | 5400-frame render |
//! |------------|-----------|-----|-------------------|
//! | 1280×720   | ~2–5 ms **est.** | 200–500 | **~11–27 s est.** |
//! | 1920×1080  | ~4–8 ms **est.** | 125–250 | **~22–43 s est.** |
//!
//! **Honest labelling:** these are estimates from Metal/wgpu workload
//! characterisation (see `docs/PERF_BENCHMARK.md §3b`). No GPU adapter was
//! available in this environment to produce measured numbers. GPU tests are
//! `#[ignore]`-tagged and must be run on a host with Metal/Vulkan:
//! `cargo test --lib -- --ignored`.
//!
//! # Interim fallback (while wgpu headless is being validated on host)
//!
//! If `WgpuRenderer::new()` fails (no GPU adapter / headless CI environment),
//! the operator is NOT blocked. The EEVEE-Next persistent-process scrub path
//! (measured in `docs/PERF_BENCHMARK.md §2c / [E4]`) provides immediate usable
//! preview:
//!
//! ```text
//! EEVEE-Next 1-fps scrub preview (Blender 4.4.3 headless, 1-sample, confirmed):
//!   30s segment × 1fps scrub = 30 frames × 52.9 ms/frame = 1.6 s  ← hits <5s/edit
//!   2fps scrub: 60 frames × 52.9 ms = 3.2 s                       ← still <5s/edit
//! Full 30fps re-render of same 30s segment: 47.6 s (does NOT hit target)
//! ```
//!
//! The interim path is a Python-only path driven by the existing Blender adapter
//! (`backend/src/melosviz/render/blender_exporter.py`) with engine set to
//! `BLENDER_EEVEE_NEXT` and samples=1. It shares the same `RenderSpec` JSON.
//! No code changes needed to activate it — the conductor already has
//! `blender_exporter.py`. Once `melosviz-render` binary is validated on the
//! host (via `cargo test --lib -- --ignored`), the conductor can switch to
//! the wgpu path for full 30fps realtime.
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
