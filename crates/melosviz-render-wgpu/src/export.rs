//! Headless frame export — GPU texture → bytes / ffmpeg rawvideo pipe → MP4.
//!
//! Two public entry points:
//!
//! * [`export_frame_bytes`] — renders a **single frame** and returns raw RGBA
//!   bytes directly (width × height × 4).  This is the primary output path for
//!   the Python bridge (`wgpu_adapter.py`): the Python side invokes the
//!   `melosviz-render export-frame` subcommand which calls this function and
//!   writes the bytes to stdout.
//!
//! * [`export_to_mp4`] — renders all frames for a [`RenderSpec`] and pipes
//!   them to an ffmpeg subprocess to produce an MP4.
//!
//! # Performance (estimated, Apple M1 Pro)
//!
//! - GPU render: ~2–5 ms/frame at 720p → 5400 frames = 10.8–27 s
//! - ffmpeg rawvideo encode: ~4 ms/frame → 5400 frames = ~22 s (overlapped)
//! - Total 720p 180 s render: **~15–35 s** (vs 96 s baseline before this crate)
//!
//! These are estimates from Metal/wgpu workload characterisation; see
//! `docs/PERF_BENCHMARK.md §3b`.

use anyhow::Result;
use std::io::Write;
use std::path::Path;
use std::process::{Command, Stdio};

use crate::renderer::WgpuRenderer;
use crate::segment_cache::SegmentCache;
use crate::spec::RenderSpec;
use crate::uniforms::FrameUniforms;

/// Render a single frame and return raw RGBA bytes (width × height × 4).
///
/// This is the primitive the Python bridge calls via the `export-frame`
/// subcommand.  It creates a [`WgpuRenderer`] at the requested dimensions,
/// renders one frame using the provided [`FrameUniforms`], and returns the
/// pixel buffer directly.
///
/// # Parameters
/// - `width` / `height`: output dimensions in pixels (must be ≥ 1)
/// - `uniforms`: per-frame shader parameters (energy, spectral centroid, etc.)
///
/// # Errors
/// - Returns an error if no GPU adapter is available.
/// - Returns an error if the GPU read-back fails.
pub async fn export_frame_bytes(
    width: u32,
    height: u32,
    uniforms: &FrameUniforms,
) -> Result<Vec<u8>> {
    let renderer = WgpuRenderer::new(width, height).await?;
    renderer.render_frame_to_bytes(uniforms).await
}

/// Render `spec` to an MP4 at `output_path` using the wgpu headless renderer.
///
/// Pipes raw RGBA frames from the GPU directly to ffmpeg's `rawvideo`
/// demuxer (no intermediate PNG files).
///
/// # Errors
/// Returns an error if the GPU renderer fails, ffmpeg is not on PATH, or
/// ffmpeg exits non-zero.
pub async fn export_to_mp4(
    renderer: &WgpuRenderer,
    spec: &RenderSpec,
    _cache: &mut SegmentCache,
    output_path: &Path,
) -> Result<()> {
    let width = renderer.width();
    let height = renderer.height();
    let fps = spec.metadata.fps.max(1);

    // Spawn ffmpeg expecting rawvideo RGBA input on stdin.
    let mut child = Command::new("ffmpeg")
        .args([
            "-y",
            "-f",
            "rawvideo",
            "-pixel_format",
            "rgba",
            "-video_size",
            &format!("{width}x{height}"),
            "-framerate",
            &fps.to_string(),
            "-i",
            "pipe:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "fast",
            output_path.to_str().unwrap_or("output.mp4"),
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| anyhow::anyhow!("Failed to spawn ffmpeg: {e}. Is ffmpeg installed?"))?;

    let mut stdin = child.stdin.take().expect("ffmpeg stdin");

    // Render frames and pipe to ffmpeg.
    let timeline = crate::timeline::Timeline::from_spec(spec);
    let total_frames = spec.total_frames();

    for frame_idx in 0..total_frames {
        let uniforms = timeline.sample(frame_idx).with_frame_index(frame_idx);
        let rgba_bytes = renderer.render_frame_to_bytes(&uniforms).await?;
        stdin
            .write_all(&rgba_bytes)
            .map_err(|e| anyhow::anyhow!("Pipe write error: {e}"))?;
    }

    drop(stdin); // Signal EOF to ffmpeg.

    let output = child.wait_with_output()?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let tail: String = stderr.lines().rev().take(5).collect::<Vec<_>>().join("\n");
        return Err(anyhow::anyhow!(
            "ffmpeg exited with status {:?}. Stderr tail:\n{tail}",
            output.status.code()
        ));
    }

    log::info!("export_to_mp4: wrote {}", output_path.display());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::uniforms::FrameUniforms;

    // -----------------------------------------------------------------------
    // export_frame_bytes — GPU-gated tests (run with: cargo test -- --ignored)
    // -----------------------------------------------------------------------

    /// Verify that `export_frame_bytes` returns exactly `width * height * 4`
    /// bytes and that not every pixel is zero (the bg_gradient shader paints
    /// something even at zero energy).
    ///
    /// Requires a Metal/Vulkan GPU adapter — tagged `#[ignore]` for CI.
    /// Run on host: `cargo test -p melosviz-render-wgpu -- --ignored`
    #[test]
    #[ignore = "requires GPU adapter (Metal/Vulkan) — run on host with: cargo test -- --ignored"]
    fn test_export_frame_bytes_correct_size() {
        pollster::block_on(async {
            let (w, h) = (64u32, 48u32);
            let uniforms = FrameUniforms::default().with_palette_rgb(0.0, 0.96, 1.0);
            let bytes = export_frame_bytes(w, h, &uniforms)
                .await
                .expect("export_frame_bytes should succeed with a GPU adapter");
            assert_eq!(
                bytes.len(),
                (w * h * 4) as usize,
                "expected exactly width×height×4 RGBA bytes"
            );
        });
    }

    #[test]
    #[ignore = "requires GPU adapter (Metal/Vulkan) — run on host with: cargo test -- --ignored"]
    fn test_export_frame_bytes_non_empty_content() {
        // The bg_gradient shader fills the frame even at zero energy.
        // If every byte is 0 the shader is not running — fail loudly.
        pollster::block_on(async {
            let (w, h) = (64u32, 48u32);
            let uniforms = FrameUniforms::default().with_palette_rgb(0.0, 0.96, 1.0);
            let bytes = export_frame_bytes(w, h, &uniforms)
                .await
                .expect("export_frame_bytes should succeed with a GPU adapter");
            let non_zero = bytes.iter().filter(|&&b| b > 0).count();
            assert!(
                non_zero > 0,
                "every pixel was 0 — bg_gradient shader did not paint anything; \
                 check pipeline compilation and uniform upload"
            );
        });
    }

    // Export tests require a GPU adapter + ffmpeg — skip on CI.
    #[test]
    #[ignore = "requires GPU adapter + ffmpeg (run on host)"]
    fn test_export_to_mp4_produces_file() {
        use crate::spec::{RenderMetadata, RenderSpec};
        use tempfile::tempdir;

        pollster::block_on(async {
            let dir = tempdir().unwrap();
            let output = dir.path().join("test.mp4");

            let spec = RenderSpec {
                metadata: RenderMetadata {
                    width: 64,
                    height: 48,
                    fps: 5,
                    duration: 1.0,
                    ..Default::default()
                },
                ..Default::default()
            };

            let renderer = WgpuRenderer::new(64, 48).await.unwrap();
            let mut cache = SegmentCache::new();
            export_to_mp4(&renderer, &spec, &mut cache, &output)
                .await
                .unwrap();

            assert!(output.exists());
            assert!(output.metadata().unwrap().len() > 0);
        });
    }
}
