"""Regression: an unusable artifact must not be accepted as a render.

A1 acceptance: "malformed or zero-duration media are rejected or explicitly
blocked so release acceptance cannot silently consume fixture output". Measured
before this fix, all three of these were labelled ``render``:

* a zero-byte ``clip.mp4``
* a path the adapter never wrote
* a directory

Each is recorded here as ``malformed`` with a reason, while the render still
completes so rehearsal stays runnable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from melosviz.conductor import registry as registry_mod
from melosviz.conductor.orchestrator import Orchestrator


class _ZeroByteAdapter:
    def render(self, render_spec: Any, **kwargs: Any) -> list[Path]:
        out = Path(str(kwargs["output_path"]))
        out.mkdir(parents=True, exist_ok=True)
        clip = out / "clip.mp4"
        clip.write_bytes(b"")
        return [clip]


class _MissingPathAdapter:
    def render(self, render_spec: Any, **kwargs: Any) -> list[Path]:
        out = Path(str(kwargs["output_path"]))
        out.mkdir(parents=True, exist_ok=True)
        return [out / "never-written.mp4"]


class _DirectoryAdapter:
    def render(self, render_spec: Any, **kwargs: Any) -> list[Path]:
        out = Path(str(kwargs["output_path"]))
        out.mkdir(parents=True, exist_ok=True)
        return [out]


class _RealClipAdapter:
    def render(self, render_spec: Any, **kwargs: Any) -> list[Path]:
        out = Path(str(kwargs["output_path"]))
        out.mkdir(parents=True, exist_ok=True)
        clip = out / "clip.mp4"
        clip.write_bytes(b"\x00" * 64)
        return [clip]


def _outcome(tmp_path: Path, adapter: Any, monkeypatch) -> dict:
    monkeypatch.setitem(registry_mod.ADAPTER_REGISTRY, "video_export", adapter)
    out = tmp_path / "out"
    orch = Orchestrator(output_dir=out, skip_assembly=True, auto_offline=False)
    spec = {
        "scene_segments": [{"scene_index": 0, "scene_name": "s0", "scene_type": "video_export"}]
    }
    orch.render(spec)
    sidecars = sorted(out.rglob("*.provenance.json"))
    assert len(sidecars) == 1, f"expected one sidecar, got {sidecars}"
    assert sidecars[0].resolve().is_relative_to(out.resolve())
    return json.loads(sidecars[0].read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("adapter", "reason_fragment"),
    [
        (_ZeroByteAdapter, "empty"),
        (_MissingPathAdapter, "missing"),
        (_DirectoryAdapter, "not a file"),
    ],
)
def test_unusable_artifact_is_not_labelled_render(
    tmp_path: Path, monkeypatch, adapter: Any, reason_fragment: str
) -> None:
    payload = _outcome(tmp_path, adapter, monkeypatch)
    assert payload["extra"]["outcome"] == "malformed", (
        f"unusable artifact labelled {payload['extra']['outcome']!r}"
    )
    reason = str(payload["extra"].get("rejection_reason", ""))
    assert reason_fragment in reason, f"unhelpful rejection reason: {reason!r}"


def test_real_clip_is_still_labelled_render(tmp_path: Path, monkeypatch) -> None:
    payload = _outcome(tmp_path, _RealClipAdapter, monkeypatch)
    assert payload["extra"]["outcome"] == "render", (
        f"a real clip was labelled {payload['extra']['outcome']!r}"
    )
    assert "rejection_reason" not in payload["extra"]
