"""Regression: a failed scene must leave a dated, contained provenance record.

A1 acceptance requires a failed render to be explicitly blocked or recorded. The
orchestrator aborted the scene, emitted an error event and raised, but wrote no
provenance sidecar at all, so a scene that failed was indistinguishable from one
that never ran. Measured on the real registry: `motion_graphics_beat_sync`,
`davinci_master` and `live_stage` all raised and left nothing behind.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from melosviz.conductor import registry as registry_mod
from melosviz.conductor.orchestrator import ConductorError, Orchestrator


class _ExplodingAdapter:
    """Adapter whose render always fails."""

    def render(self, render_spec: Any, **kwargs: Any) -> Any:
        raise RuntimeError("adapter exploded on purpose")


def _spec() -> dict[str, Any]:
    return {
        "scene_segments": [{"scene_index": 0, "scene_name": "s0", "scene_type": "video_export"}]
    }


def test_failed_scene_writes_a_traceable_sidecar(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry_mod.ADAPTER_REGISTRY, "video_export", _ExplodingAdapter)
    out = tmp_path / "out"
    orch = Orchestrator(output_dir=out, skip_assembly=True, auto_offline=False)

    with pytest.raises(ConductorError):
        orch.render(_spec())

    sidecars = sorted(out.rglob("*.provenance.json"))
    assert len(sidecars) == 1, (
        f"a failed scene left {len(sidecars)} provenance sidecars; expected 1"
    )
    sidecar = sidecars[0]
    assert sidecar.resolve().is_relative_to(out.resolve()), (
        f"failure sidecar escaped the output dir: {sidecar}"
    )

    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["extra"]["outcome"] == "failed", (
        f"failed scene labelled {payload['extra'].get('outcome')!r}"
    )
    assert "adapter exploded on purpose" in json.dumps(payload["extra"]), (
        f"the failure reason was not recorded: {payload['extra']!r}"
    )
    assert payload["scene_index"] == 0
    assert payload["scene_type"] == "video_export"


def test_failure_sidecar_stays_out_of_cwd(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry_mod.ADAPTER_REGISTRY, "video_export", _ExplodingAdapter)
    out = tmp_path / "out"
    orch = Orchestrator(output_dir=out, skip_assembly=True, auto_offline=False)
    with pytest.raises(ConductorError):
        orch.render(_spec())
    assert not list(Path.cwd().glob("*.provenance.json")), (
        "the failure sidecar was written into the process CWD"
    )
