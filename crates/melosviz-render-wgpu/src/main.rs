//! melosviz-render — CLI entry point for the wgpu headless renderer.
//!
//! # Subcommands
//!
//! ## `render-mp4` (default / legacy)
//!   Render all frames of a RenderSpec to an MP4 via ffmpeg.
//!
//!   ```text
//!   melosviz-render render-mp4 --spec path/to/spec.json --output out.mp4
//!   melosviz-render render-mp4 --spec spec.json --output out.mp4 --width 1280 --height 720
//!   ```
//!
//! ## `export-frame`  ← B18: Python bridge entry point
//!   Render a **single frame** from a RenderSpec and write raw RGBA bytes
//!   (`width × height × 4`) to **stdout**.  The Python bridge
//!   (`melosviz.render.wgpu_adapter`) calls this subcommand to obtain a
//!   rendered frame without the ffmpeg dependency.
//!
//!   ```text
//!   melosviz-render export-frame --spec spec.json --frame 0
//!   melosviz-render export-frame --spec spec.json --frame 42 --width 320 --height 240
//!   ```
//!
//!   Output: raw RGBA bytes written to stdout (no header/framing).
//!   Errors: written to stderr; exit code 1.
//!
//! ## `export-png` ← T2I "see-it" lane: single viewable PNG
//!   Render one frame from a RenderSpec and write a PNG the operator can open
//!   directly (no raw bytes, no ffmpeg).
//!
//!   ```text
//!   melosviz-render export-png --spec spec.json --frame 0 --out frame0.png
//!   open frame0.png
//!   ```
//!
//! ## `demo-frames` ← T2I "see-it" lane: frame sequence + contact sheet
//!   Render a range of frames, write each as a numbered PNG in `--out-dir`,
//!   and write a horizontal contact-sheet `sheet.png` in the same directory.
//!
//!   ```text
//!   melosviz-render demo-frames --spec spec.json \
//!       --frame-start 0 --frame-end 30 --out-dir demo_out/
//!   open demo_out/sheet.png
//!   ```
//!
//! # Python integration
//!
//! ```python
//! import subprocess, json, tempfile, pathlib
//! spec_json = render_spec.model_dump_json()
//! with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
//!     f.write(spec_json)
//!     spec_path = f.name
//! result = subprocess.run(
//!     ["melosviz-render", "export-frame", "--spec", spec_path, "--frame", "0"],
//!     capture_output=True,
//!     check=True,
//! )
//! rgba_bytes = result.stdout  # width * height * 4 raw RGBA bytes
//! ```

use anyhow::Result;
use clap::{Parser, Subcommand};
use std::io::Write as _;
use std::path::PathBuf;

#[derive(Parser, Debug)]
#[command(
    name = "melosviz-render",
    about = "MelosViz wgpu headless renderer",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]
enum Commands {
    /// Render a RenderSpec to an MP4 via ffmpeg rawvideo pipe.
    RenderMp4(RenderMp4Args),
    /// Render one frame from a RenderSpec; write raw RGBA bytes to stdout.
    ///
    /// This is the Python bridge entry point (B18).  The Python side calls:
    ///   melosviz-render export-frame --spec <path> --frame <N>
    /// and reads `width × height × 4` RGBA bytes from stdout.
    ExportFrame(ExportFrameArgs),
    /// Render one frame and write a viewable PNG file (T2I see-it lane).
    ///
    ///   melosviz-render export-png --spec spec.json --frame 0 --out frame0.png
    ///   open frame0.png
    ExportPng(ExportPngArgs),
    /// Render a frame range to numbered PNGs + a contact-sheet (T2I see-it lane).
    ///
    ///   melosviz-render demo-frames --spec spec.json \
    ///       --frame-start 0 --frame-end 30 --out-dir demo_out/
    ///   open demo_out/sheet.png
    DemoFrames(DemoFramesArgs),
}

#[derive(Parser, Debug)]
struct RenderMp4Args {
    /// Path to a RenderSpec v2 JSON file.
    #[arg(short, long)]
    spec: PathBuf,

    /// Output MP4 path.
    #[arg(short, long, default_value = "melosviz-preview.mp4")]
    output: PathBuf,

    /// Override output width (default: from spec metadata).
    #[arg(long)]
    width: Option<u32>,

    /// Override output height (default: from spec metadata).
    #[arg(long)]
    height: Option<u32>,
}

#[derive(Parser, Debug)]
struct ExportFrameArgs {
    /// Path to a RenderSpec v2 JSON file.
    #[arg(short, long)]
    spec: PathBuf,

    /// Frame index to render (0-based; defaults to 0).
    #[arg(long, default_value_t = 0)]
    frame: u32,

    /// Override output width (default: from spec metadata).
    #[arg(long)]
    width: Option<u32>,

    /// Override output height (default: from spec metadata).
    #[arg(long)]
    height: Option<u32>,
}

#[derive(Parser, Debug)]
struct ExportPngArgs {
    /// Path to a RenderSpec v2 JSON file.
    #[arg(short, long)]
    spec: PathBuf,

    /// Frame index to render (0-based; defaults to 0).
    #[arg(long, default_value_t = 0)]
    frame: u32,

    /// Output PNG path.
    #[arg(long, default_value = "frame0.png")]
    out: PathBuf,

    /// Override output width (default: from spec metadata).
    #[arg(long)]
    width: Option<u32>,

    /// Override output height (default: from spec metadata).
    #[arg(long)]
    height: Option<u32>,
}

#[derive(Parser, Debug)]
struct DemoFramesArgs {
    /// Path to a RenderSpec v2 JSON file.
    #[arg(short, long)]
    spec: PathBuf,

    /// First frame to render (0-based, inclusive; default 0).
    #[arg(long, default_value_t = 0)]
    frame_start: u32,

    /// Last frame to render (exclusive; default 30).
    #[arg(long, default_value_t = 30)]
    frame_end: u32,

    /// Output directory for numbered PNGs and sheet.png.
    #[arg(long, default_value = "demo_out")]
    out_dir: PathBuf,

    /// Contact-sheet thumbnail width per frame (0 = auto: frame_width/8).
    #[arg(long, default_value_t = 0)]
    thumb_width: u32,

    /// Contact-sheet thumbnail height per frame (0 = auto: frame_height/8).
    #[arg(long, default_value_t = 0)]
    thumb_height: u32,
}

fn main() -> Result<()> {
    env_logger::init();
    let cli = Cli::parse();

    match cli.command {
        Commands::RenderMp4(args) => run_render_mp4(args),
        Commands::ExportFrame(args) => run_export_frame(args),
        Commands::ExportPng(args) => run_export_png(args),
        Commands::DemoFrames(args) => run_demo_frames(args),
    }
}

fn run_render_mp4(args: RenderMp4Args) -> Result<()> {
    let spec_json = std::fs::read_to_string(&args.spec)
        .map_err(|e| anyhow::anyhow!("Cannot read spec file {:?}: {e}", args.spec))?;
    let spec = melosviz_render_wgpu::spec::RenderSpec::from_json(&spec_json)
        .map_err(|e| anyhow::anyhow!("Invalid RenderSpec JSON: {e}"))?;

    let width = args.width.unwrap_or(spec.metadata.width).max(1);
    let height = args.height.unwrap_or(spec.metadata.height).max(1);

    log::info!(
        "melosviz-render render-mp4: spec={:?} output={:?} {}x{} {}fps {}s ({} frames)",
        args.spec,
        args.output,
        width,
        height,
        spec.metadata.fps,
        spec.metadata.duration,
        spec.total_frames(),
    );

    pollster::block_on(async {
        let renderer = melosviz_render_wgpu::renderer::WgpuRenderer::new(width, height).await?;
        let mut cache = melosviz_render_wgpu::segment_cache::SegmentCache::new();
        melosviz_render_wgpu::export::export_to_mp4(&renderer, &spec, &mut cache, &args.output)
            .await
    })
}

fn run_export_frame(args: ExportFrameArgs) -> Result<()> {
    let spec_json = std::fs::read_to_string(&args.spec)
        .map_err(|e| anyhow::anyhow!("Cannot read spec file {:?}: {e}", args.spec))?;
    let spec = melosviz_render_wgpu::spec::RenderSpec::from_json(&spec_json)
        .map_err(|e| anyhow::anyhow!("Invalid RenderSpec JSON: {e}"))?;

    let width = args.width.unwrap_or(spec.metadata.width).max(1);
    let height = args.height.unwrap_or(spec.metadata.height).max(1);
    let frame_idx = args.frame;

    log::info!(
        "melosviz-render export-frame: spec={:?} frame={} {}x{}",
        args.spec,
        frame_idx,
        width,
        height,
    );

    let rgba_bytes = pollster::block_on(async {
        // Build per-frame uniforms from the spec timeline.
        let timeline = melosviz_render_wgpu::timeline::Timeline::from_spec(&spec);
        let uniforms = timeline.sample(frame_idx).with_frame_index(frame_idx);
        melosviz_render_wgpu::export::export_frame_bytes(width, height, &uniforms).await
    })?;

    // Write raw RGBA bytes to stdout — the Python bridge reads these directly.
    std::io::stdout()
        .write_all(&rgba_bytes)
        .map_err(|e| anyhow::anyhow!("Failed to write RGBA bytes to stdout: {e}"))?;

    log::info!(
        "export-frame: wrote {} bytes ({width}x{height} RGBA) to stdout",
        rgba_bytes.len()
    );
    Ok(())
}

fn run_export_png(args: ExportPngArgs) -> Result<()> {
    let spec_json = std::fs::read_to_string(&args.spec)
        .map_err(|e| anyhow::anyhow!("Cannot read spec file {:?}: {e}", args.spec))?;
    let spec = melosviz_render_wgpu::spec::RenderSpec::from_json(&spec_json)
        .map_err(|e| anyhow::anyhow!("Invalid RenderSpec JSON: {e}"))?;

    let width = args.width.unwrap_or(spec.metadata.width).max(1);
    let height = args.height.unwrap_or(spec.metadata.height).max(1);
    let frame_idx = args.frame;

    log::info!(
        "melosviz-render export-png: spec={:?} frame={} {}x{} out={:?}",
        args.spec,
        frame_idx,
        width,
        height,
        args.out,
    );

    pollster::block_on(async {
        let timeline = melosviz_render_wgpu::timeline::Timeline::from_spec(&spec);
        let uniforms = timeline.sample(frame_idx).with_frame_index(frame_idx);
        melosviz_render_wgpu::export::export_frame_to_png(width, height, &uniforms, &args.out).await
    })?;

    eprintln!("Wrote: {}", args.out.display());
    Ok(())
}

fn run_demo_frames(args: DemoFramesArgs) -> Result<()> {
    let spec_json = std::fs::read_to_string(&args.spec)
        .map_err(|e| anyhow::anyhow!("Cannot read spec file {:?}: {e}", args.spec))?;
    let spec = melosviz_render_wgpu::spec::RenderSpec::from_json(&spec_json)
        .map_err(|e| anyhow::anyhow!("Invalid RenderSpec JSON: {e}"))?;

    log::info!(
        "melosviz-render demo-frames: spec={:?} frames={}..{} out-dir={:?}",
        args.spec,
        args.frame_start,
        args.frame_end,
        args.out_dir,
    );

    let written = pollster::block_on(async {
        melosviz_render_wgpu::export::export_frames_to_dir(
            &spec,
            args.frame_start,
            args.frame_end,
            &args.out_dir,
            args.thumb_width,
            args.thumb_height,
        )
        .await
    })?;

    eprintln!(
        "Wrote {} files to {}:",
        written.len(),
        args.out_dir.display()
    );
    for p in &written {
        eprintln!("  {}", p.display());
    }
    if let Some(sheet) = written
        .iter()
        .find(|p| p.file_name().is_some_and(|n| n == "sheet.png"))
    {
        eprintln!("\nSee-it: open {}", sheet.display());
    }
    Ok(())
}
