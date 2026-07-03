//! Headless frame export — GPU texture → bytes / ffmpeg rawvideo pipe → MP4.
//!
//! Public entry points:
//!
//! * [`export_frame_bytes`] — renders a **single frame** and returns raw RGBA
//!   bytes directly (width × height × 4).  This is the primary output path for
//!   the Python bridge (`wgpu_adapter.py`): the Python side invokes the
//!   `melosviz-render export-frame` subcommand which calls this function and
//!   writes the bytes to stdout.
//!
//! * [`encode_rgba_to_png`] — encodes a raw RGBA byte buffer to a PNG `Vec<u8>`
//!   using the [`image`] crate.  No GPU required; pure CPU.
//!
//! * [`export_frame_to_png`] — GPU-render one frame, then PNG-encode the
//!   result.  Used by the `export-png` CLI subcommand.
//!
//! * [`export_frames_to_dir`] — GPU-render a range of frames, write each to
//!   a numbered PNG in `out_dir/`, and write a contact-sheet PNG (`sheet.png`)
//!   as a single image composed of all frames tiled horizontally.  Used by the
//!   `demo-frames` CLI subcommand.
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
use image::{ImageBuffer, Rgba};
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

/// Encode a raw RGBA byte buffer to a PNG `Vec<u8>`.
///
/// This is a pure-CPU operation — no GPU required.  Useful for:
/// - Writing frames already obtained from [`export_frame_bytes`] to disk.
/// - Unit testing PNG encoding without a GPU.
///
/// # Parameters
/// - `rgba`: raw RGBA bytes, exactly `width * height * 4` bytes long.
/// - `width` / `height`: image dimensions in pixels.
///
/// # Errors
/// Returns an error if `rgba.len() != width * height * 4`, or if the PNG
/// encoder fails (should not happen for valid dimensions).
pub fn encode_rgba_to_png(rgba: &[u8], width: u32, height: u32) -> Result<Vec<u8>> {
    let expected = (width as usize)
        .checked_mul(height as usize)
        .and_then(|n| n.checked_mul(4))
        .ok_or_else(|| anyhow::anyhow!("image dimensions overflow: {width}x{height}"))?;
    if rgba.len() != expected {
        return Err(anyhow::anyhow!(
            "rgba buffer length {} does not match {width}x{height}x4 = {expected}",
            rgba.len()
        ));
    }

    let img: ImageBuffer<Rgba<u8>, Vec<u8>> =
        ImageBuffer::from_raw(width, height, rgba.to_vec())
            .ok_or_else(|| anyhow::anyhow!("failed to construct ImageBuffer from raw RGBA data"))?;

    let mut png_bytes: Vec<u8> = Vec::new();
    img.write_to(
        &mut std::io::Cursor::new(&mut png_bytes),
        image::ImageFormat::Png,
    )
    .map_err(|e| anyhow::anyhow!("PNG encode error: {e}"))?;

    Ok(png_bytes)
}

/// GPU-render one frame then encode the result as a PNG file.
///
/// Combines [`export_frame_bytes`] (GPU render) with [`encode_rgba_to_png`]
/// (CPU PNG encode) and writes the result to `out_path`.
///
/// # Errors
/// - No GPU adapter available.
/// - GPU read-back fails.
/// - PNG write fails.
pub async fn export_frame_to_png(
    width: u32,
    height: u32,
    uniforms: &FrameUniforms,
    out_path: &Path,
) -> Result<()> {
    let rgba = export_frame_bytes(width, height, uniforms).await?;
    let png = encode_rgba_to_png(&rgba, width, height)?;
    std::fs::write(out_path, &png)
        .map_err(|e| anyhow::anyhow!("Failed to write PNG to {}: {e}", out_path.display()))?;
    log::info!(
        "export_frame_to_png: wrote {} bytes to {}",
        png.len(),
        out_path.display()
    );
    Ok(())
}

/// GPU-render a frame range from `spec` and write each frame as a numbered PNG.
///
/// Files are written to `out_dir/frame_{:06}.png`.  After all frames are
/// rendered a contact-sheet (`out_dir/sheet.png`) is written: all frames
/// tiled horizontally in a single row, each thumbnail scaled to
/// `thumb_width × thumb_height`.
///
/// # Parameters
/// - `spec`: render spec (metadata + keyframes).
/// - `frame_start` / `frame_end`: half-open range `[frame_start, frame_end)`.
///   Clamped to `[0, spec.total_frames())`.
/// - `out_dir`: directory to write PNGs into (created if missing).
/// - `thumb_width` / `thumb_height`: contact-sheet thumbnail size per frame.
///   If 0, defaults to `frame_width / 8` and `frame_height / 8`.
///
/// # Errors
/// Returns the first GPU or I/O error encountered.
#[allow(clippy::too_many_arguments)]
pub async fn export_frames_to_dir(
    spec: &RenderSpec,
    frame_start: u32,
    frame_end: u32,
    out_dir: &Path,
    thumb_width: u32,
    thumb_height: u32,
) -> Result<Vec<std::path::PathBuf>> {
    let frame_w = spec.metadata.width.max(1);
    let frame_h = spec.metadata.height.max(1);
    let total = spec.total_frames();
    let start = frame_start.min(total);
    let end = frame_end.min(total).max(start);

    std::fs::create_dir_all(out_dir)
        .map_err(|e| anyhow::anyhow!("Failed to create output dir {}: {e}", out_dir.display()))?;

    let tw = if thumb_width == 0 {
        (frame_w / 8).max(1)
    } else {
        thumb_width
    };
    let th = if thumb_height == 0 {
        (frame_h / 8).max(1)
    } else {
        thumb_height
    };

    let renderer = WgpuRenderer::new(frame_w, frame_h).await?;
    let timeline = crate::timeline::Timeline::from_spec(spec);

    let mut written: Vec<std::path::PathBuf> = Vec::new();
    // Contact-sheet buffer: frames tiled horizontally.
    let frame_count = (end - start) as usize;
    let sheet_w = tw * frame_count as u32;
    let sheet_h = th;
    let mut sheet: ImageBuffer<Rgba<u8>, Vec<u8>> =
        ImageBuffer::new(sheet_w.max(1), sheet_h.max(1));

    for (i, frame_idx) in (start..end).enumerate() {
        let uniforms = timeline.sample(frame_idx).with_frame_index(frame_idx);
        let rgba = renderer.render_frame_to_bytes(&uniforms).await?;

        // Full-resolution PNG.
        let out_path = out_dir.join(format!("frame_{frame_idx:06}.png"));
        let png = encode_rgba_to_png(&rgba, frame_w, frame_h)?;
        std::fs::write(&out_path, &png)
            .map_err(|e| anyhow::anyhow!("Failed to write {}: {e}", out_path.display()))?;
        written.push(out_path);

        // Thumbnail for contact sheet via nearest-neighbour resize.
        let full: ImageBuffer<Rgba<u8>, Vec<u8>> = ImageBuffer::from_raw(frame_w, frame_h, rgba)
            .ok_or_else(|| anyhow::anyhow!("from_raw failed at frame {frame_idx}"))?;
        let thumb = image::imageops::resize(&full, tw, th, image::imageops::FilterType::Nearest);
        image::imageops::replace(&mut sheet, &thumb, (i as u32 * tw) as i64, 0);

        log::info!(
            "demo-frames: frame {frame_idx}/{} → {}",
            end - 1,
            written.last().unwrap().display()
        );
    }

    // Write contact sheet.
    if !written.is_empty() {
        let sheet_path = out_dir.join("sheet.png");
        let mut sheet_bytes: Vec<u8> = Vec::new();
        sheet
            .write_to(
                &mut std::io::Cursor::new(&mut sheet_bytes),
                image::ImageFormat::Png,
            )
            .map_err(|e| anyhow::anyhow!("Contact sheet PNG encode error: {e}"))?;
        std::fs::write(&sheet_path, &sheet_bytes)
            .map_err(|e| anyhow::anyhow!("Failed to write sheet: {e}"))?;
        log::info!("demo-frames: contact sheet → {}", sheet_path.display());
        written.push(sheet_path);
    }

    Ok(written)
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
    // encode_rgba_to_png — pure CPU, no GPU required
    // -----------------------------------------------------------------------

    /// PNG magic bytes: first 8 bytes of every valid PNG file.
    const PNG_MAGIC: &[u8] = &[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];

    #[test]
    fn test_encode_rgba_to_png_magic_bytes() {
        let (w, h) = (4u32, 4u32);
        let rgba = vec![0u8; (w * h * 4) as usize];
        let png = encode_rgba_to_png(&rgba, w, h).expect("encode should succeed");
        assert!(
            png.starts_with(PNG_MAGIC),
            "output does not start with PNG magic bytes"
        );
    }

    #[test]
    fn test_encode_rgba_to_png_non_empty() {
        let (w, h) = (8u32, 8u32);
        let rgba = vec![128u8; (w * h * 4) as usize];
        let png = encode_rgba_to_png(&rgba, w, h).expect("encode should succeed");
        assert!(!png.is_empty(), "PNG output must not be empty");
    }

    #[test]
    fn test_encode_rgba_to_png_dimensions_in_ihdr() {
        // PNG IHDR chunk: bytes 16-19 = width (big-endian u32),
        //                 bytes 20-23 = height (big-endian u32).
        let (w, h) = (32u32, 24u32);
        let rgba = vec![0xFFu8; (w * h * 4) as usize];
        let png = encode_rgba_to_png(&rgba, w, h).expect("encode should succeed");
        assert!(png.len() >= 24, "PNG too short to contain IHDR");
        let enc_w = u32::from_be_bytes([png[16], png[17], png[18], png[19]]);
        let enc_h = u32::from_be_bytes([png[20], png[21], png[22], png[23]]);
        assert_eq!(enc_w, w, "PNG IHDR width mismatch");
        assert_eq!(enc_h, h, "PNG IHDR height mismatch");
    }

    #[test]
    fn test_encode_rgba_to_png_wrong_buffer_size_errors() {
        let (w, h) = (4u32, 4u32);
        // One byte short — must error loudly.
        let rgba = vec![0u8; (w * h * 4) as usize - 1];
        let result = encode_rgba_to_png(&rgba, w, h);
        assert!(
            result.is_err(),
            "expected error for wrong buffer size, got Ok"
        );
    }

    #[test]
    fn test_encode_rgba_to_png_1x1_pixel() {
        // Single pixel: R=255, G=0, B=128, A=255.
        let rgba = vec![255u8, 0, 128, 255];
        let png = encode_rgba_to_png(&rgba, 1, 1).expect("1×1 encode should succeed");
        assert!(png.starts_with(PNG_MAGIC));
        // IHDR at byte 16: width=1, height=1
        assert_eq!(u32::from_be_bytes([png[16], png[17], png[18], png[19]]), 1);
        assert_eq!(u32::from_be_bytes([png[20], png[21], png[22], png[23]]), 1);
    }

    #[test]
    fn test_encode_rgba_to_png_coloured_gradient() {
        // 16×1 strip: pixel i has R=i*16, G=0, B=0, A=255.
        let w = 16u32;
        let h = 1u32;
        let rgba: Vec<u8> = (0..w).flat_map(|i| [i as u8 * 16, 0, 0, 255]).collect();
        let png = encode_rgba_to_png(&rgba, w, h).expect("gradient encode should succeed");
        assert!(png.starts_with(PNG_MAGIC));
    }

    #[test]
    fn test_encode_rgba_to_png_large_frame_720p_noise() {
        // 1280×720 random-ish buffer — validates no OOM / panic on large input.
        let (w, h) = (1280u32, 720u32);
        let rgba: Vec<u8> = (0..(w * h * 4)).map(|i| (i % 256) as u8).collect();
        let png = encode_rgba_to_png(&rgba, w, h).expect("720p encode should succeed");
        assert!(png.starts_with(PNG_MAGIC));
        let enc_w = u32::from_be_bytes([png[16], png[17], png[18], png[19]]);
        let enc_h = u32::from_be_bytes([png[20], png[21], png[22], png[23]]);
        assert_eq!(enc_w, w);
        assert_eq!(enc_h, h);
    }

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

    // -----------------------------------------------------------------------
    // export_frame_to_png — GPU-gated
    // -----------------------------------------------------------------------

    #[test]
    #[ignore = "requires GPU adapter (Metal/Vulkan) — run on host with: cargo test -- --ignored"]
    fn test_export_frame_to_png_writes_valid_png() {
        use tempfile::tempdir;
        pollster::block_on(async {
            let dir = tempdir().unwrap();
            let out = dir.path().join("frame0.png");
            let uniforms = FrameUniforms::default().with_palette_rgb(0.0, 0.96, 1.0);
            export_frame_to_png(64, 48, &uniforms, &out)
                .await
                .expect("export_frame_to_png should succeed with GPU");
            let bytes = std::fs::read(&out).expect("PNG file must exist");
            assert!(bytes.starts_with(PNG_MAGIC), "output is not a valid PNG");
            let enc_w = u32::from_be_bytes([bytes[16], bytes[17], bytes[18], bytes[19]]);
            let enc_h = u32::from_be_bytes([bytes[20], bytes[21], bytes[22], bytes[23]]);
            assert_eq!(enc_w, 64);
            assert_eq!(enc_h, 48);
        });
    }

    // -----------------------------------------------------------------------
    // export_frames_to_dir — GPU-gated
    // -----------------------------------------------------------------------

    #[test]
    #[ignore = "requires GPU adapter (Metal/Vulkan) — run on host with: cargo test -- --ignored"]
    fn test_export_frames_to_dir_produces_pngs_and_sheet() {
        use crate::spec::{RenderMetadata, RenderSpec};
        use tempfile::tempdir;

        pollster::block_on(async {
            let dir = tempdir().unwrap();
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
            // Render frames 0..4 (4 frames).
            let written = export_frames_to_dir(&spec, 0, 4, dir.path(), 0, 0)
                .await
                .expect("export_frames_to_dir should succeed with GPU");
            // 4 frame PNGs + 1 contact sheet = 5 files.
            assert_eq!(written.len(), 5, "expected 4 frame PNGs + sheet.png");
            for path in &written {
                let bytes = std::fs::read(path).expect("file must exist");
                assert!(
                    bytes.starts_with(PNG_MAGIC),
                    "{} is not a valid PNG",
                    path.display()
                );
            }
            // sheet.png is the last entry.
            assert!(written.last().unwrap().file_name().unwrap() == "sheet.png");
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
