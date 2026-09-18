"""Regression: orchestrator must surface artifacts from list-returning adapters.

A1 verification (2026-09-17) found that ``Orchestrator.render`` extracts
``artifact`` only from objects exposing ``.files`` or ``.output_paths``.
Adapters that return ``list[Path]`` (ComfyUI, Cinema4D, DaVinci) therefore
emitted ``done`` events with ``artifact_path=""`` and wrote provenance
sidecars without an artifact path, so production acceptance could not
distinguish a real clip from an empty result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from melosviz.conductor import registry as registry_mod
from melosviz.conductor.orchestrator import Orchestrator


class _ListAdapter:
    """Minimal stand-in for adapters whose render() returns list[Path]."""

    scene_type = "comfyui_image"

    def render(self, render_spec: Any, **kwargs: Any) -> list[Path]:
        out = Path(str(kwargs["output_path"]))
        out.mkdir(parents=True, exist_ok=True)
        clip = out / "clip.mp4"
        clip.write_bytes(b"\x00" * 16)
        return [clip]


def test_done_event_carries_artifact_from_list_returning_adapter(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setitem(
        registry_mod.ADAPTER_REGISTRY, "comfyui_image", _ListAdapter
    )
    orch = Orchestrator(
        output_dir=tmp_path / "out",
        skip_assembly=True,
        auto_offline=False,
    )
    spec = {
        "scene_segments": [
            {
                "scene_index": 0,
                "scene_name": "s0",
                "scene_type": "comfyui_image",
            }
        ]
    }
    result = orch.render(spec)
    states = [getattr(e, "state", None) for e in result.events]
    done = [e for e in result.events if getattr(e, "state", "") == "done"]
    assert done, (
        f"expected a done event, got states={states!r} "
        f"errors={[getattr(e, 'error', None) for e in result.events]}"
    )
    assert done[0].artifact_path, (
        "done event must carry a non-empty artifact_path for list-returning adapters"
    )
    assert done[0].artifact_path.endswith("clip.mp4")


def test_provenance_outcome_tag_present(tmp_path: Path, monkeypatch) -> None:
    """Provenance sidecar records outcome=render vs offline-placeholder (A1)."""
    from melosviz.conductor.provenance import provenance_path_for

    monkeypatch.setitem(
        registry_mod.ADAPTER_REGISTRY, "comfyui_image", _ListAdapter
    )
    orch = Orchestrator(
        output_dir=tmp_path / "out",
        skip_assembly=True,
        auto_offline=False,
    )
    spec = {
        "scene_segments": [
            {
                "scene_index": 0,
                "scene_name": "s0",
                "scene_type": "comfyui_image",
            }
        ]
    }
    orch.render(spec)
    sidecars = list((tmp_path / "out").rglob("*.provenance.json"))
    assert len(sidecars) == 1, f"expected exactly 1 provenance sidecar: {sidecars}"
    import json as _json

    d = _json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert d.get("artifact_path", "").endswith("clip.mp4"), (
        f"provenance artifact_path empty or wrong: {d.get('artifact_path')!r}"
    )
    assert d.get("extra", {}).get("outcome") == "render", (
        f"provenance extra.outcome missing or wrong: {d.get('extra')!r}"
    )
