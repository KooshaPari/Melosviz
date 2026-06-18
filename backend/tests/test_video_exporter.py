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
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

import pytest

from melosviz.analysis.models import RenderSpec
from melosviz.render import video_exporter
from melosviz.render.video_exporter import (
    FFMpegNotFoundError,
    RenderExportError,
    _DEFAULT_VIDEO_COLOR,
    _DEFAULT_VIDEO_DURATION,
    _DEFAULT_VIDEO_SIZE,
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


def _fake_ffmpeg_success(
    cmd: list[str], **kwargs: Any
) -> subprocess.CompletedProcess:
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
            RenderSpec(
                metadata={"width": 16, "height": 16, "fps": 4, "duration": 1.0}
            ),
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
    with _patch_resolve(), patch(
        "melosviz.render.video_exporter.subprocess.run"
    ) as mock_run:
        with pytest.raises(RenderExportError):
            export_video(RenderSpec(), format="avi", output_dir=tmp_path)
        mock_run.assert_not_called()


def test_export_video_rejects_empty_format(tmp_path: Path) -> None:
    """Empty format string is rejected as unsupported."""
    with _patch_resolve(), patch(
        "melosviz.render.video_exporter.subprocess.run"
    ) as mock_run:
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
        result = export_video(
            RenderSpec(), format="mp4", output_dir=str(target)
        )
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
        result = export_video(
            RenderSpec(), format="mp4", output_dir=tmp_path
        )
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
    with _patch_resolve(), patch(
        "melosviz.render.video_exporter.subprocess.run",
        side_effect=_fake_ffmpeg_failure(returncode=1),
    ):
        with pytest.raises(RenderExportError):
            export_video(RenderSpec(), format="mp4", output_dir=tmp_path)


def test_export_video_ffmpeg_nonzero_exit_stderr_in_message(
    tmp_path: Path,
) -> None:
    """The :class:`RenderExportError` raised on ffmpeg failure includes stderr tail."""
    with _patch_resolve(), patch(
        "melosviz.render.video_exporter.subprocess.run",
        side_effect=_fake_ffmpeg_failure(
            returncode=2, stderr="bad codec\nfake stack trace"
        ),
    ):
        with pytest.raises(RenderExportError) as excinfo:
            export_video(RenderSpec(), format="webm", output_dir=tmp_path)
    assert "fake stack trace" in str(excinfo.value)


def test_export_video_missing_output_file_raises(tmp_path: Path) -> None:
    """ffmpeg returns 0 but produces no file → :class:`RenderExportError`."""
    def _noop(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        # Simulate ffmpeg returning success without creating a file.
        return _make_completed(returncode=0)

    with _patch_resolve(), patch(
        "melosviz.render.video_exporter.subprocess.run", side_effect=_noop
    ):
        with pytest.raises(RenderExportError):
            export_video(RenderSpec(), format="mp4", output_dir=tmp_path)


def test_export_video_empty_output_file_raises(tmp_path: Path) -> None:
    """ffmpeg returns 0 but produces an empty file → :class:`RenderExportError`."""
    def _empty(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        Path(cmd[-1]).write_bytes(b"")  # create empty file
        return _make_completed(returncode=0)

    with _patch_resolve(), patch(
        "melosviz.render.video_exporter.subprocess.run", side_effect=_empty
    ):
        with pytest.raises(RenderExportError):
            export_video(RenderSpec(), format="mp4", output_dir=tmp_path)


def test_export_video_oserror_raises_ffmpeg_not_found(tmp_path: Path) -> None:
    """``OSError`` from the subprocess call is wrapped as :class:`FFMpegNotFoundError`."""

    def _boom(cmd: list[str], **kwargs: Any) -> None:
        raise OSError("simulated spawn failure")

    with _patch_resolve(), patch(
        "melosviz.render.video_exporter.subprocess.run", side_effect=_boom
    ):
        with pytest.raises(FFMpegNotFoundError):
            export_video(RenderSpec(), format="mp4", output_dir=tmp_path)


def test_export_video_binary_resolution_failure_propagates(
    tmp_path: Path,
) -> None:
    """If ``_resolve_ffmpeg_binary`` raises :class:`FFMpegNotFoundError`, it propagates."""
    sentinel_exc = FFMpegNotFoundError("ffmpeg is missing")
    with _patch_resolve_raises(sentinel_exc), patch(
        "melosviz.render.video_exporter.subprocess.run"
    ) as mock_run:
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
    with _patch_resolve(), _patch_success(), caplog.at_level(
        logging.INFO, logger="melosviz.render.video_exporter"
    ):
        export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
    # At least one log record mentions "export_video".
    matching = [
        rec for rec in caplog.records if "export_video" in rec.getMessage()
    ]
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


# ---------------------------------------------------------------------------
# Tests — RenderSpec handling
# ---------------------------------------------------------------------------


def test_export_video_accepts_empty_renderspec(tmp_path: Path) -> None:
    """A default (empty) :class:`RenderSpec` is accepted; output is produced."""
    with _patch_resolve(), _patch_success():
        result = export_video(RenderSpec(), format="mp4", output_dir=tmp_path)
    assert result.exists()


def test_export_video_accepts_populated_renderspec(tmp_path: Path) -> None:
    """A populated :class:`RenderSpec` is accepted; output is produced."""
    spec = RenderSpec(
        metadata={"width": 1920, "height": 1080, "fps": 30, "duration": 30.0},
        palette=["#00f5ff", "#ff2fd5", "#8a75ff"],
        layers=[{"id": "bg", "type": "shader"}],
    )
    with _patch_resolve(), _patch_success():
        result = export_video(spec, format="webm", output_dir=tmp_path)
    assert result.exists()
    assert result.suffix == ".webm"


# ---------------------------------------------------------------------------
# Tests — cv2 / numpy frame rendering helpers
# ---------------------------------------------------------------------------


def test_hex_to_bgr_parses_six_digit() -> None:
    """``_hex_to_bgr`` parses 6-digit hex correctly."""
    from melosviz.render.video_exporter import _hex_to_bgr
    assert _hex_to_bgr("#FF0000") == (0, 0, 255)
    assert _hex_to_bgr("#00FF00") == (0, 255, 0)
    assert _hex_to_bgr("#0000FF") == (255, 0, 0)


def test_hex_to_bgr_parses_three_digit() -> None:
    """``_hex_to_bgr`` expands 3-digit shorthand."""
    from melosviz.render.video_exporter import _hex_to_bgr
    assert _hex_to_bgr("#F00") == (0, 0, 255)
    assert _hex_to_bgr("#0F0") == (0, 255, 0)


def test_hex_to_bgr_returns_white_for_invalid() -> None:
    """``_hex_to_bgr`` falls back to white for garbage input."""
    from melosviz.render.video_exporter import _hex_to_bgr
    assert _hex_to_bgr("not-a-color") == (255, 255, 255)
    assert _hex_to_bgr("#GGGGGG") == (255, 255, 255)


def test_mix_color_halfway() -> None:
    """``_mix_color`` returns the midpoint at ratio 0.5."""
    from melosviz.render.video_exporter import _mix_color
    # Python uses banker's rounding (round half to even), so 127.5 rounds to 128.
    assert _mix_color((0, 0, 0), (255, 255, 255), 0.5) == (128, 128, 128)


def test_mix_color_clamped() -> None:
    """``_mix_color`` clamps ratio to [0, 1]."""
    from melosviz.render.video_exporter import _mix_color
    assert _mix_color((0, 0, 0), (255, 255, 255), -1.0) == (0, 0, 0)
    assert _mix_color((0, 0, 0), (255, 255, 255), 2.0) == (255, 255, 255)


def test_frame_keyframe_at_time_empty() -> None:
    """``_frame_keyframe_at_time`` returns defaults when keyframes is empty."""
    from melosviz.render.video_exporter import _frame_keyframe_at_time
    result = _frame_keyframe_at_time([], 1.0, 30)
    assert result["energy"] == 0.5
    assert result["hue"] == 190.0


def test_frame_keyframe_at_time_lookup() -> None:
    """``_frame_keyframe_at_time`` returns the closest frame."""
    from melosviz.render.video_exporter import _frame_keyframe_at_time
    kfs = [
        {"time": 0.0, "energy": 0.1},
        {"time": 1.0, "energy": 0.9},
    ]
    result = _frame_keyframe_at_time(kfs, 1.0, 30)
    assert result["energy"] == 0.9


def test_shot_at_time_empty() -> None:
    """``_shot_at_time`` returns None for empty shots."""
    from melosviz.render.video_exporter import _shot_at_time
    assert _shot_at_time([], 1.0) is None


def test_shot_at_time_dict_hit() -> None:
    """``_shot_at_time`` finds a dict shot by time range."""
    from melosviz.render.video_exporter import _shot_at_time
    shots = [
        {"start_time": 0.0, "end_time": 2.0, "section": "intro"},
        {"start_time": 2.0, "end_time": 4.0, "section": "verse"},
    ]
    result = _shot_at_time(shots, 1.0)
    assert result is not None
    assert result["section"] == "intro"


def test_shot_transition_empty() -> None:
    """``_shot_transition`` returns default for no shot."""
    from melosviz.render.video_exporter import _shot_transition
    assert _shot_transition(None, 1.0) == ("match_cut", 0.0)


def test_shot_transition_dict() -> None:
    """``_shot_transition`` extracts transition from dict shot."""
    from melosviz.render.video_exporter import _shot_transition
    shot = {
        "start_time": 0.0,
        "end_time": 2.0,
        "cut_style": "fade",
        "transition_in": {"type": "fade", "intensity": 0.7},
    }
    kind, intensity = _shot_transition(shot, 0.1)
    assert kind == "fade"
    assert intensity == 0.7


def test_shot_transition_late_phase() -> None:
    """Late progress uses transition_out."""
    from melosviz.render.video_exporter import _shot_transition
    shot = {
        "start_time": 0.0,
        "end_time": 2.0,
        "cut_style": "match_cut",
        "transition_in": {"type": "hard_cut", "intensity": 0.5},
        "transition_out": {"type": "fade", "intensity": 0.8},
    }
    kind, intensity = _shot_transition(shot, 1.9)
    assert kind == "fade"
    assert intensity == 0.8


def test_write_raw_png_rgb(tmp_path: Path) -> None:
    """``_write_raw_png_rgb`` writes a valid PNG file."""
    from melosviz.render.video_exporter import _write_raw_png_rgb
    path = tmp_path / "solid.png"
    _write_raw_png_rgb(path, 4, 4, (255, 0, 0))
    assert path.exists()
    assert path.stat().st_size > 0


def test_write_raw_png_rgb_invalid_dimensions() -> None:
    """``_write_raw_png_rgb`` raises ValueError for invalid dimensions."""
    from melosviz.render.video_exporter import _write_raw_png_rgb
    with pytest.raises(ValueError):
        _write_raw_png_rgb(Path("/dev/null"), 0, 4, (255, 0, 0))


def test_pillow_available_returns_bool() -> None:
    """``_pillow_available`` returns a boolean."""
    from melosviz.render.video_exporter import _pillow_available
    assert isinstance(_pillow_available(), bool)


def test_save_solid_png(tmp_path: Path) -> None:
    """``_save_solid_png`` writes a valid PNG file."""
    from melosviz.render.video_exporter import _save_solid_png
    path = tmp_path / "solid.png"
    _save_solid_png(path, 4, 4, (255, 0, 0))
    assert path.exists()
    assert path.stat().st_size > 0


def test_generate_png_frames(tmp_path: Path) -> None:
    """``_generate_png_frames`` creates the expected number of frame files."""
    from melosviz.render.video_exporter import _generate_png_frames
    paths = _generate_png_frames(tmp_path, 3, 8, 8, ["#FF0000", "#00FF00"])
    assert len(paths) == 3
    for path in paths:
        assert path.exists()
    assert paths[0].name == "frame_00001.png"
    assert paths[2].name == "frame_00003.png"


def test_coerce_metadata_dict() -> None:
    """``_coerce_metadata`` extracts metadata from a dict."""
    from melosviz.render.video_exporter import _coerce_metadata
    assert _coerce_metadata({"metadata": {"fps": 60}}) == {"fps": 60}


def test_coerce_metadata_none() -> None:
    """``_coerce_metadata`` returns empty dict for None."""
    from melosviz.render.video_exporter import _coerce_metadata
    assert _coerce_metadata(None) == {}


def test_coerce_metadata_render_spec() -> None:
    """``_coerce_metadata`` extracts metadata from a RenderSpec."""
    from melosviz.render.video_exporter import _coerce_metadata
    spec = RenderSpec(metadata={"fps": 60})
    assert _coerce_metadata(spec) == {"fps": 60}


def test_extract_palette_dict() -> None:
    """``_extract_palette`` extracts palette from a dict."""
    from melosviz.render.video_exporter import _extract_palette
    assert _extract_palette({"palette": ["#FF0000", "#00FF00"]}) == ["#FF0000", "#00FF00"]


def test_extract_palette_none() -> None:
    """``_extract_palette`` returns defaults for None."""
    from melosviz.render.video_exporter import _extract_palette
    result = _extract_palette(None)
    assert len(result) == 3
    assert result[0] == "#00f5ff"


def test_extract_palette_render_spec() -> None:
    """``_extract_palette`` extracts palette from a RenderSpec."""
    from melosviz.render.video_exporter import _extract_palette
    spec = RenderSpec(palette=["#FFFFFF"])
    assert _extract_palette(spec) == ["#FFFFFF"]


def test_render_frame_small() -> None:
    """``_render_frame`` produces a valid OpenCV frame for tiny inputs."""
    import numpy as np
    from melosviz.render.video_exporter import _render_frame
    frame = _render_frame(
        width=64,
        height=64,
        time_sec=0.5,
        duration_sec=2.0,
        keyframe={"energy": 0.5, "intensity": 0.6, "hue": 180.0, "bpm_sync": 0.5, "color_shift": "#00f5ff"},
        shot={
            "start_time": 0.0,
            "end_time": 2.0,
            "section": "intro",
            "shot_type": "establishing",
            "motif": "wide",
            "cut_style": "match_cut",
            "camera": {"zoom": 1.0, "pan_x": 0.0, "pan_y": 0.0, "rotation": 0.0},
            "movement": {"speed": 0.5, "type": "push_in", "pattern": 0.0, "beat_lock": 0.5},
            "beat_anchor": 0.5,
        },
        palette=["#00f5ff", "#ff2fd5", "#8a75ff"],
    )
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (64, 64, 3)
    assert frame.dtype == np.uint8


def test_draw_text_box() -> None:
    """``_draw_text_box`` renders text without crashing."""
    import numpy as np
    from melosviz.render.video_exporter import _draw_text_box
    frame = np.zeros((200, 400, 3), dtype=np.uint8)
    _draw_text_box(frame, ["Hello", "World"], (10, 10), (0, 255, 0))
    assert frame.shape == (200, 400, 3)


def test_render_frame_with_shot_spec() -> None:
    """``_render_frame`` works with ShotSpec objects (not just dicts)."""
    import numpy as np
    from melosviz.render.video_exporter import _render_frame
    from melosviz.analysis.models import ShotSpec, CameraState
    shot = ShotSpec(
        id="s1",
        section="intro",
        start_time=0.0,
        end_time=2.0,
        shot_type="establishing",
        motif="wide",
        beat_anchor=0.5,
        energy_profile=[0.5, 0.5, 0.5],
        movement={"speed": 0.5, "type": "push_in", "pattern": 0.0, "beat_lock": 0.5},
        cut_style="match_cut",
        camera=CameraState(zoom=1.0, pan_x=0.0, pan_y=0.0, rotation=0.0),
        transition_in={"type": "cold_open", "duration": 0.35, "intensity": 1.0},
        transition_out={"type": "fade", "duration": 0.28, "intensity": 0.5},
        overlay=[],
        palette_shift="",
    )
    frame = _render_frame(
        width=64,
        height=64,
        time_sec=0.5,
        duration_sec=2.0,
        keyframe={"energy": 0.5, "intensity": 0.6, "hue": 180.0, "bpm_sync": 0.5, "color_shift": "#00f5ff"},
        shot=shot,
        palette=["#00f5ff", "#ff2fd5", "#8a75ff"],
    )
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (64, 64, 3)


def test_clamp_helper() -> None:
    """``_clamp`` bounds a value to [min, max]."""
    from melosviz.render.video_exporter import _clamp
    assert _clamp(5.0, 0.0, 10.0) == 5.0
    assert _clamp(-1.0, 0.0, 10.0) == 0.0
    assert _clamp(15.0, 0.0, 10.0) == 10.0
