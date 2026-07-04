# Testing Strategy

## Added Coverage

- `backend/tests/test_spectrum.py`
  - Hypothesis RenderSpec JSON round-trip and malformed payload checks
  - Hypothesis WAV parser robustness checks
  - Bridge HTTP property checks for invalid paths and malformed JSON
  - Chaos checks for mid-request bridge failures and missing renderer binaries

- `backend/fuzz/`
  - Atheris harnesses for RenderSpec JSON parsing, WAV parsing, and bridge HTTP payloads

## CI Coverage

- Python: pytest, coverage, ruff, mypy
- TypeScript: Bun install plus tsgo typecheck
- Rust: cargo test, clippy
- Security: bandit, semgrep, gitleaks
- DAST: schemathesis against the running bridge OpenAPI schema
- SBOM: syft plus cargo-cyclonedx
- Mutation: bounded mutmut and cargo-mutants runs

