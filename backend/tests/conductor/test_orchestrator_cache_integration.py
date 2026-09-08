"""Exercise real cache storage through the orchestrator's adapter boundary."""

from pathlib import Path
from types import SimpleNamespace

from melosviz.analysis.models import RenderSpec
from melosviz.conductor.orchestrator import Orchestrator


def test_scene_cache_reuses_artifacts_and_invalidates_only_changed_scene(
    tmp_path, monkeypatch
):
    from melosviz.conductor import registry

    rendered = []

    class FileAdapter:
        def render(self, render_spec, *, output_path, **kwargs):
            artifact = Path(output_path) / f"render-{len(rendered)}.mp4"
            artifact.write_bytes(b"rendered test fixture")
            rendered.append(artifact)
            return SimpleNamespace(files=[artifact])

    monkeypatch.setitem(registry.ADAPTER_REGISTRY, "cache_fixture", FileAdapter)
    spec = RenderSpec(
        scene_segments=[
            {
                "scene_type": "cache_fixture",
                "name": "first",
                "prompt": "ocean",
                "seed": 1,
            },
            {
                "scene_type": "cache_fixture",
                "name": "second",
                "prompt": "forest",
                "seed": 2,
            },
        ]
    )
    orchestrator = Orchestrator(
        output_dir=tmp_path, skip_assembly=True, auto_offline=False
    )
    first = orchestrator.render(spec)
    assert len(rendered) == 2
    assert len([event for event in first.events if event.state == "done"]) == 2
    second = orchestrator.render(spec)
    assert len(rendered) == 2, "unchanged scenes must reuse their stored artifacts"
    cached = [event for event in second.events if event.state == "done"]
    assert len(cached) == 2
    assert all(
        Path(event.artifact_path).read_bytes() == b"rendered test fixture"
        for event in cached
    )
    assert len({event.artifact_path for event in cached}) == 2
    spec.scene_segments[1]["prompt"] = "desert"
    orchestrator.render(spec)
    assert len(rendered) == 3, "changing the second scene must not invalidate the first"
