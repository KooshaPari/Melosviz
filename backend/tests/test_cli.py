"""Tests for the ``viz`` CLI — verifies subcommands invoke the right paths."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from melosviz.cli.main import cli, _build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spec_dict(segments=None) -> dict:
    return {
        "metadata": {"width": 320, "height": 240, "fps": 1, "duration": 1.0},
        "palette": ["#ff0000"],
        "scene_segments": segments or [],
        "dense_keyframes": [],
        "timeline_events": [],
        "stem_channels": {},
        "mir": {},
        "layers": [],
        "keyframes": [],
        "timeline": [],
    }


# ---------------------------------------------------------------------------
# Parser smoke tests
# ---------------------------------------------------------------------------

class TestParser:
    def test_analyze_parses_wav_argument(self):
        p = _build_parser()
        args = p.parse_args(["analyze", "track.wav"])
        assert args.command == "analyze"
        assert args.wav == "track.wav"

    def test_build_parses_spec_argument(self):
        p = _build_parser()
        args = p.parse_args(["build", "spec.json"])
        assert args.command == "build"
        assert args.spec == "spec.json"

    def test_render_defaults(self):
        p = _build_parser()
        args = p.parse_args(["render", "spec.json"])
        assert args.format == "mp4"
        assert not args.skip_unimplemented

    def test_render_skip_unimplemented_flag(self):
        p = _build_parser()
        args = p.parse_args(["render", "spec.json", "--skip-unimplemented"])
        assert args.skip_unimplemented

    def test_diff_parses_two_args(self):
        p = _build_parser()
        args = p.parse_args(["diff", "spec.json", "overrides.yaml"])
        assert args.spec == "spec.json"
        assert args.overrides == "overrides.yaml"

    def test_apply_parses_two_args(self):
        p = _build_parser()
        args = p.parse_args(["apply", "spec.json", "overrides.yaml"])
        assert args.command == "apply"


# ---------------------------------------------------------------------------
# cmd_build: invokes route_spec via build_plan
# ---------------------------------------------------------------------------

class TestCmdBuild:
    def test_build_prints_plan_summary(self, tmp_path, capsys):
        spec = _spec_dict([
            {"label": "intro", "energy_mean": 0.2, "dominant_stem": "other",
             "brightness_mean": 0.4, "mood": {"arousal": 0.3, "valence": 0.5}},
        ])
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(spec), encoding="utf-8")

        with pytest.raises(SystemExit) as exc:
            cli(["build", str(spec_file)])

        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "RenderPlan" in out
        assert "intro" in out


# ---------------------------------------------------------------------------
# cmd_render: dispatches to orchestrate; stubs out adapter
# ---------------------------------------------------------------------------

class TestCmdRender:
    def test_render_skip_unimplemented(self, tmp_path, capsys):
        spec = _spec_dict([
            {"label": "chorus", "energy_mean": 0.8, "dominant_stem": "drums",
             "brightness_mean": 0.7, "mood": {"arousal": 0.9, "valence": 0.7}},
        ])
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(spec), encoding="utf-8")

        with pytest.raises(SystemExit) as exc:
            cli(["render", str(spec_file), "--skip-unimplemented",
                 "--output-dir", str(tmp_path / "out")])

        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "skipped" in out.lower() or "no segments" in out.lower()

    def test_render_raises_without_skip_flag(self, tmp_path):
        spec = _spec_dict([
            {"label": "chorus", "energy_mean": 0.8, "dominant_stem": "drums",
             "brightness_mean": 0.7, "mood": {"arousal": 0.9, "valence": 0.7}},
        ])
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(spec), encoding="utf-8")

        # Without --skip-unimplemented the BlenderAdapter stub raises
        with pytest.raises(NotImplementedError):
            cli(["render", str(spec_file), "--output-dir", str(tmp_path / "out")])


# ---------------------------------------------------------------------------
# cmd_diff: invokes diff_overrides
# ---------------------------------------------------------------------------

class TestCmdDiff:
    def test_diff_reports_no_differences(self, tmp_path, capsys):
        spec = _spec_dict()
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(spec), encoding="utf-8")

        overrides_file = tmp_path / "overrides.json"
        overrides_file.write_text("{}", encoding="utf-8")

        with pytest.raises(SystemExit) as exc:
            cli(["diff", str(spec_file), str(overrides_file)])

        assert exc.value.code == 0
        assert "no differences" in capsys.readouterr().out

    def test_diff_reports_changed_key(self, tmp_path, capsys):
        spec = _spec_dict()
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(spec), encoding="utf-8")

        overrides = {"palette": ["#0000ff"]}
        ov_file = tmp_path / "overrides.json"
        ov_file.write_text(json.dumps(overrides), encoding="utf-8")

        with pytest.raises(SystemExit) as exc:
            cli(["diff", str(spec_file), str(ov_file)])

        assert exc.value.code == 0
        out = capsys.readouterr().out
        # Diff output is JSON with path field
        diffs = json.loads(out)
        assert any(d["path"] == "palette" for d in diffs)


# ---------------------------------------------------------------------------
# cmd_apply: merges overrides and emits JSON
# ---------------------------------------------------------------------------

class TestCmdApply:
    def test_apply_merges_palette(self, tmp_path, capsys):
        spec = _spec_dict()
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(spec), encoding="utf-8")

        overrides = {"palette": ["#ffffff"]}
        ov_file = tmp_path / "overrides.json"
        ov_file.write_text(json.dumps(overrides), encoding="utf-8")

        with pytest.raises(SystemExit) as exc:
            cli(["apply", str(spec_file), str(ov_file)])

        assert exc.value.code == 0
        merged = json.loads(capsys.readouterr().out)
        assert merged["palette"] == ["#ffffff"]

    def test_apply_writes_to_output_file(self, tmp_path):
        spec = _spec_dict()
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(spec), encoding="utf-8")

        ov_file = tmp_path / "overrides.json"
        ov_file.write_text("{}", encoding="utf-8")

        out_file = tmp_path / "merged.json"

        with pytest.raises(SystemExit) as exc:
            cli(["apply", str(spec_file), str(ov_file), "-o", str(out_file)])

        assert exc.value.code == 0
        assert out_file.exists()
        merged = json.loads(out_file.read_text())
        assert "palette" in merged
