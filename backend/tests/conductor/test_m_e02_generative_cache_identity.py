from __future__ import annotations

import struct
import wave
from pathlib import Path

from melosviz.conductor import registry as registry_mod
from melosviz.conductor.orchestrator import Orchestrator


class GenerativeFixtureAdapter:
    scene_type = "comfyui_image"
    calls = 0

    def render(self, render_spec, **kwargs):
        type(self).calls += 1
        out = Path(kwargs["output_path"])
        out.mkdir(parents=True, exist_ok=True)
        target = out / "clip.wav"
        with wave.open(str(target), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            for i in range(800):
                w.writeframesraw(struct.pack("<h", ((i % 40) - 20) * 200))
        return [target]


def _spec(*, cache_extra=None):
    scene = {
        "scene_index": 0,
        "scene_name": "g0",
        "scene_type": "comfyui_image",
        "prompt": "same semantic scene",
        "seed": 7,
        "start": 0.0,
        "end": 0.1,
    }
    if cache_extra is not None:
        scene["cache_extra"] = cache_extra
    return {"scene_segments": [scene]}


def test_generative_cache_without_backend_identity_is_not_reusable(tmp_path, monkeypatch):
    """Held-out recovery rule: scene inputs alone cannot qualify generative reuse."""
    monkeypatch.setitem(registry_mod.ADAPTER_REGISTRY, "comfyui_image", GenerativeFixtureAdapter)
    GenerativeFixtureAdapter.calls = 0
    out = tmp_path / "out"

    Orchestrator(output_dir=out, skip_assembly=True).render(_spec())
    Orchestrator(output_dir=out, skip_assembly=True).render(_spec())

    # Until backend/model/workflow/tool identity is explicit, the second run
    # must execute again rather than promote a scene-input-only cache hit.
    assert GenerativeFixtureAdapter.calls == 2


def test_explicit_backend_identity_can_reuse_and_change_invalidates(tmp_path, monkeypatch):
    """The existing cache_extra seam can express a reviewer-visible backend identity."""
    monkeypatch.setitem(registry_mod.ADAPTER_REGISTRY, "comfyui_image", GenerativeFixtureAdapter)
    GenerativeFixtureAdapter.calls = 0
    out = tmp_path / "out"

    a = _spec(cache_extra={"renderer_identity": "fixture-model-A/workflow-1"})
    Orchestrator(output_dir=out, skip_assembly=True).render(a)
    Orchestrator(output_dir=out, skip_assembly=True).render(a)
    assert GenerativeFixtureAdapter.calls == 1

    b = _spec(cache_extra={"renderer_identity": "fixture-model-B/workflow-1"})
    Orchestrator(output_dir=out, skip_assembly=True).render(b)
    assert GenerativeFixtureAdapter.calls == 2
