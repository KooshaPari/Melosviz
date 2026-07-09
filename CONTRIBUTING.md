# MelosViz — Contributor Guide

Thanks for contributing. MelosViz is a **spec-first** music-to-visual toolkit
(Python backend + Electrobun desktop + R3F web + Rust MIR/wgpu).

## Quick start

```bash
# Backend
cd backend && pip install -e ".[test,lint,bridge,analysis]"
python -m ruff check src/ tests/
python -m pytest -q

# Bridge
python -m melosviz.bridge.server --port 8765

# Web
cd web && bun install && bun run dev

# Desktop (macOS/Windows host)
cd desktop && bun install && bun run dev
```

Or use the [devcontainer](.devcontainer/devcontainer.json).

## Before you open a PR

1. Link an FR / NFR from [`docs/TRACEABILITY.md`](docs/TRACEABILITY.md) or
   [`docs/functional_requirements.md`](docs/functional_requirements.md).
2. Prefer a task from [`docs/WORK_DAG.md`](docs/WORK_DAG.md).
3. Run locally:
   - `cd backend && ruff check src/ tests/ && ruff format --check src/ tests/`
   - `cd backend && pytest -q`
4. Use the PR template (What / Why / How / Testing).

## Architecture pointers

- Product spec: [`SPEC.md`](SPEC.md)
- Architecture ADR: [`docs/adr/0003-spec-first-conductor.md`](docs/adr/0003-spec-first-conductor.md)
- Layout overview: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Bridge threat model: [`docs/security/BRIDGE_THREAT_MODEL.md`](docs/security/BRIDGE_THREAT_MODEL.md)
- Product threat model: [`docs/security/THREAT_MODEL.md`](docs/security/THREAT_MODEL.md)
- Observability: [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md)
- Packaging: [`docs/PACKAGING.md`](docs/PACKAGING.md)
- Scorecard: [`audit/SCORECARD.md`](audit/SCORECARD.md)

## Code of conduct / security

See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) and [`SECURITY.md`](SECURITY.md).
Report vulnerabilities via GitHub Security Advisories.
