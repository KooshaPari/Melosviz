"""Regression: a ``live_stage`` scene renders from a plain-dict spec.

Real-path incident: the conductor hands each adapter whatever the caller
supplied — a ``RenderSpec`` model, or the plain dict produced by
``model_dump()`` / ``viz generate``'s JSON spec. Every other registered adapter
reads dicts through ``.get`` (see ``comfyui_adapter._extract_scenes``), but
``TDAdapter`` forwarded the value straight into the TD generator, which reads
``render_spec.metadata``. A dict spec therefore produced::

    ConductorError: adapter for scene_type='live_stage' failed:
    TouchDesigner network generation failed:
    'dict' object has no attribute 'metadata'

The adapter now normalises a dict to ``RenderSpec`` at its own boundary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from melosviz.conductor.orchestrator import Orchestrator


def _live_stage_spec() -> dict[str, Any]:
    """The minimal dict spec a caller passes to ``Orchestrator.render``."""
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


def test_td_adapter_accepts_a_dict_spec(tmp_path: Path) -> None:
    """The adapter boundary must accept a plain dict, like every other adapter."""
    from melosviz.runtime.touchdesigner.adapter import TDAdapter

    result = TDAdapter().render(_live_stage_spec(), output_path=tmp_path / "td")

    assert result.network_spec_path is not None
    assert result.network_spec_path.is_file(), "the TD network spec was not written for a dict spec"
    assert result.bootstrap_path is not None
    assert result.bootstrap_path.is_file()


def test_live_stage_scene_renders_through_the_real_orchestrator(
    tmp_path: Path,
) -> None:
    """End-to-end: a dict spec with a ``live_stage`` scene must not raise."""
    out = tmp_path / "out"
    orch = Orchestrator(output_dir=out, skip_assembly=True, auto_offline=False)

    # Before the fix this raised ConductorError (``'dict' object has no
    # attribute 'metadata'``) from the real registry entry.
    orch.render(_live_stage_spec())

    # The TD runtime emits its plan files inside the scene output dir.
    assert (out / "live_stage" / "network_spec.json").is_file(), (
        "no network_spec.json was produced for the live_stage scene"
    )

    # And the scene leaves a provenance record that is not a failure.
    sidecars = sorted(out.rglob("*.provenance.json"))
    assert len(sidecars) == 1, f"expected exactly one provenance sidecar, found {len(sidecars)}"
    payload = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert payload["scene_type"] == "live_stage"
    assert payload["extra"]["outcome"] != "failed", (
        f"live_stage scene labelled {payload['extra'].get('outcome')!r}"
    )
    assert "error" not in payload["extra"], f"the dict spec still failed: {payload['extra']!r}"
