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

## Audit log

Protected requests append JSONL to `$MELOSVIZ_DATA_DIR/audit/bridge.jsonl`.
See `docs/security/BRIDGE_THREAT_MODEL.md`.
