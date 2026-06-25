"""Video export helpers for music-video style previews.

This module is a focused, dependency-free FFmpeg wrapper: it takes a
:class:`melosviz.analysis.models.RenderSpec`, generates a small set of
solid-colour PNG frames into a temp directory, and asks ``ffmpeg`` (via
its ``image2`` demuxer) to stitch those frames into a short MP4 or
WebM clip.

Design notes
------------
* The frame renderer uses only :mod:`struct` + :mod:`zlib` (or
  :mod:`PIL` if it happens to be installed), so the module is importable
  in any environment that has CPython. We deliberately avoid taking a
  hard dependency on ``opencv`` / ``numpy`` here so the test suite can
  run on minimal CI images.
* ``subprocess.run`` is invoked at module import time, so the test
  suite can patch it on the fully-qualified name
  ``melosviz.render.video_exporter.subprocess.run`` without the patch
  leaking across modules.
* The pipeline is intentionally simple: this is the FFmpeg wrapper used
  for smoke tests and quick visual sanity checks. Heavier render
  pipelines (multi-pass, audio mixing, real shaders, ...) live in
  separate modules that depend on this one.
"""

from __future__ import annotations

import logging
import os
import shutil
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from melosviz.analysis.models import RenderSpec

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "FFMpegNotFoundError",
    "RenderExportError",
    "export_video",
    "is_ffmpeg_available",
    "_DEFAULT_VIDEO_SIZE",
    "_DEFAULT_VIDEO_DURATION",
    "_DEFAULT_VIDEO_COLOR",
    "_DEFAULT_PALETTE_RGB",
    "_DEFAULT_FRAME_WIDTH",
    "_DEFAULT_FRAME_HEIGHT",
    "_DEFAULT_FPS",
    "_DEFAULT_DURATION_SEC",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimal colour-clip settings used by ``export_video`` for quick smoke tests.
_DEFAULT_VIDEO_SIZE = "320x240"
_DEFAULT_VIDEO_DURATION = 1
_DEFAULT_VIDEO_COLOR = "blue"
# Default palette (RGB hex strings) used to colour-cycle PNG frames when
# the spec does not provide one. Mirrors the melosviz brand palette.
_DEFAULT_PALETTE_RGB: list[str] = [
    "#00f5ff",
    "#ff2fd5",
    "#8a75ff",
]
# Default resolution, fps, and duration used when the spec omits them.
# Resolution is intentionally small so the smoke test completes quickly
# and produces a clip in well under a second on commodity hardware.
_DEFAULT_FRAME_WIDTH = 320
_DEFAULT_FRAME_HEIGHT = 240
_DEFAULT_FPS = 30
_DEFAULT_DURATION_SEC = 1.0


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RenderExportError(RuntimeError):
    """Raised when video rendering or muxing fails."""


class FFMpegNotFoundError(RenderExportError):
    """Raised when the ffmpeg binary cannot be located or spawned."""


# ---------------------------------------------------------------------------
# FFmpeg resolution
# ---------------------------------------------------------------------------

#: Environment variable honoured by :func:`_resolve_ffmpeg_binary`.
#: Useful for pointing the exporter at an ffmpeg build that is not on
#: ``$PATH`` (e.g. a Homebrew install at a non-default prefix).
_FFMPEG_ENV_VAR = "MELOSVIZ_FFMPEG_BIN"


def _resolve_ffmpeg_binary() -> str:
    """Return the path to a working ``ffmpeg`` binary, or raise.

    Lookup order:

    1. The ``MELOSVIZ_FFMPEG_BIN`` environment variable, if set and
       executable.
    2. ``shutil.which("ffmpeg")`` — the standard ``$PATH`` lookup.
    3. ``shutil.which("ffmpeg.exe")`` — a Windows-friendly fallback so
       the same code path works on developer machines and CI runners.

    Each candidate is probed with ``ffmpeg -version`` (so a broken
    binary, e.g. one with a missing shared-library dep, is rejected
    rather than being returned and then failing at the export call).

    Raises:
        FFMpegNotFoundError: When no working candidate could be found.
    """
    candidates: list[str | None] = [
        os.environ.get(_FFMPEG_ENV_VAR),
        shutil.which("ffmpeg"),
        shutil.which("ffmpeg.exe"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = Path(candidate)
        if not candidate_path.exists():
            continue
        try:
            probe = subprocess.run(
                [candidate, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            # The candidate exists on disk but could not be executed
            # (e.g. a missing shared library). Try the next one rather
            # than failing the entire export.
            continue
        if probe.returncode == 0:
            logger.info("ffmpeg resolved: %s", candidate)
            return candidate
    raise FFMpegNotFoundError(
        "Unable to locate a working ffmpeg binary for video export. "
        f"Set the {_FFMPEG_ENV_VAR} environment variable or install "
        "ffmpeg (https://ffmpeg.org/download.html)."
    )


def is_ffmpeg_available() -> bool:
    """Return ``True`` if a working ``ffmpeg`` binary can be resolved.

    This is a thin convenience wrapper around
    :func:`_resolve_ffmpeg_binary` for use in test skip conditions and
    CLI probes. It never raises; a missing binary simply yields
    ``False``.
    """
    try:
        _resolve_ffmpeg_binary()
    except FFMpegNotFoundError:
        return False
    return True


# ---------------------------------------------------------------------------
# PNG frame generation helpers
# ---------------------------------------------------------------------------


def _hex_to_rgb_bytes(color: Any) -> tuple[int, int, int]:
    """Return an ``(r, g, b)`` tuple from a ``#rgb`` / ``#rrggbb`` string.

    Falls back to black for anything that does not parse cleanly so a
    malformed palette entry never aborts the entire export.
    """
    if not isinstance(color, str):
        return (0, 0, 0)
    clean = color.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(channel * 2 for channel in clean)
    if len(clean) != 6:
        return (0, 0, 0)
    try:
        return (
            int(clean[0:2], 16),
            int(clean[2:4], 16),
            int(clean[4:6], 16),
        )
    except ValueError:
        return (0, 0, 0)


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Pack a single PNG chunk: 4-byte length, type, data, 4-byte CRC32."""
    payload = chunk_type + data
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", crc)


def _write_raw_png_rgb(
    path: Path, width: int, height: int, rgb: tuple[int, int, int]
) -> None:
    """Write a solid-colour 8-bit truecolor PNG without any third-party deps.

    Produces a valid PNG (signature + IHDR + IDAT + IEND) using only
    :mod:`struct` and :mod:`zlib` from the standard library. The output
    is consumable by ffmpeg's ``image2`` demuxer.
    """
    if width < 1 or height < 1:
        raise ValueError(f"_write_raw_png_rgb: invalid dimensions {width}x{height}")
    r = int(rgb[0]) & 0xFF
    g = int(rgb[1]) & 0xFF
    b = int(rgb[2]) & 0xFF
    signature = b"\x89PNG\r\n\x1a\n"
    # IHDR: width, height, bit depth 8, colour type 2 (truecolor),
    # compression 0, filter 0, interlace 0.
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    # IDAT: each scanline is one filter byte (0 = None) followed by the
    # RGB pixel data. Concatenate then zlib-compress.
    scanline = b"\x00" + (bytes((r, g, b)) * width)
    raw = scanline * height
    idat = zlib.compress(raw, 9)
    path.write_bytes(
        signature
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _pillow_available() -> bool:
    """Return ``True`` if Pillow is importable in the current interpreter."""
    try:
        import PIL  # noqa: F401

        return True
    except ImportError:
        return False


def _save_solid_png(
    path: Path, width: int, height: int, rgb: tuple[int, int, int]
) -> None:
    """Persist a single solid-colour PNG, preferring Pillow when present.

    Falls back to :func:`_write_raw_png_rgb` (a pure-stdlib writer) if
    Pillow is not installed. Both paths produce a valid PNG that
    ffmpeg can decode with its ``image2`` demuxer.
    """
    if _pillow_available():
        from PIL import Image  # type: ignore[import-not-found]

        Image.new("RGB", (width, height), rgb).save(path, format="PNG")
    else:
        _write_raw_png_rgb(path, width, height, rgb)


def _generate_png_frames(
    frame_dir: Path,
    frame_count: int,
    width: int,
    height: int,
    palette: list[str],
) -> list[Path]:
    """Generate ``frame_count`` solid-colour PNG files in ``frame_dir``.

    Each frame is filled with a colour that cycles through ``palette``
    (so the resulting clip is visually distinct instead of a flat block).
    The frames are named ``frame_00001.png``, ``frame_00002.png``, ...
    in the order ffmpeg's ``image2`` demuxer expects.
    """
    frame_dir.mkdir(parents=True, exist_ok=True)
    colors: list[tuple[int, int, int]] = [
        _hex_to_rgb_bytes(color) for color in (palette or _DEFAULT_PALETTE_RGB)
    ]
    if not colors:
        colors = [_hex_to_rgb_bytes(_DEFAULT_PALETTE_RGB[0])]
    paths: list[Path] = []
    for index in range(frame_count):
        color = colors[index % len(colors)]
        frame_path = frame_dir / f"frame_{index + 1:05d}.png"
        _save_solid_png(frame_path, width, height, color)
        paths.append(frame_path)
    return paths


def _coerce_metadata(spec: Any) -> dict[str, Any]:
    """Return the ``metadata`` dict from a :class:`RenderSpec` or dict."""
    if spec is None:
        return {}
    if isinstance(spec, dict):
        raw = spec.get("metadata")
        return raw if isinstance(raw, dict) else {}
    if hasattr(spec, "metadata"):
        raw = spec.metadata
        return raw if isinstance(raw, dict) else {}
    return {}


def _extract_palette(spec: Any) -> list[str]:
    """Return a list of colour strings from a :class:`RenderSpec` or dict."""
    if spec is None:
        return list(_DEFAULT_PALETTE_RGB)
    if isinstance(spec, dict):
        raw = spec.get("palette") or []
    else:
        raw = getattr(spec, "palette", None) or []
    palette = [str(color) for color in raw]
    if not palette:
        return list(_DEFAULT_PALETTE_RGB)
    return palette


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def export_video(
    spec: RenderSpec,
    format: str = "mp4",
    output_dir: Path | str | None = None,
) -> Path:
    """Render a short clip from a ``RenderSpec`` by feeding PNG frames to ffmpeg.

    The render pipeline is intentionally simple so it can be used as a
    CI smoke test or a quick visual sanity check:

    1. Pull ``width``/``height``/``fps``/``duration`` out of
       ``spec.metadata`` (falling back to sane defaults).
    2. Generate one PNG frame per tick of ``duration * fps`` into a
       fresh :class:`tempfile.TemporaryDirectory` (using Pillow when it
       is available, otherwise writing the PNG bytes directly with
       :mod:`struct` and :mod:`zlib`).
    3. Concat those frames into the requested container via ffmpeg's
       ``image2`` demuxer and the appropriate codec
       (``libx264``/``yuv420p`` for ``mp4``, ``libvpx-vp9`` for
       ``webm``).

    Args:
        spec: ``RenderSpec`` (or a plain ``dict`` shaped like one)
            describing the desired render. ``spec.metadata`` is
            consulted for ``width``, ``height``, ``fps``, and
            ``duration``; ``spec.palette`` colours the generated
            frames.
        format: Output container. Supported values: ``"mp4"`` (default)
            and ``"webm"``. Comparison is case-insensitive.
        output_dir: Directory to write the output file into. Created if
            it does not already exist. When ``None`` (the default) the
            exporter falls back to ``<tempdir>/melosviz-exports``.

    Returns:
        Absolute :class:`Path` to the produced video file.

    Raises:
        FFMpegNotFoundError: If no working ``ffmpeg`` binary is found
            (via the ``MELOSVIZ_FFMPEG_BIN`` override or ``$PATH``),
            or if spawning the binary fails with :class:`OSError`.
        RenderExportError: If ``format`` is unsupported, ffmpeg
            returns a non-zero exit code, or the produced file is
            missing / empty.
    """
    # ---- 1. Validate format ---------------------------------------------
    fmt = (format or "").lower().strip()
    if fmt == "mp4":
        extension = "mp4"
        codec_args: list[str] = [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ]
    elif fmt == "webm":
        extension = "webm"
        codec_args = [
            "-c:v",
            "libvpx-vp9",
            "-b:v",
            "200k",
        ]
    else:
        raise RenderExportError(
            f"Unsupported export format: {format!r}. " "Expected 'mp4' or 'webm'."
        )

    # ---- 2. Resolve ffmpeg ----------------------------------------------
    ffmpeg = _resolve_ffmpeg_binary()

    # ---- 3. Pull render parameters from the spec ------------------------
    metadata = _coerce_metadata(spec)
    width = max(1, int(metadata.get("width", _DEFAULT_FRAME_WIDTH)))
    height = max(1, int(metadata.get("height", _DEFAULT_FRAME_HEIGHT)))
    fps = max(1, int(metadata.get("fps", _DEFAULT_FPS)))
    try:
        duration_sec = float(metadata.get("duration", _DEFAULT_DURATION_SEC))
    except (TypeError, ValueError):
        duration_sec = _DEFAULT_DURATION_SEC
    if duration_sec <= 0.0:
        duration_sec = _DEFAULT_DURATION_SEC
    total_frames = max(1, int(round(duration_sec * fps)))
    palette = _extract_palette(spec)

    # ---- 4. Resolve output directory ------------------------------------
    if output_dir is None:
        output_dir = Path(tempfile.gettempdir()) / "melosviz-exports"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"melosviz-render.{extension}"

    logger.info(
        "export_video: format=%s width=%d height=%d fps=%d duration=%.2fs "
        "frames=%d output_dir=%s",
        fmt,
        width,
        height,
        fps,
        duration_sec,
        total_frames,
        output_dir,
    )

    # ---- 5. Generate PNG frames in a tempdir -----------------------------
    with tempfile.TemporaryDirectory(prefix="melosviz-frames-") as tmp:
        frame_dir = Path(tmp)
        _generate_png_frames(frame_dir, total_frames, width, height, palette)
        frame_pattern = frame_dir / "frame_%05d.png"

        # ---- 6. Concat frames with ffmpeg ---------------------------------
        cmd: list[str] = [
            ffmpeg,
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frame_pattern),
            *codec_args,
            str(output_path),
        ]

        logger.debug("export_video: ffmpeg cmd=%s", cmd)

        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except OSError as exc:
            raise FFMpegNotFoundError(
                f"Failed to start ffmpeg binary at {ffmpeg!r}: {exc}. "
                "Ensure ffmpeg is installed and on PATH, or set the "
                "MELOSVIZ_FFMPEG_BIN environment variable."
            ) from exc

        if completed.returncode != 0:
            stderr_snippet = (completed.stderr or "").strip().splitlines()
            tail = "\n".join(stderr_snippet[-5:]) if stderr_snippet else ""
            raise RenderExportError(
                f"ffmpeg export failed (rc={completed.returncode}) "
                f"for format={fmt!r}. Tail of stderr:\n{tail}"
            )

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RenderExportError(
                f"ffmpeg reported success but no output was produced at "
                f"{output_path}."
            )

        logger.info(
            "export_video: wrote %s (%d bytes, format=%s, frames=%d)",
            output_path,
            output_path.stat().st_size,
            fmt,
            total_frames,
        )
        return output_path
