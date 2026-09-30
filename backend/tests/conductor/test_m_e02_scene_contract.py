"""M-E02 contract tests: scene identity, selection, iteration and assembly."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class Spec:
    scene_segments: list[dict]
    fps: int = 24

    def model_dump(self):
        return {"scene_segments": self.scene_segments, "fps": self.fps, "title": "m-e02"}

    def model_copy(self, *, update):
        data = self.model_dump()
        data.update(update)
        return Spec(scene_segments=list(data["scene_segments"]), fps=data["fps"])


class SceneAdapter:
    calls: list[list[dict]] = []

    def render(self, spec, *, output_path, **kwargs):
        segs = spec.model_dump()["scene_segments"]
        type(self).calls.append(segs)
        assert len(segs) == 1, "adapter work item must be one scene"
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        artifact = output_path / "clip.mp4"
        artifact.write_bytes(("scene:" + str(segs[0]["marker"])).encode())
        return artifact


class AssemblyAdapter:
    calls: list[list[str]] = []

    def render(self, spec, *, output_path, segment_paths, **kwargs):
        paths = [str(p) for p in segment_paths]
        type(self).calls.append(paths)
        return {"segment_paths": paths}


@pytest.fixture(autouse=True)
def _clear_calls():
    SceneAdapter.calls = []
    AssemblyAdapter.calls = []


def _registry(monkeypatch):
    from melosviz.conductor import registry

    monkeypatch.setattr(
        registry,
        "ADAPTER_REGISTRY",
        {"comfyui_image": SceneAdapter, "assembly_encode": AssemblyAdapter},
    )


def _spec():
    return Spec(
        [
            {"scene_type": "comfyui_image", "name": "S0", "marker": "zero"},
            {"scene_type": "comfyui_image", "name": "S1", "marker": "one"},
            {"scene_type": "comfyui_image", "name": "S2", "marker": "two"},
        ]
    )


def test_same_backend_scenes_are_one_work_item_each(tmp_path, monkeypatch):
    from melosviz.conductor.orchestrator import Orchestrator

    _registry(monkeypatch)
    result = Orchestrator(output_dir=tmp_path).render(_spec())

    assert [x[0]["marker"] for x in SceneAdapter.calls] == ["zero", "one", "two"]
    assert list(result.per_scene_results) == [0, 1, 2]
    assert [result.per_scene_results[i]["scene_type"] for i in range(3)] == [
        "comfyui_image",
        "comfyui_image",
        "comfyui_image",
    ]
    assert len(AssemblyAdapter.calls) == 1
    assert len(AssemblyAdapter.calls[0]) == 3
    assert [Path(p).read_text() for p in AssemblyAdapter.calls[0]] == [
        "scene:zero",
        "scene:one",
        "scene:two",
    ]


def test_constructor_only_scenes_filters_before_adapter_work(tmp_path, monkeypatch):
    from melosviz.conductor.orchestrator import Orchestrator

    _registry(monkeypatch)
    result = Orchestrator(output_dir=tmp_path, skip_assembly=True, only_scenes=[1]).render(
        _spec()
    )

    assert [x[0]["marker"] for x in SceneAdapter.calls] == ["one"]
    assert list(result.per_scene_results) == [1]


def test_render_selector_overrides_constructor_selector(tmp_path, monkeypatch):
    from melosviz.conductor.orchestrator import Orchestrator

    _registry(monkeypatch)
    result = Orchestrator(
        output_dir=tmp_path, skip_assembly=True, only_scenes=[0]
    ).render(_spec(), only_scenes=[2])

    assert [x[0]["marker"] for x in SceneAdapter.calls] == ["two"]
    assert list(result.per_scene_results) == [2]


def test_invalid_selector_fails_before_adapter_work(tmp_path, monkeypatch):
    from melosviz.conductor.orchestrator import ConductorError, Orchestrator

    _registry(monkeypatch)
    with pytest.raises(ConductorError, match="out-of-range"):
        Orchestrator(output_dir=tmp_path, only_scenes=[99]).render(_spec())
    assert SceneAdapter.calls == []
    assert AssemblyAdapter.calls == []


def test_done_event_exposes_execution_outcome(tmp_path, monkeypatch):
    from melosviz.conductor.orchestrator import OUTCOME_RENDER, Orchestrator

    _registry(monkeypatch)
    result = Orchestrator(output_dir=tmp_path, skip_assembly=True, only_scenes=[0]).render(
        _spec()
    )
    done = [e for e in result.events if getattr(e, "state", None) == "done"]
    assert len(done) == 1
    extras = getattr(done[0], "extras", None) or {}
    assert extras.get("outcome") == OUTCOME_RENDER
