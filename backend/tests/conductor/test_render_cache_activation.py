"""Tests for the activated render cache.

The cache was previously inert: `RenderCache.store` wrote into a directory the
orchestrator never created, so every store died ENOENT inside a best-effort
guard and the fast-path could never hit. These tests pin the activated behaviour:
the directory exists, a second identical scene is served from cache, the cached
bytes are materialised under the artifact's real name, the reuse is recorded, and
a poisoned metadata name cannot escape the scene directory.
"""

from __future__ import annotations

import json
import os
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

    result = orch.render(_spec())
    done = _done(result)[0]
    assert done.extras.get("from_cache") is True, f"not served from cache: {done.extras!r}"

    materialised = Path(done.artifact_path)
    assert materialised.suffix == ".mp4", (
        f"a cache hit handed downstream a {materialised.suffix!r} artifact: {materialised}"
    )
    assert materialised.is_file()
    assert materialised.resolve().is_relative_to(out.resolve())

    sidecars = sorted(out.rglob("*.provenance.json"))
    assert len(sidecars) == 2, (
        f"two renders produced {len(sidecars)} provenance records; a cached render "
        "must be recorded too"
    )
    hit_payload = json.loads(materialised.with_name(materialised.name + ".provenance.json").read_text(encoding="utf-8"))
    assert hit_payload["extra"]["from_cache"] is True
    assert hit_payload["extra"]["outcome"] == "offline-placeholder", (
        f"the cached scene lost its mode: {hit_payload['extra']!r}"
    )


def test_poisoned_cache_metadata_cannot_escape_the_scene_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(OFFLINE_ENV, "1")
    orch = _orch(tmp_path)
    orch.render(_spec())
    out = tmp_path / "out"

    meta_path = next((out / "_render_cache").glob("*.json"))
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    payload["artifact_name"] = "../../escaped.mp4"
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    done = _done(orch.render(_spec()))[0]
    assert done.extras.get("from_cache") is True
    materialised = Path(done.artifact_path)
    assert materialised.name == "escaped.mp4", f"unexpected name: {materialised.name}"
    assert materialised.resolve().is_relative_to(out.resolve()), (
        f"a stored name escaped the scene dir: {materialised}"
    )
    assert not (tmp_path / "escaped.mp4").exists()
    assert not (out / "escaped.mp4").exists()


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
