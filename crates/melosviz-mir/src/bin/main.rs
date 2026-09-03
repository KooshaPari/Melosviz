// melosviz-mir CLI binary — thin wrapper around the library.
//
// Usage:
//   melosviz-mir --wav input.wav --out spec.json --fps 30

use std::path::PathBuf;

fn main() {
    let mut args = std::env::args().skip(1);
    let mut wav: Option<PathBuf> = None;
    let mut out: Option<PathBuf> = None;
    let mut fps: f64 = 30.0;

    while let Some(a) = args.next() {
        match a.as_str() {
            "--wav" => wav = args.next().map(PathBuf::from),
            "--out" => out = args.next().map(PathBuf::from),
            "--fps" => {
                fps = match args.next().and_then(|v| v.parse::<f64>().ok()) {
                    Some(v) if v.is_finite() && v > 0.0 => v,
                    _ => {
                        eprintln!("error: --fps must be a positive number");
                        std::process::exit(2);
                    }
                };
            }
            "-h" | "--help" => {
                eprintln!("melosviz-mir --wav <path> --out <path> [--fps N]");
                std::process::exit(0);
            }
            other => {
                eprintln!("warning: ignoring unknown arg {other}");
            }
        }
    }

    let wav = match wav {
        Some(p) => p,
        None => {
            eprintln!("error: --wav <path> is required");
            std::process::exit(2);
        }
    };
    let out = match out {
        Some(p) => p,
        None => {
            eprintln!("error: --out <path> is required");
            std::process::exit(2);
        }
    };

    let payload = match melosviz_mir::analyze_wav(&wav, fps) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("error: failed to analyze {wav:?}: {e}");
            std::process::exit(1);
        }
    };

    let text = match serde_json::to_string_pretty(&payload) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("error: serialization failed: {e}");
            std::process::exit(1);
        }
    };

    if let Err(e) = std::fs::write(&out, text) {
        eprintln!("error: failed to write {out:?}: {e}");
        std::process::exit(1);
    }
}
