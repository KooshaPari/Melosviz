# Research

## Codebase Findings

- The backend package is dependency-light and keeps bridge dependencies optional via `melosviz[bridge]`.
- `melosviz.bridge.server` exposes `/health`, `/analyze`, `/build`, and `/render` through a small FastAPI app.
- `RenderSpec` is a Pydantic v2 model with permissive renderer-agnostic JSON fields.
- Existing qgate coverage lives mostly in `backend/tests/test_qgate_backfill.py`, which is already oversized. New spectrum coverage should stay in focused files.
- Existing CI already runs pytest coverage, ruff, Bandit high/critical checks, bridge e2e, and qgate.

## Tooling Decisions

- Use `hypothesis` for deterministic property fuzzing in pytest.
- Provide `atheris` entrypoints under `backend/fuzz/` so coverage-guided fuzzing can run locally or in CI with bounded `-runs`.
- Use `schemathesis` against FastAPI's generated `/openapi.json` for bridge DAST.
- Use `syft` for repository SBOM and `cargo cyclonedx` for Rust workspace SBOM.
- Use `mutmut` with a bounded module subset in CI and full local runs when practical.
- Use `cargo-mutants` with workspace-level test execution and timeout limits.

