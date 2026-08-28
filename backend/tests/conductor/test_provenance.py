"""Tests for per-clip provenance metadata.

The provenance module writes a sidecar `<artifact>.provenance.json` next to
every rendered clip so a downstream consumer (DaVinci import, festival VJ
system, archival ingest) can replay the exact workflow + inputs + backend +
timestamps that produced the artifact.

We test:
- ClipProvenance dataclass: build -> to_dict -> JSON-serialisable
- write_provenance: writes a sidecar next to the artifact
- provenance_path_for: artifact.png -> artifact.png.provenance.json
- collect_manifest_from_dir: globs all sidecars + sorts by scene_index
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from melosviz.conductor.provenance import (
    ClipProvenance,
    PROVENANCE_SCHEMA_VERSION,
    collect_manifest_from_dir,
    provenance_path_for,
    write_provenance,
)


def _make_prov(
    scene_index: int = 0,
    scene_name: str = "intro",
    backend: str = "comfyui_image",
    artifact_path: str = "/work/scene_0000.png",
    **overrides,
) -> ClipProvenance:
    base = dict(
        artifact_path=artifact_path,
        scene_index=scene_index,
        scene_name=scene_name,
        scene_type="comfyui_image",
        backend=backend,
        render_started_at=time.time(),
        render_finished_at=time.time() + 5.0,
        storyboard_id="neon-tide",
        seed=42,
        input_hash="abc123",
        prompt="abstract bioluminescent city",
        width=1920,
        height=1080,
        fps=24,
        palette=["#0d0d10", "#ff2bd6"],
        continuity={"subject_token": "silver-haired dancer", "env_token": "underwater city"},
        lyric={"phrase_id": "p1", "text": "City lights", "mood_label": "yearning"},
        workflow_json_path="/work/scene_0000.workflow.json",
        comfyui_prompt_id="prompt-1",
        comfyui_job_id="job-1",
        extra={},
    )
    base.update(overrides)
    return ClipProvenance(**base)


# ---------------------------------------------------------------------------
# ClipProvenance dataclass
# ---------------------------------------------------------------------------

def test_clip_provenance_default_values():
    p = ClipProvenance(
        artifact_path="/x.png",
        scene_index=0,
        scene_name="intro",
        scene_type="comfyui_image",
        backend="comfyui_image",
        render_started_at=0.0,
    )
    assert p.render_finished_at is None
    assert p.duration_seconds == 0.0
    assert p.seed is None
    assert p.palette == []
    assert p.continuity == {}
    assert p.lyric is None
    assert p.extra == {}


def test_clip_provenance_duration_is_finished_minus_started():
    p = _make_prov(render_started_at=10.0, render_finished_at=15.0)
    assert p.duration_seconds == 5.0


def test_clip_provenance_to_dict_is_json_serializable():
    p = _make_prov()
    d = p.to_dict()
    json.dumps(d)
    assert d["schema_version"] == PROVENANCE_SCHEMA_VERSION
    assert d["scene_index"] == 0
    assert d["scene_name"] == "intro"
    assert d["backend"] == "comfyui_image"
    assert d["prompt"] == "abstract bioluminescent city"
    assert d["width"] == 1920
    assert d["height"] == 1080
    assert d["fps"] == 24
    assert d["palette"] == ["#0d0d10", "#ff2bd6"]
    assert d["continuity"]["subject_token"] == "silver-haired dancer"
    assert d["lyric"]["text"] == "City lights"


def test_clip_provenance_to_dict_handles_no_finished_at():
    p = _make_prov()
    p.render_finished_at = None
    d = p.to_dict()
    assert d["duration_seconds"] == 0.0
    assert d["render_finished_at"] is None


# ---------------------------------------------------------------------------
# provenance_path_for / write_provenance
# ---------------------------------------------------------------------------

def test_provenance_path_for_appends_suffix():
    p = provenance_path_for("/some/dir/scene_0000.png")
    assert str(p).endswith("scene_0000.png.provenance.json")


def test_provenance_path_for_handles_path_object(tmp_path):
    p = provenance_path_for(tmp_path / "scene.mp4")
    assert p.name == "scene.mp4.provenance.json"


def test_write_provenance_creates_sidecar(tmp_path):
    artifact = tmp_path / "scene_0000.png"
    artifact.write_bytes(b"fake-png-bytes")
    p = _make_prov(artifact_path=str(artifact))
    sidecar = write_provenance(p)
    assert sidecar.exists()
    assert sidecar.parent == tmp_path
    assert sidecar.name == "scene_0000.png.provenance.json"

    payload = json.loads(sidecar.read_text())
    assert payload["scene_index"] == 0
    assert payload["backend"] == "comfyui_image"
    assert payload["artifact_path"].endswith("scene_0000.png")


def test_write_provenance_overwrites_existing(tmp_path):
    artifact = tmp_path / "scene.mp4"
    artifact.write_bytes(b"x")
    p1 = _make_prov(scene_index=0, artifact_path=str(artifact), prompt="old")
    write_provenance(p1)
    p2 = _make_prov(scene_index=0, artifact_path=str(artifact), prompt="new")
    write_provenance(p2)
    payload = json.loads((tmp_path / "scene.mp4.provenance.json").read_text())
    assert payload["prompt"] == "new"


# ---------------------------------------------------------------------------
# collect_manifest_from_dir
# ---------------------------------------------------------------------------

def test_collect_manifest_from_dir_empty(tmp_path):
    out = collect_manifest_from_dir(tmp_path)
    assert out == []


def test_collect_manifest_from_dir_globs_all_sidecars(tmp_path):
    # Three scenes, write provenance for each.
    for i in range(3):
        artifact = tmp_path / f"scene_{i:04d}.png"
        artifact.write_bytes(b"x")
        p = _make_prov(scene_index=i, artifact_path=str(artifact))
        write_provenance(p)
    out = collect_manifest_from_dir(tmp_path)
    assert len(out) == 3
    assert [d["scene_index"] for d in out] == [0, 1, 2]


def test_collect_manifest_from_dir_recurses(tmp_path):
    nested = tmp_path / "comfyui_image"
    nested.mkdir()
    artifact = nested / "scene_0042.png"
    artifact.write_bytes(b"x")
    p = _make_prov(scene_index=42, artifact_path=str(artifact))
    write_provenance(p)
    out = collect_manifest_from_dir(tmp_path)
    assert len(out) == 1
    assert out[0]["scene_index"] == 42


def test_collect_manifest_from_dir_skips_invalid_json(tmp_path):
    artifact = tmp_path / "good.png"
    artifact.write_bytes(b"x")
    write_provenance(_make_prov(scene_index=0, artifact_path=str(artifact)))
    bad = tmp_path / "bad.png.provenance.json"
    bad.write_text("{not json", encoding="utf-8")
    out = collect_manifest_from_dir(tmp_path)
    assert len(out) == 1
    assert out[0]["scene_index"] == 0


def test_collect_manifest_from_dir_handles_string_path(tmp_path):
    artifact = tmp_path / "scene_0007.png"
    artifact.write_bytes(b"x")
    write_provenance(_make_prov(scene_index=7, artifact_path=str(artifact)))
    out = collect_manifest_from_dir(str(tmp_path))
    assert len(out) == 1
    assert out[0]["scene_index"] == 7
