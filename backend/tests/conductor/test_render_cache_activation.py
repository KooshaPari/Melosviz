"""Tests for the activated render cache.

The cache was inert: `RenderCache.store` wrote into a directory the orchestrator
never created, so every store died ENOENT inside a best-effort guard and the
fast-path could never hit. These tests pin the activated behaviour: the directory
exists, a second identical scene is served from cache, a hit restores the artifact
at the path a cold render would have used, the reuse is recorded, and neither
poisoned metadata field can make a path escape the render output directory.
"""

from __future__ import annotations

import json
from pathlib import Path

from melosviz.conductor.orchestrator import Orchestrator

OFFLINE_ENV = "MELOSVIZ_COMFYUI_OFFLINE"


def _spec() -> dict:
    return {
        "durationSecs": 2.0,
        "bpm": 120,
        "scene_segments": [
            {
                "scene_index": 0,
                "scene_name": "s0",
                "scene_type": "comfyui_image",
                "prompt": "cache activation",
                "start": 0.0,
                "end": 1.0,
            }
        ],
    }


def _orch(tmp_path: Path) -> Orchestrator:
    return Orchestrator(output_dir=tmp_path / "out", skip_assembly=True, auto_offline=False)


def _done(result) -> list:
    return [e for e in result.events if getattr(e, "state", "") == "done"]


def _meta_path(out: Path) -> Path:
    return next((out / "_render_cache").glob("*.json"))


def test_cache_dir_is_created_and_store_succeeds(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(OFFLINE_ENV, "1")
    orch = _orch(tmp_path)
    orch.render(_spec())

    cache_dir = tmp_path / "out" / "_render_cache"
    assert cache_dir.is_dir(), "the orchestrator never created the cache directory"
    blobs = sorted(cache_dir.glob("*.bin"))
    assert len(blobs) == 1, f"expected one cached artifact, found {len(blobs)}"


def test_second_render_is_served_from_cache_and_recorded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(OFFLINE_ENV, "1")
    orch = _orch(tmp_path)
    orch.render(_spec())
    out = tmp_path / "out"
    cold_path = out / "comfyui_image" / "scene_000" / "clip.mp4"
    assert cold_path.is_file(), "the cold render did not write the artifact"

    result = orch.render(_spec())
    done = _done(result)[0]
    assert done.extras.get("from_cache") is True, f"not served from cache: {done.extras!r}"

    materialised = Path(done.artifact_path)
    assert materialised.suffix == ".mp4", (
        f"a cache hit handed downstream a {materialised.suffix!r} artifact: {materialised}"
    )
    # A hit must restore the artifact where a cold render would have put it.
    assert materialised.resolve() == cold_path.resolve(), (
        f"the hit landed at {materialised} instead of {cold_path}"
    )

    sidecars = sorted(out.rglob("*.provenance.json"))
    assert len(sidecars) == 1, f"one artifact, one sidecar, but found {len(sidecars)}"
    payload = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert payload["extra"]["from_cache"] is True, (
        f"the sidecar does not record the reuse: {payload['extra']!r}"
    )
    assert payload["extra"]["outcome"] == "offline-placeholder", (
        f"the cached scene lost its mode: {payload['extra']!r}"
    )
    assert Path(payload["artifact_path"]).resolve() == cold_path.resolve()


def test_poisoned_cache_metadata_cannot_escape_the_output_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(OFFLINE_ENV, "1")
    orch = _orch(tmp_path)
    orch.render(_spec())
    out = tmp_path / "out"
    meta_path = _meta_path(out)

    # (a) a poisoned relative path must be rejected outright
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    payload["artifact_relpath"] = "../../../escaped.mp4"
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    done = _done(orch.render(_spec()))[0]
    assert done.extras.get("from_cache") is True
    materialised = Path(done.artifact_path)
    assert materialised.resolve().is_relative_to(out.resolve()), (
        f"a stored relative path escaped the output dir: {materialised}"
    )
    assert not (tmp_path / "escaped.mp4").exists()

    # (b) a poisoned plain name cannot climb out either
    payload["artifact_relpath"] = None
    payload["artifact_name"] = "../../escaped2.mp4"
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    done = _done(orch.render(_spec()))[0]
    materialised = Path(done.artifact_path)
    assert materialised.name == "escaped2.mp4", f"unexpected name: {materialised.name}"
    assert materialised.resolve().is_relative_to(out.resolve()), (
        f"the stored name escaped the output dir: {materialised}"
    )
    assert not (tmp_path / "escaped2.mp4").exists()


def test_missing_blob_falls_back_to_a_real_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(OFFLINE_ENV, "1")
    orch = _orch(tmp_path)
    orch.render(_spec())
    out = tmp_path / "out"
    for blob in (out / "_render_cache").glob("*.bin"):
        blob.unlink()

    done = _done(orch.render(_spec()))[0]
    assert done.extras.get("from_cache") is not True, "a deleted entry was still reported as a hit"
    assert Path(done.artifact_path).is_file()
