# Codex Resume Handoff — Melosviz `feat/production-delivery-extensions`

**Session UUID:** `01a05b35-f397-7803-9d63-462c5faa9a5a`
**Branch:** `feat/production-delivery-extensions`
**Worktree:** `/Users/kooshapari/CodeProjects/Phenotype/repos/Melosviz/.worktrees/production-delivery-extensions`
**Handed off by:** GLM-Powered Forge session (2026-09-01)
**Resume when:** Codex limits reset (approx. 5 days)

---

## What Was Done (14 unpushed commits)

| #   | Commit    | Description                                                                                           |
| --- | --------- | ----------------------------------------------------------------------------------------------------- |
| 1   | `a5e34f8` | Design doc (plan foundation)                                                                          |
| 2   | `845f4af` | Plan doc                                                                                              |
| 3   | `73d35cb` | Chore (worktree ignore)                                                                               |
| 4   | `02cbfda` | Core: LLM admission gate                                                                              |
| 5   | `0eeab0c` | Fix race conditions in cleanup                                                                        |
| 6   | `b5c1d06` | Tests for race cleanup                                                                                |
| 7   | `22a307f` | Bind attempts to cost reservations                                                                    |
| 8   | `f843553` | Reserve on attempt entry                                                                              |
| 9   | `444c9d6` | Wire Director to admission gate + retry/settle + 4 integration tests                                  |
| 10  | `fbc2852` | visual_diff module + provenance fix + cache helpers                                                   |
| 11  | `edbbff9` | GPU smoke workflow: weekly schedule + explicit defaults                                               |
| 12  | `5a31628` | VJ export: SVG + Lottie cue export                                                                    |
| 13  | `6e824c1` | Deterministic package module + viz ship CLI wiring                                                    |
| 14  | `8cc7998` | Fix orchestrator `wav_path` bug + smoke tests + ENV.md + STUDIO_PIPELINE.md + Gherkin acceptance spec |

**Total diff:** +5,100 lines across 25 files.

---

## Test Results (2026-09-01)

```
192 passed, 5 skipped in 4.59s
```

Relevant suites: `backend/tests/llm/`, `backend/tests/conductor/`, `backend/tests/export/`, `backend/tests/cli/`, `backend/tests/test_gpu_smoke_workflow.py`.

---

## Implemented Features

### LLM Admission Gate (`backend/src/melosviz/llm/admission.py`)

- `LLMAdmissionGate`: thread-safe token-bucket gate using `Decimal` for exact arithmetic
- `LLMAdmissionConfig`: `estimate()` / `actual_cost()` / `check()` / `reserve()` / `settle()`
- `LLMAdmissionError`: raised on budget exhaustion or gate timeout
- 8 test cases proving budget enforcement, concurrent bounds, exact arithmetic, and race safety

### Director Admission Integration (`backend/src/melosviz/llm/director.py`)

- `Director(llm_gate, llm_opener, llm_sleeper)` — fully injectable for testing
- `_maybe_refine_with_llm` uses `get_shared_gate().reserve()` → `reservation.attempt()` → retries 429/5xx → `reservation.settle(actual_cost())`
- Falls back to template prompts on any error
- 4 integration tests: missing prices, 429+Retry-After, 400, actual_cost settlement

### Visual Diff (`backend/src/melosviz/conductor/visual_diff.py`)

- `build_visual_diff()`: full-featured SVG timeline + JSON manifest
- `compute_visual_diff()`: orchestrator-friendly wrapper
- `ClipProvenance.visual_diff: dict | None` — round-tripped through `to_dict()`
- 4 tests

### Orchestrator Provenance Fix (`backend/src/melosviz/conductor/orchestrator.py`)

- Fixed broken `write_provenance()` call (was passing a `dict` instead of `ClipProvenance`)
- Removed non-existent fields (`duration_ms`, `license`, `content_origin`)
- Added `audio_path: Path | None` kwarg to `render()` — resolved pre-existing `wav_path` NameError
- Stamps `compute_visual_diff()` result onto every scene's `ClipProvenance`
- Added `scene_cache_key()` / `scene_render_cached()` helpers

### GPU Smoke Workflow (`.github/workflows/gpu-smoke.yml`)

- Weekly cron (Mon 08:17 UTC) trigger alongside `workflow_dispatch`
- Explicit `PYTHON_VERSION` and `INSTALL_FFMPEG` computed from event so schedule works
- Artifact upload on failure
- 3 workflow contract tests in `backend/tests/test_gpu_smoke_workflow.py`

### VJ Export (`backend/src/melosviz/export/vj.py`)

- Shot plan: provenance timing → multi-shot plan doc → single-file defaults
- SVG timeline: beat-grid, colored shot bands, scene labels, time ticks, keyframe annotations
- Lottie cue export: keyframe positions keyed by `sha256(scene_prompt)`, "next shot" cues
- Shot grouping, color assignment, overlap removal, relative media URIs
- 4 tests

### Package + Ship CLI (`backend/src/melosviz/export/package.py` + `backend/src/melosviz/cli/main.py`)

- `build_delivery_package()`: deterministic ZIP bundle (stable sort by relative path → byte-identical runs)
- `PackageManifest`: per-artifact SHA-256 with relative paths
- `MERMAID.md` visual summary + `SHA-256SUMS`
- `viz ship` CLI wired: accepts `--out`, `--bundle-name`, `--bundle-output`, prints JSON to stdout
- 5 package tests + 2 ship CLI tests

### Docs & Specs

- `docs/ENV.md`: MELOSVIZ*LLM*\* guard-rail env vars documented
- `docs/STUDIO_PIPELINE.md`: visual-diff.svg, provenance sidecars, VJ layouts, ship output
- `docs/specs/acceptance/production_delivery_extensions.feature`: Gherkin acceptance spec

---

## Known Pre-Existing Issues (not introduced by this work)

| Issue                                                                         | Location                     | Notes                                           |
| ----------------------------------------------------------------------------- | ---------------------------- | ----------------------------------------------- |
| `backend/tests/test_antigame_fuzz_chaos.py`                                   | NameError: `given` undefined | Hypothesis not installed — harmless in CI       |
| `backend/tests/test_diagnose_bdd.py`                                          | Collection error             | Needs `given` or `from hypothesis import given` |
| `backend/tests/test_fuzz_renderspec.py`                                       | Collection error             | Same                                            |
| `backend/tests/test_spectrum.py`                                              | Collection error             | Same                                            |
| These 4 files are excluded from CI runs; they don't affect the feature branch |

---

## Next Steps (for Codex on Resume)

### High Priority

1. **Rebase + PR**: Squash or interactive-rebase the 14 commits into 3-5 logical units before opening a PR against `main`:
   - Commit 1: Docs (design + plan)
   - Commit 2: LLM admission (core + Director wiring)
   - Commit 3: Orchestrator/provenance/visual_diff
   - Commit 4: GPU smoke workflow
   - Commit 5: VJ export + package + ship CLI
   - Commit 6: Smoke test fixes + docs

2. **Push and create PR**: `git push origin feat/production-delivery-extensions`, open PR with the changelog from `git log --oneline origin/main..HEAD`.

3. **Integration test for admission + Director**: The current Director integration tests mock at the network level. A real integration test that exercises the full Director → LLM → admission gate flow against a real (or mock) LLM endpoint would add more confidence.

### Medium Priority

4. **OpenAPI / API spec**: Add API documentation for the LLM admission endpoints (`/v1/llm/reserve`, `/v1/llm/settle`).

5. **Load test for the admission gate**: The gate is thread-safe but hasn't been load-tested. Consider a `k6` or `locust` test that fires 50+ concurrent requests at the Director to prove no budget overruns.

6. **Operator onboarding doc**: The acceptance spec is written; a short runbook walking an operator through `viz storyboard --wav X.wav` → `viz generate` → `viz ship` would be valuable.

7. **VJ import test**: Currently untested that a real VJ software (VDMX, Resolume, TouchDesigner) can load the exported SVG. The SVG format is standard but this should be verified manually.

### Low Priority / Future

8. **Parallel scene rendering**: The orchestrator renders scenes sequentially. Adding `concurrent.futures.ThreadPoolExecutor` for non-`assembly_encode` scenes could significantly speed up multi-scene jobs.

9. **S3/GCS export**: The `viz ship` bundle is written to disk. Adding `--target s3://...` would enable direct cloud upload.

10. **C4D adapter provenance**: The `c4d_render_plan.json` scene type doesn't yet emit a visual-diff or provenance sidecar. Add when C4D adapter is production-ready.

---

## Quick-Reference Commands

```bash
# Run all tests (fast suites only)
PYTHONPATH=backend/src python3 -m pytest backend/tests/llm/ backend/tests/conductor/ backend/tests/export/ backend/tests/cli/ -q

# Run full smoke test (slow — includes generate + ship)
MELOSVIZ_COMFYUI_OFFLINE=1 PYTHONPATH=backend/src python3 -m pytest -m slow -q backend/tests/cli/test_gpu_smoke.py

# Check branch diff vs main
git diff --stat origin/main..feat/production-delivery-extensions

# Verify imports
PYTHONPATH=backend/src python3 -c "from melosviz.llm.director import Director; from melosviz.export.package import build_delivery_package; from melosviz.export.vj import export_vj_cues; from melosviz.conductor.visual_diff import compute_visual_diff; from melosviz.llm.admission import LLMAdmissionGate; print('All imports OK')"

# Handoff date
date -u  # 2026-09-01T...
```
