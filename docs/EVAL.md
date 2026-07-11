# MelosViz Eval Surfaces

Index of evaluation, benchmark, load, and golden-corpus tooling (audit-v38 C08).

| Surface | Path | Gate |
|---------|------|------|
| Perf smoke (init / preset) | `.github/workflows/perf-smoke.yml` | PR fail if budgets exceeded |
| Criterion benches | `crates/*/benches/` | Local / optional CI |
| PERF numbers | `docs/PERF_BENCHMARK.md` | Documented baselines |
| Golden RenderSpec corpus | `eval/golden/` + `backend/tests/test_golden_corpus.py` | Pytest |
| Bridge load smoke | `backend/tests/test_load_bridge.py` + `.github/workflows/load-smoke.yml` | Concurrent /health |
| Harbor / portage adapter | `eval/harbor/` | Emit + verify in `parity-harbor.yml` / `load-smoke.yml` |
| Rust↔Python parity | `backend/tests/test_rust_python_parity.py` | `parity-harbor.yml` builds MIR + pytest |
| Mutation testing | `.github/workflows/mutmut.yml` | Weekly |
| Coverage | `ci.yml` `--cov-fail-under=85` | PR fail |
| A11y + screenshot baseline | `.github/workflows/a11y.yml` + `eval/golden/screenshots/` | axe + pixelmatch ≤0.2% |
| Flaky quarantine | pytest marker `flaky` (see below) | Skip in default CI |

## Golden corpus

Deterministic synthetic WAVs under `eval/golden/wav/` produce normalized
RenderSpec JSON under `eval/golden/expected/`. Regenerate:

```bash
cd backend
UPDATE_GOLDEN=1 python -m pytest tests/test_golden_corpus.py -q
```

## Harbor adapter

```bash
python eval/harbor/adapter.py --out eval/harbor/out
# Live runner smoke (CI):
cd backend && pytest ../eval/harbor/out/melosviz-analyze-sine/tests/ \
  ../eval/harbor/out/melosviz-bridge-health/tests/ -q
```

## Rust ↔ Python parity

```bash
cargo build --release -p melosviz-mir
export MELOSVIZ_MIR_BIN=$PWD/target/release/melosviz-mir
cd backend && pytest tests/test_rust_python_parity.py -q
```

## Load smoke

```bash
cd backend
python -m pytest tests/test_load_bridge.py -q
```

## Flaky quarantine

Mark unstable tests with `@pytest.mark.flaky` and exclude from default CI:

```bash
pytest -m "not flaky"
```

Document quarantined cases in this file when adding the marker.

## Related

- QGate: `.qgate.toml`
- Work DAG: `docs/WORK_DAG.md` (W-202, W-203)
- Observability SLOs: `docs/SLO.md`
