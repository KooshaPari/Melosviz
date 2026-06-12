<!-- AI-DD-META:START -->
<!-- This repository is planned, maintained, and managed by AI Agents only. -->
<!-- Slop issues are expected and intentionally present as part of an HITL-less -->
<!-- /minimized AI-DD metaproject of learning, refining, and building brute-force -->
<!-- training for both agents and the human operator. -->
![Downloads](https://img.shields.io/github/downloads/KooshaPari/Melosviz/total?style=flat-square&label=downloads&color=blue)
![GitHub release](https://img.shields.io/github/v/release/KooshaPari/Melosviz?style=flat-square&label=release)
![License](https://img.shields.io/github/license/KooshaPari/Melosviz?style=flat-square)
![AI-Slop](https://img.shields.io/badge/AI--DD-Slop%20Expected-orange?style=flat-square)
![AI-Only-Maintained](https://img.shields.io/badge/Planned%20%26%20Maintained%20by-AI%20Agents%20Only-red?style=flat-square)
![HITL-less](https://img.shields.io/badge/HITL--less%20AI--DD-metaproject-yellow?style=flat-square)

> ⚠️ **AI-Agent-Only Repository**
>
> This repo is **planned, maintained, and managed exclusively by AI Agents**.
> Slop issues, rough edges, and AI artifacts are **expected and intentionally
> present** as part of an **HITL-less / minimized AI-DD** metaproject focused
> on learning, refining, and brute-force training both the agents and the
> human operator. Bug reports and contributions are still welcome, but please
> expect AI-generated code, comments, and documentation throughout.
<!-- AI-DD-META:END -->
# Melosviz

**Music-to-visual generation toolkit.**

A multi-component project for analyzing audio and rendering visual content from musical input.

## Components

| Path        | Stack                                | Purpose                                      |
| ----------- | ------------------------------------ | -------------------------------------------- |
| `backend/`  | Python (FastAPI, numpy, pydantic)    | REST API, audio analysis, render specs       |
| `desktop/`  | Tauri + Electrobun                   | Native desktop shell for Melosviz            |
| `sdk/`      | Python + Rust client libraries       | Embeddable SDKs for analysis + render        |
| `web/`      | TypeScript / Vite                    | Browser-based UI                              |

## Status

Initial scaffold. See `backend/src/melosviz.egg-info/PKG-INFO` for the published Python package manifest.

## Development

```sh
# Backend (Python)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Desktop
cd desktop
# Tauri: cd src-tauri && cargo build
# Electrobun: cd electrobun && bun install

# SDK (Python)
cd sdk/python
pip install -e ".[dev]"

# SDK (Rust)
cd sdk/rust
cargo build

# Web
cd web
npm install
npm run dev
```

## License

TBD
