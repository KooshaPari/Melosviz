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
import wave
from pathlib import Path
from typing import Any

import pytest

from melosviz.conductor import registry as registry_mod
from melosviz.conductor.events import (
    ALL_OUTCOMES,
    OUTCOME_MALFORMED,
    OUTCOME_RENDER,
)
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
    assert payload["extra"]["outcome"] == OUTCOME_MALFORMED, (
        f"unusable artifact labelled {payload['extra']['outcome']!r}"
    )
    reason = str(payload["extra"].get("rejection_reason", ""))
    assert reason_fragment in reason, f"unhelpful rejection reason: {reason!r}"


def test_real_clip_is_still_labelled_render(tmp_path: Path, monkeypatch) -> None:
    payload = _outcome(tmp_path, _RealClipAdapter, monkeypatch)
    assert payload["extra"]["outcome"] == OUTCOME_RENDER, (
        f"a real clip was labelled {payload['extra']['outcome']!r}"
    )
    assert "rejection_reason" not in payload["extra"]


def _write_zero_duration_wav(path: Path) -> None:
    """Write a WAV whose data chunk contains zero frames."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        # No call to w.writeframes — zero playable frames = zero duration.


class _ZeroDurationWavAdapter:
    def render(self, render_spec: Any, **kwargs: Any) -> list[Path]:
        out = Path(str(kwargs["output_path"]))
        out.mkdir(parents=True, exist_ok=True)
        clip = out / "silent.wav"
        _write_zero_duration_wav(clip)
        return [clip]


def test_zero_duration_wav_is_rejected_as_malformed(tmp_path: Path, monkeypatch) -> None:
    """A1: zero-duration media must be rejected, not labelled ``render``."""
    payload = _outcome(tmp_path, _ZeroDurationWavAdapter, monkeypatch)
    assert payload["extra"]["outcome"] == OUTCOME_MALFORMED, (
        f"zero-duration WAV labelled {payload['extra']['outcome']!r}"
    )
    reason = str(payload["extra"].get("rejection_reason", ""))
    assert "zero-duration" in reason, f"unhelpful rejection reason: {reason!r}"


def test_outcome_constants_are_machine_readable() -> None:
    """A1: outcomes must be addressable by name, not just by string equality."""
    from melosviz.conductor.events import (
        OUTCOME_CACHE_HIT,
        OUTCOME_FAILED,
        OUTCOME_JOB_SPEC_ONLY,
        OUTCOME_MALFORMED,
        OUTCOME_OFFLINE_PLACEHOLDER,
        OUTCOME_RENDER,
        OUTCOME_UNAVAILABLE,
    )

    assert OUTCOME_RENDER == "render"
    assert OUTCOME_OFFLINE_PLACEHOLDER == "offline-placeholder"
    assert OUTCOME_JOB_SPEC_ONLY == "job-spec-only"
    assert OUTCOME_UNAVAILABLE == "unavailable"
    assert OUTCOME_MALFORMED == "malformed"
    assert OUTCOME_FAILED == "failed"
    assert OUTCOME_CACHE_HIT == "cache-hit"
    assert set(ALL_OUTCOMES) == {
        OUTCOME_RENDER,
        OUTCOME_OFFLINE_PLACEHOLDER,
        OUTCOME_JOB_SPEC_ONLY,
        OUTCOME_UNAVAILABLE,
        OUTCOME_MALFORMED,
        OUTCOME_FAILED,
        OUTCOME_CACHE_HIT,
    }
