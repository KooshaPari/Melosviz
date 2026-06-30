//! melosviz-render — CLI entry point for the wgpu headless renderer.
//!
//! Usage:
//!   melosviz-render --spec path/to/render_spec.json --output output.mp4
//!   melosviz-render --spec render_spec.json --output preview.mp4 --width 1280 --height 720
//!
//! This binary is a thin CLI wrapper around [`melosviz_render_wgpu::export::export_to_mp4`].
//! It is intended to be called as a subprocess by the MelosViz Python conductor
//! (`viz preview` command) or by the Electrobun desktop app.
//!
//! # Integration with the Python conductor
//!
//! ```python
//! import subprocess, json
//! spec_json = render_spec.model_dump_json()
//! with open('/tmp/melosviz_spec.json', 'w') as f:
//!     f.write(spec_json)
//! result = subprocess.run(
//!     ['melosviz-render', '--spec', '/tmp/melosviz_spec.json', '--output', 'preview.mp4'],
//!     check=True,
//! )
//! ```

use anyhow::Result;
use clap::Parser;
use std::path::PathBuf;

#[derive(Parser, Debug)]
#[command(
    name = "melosviz-render",
    about = "MelosViz wgpu realtime preview renderer",
    version
)]
struct Cli {
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

fn main() -> Result<()> {
    env_logger::init();
    let cli = Cli::parse();

    let spec_json = std::fs::read_to_string(&cli.spec)
        .map_err(|e| anyhow::anyhow!("Cannot read spec file {:?}: {e}", cli.spec))?;
    let spec = melosviz_render_wgpu::spec::RenderSpec::from_json(&spec_json)
        .map_err(|e| anyhow::anyhow!("Invalid RenderSpec JSON: {e}"))?;

    let width = cli.width.unwrap_or(spec.metadata.width).max(1);
    let height = cli.height.unwrap_or(spec.metadata.height).max(1);

    log::info!(
        "melosviz-render: spec={:?} output={:?} {}x{} {}fps {}s ({} frames)",
        cli.spec,
        cli.output,
        width,
        height,
        spec.metadata.fps,
        spec.metadata.duration,
        spec.total_frames(),
    );

    pollster::block_on(async {
        let renderer = melosviz_render_wgpu::renderer::WgpuRenderer::new(width, height).await?;
        let mut cache = melosviz_render_wgpu::segment_cache::SegmentCache::new();
        melosviz_render_wgpu::export::export_to_mp4(&renderer, &spec, &mut cache, &cli.output)
            .await
    })
}
