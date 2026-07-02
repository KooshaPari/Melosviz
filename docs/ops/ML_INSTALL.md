# ML Extras Install Recipe

**Scope:** how to install the optional ML/audio-DSP dependencies that power
the MIR-enriched paths in `backend/src/melosviz/analysis/audio.py` so the
optional-dep code branches are exercisable in tests and live runs.

## Background

`backend/pyproject.toml` keeps the runtime dependency graph intentionally
minimal — only `pydantic` is a hard runtime dep. The audio-analysis module
gracefully degrades when optional deps are absent and tags those branches
with `# pragma: no cover — requires <dep>`. To exercise (and cover) those
branches, install the `[analysis]` + `[stems]` + `[bridge]` extras.

## Install

```bash
# Python 3.14 venv (matches the version the optional-dep branches were
# written against; Python 3.13 also works but the audioop backport path
# won't be hit).
cd backend
uv venv --python 3.14 .venv-314
uv pip install --python .venv-314/bin/python -e ".[test,analysis,stems,bridge]"
```

This pulls in:

| Extra | Packages | Powers |
|---|---|---|
| `analysis` | `librosa`, `numpy`, `scipy` | `_try_import_librosa`, `_try_import_numpy`, `analyze_beats_with_librosa`, `_envelope_amplitude` (numpy path) |
| `stems` | `demucs`, `torch` | `_separate_stems_demucs`, `_try_import_demucs`, Demucs backend of `separate_stems` |
| `bridge` | `fastapi`, `uvicorn` | `bridge/server.py` FastAPI app |
| `test` | `pytest` | test runner |

## Verify

```bash
.venv-314/bin/python -c "import librosa, numpy, scipy, demucs, torch, fastapi; \
    print(librosa.__version__, numpy.__version__, scipy.__version__, \
          demucs.__version__, torch.__version__, fastapi.__version__)"
```

Expected output (versions pinned at time of writing):

```
0.11.0 2.4.6 1.18.0 4.0.1 2.12.1 0.139.0
```

## Coverage gate

With these extras installed, run the full backend test suite with coverage:

```bash
cd backend
.venv-314/bin/pytest tests/ \
    --cov=melosviz \
    --cov-report=term-missing \
    --cov-report=xml:coverage.xml \
    --cov-fail-under=85
```

The optional-dep branches that previously carried
`# pragma: no cover — requires <dep>` are now exercised by behavioural tests
(see `backend/tests/test_audio_ml_paths.py`).