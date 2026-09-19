"""Regression: an assembly-step failure must reach the event stream.

The per-scene failure branches emit an error event *before* raising, with an
explicit comment saying why ("so the SSE stream gets the failure before the
orchestrator aborts"). The final assembly step did not: it raised and the live
event stream saw nothing. `scene_index=-1` marks a pipeline-level step, which has
no scene of its own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from melosviz.conductor import registry as registry_mod
from melosviz.conductor.events import get_bus, reset_bus
from melosviz.conductor.orchestrator import ConductorError, Orchestrator


class _ExplodingEncoder:
    def render(self, render_spec, **kwargs):
        raise RuntimeError("encoder exploded on purpose")


def _spec() -> dict:
    # No scene_segments: the per-scene loop only materialises directories, so the
    # assembly step is the only thing that renders.
    return {"durationSecs": 1.0, "bpm": 120, "scene_segments": []}


def test_assembly_failure_emits_an_error_event(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(
        registry_mod.ADAPTER_REGISTRY, "assembly_encode", _ExplodingEncoder
    )
    reset_bus()
    seen: list = []
    get_bus().subscribe(lambda e: seen.append(e))

    orch = Orchestrator(output_dir=tmp_path / "out", skip_assembly=False, auto_offline=False)
    with pytest.raises(ConductorError, match="final assembly_encode step failed"):
        orch.render(_spec())

    errors = [e for e in seen if getattr(e, "state", "") == "error"]
    assert errors, (
        "the assembly failure never reached the event stream; "
        f"states seen: {[getattr(e, 'state', None) for e in seen]!r}"
    )
    assert errors[0].scene_type == "assembly_encode"
    assert "encoder exploded on purpose" in errors[0].error


def test_missing_assembly_adapter_emits_an_error_event(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setitem(registry_mod.ADAPTER_REGISTRY, "assembly_encode", None)
    reset_bus()
    seen: list = []
    get_bus().subscribe(lambda e: seen.append(e))

    orch = Orchestrator(output_dir=tmp_path / "out", skip_assembly=False, auto_offline=False)
    with pytest.raises(ConductorError, match="assembly_encode"):
        orch.render(_spec())

    errors = [e for e in seen if getattr(e, "state", "") == "error"]
    assert errors, "a missing assembly adapter produced no error event"
    assert errors[0].scene_type == "assembly_encode"
