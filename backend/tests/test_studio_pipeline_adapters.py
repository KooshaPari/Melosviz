"""Tests for the new ComfyUI / Cinema 4D / Unreal / DaVinci adapters.

Each adapter is exercised against a minimal RenderSpec v2 fixture.  The
goal is not to actually invoke external binaries (those are not
guaranteed to be installed in CI), but to assert that:

* the adapter class is registered in ``ADAPTER_REGISTRY``,
* ``scene_type`` attribute matches the registry key,
* the ``render(...)`` method either produces a real artefact (when
  the tool is present) or raises a *named* error (when it is not),
* for pure-Python helpers the function returns a JSON-serialisable
  job spec / parameters dict.

We also test the offline-fallback path of the ComfyUI adapter (mock
ComfyUI server) so that ``render`` always succeeds in CI.
"""

from __future__ import annotations

import json
import wave
import struct
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minimal_spec() -> Any:
    from melosviz.analysis.models import RenderSpec

    return RenderSpec(
        metadata={
            "source_audio": "test.wav",
            "duration": 30.0,
            "fps": 30,
            "width": 1280,
            "height": 720,
            "estimated_bpm": 124.0,
        },
        palette=["#0d0d10", "#ff2bd6", "#22d3ee"],
        scene_segments=[
            {
                "index": 0,
                "label": "intro",
                "start": 0.0,
                "end": 8.0,
                "energy_mean": 0.3,
                "scene_type": "comfyui_image",
            },
            {
                "index": 1,
                "label": "verse",
                "start": 8.0,
                "end": 22.0,
                "energy_mean": 0.6,
                "scene_type": "comfyui_video",
            },
            {
                "index": 2,
                "label": "chorus",
                "start": 22.0,
                "end": 30.0,
                "energy_mean": 0.85,
                "scene_type": "unreal_cinematic",
            },
            {
                "index": 3,
                "label": "outro",
                "start": 30.0,
                "end": 40.0,
                "energy_mean": 0.4,
                "scene_type": "c4d_3d",
            },
        ],
    )


# ---------------------------------------------------------------------------
# Registry coverage
# ---------------------------------------------------------------------------


def test_registry_covers_new_adapters() -> None:
    from melosviz.conductor.registry import ADAPTER_REGISTRY

    assert "comfyui_image" in ADAPTER_REGISTRY
    assert "comfyui_video" in ADAPTER_REGISTRY
    assert "c4d_3d" in ADAPTER_REGISTRY
    assert "unreal_cinematic" in ADAPTER_REGISTRY
    assert "davinci_master" in ADAPTER_REGISTRY


# ---------------------------------------------------------------------------
# ComfyUI adapter
# ---------------------------------------------------------------------------


def test_comfyui_adapter_scene_type() -> None:
    from melosviz.render.comfyui_adapter import ComfyUIAdapter, SCENE_TYPES

    assert ComfyUIAdapter.scene_type in SCENE_TYPES


def test_comfyui_offline_mode_emits_job_spec_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``MELOSVIZ_COMFYUI_OFFLINE=1`` the adapter writes a
    per-scene job-spec JSON and never touches the network."""
    from melosviz.render import comfyui_adapter as mod

    monkeypatch.setenv("MELOSVIZ_COMFYUI_OFFLINE", "1")
    monkeypatch.setenv("MELOSVIZ_COMFYUI_URL", "http://fake-comfyui:8188")

    adapter = mod.ComfyUIAdapter(scene_type="comfyui_image")
    out = tmp_path / "comfyui"
    result = adapter.render(_minimal_spec(), output_path=out)
    # Each scene gets a per-scene workflow.json + a manifest
    assert any(out.rglob("workflow.json"))
    manifest = out / "job_spec.json"
    assert manifest.exists()
    spec = json.loads(manifest.read_text())
    assert spec["mode"] == "offline-job-spec"
    assert len(spec["scenes"]) == 4
    for scene in spec["scenes"]:
        assert "prompt" in scene
        assert scene["prompt"].count(",") >= 1


def test_comfyui_unavailable_raises_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ComfyUI is unreachable the adapter raises ComfyUIUnavailableError."""
    from melosviz.render import comfyui_adapter as mod

    monkeypatch.setattr(mod, "is_comfyui_available", lambda base=None: False)
    monkeypatch.setenv("MELOSVIZ_COMFYUI_OFFLINE", "0")
    monkeypatch.setenv("MELOSVIZ_COMFYUI_URL", "http://127.0.0.1:1")  # unreachable

    adapter = mod.ComfyUIAdapter(scene_type="comfyui_image")
    with pytest.raises(mod.ComfyUIUnavailableError):
        adapter.render(_minimal_spec(), output_path=tmp_path)


def test_comfyui_workflow_templates_are_valid_json() -> None:
    """The shipped workflow templates must be parseable JSON graphs."""
    from melosviz.render.comfyui_adapter import _workflows_dir

    for fname in ("sdxl_image.json", "wan_video.json"):
        path = _workflows_dir() / fname
        assert path.is_file(), f"missing template: {path}"
        graph = json.loads(path.read_text())
        # Every node needs class_type + inputs
        for nid, node in graph.items():
            assert "class_type" in node, f"node {nid} has no class_type"
            assert "inputs" in node, f"node {nid} has no inputs"


# ---------------------------------------------------------------------------
# Cinema 4D adapter
# ---------------------------------------------------------------------------


def test_cinema4d_adapter_scene_type() -> None:
    from melosviz.render.cinema4d_adapter import C4DAdapter

    assert C4DAdapter.scene_type == "c4d_3d"


def test_cinema4d_adapter_raises_not_found_when_tool_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When neither c4dpy nor Commandline is on the box, render raises C4DNotFoundError."""
    from melosviz.render import cinema4d_adapter as mod

    monkeypatch.setattr(mod, "_c4d_python", lambda: None)
    monkeypatch.setattr(mod, "_c4d_bin", lambda: None)
    monkeypatch.setattr(mod, "is_c4d_available", lambda: False)

    adapter = mod.C4DAdapter()
    out = tmp_path / "c4d"
    with pytest.raises(mod.C4DNotFoundError):
        adapter.render(_minimal_spec(), output_path=out)


def test_cinema4d_scaffold_script_mentions_beat_or_segments() -> None:
    """The generated .py script must reference framerate / render settings."""
    from melosviz.render.cinema4d_adapter import scaffold_script

    src = scaffold_script(
        {
            "name": "test_scene",
            "width": 1280,
            "height": 720,
            "frames": 120,
            "fps": 24,
        },
        project=None,
        renderer="redshift",
        output_dir=Path("/tmp/out"),
    )
    assert "W, H = 1280, 720" in src
    assert "FRAMES, FPS = 120, 24" in src


# ---------------------------------------------------------------------------
# Unreal Engine adapter
# ---------------------------------------------------------------------------


def test_unreal_adapter_scene_type() -> None:
    from melosviz.render.unreal_adapter import UEAdapter

    assert UEAdapter.scene_type == "unreal_cinematic"


def test_unreal_adapter_raises_not_found_when_tool_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When UE binary + project are not present, render raises UENotFoundError."""
    from melosviz.render import unreal_adapter as mod

    monkeypatch.setattr(mod, "_ue_bin", lambda: None)
    monkeypatch.setattr(mod, "_ue_project", lambda: None)
    monkeypatch.setattr(mod, "is_unreal_available", lambda: False)

    adapter = mod.UEAdapter()
    out = tmp_path / "unreal"
    with pytest.raises(mod.UENotFoundError):
        adapter.render(_minimal_spec(), output_path=out)


def test_unreal_driver_template_is_valid_python() -> None:
    """The shipped UE driver script should at least parse as Python."""
    import ast

    from melosviz.render.unreal_adapter import _DRIVER_TEMPLATE

    ast.parse(_DRIVER_TEMPLATE)  # raises SyntaxError if malformed


def test_unreal_adapter_build_targets_returns_one_per_scene() -> None:
    """UEAdapter should hand back a target dict per matching scene."""
    from melosviz.render import unreal_adapter as mod

    targets = mod._extract_scenes(_minimal_spec(), scene_type="unreal_cinematic")
    assert len(targets) == 1
    assert targets[0]["scene_type"] == "unreal_cinematic"


# ---------------------------------------------------------------------------
# DaVinci Resolve adapter
# ---------------------------------------------------------------------------


def test_resolve_adapter_scene_type() -> None:
    from melosviz.render.davinci_adapter import ResolveAdapter

    assert ResolveAdapter.scene_type in ("davinci_finish", "davinci_resolve_finish")


def test_resolve_adapter_uses_ffmpeg_fallback_when_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Resolve is missing, ResolveAdapter.render() should fall back to ffmpeg
    (still produces a usable master) — never silently drop the master step."""
    from melosviz.render import davinci_adapter as mod

    monkeypatch.setattr(mod, "is_resolve_available", lambda: False)
    # Mock ffmpeg fallback so we don't need real ffmpeg in CI.
    monkeypatch.setattr(
        mod,
        "render_with_ffmpeg_fallback",
        lambda tl, *, output_dir, segment_paths=None: [Path(output_dir) / "mock.mp4"],
    )

    edit = tmp_path / "rough.mp4"
    edit.write_bytes(b"\x00")
    out = tmp_path / "master"
    adapter = mod.ResolveAdapter()
    res = adapter.render(_minimal_spec(), output_path=out, segment_paths=[edit])
    assert any(p.name == "mock.mp4" for p in res)


def test_resolve_timeline_includes_three_deliverables() -> None:
    """The Resolve timeline JSON must declare all 3 deliverables
    (festival ProRes / club H264 / YouTube H264)."""
    from melosviz.render.davinci_adapter import build_resolve_timeline

    tl = build_resolve_timeline(
        _minimal_spec(),
        segment_paths=[],
        output_dir=Path("/tmp/master"),
    )
    names = {d["name"] for d in tl["deliverables"]}
    assert {"festival_master", "club_1080p", "youtube_1080p"} <= names


# ---------------------------------------------------------------------------
# CLI surface — storyboard / generate subcommands
# ---------------------------------------------------------------------------


def test_cli_help_lists_new_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    from melosviz.cli.main import main

    with pytest.raises(SystemExit) as exc:
        main(argv=["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr().out
    for cmd in ("storyboard", "generate", "assemble", "master", "ship"):
        assert cmd in captured, f"missing {cmd!r} in CLI help"


def test_storyboard_subcommand_emits_json_for_synthetic_wav(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end: build a tiny WAV, call ``viz storyboard``, assert a
    storyboard JSON is written with the right number of scenes."""
    wav = tmp_path / "tone.wav"
    sr = 22050
    n = sr * 2  # 2 seconds
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        for i in range(n):
            sample = int(0.3 * 32767 * ((i % 463) / 463.0))
            w.writeframes(struct.pack("<h", sample))

    from melosviz.cli.main import main

    with pytest.raises(SystemExit) as exc:
        main(argv=["storyboard", str(wav), "--concept", "neon festival",
                  "--out", str(tmp_path)])
    assert exc.value.code == 0
    payload = json.loads((tmp_path / "storyboard.json").read_text())
    assert payload["concept"] == "neon festival"
    assert isinstance(payload["scenes"], list)
    assert len(payload["scenes"]) >= 1
    for s in payload["scenes"]:
        assert "scene_type" in s
        assert "prompt" in s