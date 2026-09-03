"""Deterministic per-clip visual diff.

For every rendered clip, write a ``visual-diff.svg`` next to the artifact
that gives a human + machine a one-look summary:

  * a single extracted frame (when ``ffmpeg`` is on PATH), so reviewers
    can spot motion + composition regressions in seconds,
  * the prompt the clip was generated from (XML-escaped),
  * a beat-aligned timeline strip with tick marks for every beat, and
  * the start/end seconds stamped on the card.

The function also returns a JSON-friendly payload (artifact SHA-256,
preview SHA-256, prompt SHA-256, SVG SHA-256) that the orchestrator
attaches to :class:`~melosviz.conductor.provenance.ClipProvenance` so
operators can diff two runs of the same storyboard with a single
``diff`` over the JSON.

Why "deterministic"
--------------------
SVG markup is generated from the inputs only — no timestamps, no
PIL/ffmpeg hashes leak into the markup. Two identical calls produce
byte-identical SVG, which is essential for repeatable ZIP packaging
(``viz ship`` will refuse to ship a non-reproducible manifest).

Security
--------
User-supplied text is HTML-escaped via :func:`html.escape` with
``quote=True`` and is truncated to 80/180 chars for the scene name and
prompt, so prompt injection via crafted text can't smuggle script
tags, ``href="javascript:..."``, or any other live-URL scheme. The
``<image>`` reference is always a relative local path and is generated
server-side, not from user input.
"""

from __future__ import annotations

import hashlib
import html
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path


FrameExtractor = Callable[[Path, Path], bool]


def _sha256(path: Path) -> str | None:
    """SHA-256 the file at *path*. Return ``None`` if the file is missing."""
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, root: Path) -> str:
    """Return a forward-slashed path relative to *root*; fall back to the file name."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def extract_preview_frame(source: Path, target: Path) -> bool:
    """Use ``ffmpeg`` to pull a single preview frame from *source* → *target*.

    Returns ``True`` only when ffmpeg exits 0 *and* the target file exists
    with non-zero size. Returns ``False`` silently when ffmpeg is missing
    or the source is not a regular file — operators without ffmpeg still
    get a fully usable SVG (just a coloured placeholder instead of a
    frame). Also returns ``False`` on any failure mode (timeout, OS
    error, permission denied) so a broken ffmpeg can never crash the
    render pipeline.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None or not source.is_file():
        return False
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-frames:v",
                "1",
                str(target),
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        # ffmpeg hung, the binary vanished mid-run, or the OS refused
        # the exec — every one of these should degrade to "no preview"
        # rather than crash the orchestrator.
        return False
    return completed.returncode == 0 and target.is_file() and target.stat().st_size > 0


def _timeline_svg(
    *,
    scene_name: str,
    prompt: str,
    start_seconds: float,
    end_seconds: float,
    beat_seconds: Sequence[float],
    palette: Sequence[str],
    has_preview: bool,
) -> str:
    """Render a fixed 960x540 timeline card as a single SVG string.

    Layout:
        +---------------------------------------------------+
        |  Scene name                                      |
        |  +---------------------------------------------+  |
        |  | preview frame OR colour rect                |  |
        |  +---------------------------------------------+  |
        |  Prompt (one line)                               |
        |  |-----|--------|--------|-----|--------|       |  |  ← beat ticks
        |  start - end                                     |
        +---------------------------------------------------+
    """
    duration = max(0.001, end_seconds - start_seconds)
    ticks: list[str] = []
    for beat in beat_seconds:
        position = min(1.0, max(0.0, (float(beat) - start_seconds) / duration))
        x = 48 + round(position * 864, 3)
        ticks.append(
            f'<line x1="{x}" y1="470" x2="{x}" y2="504" stroke="#ffffff" />'
        )
    color = palette[0] if palette and str(palette[0]).startswith("#") else "#202033"
    preview = (
        '<image href="visual-diff-frame.png" x="48" y="72" width="864" '
        'height="330" preserveAspectRatio="xMidYMid slice" />'
        if has_preview
        else f'<rect x="48" y="72" width="864" height="330" fill="{html.escape(color)}" />'
    )
    safe_name = html.escape(scene_name[:80], quote=True)
    safe_prompt = html.escape(" ".join(prompt.split())[:180], quote=True)
    tick_markup = "".join(ticks)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" '
        'viewBox="0 0 960 540">\n'
        '<rect width="960" height="540" fill="#0d0d10" />\n'
        f'{preview}\n'
        f'<text x="48" y="40" fill="#ffffff" font-size="24">{safe_name}</text>\n'
        f'<text x="48" y="438" fill="#ffffff" font-size="18">{safe_prompt}</text>\n'
        '<line x1="48" y1="487" x2="912" y2="487" stroke="#888899" />\n'
        f'{tick_markup}\n'
        f'<text x="48" y="526" fill="#ccccd8" font-size="16">'
        f'{start_seconds:.3f}s - {end_seconds:.3f}s</text>\n'
        '</svg>\n'
    )


def build_visual_diff(
    *,
    artifact_path: Path,
    scene_dir: Path,
    job_dir: Path,
    scene_name: str,
    prompt: str,
    start_seconds: float,
    end_seconds: float,
    beat_seconds: Sequence[float],
    palette: Sequence[str],
    frame_extractor: FrameExtractor = extract_preview_frame,
) -> dict:
    """Build the visual diff artefacts for a single clip and return the manifest.

    Writes two files into *scene_dir*:

      * ``visual-diff-frame.png`` — only when the frame extractor returns True.
      * ``visual-diff.svg``     — always, with the rendered preview (or a
        coloured placeholder when the frame extractor returned False).

    The returned dict is the canonical sidecar manifest (artifact hash,
    prompt hash, timeline hash, paths relative to *job_dir*) that the
    orchestrator attaches to the clip's
    :class:`~melosviz.conductor.provenance.ClipProvenance`.
    """
    scene_dir.mkdir(parents=True, exist_ok=True)
    preview = scene_dir / "visual-diff-frame.png"
    try:
        extracted = bool(frame_extractor(artifact_path, preview))
    except (subprocess.TimeoutExpired, OSError, ValueError):
        # Custom FrameExtractor implementations may raise; the built-in
        # extract_preview_frame already swallows these, but third-party
        # extractors shouldn't be able to crash the orchestrator either.
        extracted = False
    if not extracted and preview.exists():
        preview.unlink()
    svg_path = scene_dir / "visual-diff.svg"
    svg_path.write_text(
        _timeline_svg(
            scene_name=scene_name,
            prompt=prompt,
            start_seconds=float(start_seconds),
            end_seconds=float(end_seconds),
            beat_seconds=beat_seconds,
            palette=palette,
            has_preview=extracted,
        ),
        encoding="utf-8",
    )
    normalized_prompt = " ".join(prompt.split())
    return {
        "schema_version": "1.0",
        "rendered": {
            "path": _relative(artifact_path, job_dir),
            "sha256": _sha256(artifact_path),
            "preview_path": _relative(preview, job_dir) if extracted else None,
            "preview_sha256": _sha256(preview) if extracted else None,
        },
        "prompt": {
            "text": normalized_prompt,
            "sha256": hashlib.sha256(normalized_prompt.encode()).hexdigest(),
        },
        "timeline_thumbnail": {
            "path": _relative(svg_path, job_dir),
            "sha256": _sha256(svg_path),
            "start_seconds": float(start_seconds),
            "end_seconds": float(end_seconds),
            "beat_seconds": [float(value) for value in beat_seconds],
        },
    }


def compute_visual_diff(
    artifact_path: str | Path,
    prompt: str,
    *,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
    beat_seconds: Sequence[float] | None = None,
    palette: Sequence[str] | None = None,
) -> dict:
    """Orchestrator-facing wrapper around :func:`build_visual_diff`.

    Accepts the minimal set of arguments the orchestrator has readily
    available (``artifact_path`` + ``prompt``). Sensible defaults are used
    for all timeline fields so callers that don't know the beat map can
    still invoke this function without errors.
    """
    artifact = Path(artifact_path)
    scene_dir = artifact.parent
    job_dir = scene_dir  # visual-diff.svg lives next to the artifact
    # Use ``is None`` rather than truthiness — ``end_seconds=0.0`` is a
    # valid value (a zero-length clip) and must not be silently widened
    # to ``start + 8``.
    resolved_end = start_seconds + 8.0 if end_seconds is None else end_seconds
    return build_visual_diff(
        artifact_path=artifact,
        scene_dir=scene_dir,
        job_dir=job_dir,
        scene_name=artifact.stem,
        prompt=prompt,
        start_seconds=start_seconds,
        end_seconds=resolved_end,
        beat_seconds=beat_seconds or [],
        palette=palette or [],
        frame_extractor=extract_preview_frame,
    )


__all__ = [
    "FrameExtractor",
    "build_visual_diff",
    "compute_visual_diff",
    "extract_preview_frame",
]
