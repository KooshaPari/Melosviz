"""Adapter validation tests for the ComfyUI integration layer (G6 ecosystem).

These tests verify the adapter's public interface contract and offline
fallback behaviour WITHOUT requiring a real ComfyUI server.  All external
calls (HTTP, ffmpeg probe) are mocked or guarded by skipif markers.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from melosviz.render.comfyui_adapter import (
    ComfyUIAdapter,
    ComfyUIError,
    ComfyUIUnavailableError,
    _generate_placeholder_clip,
    _hex_to_rgb,
    _http_download,
    _scene_duration,
    _submit_workflow,
    render_image,
    render_video,
)

HAS_FFMPEG = shutil.which("ffmpeg") is not None
HAS_FFPROBE = shutil.which("ffprobe") is not None

needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not on $PATH")
needs_ffprobe = pytest.mark.skipif(not HAS_FFPROBE, reason="ffprobe not on $PATH")


# ---------------------------------------------------------------------------
# Helpers to create mock responses compatible with shutil.copyfileobj
# ---------------------------------------------------------------------------


def _make_read_mock(content: bytes):
    """Return a ``read`` method that yields *content* once, then b''.

    ``shutil.copyfileobj`` calls ``read(16384)`` in a loop; a mock that
    always returns the full payload causes an infinite loop.
    """
    calls = [content, b""]

    def _read(n=-1):
        return calls.pop(0) if calls else b""

    return _read


def _make_http_response(content: bytes):
    """Build a mock response usable as a context manager with shutil."""
    resp = MagicMock()
    resp.read = _make_read_mock(content)
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# a. Adapter has required methods / interface contract
# ---------------------------------------------------------------------------


class TestAdapterHasRequiredMethods:
    """The ComfyUI adapter must expose the conductor-facing interface."""

    def test_comfyui_adapter_has_render(self):
        adapter = ComfyUIAdapter("comfyui_image")
        assert callable(getattr(adapter, "render", None))

    def test_module_has_submit_workflow(self):
        assert callable(_submit_workflow)

    def test_module_has_generate_placeholder_clip(self):
        assert callable(_generate_placeholder_clip)

    def test_module_has_is_comfyui_available(self):
        from melosviz.render.comfyui_adapter import is_comfyui_available

        assert callable(is_comfyui_available)

    def test_module_has_render_image_and_render_video(self):
        assert callable(render_image)
        assert callable(render_video)

    def test_adapter_rejects_unknown_scene_type(self):
        with pytest.raises(ValueError, match="unsupported scene_type"):
            ComfyUIAdapter("nonexistent_scene_type")

    def test_adapter_accepts_all_known_scene_types(self):
        from melosviz.render.comfyui_adapter import SCENE_TYPES

        for st in SCENE_TYPES:
            adapter = ComfyUIAdapter(st)
            assert adapter.scene_type == st


# ---------------------------------------------------------------------------
# b. Offline mode produces clip.mp4
# ---------------------------------------------------------------------------


@needs_ffmpeg
class TestOfflineModeProducesClip:
    """When ComfyUI is offline the adapter writes a placeholder MP4."""

    @patch("melosviz.render.comfyui_adapter.is_comfyui_available", return_value=False)
    def test_offline_mode_produces_clip(self, _mock_avail, tmp_path):
        """Offline render writes scene_000/clip.mp4 and it is a valid MP4."""
        adapter = ComfyUIAdapter("comfyui_image")
        scene = {"prompt": "a neon cityscape", "seed": 42}
        spec = {"scenes": [scene]}

        with patch.dict(os.environ, {"MELOSVIZ_COMFYUI_OFFLINE": "1"}):
            results = adapter.render(spec, output_path=tmp_path)

        # With FFmpeg available, results should contain the clip path
        clips = [p for p in results if p.name == "clip.mp4"]
        assert clips, f"Expected clip.mp4 in results, got: {results}"
        clip = clips[0]
        assert clip.exists(), f"clip.mp4 does not exist at {clip}"
        assert clip.stat().st_size > 0, "clip.mp4 is empty"

        # Validate MP4 ftyp box (first 4 bytes after 'ftyp' marker)
        with open(clip, "rb") as fh:
            header = fh.read(32)
        # ftyp box: bytes 4-7 should be 'ftyp'
        assert header[4:8] == b"ftyp", f"Expected 'ftyp' box in MP4 header, got {header[4:8]!r}"


# ---------------------------------------------------------------------------
# c. Offline mode produces workflow.json
# ---------------------------------------------------------------------------


@needs_ffmpeg
class TestOfflineModeProducesWorkflowJson:
    """Offline render must emit workflow.json alongside clip.mp4."""

    @patch("melosviz.render.comfyui_adapter.is_comfyui_available", return_value=False)
    def test_offline_mode_produces_workflow_json(self, _mock_avail, tmp_path):
        adapter = ComfyUIAdapter("comfyui_image")
        scene = {"prompt": "cyberpunk alley", "seed": 7}
        spec = {"scenes": [scene]}

        with patch.dict(os.environ, {"MELOSVIZ_COMFYUI_OFFLINE": "1"}):
            adapter.render(spec, output_path=tmp_path)

        wf_path = tmp_path / "scene_000" / "workflow.json"
        assert wf_path.exists(), f"workflow.json not found at {wf_path}"

        wf = json.loads(wf_path.read_text(encoding="utf-8"))
        assert isinstance(wf, dict), "workflow.json root must be a dict"
        # A valid ComfyUI workflow has string keys mapping to node dicts
        # with at least "class_type" and "inputs".
        for node_id, node in wf.items():
            assert "class_type" in node, f"Node {node_id} missing class_type"
            assert "inputs" in node, f"Node {node_id} missing inputs"

    @patch("melosviz.render.comfyui_adapter.is_comfyui_available", return_value=False)
    def test_offline_mode_writes_job_spec_manifest(self, _mock_avail, tmp_path):
        """A job_spec.json manifest is written alongside scene outputs."""
        adapter = ComfyUIAdapter("comfyui_image")
        scene = {"prompt": "golden hour", "seed": 99}
        spec = {"scenes": [scene]}

        with patch.dict(os.environ, {"MELOSVIZ_COMFYUI_OFFLINE": "1"}):
            adapter.render(spec, output_path=tmp_path)

        manifest = tmp_path / "job_spec.json"
        assert manifest.exists(), "job_spec.json manifest not found"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data["mode"] == "offline-job-spec"
        assert len(data["scenes"]) == 1
        assert data["scenes"][0]["prompt"] == "golden hour"


# ---------------------------------------------------------------------------
# d. submit_workflow returns a job ID
# ---------------------------------------------------------------------------


class TestSubmitWorkflowReturnsJobId:
    """_submit_workflow must POST to /prompt and return the prompt_id."""

    def test_submit_workflow_returns_string_job_id(self):
        fake_response = json.dumps({"prompt_id": "abc-123-def"}).encode()
        mock_resp = _make_http_response(fake_response)

        with patch(
            "melosviz.render.comfyui_adapter.urllib.request.urlopen", return_value=mock_resp
        ) as mock_urlopen:
            result = _submit_workflow(
                {"3": {"class_type": "KSampler", "inputs": {}}},
                base_url="http://fake:8188",
                client_id="test-client",
            )

        assert isinstance(result, str)
        assert result == "abc-123-def"
        # Verify the POST was made with the workflow body
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert req.full_url == "http://fake:8188/prompt"
        assert req.method == "POST"

    def test_submit_workflow_raises_on_no_prompt_id(self):
        fake_response = json.dumps({"error": "queue full"}).encode()
        mock_resp = _make_http_response(fake_response)

        with (
            patch("melosviz.render.comfyui_adapter.urllib.request.urlopen", return_value=mock_resp),
            pytest.raises(ComfyUIError, match="no prompt_id"),
        ):
            _submit_workflow({}, base_url="http://fake:8188", client_id="test")


# ---------------------------------------------------------------------------
# e. Poll status handles retryable errors
# ---------------------------------------------------------------------------


class TestPollStatusHandlesRetryableErrors:
    """_await_workflow propagates network errors as ComfyUIUnavailableError."""

    def test_poll_propagates_connection_error(self):
        """A URLError during poll should become ComfyUIUnavailableError."""
        from melosviz.render.comfyui_adapter import _await_workflow

        with (
            patch(
                "melosviz.render.comfyui_adapter.urllib.request.urlopen",
                side_effect=urllib.error.URLError("Connection refused"),
            ),
            pytest.raises(ComfyUIUnavailableError, match="history poll failed"),
        ):
            _await_workflow(
                "prompt-xyz",
                base_url="http://fake:8188",
                timeout_s=2,
                poll_s=0.1,
            )

    def test_poll_propagates_timeout_error(self):
        from melosviz.render.comfyui_adapter import _await_workflow

        with (
            patch(
                "melosviz.render.comfyui_adapter.urllib.request.urlopen",
                side_effect=TimeoutError("timed out"),
            ),
            pytest.raises(ComfyUIUnavailableError, match="history poll failed"),
        ):
            _await_workflow(
                "prompt-xyz",
                base_url="http://fake:8188",
                timeout_s=2,
                poll_s=0.1,
            )

    def test_poll_times_out_when_workflow_never_completes(self):
        """If the workflow never completes, _await_workflow raises ComfyUIError."""
        from melosviz.render.comfyui_adapter import _await_workflow

        # Return empty history (prompt_id not found) every time
        empty_resp = json.dumps({}).encode()

        def _poll_side_effect(*args, **kwargs):
            return _make_http_response(empty_resp)

        with (
            patch(
                "melosviz.render.comfyui_adapter.urllib.request.urlopen",
                side_effect=_poll_side_effect,
            ),
            pytest.raises(ComfyUIError, match="did not finish"),
        ):
            _await_workflow(
                "prompt-xyz",
                base_url="http://fake:8188",
                timeout_s=2,
                poll_s=0.1,
            )


# ---------------------------------------------------------------------------
# f. Download output writes file
# ---------------------------------------------------------------------------


class TestDownloadOutputWritesFile:
    """_http_download must write the response bytes to the destination."""

    def test_download_writes_bytes(self, tmp_path):
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # Fake image bytes
        mock_resp = _make_http_response(content)

        dest = tmp_path / "output_image.png"
        with patch(
            "melosviz.render.comfyui_adapter.urllib.request.urlopen", return_value=mock_resp
        ):
            result = _http_download("http://fake/view?filename=x", dest)

        assert result == dest
        assert dest.exists()
        assert dest.read_bytes() == content

    def test_collect_outputs_downloads_all_items(self, tmp_path):
        """_collect_outputs iterates the history entry and downloads files."""
        from melosviz.render.comfyui_adapter import _collect_outputs

        history_entry = {
            "outputs": {
                "1": {
                    "images": [
                        {"filename": "render_001.png", "subfolder": ""},
                        {"filename": "render_002.png", "subfolder": ""},
                    ]
                }
            }
        }
        fake_bytes = b"\x89PNG" + b"\xff" * 50

        def _fake_open(*args, **kwargs):
            return _make_http_response(fake_bytes)

        with patch(
            "melosviz.render.comfyui_adapter.urllib.request.urlopen", side_effect=_fake_open
        ):
            files = _collect_outputs(
                history_entry, base_url="http://fake:8188", output_dir=tmp_path
            )

        assert len(files) == 2
        for f in files:
            assert f.exists()
            assert f.read_bytes() == fake_bytes

    def test_collect_outputs_raises_when_no_outputs(self):
        """An empty outputs section should raise ComfyUIError."""
        from melosviz.render.comfyui_adapter import _collect_outputs

        history_entry = {"outputs": {}}
        with pytest.raises(ComfyUIError, match="no images/videos"):
            _collect_outputs(history_entry, base_url="http://fake", output_dir=Path("/tmp"))


# ---------------------------------------------------------------------------
# g. Placeholder clip valid duration (ffprobe)
# ---------------------------------------------------------------------------


@needs_ffmpeg
@needs_ffprobe
class TestPlaceholderClipValidDuration:
    """Generated placeholder MP4s must have a reasonable duration."""

    def _probe_duration(self, clip_path: Path) -> float:
        """Use ffprobe to get the duration of a video file."""
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(clip_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return float(result.stdout.strip())

    def test_placeholder_clip_duration_in_range(self, tmp_path):
        scene = {"prompt": "test scene", "duration_s": 2.0}
        clip = tmp_path / "test_clip.mp4"

        _generate_placeholder_clip(scene, clip, width=640, height=360, fps=24)

        duration = self._probe_duration(clip)
        # Allow tolerance for ffmpeg encoding overhead
        assert 0.5 <= duration <= 30.0, (
            f"Placeholder clip duration {duration:.2f}s outside [0.5, 30.0]"
        )

    def test_placeholder_clip_short_duration(self, tmp_path):
        scene = {"prompt": "short", "duration_s": 0.5}
        clip = tmp_path / "short.mp4"

        _generate_placeholder_clip(scene, clip, width=320, height=180, fps=15)

        duration = self._probe_duration(clip)
        assert 0.3 <= duration <= 5.0, f"Short clip duration {duration:.2f}s unexpected"


# ---------------------------------------------------------------------------
# h. Placeholder clip valid codec (ffprobe)
# ---------------------------------------------------------------------------


@needs_ffmpeg
@needs_ffprobe
class TestPlaceholderClipValidCodec:
    """Placeholder MP4s must use H.264 codec."""

    def _probe_codec(self, clip_path: Path) -> str:
        """Use ffprobe to get the video codec name."""
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "stream=codec_name",
                "-select_streams",
                "v:0",
                "-of",
                "csv=p=0",
                str(clip_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()

    def test_placeholder_clip_uses_h264(self, tmp_path):
        scene = {"prompt": "codec test", "duration_s": 1.0}
        clip = tmp_path / "codec_test.mp4"

        _generate_placeholder_clip(scene, clip, width=640, height=360, fps=24)

        codec = self._probe_codec(clip)
        assert codec == "h264", f"Expected h264 codec, got {codec!r}"

    def test_placeholder_clip_pixel_format(self, tmp_path):
        """Verify yuv420p pixel format for maximum compatibility."""
        scene = {"prompt": "pix fmt", "duration_s": 1.0}
        clip = tmp_path / "pixfmt_test.mp4"

        _generate_placeholder_clip(scene, clip, width=640, height=360, fps=24)

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "stream=pix_fmt",
                "-select_streams",
                "v:0",
                "-of",
                "csv=p=0",
                str(clip),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        pix_fmt = result.stdout.strip()
        assert pix_fmt == "yuv420p", f"Expected yuv420p, got {pix_fmt!r}"


# ---------------------------------------------------------------------------
# Helper function tests (hex_to_rgb, scene_duration)
# ---------------------------------------------------------------------------


class TestHelpers:
    """Unit tests for pure helper functions."""

    def test_hex_to_rgb_6digit(self):
        assert _hex_to_rgb("#ff2fd5") == (255, 47, 213)

    def test_hex_to_rgb_3digit(self):
        assert _hex_to_rgb("#f0a") == (255, 0, 170)

    def test_hex_to_rgb_no_hash(self):
        assert _hex_to_rgb("00f5ff") == (0, 245, 255)

    def test_hex_to_rgb_invalid_falls_back_to_grey(self):
        assert _hex_to_rgb("not-a-color") == (128, 128, 128)

    def test_hex_to_rgb_empty_falls_back_to_grey(self):
        assert _hex_to_rgb("") == (128, 128, 128)

    def test_scene_duration_from_duration_s(self):
        assert _scene_duration({"duration_s": 3.5}) == 3.5

    def test_scene_duration_from_start_end(self):
        assert _scene_duration({"start": 10.0, "end": 15.0}) == 5.0

    def test_scene_duration_fallback(self):
        assert _scene_duration({}) == 1.0  # default

    def test_scene_duration_invalid_value(self):
        assert _scene_duration({"duration_s": "not_a_number"}) == 1.0

    def test_scene_duration_minimum(self):
        """Duration should be at least 0.1s."""
        assert _scene_duration({"duration_s": 0.01}) == 0.1
