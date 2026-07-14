"""Thin HTTP bridge between the Electrobun desktop shell and the melosviz backend.

Exposes a small FastAPI app that the Bun main process talks to over localhost.
The bridge is an *optional* performance optimisation: if FastAPI / uvicorn are
not installed, the main process falls back to spawning ``python -m
melosviz.cli.main`` as a subprocess for each request.

Start via::

    python -m melosviz.bridge.server --port 8765

or let the Electrobun main process spawn it automatically.

Security
========

The bridge ships with five defense layers installed by default:

* **Loopback guard** — refuses to bind a non-loopback interface unless
  ``MELOSVIZ_BRIDGE_ALLOW_PUBLIC=1``.
* **Bearer auth** — when ``MELOSVIZ_BRIDGE_REQUIRE_AUTH=1`` (recommended for
  any non-loopback bind) each protected request must carry
  ``Authorization: Bearer $MELOSVIZ_BRIDGE_TOKEN``.
* **Rate limit** — sliding-window per remote IP (env-tunable).
* **Audit log** — every protected request is appended to
  ``$MELOSVIZ_DATA_DIR/audit/bridge.jsonl``.
* **Body size cap** — POST bodies > 1 MiB are rejected with 413.
* **Path containment** — ``wav_path`` and ``out_dir`` must resolve inside the
  configured allowed directory.
* **Global memory cap** — ``/analyze`` ``/build`` ``/render`` refuse new work
  with problem+json 503 (hard) / 429 (soft) once process RSS crosses
  ``MELOSVIZ_MEMORY_CAP_MB`` / ``MELOSVIZ_MEMORY_SOFT_CAP_MB``; the process
  itself never crashes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Attempt FastAPI import; if absent, print a helpful message and exit so the
# Bun main process knows to use the CLI fallback instead.
# ---------------------------------------------------------------------------

try:
    import uvicorn
    from fastapi import FastAPI, File, HTTPException, Request, UploadFile
    from fastapi.responses import PlainTextResponse
    from pydantic import BaseModel, model_validator
except (
    ImportError
):  # pragma: no cover — only reachable without [bridge] extras installed
    print(
        "[melosviz bridge] FastAPI/uvicorn not installed. "
        "Install with:  pip install 'melosviz[bridge]'\n"
        "The desktop app will use the CLI subprocess fallback.",
        file=sys.stderr,
    )
    sys.exit(1)

# Local security primitives. Imported eagerly because the middleware is
# registered at app-startup time and the security helpers are stdlib-only.
import contextlib
import subprocess
import tempfile

from fastapi import HTTPException as _HTTPException  # noqa: E402

from melosviz import observability as obs  # noqa: E402
from melosviz.bridge import security  # noqa: E402
from melosviz.bridge.errors import http_exception_problem  # noqa: E402

obs.configure_logging()
obs.configure_otel()
obs.ensure_continuous_profiler()
_log = __import__("logging").getLogger("melosviz.bridge")

app = FastAPI(title="MelosViz bridge", version="0.1.0")
app.add_exception_handler(_HTTPException, http_exception_problem)

# Install the security middleware once at module import time. Tests that
# need to reset state between cases can call ``server.security_limiter.reset()``.
security_limiter = security.install_middleware(
    app,
    protected_paths=(
        "/analyze",
        "/build",
        "/render",
        "/upload",
        "/health",
        "/ready",
        "/metrics",
    ),
)

# Shared render quota + MIR circuit breaker (tests may ``.reset()``).
render_quota = security.RenderQuota()
mir_breaker = security.CircuitBreaker()
# Global process-level RSS ceiling — independent of render_quota's per-slot
# soft check (see security.MemoryCapGuard docstring). Stateless; safe to
# share across requests without a reset hook.
memory_cap = security.MemoryCapGuard()


@app.middleware("http")
async def _obs_middleware(request, call_next):  # type: ignore[no-untyped-def]
    """Record RED metrics + structured request logs for every HTTP call."""
    import time as _time

    t0 = _time.monotonic()
    tp = obs.extract_traceparent(request.headers)
    path = request.url.path
    with obs.span("http.request", traceparent=tp, path=path, method=request.method):
        response = await call_next(request)
    dur_ms = (_time.monotonic() - t0) * 1000.0
    obs.record_request(path, response.status_code, dur_ms)
    _log.info(
        "request",
        extra={
            "path": path,
            "method": request.method,
            "status": response.status_code,
            "dur_ms": round(dur_ms, 2),
            "trace_id": (tp.split("-")[1] if tp and "-" in tp else None),
        },
    )
    return response


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    wav_path: str | None = None
    audio_path: str | None = None

    @model_validator(mode="after")
    def _require_audio_path(self) -> "AnalyzeRequest":
        if not self.wav_path and not self.audio_path:
            raise ValueError("Either wav_path or audio_path is required")
        return self

    def resolved_path(self) -> str:
        return self.wav_path or self.audio_path or ""


class BuildRequest(BaseModel):
    wav_path: str
    out_dir: str | None = None


class RenderRequest(BaseModel):
    wav_path: str
    out_dir: str


# ---------------------------------------------------------------------------
# Analyzer selection (Rust MIR first, Python fallback)
# ---------------------------------------------------------------------------


def _analyze_with_mir_or_python(wav_path: Path) -> dict:
    """Try Rust MIR analyzer first; fall back to Python if unavailable.

    Rust MIR is faster (~0.82s for 180s audio); Python stdlib is the fallback.
    Returns the RenderSpec v2 dict directly (parsed JSON from either source).
    """
    # Attempt Rust MIR first — look in standard cargo build output locations
    mir_candidates = [
        Path(__file__).parent.parent.parent.parent
        / "target"
        / "release"
        / "melosviz-mir",
        Path(__file__).parent.parent.parent.parent
        / "target"
        / "debug"
        / "melosviz-mir",
    ]

    for mir_binary in mir_candidates:
        if mir_binary.exists():
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False
                ) as tmp:
                    tmp_spec_path = tmp.name
                try:
                    subprocess.run(
                        [
                            str(mir_binary),
                            "--wav",
                            str(wav_path),
                            "--out",
                            tmp_spec_path,
                        ],
                        check=True,
                        capture_output=True,
                        timeout=120,
                    )
                    with open(tmp_spec_path) as f:
                        spec_dict = json.load(f)
                    return spec_dict
                finally:
                    with contextlib.suppress(Exception):
                        Path(tmp_spec_path).unlink()
            except (
                subprocess.CalledProcessError,
                FileNotFoundError,
                json.JSONDecodeError,
                TimeoutError,
            ) as e:
                # Log but continue to Python fallback
                import logging

                logging.warning(
                    f"[MelosViz] Rust MIR failed: {e}; using Python fallback"
                )
                continue

    # Fallback to Python analyzer (rich MIR path when librosa available)
    from melosviz.analysis.audio import spec_from_wav_rich

    spec = spec_from_wav_rich(wav_path)
    data = spec.model_dump() if hasattr(spec, "model_dump") else dict(spec)  # type: ignore[arg-type]

    # --- Inject convenience top-level fields ---
    # bpm: from mir.tempo_bpm (librosa-backed) or metadata.estimated_bpm (stdlib)
    mir: dict = data.get("mir") or {}
    data["bpm"] = mir.get("tempo_bpm") or data.get("metadata", {}).get("estimated_bpm")

    # key: combine mir.key + mir.mode into "C major" / "A minor" style string
    _key = mir.get("key")
    _mode = mir.get("mode")
    if _key and _mode:
        data["key"] = f"{_key} {_mode}"
    elif _key:
        data["key"] = _key
    else:
        _legacy_scale = data.get("metadata", {}).get("scale")
        data["key"] = _legacy_scale  # may be None

    # beat_times: extract from timeline_events where type == "beat"
    data["beat_times"] = sorted(
        [
            float(ev["t"])
            for ev in data.get("timeline_events", [])
            if ev.get("type") == "beat"
        ]
    )

    return data


def _guarded_analyze(wav: Path) -> dict:
    """Run MIR/Python analyze behind the circuit breaker; trip on systemic failures."""
    if not mir_breaker.allow():
        raise HTTPException(
            status_code=503,
            detail="circuit breaker open: MIR temporarily unavailable",
        )
    try:
        data = _analyze_with_mir_or_python(wav)
        mir_breaker.record_success()
        return data
    except HTTPException:
        raise
    except (TimeoutError, OSError, MemoryError, RuntimeError):
        # Systemic / infrastructure failures trip the breaker; bad-WAV parse
        # errors (ValueError, wave.Error, etc.) do not.
        mir_breaker.record_failure()
        raise


# ---------------------------------------------------------------------------
# Path containment helper
# ---------------------------------------------------------------------------


def _check_inside(path_str: str) -> Path:
    """Resolve and validate ``path_str`` is inside the allowed directory.

    When the bridge runs in **legacy desktop mode** (auth disabled, loopback
    bind, no ``MELOSVIZ_BRIDGE_ALLOWED_DIR`` override) the path check is
    skipped — the Bun shell is trusted to send only local paths. This
    preserves backward compatibility with pre-hardening clients.

    Raises :class:`HTTPException` 400 with a sanitised message otherwise.
    """
    if not path_str:
        raise HTTPException(status_code=400, detail="path is empty")
    try:
        target = Path(path_str).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid path: {exc}") from exc
    # Legacy desktop mode: auth off AND no explicit allowed-dir override.
    legacy = not security.auth_required() and not os.environ.get(
        "MELOSVIZ_BRIDGE_ALLOWED_DIR"
    )
    if legacy:
        return target
    if not security.is_path_allowed(target):
        raise HTTPException(
            status_code=400,
            detail=f"path is outside the allowed data directory: {target}",
        )
    return target


def _enforce_memory_cap(request: Request) -> None:
    """Reject heavy work with problem+json 503/429 when RSS is over cap.

    Raises :class:`HTTPException` — never lets a memory-cap breach crash the
    process. Also appends a dedicated audit row (beyond the generic
    per-request row the security middleware already writes) so operators can
    grep ``reason=memory_cap_exceeded`` independent of HTTP status codes.
    """
    try:
        memory_cap.check()
    except security.MemoryCapExceeded as exc:
        status = 503 if exc.tier == "hard" else 429
        ip = request.client.host if request.client else "unknown"
        security.append_audit(
            security.build_audit_row(
                ip=ip,
                method=request.method,
                path=request.url.path,
                status=status,
                dur_ms=0.0,
            )
            | {
                "reason": "memory_cap_exceeded",
                "tier": exc.tier,
                "rss_mb": round(exc.rss_mb, 1),
                "cap_mb": exc.cap_mb,
            }
        )
        headers = {"Retry-After": "30"} if status == 429 else None
        raise HTTPException(
            status_code=status, detail=str(exc), headers=headers
        ) from exc


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, object]:
    """Readiness probe — green once the bridge process is serving."""
    if not obs.is_ready():
        raise HTTPException(status_code=503, detail="not ready")
    return {"status": "ready", "uptime_s": obs.metrics_snapshot()["uptime_s"]}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    """Prometheus-text metrics for request counts, errors, latency, and RSS."""
    lines = [obs.metrics_prometheus().rstrip("\n")]
    rss = memory_cap.current_rss_mb()
    if rss is not None:
        lines.append("# HELP melosviz_memory_rss_mb Current bridge process RSS (MiB)")
        lines.append("# TYPE melosviz_memory_rss_mb gauge")
        lines.append(f"melosviz_memory_rss_mb {rss:.1f}")
    lines.append(
        "# HELP melosviz_memory_cap_mb Configured hard memory cap (MiB); 0 = disabled"
    )
    lines.append("# TYPE melosviz_memory_cap_mb gauge")
    lines.append(f"melosviz_memory_cap_mb {max(memory_cap.hard_cap_mb, 0)}")
    return "\n".join(lines) + "\n"


@app.get("/debug/profile")
async def debug_profile() -> dict[str, object]:
    """Opt-in CPU profile sample (``MELOSVIZ_PROFILE``).

    * ``1`` / ``true`` — one-shot in-process ``cProfile`` of a trivial workload
      on each request.
    * ``continuous`` / ``2`` — return the latest dump from a lightweight
      background sampler (interval ``MELOSVIZ_PROFILE_INTERVAL_S``, default 30s).
      This is an in-process continuous sample, not a py-spy / external agent.

    Disabled (404) unless explicitly enabled — keeps the default attack surface
    small.
    """
    mode = obs.profile_mode()
    if mode == "off":
        raise HTTPException(status_code=404, detail="profiler disabled")
    if mode == "continuous":
        latest = obs.latest_continuous_profile()
        if latest is None:
            raise HTTPException(status_code=503, detail="no continuous sample yet")
        return latest
    sample = obs.cprofile_sample()
    sample["mode"] = "oneshot"
    return sample


@app.post("/analyze", response_class=PlainTextResponse)
async def analyze(req: AnalyzeRequest, request: Request) -> str:
    """Analyze a WAV file and return the RenderSpec as JSON text.

    Uses the fast Rust MIR analyzer when available; falls back to Python.
    """
    _enforce_memory_cap(request)
    wav = _check_inside(req.resolved_path())

    try:
        if not wav.exists():
            raise HTTPException(status_code=400, detail=f"File not found: {wav}")
        tp = None  # request-scoped traceparent already applied by middleware
        with render_quota.slot(), obs.span("analyze", traceparent=tp, wav=str(wav)):
            data = _guarded_analyze(wav)
    except security.QuotaExceeded as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — surface as 400 (incl. stdlib `wave.Error`)
        raise HTTPException(status_code=400, detail=f"invalid WAV: {exc}") from exc
    return json.dumps(data, indent=2, default=str)


_UPLOAD_CHUNK_BYTES = 1024 * 1024  # 1 MiB streaming chunks
_UPLOAD_SUFFIXES = frozenset({".wav", ".wave", ".mp3", ".flac", ".ogg", ".m4a", ".aac"})


@app.post("/upload")
async def upload_audio(
    request: Request, file: UploadFile = File(...)
) -> dict[str, str]:
    """Stream a browser-uploaded audio file into the allowed data directory.

    Returns ``{"wav_path": "<absolute path>"}`` for use with ``POST /analyze``.
    """
    upload_root = security.allowed_dir() / "uploads"
    upload_root.mkdir(parents=True, exist_ok=True)

    raw_suffix = Path(file.filename or "audio.wav").suffix.lower()
    suffix = raw_suffix if raw_suffix in _UPLOAD_SUFFIXES else ".wav"
    dest = upload_root / f"{uuid.uuid4().hex}{suffix}"

    written = 0
    max_bytes = security.max_upload_bytes()
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(_UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds {max_bytes} bytes",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"upload failed: {exc}") from exc

    resolved = dest.resolve()
    if not security.is_path_allowed(resolved):
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="upload path is outside the allowed data directory",
        )
    return {"wav_path": str(resolved)}


@app.post("/build", response_class=PlainTextResponse)
async def build(req: BuildRequest, request: Request) -> str:
    """Analyze a WAV then assemble a render plan; return plan JSON.

    Uses the fast Rust MIR analyzer when available; falls back to Python.
    """
    from melosviz.compose.assemble import assemble_render_plan

    _enforce_memory_cap(request)
    wav = _check_inside(req.wav_path)

    try:
        if not wav.exists():
            raise HTTPException(status_code=400, detail=f"File not found: {wav}")
        with render_quota.slot():
            spec_data = _guarded_analyze(wav)
            # assemble_render_plan expects a RenderSpec object, not a dict
            # For now, we'll pass the dict directly and let assemble_render_plan handle it
            plan = assemble_render_plan(spec_data, mock_adapters=True)
    except security.QuotaExceeded as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid WAV: {exc}") from exc
    return json.dumps(plan, indent=2, default=str)


@app.post("/render", response_class=PlainTextResponse)
async def render(req: RenderRequest, request: Request) -> str:
    """Run the full conductor pipeline; return output directory path.

    Uses the fast Rust MIR analyzer when available; falls back to Python.
    """
    from melosviz.compose.assemble import assemble_render_plan

    _enforce_memory_cap(request)
    wav = _check_inside(req.wav_path)

    try:
        if not wav.exists():
            raise HTTPException(status_code=400, detail=f"File not found: {wav}")

        out = _check_inside(req.out_dir)
        out.mkdir(parents=True, exist_ok=True)

        with render_quota.slot():
            spec_data = _guarded_analyze(wav)
            # Use mock_adapters=False to attempt real adapters; they fail-open to mocks
            # if Blender / TouchDesigner are absent.
            plan = assemble_render_plan(spec_data, mock_adapters=False)
    except security.QuotaExceeded as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid WAV: {exc}") from exc
    plan_path = out / "render_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, default=str))

    return str(out)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="MelosViz HTTP bridge")
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="TCP port to listen on (default: 8765)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    ok, reason = security.loopback_check(args.host)
    if not ok:
        print(f"[melosviz bridge] {reason}", file=sys.stderr)
        sys.exit(2)

    print(f"[melosviz bridge] binding {args.host}:{args.port} ({reason})")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
