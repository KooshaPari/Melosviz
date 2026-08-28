"""Tests for the beat-aligned assemble-effects planner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from melosviz.compose.beat_cuts import (
    AssembleEffectsPlan,
    InternalCut,
    TransitionAtBoundary,
    build_assemble_effects_plan,
    load_storyboard_for_plan,
    plan_to_ffmpeg_filter,
    summarize_plan,
    write_effects_plan,
)


def _storyboard_with_beats(
    scenes: list[dict],
    *,
    bpm: int = 124,
    downbeat_times: list[float] | None = None,
    total_seconds: float | None = None,
) -> dict:
    """Build a minimal storyboard dict for the planner."""
    if downbeat_times is None:
        # generate a 124 bpm grid that covers the scenes
        beat_period = 60.0 / bpm
        last = max((s["end"] for s in scenes), default=30.0)
        downbeat_times = [round(i * beat_period, 3) for i in range(int(last / beat_period) + 1)]
    return {
        "concept": "neon noir test",
        "bpm": bpm,
        "downbeat_times": downbeat_times,
        "scenes": scenes,
    }


def test_build_plan_returns_assemble_effects_plan_type():
    sb = _storyboard_with_beats([
        {"name": "intro", "start": 0.0, "end": 4.0, "camera": "slow_dolly_in"},
        {"name": "verse", "start": 4.0, "end": 8.0, "camera": "whip_pan_burst"},
        {"name": "chorus", "start": 8.0, "end": 12.0, "camera": "slow_pull_back"},
    ])
    plan = build_assemble_effects_plan(sb)
    assert isinstance(plan, AssembleEffectsPlan)
    assert plan.schema_version == "1.0"
    assert len(plan.transitions) == 2  # 3 scenes → 2 boundaries


def test_plan_snaps_transitions_to_nearest_beat():
    # 124 bpm → 0.4838 s between beats
    scenes = [
        {"name": "a", "start": 0.0, "end": 4.83, "camera": "slow_dolly_in"},
        {"name": "b", "start": 4.83, "end": 9.66, "camera": "slow_pull_back"},
    ]
    sb = _storyboard_with_beats(scenes, bpm=124)
    plan = build_assemble_effects_plan(sb)
    assert len(plan.transitions) == 1
    t = plan.transitions[0]
    # the boundary at 4.83 is on the 10th downbeat exactly
    assert abs(t.beat_offset_ms) <= 60.0
    assert t.kind in {"hard_cut", "crossfade", "whip_pan", "dip_to_black"}


def test_plan_marks_whip_pan_transition_kind():
    sb = _storyboard_with_beats([
        {"name": "a", "start": 0.0, "end": 4.0, "camera": "slow_dolly_in"},
        {"name": "b", "start": 4.0, "end": 8.0, "camera": "whip_pan_burst_then_hold"},
    ])
    plan = build_assemble_effects_plan(sb)
    assert plan.transitions[0].kind == "whip_pan"


def test_plan_marks_dip_to_black_for_chorus_or_drop_boundary():
    scenes = [
        {"name": "verse", "start": 0.0, "end": 5.0, "camera": "slow_pull_back"},
        {"name": "drop", "start": 5.0, "end": 10.0, "camera": "slow_dolly_in", "lyric": {"mood_label": "drop"}},
    ]
    sb = _storyboard_with_beats(scenes, bpm=120)
    plan = build_assemble_effects_plan(sb)
    assert plan.transitions[0].kind == "dip_to_black"


def test_plan_emits_internal_cuts_for_long_scenes():
    # 124 bpm grid; scenes are 12 s, target avg 3.5 → expect ~3 internal cuts per scene
    long_scene = {
        "name": "long_chorus",
        "start": 0.0,
        "end": 12.0,
        "camera": "slow_dolly_in",
    }
    sb = _storyboard_with_beats([long_scene], bpm=124)
    plan = build_assemble_effects_plan(sb, target_avg_shot_length_s=3.5)
    assert len(plan.internal_cuts) >= 1
    for c in plan.internal_cuts:
        assert c.scene_index == 0
        assert abs(c.beat_offset_ms) <= 200.0  # tolerance


def test_plan_skips_internal_cuts_for_short_scenes():
    short_scene = {"name": "intro", "start": 0.0, "end": 2.0, "camera": "slow_dolly_in"}
    sb = _storyboard_with_beats([short_scene], bpm=120)
    plan = build_assemble_effects_plan(sb, target_avg_shot_length_s=3.5)
    assert plan.internal_cuts == []


def test_plan_emits_risk_report_when_no_beat_grid():
    sb = _storyboard_with_beats(
        [{"name": "a", "start": 0.0, "end": 5.0, "camera": "slow_dolly_in"}],
        downbeat_times=[],
    )
    plan = build_assemble_effects_plan(sb)
    assert any("downbeat" in r.lower() or "no mir" in r.lower() for r in plan.risk_report)


def test_plan_emits_risk_report_for_unmusical_boundary():
    # boundary at 4.20 with 124 bpm grid (beats at 0.484 → closest is 4.354 / 3.871 → ~150 ms off)
    sb = _storyboard_with_beats(
        [
            {"name": "a", "start": 0.0, "end": 4.20, "camera": "slow_dolly_in"},
            {"name": "b", "start": 4.20, "end": 8.40, "camera": "slow_pull_back"},
        ],
        bpm=124,
    )
    plan = build_assemble_effects_plan(sb, beat_tolerance_ms=60.0)
    assert any("unmusical" in r.lower() for r in plan.risk_report)


def test_plan_cut_points_are_sorted_unique():
    sb = _storyboard_with_beats([
        {"name": "a", "start": 0.0, "end": 5.0, "camera": "slow_dolly_in"},
        {"name": "b", "start": 5.0, "end": 15.0, "camera": "slow_pull_back"},  # long
        {"name": "c", "start": 15.0, "end": 20.0, "camera": "slow_dolly_in"},
    ])
    plan = build_assemble_effects_plan(sb)
    assert plan.cut_points == sorted(plan.cut_points)
    # cut points is the union of transition times + internal cut times
    expected = sorted([t.at_time for t in plan.transitions] + [c.at_time for c in plan.internal_cuts])
    assert plan.cut_points == expected


def test_plan_handles_missing_optional_keys():
    # minimal scenes with no camera / no lyric / no downbeat_times
    sb = {
        "scenes": [
            {"start": 0.0, "duration": 5.0},  # no end key
            {"start": 5.0, "duration": 5.0},
        ],
    }
    plan = build_assemble_effects_plan(sb)
    assert len(plan.transitions) == 1


def test_plan_transition_kinds_property():
    sb = _storyboard_with_beats([
        {"name": "a", "start": 0.0, "end": 5.0, "camera": "slow_dolly_in"},
        {"name": "b", "start": 5.0, "end": 10.0, "camera": "slow_dolly_in"},  # same camera
    ])
    plan = build_assemble_effects_plan(sb)
    assert isinstance(plan.transition_kinds, list)
    assert all(isinstance(k, str) for k in plan.transition_kinds)


def test_plan_to_dict_roundtrips():
    sb = _storyboard_with_beats([
        {"name": "a", "start": 0.0, "end": 5.0, "camera": "slow_dolly_in"},
        {"name": "b", "start": 5.0, "end": 10.0, "camera": "whip_pan_burst"},
    ])
    plan = build_assemble_effects_plan(sb)
    d = plan.to_dict()
    # round-trip through json
    s = json.dumps(d, default=str)
    parsed = json.loads(s)
    assert parsed["schema_version"] == "1.0"
    assert len(parsed["transitions"]) == 1
    assert parsed["transitions"][0]["kind"] in {"whip_pan", "hard_cut", "crossfade", "dip_to_black"}


def test_plan_to_ffmpeg_filter_returns_string():
    sb = _storyboard_with_beats([
        {"name": "a", "start": 0.0, "end": 5.0, "camera": "slow_dolly_in"},
        {"name": "b", "start": 5.0, "end": 10.0, "camera": "slow_dolly_in"},
    ])
    plan = build_assemble_effects_plan(sb)
    s = plan_to_ffmpeg_filter(plan)
    assert "ffmpeg" in s
    assert isinstance(s, str)


def test_summarize_plan_one_liner():
    sb = _storyboard_with_beats([
        {"name": "a", "start": 0.0, "end": 5.0, "camera": "slow_dolly_in"},
        {"name": "b", "start": 5.0, "end": 10.0, "camera": "whip_pan_burst"},
    ])
    plan = build_assemble_effects_plan(sb)
    s = summarize_plan(plan)
    assert "effects plan v" in s
    assert "transitions" in s
    assert "risk notes" in s


def test_write_effects_plan_persists_to_disk(tmp_path: Path):
    sb = _storyboard_with_beats([
        {"name": "a", "start": 0.0, "end": 5.0, "camera": "slow_dolly_in"},
        {"name": "b", "start": 5.0, "end": 10.0, "camera": "slow_pull_back"},
    ])
    plan = build_assemble_effects_plan(sb)
    out = write_effects_plan(plan, tmp_path / "effects.json")
    assert out.exists()
    parsed = json.loads(out.read_text())
    assert parsed["schema_version"] == "1.0"
    assert len(parsed["transitions"]) == 1


def test_load_storyboard_for_plan_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_storyboard_for_plan(tmp_path / "does_not_exist.json")


def test_load_storyboard_for_plan_invalid_json(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text("[1, 2, 3]")  # not an object
    with pytest.raises(ValueError):
        load_storyboard_for_plan(p)


def test_plan_accepts_legacy_scene_segments_key():
    sb = _storyboard_with_beats(
        [
            {"name": "a", "start": 0.0, "end": 5.0, "camera": "slow_dolly_in"},
            {"name": "b", "start": 5.0, "end": 10.0, "camera": "slow_pull_back"},
        ],
    )
    sb["scene_segments"] = sb.pop("scenes")
    plan = build_assemble_effects_plan(sb)
    assert len(plan.transitions) == 1


def test_plan_zero_scenes_returns_only_risk_report():
    sb = {"scenes": [], "downbeat_times": []}
    plan = build_assemble_effects_plan(sb)
    assert plan.transitions == []
    assert plan.internal_cuts == []
    assert any("no scenes" in r.lower() for r in plan.risk_report)


def test_dataclass_field_defaults_are_safe():
    plan = AssembleEffectsPlan()
    assert plan.schema_version == "1.0"
    assert plan.target_avg_shot_length_s == 3.5
    assert plan.transitions == []
    assert plan.internal_cuts == []
    assert plan.cut_points == []
    assert plan.risk_report == []


def test_dataclass_dataclass_field_construction():
    t = TransitionAtBoundary(
        at_scene=0,
        at_time=4.0,
        kind="hard_cut",
        nearest_beat=3.87,
        beat_offset_ms=130.0,
        rational="test",
    )
    c = InternalCut(scene_index=0, at_time=3.5, nearest_beat=3.87, beat_offset_ms=-370.0)
    assert t.kind == "hard_cut"
    assert c.target_shot == "b-roll"  # default