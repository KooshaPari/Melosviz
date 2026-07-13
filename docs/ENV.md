# MelosViz environment catalog (12-factor)

| Variable | Default | Surface | Purpose |
|----------|---------|---------|---------|
| `MELOSVIZ_BRIDGE_REQUIRE_AUTH` | unset/0 | bridge | Require Bearer token when set |
| `MELOSVIZ_BRIDGE_TOKEN` | — | bridge | Shared secret for auth |
| `MELOSVIZ_BRIDGE_RATE_LIMIT` | 30 | bridge | Requests per window |
| `MELOSVIZ_BRIDGE_WINDOW` | 60 | bridge | Rate-limit window (seconds) |
| `MELOSVIZ_BRIDGE_MAX_BODY_BYTES` | 1 MiB | bridge | POST body cap |
| `MELOSVIZ_BRIDGE_ALLOWED_DIR` | `$MELOSVIZ_DATA_DIR` / `$HOME` | bridge | Path containment root |
| `MELOSVIZ_DATA_DIR` | platform | bridge | Audit JSONL + data |
| `MELOSVIZ_AUDIT_MAX_BYTES` | `5000000` | bridge | Prune audit JSONL when file exceeds this size (`<=0` disables) |
| `MELOSVIZ_AUDIT_MAX_LINES` | `50000` | bridge | Prune audit JSONL when line count exceeds this (`<=0` disables); keep newest ~80% |
| `MELOSVIZ_RENDER_MAX_CONCURRENT` | `2` | bridge | Max concurrent `/analyze` `/build` `/render` slots (`<=0` disables) |
| `MELOSVIZ_RENDER_MAX_RSS_MB` | `2048` | bridge | Soft RSS ceiling before refusing a new render slot (`<=0` disables; skipped if RSS unavailable) |
| `MELOSVIZ_MEMORY_CAP_MB` | `4096` | bridge | **Global** hard process RSS ceiling; `/analyze` `/build` `/render` refuse new work with problem+json `503` once exceeded (`<=0` disables). Distinct from `MELOSVIZ_RENDER_MAX_RSS_MB` — independent of concurrency-slot accounting. |
| `MELOSVIZ_MEMORY_SOFT_CAP_MB` | 85% of `MELOSVIZ_MEMORY_CAP_MB` | bridge | Soft RSS ceiling; refuses new work with problem+json `429` + `Retry-After` before the hard cap trips (`<=0` disables the soft tier only) |
| `MELOSVIZ_BREAKER_FAILURE_THRESHOLD` | `5` | bridge | MIR/render failures before circuit opens |
| `MELOSVIZ_BREAKER_RESET_SECONDS` | `30` | bridge | Seconds before open breaker enters half-open |
| `MELOSVIZ_LOG_JSON` | 1 | observability | JSON structured logs |
| `MELOSVIZ_OTEL` | auto | observability | Force OTel on/off |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | observability | OTLP HTTP endpoint (auto-enables OTel) |
| `OTEL_SERVICE_NAME` | melosviz-bridge | observability | Resource service.name |
| `MELOSVIZ_PROFILE` | unset/0 | bridge | Opt-in `GET /debug/profile`: `1`/`true` = one-shot cProfile; `continuous`/`2` = in-process background sampler (not a py-spy sidecar) |
| `MELOSVIZ_PROFILE_INTERVAL_S` | `30` | bridge | Continuous sampler period (seconds); only used when `MELOSVIZ_PROFILE=continuous` or `2` |
| `MELOSVIZ_LOCALE` | `en` | web / CLI / desktop | Locale (`en` / `es`) — see `docs/I18N.md` (scaffold; not full coverage) |
| `MELOSVIZ_BACKEND_PORT` | — | desktop | Sidecar port hint |

Token rotation: `docs/KEY_ROTATION.md`. Privacy: `docs/PRIVACY.md`.

See `docs/security/BRIDGE_THREAT_MODEL.md` and `docs/OBSERVABILITY.md`.
