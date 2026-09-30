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


def test_cli_assembly_state_distinguishes_plan_from_real_media(tmp_path):
    from melosviz.cli.main import _assembly_execution_state

    class PlanOnly:
        used_ffmpeg_fallback = False
        ffmpeg_output_path = None

    class Produced:
        used_ffmpeg_fallback = True
        ffmpeg_output_path = tmp_path / "assembled.mp4"

    assert _assembly_execution_state(None) == "not_attempted"
    assert _assembly_execution_state(PlanOnly()) == "plan_only"
    produced = Produced()
    assert _assembly_execution_state(produced) == "plan_only"
    produced.ffmpeg_output_path.write_bytes(b"media")
    assert _assembly_execution_state(produced) == "produced_unverified"


def test_partial_rerender_reuses_only_valid_unchanged_cache_for_full_assembly(
    tmp_path, monkeypatch
):
    from melosviz.conductor.orchestrator import Orchestrator

    _registry(monkeypatch)
    out = tmp_path / "out"
    orch = Orchestrator(output_dir=out)
    r1 = _spec()
    # Partial-rerender reuse is only admissible for real renders whose backend /
    # model / workflow identity is explicit. This fixture is a synthetic real
    # renderer, so qualify its cache evidence rather than weakening production
    # cache policy.
    for seg in r1.scene_segments:
        seg["cache_extra"] = {"backend_identity": "fixture-model-workflow:v1"}
    orch.render(r1)
    assert len(AssemblyAdapter.calls[-1]) == 3
    r1_bytes = [Path(p).read_bytes() for p in AssemblyAdapter.calls[-1]]

    r2 = _spec()
    for seg in r2.scene_segments:
        seg["cache_extra"] = {"backend_identity": "fixture-model-workflow:v1"}
    r2.scene_segments[1] = dict(r2.scene_segments[1])
    # Change a declared production cache input (prompt) and the synthetic
    # fixture marker that SceneAdapter turns into output bytes. Marker alone is
    # intentionally not part of SceneCacheKey unless an adapter declares it via
    # cache_extra.
    r2.scene_segments[1]["prompt"] = "scene one revised"
    r2.scene_segments[1]["marker"] = "one-r2"
    SceneAdapter.calls = []
    AssemblyAdapter.calls = []

    result = Orchestrator(output_dir=out, only_scenes=[1]).render(r2)

    assert [x[0]["marker"] for x in SceneAdapter.calls] == ["one-r2"]
    assert list(result.per_scene_results) == [1]
    assert len(AssemblyAdapter.calls) == 1
    r2_paths = [Path(p) for p in AssemblyAdapter.calls[0]]
    assert len(r2_paths) == 3
    r2_bytes = [p.read_bytes() for p in r2_paths]
    assert r2_bytes[0] == r1_bytes[0]
    assert r2_bytes[2] == r1_bytes[2]
    assert r2_bytes[1] != r1_bytes[1]


def test_partial_rerender_without_prior_unchanged_evidence_refuses_full_assembly(
    tmp_path, monkeypatch
):
    from melosviz.conductor.orchestrator import ConductorError, Orchestrator

    _registry(monkeypatch)
    with pytest.raises(ConductorError, match="lack current render evidence"):
        Orchestrator(output_dir=tmp_path / "out", only_scenes=[1]).render(_spec())
    assert [x[0]["marker"] for x in SceneAdapter.calls] == ["one"]
    assert AssemblyAdapter.calls == []


def test_real_render_without_backend_identity_is_not_reused(tmp_path, monkeypatch):
    from melosviz.conductor.orchestrator import Orchestrator

    _registry(monkeypatch)
    orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
    orch.render(_spec())
    orch.render(_spec())

    assert len(SceneAdapter.calls) == 6, (
        "three unqualified real-render scenes must execute again rather than "
        "reusing evidence with unknown renderer/model/workflow identity"
    )


def test_backend_identity_change_invalidates_real_render_cache(tmp_path, monkeypatch):
    from melosviz.conductor.orchestrator import Orchestrator

    _registry(monkeypatch)
    base = _spec()
    for seg in base.scene_segments:
        seg["cache_extra"] = {"backend_identity": "fixture-model-workflow:v1"}
    orch = Orchestrator(output_dir=tmp_path, skip_assembly=True, only_scenes=[0])
    orch.render(base)
    orch.render(base)
    assert len(SceneAdapter.calls) == 1, "qualified identical evidence should be reusable"

    changed = _spec()
    for seg in changed.scene_segments:
        seg["cache_extra"] = {"backend_identity": "fixture-model-workflow:v2"}
    orch.render(changed)
    assert len(SceneAdapter.calls) == 2, (
        "renderer/model/workflow identity change must invalidate the old real-render cache"
    )


def test_video_export_has_explicit_stable_cache_identity():
    from melosviz.conductor.render_cache import scene_cache_backend_identity

    assert scene_cache_backend_identity({"scene_type": "video_export"}) == "video_export:ffmpeg:v1"
    assert scene_cache_backend_identity({"scene_type": "comfyui_image"}) is None
    assert scene_cache_backend_identity({
        "scene_type": "comfyui_image",
        "cache_extra": {"backend_identity": "comfyui:model-x:workflow-y:nodes-z"},
    }) == "comfyui:model-x:workflow-y:nodes-z"
