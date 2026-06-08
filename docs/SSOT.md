# SSOT — Melosviz

## State
- Default branch: main
- Last verified: 2026-06-08
- CI status: green (backend + web + sdk-rust)
- Open PRs: 0
- Open branches: 1 (main)
- Stashes: 0

## Dependencies
- Rust: stable
- Node: 20
- Python: 3.12

## Architecture
- Hexagonal: yes (documented, per-component)
- Ports: AudioSource, Renderer, RenderSpec
- Adapters: FastAPI, Web Audio API, Canvas, Tauri
- Domain: Audio analysis, visual generation

## Next Steps (DAG)
1. [x] P0: State unification
2. [x] P1: Tooling + governance (Taskfile, LICENSE, CI, EditorConfig)
3. [x] P2: Hexagonal docs (ARCHITECTURE.md, hexagonal.md)
4. [ ] P3: Implement backend domain (FFT analysis)
5. [ ] P4: Implement web renderer adapter
6. [ ] P5: Add cross-component integration tests

## Fleet Links
- Parent: Phenotype
- Related: Pine (Rust), AgentMCP (Python)
- Consumes: N/A
- Merged into: N/A
