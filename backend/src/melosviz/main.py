"""Melosviz FastAPI application and CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from melosviz.analysis import AudioAnalysisEngine, AnalysisResult
from melosviz.analysis.engine import AudioDecodeError
from melosviz.analysis.models import (
    AnalyzeRequest,
    AnalysisType,
    GenreTheme,
    RenderStyle,
    VisualizeRequest,
    VisualizeResponse,
)
from melosviz.presets import ThemePresetRegistry
from melosviz.render import VisualizationSpecBuilder

logger = logging.getLogger(__name__)

app = FastAPI(title="Melosviz API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = AudioAnalysisEngine()
presets_registry = ThemePresetRegistry()
builder = VisualizationSpecBuilder()


class TemporaryUploadWriteError(Exception):
    """Raised when an uploaded file cannot be written to a temporary path."""


def _temp_suffix(file: UploadFile) -> str:
    """Choose a safe suffix for a temporary upload file."""
    suffix = Path(file.filename).suffix.lower() if file.filename else ""
    return suffix if suffix else ".wav"


def _write_temp_audio(file: UploadFile) -> Path:
    """Persist uploaded bytes in a unique temporary file."""
    suffix = _temp_suffix(file)
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, prefix="melosviz-"
        ) as handle:
            file.seek(0)
            shutil.copyfileobj(file.file, handle)
            return Path(handle.name)
    except Exception as exc:
        raise TemporaryUploadWriteError(
            f"Unable to store uploaded audio temporarily: {exc}"
        ) from None


def _cleanup_temp_audio(path: Path | None) -> None:
    """Best-effort cleanup for temporary uploaded audio files."""
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


@app.get("/v1/health")
def health() -> dict[str, str]:
    """Return service health status."""
    return {"status": "ok"}


@app.get("/v1/presets")
def presets() -> list[object]:
    """Return all theme presets."""
    return presets_registry.get_all_presets()


@app.post("/v1/audio/analyze", response_model=AnalysisResult)
def analyze_audio(
    file: UploadFile = File(...),
    request: str = Form(...),
) -> AnalysisResult:
    """Analyze an uploaded audio file."""
    temp_path: Path | None = None
    try:
        temp_path = _write_temp_audio(file)
        req = AnalyzeRequest.model_validate_json(request)
        result = engine.full_analysis(temp_path, request=req)
    except TemporaryUploadWriteError as exc:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=str(exc),
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found",
        )
    except AudioDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        )
    except (OSError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    finally:
        _cleanup_temp_audio(temp_path)
    return result


@app.post("/v1/audio/visualize")
def visualize_audio(
    file: UploadFile = File(...),
    payload: str = Form(...),
    theme: str = Form("dark_street"),
    analysis: str = Form("full"),
    fps: int = Form(60),
    width: int = Form(1920),
    height: int = Form(1080),
    duration_sec: float = Form(30.0),
    export_format: str = Form("html"),
    seed: int = Form(0),
) -> VisualizeResponse:
    """Analyze uploaded audio and build visualization layers."""
    temp_path: Path | None = None
    try:
        temp_path = _write_temp_audio(file)
        payload_data = json.loads(payload)
        request = VisualizeRequest.model_validate(payload_data)
        requested_theme = GenreTheme(theme)
        selected_preset = presets_registry.get_preset(requested_theme)
        analysis_request = AnalyzeRequest(
            source_file=str(temp_path),
            analysis=request.analysis,
            style=request.style,
            preset=selected_preset,
            fps=request.fps,
            width=request.width,
            height=request.height,
            duration_sec=request.duration_sec,
            export_format=request.export_format,
            seed=request.seed,
        )
        analysis_result = engine.full_analysis(temp_path, request=analysis_request)
        render = builder.build_spec(
            analysis=analysis_result,
            style=request.style,
            preset=selected_preset,
            fps=request.fps,
            width=request.width,
            height=request.height,
            duration_sec=request.duration_sec,
            export_format=request.export_format,
            seed=request.seed,
        )
        return VisualizeResponse(
            status="ok",
            message="Visualization spec generated",
            analysis=analysis_result,
            selected_theme=selected_preset,
            render=render,
            keyframes=len(render.keyframes),
        )
    except TemporaryUploadWriteError as exc:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=str(exc),
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found",
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid payload JSON: {exc}",
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        )
    finally:
        _cleanup_temp_audio(temp_path)


def cli() -> None:
    """Command-line interface with local analyze and visualize helpers."""
    parser = argparse.ArgumentParser(prog="melosviz")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8000)

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("file")
    analyze_parser.add_argument("--theme", default="dark_street")

    visualize_parser = subparsers.add_parser("visualize")
    visualize_parser.add_argument("file")
    visualize_parser.add_argument("--theme", default="dark_street")

    args = parser.parse_args()

    if args.command == "serve":
        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port)
    elif args.command == "analyze":
        result = engine.full_analysis(args.file)
        print(result.model_dump_json(indent=2))
    elif args.command == "visualize":
        requested_theme = GenreTheme(args.theme)
        preset = presets_registry.get_preset(requested_theme)
        render = builder.build_spec(
            analysis=engine.full_analysis(args.file),
            style=RenderStyle(),
            preset=preset,
            fps=60,
            width=1920,
            height=1080,
            duration_sec=30.0,
            export_format="html",
            seed=0,
        )
        print(
            VisualizeResponse(
                status="ok",
                message="Visualization spec generated",
                analysis=engine.full_analysis(args.file),
                selected_theme=preset,
                render=render,
                keyframes=len(render.keyframes),
            ).model_dump_json(indent=2)
        )
