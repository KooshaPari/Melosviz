"""Regression: a `live_stage` scene is `job-spec-only`, not `unavailable`.

Observed on the real path: once the TD adapter accepted a dict spec (06a013e) the
scene rendered, but its provenance sidecar recorded `outcome="unavailable"` even
though the adapter had written a network spec and a bootstrap script. The other
plan-only adapters (Cinema 4D, Unreal, Blender) are labelled `job-spec-only`; the
TD adapter is plan-only unconditionally, not just in offline mode.
"""

from __future__ import annotations

import json
from pathlib import Path

from melosviz.conductor.orchestrator import Orchestrator


def _live_stage_spec() -> dict:
    return {
        "durationSecs": 1.0,
        "bpm": 120,
        "scene_segments": [
            {
                "scene_index": 0,
                "scene_name": "s0",
                "scene_type": "live_stage",
                "prompt": "p",
                "start": 0.0,
                "end": 0.5,
            }
        ],
    }


def test_live_stage_scene_is_labelled_job_spec_only(tmp_path: Path) -> None:
    out = tmp_path / "out"
    Orchestrator(output_dir=out, skip_assembly=True, auto_offline=False).render(_live_stage_spec())

    sidecars = sorted(out.rglob("*.provenance.json"))
    assert len(sidecars) == 1, f"expected one sidecar, found {len(sidecars)}"
    payload = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert payload["extra"]["outcome"] == "job-spec-only", (
        f"live_stage labelled {payload['extra'].get('outcome')!r}"
    )
    # The plan the label refers to must actually exist.
    assert (out / "live_stage" / "network_spec.json").is_file()


def test_offline_adapters_are_unaffected(tmp_path: Path, monkeypatch) -> None:
    """A live renderer must still be labelled `render` when it produces media."""
    from melosviz.conductor import registry as registry_mod

    class _MediaAdapter:
        def render(self, render_spec, **kwargs):
            scene_out = Path(str(kwargs["output_path"]))
            scene_out.mkdir(parents=True, exist_ok=True)
            clip = scene_out / "clip.mp4"
            clip.write_bytes(b"\x00" * 32)
            return [clip]

    monkeypatch.setitem(registry_mod.ADAPTER_REGISTRY, "video_export", _MediaAdapter)
    out = tmp_path / "out2"
    spec = _live_stage_spec()
    spec["scene_segments"][0]["scene_type"] = "video_export"
    Orchestrator(output_dir=out, skip_assembly=True, auto_offline=False).render(spec)

    sidecar = next(out.rglob("*.provenance.json"))
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["extra"]["outcome"] == "render"
