use serde::{Deserialize, Serialize};
use std::process::Command;
use tauri::State;

// ---------------------------------------------------------------------------
// Pipeline status tracker (in-memory, per-window lifetime)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PipelineStatus {
    pub running: bool,
    pub last_exit_code: Option<i32>,
    pub last_stdout: String,
    pub last_stderr: String,
    pub last_command: Option<String>,
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

/// Run a melosviz CLI sub-command.
///
/// `concept` is passed as the `--concept` flag (used by `storyboard`).
/// `wav_path` is the positional WAV argument common to most sub-commands.
/// `sub_command` selects which CLI verb to invoke (default: `"render"`).
#[tauri::command]
async fn run_pipeline(
    concept: String,
    wav_path: String,
    sub_command: Option<String>,
    status: State<'_, std::sync::Mutex<PipelineStatus>>,
) -> Result<PipelineStatus, String> {
    let cmd_name = sub_command.unwrap_or_else(|| "render".to_string());

    // Build the CLI invocation.  `viz` is the console-script entry-point
    // installed by the `melosviz` Python package.
    let mut args: Vec<String> = vec![cmd_name.clone(), wav_path.clone()];
    if !concept.is_empty() {
        args.push("--concept".into());
        args.push(concept);
    }

    // Mark running
    {
        let mut s = status.lock().map_err(|e| e.to_string())?;
        s.running = true;
        s.last_command = Some(format!("viz {}", args.join(" ")));
        s.last_stdout.clear();
        s.last_stderr.clear();
    }

    // Try `viz` first (installed console-script), fall back to
    // `python -m melosviz.cli.main`.
    let output = match Command::new("viz").args(&args).output() {
        Ok(o) => o,
        Err(_) => {
            // Fallback: invoke via Python module
            let mut py_args = vec!["-m", "melosviz.cli.main"];
            py_args.extend(args.iter().map(String::as_str));
            Command::new("python3")
                .args(&py_args)
                .output()
                .map_err(|e| format!("Failed to launch melosviz CLI: {e}"))?
        }
    };

    let exit_code = output.status.code().unwrap_or(-1);
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();

    let result = {
        let mut s = status.lock().map_err(|e| e.to_string())?;
        s.running = false;
        s.last_exit_code = Some(exit_code);
        s.last_stdout = stdout;
        s.last_stderr = stderr;
        s.clone()
    };

    if exit_code != 0 {
        return Err(format!(
            "CLI exited with code {exit_code}:\n{}",
            result.last_stderr
        ));
    }

    Ok(result)
}

/// Return the current pipeline status without running anything.
#[tauri::command]
async fn get_status(
    status: State<'_, std::sync::Mutex<PipelineStatus>>,
) -> Result<PipelineStatus, String> {
    status
        .lock()
        .map(|s| s.clone())
        .map_err(|e| e.to_string())
}

// ---------------------------------------------------------------------------
// App entry-point
// ---------------------------------------------------------------------------

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(std::sync::Mutex::new(PipelineStatus::default()))
        .invoke_handler(tauri::generate_handler![run_pipeline, get_status])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
