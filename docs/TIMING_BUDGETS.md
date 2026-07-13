# Feedback-loop timing budgets (WBS-P1.11 / C03 L30.10)

Agent and human feedback loops stay fast enough that “run the short check”
is cheaper than context-switching. This document is the **engineering loop**
budget (diagnose / pytest smoke / `cargo check` / golden), not the product
render SLOs in [`PERF_BENCHMARK.md`](PERF_BENCHMARK.md).

Lane note: audit C03 marks feedback-loop speed under **L30.10**; the WBS row
`WBS-P1.11` historically cited L30.11 — L30.10 is the correct control.

## Budgets (wall clock, CI-safe)

Generous ceilings for `ubuntu-22.04` GitHub-hosted runners (cold-ish caches).
Local machines should land well under these.

| Loop | Command (canonical) | Budget (s) | Notes |
|------|---------------------|------------|-------|
| diagnose | `python scripts/diagnose.py` / `make diagnose` | 60 | Stdlib-only; usually &lt; 5 s |
| backend pytest smoke | narrow pytest subset (see script) | 180 | Not the full suite |
| cargo check | `cargo check --locked --workspace` | 600 | Cold compile can dominate |
| make golden | `make golden` → `test_golden_corpus.py` | 180 | Corpus asserts only |

Optional accelerators (not required for the gate): `sccache`, `cargo nextest`,
`hyperfine` for local profiling. The CI gate records wall times and fails on
over-budget — it does not install sccache/nextest.

## Enforcement

```bash
# Local (after deps are installed)
python scripts/check_timing_budgets.py
make timing-budgets
```

CI: `.github/workflows/timing-budgets.yml` on `ubuntu-22.04`.

Override a single budget (seconds) via env, e.g.
`MELOSVIZ_BUDGET_CARGO_CHECK=900`.

## Relationship to PERF_BENCHMARK

| Doc | Concern |
|-----|---------|
| `PERF_BENCHMARK.md` | Product render / analysis latency targets |
| `TIMING_BUDGETS.md` (this file) | Developer / agent inner-loop wall times |
