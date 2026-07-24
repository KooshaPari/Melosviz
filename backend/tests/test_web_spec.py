"""Tests for web-facing shot keyframe composition."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from melosviz.analysis.models import RenderSpec
from melosviz.compose.web_spec import (
    build_shot_keyframes,
    enrich_render_spec_for_web,
    tag_dense_keyframes_with_scenes,
)
from melosviz.presets.scene_families import remap_scene_segments


def _sample_segments() -> list[dict]:
    return [
        {
            "index": 0,
            "label": "intro",
            "start": 0.0,
            "end": 30.0,
            "energy_mean": 0.25,
            "brightness_mean": 0.4,
        },
        {
            "index": 1,
            "label": "verse",
            "start": 30.0,
            "end": 60.0,
            "energy_mean": 0.45,
            "brightness_mean": 0.5,
        },
        {
            "index": 2,
            "label": "chorus",
            "start": 60.0,
            "end": 90.0,
            "energy_mean": 0.75,
            "brightness_mean": 0.65,
        },
        {
            "index": 3,
            "label": "outro",
            "start": 90.0,
            "end": 120.0,
            "energy_mean": 0.3,
            "brightness_mean": 0.35,
        },
    ]


class TestRemapSceneSegments:
    def test_adjacent_templates_are_unique(self) -> None:
        remapped = remap_scene_segments(_sample_segments(), preset_name="cinematic")
        templates = [s["scene_template"] for s in remapped]
        for i in range(1, len(templates)):
            assert templates[i] != templates[i - 1]

    def test_cinematic_differs_from_default(self) -> None:
        default = remap_scene_segments(_sample_segments())
        cinematic = remap_scene_segments(_sample_segments(), preset_name="cinematic")
        assert [s["scene_template"] for s in default] != [
            s["scene_template"] for s in cinematic
        ]


class TestBuildShotKeyframes:
    def test_one_keyframe_per_segment_plus_terminal(self) -> None:
        segs = remap_scene_segments(_sample_segments())
        kfs = build_shot_keyframes(segs, 120.0, ["#111111", "#222222"])
        assert len(kfs) == len(segs) + 1
        assert kfs[0]["t"] == pytest.approx(0.0)
        assert kfs[-1]["t"] == pytest.approx(1.0)

    def test_keyframes_carry_scene_template(self) -> None:
        segs = remap_scene_segments(_sample_segments())
        kfs = build_shot_keyframes(segs, 120.0)
        templates = {kf["scene_template"] for kf in kfs}
        assert len(templates) >= 3


class TestEnrichRenderSpecForWeb:
    def test_analyze_wav_rich_populates_web_keyframes(self, tmp_path: Path) -> None:
        import struct
        import wave

        from melosviz.analysis.audio import analyze_wav_rich

        wav = tmp_path / "tone.wav"
        n = 44100
        with wave.open(str(wav), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(struct.pack("<" + "h" * n, *([1000] * n)))

        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
        ):
            spec = analyze_wav_rich(str(wav))

        assert len(spec.scene_segments) >= 4
        assert len(spec.keyframes) >= 4
        templates = {kf.get("scene_template") for kf in spec.keyframes}
        assert len(templates) >= 2
        for seg in spec.scene_segments:
            assert "scene_template" in seg

    def test_dense_keyframes_tagged_with_scene(self) -> None:
        segs = remap_scene_segments(_sample_segments())
        dense = [{"t": 0.0, "energy": 0.5}, {"t": 60.0, "energy": 0.8}]
        tagged = tag_dense_keyframes_with_scenes(dense, segs)
        assert tagged[0]["scene_template"]
        assert tagged[1]["scene_template"]

    def test_preset_enrichment_remaps_templates(self) -> None:
        spec = RenderSpec(
            metadata={"duration": 120.0},
            scene_segments=_sample_segments(),
            palette=["#0A0F1A", "#C45A1A"],
        )
        enriched = enrich_render_spec_for_web(spec, preset_name="synthwave")
        templates = [s["scene_template"] for s in enriched["scene_segments"]]
        assert templates[0] == "grid_depth"
