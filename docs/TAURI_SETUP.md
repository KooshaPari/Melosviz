# Tauri Desktop Shell — Setup Guide

This document describes the minimal Tauri v2 desktop shell that wraps the
Melosviz Python CLI pipeline.

## Directory Layout

```
melosviz/
  src-tauri/              # Tauri Rust backend (this scaffold)
    Cargo.toml
    build.rs
    tauri.conf.json
    src/
      lib.rs              # Tauri commands + app setup
      main.rs             # Binary entry-point
  web/                    # React + Vite frontend (existing)
  backend/                # Python CLI package (existing)
```

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| **Rust** | stable (1.77+) | `rustup update stable` |
| **Node.js** | 18+ | For Vite dev server |
| **Python** | 3.10+ | For the melosviz backend |
| **melosviz** package | installed | `cd backend && pip install -e .` |
| **System deps** | varies | See below |

### macOS

Xcode Command Line Tools are required:

```bash
xcode-select --install
```

No additional system libraries needed beyond what Tauri v2 bundles.

### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y \
  libwebkit2gtk-4.1-dev \
  build-essential \
  curl \
  wget \
  file \
  libxdo-dev \
  libssl-dev \
  libayatana-appindicator3-dev \
  librsvg2-dev
```

### Windows

WebView2 is pre-installed on Windows 10/11. No extra system deps needed
beyond the MSVC build tools (`rustup` will prompt to install them).

## Development

### 1. Install Python backend

```bash
cd backend
pip install -e .
```

Verify: `viz --help` should print the CLI help.

### 2. Install web frontend deps

```bash
cd web
npm install
```

### 3. Add Tauri API to frontend (optional, for invoke calls)

```bash
cd web
npm install @tauri-apps/api
```

### 4. Run in dev mode

From the repo root:

```bash
cd src-tauri
cargo tauri dev
```

This will:
1. Start the Vite dev server (`npm run dev` in `web/`)
2. Open a native window pointed at `http://localhost:5173`
3. Hot-reload the frontend on code changes

### 5. Available Tauri commands from the frontend

```typescript
import { invoke } from '@tauri-apps/api/core';

// Run a pipeline sub-command
const result = await invoke('run_pipeline', {
  concept: 'neon cityscape',
  wavPath: '/path/to/audio.wav',
  subCommand: 'render',  // optional, defaults to 'render'
});

// Check status
const status = await invoke('get_status');
```

## Production Build

```bash
cd src-tauri
cargo tauri build
```

This produces:
- **macOS**: `.dmg` and `.app` in `src-tauri/target/release/bundle/`
- **Linux**: `.deb` and `.AppImage`
- **Windows**: `.msi` and `.exe` installer

## How It Works

The desktop shell is a thin native wrapper:

1. **Frontend** (React + Vite) renders the UI and calls Tauri `invoke()`
2. **Rust backend** (`lib.rs`) receives those calls via `#[tauri::command]`
3. Commands shell out to the Python CLI (`viz` or `python3 -m melosviz.cli.main`)
4. Stdout/stderr and exit codes flow back to the frontend as JSON

The Python backend must be installed and available on `$PATH` for the
desktop app to function. In production builds, you may want to bundle
the Python environment (see PyInstaller/PyOxidizer docs for options).

## Architecture Notes

- **src-tauri is excluded from the root Cargo workspace** to avoid
  dependency conflicts with the existing Rust crates (`melosviz-demo`,
  `melosviz-mir`, `melosviz-render-wgpu`).
- The `#[cfg_attr(mobile, tauri::mobile_entry_point)]` attribute on
  `lib.rs::run()` enables future mobile targets without changes.
- `PipelineStatus` is held in-process via Tauri's state management;
  it resets when the app window is closed.
