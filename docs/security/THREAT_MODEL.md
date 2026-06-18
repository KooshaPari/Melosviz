---
title: "Threat Model"
version: 0.1.0
lastUpdated: 2026-06-16
---

# Threat Model

> **Source of truth:** Melosviz (Music-to-visual generation toolkit: FastAPI backend, desktop (Tauri/Electrobun), Python + Rust SDKs, web client)
> **Scope:** Audio input pipeline, music analysis models, code-gen backends, web client, desktop binary, distribution

## Assets

1. **Audio input files** — User-provided audio (`.wav`, `.mp3`, `.flac`). If logged or cached without redaction, may leak private recordings.
2. **Music analysis models** — ONNX/Whisper/MIDI-extractor checkpoints. If mutable, an attacker can ship a model that produces biased or manipulated analyses.
3. **Code-gen backends (Tauri/Electrobun)** — Desktop app shells. If compromised, the shell can wrap any analysis in arbitrary code.
4. **Web client bundles** — JS bundles served to users. Supply-chain attack via a compromised dep can inject malicious JS into every web session.
5. **User auth tokens** — Bearer tokens for the FastAPI backend. If leaked, an adversary can drive the API on behalf of the user.

## Threats (STRIDE)

| Category | Threat | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **Spoofing** | An attacker publishes a Melosviz desktop binary under a similar download URL (typosquat). | Medium | High | Releases are signed (cosign, keyless). The download page HSTS-preloads. README documents the canonical install paths (cargo install, brew, etc.). |
| **Tampering** | An analysis model checkpoint is replaced with a backdoored one in a release artifact. | Low | High | All ONNX checkpoints are content-addressed by SHA-256. The download script verifies the checksum on every fetch. Models are pinned to specific versions in `pyproject.toml` / `Cargo.toml`. |
| **Repudiation** | A contributor pushes a model swap and later denies it. | Low | Medium | All commits are signed (gitsign, keyless). Releases are tagged. The git history is the audit trail. |
| **Information Disclosure** | User-provided audio is uploaded to the FastAPI backend and persisted to a cache or training set. | High | High | The FastAPI backend has a "no-retention" mode (default) that streams audio through the analysis pipeline and discards the buffer. Cache files use `0600` permissions and are opt-in. |
| **Denial of Service** | A malicious or oversized audio file (10GB WAV) causes the FastAPI backend to OOM. | Medium | Medium | FastAPI enforces `max-upload-bytes=100MB` and a `request-timeout=120s`. Inputs over the limit return a clear error. |
| **Elevation of Privilege** | A malicious Python or Rust dependency in the workspace executes arbitrary code at build time. | Low | Critical | `Cargo.lock` and `poetry.lock` / `requirements.txt` are committed. CI uses `cargo build --locked` and `pip install --no-deps` where possible. `pip-audit` and `cargo audit` run on every push. |

## Residual Risk and Revision Cadence

The most material residual risk is **music analysis model compromise** — if a model checkpoint is replaced with a backdoored one, every user that downloads Melosviz gets the backdoored model. The strongest available mitigation is the SHA-256 content-addressed checkpoint + checksum verification, but this assumes the index of known-good checksums is itself trustworthy. The next highest residual is **typosquatted download domain** — there is no automated way to detect a lookalike download URL. This threat model should be revised quarterly (February, May, August, November) or whenever a new model is integrated, a new code-gen backend is added, or the desktop app shell is changed. The revision trigger is any PR that adds a new model, a new backend (e.g., switching from Tauri to a different shell), or a new user-facing endpoint.
