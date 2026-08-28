"""Tests for storyboard validation — catches missing / out-of-range /
incompatible fields before they break a 3-minute render.

Rules covered: schema_version, scene timing, gap/overlap detection, palette
shape, camera whitelist, scene_type whitelist, total duration, continuity
anchor presence, lyric dangling refs, edit_count vs edits[] consistency.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from melosviz.conductor.validate import (
    ALLOWED_CAMERAS,
    ALLOWED_SCENE_TYPES,
    Issue,
    SUPPORTED_SCHEMA_VERSIONS,
    ValidationReport,
    validate_storyboard,
    validate_storyboard_file,
    write_report,
)


def _sb(**overrides):
    sb = {
        "schema_version": "1.0",
        "concept": "neon noir",
        "bpm": 124,
        "aspect_ratio": "festival_16x9_4k",
        "scenes": [
            {
                "scene_index": 0,
                "name": "intro",
                "start": 0.0,
                "end": 10.0,
                "duration": 10.0,
                "prompt": "abstract bioluminescent city",
                "camera": "slow_dolly_in",
                "seed": 1,
                "scene_type": "comfyui_image",
                "palette": ["#0d0d10", "#ff2bd6", "#22d3ee"],
                "width": 1920,
                "height": 1080,
                "fps": 24,
            },
            {
                "scene_index": 1,
                "name": "verse",
                "start": 10.0,
                "end": 30.0,
                "duration": 20.0,
                "prompt": "silver-haired dancer",
                "camera": "slow_pull_back",
                "seed": 2,
                "scene_type": "comfyui_video",
                "palette": ["#0d0d10", "#22d3ee", "#c084fc"],
                "width": 1920,
                "height": 1080,
                "fps": 24,
            },
            {
                "scene_index": 2,
                "name": "chorus",
                "start": 30.0,
                "end": 50.0,
                "duration": 20.0,
                "prompt": "whip pan skyway",
                "camera": "whip_pan_burst",
                "seed": 3,
                "scene_type": "unreal_cinematic",
                "palette": ["#0d0d10", "#c084fc", "#f0f0f8"],
                "width": 1920,
                "height": 1080,
                "fps": 24,
            },
        ],
    }
    sb.update(overrides)
    return sb


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------

def test_validate_storyboard_clean_returns_no_errors():
    rpt = validate_storyboard(_sb())
    assert not rpt.has_errors
    assert rpt.scene_count == 3
    assert rpt.total_duration == 50.0
    assert sorted(rpt.cameras_used) == ["slow_dolly_in", "slow_pull_back", "whip_pan_burst"]
    assert "comfyui_image" in rpt.scene_types_used


def test_validate_storyboard_populates_palette_used():
    rpt = validate_storyboard(_sb())
    assert len(rpt.palette_used) == 5  # union of 3 scenes x 3 colors (one overlap)


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

def test_validate_storyboard_missing_schema_is_error():
    sb = _sb()
    sb.pop("schema_version")
    rpt = validate_storyboard(sb)
    assert rpt.has_errors
    assert any(i.code == "schema_missing" for i in rpt.issues)


def test_validate_storyboard_unsupported_schema_is_error():
    sb = _sb(schema_version="99.0")
    rpt = validate_storyboard(sb)
    assert any(i.code == "schema_unsupported" for i in rpt.issues)


def test_supported_schema_versions_includes_1_0():
    assert "1.0" in SUPPORTED_SCHEMA_VERSIONS


# ---------------------------------------------------------------------------
# Scene timing
# ---------------------------------------------------------------------------

def test_validate_storyboard_detects_overlapping_scenes():
    sb = _sb()
    sb["scenes"][1]["start"] = 5.0
    sb["scenes"][1]["end"] = 30.0
    sb["scenes"][1]["duration"] = 25.0
    rpt = validate_storyboard(sb)
    assert any(i.code == "scene_timing_inverted" or "start" in i.message for i in rpt.issues if i.severity == "error")


def test_validate_storyboard_detects_gap_too_large():
    sb = _sb()
    sb["scenes"][1]["start"] = 15.0
    sb["scenes"][1]["end"] = 30.0
    sb["scenes"][1]["duration"] = 15.0
    rpt = validate_storyboard(sb)
    assert any(i.code == "scene_gap_too_large" for i in rpt.issues)


def test_validate_storyboard_detects_duration_mismatch():
    sb = _sb()
    sb["scenes"][0]["duration"] = 999.0
    rpt = validate_storyboard(sb)
    assert any(i.code == "scene_duration_mismatch" for i in rpt.issues)


def test_validate_storyboard_detects_missing_timing():
    sb = _sb()
    sb["scenes"][0].pop("start")
    rpt = validate_storyboard(sb)
    assert any(i.code == "scene_timing_missing" for i in rpt.issues)


def test_validate_storyboard_detects_empty_scenes():
    sb = _sb(scenes=[])
    rpt = validate_storyboard(sb)
    assert any(i.code == "scenes_empty" for i in rpt.issues)
    assert rpt.has_errors


# ---------------------------------------------------------------------------
# Scene type / camera
# ---------------------------------------------------------------------------

def test_validate_storyboard_detects_unknown_scene_type():
    sb = _sb()
    sb["scenes"][0]["scene_type"] = "nuke_render"
    rpt = validate_storyboard(sb)
    assert any(i.code == "scene_type_unsupported" for i in rpt.issues)


def test_allowed_scene_types_contains_comfyui_image():
    assert "comfyui_image" in ALLOWED_SCENE_TYPES


def test_validate_storyboard_detects_unknown_camera_as_warning():
    sb = _sb()
    sb["scenes"][0]["camera"] = "ufo_abduction"
    rpt = validate_storyboard(sb)
    assert any(i.code == "camera_unknown" for i in rpt.issues)


def test_allowed_cameras_contains_basic_archetypes():
    for cam in ("slow_dolly_in", "slow_pull_back", "whip_pan_burst", "static_wide"):
        assert cam in ALLOWED_CAMERAS


def test_validate_storyboard_detects_empty_camera():
    sb = _sb()
    sb["scenes"][0].pop("camera")
    rpt = validate_storyboard(sb)
    assert any(i.code == "scene_camera_empty" for i in rpt.issues)


# ---------------------------------------------------------------------------
# Prompt / palette
# ---------------------------------------------------------------------------

def test_validate_storyboard_detects_empty_prompt():
    sb = _sb()
    sb["scenes"][0]["prompt"] = ""
    rpt = validate_storyboard(sb)
    assert any(i.code == "scene_prompt_empty" for i in rpt.issues)


def test_validate_storyboard_detects_invalid_hex_in_palette():
    sb = _sb()
    sb["scenes"][0]["palette"] = ["#0d0d10", "neon", "#ff2bd6"]
    rpt = validate_storyboard(sb)
    assert any(i.code == "palette_invalid_hex" for i in rpt.issues)


def test_validate_storyboard_detects_thin_global_palette():
    """Two distinct colors is too thin for a 3-minute video."""
    sb = _sb()
    # Force all scenes to share only 1 color
    for sc in sb["scenes"]:
        sc["palette"] = ["#0d0d10", "#0d0d10", "#0d0d10"]
    rpt = validate_storyboard(sb)
    assert any(i.code == "palette_too_thin" for i in rpt.issues)


def test_validate_storyboard_detects_repetitive_cameras():
    sb = _sb()
    for sc in sb["scenes"]:
        sc["camera"] = "slow_dolly_in"
    rpt = validate_storyboard(sb)
    assert any(i.code == "cameras_repetitive" for i in rpt.issues)


# ---------------------------------------------------------------------------
# Continuity, lyrics, edits
# ---------------------------------------------------------------------------

def test_validate_storyboard_require_continuity_warns_when_missing():
    rpt = validate_storyboard(_sb(), require_continuity=True)
    assert any(i.code == "continuity_missing" for i in rpt.issues)


def test_validate_storyboard_continuity_present_when_anchored():
    sb = _sb()
    sb["continuity"] = {
        "subject_token": "silver-haired dancer",
        "env_token": "underwater city",
    }
    rpt = validate_storyboard(sb)
    assert rpt.continuity_present


def test_validate_storyboard_dangling_lyric_ref_is_info():
    sb = _sb()
    sb["scenes"][0]["lyric"] = {"phrase_id": "missing-phrase"}
    rpt = validate_storyboard(sb)
    assert any(i.code == "lyric_dangling_ref" for i in rpt.issues)


def test_validate_storyboard_edits_consistency():
    sb = _sb()
    sb["edit_count"] = 3
    sb["edits"] = []  # empty even though count says 3
    rpt = validate_storyboard(sb)
    assert any(i.code == "edits_missing" for i in rpt.issues)


# ---------------------------------------------------------------------------
# Severity / reporting shape
# ---------------------------------------------------------------------------

def test_validation_report_summary_counts_by_severity():
    sb = _sb()
    sb["scenes"][0]["scene_type"] = "nuke_render"
    sb["scenes"][0]["prompt"] = ""
    sb["scenes"][0].pop("camera")
    rpt = validate_storyboard(sb)
    assert rpt.summary.get("error", 0) >= 1
    assert rpt.summary.get("warning", 0) >= 2


def test_validation_report_to_dict_round_trip():
    sb = _sb()
    rpt = validate_storyboard(sb)
    d = rpt.to_dict()
    assert d["scene_count"] == 3
    assert "issues" in d
    json.dumps(d)


def test_issue_to_dict_omits_none_fields():
    issue = Issue("error", "scene_timing_missing", "scene 0 missing start/end/duration", scene_index=0)
    d = issue.to_dict()
    assert d == {
        "severity": "error",
        "code": "scene_timing_missing",
        "message": "scene 0 missing start/end/duration",
        "scene_index": 0,
    }


# ---------------------------------------------------------------------------
# File-based validation + report writing
# ---------------------------------------------------------------------------

def test_validate_storyboard_file_reads_json(tmp_path):
    p = tmp_path / "sb.json"
    p.write_text(json.dumps(_sb()), encoding="utf-8")
    rpt = validate_storyboard_file(p)
    assert rpt.storyboard_path == str(p)
    assert rpt.scene_count == 3


def test_validate_storyboard_file_raises_on_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_storyboard_file(tmp_path / "missing.json")


def test_validate_storyboard_file_raises_on_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        validate_storyboard_file(p)


def test_write_report_round_trip(tmp_path):
    rpt = validate_storyboard(_sb())
    target = tmp_path / "storyboard.report.json"
    out = write_report(rpt, target)
    assert out == target
    payload = json.loads(target.read_text())
    assert payload["scene_count"] == 3
    assert payload["schema_version"] == "1.0"
    assert "issues" in payload
    assert "summary" in payload
