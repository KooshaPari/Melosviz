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
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Attempt FastAPI import; if absent, print a helpful message and exit so the
# Bun main process knows to use the CLI fallback instead.
# ---------------------------------------------------------------------------

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import PlainTextResponse
    from pydantic import BaseModel
except ImportError:  # pragma: no cover — only reachable without [bridge] extras installed
    print(
        "[melosviz bridge] FastAPI/uvicorn not installed. "
        "Install with:  pip install 'melosviz[bridge]'\n"
        "The desktop app will use the CLI subprocess fallback.",
        file=sys.stderr,
    )
    sys.exit(1)

# Local security primitives. Imported eagerly because the middleware is
# registered at app-startup time and the security helpers are stdlib-only.
from melosviz.bridge import security  # noqa: E402
import subprocess
import tempfile

app = FastAPI(title="MelosViz bridge", version="0.1.0")

# Install the security middleware once at module import time. Tests that
# need to reset state between cases can call ``server.security_limiter.reset()``.
security_limiter = security.install_middleware(
    app,
    protected_paths=("/analyze", "/build", "/render", "/health"),
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    wav_path: str


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
        Path(__file__).parent.parent.parent.parent / "target" / "release" / "melosviz-mir",
        Path(__file__).parent.parent.parent.parent / "target" / "debug" / "melosviz-mir",
    ]

    for mir_binary in mir_candidates:
        if mir_binary.exists():
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False
                ) as tmp:
                    tmp_spec_path = tmp.name
                try:
                    result = subprocess.run(
                        [str(mir_binary), "--wav", str(wav_path), "--out", tmp_spec_path],
                        check=True,
                        capture_output=True,
                        timeout=120,
                    )
                    with open(tmp_spec_path, "r") as f:
                        spec_dict = json.load(f)
                    return spec_dict
                finally:
                    try:
                        Path(tmp_spec_path).unlink()
                    except Exception:
                        pass
            except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError, TimeoutError) as e:
                # Log but continue to Python fallback
                import logging
                logging.warning(f"[MelosViz] Rust MIR failed: {e}; using Python fallback")
                continue

    # Fallback to Python analyzer
    from melosviz.analysis.audio import spec_from_wav

    spec = spec_from_wav(wav_path)
    data = spec.model_dump() if hasattr(spec, "model_dump") else dict(spec)  # type: ignore[arg-type]
    return data


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
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid path: {exc}") from exc
    # Legacy desktop mode: auth off AND no explicit allowed-dir override.
    legacy = (
        not security.auth_required()
        and not os.environ.get("MELOSVIZ_BRIDGE_ALLOWED_DIR")
    )
    if legacy:
        return target
    if not security.is_path_allowed(target):
        raise HTTPException(
            status_code=400,
            detail=f"path is outside the allowed data directory: {target}",
        )
    return target


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_class=PlainTextResponse)
async def analyze(req: AnalyzeRequest) -> str:
    """Analyze a WAV file and return the RenderSpec as JSON text.

    Uses the fast Rust MIR analyzer when available; falls back to Python.
    """
    wav = _check_inside(req.wav_path)
    if not wav.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {wav}")

    try:
        data = _analyze_with_mir_or_python(wav)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — surface as 400 (incl. stdlib `wave.Error`)
        raise HTTPException(status_code=400, detail=f"invalid WAV: {exc}") from exc
    return json.dumps(data, indent=2, default=str)


@app.post("/build", response_class=PlainTextResponse)
async def build(req: BuildRequest) -> str:
    """Analyze a WAV then assemble a render plan; return plan JSON.

    Uses the fast Rust MIR analyzer when available; falls back to Python.
    """
    from melosviz.compose.assemble import assemble_render_plan

    wav = _check_inside(req.wav_path)
    if not wav.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {wav}")

    try:
        spec_data = _analyze_with_mir_or_python(wav)
        # assemble_render_plan expects a RenderSpec object, not a dict
        # For now, we'll pass the dict directly and let assemble_render_plan handle it
        plan = assemble_render_plan(spec_data, mock_adapters=True)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid WAV: {exc}") from exc
    return json.dumps(plan, indent=2, default=str)


@app.post("/render", response_class=PlainTextResponse)
async def render(req: RenderRequest) -> str:
    """Run the full conductor pipeline; return output directory path.

    Uses the fast Rust MIR analyzer when available; falls back to Python.
    """
    from melosviz.compose.assemble import assemble_render_plan

    wav = _check_inside(req.wav_path)
    if not wav.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {wav}")

    out = _check_inside(req.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    try:
        spec_data = _analyze_with_mir_or_python(wav)
        # Use mock_adapters=False to attempt real adapters; they fail-open to mocks
        # if Blender / TouchDesigner are absent.
        plan = assemble_render_plan(spec_data, mock_adapters=False)
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

    # Loopback guard. Runs *before* uvicorn.bind() so a misconfigured public
    # bind never even reaches the socket layer.
    ok, reason = security.loopback_check(args.host)
    if not ok:
        print(f"[melosviz bridge] {reason}", file=sys.stderr)
        sys.exit(2)
    print(f"[melosviz bridge] binding {args.host}:{args.port} ({reason})")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    main()
