"""Tests for MultiShotDirector — 3-pass planning: outline -> scenes -> shots."""
from __future__ import annotations
import json

import pytest

from melosviz.llm.director import (
    DirectorRequest,
    MultiShotDirector,
    Shot,
    StoryOutline,
)


def _req() -> DirectorRequest:
    # DirectorRequest.segments is a list of plain dicts {start, end, scene_type, label}
    return DirectorRequest(
        concept="neon noir underwater city, dancer in silver hair, 35mm",
        bpm=124,
        palette=["#0d0d10", "#ff2bd6", "#22d3ee", "#c084fc"],
        duration_s=120,
        segments=[
            {"start": 0.0, "end": 10.0, "scene_type": "comfyui_image", "label": "intro"},
            {"start": 10.0, "end": 30.0, "scene_type": "comfyui_image", "label": "verse"},
            {"start": 30.0, "end": 60.0, "scene_type": "comfyui_video", "label": "drop"},
            {"start": 60.0, "end": 90.0, "scene_type": "comfyui_video", "label": "outro"},
        ],
    )
    d = so.to_dict()
    assert d["title"] == "Neon Tide"
    assert d["acts"][0]["name"] == "intro"
    assert d["emotional_arc"] == ["wonder", "joy"]
    json.dumps(d)


def test_plan_outline_has_4_acts_and_arc():
    d = MultiShotDirector(seed=42).plan_outline(_req())
    assert d.title
    assert len(d.acts) == 4
    act_names = [a["name"] for a in d.acts]
    assert act_names == ["intro", "build", "peak", "outro"]
    assert sum(a["end"] - a["start"] for a in d.acts) == pytest.approx(120, abs=0.1)
    assert len(d.emotional_arc) >= 4
    # climax lands somewhere in the peak act
    peak_idx = next(i for i, a in enumerate(d.acts) if a["name"] == "peak")
    peak_scene = max(0, min(len(d.emotional_arc) - 1, int(len(d.emotional_arc) * (peak_idx + 1) / len(d.acts))))
    assert d.emotional_arc[peak_scene] == "ecstasy"
    assert len(d.palette_arc) == len(d.emotional_arc)
    assert all(len(pa) == 2 for pa in d.palette_arc)


def test_plan_three_pass_returns_outline_storyboard_shots():
    msd = MultiShotDirector(seed=7, shots_per_scene=3)
    result = msd.plan_three_pass(_req())
    assert "outline" in result
    assert "storyboard" in result
    assert "shots" in result
    outline = result["outline"]
    assert len(outline["acts"]) == 4
    sb = result["storyboard"]
    assert sb.scenes
    shots = result["shots"]
    # 4 scenes * 3 shots = 12
    assert len(shots) == len(sb.scenes) * 3
    for s in shots:
        assert isinstance(s, dict)
        assert s["scene_index"] >= 0
        assert s["shot_index"] >= 0
        assert s["kind"] in {"wide", "medium", "closeup", "insert", "cutaway"}
        assert s["camera_motion"]
        assert s["duration_s"] > 0
        assert s["prompt"]


def test_plan_three_pass_shots_respect_shots_per_scene_setting():
    for n in (2, 3, 5):
        msd = MultiShotDirector(seed=1, shots_per_scene=n)
        result = msd.plan_three_pass(_req())
        shots = result["shots"]
        # clamp is 2..5 in the constructor
        assert n == min(5, max(2, n))
        assert len(shots) == len(result["storyboard"].scenes) * n


def test_plan_three_pass_is_seed_deterministic():
    r1 = MultiShotDirector(seed=123).plan_three_pass(_req())
    r2 = MultiShotDirector(seed=123).plan_three_pass(_req())
    assert r1["outline"] == r2["outline"]
    # shots are dicts; compare camera_motion + kind per (scene,shot)
    for s1, s2 in zip(r1["shots"], r2["shots"]):
        assert s1["camera_motion"] == s2["camera_motion"]
        assert s1["kind"] == s2["kind"]


def test_plan_shots_first_shot_inherits_scene_camera():
    msd = MultiShotDirector(seed=11, shots_per_scene=3)
    sb = msd._base.storyboard(_req())
    shots = msd.plan_shots(sb)
    # first shot of each scene should use the scene's original camera
    for i, scene in enumerate(sb.scenes):
        assert shots[i * 3].camera_motion == scene.camera


def test_plan_shots_alternate_kinds_include_wide_and_medium():
    msd = MultiShotDirector(seed=42, shots_per_scene=4)
    sb = msd._base.storyboard(_req())
    shots = msd.plan_shots(sb)
    # first two shots per scene must always be wide then medium
    for i in range(len(sb.scenes)):
        first_two = [shots[i * 4 + j].kind for j in range(2)]
        assert first_two == ["wide", "medium"]


def test_plan_scenes_attaches_emotional_arc_to_scene_notes():
    msd = MultiShotDirector(seed=55)
    req = _req()
    outline = msd.plan_outline(req)
    sb = msd.plan_scenes(req, outline)
    # at least one scene carries a mood=<word> note
    notes_blob = " ".join(s.notes or "" for s in sb.scenes)
    assert "mood=" in notes_blob
