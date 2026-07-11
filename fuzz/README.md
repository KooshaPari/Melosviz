# Fuzz / property harnesses

| Harness | Path | How to run |
|---------|------|------------|
| Hypothesis RenderSpec JSON | `backend/tests/test_fuzz_renderspec.py` | `pytest tests/test_fuzz_renderspec.py` |
| Bridge path fuzz | `backend/tests/test_spectrum.py` (hypothesis) | part of backend suite |
| Optional atheris | `fuzz/atheris_renderspec.py` | `pip install atheris && python fuzz/atheris_renderspec.py` |
| cargo-fuzz `renderspec_json` | `fuzz/fuzz_targets/renderspec_json.rs` | `cargo fuzz run renderspec_json` |
| cargo-fuzz `wav_header` | `fuzz/fuzz_targets/wav_header.rs` | `cargo fuzz run wav_header` |

CI: hypothesis via `load-smoke.yml` / main pytest. Nightly: `.github/workflows/cargo-fuzz.yml`
runs each target for a short bounded window (`-max_total_time=60`).

```bash
cargo install cargo-fuzz
cd fuzz   # or from repo root with -p path
cargo fuzz run renderspec_json -- -max_total_time=30
```
