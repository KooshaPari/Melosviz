# MelosViz (agent notes)

Spec-first music→visual toolkit: Python bridge/conductor + Electrobun desktop +
R3F web + Rust MIR/wgpu.

## Build & test

```bash
# Backend
cd backend && uv sync --frozen   # or: pip install -e ".[test,lint,bridge]"
ruff check src/ tests/ && ruff format --check src/ tests/
pytest -q

# Bridge
python -m melosviz.bridge.server --port 8765

# Web
cd web && bun install && bun run test && bun run build

# Rust
cargo test --workspace --locked
cargo bench -p melosviz-mir --bench analyzer -- 1s
```

Or use `.devcontainer/devcontainer.json` / `scripts/diagnose.py`.

## Layout

| Path | Role |
|------|------|
| `backend/src/melosviz/` | Python package (analysis, bridge, conductor, cli) |
| `crates/melosviz-mir/` | Rust MIR analyzer |
| `crates/melosviz-render-wgpu/` | wgpu renderer |
| `desktop/` | Electrobun shell |
| `web/` | Vite + R3F UI |
| `eval/` | Golden corpus, Harbor adapter, screenshots |
| `docs/` | Architecture, EVAL, AIRGAP, a11y, WORK_DAG |
| `audit/` | audit-v38 scorecard lanes |
| `fuzz/` | cargo-fuzz + atheris |

## Conventions

- Link PRs to FR IDs (`docs/TRACEABILITY.md`) and claim `docs/WORK_DAG.md` tasks.
- DCO: `git commit -s` (enforced by `.github/workflows/dco.yml`).
- Do not bypass ruff/pytest/cargo-deny gates.
- Prefer tokens (`--mv-*`) over hardcoded hex; see `docs/VISUAL_SPEC.md`.
- Errors from the bridge use `application/problem+json` (RFC 7807-ish).

## Agent pointers

- Product: `SPEC.md`
- Scorecard: `audit/SCORECARD.md`
- Contributor: `CONTRIBUTING.md`
- Global Phenotype: `~/.claude/CLAUDE.md`
