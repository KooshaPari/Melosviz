"""Regression: an unregistered scene type must still leave a failure record.

`Orchestrator.render` aborts with `ConductorError` when no adapter is registered
for a scene type, which is the "explicitly blocked" half of the A1 acceptance
criterion, but it wrote no provenance at all, so the aborted scene left no trace.
A1 also asks that a failed render is *recorded*.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from melosviz.conductor.orchestrator import ConductorError, Orchestrator


def test_missing_adapter_records_a_failure_sidecar(tmp_path: Path) -> None:
    out = tmp_path / "out"
    spec = {
        "scene_segments": [
            {
                "scene_index": 0,
                "scene_name": "s0",
                "scene_type": "definitely_not_a_registered_type",
            }
        ]
    }

    with pytest.raises(ConductorError, match="no adapter registered"):
        Orchestrator(output_dir=out, skip_assembly=True, auto_offline=False).render(spec)

    sidecars = sorted(out.rglob("*.provenance.json"))
    assert len(sidecars) == 1, (
        f"an unregistered scene type left {len(sidecars)} provenance records; expected 1"
    )
    assert sidecars[0].resolve().is_relative_to(out.resolve())
    payload = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert payload["extra"]["outcome"] == "failed", (
        f"unregistered scene labelled {payload['extra'].get('outcome')!r}"
    )
    assert "no adapter registered" in payload["extra"]["error"]
    assert payload["scene_type"] == "definitely_not_a_registered_type"
    assert payload["backend"] == "(no adapter)"
