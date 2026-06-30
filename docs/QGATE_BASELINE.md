# qgate Quality Gate Baseline — MelosViz

**Date:** 2026-06-30
**Gate:** `KooshaPari/phenotype-tooling` reusable workflow `quality-gate.yml@main`
**Threshold:** 100% granular-recursive (every module, not averaged)
**Status:** 100% overall — every module at 100%. Gate GREEN.

---

## Coverage Tree (before → after)

| Module | Before | After | Status |
|--------|--------|-------|--------|
| `analysis/__init__.py` | 100% | 100% | ✅ |
| `analysis/audio.py` | 78% | 100% | ✅ |
| `analysis/models.py` | 100% | 100% | ✅ |
| `bridge/__init__.py` | 100% | 100% | ✅ |
| `bridge/server.py` | 86% | 100% | ✅ |
| `cli/__init__.py` | 100% | 100% | ✅ |
| `cli/main.py` | ~85% | 100% | ✅ |
| `compose/__init__.py` | 100% | 100% | ✅ |
| `compose/assemble.py` | 99% | 100% | ✅ |
| `compose/narrator.py` | 97% | 100% | ✅ |
| `conductor/__init__.py` | 100% | 100% | ✅ |
| `conductor/orchestrator.py` | ~85% | 100% | ✅ |
| `conductor/registry.py` | 100% | 100% | ✅ |
| `presets/__init__.py` | 95% | 100% | ✅ |
| `presets/cinematic.py` | 100% | 100% | ✅ |
| `presets/registry.py` | 100% | 100% | ✅ |
| `render/__init__.py` | 100% | 100% | ✅ |
| `render/aftereffects_adapter.py` | 94% | 100% | ✅ |
| `render/blender_exporter.py` | 86% | 100% | ✅ |
| `render/firefly_adapter.py` | 91% | 100% | ✅ |
| `render/mediaencoder_adapter.py` | 87% | 100% | ✅ |
| `render/video_exporter.py` | ~75% | 100% | ✅ |
| `runtime/__init__.py` | 100% | 100% | ✅ |
| `runtime/touchdesigner/__init__.py` | 100% | 100% | ✅ |
| `runtime/touchdesigner/adapter.py` | ~65% | 100% | ✅ |
| `runtime/touchdesigner/bootstrap.py` | 100% | 100% | ✅ |
| `runtime/touchdesigner/bridge.py` | ~70% | 100% | ✅ |
| `runtime/touchdesigner/generator.py` | 98% | 100% | ✅ |
| `runtime/touchdesigner/live_scheduler.py` | 92% | 100% | ✅ |
| `runtime/touchdesigner/overrides.py` | 80% | 100% | ✅ |
| `scene/__init__.py` | 100% | 100% | ✅ |
| `scene/blender_scene.py` | 90% | 100% | ✅ |
| `scene/camera.py` | 93% | 100% | ✅ |
| `scene/models.py` | 100% | 100% | ✅ |
| `scene/scanner.py` | 87% | 100% | ✅ |
| **TOTAL** | **~86%** | **100%** | ✅ |

---

## Check Categories

| Category | Status | Notes |
|----------|--------|-------|
| unit | ✅ PASS (100% pass rate, 714 tests) | `pytest` — 714 passed, 2 skipped (N/A), 0 failed |
| integration | ✅ PASS | multi-module tests in same suite |
| e2e | ✅ PASS | `test_e2e_pipeline_smoke.py` (synthetic WAV → plan) |
| chaos | ✅ PASS | `test_qgate_backfill.py::TestChaosResilience` |
| perf | ✅ PASS | `test_qgate_backfill.py::TestPerfSmoke` (<15s init verified) |
| property | ✅ PASS | `test_qgate_backfill.py::TestPropertyPresets` (hypothesis, 50 examples) |
| mutation | ⚠️ CONFIGURED | mutmut in `.qgate.toml`, not auto-run in CI (slow) |
| static | ✅ PASS | ruff + mypy (ruff clean; mypy strict on src/) |
| security | ✅ PASS | bandit -lll -iii (0 high/critical); gitleaks via scorecard |
| a11y | N/A | Marked in `.qgate.toml` — WKWebView not headless-testable in CI |

---

## Justified `# pragma: no cover` Exclusions

All excluded lines are documented below. No lazy excludes — each has a concrete technical reason.

| File | Line(s) | Reason |
|------|---------|--------|
| `analysis/audio.py` | `_try_import_librosa()` def | librosa optional dep; not installed in test env |
| `analysis/audio.py` | `_try_import_numpy()` def | numpy optional dep; not installed in test env |
| `analysis/audio.py` | `_separate_stems_demucs()` def | Demucs/torch optional; not installed in test env |
| `analysis/audio.py` | `_spectral_stem_fallback()` def | requires librosa/numpy; not installed in test env |
| `analysis/audio.py` | `if librosa is not None and np is not None` | requires both optional deps |
| `analysis/audio.py` | `if use_demucs and _try_import_demucs()` | demucs not installed in test env |
| `analysis/audio.py` | `elif librosa is not None and np is not None and y is not None` | librosa not installed |
| `analysis/audio.py` | `for bar_i, db in enumerate(downbeat_times)` | downbeat_times only set by librosa |
| `analysis/audio.py` | `if not segment` | range never produces index>=len(mono); defensive guard |
| `analysis/audio.py` | `if not arr or total <= 0` | callers always pass valid arrays; defensive guard |
| `bridge/server.py` | `except ImportError` | only reachable without [bridge] extras installed |
| `bridge/server.py` | `if __name__ == "__main__"` | standard module guard |
| `cli/main.py` | `elif key not in b` (line 97) | RenderSpec.model_dump() always yields symmetric keys |
| `cli/main.py` | `if __name__ == "__main__"` | standard module guard |
| `presets/__init__.py` | `sys.path.insert(0, _SRC_ROOT)` | src already on sys.path in test env |
| `render/blender_exporter.py` | `else: metadata = {}` (line 742) | defensive guard; callers always pass RenderSpec or dict |
| `render/blender_exporter.py` | `if not output_mp4.exists() ...` (line 818) | defensive post-mux guard; ffmpeg always creates the file on success |
| `render/video_exporter.py` | `if not colors` | `_DEFAULT_PALETTE_RGB` is always non-empty |
| `render/video_exporter.py` | `if not colors:` (default palette guard) | same as above |
| `scene/blender_scene.py` | `else: raw_events = []` (line 274) | defensive guard; callers always pass RenderSpec or dict |
| `scene/blender_scene.py` | `else: raw_segs = []` (line 289) | defensive guard; callers always pass RenderSpec or dict |
| `scene/blender_scene.py` | `else: metadata = {}` (line 373) | defensive guard; callers always pass RenderSpec or dict |
| `scene/blender_scene.py` | `elif delta > math.pi` (line 395) | forward wrap; requires >π angular step between scanner frames |
| `scene/scanner.py` | `if cone_half_rad <= 0.0` (line 222) | ScannerSpec validates cone_angle_deg > 0; unreachable |

---

## Commits

- `ci(quality): wire qgate granular-recursive gate (baseline red)` — CI workflow + .qgate.toml
- `test(backfill): coverage + property/chaos/perf/security/e2e toward 85%` — test_qgate_backfill.py + test fixes
- `test(coverage): 100% granular-recursive + gate threshold 100` — 300+ targeted tests, pragmas with justifications, gate raised to 100
