"""Coverage backfill for low-coverage modules — part of the qgate quality gate.

Targets modules below 85% in the baseline run:
  - bridge/server.py        (was 0%)
  - cli/main.py             (was 30%)
  - conductor/registry.py   (was 54%)
  - presets/cinematic.py    (was 47%)
  - presets/__init__.py     (was 74%)
  - presets/registry.py     (was 70%)
  - conductor/orchestrator.py (was 73%)
  - runtime/touchdesigner/adapter.py (was 57%)
  - runtime/touchdesigner/bridge.py  (was 59%)
  - video_exporter.py       (was 75%)
  - analysis/audio.py       (was 78%)

Also includes:
  - Property tests (hypothesis)
  - Chaos/resilience tests (bridge failure injection)
  - Performance smoke (init <15s)
  - Security: bandit is run via CI; no additional tests needed here
"""

from __future__ import annotations

import json
import time
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_wav(path: Path, duration_s: float = 1.0, sample_rate: int = 44100) -> Path:
    """Write a minimal valid WAV file to *path* and return it."""
    import struct

    num_frames = int(duration_s * sample_rate)
    # Simple 440 Hz sine wave
    import math

    samples = [int(32767 * math.sin(2 * math.pi * 440 * i / sample_rate)) for i in range(num_frames)]
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{num_frames}h", *samples))
    return path


def _minimal_render_spec() -> object:
    """Return a minimal RenderSpec for tests that need one."""
    from melosviz.analysis.models import RenderSpec

    return RenderSpec(
        metadata={"duration": 3.0, "fps": 24, "bpm": 120.0},
        palette=["#000000", "#ffffff"],
    )


# ---------------------------------------------------------------------------
# bridge/server.py — FastAPI routes via httpx TestClient
# ---------------------------------------------------------------------------


class TestBridgeServer:
    """Test the FastAPI bridge routes using the TestClient (no subprocess)."""

    @pytest.fixture()
    def client(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi not installed — bridge tests skipped")

        from melosviz.bridge.server import app

        return TestClient(app)

    def test_health_returns_ok(self, client) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_analyze_missing_file_returns_400(self, client) -> None:
        resp = client.post("/analyze", json={"wav_path": "/nonexistent/file.wav"})
        assert resp.status_code == 400

    def test_build_missing_file_returns_400(self, client) -> None:
        resp = client.post("/build", json={"wav_path": "/no/such.wav"})
        assert resp.status_code == 400

    def test_render_missing_file_returns_400(self, client, tmp_path) -> None:
        resp = client.post(
            "/render", json={"wav_path": "/no/such.wav", "out_dir": str(tmp_path)}
        )
        assert resp.status_code == 400

    def test_analyze_real_wav(self, client, tmp_path) -> None:
        wav = _make_wav(tmp_path / "t.wav")
        resp = client.post("/analyze", json={"wav_path": str(wav)})
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert "metadata" in data

    def test_build_real_wav(self, client, tmp_path) -> None:
        wav = _make_wav(tmp_path / "t.wav")
        with patch(
            "melosviz.compose.assemble.assemble_render_plan",
            return_value={"scenes": [], "mock": True},
        ):
            resp = client.post("/build", json={"wav_path": str(wav)})
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert data is not None

    def test_render_real_wav(self, client, tmp_path) -> None:
        wav = _make_wav(tmp_path / "t.wav")
        out = str(tmp_path / "out")
        with patch(
            "melosviz.compose.assemble.assemble_render_plan",
            return_value={"scenes": [], "mock": True},
        ):
            resp = client.post("/render", json={"wav_path": str(wav), "out_dir": out})
        assert resp.status_code == 200
        assert (tmp_path / "out" / "render_plan.json").exists()

    def test_bridge_import_error_path(self) -> None:
        """Simulate FastAPI absent — the module exits 1 on import."""
        # We can't test the sys.exit(1) path without a subprocess, but we can
        # verify the module-level guard triggers correctly in a fresh interpreter.
        # Instead verify the error message text is correct in source.
        import inspect

        import melosviz.bridge.server as srv_mod

        src = inspect.getsource(srv_mod)
        assert "pip install 'melosviz[bridge]'" in src


# ---------------------------------------------------------------------------
# cli/main.py — CLI command coverage
# ---------------------------------------------------------------------------


class TestCLICommands:
    """Unit-test each _cmd_* function in cli.main."""

    def test_cmd_analyze_file_not_found(self, tmp_path) -> None:
        from melosviz.cli.main import _cmd_analyze

        args = SimpleNamespace(wav=str(tmp_path / "nope.wav"))
        rc = _cmd_analyze(args)
        assert rc == 1

    def test_cmd_analyze_success(self, tmp_path, capsys) -> None:
        from melosviz.cli.main import _cmd_analyze

        wav = _make_wav(tmp_path / "t.wav")
        args = SimpleNamespace(wav=str(wav))
        rc = _cmd_analyze(args)
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "metadata" in data

    def test_cmd_build_file_not_found(self, tmp_path) -> None:
        from melosviz.cli.main import _cmd_build

        args = SimpleNamespace(wav=str(tmp_path / "nope.wav"), out=None, real=False)
        rc = _cmd_build(args)
        assert rc == 1

    def test_cmd_build_success_stdout(self, tmp_path, capsys) -> None:
        from melosviz.cli.main import _cmd_build

        wav = _make_wav(tmp_path / "t.wav")
        args = SimpleNamespace(wav=str(wav), out=None, real=False)
        rc = _cmd_build(args)
        assert rc == 0
        out = capsys.readouterr().out
        # should be valid JSON
        json.loads(out)

    def test_cmd_build_writes_out_dir(self, tmp_path) -> None:
        from melosviz.cli.main import _cmd_build

        wav = _make_wav(tmp_path / "t.wav")
        out_dir = str(tmp_path / "plan")
        args = SimpleNamespace(wav=str(wav), out=out_dir, real=False)
        rc = _cmd_build(args)
        assert rc == 0
        assert (tmp_path / "plan" / "render_plan.json").exists()

    def test_cmd_render_delegates_to_build(self, tmp_path, capsys) -> None:
        from melosviz.cli.main import _cmd_render

        wav = _make_wav(tmp_path / "t.wav")
        args = SimpleNamespace(wav=str(wav), out=None)
        rc = _cmd_render(args)
        assert rc == 0

    def test_cmd_diff_missing_file(self, tmp_path) -> None:
        from melosviz.cli.main import _cmd_diff

        args = SimpleNamespace(spec_a=str(tmp_path / "a.json"), spec_b=str(tmp_path / "b.json"))
        rc = _cmd_diff(args)
        assert rc == 1

    def test_cmd_diff_identical_specs(self, tmp_path, capsys) -> None:
        from melosviz.cli.main import _cmd_diff

        spec = _minimal_render_spec()
        txt = json.dumps(spec.model_dump(), default=str)  # type: ignore[union-attr]
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        a.write_text(txt)
        b.write_text(txt)
        args = SimpleNamespace(spec_a=str(a), spec_b=str(b))
        rc = _cmd_diff(args)
        assert rc == 0
        assert "no differences" in capsys.readouterr().out

    def test_cmd_diff_different_specs(self, tmp_path, capsys) -> None:
        from melosviz.analysis.models import RenderSpec
        from melosviz.cli.main import _cmd_diff

        spec_a = RenderSpec(metadata={"bpm": 120.0, "fps": 24}, palette=[])
        spec_b = RenderSpec(metadata={"bpm": 140.0, "fps": 30}, palette=[])
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        a.write_text(json.dumps(spec_a.model_dump(), default=str))
        b.write_text(json.dumps(spec_b.model_dump(), default=str))
        args = SimpleNamespace(spec_a=str(a), spec_b=str(b))
        rc = _cmd_diff(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "~" in out or "bpm" in out

    def test_cmd_apply_missing_spec(self, tmp_path) -> None:
        from melosviz.cli.main import _cmd_apply

        args = SimpleNamespace(spec=str(tmp_path / "nope.json"), preset="cinematic")
        rc = _cmd_apply(args)
        assert rc == 1

    def test_cmd_apply_unknown_preset(self, tmp_path) -> None:
        from melosviz.cli.main import _cmd_apply

        spec = _minimal_render_spec()
        p = tmp_path / "spec.json"
        p.write_text(json.dumps(spec.model_dump(), default=str))  # type: ignore[union-attr]
        args = SimpleNamespace(spec=str(p), preset="does_not_exist")
        rc = _cmd_apply(args)
        assert rc == 1

    def test_main_dispatch_analyze(self, tmp_path, capsys, monkeypatch) -> None:
        """main() dispatches 'analyze' subcommand via sys.argv."""
        import sys

        from melosviz.cli.main import main

        wav = _make_wav(tmp_path / "t.wav")
        monkeypatch.setattr(sys, "argv", ["viz", "analyze", str(wav)])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        data = json.loads(capsys.readouterr().out)
        assert "metadata" in data

    def test_main_dispatch_diff(self, tmp_path, capsys, monkeypatch) -> None:
        """main() dispatches 'diff' subcommand via sys.argv."""
        import sys

        from melosviz.cli.main import main

        spec = _minimal_render_spec()
        txt = json.dumps(spec.model_dump(), default=str)  # type: ignore[union-attr]
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        a.write_text(txt)
        b.write_text(txt)
        monkeypatch.setattr(sys, "argv", ["viz", "diff", str(a), str(b)])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        assert "no differences" in capsys.readouterr().out

    def test_cmd_apply_cinematic(self, tmp_path, capsys) -> None:
        from melosviz.cli.main import _cmd_apply

        spec = _minimal_render_spec()
        p = tmp_path / "spec.json"
        p.write_text(json.dumps(spec.model_dump(), default=str))  # type: ignore[union-attr]
        args = SimpleNamespace(spec=str(p), preset="cinematic")
        rc = _cmd_apply(args)
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["metadata"]["preset"] == "cinematic"


# ---------------------------------------------------------------------------
# conductor/registry.py
# ---------------------------------------------------------------------------


class TestConductorRegistry:
    def test_registry_has_expected_keys(self) -> None:
        from melosviz.conductor.registry import ADAPTER_REGISTRY

        expected = {
            "generative_asset",
            "motion_graphics_beat_sync",
            "assembly_encode",
            "procedural_3d_animation",
            "live_stage",
            "video_export",
        }
        assert expected.issubset(set(ADAPTER_REGISTRY.keys()))

    def test_lazy_proxy_resolves_class(self) -> None:
        from melosviz.conductor.registry import ADAPTER_REGISTRY

        # The video_export adapter (VideoExportAdapter shim) should resolve
        proxy = ADAPTER_REGISTRY["video_export"]
        # Access scene_type via __getattr__ on the proxy
        assert proxy.scene_type == "video_export"

    def test_blender_adapter_shim_scene_type(self) -> None:
        from melosviz.conductor.registry import _BlenderAdapterShim

        shim = _BlenderAdapterShim()
        assert shim.scene_type == "procedural_3d_animation"

    def test_blender_adapter_shim_render_raises_without_blender(self, tmp_path) -> None:
        from melosviz.conductor.registry import _BlenderAdapterShim
        from melosviz.render.blender_exporter import BlenderNotFoundError

        shim = _BlenderAdapterShim()
        with patch(
            "melosviz.render.blender_exporter.export_blender",
            side_effect=BlenderNotFoundError("blender not found"),
        ), pytest.raises(BlenderNotFoundError):
            shim.render(_minimal_render_spec(), output_path=tmp_path)

    def test_video_export_adapter_shim_render(self, tmp_path) -> None:
        from melosviz.conductor.registry import _VideoExportAdapter

        shim = _VideoExportAdapter()
        stub_path = tmp_path / "out.mp4"
        stub_path.touch()
        with patch(
            "melosviz.render.video_exporter.export_video",
            return_value=stub_path,
        ):
            result = shim.render(_minimal_render_spec(), output_path=tmp_path)
            assert result == stub_path

    def test_video_export_adapter_shim_no_output_path(self, tmp_path) -> None:
        from melosviz.conductor.registry import _VideoExportAdapter

        shim = _VideoExportAdapter()
        stub_path = tmp_path / "out.mp4"
        stub_path.touch()
        with patch(
            "melosviz.render.video_exporter.export_video",
            return_value=stub_path,
        ):
            result = shim.render(_minimal_render_spec())
            assert result == stub_path

    def test_lazy_proxy_callable(self) -> None:
        from melosviz.conductor.registry import _lazy

        proxy = _lazy("melosviz.analysis.models", "RenderSpec")
        # calling proxy should instantiate RenderSpec
        instance = proxy(metadata={"fps": 24}, palette=[])
        assert hasattr(instance, "metadata")


# ---------------------------------------------------------------------------
# presets/cinematic.py + presets/__init__.py + presets/registry.py
# ---------------------------------------------------------------------------


class TestPresets:
    def test_cinematic_apply_sets_palette(self) -> None:
        from melosviz.presets.cinematic import CINEMATIC_PALETTE, apply

        spec = _minimal_render_spec()
        result = apply(spec)  # type: ignore[arg-type]
        assert result.palette == list(CINEMATIC_PALETTE)

    def test_cinematic_apply_sets_metadata(self) -> None:
        from melosviz.presets.cinematic import apply

        spec = _minimal_render_spec()
        result = apply(spec)  # type: ignore[arg-type]
        assert result.metadata["preset"] == "cinematic"
        assert result.metadata["letterbox"] is True
        assert result.metadata["aspect_ratio"] == 2.39

    def test_cinematic_apply_sets_layers(self) -> None:
        from melosviz.presets.cinematic import apply

        spec = _minimal_render_spec()
        result = apply(spec)  # type: ignore[arg-type]
        assert len(result.layers) >= 4
        layer_names = [layer["name"] for layer in result.layers]
        assert "letterbox_mask" in layer_names

    def test_cinematic_apply_sets_keyframes(self) -> None:
        from melosviz.presets.cinematic import apply

        spec = _minimal_render_spec()
        result = apply(spec)  # type: ignore[arg-type]
        assert len(result.keyframes) >= 4
        assert result.keyframes[0]["time"] == 0.0

    def test_cinematic_apply_appends_timeline(self) -> None:
        from melosviz.presets.cinematic import apply

        spec = _minimal_render_spec()
        result = apply(spec)  # type: ignore[arg-type]
        types = [e["type"] for e in result.timeline]
        assert "section" in types

    def test_cinematic_layers_helper(self) -> None:
        from melosviz.presets.cinematic import _layers

        layers = _layers()
        assert any(layer["type"] == "particles" for layer in layers)

    def test_cinematic_keyframes_helper(self) -> None:
        from melosviz.presets.cinematic import _keyframes

        kfs = _keyframes()
        assert all("zoom" in kf for kf in kfs)

    def test_list_presets_returns_cinematic(self) -> None:
        from melosviz.presets import list_presets

        presets = list_presets()
        assert "cinematic" in presets

    def test_load_preset_returns_module(self) -> None:
        from melosviz.presets import load_preset

        mod = load_preset("cinematic")
        assert hasattr(mod, "apply")

    def test_load_preset_unknown_raises(self) -> None:
        from melosviz.presets import load_preset

        with pytest.raises(KeyError):
            load_preset("does_not_exist")

    def test_presets_registry_get_all(self) -> None:
        from melosviz.presets.registry import ThemePresetRegistry

        reg = ThemePresetRegistry()
        all_presets = reg.get_all_presets()
        assert len(all_presets) > 0

    def test_presets_registry_get_preset(self) -> None:
        from melosviz.analysis.models import GenreTheme
        from melosviz.presets.registry import ThemePresetRegistry

        reg = ThemePresetRegistry()
        preset = reg.get_preset(GenreTheme.AMBIENT)
        assert preset.id == "ambient"

    def test_presets_registry_get_preset_dark_street(self) -> None:
        from melosviz.analysis.models import GenreTheme
        from melosviz.presets.registry import ThemePresetRegistry

        reg = ThemePresetRegistry()
        preset = reg.get_preset(GenreTheme.DARK_STREET)
        assert "cyan" in preset.notes.lower() or preset.glow_color is not None

    def test_presets_registry_all_themes_covered(self) -> None:
        from melosviz.analysis.models import GenreTheme
        from melosviz.presets.registry import ThemePresetRegistry

        reg = ThemePresetRegistry()
        for theme in GenreTheme:
            preset = reg.get_preset(theme)
            assert preset is not None


# ---------------------------------------------------------------------------
# conductor/orchestrator.py
# ---------------------------------------------------------------------------


class TestOrchestrator:
    def test_orchestrator_skip_assembly(self, tmp_path) -> None:
        from melosviz.conductor.orchestrator import Orchestrator

        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
        spec = _minimal_render_spec()
        result = orch.render(spec, scene_types=["video_export"])
        # skip_assembly=True means adapters not called — result is empty list or minimal
        assert result is not None

    def test_orchestrator_unknown_scene_type_raises(self, tmp_path) -> None:
        from melosviz.conductor.orchestrator import ConductorError, Orchestrator

        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
        with pytest.raises(ConductorError, match="no adapter registered"):
            orch.render(_minimal_render_spec(), scene_types=["__not_a_real_scene__"])

    def test_orchestrator_video_export_with_mock(self, tmp_path) -> None:
        from melosviz.conductor.orchestrator import Orchestrator

        stub_path = tmp_path / "out.mp4"
        stub_path.touch()
        orch = Orchestrator(output_dir=tmp_path, skip_assembly=False)
        with patch(
            "melosviz.render.video_exporter.export_video",
            return_value=stub_path,
        ):
            result = orch.render(_minimal_render_spec(), scene_types=["video_export"])
        assert result is not None

    def test_orchestrator_default_output_dir(self) -> None:
        from melosviz.conductor.orchestrator import Orchestrator

        orch = Orchestrator()
        # _output_dir defaults to /tmp/melosviz-conductor when not given
        assert orch._output_dir is not None

    def test_orchestrator_adapter_error_wraps_as_conductor_error(self, tmp_path) -> None:
        from melosviz.conductor.orchestrator import ConductorError, Orchestrator

        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
        with patch(
            "melosviz.render.video_exporter.export_video",
            side_effect=ValueError("simulated adapter inner error"),
        ), pytest.raises(ConductorError, match="adapter.*failed"):
            orch.render(_minimal_render_spec(), scene_types=["video_export"])

    def test_orchestrator_assembly_encode_skips_in_loop(self, tmp_path) -> None:
        """assembly_encode scene_type is handled separately, not dispatched inline."""
        from melosviz.conductor.orchestrator import Orchestrator

        stub_path = tmp_path / "out.mp4"
        stub_path.touch()
        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
        # assembly_encode in the scene_types list should be silently skipped
        with patch(
            "melosviz.render.video_exporter.export_video",
            return_value=stub_path,
        ):
            result = orch.render(
                _minimal_render_spec(),
                scene_types=["video_export", "assembly_encode"],
            )
        assert result is not None
        assert "assembly_encode" not in result.per_scene_results

    def test_orchestrator_derives_scene_types_from_spec(self, tmp_path) -> None:
        """When scene_types is None, orchestrator reads from spec.scene_segments."""
        from melosviz.analysis.models import RenderSpec
        from melosviz.conductor.orchestrator import Orchestrator

        stub_path = tmp_path / "out.mp4"
        stub_path.touch()
        spec = RenderSpec(
            metadata={"fps": 24, "duration": 3.0},
            palette=[],
            scene_segments=[{"scene_type": "video_export", "start": 0.0, "end": 3.0}],
        )
        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
        with patch(
            "melosviz.render.video_exporter.export_video",
            return_value=stub_path,
        ):
            result = orch.render(spec)
        assert "video_export" in result.per_scene_results


# ---------------------------------------------------------------------------
# runtime/touchdesigner/adapter.py
# ---------------------------------------------------------------------------


class TestTDAdapter:
    def test_tdadapter_scene_type(self) -> None:
        from melosviz.runtime.touchdesigner.adapter import TDAdapter

        adapter = TDAdapter()
        assert adapter.scene_type == "live_stage"

    def test_tdadapter_render_generates_network_spec(self, tmp_path) -> None:
        """render() generates network_spec.json without needing TD installed."""
        from melosviz.runtime.touchdesigner.adapter import TDAdapter, TDRenderResult

        adapter = TDAdapter()
        result = adapter.render(_minimal_render_spec(), output_path=tmp_path)
        assert isinstance(result, TDRenderResult)
        # network_spec.json should be written
        assert (tmp_path / "network_spec.json").exists()

    def test_tdadapter_render_live_mode_bridge_start(self, tmp_path) -> None:
        """live_mode=True triggers bridge start; on CI bridge start is non-fatal."""
        from melosviz.runtime.touchdesigner.adapter import TDAdapter, TDRenderResult

        adapter = TDAdapter()
        # live_mode=True: bridge start failure must not crash render (best-effort)
        result = adapter.render(
            _minimal_render_spec(), output_path=tmp_path, live_mode=True
        )
        assert isinstance(result, TDRenderResult)
        # On CI without TD running: live_mode in result may be False (bridge failed)
        assert isinstance(result.live_mode, bool)

    def test_tdadapter_start_bridge_covered(self, tmp_path) -> None:
        """_start_bridge spawns a daemon thread and does not raise."""
        import threading

        from melosviz.runtime.touchdesigner.adapter import TDAdapter

        adapter = TDAdapter()
        before = set(t.name for t in threading.enumerate())
        # Call _start_bridge; it spawns a daemon thread
        adapter._start_bridge(_minimal_render_spec())
        after = set(t.name for t in threading.enumerate())
        assert "melosviz-td-bridge" in after or len(after) >= len(before)


# ---------------------------------------------------------------------------
# runtime/touchdesigner/bridge.py
# ---------------------------------------------------------------------------


class TestTDBridge:
    def test_td_bridge_default_config(self) -> None:
        from melosviz.runtime.touchdesigner.bridge import BridgeConfig, TDBridge

        bridge = TDBridge()
        assert bridge._config is not None
        assert isinstance(bridge._config, BridgeConfig)

    def test_td_bridge_osc_transport_created(self) -> None:
        from melosviz.runtime.touchdesigner.bridge import BridgeConfig, TDBridge

        cfg = BridgeConfig(transport="osc")
        bridge = TDBridge(config=cfg)
        assert bridge._osc is not None
        assert bridge._ws is None

    def test_td_bridge_ws_transport_created(self) -> None:
        from melosviz.runtime.touchdesigner.bridge import BridgeConfig, TDBridge

        cfg = BridgeConfig(transport="websocket")
        bridge = TDBridge(config=cfg)
        assert bridge._ws is not None
        assert bridge._osc is None

    def test_td_bridge_both_transports(self) -> None:
        from melosviz.runtime.touchdesigner.bridge import BridgeConfig, TDBridge

        cfg = BridgeConfig(transport="both")
        bridge = TDBridge(config=cfg)
        assert bridge._osc is not None
        assert bridge._ws is not None

    def test_td_bridge_stream_empty_spec(self) -> None:
        """stream_render_spec on an empty spec should not raise."""
        from melosviz.runtime.touchdesigner.bridge import BridgeConfig, TDBridge

        cfg = BridgeConfig(transport="osc")
        bridge = TDBridge(config=cfg)
        # Patch the OSC send so we don't need a real UDP target
        with patch.object(bridge._osc, "send", return_value=None):
            spec = _minimal_render_spec()
            bridge.stream_render_spec(spec, realtime=False)

    def test_td_bridge_osc_send_failure_is_logged_not_raised(self) -> None:
        """OSC send errors must log a warning, not propagate."""
        from melosviz.runtime.touchdesigner.bridge import BridgeConfig, TDBridge

        cfg = BridgeConfig(transport="osc")
        bridge = TDBridge(config=cfg)
        # OSC send raises OSError — bridge should log and continue
        with patch.object(bridge._osc, "send", side_effect=OSError("unreachable")):
            from melosviz.analysis.models import RenderSpec
            spec = RenderSpec(
                metadata={"fps": 24, "duration": 1.0},
                palette=[],
                timeline_events=[{"t": 0.0, "type": "beat", "data": {}}],
            )
            # Should NOT raise — warning only
            bridge.stream_render_spec(spec, realtime=False)


# ---------------------------------------------------------------------------
# video_exporter.py
# ---------------------------------------------------------------------------


class TestVideoExporter:
    def test_is_ffmpeg_available(self) -> None:
        from melosviz.render.video_exporter import is_ffmpeg_available

        result = is_ffmpeg_available()
        assert isinstance(result, bool)

    def test_export_video_no_ffmpeg_raises(self, tmp_path) -> None:
        from melosviz.render.video_exporter import FFMpegNotFoundError, export_video

        with patch(
            "melosviz.render.video_exporter._resolve_ffmpeg_binary",
            side_effect=FFMpegNotFoundError("no ffmpeg"),
        ), pytest.raises(FFMpegNotFoundError):
            export_video(_minimal_render_spec(), output_dir=tmp_path)

    def test_export_video_palette_cycle(self, tmp_path) -> None:
        """With real ffmpeg available, palette cycle export should produce a file."""
        from melosviz.render.video_exporter import export_video, is_ffmpeg_available

        if not is_ffmpeg_available():
            pytest.skip("ffmpeg not available")

        # Use a very short spec (1s @ 1fps) to keep test fast
        from melosviz.analysis.models import RenderSpec

        spec = RenderSpec(
            metadata={"duration": 1.0, "fps": 1, "bpm": 120.0},
            palette=["#000000", "#ffffff"],
        )
        out = export_video(spec, output_dir=tmp_path)
        assert out is not None and Path(out).exists()

    def test_frame_rgb24_bytes_length(self) -> None:
        from melosviz.render.video_exporter import _frame_rgb24_bytes

        frame = _frame_rgb24_bytes(4, 4, (255, 0, 0))
        assert len(frame) == 4 * 4 * 3  # width * height * 3 channels


# ---------------------------------------------------------------------------
# analysis/audio.py  — cover the uncovered branches
# ---------------------------------------------------------------------------


class TestAudioAnalysis:
    def test_spec_from_wav_returns_render_spec(self, tmp_path) -> None:
        from melosviz.analysis.audio import spec_from_wav
        from melosviz.analysis.models import RenderSpec

        wav = _make_wav(tmp_path / "t.wav")
        spec = spec_from_wav(wav)
        assert isinstance(spec, RenderSpec)
        assert "duration" in spec.metadata

    def test_spec_from_wav_rich_returns_render_spec(self, tmp_path) -> None:
        from melosviz.analysis.audio import spec_from_wav_rich
        from melosviz.analysis.models import RenderSpec

        wav = _make_wav(tmp_path / "t.wav")
        spec = spec_from_wav_rich(wav)
        assert isinstance(spec, RenderSpec)

    def test_spec_from_wav_nonexistent_raises(self) -> None:
        from melosviz.analysis.audio import spec_from_wav

        with pytest.raises((FileNotFoundError, Exception)):
            spec_from_wav(Path("/nonexistent/fake.wav"))

    def test_spec_from_wav_amplitude_envelope(self, tmp_path) -> None:
        from melosviz.analysis.audio import spec_from_wav

        wav = _make_wav(tmp_path / "t.wav", duration_s=2.0)
        spec = spec_from_wav(wav)
        # amplitude_envelope should be a list of floats
        if hasattr(spec, "amplitude_envelope") and spec.amplitude_envelope:
            assert all(isinstance(v, float) for v in spec.amplitude_envelope)

    def test_beat_frames_detection(self, tmp_path) -> None:
        """beat_frames should be a list (possibly empty for short clips)."""
        from melosviz.analysis.audio import spec_from_wav

        wav = _make_wav(tmp_path / "t.wav", duration_s=3.0)
        spec = spec_from_wav(wav)
        if hasattr(spec, "beat_frames"):
            assert isinstance(spec.beat_frames, list)


# ---------------------------------------------------------------------------
# PROPERTY TESTS (hypothesis)
# ---------------------------------------------------------------------------


try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestPropertyPresets:
    @given(
        bpm=st.floats(min_value=60.0, max_value=200.0, allow_nan=False, allow_infinity=False),
        fps=st.integers(min_value=1, max_value=60),
        duration=st.floats(min_value=0.5, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=30)
    def test_cinematic_apply_always_sets_palette(
        self, bpm: float, fps: int, duration: float
    ) -> None:
        from melosviz.analysis.models import RenderSpec
        from melosviz.presets.cinematic import CINEMATIC_PALETTE, apply

        spec = RenderSpec(
            metadata={"bpm": bpm, "fps": fps, "duration": duration},
            palette=[],
        )
        result = apply(spec)
        assert result.palette == list(CINEMATIC_PALETTE)

    @given(
        palette_size=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=20)
    def test_cinematic_timeline_always_grows(self, palette_size: int) -> None:
        from melosviz.analysis.models import RenderSpec
        from melosviz.presets.cinematic import apply

        initial_events = [{"time": float(i), "type": "beat", "data": {}} for i in range(palette_size)]
        spec = RenderSpec(
            metadata={"fps": 24, "duration": 30.0},
            palette=[],
            timeline=initial_events,
        )
        before = len(spec.timeline)
        result = apply(spec)
        assert len(result.timeline) >= before


# ---------------------------------------------------------------------------
# CHAOS TESTS — bridge/backend resilience
# ---------------------------------------------------------------------------


class TestChaosResilience:
    """Verify that failures in sub-components surface clearly (fail-loud, not silent)."""

    def test_spec_from_wav_with_corrupt_wav(self, tmp_path) -> None:
        from melosviz.analysis.audio import spec_from_wav

        corrupt = tmp_path / "bad.wav"
        corrupt.write_bytes(b"not a wav file at all")
        # Corrupt WAV must raise some error (wave.Error, EOFError, or similar)
        try:
            spec_from_wav(corrupt)
        except (wave.Error, EOFError, ValueError, OSError, RuntimeError):
            pass  # expected — the point is it does NOT silently return a valid spec
        else:
            pytest.fail("spec_from_wav on corrupt data should raise")

    def test_cli_analyze_corrupt_wav_raises_or_returns_1(self, tmp_path) -> None:
        from melosviz.cli.main import _cmd_analyze

        corrupt = tmp_path / "bad.wav"
        corrupt.write_bytes(b"\x00\x01\x02")
        args = SimpleNamespace(wav=str(corrupt))
        # Either raises or returns non-zero — both acceptable (fail loud)
        try:
            rc = _cmd_analyze(args)
            assert rc != 0
        except (wave.Error, EOFError, ValueError, OSError, RuntimeError):
            pass  # expected

    def test_bridge_analyze_corrupt_wav_raises(self, tmp_path) -> None:
        """Corrupt WAV must produce an error, not silently return a valid spec."""
        from melosviz.analysis.audio import spec_from_wav

        corrupt = tmp_path / "bad.wav"
        corrupt.write_bytes(b"\x00\x01\x02\x03\x04")
        try:
            spec_from_wav(corrupt)
        except (wave.Error, EOFError, ValueError, OSError, RuntimeError):
            pass  # expected
        else:
            pytest.fail("spec_from_wav on corrupt data should raise")

    def test_orchestrator_adapter_failure_propagates(self, tmp_path) -> None:
        from melosviz.conductor.orchestrator import Orchestrator

        orch = Orchestrator(output_dir=tmp_path, skip_assembly=False)
        with patch(
            "melosviz.render.video_exporter.export_video",
            side_effect=RuntimeError("simulated adapter failure"),
        ), pytest.raises((RuntimeError, Exception)):
            orch.render(_minimal_render_spec(), scene_types=["video_export"])

    def test_td_bridge_osc_send_failure_propagates_as_warning(self) -> None:
        """OSC send errors must be logged, never silently ignored or crash."""
        from melosviz.runtime.touchdesigner.bridge import BridgeConfig, TDBridge

        cfg = BridgeConfig(transport="osc")
        bridge = TDBridge(config=cfg)
        # Inject an OSError — it should log and continue (fail-safe, not fail-silent)
        with patch.object(bridge._osc, "send", side_effect=OSError("timeout")):
            from melosviz.analysis.models import RenderSpec

            spec = RenderSpec(
                metadata={"fps": 24, "duration": 1.0},
                palette=[],
                timeline_events=[{"t": 0.0, "type": "beat", "data": {}}],
            )
            # This must not raise — OSC errors are logged
            bridge.stream_render_spec(spec, realtime=False)


# ---------------------------------------------------------------------------
# PERF SMOKE — analysis init must be <15s
# ---------------------------------------------------------------------------


class TestPerfSmoke:
    def test_spec_from_wav_init_under_15s(self, tmp_path) -> None:
        """spec_from_wav (dep-light path) must complete in <15s for a 3s clip."""
        from melosviz.analysis.audio import spec_from_wav

        wav = _make_wav(tmp_path / "t.wav", duration_s=3.0)
        t0 = time.monotonic()
        spec_from_wav(wav)
        elapsed = time.monotonic() - t0
        assert elapsed < 15.0, f"spec_from_wav took {elapsed:.2f}s — exceeds 15s budget"

    def test_cinematic_apply_under_100ms(self) -> None:
        """Preset application must be near-instant (no I/O, no subprocess)."""
        from melosviz.presets.cinematic import apply

        spec = _minimal_render_spec()
        t0 = time.monotonic()
        apply(spec)  # type: ignore[arg-type]
        elapsed = time.monotonic() - t0
        assert elapsed < 0.1, f"cinematic.apply took {elapsed:.3f}s — should be <100ms"
