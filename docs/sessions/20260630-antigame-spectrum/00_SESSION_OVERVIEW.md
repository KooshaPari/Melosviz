# Antigame Spectrum Session

## Goal

Add and run the security-spectrum quality gates for Melosviz:

- mutation testing: mutmut for Python, cargo-mutants for Rust
- fuzz testing: Hypothesis plus Atheris harnesses for RenderSpec JSON, WAV parsing, and bridge HTTP payloads
- chaos testing: bridge mid-request failures, missing ffmpeg/blender binaries, malformed RenderSpec payloads
- CI/qgate coverage: SAST, DAST, SBOM, secrets, type/lint checks across Python, Rust, and desktop TypeScript

## Success Criteria

- New tests are checked into focused canonical files.
- Linux CI contains the requested check-spectrum jobs.
- Real local runs are attempted and recorded with honest pass/fail/gap status.
- Branch `test/antigame-spectrum-3` is pushed and a PR is opened without AI attribution.

