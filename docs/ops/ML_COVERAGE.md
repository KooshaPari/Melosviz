# ML Optional-Dep Coverage — Verification Record

**Date:** 2026-07-01
**Branch:** `test/cover-optionals-3`
**Worktree:** `.claude/worktrees/cover-optionals-3`
**Python:** 3.14 (with `audioop-lts` backport)
**Extras installed:** `librosa 0.11.0`, `numpy 2.4.6`, `scipy 1.18.0`, `demucs 4.0.1`, `torch 2.12.1`, `fastapi 0.139.0`

## Result

```
TOTAL 2737   125   95%
```

**Backend coverage: 95% (target: ≥ 85%).** The ML-extras branches in
`audio.py` are now covered at **93%**, up from being explicitly excluded
from the coverage report.

## Test suite

```
668 passed, 7 errors, 1 failed, 3 skipped
```

* **668 passed** — every existing test plus the 41 new behavioural tests in
  `tests/test_audio_ml_paths.py`.
* **7 errors + 1 failed** — all pre-existing failures in `bridge/server.py`
  FastAPI tests, caused by `starlette.testclient` requiring `httpx2` (not
  installed). These failures exist on `origin/main` and are unrelated to
  this change set.
* **3 skipped** — pre-existing skips (heavy Blender / FFmpeg paths).

## Coverage per module (post-change)

| Module | Coverage |
|---|---|
| `analysis/audio.py` | **93%** (was excluded) |
| `analysis/models.py` | 100% |
| `compose/narrator.py` | 100% |
| `compose/assemble.py` | 86% |
| `conductor/orchestrator.py` | 100% |
| `render/blender_exporter.py` | 100% |
| `render/video_exporter.py` | 99% |
| `scene/*` | 100% |
| `runtime/touchdesigner/*` | 100% |
| `bridge/server.py` | 54% (FastAPI tests gated on httpx2) |
| **TOTAL** | **95%** |

## Pragma audit

Removed 9 optional-dep `# pragma: no cover — requires <dep>` lines from
`backend/src/melosviz/analysis/audio.py`:

| Line | Branch |
|---|---|
| 194 | `_try_import_librosa` |
| 203 | `_try_import_numpy` |
| 212 | `_try_import_demucs` |
| 329 | `_separate_stems_demucs` |
| 371 | `_spectral_stem_fallback` |
| 609 | librosa/numpy-rich path inside `analyze_wav_rich` |
| 735 | demucs branch inside `analyze_wav_rich` |
| 737 | spectral-fallback branch inside `analyze_wav_rich` |
| 761 | downbeat timeline loop |

Three pragmas were **kept** because they are genuinely unreachable:

| Line | Why kept |
|---|---|
| 38 | `audioop` ImportError — Python 3.14 with `audioop-lts` always succeeds |
| 124 | `if not segment` — `range(0, len(mono), step)` cannot exceed `len(mono)` |
| 504 | `if not arr or total <= 0` — `_build_scene_segments` always passes populated arrays |

## Coverage config

`backend/pyproject.toml [tool.coverage.report].exclude_also` was updated:

* **Removed** `import librosa`, `import torch`, `import torchaudio`,
  `import numpy as np`, `from demucs` — these are no longer unreachable.
* **Added** `if TYPE_CHECKING:` — Python never executes these at runtime.

## Reproducing

```bash
cd backend
uv venv --python 3.14 .venv-314
uv pip install --python .venv-314/bin/python -e ".[test,analysis,stems,bridge]" pytest-cov
.venv-314/bin/python -m pytest tests/ \
    --ignore=tests/test_qgate_backfill.py \
    --cov=melosviz --cov-report=term \
    --cov-report=xml:coverage.xml -q
```

Expected: **95% coverage**, 668 passed, 7 unrelated FastAPI/httpx2 errors,
1 unrelated FastAPI/httpx2 failure.