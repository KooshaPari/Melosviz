# Fuzz / property harnesses

| Harness | Path | How to run |
|---------|------|------------|
| Hypothesis RenderSpec JSON | `backend/tests/test_fuzz_renderspec.py` | `pytest tests/test_fuzz_renderspec.py` |
| Bridge path fuzz | `backend/tests/test_spectrum.py` (hypothesis) | part of backend suite |
| Optional atheris | `fuzz/atheris_renderspec.py` | `pip install atheris && python fuzz/atheris_renderspec.py` |
| cargo-fuzz (future) | `fuzz/README.md` | nightly + `cargo fuzz` — not CI-gated yet |

CI runs the hypothesis suite via `load-smoke.yml` and main pytest.
