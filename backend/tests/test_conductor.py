"""Tests for the conductor: router, adapters, overrides, orchestrator."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from melosviz.conductor.router import SceneType, route_segment, route_spec
from melosviz.conductor.adapters import (
    ADAPTER_REGISTRY,
    AdapterBase,
    BlenderAdapter,
    ExperimentalCodeGenAdapter,
    LiveStageAdapter,
    MotionGraphicsAdapter,
    VideoExportAdapter,
    get_adapter,
)
from melosviz.conductor.overrides import OverrideError, apply_overrides, diff_overrides
from melosviz.conductor.orchestrator import RenderPlan, RenderResult, build_plan, orchestrate


# ---------------------------------------------------------------------------
# Router tests
# ---------------------------------------------------------------------------

class TestRouteSegment:
    """route_segment maps representative segments to expected SceneTypes."""

    def _seg(self, label: str, energy: float = 0.5, dominant_stem: str = "other",
             brightness: float = 0.5, arousal: float = 0.5) -> dict:
        return {
            "label": label,
            "energy_mean": energy,
            "dominant_stem": dominant_stem,
            "brightness_mean": brightness,
            "mood": {"arousal": arousal, "valence": 0.5},
        }

    def test_intro_yields_generative_asset(self):
        assert route_segment(self._seg("intro")) == SceneType.GENERATIVE_ASSET

    def test_outro_yields_generative_asset(self):
        assert route_segment(self._seg("outro")) == SceneType.GENERATIVE_ASSET

    def test_drop_always_procedural_3d(self):
        assert route_segment(self._seg("drop", energy=0.1)) == SceneType.PROCEDURAL_3D_ANIMATION

    def test_chorus_yields_procedural_3d(self):
        assert route_segment(self._seg("chorus")) == SceneType.PROCEDURAL_3D_ANIMATION

    def test_high_energy_drums_yields_procedural_3d(self):
        seg = self._seg("verse", energy=0.75, dominant_stem="drums")
        assert route_segment(seg) == SceneType.PROCEDURAL_3D_ANIMATION

    def test_low_energy_drums_verse_yields_beat_sync(self):
        # energy below 0.55 threshold → does not trigger drums rule → verse → beat_sync
        seg = self._seg("verse", energy=0.4, dominant_stem="drums")
        assert route_segment(seg) == SceneType.MOTION_GRAPHICS_BEAT_SYNC

    def test_verse_yields_motion_graphics(self):
        assert route_segment(self._seg("verse")) == SceneType.MOTION_GRAPHICS_BEAT_SYNC

    def test_bridge_yields_motion_graphics(self):
        assert route_segment(self._seg("bridge")) == SceneType.MOTION_GRAPHICS_BEAT_SYNC

    def test_breakdown_yields_live_stage(self):
        assert route_segment(self._seg("breakdown")) == SceneType.LIVE_STAGE

    def test_unknown_low_brightness_yields_experimental(self):
        seg = self._seg("unknown", brightness=0.1)
        assert route_segment(seg) == SceneType.EXPERIMENTAL_CODE_GEN

    def test_unknown_high_brightness_fallback_to_beat_sync(self):
        seg = self._seg("unknown", brightness=0.7)
        assert route_segment(seg) == SceneType.MOTION_GRAPHICS_BEAT_SYNC

    def test_accepts_pydantic_model(self):
        """route_segment accepts a SceneSegment pydantic model, not just a dict."""
        from melosviz.analysis.models import SceneSegment, MoodVector
        seg = SceneSegment(
            index=0, label="chorus", start=0.0, end=30.0,
            energy_mean=0.8, brightness_mean=0.6,
            mood=MoodVector(valence=0.7, arousal=0.8),
            dominant_stem="other",
        )
        assert route_segment(seg) == SceneType.PROCEDURAL_3D_ANIMATION

    def test_route_spec_returns_pairs(self):
        spec = {
            "scene_segments": [
                {"label": "intro", "energy_mean": 0.2, "dominant_stem": "other",
                 "brightness_mean": 0.4, "mood": {"arousal": 0.3, "valence": 0.5}},
                {"label": "chorus", "energy_mean": 0.9, "dominant_stem": "drums",
                 "brightness_mean": 0.8, "mood": {"arousal": 0.9, "valence": 0.7}},
            ]
        }
        pairs = route_spec(spec)
        assert len(pairs) == 2
        assert pairs[0][1] == SceneType.GENERATIVE_ASSET
        assert pairs[1][1] == SceneType.PROCEDURAL_3D_ANIMATION


# ---------------------------------------------------------------------------
# Adapter / registry tests
# ---------------------------------------------------------------------------

class TestAdapters:
    def test_all_scene_types_have_registered_adapters(self):
        for st in SceneType:
            adapter = get_adapter(st)
            assert isinstance(adapter, AdapterBase)

    def test_blender_adapter_raises_not_implemented(self):
        adapter = BlenderAdapter()
        with pytest.raises(NotImplementedError, match="BlenderAdapter"):
            adapter.render(segment={}, spec={}, output_dir=Path("/tmp"))

    def test_motion_graphics_adapter_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="MotionGraphicsAdapter"):
            MotionGraphicsAdapter().render({}, {}, Path("/tmp"))

    def test_live_stage_adapter_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="LiveStageAdapter"):
            LiveStageAdapter().render({}, {}, Path("/tmp"))

    def test_experimental_code_gen_adapter_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="ExperimentalCodeGenAdapter"):
            ExperimentalCodeGenAdapter().render({}, {}, Path("/tmp"))

    def test_unknown_scene_type_key_error(self):
        """A scene_type not in the registry raises KeyError, not silent fallback."""
        import copy
        original = dict(ADAPTER_REGISTRY)
        # Temporarily remove one entry to test missing key behaviour
        st = SceneType.GENERATIVE_ASSET
        del ADAPTER_REGISTRY[st]
        try:
            with pytest.raises(KeyError, match="No adapter registered"):
                get_adapter(st)
        finally:
            ADAPTER_REGISTRY.update(original)


# ---------------------------------------------------------------------------
# Overrides tests
# ---------------------------------------------------------------------------

class TestOverrides:
    def _base_spec(self) -> dict:
        return {
            "metadata": {"width": 1920, "height": 1080, "fps": 30},
            "palette": ["#ff0000", "#00ff00"],
            "scene_segments": [],
        }

    def test_apply_overrides_merges_top_level(self):
        spec = self._base_spec()
        merged = apply_overrides(spec, {"palette": ["#0000ff"]})
        assert merged["palette"] == ["#0000ff"]
        # Original spec untouched
        assert spec["palette"] == ["#ff0000", "#00ff00"]

    def test_apply_overrides_deep_merges_nested(self):
        spec = self._base_spec()
        merged = apply_overrides(spec, {"metadata": {"fps": 60}})
        assert merged["metadata"]["fps"] == 60
        # Other metadata keys preserved
        assert merged["metadata"]["width"] == 1920

    def test_apply_overrides_none_is_identity(self):
        spec = self._base_spec()
        merged = apply_overrides(spec, None)
        assert merged == spec

    def test_apply_overrides_empty_is_identity(self):
        spec = self._base_spec()
        merged = apply_overrides(spec, {})
        assert merged == spec

    def test_apply_overrides_adds_new_keys(self):
        spec = self._base_spec()
        merged = apply_overrides(spec, {"adapter_flags": {"blender_samples": 64}})
        assert merged["adapter_flags"] == {"blender_samples": 64}

    def test_apply_overrides_rejects_non_dict(self):
        with pytest.raises(OverrideError, match="must be a dict"):
            apply_overrides(self._base_spec(), ["bad", "list"])

    def test_diff_overrides_empty_returns_no_diffs(self):
        spec = self._base_spec()
        assert diff_overrides(spec, {}) == []

    def test_diff_overrides_detects_changed_value(self):
        spec = self._base_spec()
        diffs = diff_overrides(spec, {"palette": ["#blue"]})
        assert len(diffs) == 1
        assert diffs[0]["path"] == "palette"
        assert diffs[0]["canonical"] == ["#ff0000", "#00ff00"]
        assert diffs[0]["override"] == ["#blue"]

    def test_diff_overrides_detects_nested_change(self):
        spec = self._base_spec()
        diffs = diff_overrides(spec, {"metadata": {"fps": 60}})
        assert any(d["path"] == "metadata.fps" for d in diffs)

    def test_diff_overrides_new_key_reported(self):
        spec = self._base_spec()
        diffs = diff_overrides(spec, {"new_key": "value"})
        assert any(d["path"] == "new_key" for d in diffs)

    def test_diff_overrides_rejects_non_dict(self):
        with pytest.raises(OverrideError):
            diff_overrides(self._base_spec(), "bad")

    def test_apply_then_diff_round_trip(self):
        """apply_overrides + diff_overrides round-trip: diffs from the merged spec are empty."""
        spec = self._base_spec()
        overrides = {"palette": ["#0000ff"], "metadata": {"fps": 60}}
        merged = apply_overrides(spec, overrides)
        # diff of merged vs the same overrides should show no changes for the overridden keys
        remaining_diffs = diff_overrides(merged, overrides)
        # merged already has the overridden values, so no divergence for those keys
        assert remaining_diffs == []

    def test_apply_pydantic_model(self):
        """apply_overrides accepts a RenderSpec pydantic model."""
        from melosviz.analysis.models import RenderSpec
        spec = RenderSpec(palette=["#aabbcc"])
        merged = apply_overrides(spec, {"palette": ["#ffffff"]})
        assert merged["palette"] == ["#ffffff"]


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------

class TestOrchestrator:
    def _spec_with_segments(self, *labels) -> dict:
        return {
            "scene_segments": [
                {"label": label, "energy_mean": 0.5, "dominant_stem": "other",
                 "brightness_mean": 0.5, "mood": {"arousal": 0.5, "valence": 0.5}}
                for label in labels
            ],
            "palette": ["#ff0000"],
            "metadata": {"width": 320, "height": 240, "fps": 1, "duration": 1.0},
        }

    def test_build_plan_no_render(self):
        spec = self._spec_with_segments("intro", "chorus")
        plan = build_plan(spec)
        assert isinstance(plan, RenderPlan)
        assert len(plan.routes) == 2
        summary = plan.summary()
        assert "intro" in summary
        assert "chorus" in summary

    def test_orchestrate_skips_unimplemented_when_flag_set(self, tmp_path):
        """Stub adapters are skipped (not raised) when skip_unimplemented=True."""
        spec = self._spec_with_segments("chorus")  # → BlenderAdapter stub
        result = orchestrate(spec, tmp_path, skip_unimplemented=True)
        assert result.skipped_count == 1
        assert result.success  # skips are not errors

    def test_orchestrate_raises_unimplemented_by_default(self, tmp_path):
        """Without skip_unimplemented, a stub adapter raises NotImplementedError."""
        spec = self._spec_with_segments("chorus")  # → BlenderAdapter stub
        with pytest.raises(NotImplementedError, match="BlenderAdapter"):
            orchestrate(spec, tmp_path, skip_unimplemented=False)

    def test_orchestrate_empty_spec_succeeds(self, tmp_path):
        spec = {"scene_segments": []}
        result = orchestrate(spec, tmp_path, skip_unimplemented=True)
        assert result.success
        assert result.skipped_count == 0
        assert result.rendered_paths == []

    def test_orchestrate_generative_asset_calls_video_export(self, tmp_path):
        """Generative-asset segments go through VideoExportAdapter.render."""
        spec = self._spec_with_segments("intro")  # → VideoExportAdapter
        mock_path = tmp_path / "mock_output.mp4"
        mock_path.touch()

        with patch(
            "melosviz.conductor.adapters.VideoExportAdapter.render",
            return_value=mock_path,
        ) as mock_render:
            result = orchestrate(spec, tmp_path, skip_unimplemented=True)

        mock_render.assert_called_once()
        assert result.rendered_paths == [mock_path]
        assert result.success
