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


class StudioStoryboardRequest(BaseModel):
    wav_path: str
    concept: str = "abstract narrative, digital medium-format film, 35mm grain"
    bpm: float = 120.0
    palette: str = "#0d0d10 #ff2bd6 #22d3ee #c084fc #f0f0f8"
    out_dir: str
    target_scenes: int = 4
    use_llm_director: bool = True
    # v2 — narrative inputs
    lyrics_path: str | None = None
    mood_board_paths: list[str] | None = None
    continuity_character: str | None = None
    continuity_environment: str | None = None
    aspect_ratio: str = "youtube_16x9_1080p"


class StudioGenerateRequest(BaseModel):
    wav_path: str
    storyboard_path: str
    out_dir: str
    offline: bool = True
    # Optional correlation ID forwarded to the render event bus so the
    # Director's Console SSE stream can subscribe to per-scene events.
    job_id: str | None = None


class StudioMasterRequest(BaseModel):
    edit_path: str
    out_dir: str
    offline: bool = True
    # v3 — audio finishing
    lufs_target: str | None = None  # club_pa / youtube / broadcast_ebu_r128 / cinema_pulse
    export_stems: bool = False
    audio_wav_path: str | None = None


class StudioShipRequest(BaseModel):
    master_dir: str
    offline: bool = True


class StudioDirectRequest(BaseModel):
    """Art-director edit + optional single-scene re-render.

    Mirrors the `viz direct` CLI subcommand (backend/src/melosviz/cli/main.py).
    """

    storyboard_path: str
    scene_index: int
    replace_prompt: str | None = None
    replace_camera: str | None = None
    replace_name: str | None = None
    out_path: str | None = None
    re_render: bool = False
    wav_path: str | None = None
    render_out: str | None = None
    render_offline: bool = True


class StudioValidateRequest(BaseModel):
    """Storyboard validation request — runs the conductor's ``validate_storyboard`` helper."""

    storyboard_path: str
    # Optional hard-rule overrides (kept conservative by default).
    max_scene_seconds: float = 30.0
    require_continuity: bool = False


class StudioPipelineStatus(BaseModel):
    storyboard: dict[str, object] | None = None
    generate: dict[str, object] | None = None
    master: dict[str, object] | None = None
    ship: dict[str, object] | None = None


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
        from melosviz.compose.web_spec import enrich_render_spec_for_web

        data = enrich_render_spec_for_web(data)
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
# Studio pipeline endpoints (ComfyUI-centric music-video production)
# ---------------------------------------------------------------------------
#
# These endpoints wrap the ``python -m melosviz.cli.main`` subcommands
# (storyboard / generate / master / ship) so a thin web/desktop UI can
# drive the orchestrator without bundling Python internals.
#
# Each endpoint:
# - Validates input paths under the security-allowed data directory
# - Enforces the global memory cap
# - Runs the corresponding CLI subcommand as a subprocess with a timeout
# - Returns the emitted artifact JSON / plan / zip path as JSON text

_STUDIO_CMD_TIMEOUT_SEC = 60 * 10  # 10 minutes per stage


def _run_studio_subprocess(args: list[str], *, cwd: str | None = None) -> dict[str, object]:
    """Execute a ``python -m melosviz.cli.main`` subcommand and return its result.

    Mirrors how the desktop shell invokes the CLI via ``runVizCli`` in
    ``desktop/src/index.ts``. The subprocess runs with ``MELOSVIZ_COMFYUI_OFFLINE``
    already exported by the caller when offline mode is requested.
    """
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", "src")
    env.setdefault("PYTHONUNBUFFERED", "1")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "melosviz.cli.main", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=_STUDIO_CMD_TIMEOUT_SEC,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=504,
            detail=f"studio subcommand timed out after {_STUDIO_CMD_TIMEOUT_SEC}s",
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if proc.returncode != 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"studio subcommand failed (exit {proc.returncode}): "
                f"{proc.stderr.strip().splitlines()[-1] if proc.stderr else 'no stderr'}"
            ),
        )

    return {
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout.splitlines()[-5:],
        "stderr_tail": proc.stderr.splitlines()[-5:] if proc.stderr else [],
    }


@app.post("/api/studio/storyboard", response_class=PlainTextResponse)
async def studio_storyboard(req: StudioStoryboardRequest, request: Request) -> str:
    """Generate a storyboard JSON for a WAV using the LLM-driven director.

    Emits ``<out_dir>/storyboard.json`` and returns its contents.
    """
    _enforce_memory_cap(request)
    wav = _check_inside(req.wav_path)
    out = _check_inside(req.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not wav.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {wav}")

    if not req.use_llm_director:
        os.environ["MELOSVIZ_DIRECTOR_DISABLE"] = "1"

    cmd: list[str] = [
        "storyboard", str(wav),
        "--concept", req.concept,
        "--bpm", str(req.bpm),
        "--palette", req.palette,
        "--out", str(out),
    ]
    if req.aspect_ratio:
        cmd += ["--aspect-ratio", req.aspect_ratio]
    if req.lyrics_path:
        cmd += ["--lyrics", req.lyrics_path]
    if req.mood_board_paths:
        for mb in req.mood_board_paths:
            if mb:
                cmd += ["--mood-board", mb]
    if req.continuity_character:
        cmd += ["--continuity-character", req.continuity_character]
    if req.continuity_environment:
        cmd += ["--continuity-environment", req.continuity_environment]

    try:
        _run_studio_subprocess(cmd)
    finally:
        os.environ.pop("MELOSVIZ_DIRECTOR_DISABLE", None)

    sb_path = out / "storyboard.json"
    if not sb_path.exists():
        raise HTTPException(status_code=500, detail="storyboard.json was not emitted")
    return sb_path.read_text()


@app.post("/api/studio/generate", response_class=PlainTextResponse)
async def studio_generate(req: StudioGenerateRequest, request: Request) -> str:
    """Dispatch the conductor pipeline across all storyboard scenes.

    Emits ``<out_dir>/{comfyui_image,comfyui_video,generative_asset,...}/scene_*`` folders,
    each with a ``workflow.json`` ready for ComfyUI (or an ``ffmpeg``/``blender`` command
    for non-ComfyUI scenes). Returns a JSON manifest listing every emitted scene.
    """
    _enforce_memory_cap(request)
    wav = _check_inside(req.wav_path)
    sb = _check_inside(req.storyboard_path)
    out = _check_inside(req.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not wav.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {wav}")
    if not sb.exists():
        raise HTTPException(status_code=400, detail=f"Storyboard not found: {sb}")

    env_overlay: dict[str, str] = {}
    if req.offline:
        env_overlay["MELOSVIZ_COMFYUI_OFFLINE"] = "1"
    # When the caller supplies a correlation ID, forward it to the CLI subprocess
    # so every per-scene event the orchestrator emits lands under that job_id and
    # the Director's Console SSE stream can subscribe to per-pipeline progress.
    cli_args: list[str] = [
        "generate", str(wav),
        "--storyboard", str(sb),
        "--out", str(out),
    ]
    if req.job_id:
        cli_args += ["--job-id", req.job_id]
    prior = {k: os.environ.get(k) for k in env_overlay}
    os.environ.update(env_overlay)
    try:
        _run_studio_subprocess(cli_args)
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # Return a manifest of everything emitted (scoped by scene_type subfolders,
    # e.g. comfyui_image/scene_*, comfyui_video/scene_*, plus any flat scene_* dirs).
    scenes: list[dict[str, object]] = []
    for scene_dir in sorted(out.glob("scene_*")):
        if not scene_dir.is_dir():
            continue
        scene_meta: dict[str, object] = {"scene_dir": str(scene_dir), "name": scene_dir.name}
        wf = scene_dir / "workflow.json"
        js = scene_dir / "job_spec.json"
        plan = scene_dir / "plan.json"
        if wf.exists():
            scene_meta["workflow_json"] = str(wf)
        if js.exists():
            scene_meta["job_spec_json"] = str(js)
        if plan.exists():
            scene_meta["plan_json"] = str(plan)
        scenes.append(scene_meta)

    return json.dumps({"out_dir": str(out), "scenes": scenes}, indent=2)


@app.post("/api/studio/master", response_class=PlainTextResponse)
async def studio_master(req: StudioMasterRequest, request: Request) -> str:
    """Run color + audio mix + master encode via DaVinci / ffmpeg fallback.

    Emits ``<out_dir>/{festival.mov, club.mp4, youtube.mp4, mix.wav, captions.srt}``
    plus ``master_plan.json`` describing each deliverable.
    """
    _enforce_memory_cap(request)
    edit = _check_inside(req.edit_path)
    out = _check_inside(req.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not edit.exists():
        raise HTTPException(status_code=400, detail=f"Edit/plan not found: {edit}")

    env_overlay: dict[str, str] = {}
    if req.offline:
        env_overlay["MELOSVIZ_COMFYUI_OFFLINE"] = "1"
    prior = {k: os.environ.get(k) for k in env_overlay}
    os.environ.update(env_overlay)
    try:
        cmd = ["master", str(edit), "--out", str(out)]
        if req.lufs_target:
            cmd += ["--lufs-target", req.lufs_target]
        if req.export_stems:
            cmd += ["--export-stems"]
        if req.audio_wav_path:
            audio_wav = _check_inside(req.audio_wav_path)
            if audio_wav.exists():
                cmd += ["--audio", str(audio_wav)]
        _run_studio_subprocess(cmd)
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    master_plan = out / "master_plan.json"
    if master_plan.exists():
        return master_plan.read_text()
    # Fallback: emit a tiny summary so the UI always has something to show
    files = sorted(p.name for p in out.iterdir() if p.is_file())
    return json.dumps({"out_dir": str(out), "files": files}, indent=2)


@app.post("/api/studio/ship", response_class=PlainTextResponse)
async def studio_ship(req: StudioShipRequest, request: Request) -> str:
    """Package master deliverables into a single distributable bundle.

    Emits ``<master_dir>/final.zip`` + ``<master_dir>/manifest.json``.
    """
    _enforce_memory_cap(request)
    master_dir = _check_inside(req.master_dir)
    if not master_dir.exists():
        raise HTTPException(status_code=400, detail=f"Master dir not found: {master_dir}")

    env_overlay: dict[str, str] = {}
    if req.offline:
        env_overlay["MELOSVIZ_COMFYUI_OFFLINE"] = "1"
    prior = {k: os.environ.get(k) for k in env_overlay}
    os.environ.update(env_overlay)
    try:
        _run_studio_subprocess(["ship", str(master_dir)])
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    final_zip = master_dir / "final.zip"
    manifest = master_dir / "manifest.json"
    out: dict[str, object] = {"master_dir": str(master_dir)}
    if final_zip.exists():
        out["final_zip"] = str(final_zip)
        out["final_zip_bytes"] = final_zip.stat().st_size
    if manifest.exists():
        out["manifest"] = json.loads(manifest.read_text())
    return json.dumps(out, indent=2)


# ---------------------------------------------------------------------------
# Art-director edit (single-scene mutation + optional re-render)
# ---------------------------------------------------------------------------


@app.post("/api/studio/direct", response_class=PlainTextResponse)
async def studio_direct(req: "StudioDirectRequest", request: Request) -> str:
    """Edit one scene's prompt / camera / name and (optionally) re-render.

    Body:
        storyboard_path: str       — path to storyboard.json
        scene_index: int           — 0-based scene index to edit
        replace_prompt:  str | None
        replace_camera:  str | None
        replace_name:    str | None
        out:             str | None  — if set, writes a separate file
        re_render:       bool         — also invoke ``viz generate`` for
                                       that scene + neighbors
        wav:             str | None   — required when re_render=true
        render_out:      str | None   — required when re_render=true
        render_offline:  bool
    """
    _enforce_memory_cap(request)
    sb_path = _check_inside(req.storyboard_path)
    if not sb_path.exists():
        raise HTTPException(status_code=400, detail=f"storyboard not found: {sb_path}")

    env_overlay: dict[str, str] = {}
    if req.render_offline:
        env_overlay["MELOSVIZ_COMFYUI_OFFLINE"] = "1"
    prior = {k: os.environ.get(k) for k in env_overlay}
    os.environ.update(env_overlay)
    try:
        cmd = ["direct", str(sb_path), "--scene-index", str(req.scene_index)]
        if req.replace_prompt:
            cmd += ["--replace-prompt", req.replace_prompt]
        if req.replace_camera:
            cmd += ["--replace-camera", req.replace_camera]
        if req.replace_name:
            cmd += ["--replace-name", req.replace_name]
        if req.out_path:
            cmd += ["--out", str(_check_inside(req.out_path))]
        if req.re_render:
            cmd += ["--re-render"]
            if req.wav_path:
                cmd += ["--wav", str(_check_inside(req.wav_path))]
            if req.render_out:
                cmd += ["--render-out", str(_check_inside(req.render_out))]
        _run_studio_subprocess(cmd)
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # Always list the supported edit operations, but report edit_count
    # as the number actually applied (i.e. those with a non-None value).
    edits = ["replace_prompt", "replace_camera", "replace_name"]
    applied = sum(
        1
        for op in edits
        if getattr(req, op, None)
    )
    return json.dumps(
        {
            "storyboard_path": str(sb_path),
            "scene_index": req.scene_index,
            "edits": edits,
            "edit_count": applied,
            "re_render": req.re_render,
            "render_out": str(_check_inside(req.render_out)) if req.render_out else None,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Storyboard validation (severity-tagged report)
# ---------------------------------------------------------------------------


@app.post("/api/studio/validate", response_class=PlainTextResponse)
async def studio_validate(req: "StudioValidateRequest", request: Request) -> str:
    """Validate a storyboard.json and return a structured severity report.

    Returns ``StoryboardValidationReport`` JSON:
        {
          "storyboard": "<path>",
          "issues": [ {severity, code, scene_index, message}, ... ],
          "errors":   <int>,
          "warnings": <int>,
          "info":     <int>,
          "ok":       <bool>
        }
    """
    _enforce_memory_cap(request)
    sb_path = _check_inside(req.storyboard_path)
    if not sb_path.exists():
        raise HTTPException(status_code=400, detail=f"storyboard not found: {sb_path}")

    from melosviz.conductor.validate import validate_storyboard

    payload = json.loads(sb_path.read_text())
    report = validate_storyboard(payload, storyboard_path=str(sb_path))
    return json.dumps(report.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# SSE — live render queue events (queued / rendering / done / error per scene)
# ---------------------------------------------------------------------------

import asyncio
import json as _json


@app.get("/api/render/events")
async def render_events(job_id: str | None = None, since_ms: int = 0) -> object:
    """Server-Sent Events stream of orchestrator render progress.

    Clients (web StudioConsole, desktop Director's Console) open an
    ``EventSource('/api/render/events?job_id=...')`` and receive one
    ``data: <json>\\n\\n`` SSE frame per RenderEvent. Frames are flushed
    every 250ms while the connection is open and the bus has new events.

    Query params:
        job_id  — only emit events for this job (None = all jobs)
        since_ms — replay buffered events newer than this timestamp
                  (useful when a client reconnects mid-render)
    """
    from fastapi.responses import StreamingResponse

    from melosviz.conductor.events import get_bus

    bus = get_bus()

    async def event_stream():
        last_seen_ms = int(since_ms)
        # Replay buffered events older than the connection start so a
        # reconnecting client doesn't lose the queued/rendering events that
        # fired while it was offline.
        for evt in bus.recent(job_id=job_id, since_ms=last_seen_ms):
            last_seen_ms = max(last_seen_ms, evt.ts_ms + 1)
            yield f"data: {_json.dumps(evt.to_dict())}\n\n"

        while True:
            # Drain anything emitted since last flush, then sleep briefly
            await asyncio.sleep(0.25)
            for evt in bus.recent(job_id=job_id, since_ms=last_seen_ms):
                last_seen_ms = max(last_seen_ms, evt.ts_ms + 1)
                yield f"data: {_json.dumps(evt.to_dict())}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/render/events/recent")
async def render_events_recent(
    job_id: str | None = None, since_ms: int = 0
) -> dict[str, object]:
    """JSON snapshot of buffered events for clients that don't want SSE.

    Returns the same shape the SSE stream emits, in a single response. Useful
    for polling clients (e.g. older desktop builds) and for tests.
    """
    from melosviz.conductor.events import get_bus

    bus = get_bus()
    events = [evt.to_dict() for evt in bus.recent(job_id=job_id, since_ms=since_ms)]
    return {"events": events, "count": len(events)}


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
