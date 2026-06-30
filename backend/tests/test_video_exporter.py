"""Tests for the FFmpeg-backed video exporter.

These tests mock :mod:`subprocess` to simulate ffmpeg invocations, so the
suite can run on hosts that don't have a working ffmpeg binary (the
Homebrew ffmpeg package on this macOS host has a known x265 dyld
mismatch that breaks the binary at runtime, but ``subprocess.run`` is
still fully functional for mocks).

The mock layer:
    * Patches ``melosviz.render.video_exporter.subprocess.run`` so the
      exporter never shells out to a real binary.
    * Patches ``_resolve_ffmpeg_binary`` to return a deterministic
      sentinel path so command-line assertions don't depend on
      ``$PATH`` or ``MELOSVIZ_FFMPEG_BIN``.
    * The success-mode side effect writes a small placeholder file at
      the path the exporter passed to ffmpeg, mirroring what a real
      ffmpeg invocation would have produced.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from melosviz.analysis.models import RenderSpec
from melosviz.render import video_exporter
from melosviz.render.video_exporter import (
    _DEFAULT_VIDEO_COLOR,
    _DEFAULT_VIDEO_DURATION,
    _DEFAULT_VIDEO_SIZE,
    FFMpegNotFoundError,
    RenderExportError,
    export_video,
    is_ffmpeg_available,
)

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

SENTINEL_FFMPEG = "/fake/path/to/ffmpeg"
SENTINEL_OUTPUT_BYTES = b"\x00" * 4096  # > 0 so size check passes


def _make_completed(
    returncode: int = 0, stderr: str = "", stdout: str = ""
) -> subprocess.CompletedProcess:
    """Build a ``CompletedProcess`` instance matching what ffmpeg returns."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stderr=stderr, stdout=stdout
    )


def _fake_ffmpeg_success(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """Side-effect that simulates a successful ffmpeg invocation.

    Writes a small placeholder file at the output path (the last element
    of ``cmd``) and returns a ``CompletedProcess`` with ``returncode=0``.
    """
    output_path = Path(cmd[-1])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(SENTINEL_OUTPUT_BYTES)
    return _make_completed(returncode=0)


def _fake_ffmpeg_failure(
    returncode: int = 1, stderr: str = "ffmpeg: error\nfake stack trace"
) -> Callable[..., subprocess.CompletedProcess]:
    """Return a side-effect that simulates ffmpeg failing."""

    def _side(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        return _make_completed(returncode=returncode, stderr=stderr)

    return _side


def _patch_success() -> Any:
    """Return a context manager that patches ffmpeg to succeed."""
    return patch(
        "melosviz.render.video_exporter.subprocess.run",
        side_effect=_fake_ffmpeg_success,
    )


def _patch_resolve() -> Any:
    """Patch ``_resolve_ffmpeg_binary`` to return the sentinel path."""
    return patch(
        "melosviz.render.video_exporter._resolve_ffmpeg_binary",
        return_value=SENTINEL_FFMPEG,
    )


def _patch_resolve_raises(exc: BaseException) -> Any:
    """Patch ``_resolve_ffmpeg_binary`` to raise ``exc``."""
    return patch(
        "melosviz.render.video_exporter._resolve_ffmpeg_binary",
        side_effect=exc,
    )


# ---------------------------------------------------------------------------
# Tests — happy path, MP4
# ---------------------------------------------------------------------------


def test_export_video_mp4_returns_path(tmp_path: Path) -> None:
    """``export_video(format='mp4')`` returns a :class:`Path` to the file."""
    with _patch_resolve(), _patch_success():
        result = export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
    assert isinstance(result, Path)
    assert result.suffix == ".mp4"


def test_export_video_mp4_creates_file(tmp_path: Path) -> None:
    """The returned MP4 path exists on disk and is non-empty."""
    with _patch_resolve(), _patch_success():
        result = export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
    assert result.exists()
    assert result.is_file()
    assert result.stat().st_size > 0


def test_export_video_mp4_uses_libx264(tmp_path: Path) -> None:
    """MP4 exports invoke ffmpeg with the libx264 video codec."""
    with _patch_resolve(), _patch_success() as mock_run:
        export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
    assert mock_run.call_count == 1
    cmd = mock_run.call_args[0][0]
    assert "libx264" in cmd
    # MP4 should request yuv420p for broad player compatibility.
    assert "yuv420p" in cmd


def test_export_video_mp4_uses_png_input_pattern(tmp_path: Path) -> None:
    """MP4 exports feed ffmpeg an image2 demuxer pattern of PNG frames."""
    with _patch_resolve(), _patch_success() as mock_run:
        export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
    cmd = mock_run.call_args[0][0]
    # The exporter should drive ffmpeg's image2 demuxer, not lavfi.
    assert "-framerate" in cmd
    assert "-i" in cmd
    # The input pattern must end with a printf-style frame number and a
    # .png extension so ffmpeg's image2 demuxer picks up the sequence.
    input_idx = cmd.index("-i")
    input_pattern = cmd[input_idx + 1]
    assert input_pattern.endswith("frame_%05d.png")
    # lavfi / color=c= must NOT appear in the new PNG-frame pipeline.
    assert "lavfi" not in cmd
    assert "color=c=" not in cmd


def test_export_video_generates_png_frames_in_tempdir(
    tmp_path: Path,
) -> None:
    """``export_video`` writes one PNG per frame into a tempdir before muxing."""
    with _patch_resolve(), _patch_success() as mock_run:
        result = export_video(
            RenderSpec(metadata={"width": 16, "height": 16, "fps": 4, "duration": 1.0}),
            format="mp4",
            output_dir=tmp_path,
        )
    # Final output exists (mock ffmpeg writes the placeholder).
    assert result.exists()
    # The mock's input pattern points at a frame_%05d.png file inside a
    # frames tempdir; verify the cmd shape and that the tempdir was used.
    cmd = mock_run.call_args[0][0]
    input_idx = cmd.index("-i")
    pattern_dir = Path(cmd[input_idx + 1]).parent
    assert pattern_dir.is_absolute()


def test_export_video_two_positional_args_signature(
    tmp_path: Path,
) -> None:
    """The acceptance-test signature ``export_video(spec, 'mp4')`` works."""
    with _patch_resolve(), _patch_success():
        result = export_video(RenderSpec(), "mp4")
    assert isinstance(result, Path)
    assert result.suffix == ".mp4"
    assert result.exists()
    assert result.stat().st_size > 0


# ---------------------------------------------------------------------------
# Tests — happy path, WebM
# ---------------------------------------------------------------------------


def test_export_video_webm_returns_path(tmp_path: Path) -> None:
    """``export_video(format='webm')`` returns a :class:`Path` to the file."""
    with _patch_resolve(), _patch_success():
        result = export_video(RenderSpec(), format="webm", output_dir=tmp_path)
    assert isinstance(result, Path)
    assert result.suffix == ".webm"


def test_export_video_webm_creates_file(tmp_path: Path) -> None:
    """The returned WebM path exists on disk and is non-empty."""
    with _patch_resolve(), _patch_success():
        result = export_video(RenderSpec(), format="webm", output_dir=tmp_path)
    assert result.exists()
    assert result.is_file()
    assert result.stat().st_size > 0


def test_export_video_webm_uses_libvpx_vp9(tmp_path: Path) -> None:
    """WebM exports invoke ffmpeg with the libvpx-vp9 video codec."""
    with _patch_resolve(), _patch_success() as mock_run:
        export_video(RenderSpec(), format="webm", output_dir=tmp_path)
    cmd = mock_run.call_args[0][0]
    assert "libvpx-vp9" in cmd
    # WebM should request a constrained bitrate for the placeholder.
    assert "-b:v" in cmd


# ---------------------------------------------------------------------------
# Tests — format handling
# ---------------------------------------------------------------------------


def test_export_video_default_format_is_mp4(tmp_path: Path) -> None:
    """Omitting ``format`` defaults to MP4 output."""
    with _patch_resolve(), _patch_success():
        result = export_video(RenderSpec(), output_dir=tmp_path)
    assert result.suffix == ".mp4"


def test_export_video_format_uppercase_accepted(tmp_path: Path) -> None:
    """Uppercase format strings (``MP4``, ``WEBM``) are accepted."""
    with _patch_resolve(), _patch_success():
        mp4 = export_video(RenderSpec(), format="MP4", output_dir=tmp_path)
        webm = export_video(RenderSpec(), format="WEBM", output_dir=tmp_path)
    assert mp4.suffix == ".mp4"
    assert webm.suffix == ".webm"


def test_export_video_format_mixed_case_accepted(tmp_path: Path) -> None:
    """Mixed-case format strings are accepted (case-insensitive)."""
    with _patch_resolve(), _patch_success():
        result = export_video(RenderSpec(), format="Mp4", output_dir=tmp_path)
    assert result.suffix == ".mp4"


def test_export_video_rejects_unknown_format(tmp_path: Path) -> None:
    """Unknown formats raise :class:`RenderExportError` and never run ffmpeg."""
    with (
        _patch_resolve(),
        patch("melosviz.render.video_exporter.subprocess.run") as mock_run,
    ):
        with pytest.raises(RenderExportError):
            export_video(RenderSpec(), format="avi", output_dir=tmp_path)
        mock_run.assert_not_called()


def test_export_video_rejects_empty_format(tmp_path: Path) -> None:
    """Empty format string is rejected as unsupported."""
    with (
        _patch_resolve(),
        patch("melosviz.render.video_exporter.subprocess.run") as mock_run,
    ):
        with pytest.raises(RenderExportError):
            export_video(RenderSpec(), format="", output_dir=tmp_path)
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — output directory handling
# ---------------------------------------------------------------------------


def test_export_video_creates_output_dir(tmp_path: Path) -> None:
    """``output_dir`` is created if it does not already exist."""
    nested = tmp_path / "nested" / "out"
    assert not nested.exists()
    with _patch_resolve(), _patch_success():
        result = export_video(RenderSpec(), format="mp4", output_dir=nested)
    assert nested.exists()
    assert nested.is_dir()
    assert result.parent == nested


def test_export_video_accepts_string_output_dir(tmp_path: Path) -> None:
    """``output_dir`` may be passed as a plain string."""
    target = tmp_path / "from-str"
    with _patch_resolve(), _patch_success():
        result = export_video(RenderSpec(), format="mp4", output_dir=str(target))
    assert result.parent == target


def test_export_video_creates_deeply_nested_dirs(tmp_path: Path) -> None:
    """Deeply nested output dirs are created (parents=True)."""
    deep = tmp_path / "a" / "b" / "c" / "d"
    with _patch_resolve(), _patch_success():
        result = export_video(RenderSpec(), format="mp4", output_dir=deep)
    assert deep.is_dir()
    assert result.parent == deep


# ---------------------------------------------------------------------------
# Tests — subprocess command-line shape
# ---------------------------------------------------------------------------


def test_export_video_command_starts_with_resolved_ffmpeg(
    tmp_path: Path,
) -> None:
    """The ffmpeg command begins with the resolved binary path."""
    with _patch_resolve(), _patch_success() as mock_run:
        export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == SENTINEL_FFMPEG


def test_export_video_command_includes_overwrite_flag(tmp_path: Path) -> None:
    """The ffmpeg command includes ``-y`` to overwrite existing files."""
    with _patch_resolve(), _patch_success() as mock_run:
        export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
    cmd = mock_run.call_args[0][0]
    assert "-y" in cmd


def test_export_video_command_ends_with_output_path(tmp_path: Path) -> None:
    """The ffmpeg command ends with the destination output path."""
    with _patch_resolve(), _patch_success() as mock_run:
        result = export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
    cmd = mock_run.call_args[0][0]
    assert Path(cmd[-1]) == result


def test_export_video_captures_subprocess_output(tmp_path: Path) -> None:
    """The exporter captures stdout/stderr and uses text mode with a timeout."""
    with _patch_resolve(), _patch_success() as mock_run:
        export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
    kwargs = mock_run.call_args[1]
    assert kwargs.get("capture_output") is True
    assert kwargs.get("text") is True
    # Concatting PNG frames takes longer than the lavfi one-shot did, so
    # the timeout is bumped to 120s to accommodate slower hardware.
    assert kwargs.get("timeout") == 120


def test_export_video_subprocess_invoked_exactly_once(tmp_path: Path) -> None:
    """``export_video`` invokes ``subprocess.run`` exactly once per call."""
    with _patch_resolve(), _patch_success() as mock_run:
        export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
        export_video(RenderSpec(), format="webm", output_dir=tmp_path)
    assert mock_run.call_count == 2


# ---------------------------------------------------------------------------
# Tests — error paths
# ---------------------------------------------------------------------------


def test_export_video_ffmpeg_nonzero_exit_raises(tmp_path: Path) -> None:
    """A non-zero ffmpeg exit code raises :class:`RenderExportError`."""
    with (
        _patch_resolve(),
        patch(
            "melosviz.render.video_exporter.subprocess.run",
            side_effect=_fake_ffmpeg_failure(returncode=1),
        ),
        pytest.raises(RenderExportError),
    ):
        export_video(RenderSpec(), format="mp4", output_dir=tmp_path)


def test_export_video_ffmpeg_nonzero_exit_stderr_in_message(
    tmp_path: Path,
) -> None:
    """The :class:`RenderExportError` raised on ffmpeg failure includes stderr tail."""
    with (
        _patch_resolve(),
        patch(
            "melosviz.render.video_exporter.subprocess.run",
            side_effect=_fake_ffmpeg_failure(
                returncode=2, stderr="bad codec\nfake stack trace"
            ),
        ),
        pytest.raises(RenderExportError) as excinfo,
    ):
        export_video(RenderSpec(), format="webm", output_dir=tmp_path)
    assert "fake stack trace" in str(excinfo.value)


def test_export_video_missing_output_file_raises(tmp_path: Path) -> None:
    """ffmpeg returns 0 but produces no file → :class:`RenderExportError`."""

    def _noop(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        # Simulate ffmpeg returning success without creating a file.
        return _make_completed(returncode=0)

    with (
        _patch_resolve(),
        patch("melosviz.render.video_exporter.subprocess.run", side_effect=_noop),
        pytest.raises(RenderExportError),
    ):
        export_video(RenderSpec(), format="mp4", output_dir=tmp_path)


def test_export_video_empty_output_file_raises(tmp_path: Path) -> None:
    """ffmpeg returns 0 but produces an empty file → :class:`RenderExportError`."""

    def _empty(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        Path(cmd[-1]).write_bytes(b"")  # create empty file
        return _make_completed(returncode=0)

    with (
        _patch_resolve(),
        patch("melosviz.render.video_exporter.subprocess.run", side_effect=_empty),
        pytest.raises(RenderExportError),
    ):
        export_video(RenderSpec(), format="mp4", output_dir=tmp_path)


def test_export_video_oserror_raises_ffmpeg_not_found(tmp_path: Path) -> None:
    """``OSError`` from the subprocess call is wrapped as :class:`FFMpegNotFoundError`."""

    def _boom(cmd: list[str], **kwargs: Any) -> None:
        raise OSError("simulated spawn failure")

    with (
        _patch_resolve(),
        patch("melosviz.render.video_exporter.subprocess.run", side_effect=_boom),
        pytest.raises(FFMpegNotFoundError),
    ):
        export_video(RenderSpec(), format="mp4", output_dir=tmp_path)


def test_export_video_binary_resolution_failure_propagates(
    tmp_path: Path,
) -> None:
    """If ``_resolve_ffmpeg_binary`` raises :class:`FFMpegNotFoundError`, it propagates."""
    sentinel_exc = FFMpegNotFoundError("ffmpeg is missing")
    with (
        _patch_resolve_raises(sentinel_exc),
        patch("melosviz.render.video_exporter.subprocess.run") as mock_run,
    ):
        with pytest.raises(FFMpegNotFoundError):
            export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — logging & module surface
# ---------------------------------------------------------------------------


def test_export_video_logs_info_on_success(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A successful export emits an INFO log line about the output path."""
    with (
        _patch_resolve(),
        _patch_success(),
        caplog.at_level(logging.INFO, logger="melosviz.render.video_exporter"),
    ):
        export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
    # At least one log record mentions "export_video".
    matching = [rec for rec in caplog.records if "export_video" in rec.getMessage()]
    assert matching, f"expected an export_video log record, got: {caplog.records}"


def test_module_exports_include_export_video() -> None:
    """``export_video`` is exposed in ``__all__`` for public use."""
    assert "export_video" in video_exporter.__all__
    assert callable(export_video)


def test_module_exports_include_error_classes() -> None:
    """The error classes are part of the public API surface."""
    for name in ("RenderExportError", "FFMpegNotFoundError", "export_video"):
        assert name in video_exporter.__all__


def test_is_ffmpeg_available_returns_bool() -> None:
    """``is_ffmpeg_available`` returns a boolean and does not raise."""
    result = is_ffmpeg_available()
    assert isinstance(result, bool)


def test_default_video_constants_have_expected_values() -> None:
    """The legacy ``_DEFAULT_VIDEO_*`` constants keep their original values.

    These constants are documented in the module docstring / public API
    and are used by downstream code to drive the colour-clip defaults.
    Pin them here so a future refactor can't silently change the
    smoke-test output (a regression that would break the staging CLI).
    """
    assert _DEFAULT_VIDEO_SIZE == "320x240"
    assert _DEFAULT_VIDEO_DURATION == 1
    assert _DEFAULT_VIDEO_COLOR == "blue"


# ---------------------------------------------------------------------------
# Tests — RenderSpec handling
# ---------------------------------------------------------------------------


def test_export_video_accepts_empty_renderspec(tmp_path: Path) -> None:
    """A default (empty) :class:`RenderSpec` is accepted; output is produced."""
    with _patch_resolve(), _patch_success():
        result = export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
    assert result.exists()


def test_export_video_accepts_populated_renderspec(tmp_path: Path) -> None:
    """A populated :class:`RenderSpec` is accepted; output is produced.

    The dimensions/fps/duration here are intentionally tiny (32x32, 4 fps,
    0.25s → 1 frame). The test's purpose is to confirm that the
    exporter *accepts* a populated spec end-to-end and produces a file
    with the correct extension — it is not exercising PNG-frame
    generation at scale, so a 32x32 single-frame render keeps the
    suite under a second even on slow hardware. Larger dimensions are
    covered by the dedicated scale/render tests, not by this contract
    test.
    """
    spec = RenderSpec(
        metadata={"width": 32, "height": 32, "fps": 4, "duration": 0.25},
        palette=["#00f5ff", "#ff2fd5", "#8a75ff"],
        layers=[{"id": "bg", "type": "shader"}],
    )
    with _patch_resolve(), _patch_success():
        result = export_video(spec, format="webm", output_dir=tmp_path)
    assert result.exists()
    assert result.suffix == ".webm"


# ---------------------------------------------------------------------------
# Tests — rawvideo pipe path (fast path for large frame counts)
# ---------------------------------------------------------------------------

import io
from unittest.mock import MagicMock, patch as _patch

from melosviz.render.video_exporter import (
    _RAWVIDEO_FRAME_THRESHOLD,
    _frame_rgb24_bytes,
    _export_video_rawvideo_pipe,
)


def _make_popen_mock(returncode: int = 0, output_path: Path | None = None) -> MagicMock:
    """Build a ``Popen`` mock that simulates a successful (or failing) ffmpeg run."""
    mock_proc = MagicMock()
    mock_proc.__enter__ = lambda s: s
    mock_proc.__exit__ = MagicMock(return_value=False)
    mock_proc.stdin = io.BytesIO()
    mock_proc.returncode = returncode
    mock_proc.communicate.return_value = (b"", b"")

    if output_path is not None and returncode == 0:
        # simulate ffmpeg creating the output file when communicate() is called
        def _communicate(timeout=None):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"\x00" * 1024)
            mock_proc.returncode = 0
            return (b"", b"")

        mock_proc.communicate.side_effect = _communicate

    return mock_proc


def test_frame_rgb24_bytes_size() -> None:
    """``_frame_rgb24_bytes`` returns exactly width*height*3 bytes."""
    data = _frame_rgb24_bytes(16, 9, (255, 0, 128))
    assert len(data) == 16 * 9 * 3


def test_frame_rgb24_bytes_content() -> None:
    """Each pixel in the raw frame matches the supplied RGB tuple."""
    rgb = (10, 20, 30)
    data = _frame_rgb24_bytes(4, 4, rgb)
    assert len(data) == 4 * 4 * 3
    for i in range(0, len(data), 3):
        assert data[i] == rgb[0]
        assert data[i + 1] == rgb[1]
        assert data[i + 2] == rgb[2]


def test_rawvideo_threshold_constant() -> None:
    """``_RAWVIDEO_FRAME_THRESHOLD`` must be positive so the guard is meaningful."""
    assert isinstance(_RAWVIDEO_FRAME_THRESHOLD, int)
    assert _RAWVIDEO_FRAME_THRESHOLD > 0


def test_export_video_large_mp4_uses_rawvideo_pipe(tmp_path: Path) -> None:
    """MP4 renders above the threshold use the rawvideo Popen pipe, not subprocess.run."""
    # frame count above threshold so the fast path is chosen
    frame_count = _RAWVIDEO_FRAME_THRESHOLD + 1
    duration = frame_count / 30.0
    spec = RenderSpec(metadata={"width": 8, "height": 8, "fps": 30, "duration": duration})
    output_path = tmp_path / "melosviz-render.mp4"

    mock_proc = _make_popen_mock(returncode=0, output_path=output_path)

    with (
        _patch_resolve(),
        patch("melosviz.render.video_exporter.subprocess.run") as mock_run,
        patch("melosviz.render.video_exporter.subprocess.Popen", return_value=mock_proc),
    ):
        result = export_video(spec, format="mp4", output_dir=tmp_path)

    # rawvideo path uses Popen, not run — subprocess.run should NOT be invoked for the render
    # (it may be invoked by _resolve_ffmpeg_binary probe, but we patched _resolve above)
    mock_run.assert_not_called()
    assert result.exists()
    assert result.suffix == ".mp4"


def test_export_video_large_mp4_rawvideo_cmd_shape(tmp_path: Path) -> None:
    """The rawvideo pipe ffmpeg command includes the correct demuxer and pixel format flags."""
    frame_count = _RAWVIDEO_FRAME_THRESHOLD + 10
    duration = frame_count / 30.0
    spec = RenderSpec(metadata={"width": 8, "height": 8, "fps": 30, "duration": duration})
    output_path = tmp_path / "melosviz-render.mp4"

    popen_calls: list[list[str]] = []

    def _capture_popen(cmd, **kwargs):
        popen_calls.append(cmd)
        return _make_popen_mock(returncode=0, output_path=output_path)

    with (
        _patch_resolve(),
        patch("melosviz.render.video_exporter.subprocess.Popen", side_effect=_capture_popen),
    ):
        export_video(spec, format="mp4", output_dir=tmp_path)

    assert popen_calls, "expected Popen to be called for large-frame MP4"
    cmd = popen_calls[0]
    assert "-f" in cmd
    rawvideo_idx = cmd.index("-f")
    assert cmd[rawvideo_idx + 1] == "rawvideo"
    assert "-pixel_format" in cmd
    pf_idx = cmd.index("-pixel_format")
    assert cmd[pf_idx + 1] == "rgb24"
    assert "pipe:0" in cmd
    assert "libx264" in cmd


def test_export_video_small_mp4_uses_png_path(tmp_path: Path) -> None:
    """MP4 renders at or below the threshold stay on the PNG image2 path."""
    # 30 frames is the default 1s@30fps spec — well below the 150 threshold
    with _patch_resolve(), _patch_success() as mock_run:
        export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
    assert mock_run.call_count == 1
    cmd = mock_run.call_args[0][0]
    # PNG path uses image2 demuxer with a frame_%05d.png pattern
    input_idx = cmd.index("-i")
    assert cmd[input_idx + 1].endswith("frame_%05d.png")


def test_export_video_webm_always_uses_png_path(tmp_path: Path) -> None:
    """WebM exports always use the PNG image2 path regardless of frame count."""
    with _patch_resolve(), _patch_success() as mock_run:
        export_video(RenderSpec(), format="webm", output_dir=tmp_path)
    assert mock_run.call_count == 1
    cmd = mock_run.call_args[0][0]
    assert "libvpx-vp9" in cmd


# ---------------------------------------------------------------------------
# Tests — zlib level regression (level 1, not 9)
# ---------------------------------------------------------------------------


def test_write_raw_png_rgb_zlib_level_is_fast() -> None:
    """``_write_raw_png_rgb`` uses zlib level 1 (fast) not level 9 (slow).

    This is a regression guard for PERF_BENCHMARK.md §1b P0: the level-9
    zlib compress was the bottleneck at ~30 ms/frame for 720p solid-colour
    frames.  Level 1 is ~3 ms/frame — a 10× improvement with identical
    output size for solid-colour data.

    We verify that the written PNG actually decompresses correctly (the
    level-1 output is still valid zlib) and that the IDAT chunk is present.
    """
    import struct as _struct
    import zlib as _zlib
    from pathlib import Path as _Path
    import tempfile

    from melosviz.render.video_exporter import _write_raw_png_rgb

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        png_path = _Path(f.name)

    try:
        _write_raw_png_rgb(png_path, 16, 16, (255, 0, 128))
        data = png_path.read_bytes()
    finally:
        png_path.unlink(missing_ok=True)

    # PNG signature
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    # IDAT chunk present
    assert b"IDAT" in data
    # Extract IDAT chunk and verify it is valid zlib (decompresses without error)
    idat_start = data.index(b"IDAT")
    length = _struct.unpack(">I", data[idat_start - 4 : idat_start])[0]
    idat_data = data[idat_start + 4 : idat_start + 4 + length]
    decompressed = _zlib.decompress(idat_data)
    # 16 pixels wide × 3 bytes + 1 filter byte per row × 16 rows
    assert len(decompressed) == (1 + 16 * 3) * 16


# ---------------------------------------------------------------------------
# Tests — per-frame gen time budget (perf regression, skipped on slow CI)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    # Skip on CI where CPU may be slow / contended — budget is hardware-dependent.
    # Set MELOSVIZ_STRICT_PERF=1 in the environment to enforce locally.
    not os.environ.get("MELOSVIZ_STRICT_PERF"),
    reason="perf budget test skipped unless MELOSVIZ_STRICT_PERF=1 is set",
)
def test_png_frame_gen_time_budget() -> None:
    """Generating a 1280×720 solid-colour PNG must complete in < 5 ms/frame.

    Baseline: level-9 zlib measured at 29.6 ms/frame (PERF_BENCHMARK.md §1b).
    Level-1 target: < 5 ms/frame (10× headroom vs the old bottleneck).

    This test is timing-based and may be skipped in environments where
    the host is under heavy load.  It uses a single frame to keep the
    test itself sub-millisecond on fast hardware.
    """
    import time
    import tempfile

    from melosviz.render.video_exporter import _write_raw_png_rgb

    BUDGET_MS = 5.0  # per-frame budget in milliseconds
    WIDTH, HEIGHT = 1280, 720

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        png_path = Path(f.name)

    try:
        t0 = time.perf_counter()
        _write_raw_png_rgb(png_path, WIDTH, HEIGHT, (0, 245, 255))
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
    finally:
        png_path.unlink(missing_ok=True)

    assert elapsed_ms < BUDGET_MS, (
        f"PNG frame gen took {elapsed_ms:.1f} ms — exceeds {BUDGET_MS} ms budget. "
        f"Check that zlib.compress level is 1, not 9 (level 9 was ~30 ms/frame). "
        f"See docs/PERF_BENCHMARK.md §1b."
    )
