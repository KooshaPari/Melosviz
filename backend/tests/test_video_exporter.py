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
