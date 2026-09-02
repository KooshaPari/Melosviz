"""Tests for the VJ export module (SVG cues + Lottie markers)."""
from __future__ import annotations

import json
from pathlib import Path

from melosviz.export.vj import discover_shots, export_vj_cues


def test_discover_shots_prefers_multi_shot_plan(tmp_path: Path) -> None:
    (tmp_path / "plan.json").write_text(json.dumps({
        "shots": [{
            "scene_index": 2,
            "shot_index": 1,
            "duration_s": 4.0,
            "prompt": "hero <wide>",
            "camera_motion": "orbit",
        }]
    }))
    (tmp_path / "storyboard.json").write_text(json.dumps({
        "scenes": [{"index": 9, "duration": 8.0, "prompt": "fallback"}]
    }))
    shots = discover_shots(tmp_path, [])
    assert [(shot["scene_index"], shot["shot_index"]) for shot in shots] == [(2, 1)]


def test_export_vj_cues_writes_deterministic_svg_and_lottie(tmp_path: Path) -> None:
    shots = [{
        "scene_index": 1,
        "shot_index": 2,
        "start": 10.0,
        "duration_s": 4.0,
        "label": "chorus & drop",
        "prompt": "hero <wide>",
        "camera_motion": "orbit",
        "palette": ["#ff00aa", "#00ffee"],
        "beats": [10.0, 12.0, 14.0],
        "width": 1920,
        "height": 1080,
        "fps": 24,
    }]
    first = export_vj_cues(shots, tmp_path / "vj")
    svg_path = tmp_path / "vj" / "shot-0001-02.svg"
    lottie_path = tmp_path / "vj" / "shot-0001-02.lottie.json"
    first_svg = svg_path.read_bytes()
    first_lottie = lottie_path.read_bytes()
    second = export_vj_cues(shots, tmp_path / "vj")
    assert first == second
    assert svg_path.read_bytes() == first_svg
    assert lottie_path.read_bytes() == first_lottie
    assert "chorus &amp; drop" in first_svg.decode()
    lottie = json.loads(first_lottie)
    assert lottie["v"] == "5.12.0"
    assert lottie["op"] == 96
    assert {layer["ty"] for layer in lottie["layers"]} == {4, 5}
    assert any(
        layer.get("t", {}).get("d", {}).get("k", [{}])[0].get("s", {}).get("t")
        == "chorus & drop"
        for layer in lottie["layers"]
        if layer["ty"] == 5
    )
    assert any(
        layer.get("t", {}).get("d", {}).get("k", [{}])[0].get("s", {}).get("t")
        == "hero <wide>"
        for layer in lottie["layers"]
        if layer["ty"] == 5
    )
    assert [marker["cm"] for marker in lottie["markers"]] == [
        "shot-start", "beat-000", "beat-001", "beat-002", "shot-end"
    ]


def test_discover_shots_reads_provenance_timing(tmp_path: Path) -> None:
    sidecar = tmp_path / "clip.mp4.provenance.json"
    sidecar.write_text(json.dumps({
        "artifact_path": str(tmp_path / "clip.mp4"),
        "scene_index": 3,
        "scene_name": "bridge",
        "prompt": "type morph",
        "extra": {
            "start_seconds": 12.0,
            "end_seconds": 16.0,
            "beat_seconds": [12.0, 14.0, 16.0],
        },
    }))
    shots = discover_shots(tmp_path, [])
    assert len(shots) == 1
    assert shots[0]["scene_index"] == 3
    assert shots[0]["start"] == 12.0
    assert shots[0]["duration_s"] == 4.0
    assert shots[0]["beats"] == [12.0, 14.0, 16.0]


def test_discover_shots_orders_media_by_relative_path(tmp_path: Path) -> None:
    first = tmp_path / "a" / "z.mp4"
    second = tmp_path / "b" / "a.mp4"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    shots = discover_shots(tmp_path, [second, first])
    assert [shot["label"] for shot in shots] == ["z", "a"]
    assert [shot["scene_index"] for shot in shots] == [0, 1]
