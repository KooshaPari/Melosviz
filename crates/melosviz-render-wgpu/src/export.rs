//! Headless frame export — GPU texture → ffmpeg rawvideo pipe → MP4.
//!
//! [`export_to_mp4`] takes a [`WgpuRenderer`], a [`RenderSpec`], and an
//! output path, renders every frame, and pipes raw RGBA bytes to an `ffmpeg`
//! subprocess using the `rawvideo` demuxer.
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
    cache: &mut SegmentCache,
    output_path: &Path,
) -> Result<()> {
    let width = renderer.width();
    let height = renderer.height();
    let fps = spec.metadata.fps.max(1);

    // Spawn ffmpeg expecting rawvideo RGBA input on stdin.
    let mut child = Command::new("ffmpeg")
        .args([
            "-y",
            "-f", "rawvideo",
            "-pixel_format", "rgba",
            "-video_size", &format!("{width}x{height}"),
            "-framerate", &fps.to_string(),
            "-i", "pipe:0",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
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
        stdin.write_all(&rgba_bytes).map_err(|e| anyhow::anyhow!("Pipe write error: {e}"))?;
    }

    drop(stdin);  // Signal EOF to ffmpeg.

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

    // Export tests require a GPU adapter — skip on CI.
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
            export_to_mp4(&renderer, &spec, &mut cache, &output).await.unwrap();

            assert!(output.exists());
            assert!(output.metadata().unwrap().len() > 0);
        });
    }
}
