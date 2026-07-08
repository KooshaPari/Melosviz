"""Lightweight observability helpers for the MelosViz bridge.

Provides:
* JSON structured logging (stdlib only; no third-party required)
* Optional OpenTelemetry span wrapping when ``opentelemetry-api`` is installed
* In-process RED-style counters for /metrics
* Process readiness probe used by ``GET /ready``

Env knobs:
* ``MELOSVIZ_LOG_JSON=1`` (default) — emit one JSON object per log line
* ``MELOSVIZ_OTEL=1`` — attempt to create OTel spans when the SDK is present
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record (structured logs)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "path", "method", "status", "dur_ms", "span"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Install a JSON (or plain) handler on the root logger once."""
    root = logging.getLogger()
    if getattr(root, "_melosviz_configured", False):
        return
    handler = logging.StreamHandler(sys.stderr)
    if os.environ.get("MELOSVIZ_LOG_JSON", "1") not in ("0", "false", "False"):
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root._melosviz_configured = True  # type: ignore[attr-defined]


_metrics_lock = threading.Lock()
_request_counts: Counter[str] = Counter()
_error_counts: Counter[str] = Counter()
_latency_ms: Counter[str] = Counter()
_latency_n: Counter[str] = Counter()
_started_at = time.time()
_ready = True


def set_ready(value: bool) -> None:
    global _ready
    _ready = value


def is_ready() -> bool:
    return _ready


def record_request(path: str, status: int, dur_ms: float) -> None:
    with _metrics_lock:
        _request_counts[path] += 1
        _latency_ms[path] += int(dur_ms)
        _latency_n[path] += 1
        if status >= 400:
            _error_counts[path] += 1


def metrics_snapshot() -> dict[str, Any]:
    with _metrics_lock:
        paths = sorted(set(_request_counts) | set(_error_counts) | set(_latency_n))
        per_path = {}
        for path in paths:
            n = _latency_n[path]
            avg = (_latency_ms[path] / n) if n else 0.0
            per_path[path] = {
                "requests": _request_counts[path],
                "errors": _error_counts[path],
                "avg_latency_ms": round(avg, 2),
            }
        return {
            "uptime_s": round(time.time() - _started_at, 1),
            "ready": _ready,
            "paths": per_path,
        }


def metrics_prometheus() -> str:
    """Render a minimal Prometheus text exposition."""
    snap = metrics_snapshot()
    lines = [
        "# HELP melosviz_up 1 if process is up",
        "# TYPE melosviz_up gauge",
        "melosviz_up 1",
        "# HELP melosviz_ready 1 if readiness probe is green",
        "# TYPE melosviz_ready gauge",
        f"melosviz_ready {1 if snap['ready'] else 0}",
        "# HELP melosviz_uptime_seconds Process uptime",
        "# TYPE melosviz_uptime_seconds gauge",
        f"melosviz_uptime_seconds {snap['uptime_s']}",
        "# HELP melosviz_http_requests_total HTTP requests by path",
        "# TYPE melosviz_http_requests_total counter",
    ]
    for path, stats in snap["paths"].items():
        safe = path.replace('"', "")
        lines.append(
            f'melosviz_http_requests_total{{path="{safe}"}} {stats["requests"]}'
        )
    lines.append("# HELP melosviz_http_errors_total HTTP 4xx/5xx by path")
    lines.append("# TYPE melosviz_http_errors_total counter")
    for path, stats in snap["paths"].items():
        safe = path.replace('"', "")
        lines.append(f'melosviz_http_errors_total{{path="{safe}"}} {stats["errors"]}')
    lines.append("# HELP melosviz_http_latency_ms_avg Average latency by path")
    lines.append("# TYPE melosviz_http_latency_ms_avg gauge")
    for path, stats in snap["paths"].items():
        safe = path.replace('"', "")
        lines.append(
            f'melosviz_http_latency_ms_avg{{path="{safe}"}} {stats["avg_latency_ms"]}'
        )
    return "\n".join(lines) + "\n"


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[None]:
    """Optional OpenTelemetry span; no-op when OTel is absent or disabled."""
    log = logging.getLogger("melosviz.otel")
    if os.environ.get("MELOSVIZ_OTEL", "0") not in ("1", "true", "True"):
        yield
        return
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]

        tracer = trace.get_tracer("melosviz")
        with tracer.start_as_current_span(name) as current:
            for k, v in attrs.items():
                current.set_attribute(k, v)
            yield
    except Exception:  # noqa: BLE001 — OTel is best-effort
        log.debug("otel span unavailable for %s", name, exc_info=True)
        yield
