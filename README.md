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
