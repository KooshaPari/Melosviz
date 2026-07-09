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
`path`, `method`, `status`, `dur_ms`.

## OpenTelemetry

```bash
pip install 'melosviz[otel]'
export MELOSVIZ_OTEL=1
# Configure OTEL_EXPORTER_OTLP_ENDPOINT as usual for the SDK
python -m melosviz.bridge.server --port 8765
```

Spans are best-effort: if the SDK is missing, the bridge still serves.

## Prometheus scrape snippet

```yaml
scrape_configs:
  - job_name: melosviz-bridge
    static_configs:
      - targets: ["127.0.0.1:8765"]
    metrics_path: /metrics
```

## Alert ideas (operator-owned)

| Alert | Expr (sketch) | Severity |
|-------|---------------|----------|
| Bridge down | `up{job="melosviz-bridge"} == 0` | critical |
| High error rate | `rate(melosviz_http_errors_total[5m]) > 0.1` | warning |
| Analyze latency | `melosviz_http_latency_ms_avg{path="/analyze"} > 15000` | warning |

## Audit log

Protected requests append JSONL to `$MELOSVIZ_DATA_DIR/audit/bridge.jsonl`.
See `docs/security/BRIDGE_THREAT_MODEL.md`.
