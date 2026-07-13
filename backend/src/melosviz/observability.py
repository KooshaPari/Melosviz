"""Lightweight observability helpers for the MelosViz bridge.

Provides:
* JSON structured logging (stdlib only; no third-party required)
* Optional OpenTelemetry spans + OTLP exporter when ``opentelemetry-*`` is installed
* W3C ``traceparent`` extraction for distributed context
* In-process RED-style counters for /metrics
* Process readiness probe used by ``GET /ready``
* Opt-in in-process cProfile samples (one-shot or continuous) for ``/debug/profile``

Env knobs:
* ``MELOSVIZ_LOG_JSON=1`` (default) — emit one JSON object per log line
* ``MELOSVIZ_OTEL=1`` — enable OTel spans (auto-on when OTLP endpoint is set)
* ``OTEL_EXPORTER_OTLP_ENDPOINT`` — e.g. ``http://127.0.0.1:4318``
* ``OTEL_SERVICE_NAME`` — defaults to ``melosviz-bridge``
* ``MELOSVIZ_PROFILE=1`` — one-shot cProfile on each ``GET /debug/profile``
* ``MELOSVIZ_PROFILE=continuous`` (or ``2``) — background sampler; endpoint returns latest
* ``MELOSVIZ_PROFILE_INTERVAL_S`` — continuous sample period (default ``30``)
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

_log = logging.getLogger("melosviz.otel")
_otel_configured = False


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record (structured logs)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in (
            "request_id",
            "path",
            "method",
            "status",
            "dur_ms",
            "span",
            "trace_id",
        ):
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


def _otel_enabled() -> bool:
    if os.environ.get("MELOSVIZ_OTEL", "").lower() in ("0", "false"):
        return False
    if os.environ.get("MELOSVIZ_OTEL", "").lower() in ("1", "true"):
        return True
    # Auto-enable when an OTLP endpoint is configured.
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))


def configure_otel() -> bool:
    """Install a TracerProvider + OTLP exporter once. Returns True if live."""
    global _otel_configured
    if _otel_configured:
        return True
    if not _otel_enabled():
        return False
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.sdk.resources import (
            Resource,  # type: ignore[import-not-found]
        )
        from opentelemetry.sdk.trace import (
            TracerProvider,  # type: ignore[import-not-found]
        )
        from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )

        service = os.environ.get("OTEL_SERVICE_NAME", "melosviz-bridge")
        provider = TracerProvider(resource=Resource.create({"service.name": service}))
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
                    OTLPSpanExporter,
                )

                provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
                _log.info("otel OTLP exporter configured endpoint=%s", endpoint)
            except Exception:  # noqa: BLE001
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
                _log.warning("otel OTLP import failed; using console exporter")
        else:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        _otel_configured = True
        return True
    except Exception:  # noqa: BLE001
        _log.debug("otel configure failed", exc_info=True)
        return False


def extract_traceparent(headers: Any) -> str | None:
    """Return a W3C traceparent header value if present."""
    try:
        value = headers.get("traceparent")  # type: ignore[union-attr]
        if value:
            return str(value)
    except Exception:  # noqa: BLE001
        return None
    return None


@contextmanager
def span(
    name: str,
    *,
    traceparent: str | None = None,
    **attrs: Any,
) -> Iterator[None]:
    """Optional OpenTelemetry span; no-op when OTel is absent or disabled."""
    if not _otel_enabled():
        yield
        return
    configure_otel()
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.trace.propagation.tracecontext import (  # type: ignore[import-not-found]
            TraceContextTextMapPropagator,
        )

        tracer = trace.get_tracer("melosviz")
        ctx = None
        if traceparent:
            carrier = {"traceparent": traceparent}
            ctx = TraceContextTextMapPropagator().extract(carrier=carrier)
        with tracer.start_as_current_span(name, context=ctx) as current:
            for k, v in attrs.items():
                current.set_attribute(k, str(v))
            yield
    except Exception:  # noqa: BLE001 — OTel is best-effort
        _log.debug("otel span unavailable for %s", name, exc_info=True)
        yield


# ---------------------------------------------------------------------------
# Opt-in in-process profiler (not a py-spy / external agent sidecar)
# ---------------------------------------------------------------------------


def profile_mode() -> str:
    """Return ``off``, ``oneshot``, or ``continuous`` from ``MELOSVIZ_PROFILE``."""
    raw = os.environ.get("MELOSVIZ_PROFILE", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return "oneshot"
    if raw in ("2", "continuous"):
        return "continuous"
    return "off"


def profile_interval_s() -> float:
    """Continuous sampler period; default 30s, floored to avoid a busy loop."""
    try:
        value = float(os.environ.get("MELOSVIZ_PROFILE_INTERVAL_S", "30"))
    except ValueError:
        return 30.0
    return max(0.1, value)


def cprofile_sample(*, stats_limit: int = 20) -> dict[str, Any]:
    """Run a short stdlib ``cProfile`` dump of a trivial CPU workload."""
    import cProfile
    import io
    import pstats

    def _work() -> int:
        total = 0
        for i in range(50_000):
            total += i * i
        return total

    pr = cProfile.Profile()
    pr.enable()
    result = _work()
    pr.disable()
    buf = io.StringIO()
    pstats.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(stats_limit)
    return {
        "status": "ok",
        "result": result,
        "profile": buf.getvalue(),
        "sampled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


class ContinuousProfiler:
    """Daemon thread that keeps the latest in-process cProfile dump."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: dict[str, Any] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        # Seed immediately so /debug/profile is useful before the first interval.
        self._capture()
        self._thread = threading.Thread(
            target=self._loop,
            name="melosviz-continuous-profiler",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None

    def latest(self) -> dict[str, Any] | None:
        with self._lock:
            if self._latest is None:
                return None
            return dict(self._latest)

    def _capture(self) -> None:
        sample = cprofile_sample()
        sample["mode"] = "continuous"
        sample["interval_s"] = profile_interval_s()
        with self._lock:
            self._latest = sample

    def _loop(self) -> None:
        while not self._stop.wait(timeout=profile_interval_s()):
            try:
                self._capture()
            except Exception:  # noqa: BLE001 — sampler must not kill the process
                _log.debug("continuous profiler sample failed", exc_info=True)


_continuous_profiler = ContinuousProfiler()
_continuous_lock = threading.Lock()


def ensure_continuous_profiler() -> ContinuousProfiler:
    """Start the background sampler when ``MELOSVIZ_PROFILE`` is continuous."""
    with _continuous_lock:
        if profile_mode() == "continuous":
            _continuous_profiler.start()
        return _continuous_profiler


def stop_continuous_profiler() -> None:
    """Stop the background sampler (tests / shutdown)."""
    with _continuous_lock:
        _continuous_profiler.stop()


def latest_continuous_profile() -> dict[str, Any] | None:
    """Return the latest continuous sample, or ``None`` if none yet."""
    ensure_continuous_profiler()
    return _continuous_profiler.latest()
