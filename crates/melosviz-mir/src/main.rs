//! `melosviz-mir` CLI — Rust audio analysis, replaces Python `analyze_wav_rich`.
//!
//! Usage:
//!   melosviz-mir --wav <path> --fps 15 --out spec.json
//!
//! Output: RenderSpec v2 JSON written to `--out` (or stdout if `-`).

use anyhow::{bail, Context, Result};
use clap::Parser;
use melosviz_mir::{
    analyze,
    mir::MirParams,
    wav::load_wav_mono,
};
use std::io::{self, Write};
use std::path::PathBuf;
use std::time::Instant;

#[derive(Parser, Debug)]
#[command(name = "melosviz-mir", version, about = "Rust MIR analysis → RenderSpec v2")]
struct Args {
    /// Input WAV file path.
    #[arg(long)]
    wav: PathBuf,

    /// Dense keyframe rate (frames per second, 10–30).
    #[arg(long, default_value_t = 15)]
    fps: u32,

    /// Output path for RenderSpec v2 JSON. Use `-` for stdout.
    #[arg(long, default_value = "-")]
    out: String,

    /// Print analysis wall time to stderr.
    #[arg(long, default_value_t = false)]
    time: bool,
}

fn main() -> Result<()> {
    env_logger::init();
    let args = Args::parse();

    if !args.wav.exists() {
        bail!("WAV file not found: {}", args.wav.display());
    }

    let t0 = Instant::now();
    let wav = load_wav_mono(&args.wav)
        .with_context(|| format!("loading WAV: {}", args.wav.display()))?;
    let t_load = t0.elapsed();

    eprintln!(
        "melosviz-mir: loaded {:.1} s WAV ({} samples @ {} Hz) in {:.3} s",
        wav.duration_sec,
        wav.samples.len(),
        wav.sample_rate,
        t_load.as_secs_f64()
    );

    let t1 = Instant::now();
    let mut spec = analyze(
        &wav,
        MirParams {
            n_dense_fps: args.fps,
            n_fft: 2048,
            hop_length: 512,
        },
    );
    let t_analyze = t1.elapsed();
    let t_total = t0.elapsed();

    // Patch in the source path.
    spec.metadata.source_audio = args.wav.to_string_lossy().into_owned();

    // Always print timing; --time flag is available for scripting consumers.
    let _ = args.time;
    {
        eprintln!(
            "melosviz-mir: analysis {:.3} s | total {:.3} s | {} dense keyframes | BPM {:.1} | key {}/{}",
            t_analyze.as_secs_f64(),
            t_total.as_secs_f64(),
            spec.dense_keyframes.len(),
            spec.mir.tempo_bpm.unwrap_or(0.0),
            spec.mir.key.as_deref().unwrap_or("?"),
            spec.mir.mode.as_deref().unwrap_or("?"),
        );
    }

    let json = serde_json::to_string_pretty(&spec).context("serialising RenderSpec")?;

    if args.out == "-" {
        let stdout = io::stdout();
        let mut handle = stdout.lock();
        handle.write_all(json.as_bytes()).context("writing JSON to stdout")?;
        handle.write_all(b"\n").ok();
    } else {
        std::fs::write(&args.out, &json)
            .with_context(|| format!("writing JSON to {}", args.out))?;
        eprintln!("melosviz-mir: spec written to {}", args.out);
    }

    Ok(())
}
