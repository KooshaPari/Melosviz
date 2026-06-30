"""Thin HTTP bridge between the Electrobun desktop shell and the melosviz backend.

Exposes a small FastAPI app that the Bun main process talks to over localhost.
The bridge is an *optional* performance optimisation: if FastAPI / uvicorn are
not installed, the main process falls back to spawning ``python -m
melosviz.cli.main`` as a subprocess for each request.

Start via::

    python -m melosviz.bridge.server --port 8765

or let the Electrobun main process spawn it automatically.
"""

from __future__ import annotations

import argparse
import json
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
except ImportError:
    print(
        "[melosviz bridge] FastAPI/uvicorn not installed. "
        "Install with:  pip install 'melosviz[bridge]'\n"
        "The desktop app will use the CLI subprocess fallback.",
        file=sys.stderr,
    )
    sys.exit(1)

app = FastAPI(title="MelosViz bridge", version="0.1.0")


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
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_class=PlainTextResponse)
async def analyze(req: AnalyzeRequest) -> str:
    """Analyze a WAV file and return the RenderSpec as JSON text."""
    from melosviz.analysis.audio import spec_from_wav

    wav = Path(req.wav_path)
    if not wav.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {wav}")

    spec = spec_from_wav(wav)
    data = spec.model_dump() if hasattr(spec, "model_dump") else dict(spec)  # type: ignore[arg-type]
    return json.dumps(data, indent=2, default=str)


@app.post("/build", response_class=PlainTextResponse)
async def build(req: BuildRequest) -> str:
    """Analyze a WAV then assemble a render plan; return plan JSON."""
    from melosviz.analysis.audio import spec_from_wav
    from melosviz.compose.assemble import assemble_render_plan

    wav = Path(req.wav_path)
    if not wav.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {wav}")

    spec = spec_from_wav(wav)
    plan = assemble_render_plan(spec, mock_adapters=True)
    return json.dumps(plan, indent=2, default=str)


@app.post("/render", response_class=PlainTextResponse)
async def render(req: RenderRequest) -> str:
    """Run the full conductor pipeline; return output directory path."""
    from melosviz.analysis.audio import spec_from_wav
    from melosviz.compose.assemble import assemble_render_plan

    wav = Path(req.wav_path)
    if not wav.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {wav}")

    out = Path(req.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    spec = spec_from_wav(wav)
    # Use mock_adapters=False to attempt real adapters; they fail-open to mocks
    # if Blender / TouchDesigner are absent.
    plan = assemble_render_plan(spec, mock_adapters=False)
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

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
