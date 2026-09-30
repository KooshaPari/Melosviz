"""M-E02 contract tests: scene identity, selection, iteration and assembly."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import wave

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
        artifact = output_path / "clip.wav"
        marker = str(segs[0]["marker"]).encode()
        # Real, decodable media fixture. Encode marker bytes as sample values so
        # distinct scenes remain distinguishable without accepting fake .mp4 bytes.
        pcm = bytes((b % 128 for b in marker)) * 256
        if len(pcm) % 2:
            pcm += b"\0"
        with wave.open(str(artifact), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(pcm)
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
    assert all(result.per_scene_results[i]["artifact_sha256"] for i in range(3))
    assert len(AssemblyAdapter.calls) == 1
    assert len(AssemblyAdapter.calls[0]) == 3
    assert all(Path(p).suffix == ".wav" and Path(p).stat().st_size > 44 for p in AssemblyAdapter.calls[0])
    assert len({Path(p).read_bytes() for p in AssemblyAdapter.calls[0]}) == 3


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


def test_cache_materialisation_replaces_equal_size_wrong_bytes(tmp_path):
    from melosviz.conductor.orchestrator import _materialise_cached_artifact

    output = tmp_path / "out"
    scene = output / "comfyui_image" / "dispatch_000"
    scene.mkdir(parents=True)
    blob = tmp_path / "cache.bin"
    blob.write_bytes(b"NEW!")
    blob.with_suffix(".json").write_text(
        '{"artifact_relpath":"comfyui_image/dispatch_000/clip.mp4"}'
    )
    target = scene / "clip.mp4"
    target.write_bytes(b"OLD!")

    got = _materialise_cached_artifact(blob, output, scene)

    assert got == target
    assert target.read_bytes() == b"NEW!"


def test_cache_hit_done_event_carries_outcome(tmp_path, monkeypatch):
    from melosviz.conductor.events import OUTCOME_RENDER
    from melosviz.conductor.orchestrator import Orchestrator
    import melosviz.conductor.orchestrator as orchestrator_module

    _registry(monkeypatch)
    cached = tmp_path / "cached.wav"
    with wave.open(str(cached), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x01\x00" * 256)
    monkeypatch.setattr(orchestrator_module, "scene_render_cached", lambda *_: cached)
    monkeypatch.setattr(
        orchestrator_module,
        "scene_cache_meta",
        lambda *_: {"outcome": OUTCOME_RENDER},
    )

    result = Orchestrator(
        output_dir=tmp_path / "out", skip_assembly=True, only_scenes=[0]
    ).render(_spec())

    assert SceneAdapter.calls == []
    assert result.per_scene_results[0]["outcome"] == OUTCOME_RENDER
    done = [e for e in result.events if getattr(e, "state", None) == "done"]
    assert len(done) == 1
    assert (getattr(done[0], "extras", None) or {}).get("outcome") == OUTCOME_RENDER


def test_same_named_same_prompt_scenes_get_distinct_cache_identity(tmp_path, monkeypatch):
    from melosviz.conductor.orchestrator import Orchestrator
    import melosviz.conductor.orchestrator as orchestrator_module

    _registry(monkeypatch)
    seen_fingerprints = []

    class NoHit:
        cache_dir = tmp_path / "cache"

        def store(self, key, **kwargs):
            seen_fingerprints.append(key.fingerprint())

    spec = Spec(
        [
            {"scene_type": "comfyui_image", "name": "same", "prompt": "same", "marker": "x"},
            {"scene_type": "comfyui_image", "name": "same", "prompt": "same", "marker": "x"},
        ]
    )
    orch = Orchestrator(output_dir=tmp_path / "out", skip_assembly=True)
    orch._render_cache = NoHit()
    monkeypatch.setattr(orchestrator_module, "scene_render_cached", lambda *_: None)

    orch.render(spec)

    assert len(seen_fingerprints) == 2
    assert seen_fingerprints[0] != seen_fingerprints[1]


def test_nonempty_garbage_mp4_is_not_render(tmp_path, monkeypatch):
    from melosviz.conductor.orchestrator import OUTCOME_MALFORMED, Orchestrator

    class GarbageAdapter:
        def render(self, spec, *, output_path, **kwargs):
            output_path = Path(output_path)
            output_path.mkdir(parents=True, exist_ok=True)
            artifact = output_path / "garbage.mp4"
            artifact.write_bytes(bytes(64))
            return artifact

    from melosviz.conductor import registry
    monkeypatch.setattr(registry, "ADAPTER_REGISTRY", {"comfyui_image": GarbageAdapter})
    result = Orchestrator(output_dir=tmp_path, skip_assembly=True, only_scenes=[0]).render(_spec())
    assert result.per_scene_results[0]["outcome"] == OUTCOME_MALFORMED
    assert result.per_scene_results[0]["artifact_sha256"] is None


def test_cache_historical_render_label_does_not_override_current_media_validation(tmp_path, monkeypatch):
    from melosviz.conductor.events import OUTCOME_MALFORMED, OUTCOME_RENDER
    from melosviz.conductor.orchestrator import Orchestrator
    import melosviz.conductor.orchestrator as orchestrator_module

    _registry(monkeypatch)
    cached = tmp_path / "cached.mp4"
    cached.write_bytes(bytes(64))
    monkeypatch.setattr(orchestrator_module, "scene_render_cached", lambda *_: cached)
    monkeypatch.setattr(orchestrator_module, "scene_cache_meta", lambda *_: {"outcome": OUTCOME_RENDER})
    result = Orchestrator(output_dir=tmp_path / "out", skip_assembly=True, only_scenes=[0]).render(_spec())
    assert result.per_scene_results[0]["outcome"] == OUTCOME_MALFORMED
