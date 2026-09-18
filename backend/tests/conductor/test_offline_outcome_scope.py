"""Regression: the offline label must cover every scene type offline mode serves.

Real-path incident: with ``MELOSVIZ_COMFYUI_OFFLINE=1`` a ``viz generate`` run
produced a placeholder clip plus ``job_spec.json`` for a ``comfyui_video`` and a
``comfyui_audio_video_seedance`` scene, yet their provenance sidecars recorded
``extra.outcome = "render"``. Only ``comfyui_image`` was labelled
``offline-placeholder``, because the orchestrator hardcoded that one scene type
while the adapter branches on offline mode once, before any dispatch.

The label now comes from the serving adapter (``emits_offline_placeholders``), so
an adapter without an offline branch still reports ``render``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from melosviz.conductor import registry as registry_mod
from melosviz.conductor.orchestrator import Orchestrator

OFFLINE_ENV = "MELOSVIZ_COMFYUI_OFFLINE"


class _OfflineCapableAdapter:
    """Stands in for an adapter whose offline mode emits placeholder clips."""

    emits_offline_placeholders = True

    def render(self, render_spec: Any, **kwargs: Any) -> list[Path]:
        out = Path(str(kwargs["output_path"]))
        out.mkdir(parents=True, exist_ok=True)
        clip = out / "placeholder.mp4"
        clip.write_bytes(b"\x00" * 16)
        return [clip]


class _NoOfflineBranchAdapter:
    """An adapter with no offline branch must keep reporting a real render."""

    def render(self, render_spec: Any, **kwargs: Any) -> list[Path]:
        out = Path(str(kwargs["output_path"]))
        out.mkdir(parents=True, exist_ok=True)
        clip = out / "render.mp4"
        clip.write_bytes(b"\x00" * 16)
        return [clip]


def _render(tmp_path: Path, scene_type: str, adapter: Any, monkeypatch) -> dict:
    monkeypatch.setitem(registry_mod.ADAPTER_REGISTRY, scene_type, adapter)
    spec = {
        "scene_segments": [
            {"scene_index": 0, "scene_name": "s0", "scene_type": scene_type}
        ]
    }
    orch = Orchestrator(
        output_dir=tmp_path / "out", skip_assembly=True, auto_offline=False
    )
    orch.render(spec)
    sidecar = next((tmp_path / "out").rglob("*.provenance.json"))
    return json.loads(sidecar.read_text(encoding="utf-8"))


def test_non_image_comfyui_scene_is_labelled_offline(
    tmp_path: Path, monkeypatch
) -> None:
    """Regression: comfyui_video offline was reported as a real render."""
    monkeypatch.setenv(OFFLINE_ENV, "1")
    payload = _render(
        tmp_path, "comfyui_video", _OfflineCapableAdapter, monkeypatch
    )
    assert payload["extra"]["outcome"] == "offline-placeholder", (
        f"offline-produced scene labelled {payload['extra']['outcome']!r}"
    )


def test_adapter_without_offline_branch_still_reports_render(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(OFFLINE_ENV, "1")
    payload = _render(
        tmp_path, "video_export", _NoOfflineBranchAdapter, monkeypatch
    )
    assert payload["extra"]["outcome"] == "render", (
        f"adapter without an offline branch labelled {payload['extra']['outcome']!r}"
    )


def test_comfyui_adapter_declares_offline_placeholders() -> None:
    """The shipped adapter must declare the capability the label relies on."""
    from melosviz.render.comfyui_adapter import ComfyUIAdapter

    assert getattr(ComfyUIAdapter, "emits_offline_placeholders", False) is True
