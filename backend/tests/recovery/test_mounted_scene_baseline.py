"""M-E01 baseline diagnostics.

These tests deliberately assert the *observed broken baseline* so CI can preserve an
immutable reproduction before a repair branch exists. They are NOT product
acceptance tests. M-E02 must replace/retire them with positive contract tests once
its result schema is reviewed.
"""
from __future__ import annotations

import json
import struct
import wave
from pathlib import Path

from fastapi.testclient import TestClient


def _wav(path: Path) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        for i in range(800):
            w.writeframesraw(struct.pack("<h", (i % 50) * 100))


def test_baseline_orchestrator_calls_whole_spec_once_per_same_type_scene(tmp_path, monkeypatch):
    """Observed defect M-F13: iteration is owned by both orchestrator and adapter."""
    from melosviz.conductor import registry as registry_mod
    from melosviz.conductor.orchestrator import Orchestrator

    class WholeSpecWitness:
        scene_type = "baseline_same_type"
        observed_scene_counts: list[int] = []
        observed_output_dirs: list[str] = []

        def render(self, render_spec, **kwargs):
            data = render_spec.model_dump() if hasattr(render_spec, "model_dump") else render_spec
            scenes = data.get("scene_segments") or data.get("scenes") or []
            type(self).observed_scene_counts.append(len(scenes))
            type(self).observed_output_dirs.append(str(kwargs["output_path"]))
            return []

    monkeypatch.setitem(registry_mod.ADAPTER_REGISTRY, "baseline_same_type", WholeSpecWitness)
    spec = {
        "version": 2,
        "scene_segments": [
            {"scene_index": 0, "name": "S1", "scene_type": "baseline_same_type"},
            {"scene_index": 1, "name": "S2", "scene_type": "baseline_same_type"},
        ],
    }

    Orchestrator(output_dir=tmp_path / "out", skip_assembly=True, auto_offline=False).render(spec)

    # Diagnostic assertion: two scene envelopes each passed the entire 2-scene
    # RenderSpec to the adapter. A correct scene-targeted design must make this
    # baseline assertion fail and replace it with the accepted positive contract.
    assert WholeSpecWitness.observed_scene_counts == [2, 2]
    # Both calls also share the same scene-type output directory.
    assert len(set(WholeSpecWitness.observed_output_dirs)) == 1


def test_baseline_bridge_generate_misses_real_nested_scene_layout(tmp_path, monkeypatch):
    """Observed defect M-F14: route scans out/scene_* while adapters emit type/scene_*."""
    from melosviz.bridge import server

    wav = tmp_path / "track.wav"
    _wav(wav)
    storyboard = tmp_path / "storyboard.json"
    storyboard.write_text(json.dumps({
        "scenes": [
            {"name": "S1", "scene_type": "comfyui_image"},
            {"name": "S2", "scene_type": "comfyui_image"},
        ]
    }))
    out = tmp_path / "generate"

    def fake_real_layout(_args):
        # Reproduce the orchestrator/adapter directory shape, not the route test's
        # historical pre-seeded flat out/scene_0 fixture.
        scene = out / "comfyui_image" / "scene_000"
        scene.mkdir(parents=True, exist_ok=True)
        (scene / "workflow.json").write_text("{}")
        return {"returncode": 0}

    monkeypatch.setattr(server, "_run_studio_subprocess", fake_real_layout)
    client = TestClient(server.app)
    response = client.post("/api/studio/generate", json={
        "wav_path": str(wav),
        "storyboard_path": str(storyboard),
        "out_dir": str(out),
        "offline": True,
    })

    assert response.status_code == 200
    payload = response.json()
    assert (out / "comfyui_image" / "scene_000" / "workflow.json").exists()
    # Diagnostic assertion: real nested output exists but bridge returns none.
    assert payload["scenes"] == []


def test_baseline_bridge_regression_test_can_pass_without_generate_output(tmp_path, monkeypatch):
    """Proves the historical bridge test shape can validate a pre-created fixture."""
    from melosviz.bridge import server

    wav = tmp_path / "track.wav"
    _wav(wav)
    storyboard = tmp_path / "storyboard.json"
    storyboard.write_text('{"scenes":[]}')
    out = tmp_path / "generate"
    flat = out / "scene_0"
    flat.mkdir(parents=True)
    (flat / "workflow.json").write_text("{}")

    monkeypatch.setattr(server, "_run_studio_subprocess", lambda _args: {"returncode": 0})
    response = TestClient(server.app).post("/api/studio/generate", json={
        "wav_path": str(wav),
        "storyboard_path": str(storyboard),
        "out_dir": str(out),
        "offline": True,
    })
    assert response.status_code == 200
    assert response.json()["scenes"][0]["name"] == "scene_0"
