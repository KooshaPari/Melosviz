# MelosViz Eval Surfaces

Index of evaluation, benchmark, load, and golden-corpus tooling (audit-v38 C08).

| Surface | Path | Gate |
|---------|------|------|
| Perf smoke (init / preset) | `.github/workflows/perf-smoke.yml` | PR fail if budgets exceeded |
| Criterion benches | `crates/*/benches/` | Local / optional CI |
| PERF numbers | `docs/PERF_BENCHMARK.md` | Documented baselines |
| Golden RenderSpec corpus | `eval/golden/` + `backend/tests/test_golden_corpus.py` | Pytest |
| Bridge load smoke | `backend/tests/test_load_bridge.py` + `.github/workflows/load-smoke.yml` | Concurrent /health |
| Harbor / portage adapter | `eval/harbor/` | Emit task trees for agent eval |
| Mutation testing | `.github/workflows/mutmut.yml` | Weekly |
| Coverage | `ci.yml` `--cov-fail-under=85` | PR fail |
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
# Emits portage/Harbor task trees (task.toml + instruction.md + tests/)
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
