# MelosViz Observability

Bridge telemetry for operators and agents.

## Endpoints

| Path | Purpose |
|------|---------|
| `GET /health` | Liveness — process is up |
| `GET /ready` | Readiness — safe to send traffic |
| `GET /metrics` | Prometheus text (RED: requests, errors, avg latency) |

## Structured logs

Set `MELOSVIZ_LOG_JSON=1` (default). Each request emits a JSON line with
`path`, `method`, `status`, `dur_ms`, and optional `trace_id`.

## OpenTelemetry + OTLP

```bash
pip install 'melosviz[otel]'
export MELOSVIZ_OTEL=1
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
export OTEL_SERVICE_NAME=melosviz-bridge
python -m melosviz.bridge.server --port 8765
```

If `OTEL_EXPORTER_OTLP_ENDPOINT` is set, OTel auto-enables even without
`MELOSVIZ_OTEL=1`. Spans are best-effort: if the SDK is missing, the bridge
still serves.

### Trace propagation

The bridge reads inbound W3C `traceparent` headers and continues the trace
for `http.request` / `analyze` spans. Desktop/web clients should forward
`traceparent` when calling `/analyze`, `/build`, or `/render`.

**Desktop Bun client** (`desktop/src/index.ts`): `bridgeFetch` and the
startup `/health` probe always send a W3C `traceparent`
(`00-<32-hex-trace_id>-<16-hex-span_id>-01`). If a caller already supplies a
valid header, it is forwarded unchanged; otherwise Bun mints a new sampled
context so bridge spans stay correlatable in logs / OTel.

## Prometheus scrape snippet

```yaml
scrape_configs:
  - job_name: melosviz-bridge
    static_configs:
      - targets: ["127.0.0.1:8765"]
    metrics_path: /metrics
```

## Grafana

Import [`docs/observability/grafana-bridge.json`](observability/grafana-bridge.json)
into Grafana (Prometheus datasource). Panels: up, ready, uptime, request rate,
error rate, avg latency.

## Continuous profiling (optional)

Bridge CPU profiling is **operator-opt-in**. MelosViz ships an **in-process**
cProfile path — not a production py-spy / continuous-profiler sidecar agent.

| `MELOSVIZ_PROFILE` | Behavior |
|--------------------|----------|
| unset / `0` | `GET /debug/profile` → 404 |
| `1` / `true` | One-shot: each request runs a short in-process cProfile dump |
| `continuous` / `2` | Background sampler every `MELOSVIZ_PROFILE_INTERVAL_S` (default **30**); `GET /debug/profile` returns the **latest** dump |

```bash
# One-shot on-request sample
export MELOSVIZ_PROFILE=1
curl -s localhost:8765/debug/profile

# In-process continuous sample (keeps latest dump)
export MELOSVIZ_PROFILE=continuous
# export MELOSVIZ_PROFILE_INTERVAL_S=30   # optional; default 30
curl -s localhost:8765/debug/profile

# External attach (operator-owned; not bundled as a MelosViz agent)
pip install py-spy
py-spy top --pid <bridge-pid>

# stdlib cProfile for a single analyze
python -m cProfile -o analyze.prof -m melosviz.cli.main analyze track.wav
```

Documented for C05 L45. Always-on **external** profiler agents remain optional /
future (WBS-P3.4 residual).

## Alert ideas (operator-owned)

Committed PrometheusRule sketches:
[`deploy/prometheus/melosviz-bridge-rules.yaml`](../deploy/prometheus/melosviz-bridge-rules.yaml).

| Alert | Expr (sketch) | Severity |
|-------|---------------|----------|
| Bridge down | `melosviz_up == 0` | critical |
| High error rate | `rate(melosviz_http_errors_total[5m]) > 0.1` | warning |
| Analyze latency | `melosviz_http_latency_ms_avg{path="/analyze"} > 15000` | warning |

## Global memory-cap enforcement (C00 L8)

The bridge enforces a **process-level** soft/hard RSS ceiling on top of
`RenderQuota`'s per-slot soft check (`MELOSVIZ_RENDER_MAX_RSS_MB`). This
closes the "no global memory-cap enforcement" gap: `RenderQuota` only checks
RSS at slot-acquisition time and is scoped to concurrency accounting; the
global cap (`security.MemoryCapGuard`) checks RSS on every `/analyze`
`/build` `/render` call regardless of how many slots are in flight.

| `MELOSVIZ_MEMORY_CAP_MB` | Behavior |
|---------------------------|----------|
| unset (default `4096`) | Hard ceiling; RSS over this → `503` problem+json, request rejected |
| `<=0` | Hard tier disabled |

| `MELOSVIZ_MEMORY_SOFT_CAP_MB` | Behavior |
|---------------------------------|----------|
| unset (default: 85% of hard cap) | Soft ceiling; RSS over this (but under hard) → `429` problem+json + `Retry-After: 30` |
| `<=0` | Soft tier disabled (hard cap still applies) |

Both checks use the same best-effort RSS probe as `RenderQuota`
(`resource.getrusage` on Linux/macOS, `psutil` fallback for Windows). If RSS
can't be measured, the guard **fails open** — requests proceed and the
process never crashes or wedges due to a measurement gap.

Every rejection:

* Returns `application/problem+json` (`503` hard / `429` soft) via the
  existing `http_exception_problem` handler — no bespoke error shape.
* Appends a dedicated audit row to `$MELOSVIZ_DATA_DIR/audit/bridge.jsonl`
  with `reason=memory_cap_exceeded`, `tier`, `rss_mb`, `cap_mb` (in addition
  to the generic per-request row the security middleware always writes).
* Never terminates the process — enforcement is a request-level refusal,
  not a `SIGKILL`/OOM-style intervention.

`GET /metrics` exposes `melosviz_memory_rss_mb` (best-effort gauge) and
`melosviz_memory_cap_mb` (configured hard cap; `0` = disabled) for operator
dashboards/alerts.

```bash
# Lower the ceiling for a memory-constrained host
export MELOSVIZ_MEMORY_CAP_MB=1024
export MELOSVIZ_MEMORY_SOFT_CAP_MB=768
python -m melosviz.bridge.server --port 8765
```

Tests: `backend/tests/test_bridge_memory_cap.py`.

## Audit log

Protected requests append JSONL to `$MELOSVIZ_DATA_DIR/audit/bridge.jsonl`.
See `docs/security/BRIDGE_THREAT_MODEL.md`.
