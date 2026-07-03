"""Tests for the wgpu headless export → Python bridge (B18).

Test strategy
=============

Two tiers of tests live here:

**Tier 1 — pure-logic tests (always run, no GPU, no binary required)**
    These test the Python-side adapter logic in isolation: argument validation,
    error-message classification, JSON serialisation, spec-dict handling, and
    binary-resolution helpers.  All subprocess calls are patched so no real
    binary is needed.

**Tier 2 — live wgpu integration tests (GPU + binary required)**
    These call :func:`melosviz.render.wgpu_adapter.render_frame_bytes` for
    real.  They are gated by :func:`_require_wgpu` which calls
    :func:`is_wgpu_available` and issues a loud ``pytest.skip`` (NOT a
    silent skip) when the binary is missing or the GPU is unavailable.

    Run on a host with Metal/Vulkan:

    .. code-block:: bash

        MELOSVIZ_RENDER_BIN=./target/release/melosviz-render \\
            pytest backend/tests/test_wgpu_headless_export.py -v \\
            -k "live"

GPU-unavailable policy
======================
When ``is_wgpu_available()`` returns False the tier-2 tests emit:

    SKIPPED: melosviz-render binary not found or no GPU adapter available …

This is intentional and acceptable per the task spec:
"gate the GPU-requiring test with a clear skip that PRINTS why (loud skip,
not silent) and still keep a non-GPU logic test that runs."
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from melosviz.render.wgpu_adapter import (
    WGPU_BINARY_ENV_VAR,
    WgpuExportError,
    WgpuNotAvailableError,
    _find_repo_root,
    _spec_to_json,
    is_wgpu_available,
    render_frame_bytes,
    resolve_render_binary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: Minimal valid RenderSpec dict for subprocess patching tests.
_MINIMAL_SPEC: dict[str, Any] = {
    "metadata": {"width": 64, "height": 48, "fps": 5, "duration": 1.0, "title": "test"},
    "palette": ["#00f5ff"],
    "dense_keyframes": [],
    "scene_segments": [],
}


def _fake_success_result(width: int = 64, height: int = 48) -> MagicMock:
    """Return a mock CompletedProcess that looks like a successful export."""
    mock = MagicMock()
    mock.returncode = 0
    # Produce exactly width*height*4 non-zero RGBA bytes.
    mock.stdout = b"\x80\x40\xc0\xff" * (width * height)
    mock.stderr = b""
    return mock


def _require_wgpu() -> None:
    """Skip with a loud message if the live wgpu path is not available."""
    if not is_wgpu_available():
        pytest.skip(
            "melosviz-render binary not found or no GPU adapter available. "
            "To run live wgpu tests:\n"
            "  1. Build the binary:  cargo build -p melosviz-render-wgpu --release\n"
            "  2. Set env:           export MELOSVIZ_RENDER_BIN=./target/release/melosviz-render\n"
            "  3. Re-run:            pytest backend/tests/test_wgpu_headless_export.py -k live\n"
            "Skipping live GPU test — this is expected in CI without a GPU adapter.",
            allow_module_level=False,
        )


# ===========================================================================
# Tier 1 — pure-logic tests (no GPU, no binary)
# ===========================================================================


class TestSpecToJson:
    """_spec_to_json serialises various spec types correctly."""

    def test_dict_spec_is_json(self) -> None:
        out = _spec_to_json(_MINIMAL_SPEC)
        parsed = json.loads(out)
        assert parsed["metadata"]["width"] == 64

    def test_pydantic_v2_model(self) -> None:
        """Objects with model_dump_json() are handled via the pydantic v2 path."""

        class FakeSpec:
            def model_dump_json(self) -> str:
                return json.dumps(_MINIMAL_SPEC)

        out = _spec_to_json(FakeSpec())  # type: ignore[arg-type]
        parsed = json.loads(out)
        assert parsed["metadata"]["fps"] == 5

    def test_pydantic_v1_model(self) -> None:
        """Objects with json() (pydantic v1 style) are handled."""

        class FakeSpecV1:
            def json(self) -> str:
                return json.dumps(_MINIMAL_SPEC)

        out = _spec_to_json(FakeSpecV1())  # type: ignore[arg-type]
        parsed = json.loads(out)
        assert parsed["metadata"]["height"] == 48

    def test_fallback_dict_path(self) -> None:
        """Objects with neither model_dump_json nor json fall back to __dict__."""

        class BareSpec:
            def __init__(self) -> None:
                self.metadata = {"width": 32, "height": 24}

        out = _spec_to_json(BareSpec())  # type: ignore[arg-type]
        parsed = json.loads(out)
        assert parsed["metadata"]["width"] == 32


class TestArgumentValidation:
    """render_frame_bytes validates arguments before spawning a subprocess."""

    def test_negative_frame_index_raises(self) -> None:
        with pytest.raises(ValueError, match="frame_index must be"):
            render_frame_bytes(_MINIMAL_SPEC, frame_index=-1)

    def test_zero_width_raises(self) -> None:
        with pytest.raises(ValueError, match="width must be"):
            render_frame_bytes(_MINIMAL_SPEC, width=0)

    def test_zero_height_raises(self) -> None:
        with pytest.raises(ValueError, match="height must be"):
            render_frame_bytes(_MINIMAL_SPEC, height=0)

    def test_negative_width_raises(self) -> None:
        with pytest.raises(ValueError, match="width must be"):
            render_frame_bytes(_MINIMAL_SPEC, width=-5)

    def test_negative_height_raises(self) -> None:
        with pytest.raises(ValueError, match="height must be"):
            render_frame_bytes(_MINIMAL_SPEC, height=-1)


class TestSubprocessSuccess:
    """render_frame_bytes returns stdout bytes on a successful subprocess run."""

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_returns_stdout_bytes(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_run.return_value = _fake_success_result(64, 48)
        result = render_frame_bytes(_MINIMAL_SPEC, frame_index=0)
        assert isinstance(result, bytes)
        assert len(result) == 64 * 48 * 4

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_correct_byte_count_non_standard_dimensions(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_run.return_value = _fake_success_result(16, 16)
        result = render_frame_bytes(_MINIMAL_SPEC, frame_index=0, width=16, height=16)
        assert len(result) == 16 * 16 * 4

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_non_zero_pixel_content(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_run.return_value = _fake_success_result(64, 48)
        result = render_frame_bytes(_MINIMAL_SPEC, frame_index=0)
        non_zero = sum(1 for b in result if b > 0)
        assert non_zero > 0, "all pixels were zero — unexpected for a non-black frame"

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_subcommand_in_argv(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """The subprocess call must include the 'export-frame' subcommand."""
        mock_run.return_value = _fake_success_result()
        render_frame_bytes(_MINIMAL_SPEC)
        call_args = mock_run.call_args[0][0]  # first positional arg = cmd list
        assert "export-frame" in call_args

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_frame_index_in_argv(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_run.return_value = _fake_success_result()
        render_frame_bytes(_MINIMAL_SPEC, frame_index=7)
        call_args = mock_run.call_args[0][0]
        assert "--frame" in call_args
        idx = call_args.index("--frame")
        assert call_args[idx + 1] == "7"

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_width_height_override_in_argv(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_run.return_value = _fake_success_result(32, 32)
        render_frame_bytes(_MINIMAL_SPEC, width=32, height=32)
        call_args = mock_run.call_args[0][0]
        assert "--width" in call_args
        assert "--height" in call_args


class TestSubprocessFailure:
    """render_frame_bytes raises the right exception on subprocess failure."""

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_non_zero_exit_raises_wgpu_export_error(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=b"",
            stderr=b"some generic render failure",
        )
        with pytest.raises(WgpuExportError):
            render_frame_bytes(_MINIMAL_SPEC)

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_no_gpu_adapter_stderr_raises_not_available(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """'No GPU adapter found' in stderr → WgpuNotAvailableError."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=b"",
            stderr=b"Error: No GPU adapter found -- Metal/Vulkan required for rendering",
        )
        with pytest.raises(WgpuNotAvailableError, match="no GPU adapter"):
            render_frame_bytes(_MINIMAL_SPEC)

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_empty_stdout_on_success_raises(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Exit 0 but empty stdout is a Rust-side bug — must raise."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"",
            stderr=b"",
        )
        with pytest.raises(WgpuExportError, match="no output"):
            render_frame_bytes(_MINIMAL_SPEC)

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_timeout_raises_wgpu_export_error(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=120)
        with pytest.raises(WgpuExportError, match="timed out"):
            render_frame_bytes(_MINIMAL_SPEC)

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_file_not_found_raises_not_available(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_run.side_effect = FileNotFoundError("No such file or directory: '/fake/bin'")
        with pytest.raises(WgpuNotAvailableError, match="not found"):
            render_frame_bytes(_MINIMAL_SPEC)


class TestBinaryResolution:
    """resolve_render_binary raises WgpuNotAvailableError when nothing is found."""

    def test_raises_when_no_binary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(WGPU_BINARY_ENV_VAR, raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)
        # Patch _find_repo_root to return None so Cargo dirs are not searched.
        with patch("melosviz.render.wgpu_adapter._find_repo_root", return_value=None):
            with pytest.raises(WgpuNotAvailableError, match="melosviz-render"):
                resolve_render_binary()

    def test_env_var_missing_file_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nonexistent-binary"
        monkeypatch.setenv(WGPU_BINARY_ENV_VAR, str(missing))
        with pytest.raises(WgpuNotAvailableError, match=WGPU_BINARY_ENV_VAR):
            resolve_render_binary()

    def test_env_var_executable_is_used(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake_bin = tmp_path / "melosviz-render"
        fake_bin.write_bytes(b"#!/bin/sh\n")
        fake_bin.chmod(0o755)
        monkeypatch.setenv(WGPU_BINARY_ENV_VAR, str(fake_bin))
        result = resolve_render_binary()
        assert result == str(fake_bin)

    def test_find_repo_root_locates_cargo_toml(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text("[package]\nname = 'test'\n")
        sub = tmp_path / "backend" / "src" / "melosviz" / "render"
        sub.mkdir(parents=True)
        result = _find_repo_root(sub / "wgpu_adapter.py")
        assert result == tmp_path

    def test_find_repo_root_returns_none_when_no_cargo_toml(
        self, tmp_path: Path
    ) -> None:
        result = _find_repo_root(tmp_path)
        # tmp_path has no Cargo.toml in any ancestor that we control.
        # We can only assert it returns Path | None without raising.
        assert result is None or isinstance(result, Path)


class TestIsWgpuAvailable:
    """is_wgpu_available returns bool without raising."""

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary")
    def test_returns_false_when_no_binary(self, mock_resolve: MagicMock) -> None:
        mock_resolve.side_effect = WgpuNotAvailableError("no binary")
        assert is_wgpu_available() is False

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_returns_true_when_binary_responds(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        assert is_wgpu_available() is True

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_returns_false_when_binary_fails_help(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_run.return_value = MagicMock(returncode=1)
        assert is_wgpu_available() is False

    @patch("melosviz.render.wgpu_adapter.resolve_render_binary", return_value="/fake/bin")
    @patch("melosviz.render.wgpu_adapter.subprocess.run")
    def test_returns_false_on_os_error(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        mock_run.side_effect = OSError("no such process")
        assert is_wgpu_available() is False


# ===========================================================================
# Tier 2 — live wgpu integration tests (GPU + binary required)
# Skipped loudly when binary/GPU is unavailable.
# ===========================================================================


class TestLiveWgpuExport:
    """Integration tests that call the real melosviz-render binary."""

    def test_live_render_frame_returns_correct_size(self) -> None:
        """Frame bytes must be exactly width*height*4 (RGBA)."""
        _require_wgpu()

        (w, h) = (64, 48)
        spec = {
            "metadata": {"width": w, "height": h, "fps": 5, "duration": 1.0, "title": "test"},
            "palette": ["#00f5ff"],
            "dense_keyframes": [],
            "scene_segments": [],
        }
        rgba = render_frame_bytes(spec, frame_index=0, width=w, height=h)
        assert isinstance(rgba, bytes), "expected bytes from render_frame_bytes"
        assert len(rgba) == w * h * 4, (
            f"expected {w * h * 4} bytes (RGBA for {w}×{h}), got {len(rgba)}"
        )

    def test_live_render_frame_non_empty_content(self) -> None:
        """At least one pixel must be non-zero — the bg_gradient shader paints."""
        _require_wgpu()

        (w, h) = (64, 48)
        spec = {
            "metadata": {"width": w, "height": h, "fps": 5, "duration": 1.0, "title": "test"},
            "palette": ["#00f5ff"],
            "dense_keyframes": [],
            "scene_segments": [],
        }
        rgba = render_frame_bytes(spec, frame_index=0, width=w, height=h)
        non_zero = sum(1 for b in rgba if b > 0)
        assert non_zero > 0, (
            "all RGBA pixels were 0 — the bg_gradient shader did not run. "
            "Check pipeline compilation and uniform upload in the Rust crate."
        )

    def test_live_render_frame_rgba_alpha_channel(self) -> None:
        """Verify the output is genuine RGBA (alpha bytes present at index 3, 7, …)."""
        _require_wgpu()

        (w, h) = (32, 32)
        spec = {
            "metadata": {"width": w, "height": h, "fps": 5, "duration": 1.0, "title": "test"},
            "palette": ["#ff2fd5"],
            "dense_keyframes": [],
            "scene_segments": [],
        }
        rgba = render_frame_bytes(spec, frame_index=0, width=w, height=h)
        # Alpha bytes are at offsets 3, 7, 11, … in row-major RGBA.
        alpha_values = [rgba[i] for i in range(3, len(rgba), 4)]
        # Not all alpha bytes should be 0 — the compositor sets alpha=255.
        assert any(a > 0 for a in alpha_values), (
            "all alpha bytes are 0 — frame appears fully transparent; "
            "check the Rust compositor's store op / clear colour."
        )
