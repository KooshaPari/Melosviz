# MelosViz SLO / Error Budget (C02 L27)

Operator-facing service level objectives for the **local bridge**
(`melosviz.bridge.server`). Desktop is single-user; these are soft SLOs
for agents and maintainers, not contractual SaaS SLAs.

## Objectives

| SLO | Target | Measurement |
|-----|--------|-------------|
| Bridge liveness | 99% of local sessions `/health` 200 within 5s of spawn | desktop e2e + load-smoke |
| Analyze init (stdlib path) | p95 < 15s for ≤180s WAV | `perf-smoke.yml`, PERF_BENCHMARK |
| Preset apply | p95 < 100ms | `perf-smoke.yml` |
| HTTP error rate (4xx/5xx excl. client 400) | < 1% over 5m window | `/metrics` + Grafana |

## Error budget

For a 30-day window, 99% liveness ⇒ ~7.2h budget. Burn alerts (sketch):

| Alert | Condition | Action |
|-------|-----------|--------|
| Fast burn | 2% errors in 1h | Check bridge logs / rate limiter |
| Slow burn | 5% errors in 6h | Open incident note; triage adapters |

See `docs/OBSERVABILITY.md` and `docs/observability/grafana-bridge.json`.

## Out of scope

- Multi-tenant hosted MelosViz
- GPU render wall-clock (tracked in PERF_BENCHMARK, not SLO-gated yet)
