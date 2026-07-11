# MelosViz environment catalog (12-factor)

| Variable | Default | Surface | Purpose |
|----------|---------|---------|---------|
| `MELOSVIZ_BRIDGE_REQUIRE_AUTH` | unset/0 | bridge | Require Bearer token when set |
| `MELOSVIZ_BRIDGE_TOKEN` | — | bridge | Shared secret for auth |
| `MELOSVIZ_BRIDGE_RATE_LIMIT` | 30 | bridge | Requests per window |
| `MELOSVIZ_BRIDGE_WINDOW` | 60 | bridge | Rate-limit window (seconds) |
| `MELOSVIZ_BRIDGE_MAX_BODY` | 1 MiB | bridge | POST body cap |
| `MELOSVIZ_ALLOWED_DIR` | cwd | bridge | Path containment root |
| `MELOSVIZ_DATA_DIR` | platform | bridge | Audit JSONL + data |
| `MELOSVIZ_LOG_JSON` | 1 | observability | JSON structured logs |
| `MELOSVIZ_OTEL` | auto | observability | Force OTel on/off |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | observability | OTLP HTTP endpoint (auto-enables OTel) |
| `OTEL_SERVICE_NAME` | melosviz-bridge | observability | Resource service.name |
| `MELOSVIZ_PROFILE` | unset/0 | bridge | Enable `GET /debug/profile` cProfile sample |
| `MELOSVIZ_LOCALE` | `en` | web | UI locale (`en` / `es`) — see `docs/I18N.md` |
| `MELOSVIZ_BACKEND_PORT` | — | desktop | Sidecar port hint |

Token rotation: `docs/KEY_ROTATION.md`. Privacy: `docs/PRIVACY.md`.

See `docs/security/BRIDGE_THREAT_MODEL.md` and `docs/OBSERVABILITY.md`.
