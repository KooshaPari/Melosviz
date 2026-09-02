//! `melosviz-demo`: zero-dependency end-to-end fixture binary.
//!
//! Creates a 6-second silent wav at the chosen output directory, invokes the
//! installed `melosviz.cli.main` storyboard -> generate -> ship pipeline, and
//! prints a JSON artifact summary. Replacement for `scripts/demo_offline.sh`.
//!
//! Flags:
//!   --out-dir <path>     output directory (default: ./melosviz-demo-out)
//!   --concept <text>     prompt concept (default: "neon city")
//!   --bpm <float>        beats per minute (default: 124.0)
//!   --duration-secs <f>  test wav duration (default: 6.0)
//!   --verbose            stream subprocess output to stderr
//!
//! Exit code is 0 on a complete pipeline (storyboard.json + final.zip both
//! exist), non-zero with a diagnostic message otherwise.

use std::env;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use serde::Serialize;
use sha2::{Digest, Sha256};

#[derive(Debug, serde::Serialize, serde::Deserialize, Clone)]
struct ArtifactEntry {
    relpath: String,
    sha256: String,
    bytes: u64,
}

#[derive(Serialize)]
struct DemoReport {
    out_dir: String,
    concept: String,
    bpm: f32,
    duration_secs: f32,
    storyboard: Option<ArtifactEntry>,
    scene_count: usize,
    deliverables: Vec<ArtifactEntry>,
    final_zip: Option<ArtifactEntry>,
    bundle_sha256sums: Option<String>,
    elapsed_secs: f32,
    success: bool,
    steps: Vec<StepRecord>,
}

#[derive(Serialize)]
struct StepRecord {
    name: String,
    cmd: String,
    exit_code: i32,
    duration_secs: f32,
    stdout_tail: String,
}

fn main() {
    let args = collect_args();
    if let Err(msg) = run(&args) {
        eprintln!("melosviz-demo: error: {msg}");
        std::process::exit(1);
    }
}

#[derive(Debug)]
struct Args {
    out_dir: PathBuf,
    concept: String,
    bpm: f32,
    duration_secs: f32,
    verbose: bool,
}

fn collect_args() -> Args {
    let mut out_dir = env::current_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join("melosviz-demo-out");
    let mut concept = "neon city".to_string();
    let mut bpm: f32 = 124.0;
    let mut duration_secs: f32 = 6.0;
    let mut verbose = false;
    let mut it = env::args().skip(1);
    while let Some(arg) = it.next() {
        match arg.as_str() {
            "--out-dir" => {
                out_dir = PathBuf::from(it.next().expect("--out-dir requires a value"));
            }
            "--concept" => {
                concept = it.next().expect("--concept requires a value");
            }
            "--bpm" => {
                bpm = it
                    .next()
                    .expect("--bpm requires a value")
                    .parse()
                    .expect("--bpm must be a float");
            }
            "--duration-secs" => {
                duration_secs = it
                    .next()
                    .expect("--duration-secs requires a value")
                    .parse()
                    .expect("--duration-secs must be a float");
            }
            "--verbose" | "-v" => {
                verbose = true;
            }
            "--help" | "-h" => {
                print_help();
                std::process::exit(0);
            }
            other => {
                eprintln!("melosviz-demo: unknown flag: {other}");
                std::process::exit(2);
            }
        }
    }
    Args {
        out_dir,
        concept,
        bpm,
        duration_secs,
        verbose,
    }
}

fn print_help() {
    eprintln!(
        "melosviz-demo: zero-dep end-to-end fixture\n\
         \n\
         Usage: melosviz-demo [flags]\n\
         \n\
         Flags:\n\
           --out-dir <path>     output directory (default: ./melosviz-demo-out)\n\
           --concept <text>     prompt concept (default: \"neon city\")\n\
           --bpm <float>        beats per minute (default: 124.0)\n\
           --duration-secs <f>  test wav duration in seconds (default: 6.0)\n\
           --verbose, -v        stream subprocess output to stderr\n\
           --help, -h           print this message"
    );
}

fn run(args: &Args) -> Result<(), String> {
    let started = std::time::Instant::now();
    let out_dir = &args.out_dir;
    fs::create_dir_all(out_dir).map_err(|e| format!("create_dir_all({}): {e}", out_dir.display()))?;

    let wav_path = out_dir.join("track.wav");
    write_silent_wav(&wav_path, args.duration_secs)?;

    let env_offline = [("MELOSVIZ_COMFYUI_OFFLINE", "1")];

    // Step 1: storyboard
    let storyboard_path = out_dir.join("storyboard.json");
    let storyboard_step = run_step(
        "storyboard",
        &[
            "-m",
            "melosviz.cli.main",
            "storyboard",
            wav_path.to_str().unwrap(),
            "--concept",
            &args.concept,
            "--bpm",
            &args.bpm.to_string(),
            "--out",
            storyboard_path.to_str().unwrap(),
        ],
        &env_offline,
        args.verbose,
    )?;
    if !storyboard_path.exists() {
        return Err(format!(
            "storyboard step succeeded but {} was not produced",
            storyboard_path.display()
        ));
    }

    // Step 2: generate
    let gen_dir = out_dir.join("generate");
    let generate_step = run_step(
        "generate",
        &[
            "-m",
            "melosviz.cli.main",
            "generate",
            wav_path.to_str().unwrap(),
            "--storyboard",
            storyboard_path.to_str().unwrap(),
            "--out",
            gen_dir.to_str().unwrap(),
        ],
        &env_offline,
        args.verbose,
    )?;

    // Step 3: ship
    let ship_step = run_step(
        "ship",
        &[
            "-m",
            "melosviz.cli.main",
            "ship",
            gen_dir.to_str().unwrap(),
        ],
        &env_offline,
        args.verbose,
    )?;

    let storyboard_entry = hash_artifact(&storyboard_path, "storyboard.json")?;
    let deliverables_dir = gen_dir.join("deliverables");
    let mut deliverables: Vec<ArtifactEntry> = Vec::new();
    if deliverables_dir.is_dir() {
        collect_artifacts(&deliverables_dir, &deliverables_dir, &mut deliverables)?;
    }
    let mut final_zip_entry: Option<ArtifactEntry> = None;
    for entry in fs::read_dir(&gen_dir)
        .map_err(|e| format!("read_dir({}): {e}", gen_dir.display()))?
    {
        let entry = entry.map_err(|e| format!("read_dir entry: {e}"))?;
        let p = entry.path();
        if p.extension().and_then(|s| s.to_str()) == Some("zip") {
            let name = p.file_name().unwrap().to_str().unwrap().to_string();
            final_zip_entry = Some(hash_artifact(&p, &name)?);
        }
    }

    let scene_count = count_scenes(&gen_dir);

    let report = DemoReport {
        out_dir: out_dir.display().to_string(),
        concept: args.concept.clone(),
        bpm: args.bpm,
        duration_secs: args.duration_secs,
        storyboard: Some(storyboard_entry),
        scene_count,
        deliverables,
        final_zip: final_zip_entry.clone(),
        bundle_sha256sums: None,
        elapsed_secs: started.elapsed().as_secs_f32(),
        success: final_zip_entry.is_some() && ship_step.exit_code == 0,
        steps: vec![storyboard_step, generate_step, ship_step],
    };

    println!(
        "{}",
        serde_json::to_string_pretty(&report).map_err(|e| format!("serialize report: {e}"))?
    );
    Ok(())
}

fn write_silent_wav(path: &Path, duration_secs: f32) -> Result<(), String> {
    let sample_rate: u32 = 22050;
    let channels: u16 = 1;
    let bits_per_sample: u16 = 16;
    let total_samples = (sample_rate as f32 * duration_secs) as u32;
    let byte_rate = sample_rate * u32::from(channels) * u32::from(bits_per_sample) / 8;
    let block_align = channels * bits_per_sample / 8;
    let data_size = total_samples * u32::from(block_align);
    let chunk_size = 36 + data_size;
    let mut f = fs::File::create(path).map_err(|e| format!("create wav {}: {e}", path.display()))?;
    f.write_all(b"RIFF").map_err(|e| e.to_string())?;
    f.write_all(&chunk_size.to_le_bytes())
        .map_err(|e| e.to_string())?;
    f.write_all(b"WAVE").map_err(|e| e.to_string())?;
    f.write_all(b"fmt ").map_err(|e| e.to_string())?;
    f.write_all(&16u32.to_le_bytes())
        .map_err(|e| e.to_string())?;
    f.write_all(&1u16.to_le_bytes())
        .map_err(|e| e.to_string())?;
    f.write_all(&channels.to_le_bytes())
        .map_err(|e| e.to_string())?;
    f.write_all(&sample_rate.to_le_bytes())
        .map_err(|e| e.to_string())?;
    f.write_all(&byte_rate.to_le_bytes())
        .map_err(|e| e.to_string())?;
    f.write_all(&block_align.to_le_bytes())
        .map_err(|e| e.to_string())?;
    f.write_all(&bits_per_sample.to_le_bytes())
        .map_err(|e| e.to_string())?;
    f.write_all(b"data").map_err(|e| e.to_string())?;
    f.write_all(&data_size.to_le_bytes())
        .map_err(|e| e.to_string())?;
    let zeros = vec![0u8; 4096];
    let mut remaining = data_size as usize;
    while remaining > 0 {
        let n = remaining.min(zeros.len());
        f.write_all(&zeros[..n]).map_err(|e| e.to_string())?;
        remaining -= n;
    }
    Ok(())
}

fn run_step(
    name: &str,
    sub_args: &[&str],
    env_overrides: &[(&str, &str)],
    verbose: bool,
) -> Result<StepRecord, String> {
    let started = std::time::Instant::now();
    let mut cmd = Command::new("python3");
    cmd.args(sub_args);
    for (k, v) in env_overrides {
        cmd.env(k, v);
    }
    if verbose {
        cmd.stdout(Stdio::inherit());
        cmd.stderr(Stdio::inherit());
    } else {
        cmd.stdout(Stdio::piped());
        cmd.stderr(Stdio::piped());
    }
    let output = cmd
        .output()
        .map_err(|e| format!("{name}: failed to spawn python3 ({e})"))?;
    let duration_secs = started.elapsed().as_secs_f32();
    let stdout_tail = String::from_utf8_lossy(&output.stdout)
        .chars()
        .rev()
        .take(280)
        .collect::<String>()
        .chars()
        .rev()
        .collect::<String>();
    let cmd_str = format!("python3 {}", sub_args.join(" "));
    Ok(StepRecord {
        name: name.to_string(),
        cmd: cmd_str,
        exit_code: output.status.code().unwrap_or(-1),
        duration_secs,
        stdout_tail,
    })
}

fn hash_artifact(path: &Path, relpath: &str) -> Result<ArtifactEntry, String> {
    let bytes = fs::read(path).map_err(|e| format!("read {}: {e}", path.display()))?;
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    Ok(ArtifactEntry {
        relpath: relpath.to_string(),
        sha256: hex::encode(hasher.finalize()),
        bytes: bytes.len() as u64,
    })
}

fn collect_artifacts(
    root: &Path,
    current: &Path,
    out: &mut Vec<ArtifactEntry>,
) -> Result<(), String> {
    if current.is_file() {
        let rel = current
            .strip_prefix(root)
            .unwrap_or(current)
            .display()
            .to_string();
        out.push(hash_artifact(current, &rel)?);
    } else if current.is_dir() {
        for entry in fs::read_dir(current).map_err(|e| format!("read_dir: {e}"))? {
            let entry = entry.map_err(|e| format!("read_dir entry: {e}"))?;
            collect_artifacts(root, &entry.path(), out)?;
        }
    }
    Ok(())
}

fn count_scenes(gen_dir: &Path) -> usize {
    let mut count = 0;
    if let Ok(entries) = fs::read_dir(gen_dir) {
        for entry in entries.flatten() {
            let p = entry.path();
            if p.is_dir()
                && p.file_name()
                    .and_then(|s| s.to_str())
                    .map(|s| s.starts_with("scene_") || s.starts_with("scene-"))
                    .unwrap_or(false)
            {
                count += 1;
            }
        }
    }
    count
}