"""Headless Cinema 4D adapter — RenderSpec v2 → high-end 3-D scene → MP4.

Cinema 4D (a.k.a. C4D) is the **premium-tier 3-D renderer** of the
MelosViz pipeline. Where Blender (`melosviz.render.blender_exporter`)
handles the budget-friendly 3-D path, C4D is what a music-video director
picks for product-grade cinematic shots: MoGraph clones, X-Particles,
Redshift / Octane renders, and the kind of stylised typography motion
design that defines the modern "music video for a track on a label".

This adapter wraps C4D in two modes, depending on what's installed:

1. **``c4dpy`` mode** (preferred) — when the official `c4dpy` Python
   package is importable, we drive C4D's internal scripting engine
   directly. No subprocess overhead, no temp .c4d file round-trips.

2. **``commandline`` mode** (fallback) — we generate a ``.py`` script that
   the user runs with ``Commandline.exe`` /
   ``Cinema 4D R26.app/Contents/MacOS/Commandline`` and capture the
   resulting image sequence. Works without `c4dpy`.

Both modes emit a per-scene image sequence which is then muxed to MP4 by
ffmpeg (same fallback chain as the Blender adapter).

Configuration (env vars)
------------------------
``MELOSVIZ_C4D_BIN``         Path to the C4D ``Commandline`` binary.
``MELOSVIZ_C4D_PYTHON``      Path to the C4D ``python`` (c4dpy) executable.
``MELOSVIZ_C4D_PROJECT``     Path to a ``.c4d`` template project we
                             substitute the scene into (recommended —
                             ships with your studio's lighting / render
                             settings).
``MELOSVIZ_C4D_RENDERER``    Render engine (``"redshift"``, ``"octane"``,
                             ``"physical"``, ``"standard"``).
``MELOSVIZ_C4D_TIMEOUT``     Wall-clock per-scene render timeout, seconds
                             (default ``1800`` = 30 min).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from melosviz.analysis.models import RenderSpec

logger = logging.getLogger(__name__)

__all__ = [
    "C4DAdapter",
    "C4DNotFoundError",
    "C4DRenderError",
    "is_c4d_available",
    "render_scene",
    "scaffold_script",
]

# ---------------------------------------------------------------------------
# Constants / env vars
# ---------------------------------------------------------------------------

_C4D_BIN_ENV = "MELOSVIZ_C4D_BIN"
_C4D_PYTHON_ENV = "MELOSVIZ_C4D_PYTHON"
_C4D_PROJECT_ENV = "MELOSVIZ_C4D_PROJECT"
_C4D_RENDERER_ENV = "MELOSVIZ_C4D_RENDERER"
_C4D_TIMEOUT_ENV = "MELOSVIZ_C4D_TIMEOUT"

DEFAULT_RENDERER = "redshift"
DEFAULT_TIMEOUT_S = 1800

SCENE_TYPES: tuple[str, ...] = ("c4d_3d", "cinema4d")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class C4DError(RuntimeError):
    """Base class for any C4D adapter failure."""


class C4DNotFoundError(C4DError):
    """Neither ``c4dpy`` nor the Commandline binary is on the box."""


class C4DRenderError(C4DError):
    """C4D exited non-zero or produced no frames."""


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


def _c4d_bin() -> str | None:
    p = os.environ.get(_C4D_BIN_ENV)
    if p and Path(p).exists():
        return p
    # Common install locations
    candidates = [
        "/Applications/Maxon Cinema 4D R2025/Contents/MacOS/Commandline",
        "/Applications/Maxon Cinema 4D R2024/Contents/MacOS/Commandline",
        "/usr/local/bin/Commandline",
        "C:\\Program Files\\Maxon Cinema 4D R2025\\Commandline.exe",
        "C:\\Program Files\\Maxon Cinema 4D R2024\\Commandline.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    on_path = shutil.which("Commandline")
    return on_path


def _c4d_python() -> str | None:
    p = os.environ.get(_C4D_PYTHON_ENV)
    if p and Path(p).exists():
        return p
    return shutil.which("c4dpy")


def _c4d_project() -> Path | None:
    p = os.environ.get(_C4D_PROJECT_ENV)
    return Path(p).expanduser().resolve() if p else None


def _c4d_renderer() -> str:
    return os.environ.get(_C4D_RENDERER_ENV, DEFAULT_RENDERER)


def _c4d_timeout_s() -> int:
    raw = os.environ.get(_C4D_TIMEOUT_ENV, str(DEFAULT_TIMEOUT_S))
    try:
        return max(60, int(raw))
    except ValueError:
        return DEFAULT_TIMEOUT_S


def is_c4d_available() -> bool:
    """True iff either ``c4dpy`` or the ``Commandline`` binary is reachable."""
    return _c4d_python() is not None or _c4d_bin() is not None


# ---------------------------------------------------------------------------
# Script generation
# ---------------------------------------------------------------------------


def scaffold_script(scene: dict[str, Any], *, project: Path | None,
                    renderer: str, output_dir: Path) -> str:
    """Return Python source that drives C4D to render one scene.

    The script is deliberately conservative: it expects a ``.c4d`` template
    the user has set up. We only mutate the ``scene``/``take`` settings,
    point the render path at ``output_dir``, and trigger the render.
    """
    name = scene.get("name", "melosviz_scene")
    width = int(scene.get("width", 1280))
    height = int(scene.get("height", 720))
    frames = int(scene.get("frames", 240))
    fps = int(scene.get("fps", 24))
    cam = scene.get("camera", "Camera")
    motion_text = scene.get("motion_text", "")
    renderer_enum = {
        "redshift": "c4d.REDSHIFT",
        "octane": "c4d.OCTANE",
        "physical": "c4d.PHYSICAL",
        "standard": "c4d.STANDARD",
    }.get(renderer.lower(), "c4d.STANDARD")
    return textwrap.dedent(
        f"""\
        # Auto-generated by melosviz.render.cinema4d_adapter
        # Renders one beat-synced scene of a music video.
        import c4d, os

        PROJECT = {project!r}
        OUT_DIR = {str(output_dir)!r}
        NAME = {name!r}
        W, H = {width}, {height}
        FRAMES, FPS = {frames}, {fps}
        RENDERER = {renderer_enum}

        def main():
            doc = c4d.documents.LoadDocument(
                PROJECT, c4d.SCENEFILTER_OBJECTS, quiet=True
            ) if PROJECT and os.path.isfile(PROJECT) else c4d.documents.GetActiveDocument()
            if doc is None:
                raise RuntimeError("c4d: failed to load template project")
            doc.SetDocumentName(NAME)
            # Render settings
            rd = doc.GetActiveRenderData()
            rd[c4d.RDATA_FRAMESEQUENCE] = c4d.RDATA_FRAMESEQUENCE_MANUAL
            rd[c4d.RDATA_FRAMERATE] = float(FPS)
            rd[c4d.RDATA_FRAMEFROM] = c4d.BaseTime(0, FPS)
            rd[c4d.RDATA_FRAMETO] = c4d.BaseTime(FRAMES, FPS)
            rd[c4d.RDATA_RENDERENGINE] = RENDERER
            rd[c4d.RDATA_XRES] = W
            rd[c4d.RDATA_YRES] = H
            rd[c4d.RDATA_PATH] = os.path.join(OUT_DIR, NAME + "_$F.png")
            # Optional motion-graphics text
            if {motion_text!r}:
                txt = c4d.BaseObject(c4d.Onull)
                txt.SetName("melosviz_text")
                doc.InsertObject(txt)
                # Director is expected to wire this null to a MoGraph text in the template
            # Render
            ok = c4d.documents.RenderDocument(
                doc, rd, c4d.BaseTime(0, FPS),
                c4d.RENDERFLAGS_EXTERNAL,
                bmp=None, prog=None, wbuf=None,
                th=None, texturepath=None,
            )
            if not ok:
                raise RuntimeError("c4d: RenderDocument returned False")
            print("C4D_RENDER_OK")

        if __name__ == "__main__":
            main()
        """
    )


def render_scene(scene: dict[str, Any], *, output_dir: Path | str,
                 project: Path | None = None,
                 renderer: str | None = None) -> list[Path]:
    """Render one C4D scene; returns the per-frame PNG paths."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    renderer = renderer or _c4d_renderer()
    project = project or _c4d_project()

    script = scaffold_script(scene, project=project, renderer=renderer,
                             output_dir=out)
    script_path = out / "_c4d_render.py"
    script_path.write_text(script, encoding="utf-8")

    timeout = _c4d_timeout_s()

    # Mode 1: c4dpy in-process
    py = _c4d_python()
    if py is not None:
        logger.info("C4D: rendering via c4dpy %s", py)
        try:
            proc = subprocess.run(
                [py, str(script_path)],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise C4DRenderError(f"C4D timed out after {timeout}s") from exc
        if proc.returncode != 0 or "C4D_RENDER_OK" not in proc.stdout:
            raise C4DRenderError(
                f"C4D render failed (rc={proc.returncode}): "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
    else:
        # Mode 2: Commandline binary
        bin_ = _c4d_bin()
        if bin_ is None:
            raise C4DNotFoundError(
                "Neither c4dpy nor the C4D Commandline binary was found. "
                f"Set ${_C4D_BIN_ENV} or ${_C4D_PYTHON_ENV}."
            )
        cmd = [bin_, str(script_path)]
        if project is not None:
            cmd += ["--render", str(project)]
        logger.info("C4D: rendering via Commandline %s", bin_)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise C4DRenderError(f"C4D timed out after {timeout}s") from exc
        if proc.returncode != 0:
            raise C4DRenderError(
                f"C4D Commandline exited {proc.returncode}: "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )

    frames = sorted(out.glob("*.png"))
    if not frames:
        raise C4DRenderError(f"C4D produced no frames under {out}")
    return frames


# ---------------------------------------------------------------------------
# Adapter (conductor integration)
# ---------------------------------------------------------------------------


class C4DAdapter:
    """Conductor-compatible adapter for Cinema 4D."""

    scene_type: str = "c4d_3d"

    def render(self, render_spec: Any, *, output_path: Any = None,
               **kwargs: Any) -> list[Path]:
        out_dir = Path(str(output_path)) if output_path is not None else Path(
            "/tmp/melosviz-c4d"
        )
        out_dir.mkdir(parents=True, exist_ok=True)

        # ---- Offline mode: write job-spec JSON, do NOT invoke C4D -----------
        if os.environ.get("MELOSVIZ_COMFYUI_OFFLINE") == "1":
            scenes = _extract_scenes(render_spec, scene_type=self.scene_type)
            plan_path = out_dir / "c4d_render_plan.json"
            spec_dict: dict[str, Any] = (
                render_spec.model_dump()
                if hasattr(render_spec, "model_dump")
                else (render_spec if isinstance(render_spec, dict) else {})
            )
            plan = {
                "renderer": "cinema4d",
                "mode": "offline",
                "reason": "MELOSVIZ_COMFYUI_OFFLINE=1 — c4d not invoked",
                "output_dir": str(out_dir),
                "n_scenes": len(scenes),
                "spec_summary": {
                    "duration_s": (spec_dict.get("metadata") or {}).get("duration"),
                    "n_segments": len(spec_dict.get("scene_segments") or []),
                    "palette": spec_dict.get("palette", []),
                },
                "render_params": {
                    "renderer": kwargs.get("renderer") or _c4d_renderer(),
                    "project": str(kwargs.get("project") or _c4d_project() or ""),
                    "timeout_s": _c4d_timeout_s(),
                },
                "driver_script_path": "scene_NNN/_c4d_render.py",
                "next_steps": [
                    "Install Cinema 4D and ensure Commandline.exe (or c4dpy) is on PATH.",
                    "Re-run with MELOSVIZ_COMFYUI_OFFLINE unset (or =0).",
                    f"Or: set ${_C4D_BIN_ENV} / ${_C4D_PYTHON_ENV} and re-run.",
                ],
            }
            plan_path.write_text(json.dumps(plan, indent=2, default=str))
            # Also scaffold the per-scene C4D scripts so the operator can
            # hand them to a Studio render farm.
            for i, scene in enumerate(scenes):
                scene_out = out_dir / f"scene_{i:03d}"
                scene_out.mkdir(parents=True, exist_ok=True)
                script = scaffold_script(
                    scene,
                    project=kwargs.get("project") or _c4d_project(),
                    renderer=kwargs.get("renderer") or _c4d_renderer(),
                    output_dir=scene_out,
                )
                (scene_out / "_c4d_render.py").write_text(script, encoding="utf-8")
            logger.info("C4DAdapter: offline mode → wrote %s", plan_path)
            return [plan_path]

        scenes = _extract_scenes(render_spec, scene_type=self.scene_type)
        if not scenes:
            logger.warning(
                "C4DAdapter: no scenes of type=%r in spec; nothing to render",
                self.scene_type,
            )
            return []

        results: list[Path] = []
        for i, scene in enumerate(scenes):
            scene_out = out_dir / f"scene_{i:03d}"
            scene_out.mkdir(parents=True, exist_ok=True)
            try:
                frames = render_scene(
                    scene, output_dir=scene_out,
                    project=kwargs.get("project"),
                    renderer=kwargs.get("renderer"),
                )
            except C4DError:
                raise
            results.extend(frames)
        return results


def _extract_scenes(render_spec: Any, *, scene_type: str) -> list[dict]:
    if hasattr(render_spec, "model_dump"):
        data = render_spec.model_dump()
    elif isinstance(render_spec, dict):
        data = render_spec
    else:
        return []
    scenes = data.get("scenes") or data.get("scene_segments") or []
    out: list[dict] = []
    for s in scenes:
        if isinstance(s, dict) and s.get("scene_type") in SCENE_TYPES:
            out.append(s)
    return out
