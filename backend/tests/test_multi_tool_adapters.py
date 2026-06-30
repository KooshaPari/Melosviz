"""Tests for P6 multi-tool conductor adapters.

TDD protocol (failing-first → green):
(a) AEAdapter generates valid nexrender job spec from a sample RenderSpec.
(b) AE RenderSpec→job-param mappings correct (beats/segments/mogrt).
(c) Registry no longer raises for motion_graphics_beat_sync.
(d) MEAdapter generates AME job spec; assembles multi-segment via ffmpeg fallback.
(e) Explicit error (not silent) when a tool's job spec can't be built.
(f) FireflyAdapter generates per-segment job specs with correct prompt/mood mapping.
(g) Orchestrator dispatches scene types to correct adapters + runs assembly.
(h) Registry covers all GOLD/SILVER adapter scene types.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _minimal_spec(
    duration: float = 60.0,
    with_segments: bool = True,
    with_beats: bool = True,
) -> Any:
    """Build a minimal RenderSpec v2 for adapter tests (no heavy audio deps)."""
    from melosviz.analysis.models import RenderSpec

    spec = RenderSpec(
        metadata={
            "source_audio": "test.wav",
            "duration": duration,
            "fps": 30,
            "width": 1920,
            "height": 1080,
            "estimated_bpm": 128.0,
        },
        palette=["#00f5ff", "#ff2fd5", "#8a75ff"],
    )
    dense_kfs: list[dict[str, Any]] = []
    if with_beats:
        dense_kfs = [
            {
                "t": 0.0, "energy": 0.7, "brightness": 0.6,
                "valence": 0.5, "arousal": 0.8,
                "beat_strength": 0.9, "onset_strength": 0.4,
                "spectral_centroid": 3200.0,
                "stems": {"drums": 0.8, "bass": 0.5, "vocals": 0.2, "other": 0.3},
                "easing": "ease_in_out",
            },
            {
                "t": 0.47, "energy": 0.5, "brightness": 0.4,
                "valence": 0.4, "arousal": 0.6,
                "beat_strength": 0.0, "onset_strength": 0.6,
                "spectral_centroid": 2400.0,
                "stems": {"drums": 0.3, "bass": 0.6, "vocals": 0.5, "other": 0.2},
                "easing": "linear",
            },
            {
                "t": 0.94, "energy": 0.9, "brightness": 0.8,
                "valence": 0.7, "arousal": 0.9,
                "beat_strength": 1.0, "onset_strength": 0.7,
                "spectral_centroid": 4000.0,
                "stems": {"drums": 0.9, "bass": 0.4, "vocals": 0.3, "other": 0.1},
                "easing": "ease_in",
            },
        ]

    segs: list[dict[str, Any]] = []
    if with_segments:
        segs = [
            {
                "index": 0, "label": "intro", "start": 0.0, "end": 30.0,
                "energy_mean": 0.3, "brightness_mean": 0.4,
                "mood": {"valence": 0.5, "arousal": 0.4},
                "dominant_stem": "bass",
            },
            {
                "index": 1, "label": "drop", "start": 30.0, "end": 60.0,
                "energy_mean": 0.9, "brightness_mean": 0.8,
                "mood": {"valence": 0.8, "arousal": 0.95},
                "dominant_stem": "drums",
            },
        ]

    # Inject v2 fields — RenderSpec allows extra via model_config or direct dict
    spec_dict = spec.model_dump()
    spec_dict["dense_keyframes"] = dense_kfs
    spec_dict["scene_segments"] = segs
    spec_dict["mir"] = {
        "tempo_bpm": 128.0,
        "danceability": 0.85,
        "key": "C",
        "mode": "major",
    }
    return type(spec).model_validate(spec_dict)


# ---------------------------------------------------------------------------
# (a) AEAdapter: valid nexrender job spec from RenderSpec
# ---------------------------------------------------------------------------


class TestAEAdapterJobSpec:
    def test_build_ae_job_spec_returns_dict(self) -> None:
        from melosviz.render.aftereffects_adapter import build_ae_job_spec

        spec = _minimal_spec()
        job = build_ae_job_spec(spec)
        assert isinstance(job, dict)

    def test_job_spec_has_required_top_level_keys(self) -> None:
        from melosviz.render.aftereffects_adapter import build_ae_job_spec

        job = build_ae_job_spec(_minimal_spec())
        for key in ("schema", "template", "assets", "actions", "mogrt_params", "melosviz_meta"):
            assert key in job, f"Missing key: {key!r}"

    def test_template_block_has_frame_range(self) -> None:
        from melosviz.render.aftereffects_adapter import build_ae_job_spec

        spec = _minimal_spec(duration=60.0)
        job = build_ae_job_spec(spec)
        template = job["template"]
        # 60s * 30fps = 1800 frames
        assert template["frameEnd"] == 1800
        assert template["frameStart"] == 0

    def test_assets_contain_beat_onset_segment_palette(self) -> None:
        from melosviz.render.aftereffects_adapter import build_ae_job_spec

        job = build_ae_job_spec(_minimal_spec())
        layer_names = {a["layerName"] for a in job["assets"]}
        assert "beat_data" in layer_names
        assert "onset_data" in layer_names
        assert "segment_data" in layer_names
        assert "palette_data" in layer_names

    def test_job_spec_is_json_serialisable(self) -> None:
        from melosviz.render.aftereffects_adapter import build_ae_job_spec

        job = build_ae_job_spec(_minimal_spec())
        serialised = json.dumps(job)
        assert len(serialised) > 100

    def test_rotobrush3_hook_absent_without_source_video(self) -> None:
        from melosviz.render.aftereffects_adapter import build_ae_job_spec

        job = build_ae_job_spec(_minimal_spec())
        layer_names = [a.get("layerName") for a in job["assets"]]
        assert "rotobrush3_source" not in layer_names

    def test_rotobrush3_hook_present_with_source_video(self) -> None:
        from melosviz.analysis.models import RenderSpec
        from melosviz.render.aftereffects_adapter import build_ae_job_spec

        spec = _minimal_spec()
        d = spec.model_dump()
        d["metadata"]["source_video"] = "/footage/performer.mp4"
        spec2 = RenderSpec.model_validate(d)

        job = build_ae_job_spec(spec2)
        roto = next((a for a in job["assets"] if a.get("layerName") == "rotobrush3_source"), None)
        assert roto is not None
        assert roto["src"] == "/footage/performer.mp4"
        assert roto["rotobrush3"]["enabled"] is True
        assert job["melosviz_meta"]["has_rotobrush3"] is True


# ---------------------------------------------------------------------------
# (b) AE RenderSpec→job-param mapping correct
# ---------------------------------------------------------------------------


class TestAEParamMapping:
    def test_beats_csv_contains_only_beat_frames(self) -> None:
        from melosviz.render.aftereffects_adapter import build_beats_csv

        kfs = [
            {"t": 0.0, "beat_strength": 0.9, "energy": 0.7},
            {"t": 0.47, "beat_strength": 0.0, "energy": 0.5},  # not a beat
            {"t": 0.94, "beat_strength": 1.0, "energy": 0.9},
        ]
        csv_content = build_beats_csv(kfs)
        lines = [ln for ln in csv_content.strip().splitlines() if ln]
        # header + 2 beat rows (t=0.0 and t=0.94)
        assert len(lines) == 3
        assert "0.0" in lines[1]
        assert "0.94" in lines[2]

    def test_onsets_csv_contains_only_onset_frames(self) -> None:
        from melosviz.render.aftereffects_adapter import build_onsets_csv

        kfs = [
            {"t": 0.0, "onset_strength": 0.0},
            {"t": 0.47, "onset_strength": 0.6, "brightness": 0.4},
            {"t": 0.94, "onset_strength": 0.7, "brightness": 0.8},
        ]
        csv_content = build_onsets_csv(kfs)
        lines = [ln for ln in csv_content.strip().splitlines() if ln]
        assert len(lines) == 3  # header + 2 rows

    def test_segment_csv_contains_mogrt_template_column(self) -> None:
        from melosviz.render.aftereffects_adapter import build_segment_csv

        segs = [
            {"index": 0, "label": "chorus", "start": 0.0, "end": 30.0,
             "energy_mean": 0.8, "dominant_stem": "vocals",
             "mood": {"valence": 0.8, "arousal": 0.9}},
        ]
        csv_content = build_segment_csv(segs)
        assert "ChorusBurst" in csv_content

    def test_mogrt_param_map_per_segment(self) -> None:
        from melosviz.render.aftereffects_adapter import build_mogrt_param_map

        segs = [
            {"index": 0, "label": "drop", "dominant_stem": "drums",
             "energy_mean": 0.9, "mood": {"valence": 0.8, "arousal": 0.95}},
        ]
        result = build_mogrt_param_map(segs, ["#00f5ff"], {"tempo_bpm": 128.0, "key": "C", "mode": "major"})
        assert "drop" in result
        drop_params = result["drop"]
        assert drop_params["mogrt_template"] == "DropImpact"
        assert drop_params["tempo_bpm"] == 128.0
        assert "rhythm_layer_opacity" in drop_params  # drums stem param

    def test_melosviz_meta_beat_count(self) -> None:
        from melosviz.render.aftereffects_adapter import build_ae_job_spec

        job = build_ae_job_spec(_minimal_spec(with_beats=True))
        # 2 keyframes have beat_strength > 0 (t=0.0 and t=0.94)
        assert job["melosviz_meta"]["beat_count"] == 2


# ---------------------------------------------------------------------------
# (c) Registry no longer raises for motion_graphics_beat_sync
# ---------------------------------------------------------------------------


class TestRegistryMotionGraphics:
    def test_motion_graphics_in_registry(self) -> None:
        from melosviz.conductor.registry import ADAPTER_REGISTRY

        assert "motion_graphics_beat_sync" in ADAPTER_REGISTRY

    def test_motion_graphics_adapter_instantiates(self) -> None:
        from melosviz.conductor.registry import ADAPTER_REGISTRY

        adapter_cls = ADAPTER_REGISTRY["motion_graphics_beat_sync"]
        # Should not raise
        adapter = adapter_cls()
        assert adapter is not None

    def test_motion_graphics_adapter_render_does_not_raise(self, tmp_path: Path) -> None:
        from melosviz.conductor.registry import ADAPTER_REGISTRY

        adapter = ADAPTER_REGISTRY["motion_graphics_beat_sync"]()
        # Should not raise NotImplementedError or ConductorError
        result = adapter.render(_minimal_spec(), output_path=tmp_path)
        assert result is not None

    def test_all_gold_scene_types_in_registry(self) -> None:
        from melosviz.conductor.registry import ADAPTER_REGISTRY

        for st in ("generative_asset", "motion_graphics_beat_sync", "assembly_encode",
                   "procedural_3d_animation", "live_stage", "video_export"):
            assert st in ADAPTER_REGISTRY, f"Missing scene type: {st!r}"


# ---------------------------------------------------------------------------
# (d) MEAdapter: multi-segment assembly via AME spec / ffmpeg fallback
# ---------------------------------------------------------------------------


class TestMEAdapter:
    def test_build_ame_job_spec_returns_dict(self, tmp_path: Path) -> None:
        from melosviz.render.mediaencoder_adapter import build_ame_job_spec

        seg_paths = [tmp_path / "seg0.mp4", tmp_path / "seg1.mp4"]
        job = build_ame_job_spec(_minimal_spec(), seg_paths)
        assert isinstance(job, dict)

    def test_ame_job_spec_has_required_keys(self, tmp_path: Path) -> None:
        from melosviz.render.mediaencoder_adapter import build_ame_job_spec

        seg_paths = [tmp_path / "seg0.mp4"]
        job = build_ame_job_spec(_minimal_spec(), seg_paths)
        for key in ("ame_batch_version", "melosviz_meta", "source_clips", "encode_queue",
                    "assembly_order", "transition"):
            assert key in job, f"Missing key: {key!r}"

    def test_encode_queue_has_prores_and_h264(self, tmp_path: Path) -> None:
        from melosviz.render.mediaencoder_adapter import build_ame_job_spec

        job = build_ame_job_spec(_minimal_spec(), [tmp_path / "s.mp4"])
        presets = [e["preset"] for e in job["encode_queue"]]
        assert "ProRes_Master" in presets
        assert "H264_Delivery" in presets

    def test_source_clips_aligned_with_segments(self, tmp_path: Path) -> None:
        from melosviz.render.mediaencoder_adapter import build_ame_job_spec

        seg_paths = [tmp_path / "intro.mp4", tmp_path / "drop.mp4"]
        job = build_ame_job_spec(_minimal_spec(), seg_paths)
        clips = job["source_clips"]
        assert len(clips) == 2
        assert clips[0]["label"] == "intro"
        assert clips[1]["label"] == "drop"

    def test_me_adapter_render_writes_job_spec(self, tmp_path: Path) -> None:
        from melosviz.render.mediaencoder_adapter import MEAdapter

        # Create a dummy segment path (need at least one to build a valid spec)
        seg = tmp_path / "seg0.mp4"
        seg.touch()

        # use_ame=None: auto-detect. AME absent in CI → spec written, no assembly.
        adapter = MEAdapter(use_ame=None)
        result = adapter.render(
            _minimal_spec(),
            output_path=tmp_path,
            segment_paths=[seg],
        )
        assert result is not None
        # Job spec file should be written regardless of AME availability
        assert (tmp_path / "ame_batch_job.json").exists()

    def test_ffmpeg_fallback_logged_explicitly(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When AME absent, ffmpeg fallback must log a WARNING — not be silent."""
        import logging

        from melosviz.render.mediaencoder_adapter import assemble_with_ffmpeg
        from melosviz.render.video_exporter import is_ffmpeg_available

        if not is_ffmpeg_available():
            pytest.skip("ffmpeg not available in this environment")

        # Create tiny dummy segment files (not real video — ffmpeg will fail)
        # We only need to verify the WARNING is emitted, not that ffmpeg succeeds.
        import contextlib

        with caplog.at_level(logging.WARNING, logger="melosviz.render.mediaencoder_adapter"), \
                contextlib.suppress(Exception):
            assemble_with_ffmpeg([tmp_path / "fake.mp4"], tmp_path / "out.mp4")
            # ffmpeg will fail on empty file — that's expected

        assert any("AME not available" in r.message for r in caplog.records), (
            "Expected explicit AME-absent WARNING log from assemble_with_ffmpeg"
        )

    def test_me_adapter_job_spec_is_json_serialisable(self, tmp_path: Path) -> None:
        from melosviz.render.mediaencoder_adapter import build_ame_job_spec

        job = build_ame_job_spec(_minimal_spec(), [tmp_path / "s.mp4"])
        assert json.dumps(job)

    def test_me_adapter_scene_type(self) -> None:
        from melosviz.render.mediaencoder_adapter import MEAdapter

        assert MEAdapter.scene_type == "assembly_encode"


# ---------------------------------------------------------------------------
# (e) Explicit error when spec can't be built
# ---------------------------------------------------------------------------


class TestExplicitErrors:
    def test_ae_spec_error_on_missing_duration(self) -> None:
        from melosviz.analysis.models import RenderSpec
        from melosviz.render.aftereffects_adapter import AESpecError, build_ae_job_spec

        spec = RenderSpec(metadata={"fps": 30}, palette=[])  # no duration
        with pytest.raises(AESpecError, match="duration"):
            build_ae_job_spec(spec)

    def test_me_spec_error_on_none_segment_paths(self) -> None:
        from melosviz.render.mediaencoder_adapter import MESpecError, build_ame_job_spec

        with pytest.raises((MESpecError, TypeError)):
            build_ame_job_spec(_minimal_spec(), None)  # type: ignore[arg-type]

    def test_firefly_spec_error_on_missing_duration(self) -> None:
        from melosviz.analysis.models import RenderSpec
        from melosviz.render.firefly_adapter import (
            FireflySpecError,
            build_firefly_job_specs,
        )

        spec = RenderSpec(metadata={"fps": 30}, palette=[])
        with pytest.raises(FireflySpecError, match="duration"):
            build_firefly_job_specs(spec)

    def test_conductor_error_on_unknown_scene_type(self, tmp_path: Path) -> None:
        from melosviz.conductor.orchestrator import ConductorError, Orchestrator

        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
        with pytest.raises(ConductorError, match="no adapter registered"):
            orch.render(_minimal_spec(), scene_types=["nonexistent_scene_type"])


# ---------------------------------------------------------------------------
# (f) FireflyAdapter: per-segment job specs with prompt/mood mapping
# ---------------------------------------------------------------------------


class TestFireflyAdapter:
    def test_build_firefly_job_specs_returns_list(self) -> None:
        from melosviz.render.firefly_adapter import build_firefly_job_specs

        specs = build_firefly_job_specs(_minimal_spec())
        assert isinstance(specs, list)
        assert len(specs) == 2  # 2 segments in _minimal_spec

    def test_each_spec_has_required_keys(self) -> None:
        from melosviz.render.firefly_adapter import build_firefly_job_specs

        specs = build_firefly_job_specs(_minimal_spec())
        for spec in specs:
            for k in ("firefly_schema", "prompt", "negative_prompt", "n", "size",
                      "styles", "seed", "content_class", "melosviz_meta"):
                assert k in spec, f"Missing key {k!r} in Firefly spec"

    def test_prompt_contains_segment_label(self) -> None:
        from melosviz.render.firefly_adapter import build_firefly_job_specs

        specs = build_firefly_job_specs(_minimal_spec())
        intro_spec = next(s for s in specs if s["melosviz_meta"]["segment_label"] == "intro")
        assert "intro" in intro_spec["prompt"].lower()

    def test_prompt_contains_mood_descriptor(self) -> None:
        from melosviz.render.firefly_adapter import build_firefly_job_specs

        specs = build_firefly_job_specs(_minimal_spec())
        drop_spec = next(s for s in specs if s["melosviz_meta"]["segment_label"] == "drop")
        # drop has arousal=0.95 → should include energetic/vibrant descriptor
        assert any(word in drop_spec["prompt"].lower()
                   for word in ("energetic", "vibrant", "intense"))

    def test_styles_match_segment_label(self) -> None:
        from melosviz.render.firefly_adapter import build_firefly_job_specs

        specs = build_firefly_job_specs(_minimal_spec())
        drop_spec = next(s for s in specs if s["melosviz_meta"]["segment_label"] == "drop")
        assert "synthwave" in drop_spec["styles"]

    def test_each_spec_has_unique_seed(self) -> None:
        from melosviz.render.firefly_adapter import build_firefly_job_specs

        specs = build_firefly_job_specs(_minimal_spec())
        seeds = [s["seed"] for s in specs]
        assert len(seeds) == len(set(seeds)), "Seeds must be unique per segment"

    def test_output_key_in_meta(self) -> None:
        from melosviz.render.firefly_adapter import build_firefly_job_specs

        specs = build_firefly_job_specs(_minimal_spec())
        for spec in specs:
            meta = spec["melosviz_meta"]
            assert meta["output_key"].endswith(".png")

    def test_firefly_adapter_render_writes_file(self, tmp_path: Path) -> None:
        from melosviz.render.firefly_adapter import FireflyAdapter

        adapter = FireflyAdapter()
        result = adapter.render(_minimal_spec(), output_path=tmp_path)
        assert result.job_specs_path is not None
        assert Path(result.job_specs_path).exists()
        loaded = json.loads(Path(result.job_specs_path).read_text())
        assert isinstance(loaded, list)
        assert len(loaded) == 2

    def test_force_video_export_fallback_is_explicit(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """force_video_export=True must log a WARNING — never silent.

        We mock the low-level video export so the test only verifies the
        warning/flag behaviour, not ffmpeg binary availability or output format
        compatibility (those are tested separately in test_video_exporter.py).
        """
        import logging
        from unittest.mock import patch

        from melosviz.render.firefly_adapter import FireflyAdapter

        # Stub out the underlying export_video so no subprocess is spawned.

        stub_out = tmp_path / "stub.mp4"
        stub_out.touch()

        with patch(
            "melosviz.render.video_exporter.export_video",
            return_value=stub_out,
        ):
            adapter = FireflyAdapter()
            with caplog.at_level(logging.WARNING, logger="melosviz.render.firefly_adapter"):
                result = adapter.render(
                    _minimal_spec(), output_path=tmp_path, force_video_export=True
                )

        assert result.used_video_export_fallback is True
        assert any("force_video_export" in r.message for r in caplog.records)

    def test_empty_segments_returns_empty_list(self) -> None:
        from melosviz.render.firefly_adapter import build_firefly_job_specs

        spec = _minimal_spec(with_segments=False)
        specs = build_firefly_job_specs(spec)
        assert specs == []

    def test_firefly_adapter_scene_type(self) -> None:
        from melosviz.render.firefly_adapter import FireflyAdapter

        assert FireflyAdapter.scene_type == "generative_asset"


# ---------------------------------------------------------------------------
# (g) Orchestrator dispatches adapters + runs assembly
# ---------------------------------------------------------------------------


class TestOrchestrator:
    def test_orchestrator_instantiates(self, tmp_path: Path) -> None:
        from melosviz.conductor.orchestrator import Orchestrator

        orch = Orchestrator(output_dir=tmp_path)
        assert orch is not None

    def test_orchestrator_render_with_explicit_scene_types(self, tmp_path: Path) -> None:
        from melosviz.conductor.orchestrator import Orchestrator

        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
        result = orch.render(
            _minimal_spec(),
            scene_types=["motion_graphics_beat_sync"],
        )
        assert "motion_graphics_beat_sync" in result.per_scene_results

    def test_orchestrator_assembly_result_present_when_not_skipped(self, tmp_path: Path) -> None:
        from melosviz.conductor.orchestrator import Orchestrator

        orch = Orchestrator(output_dir=tmp_path, skip_assembly=False)
        result = orch.render(
            _minimal_spec(),
            scene_types=["motion_graphics_beat_sync"],
            segment_paths=[],
        )
        assert result.assembly_result is not None

    def test_orchestrator_assembly_skipped_when_flag_set(self, tmp_path: Path) -> None:
        from melosviz.conductor.orchestrator import Orchestrator

        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
        result = orch.render(
            _minimal_spec(),
            scene_types=["generative_asset"],
        )
        assert result.assembly_result is None

    def test_orchestrator_creates_output_dirs(self, tmp_path: Path) -> None:
        from melosviz.conductor.orchestrator import Orchestrator

        out = tmp_path / "conductor_out"
        orch = Orchestrator(output_dir=out, skip_assembly=True)
        orch.render(_minimal_spec(), scene_types=["motion_graphics_beat_sync"])
        assert (out / "motion_graphics_beat_sync").is_dir()


# ---------------------------------------------------------------------------
# (h) Registry covers all GOLD/SILVER scene types
# ---------------------------------------------------------------------------


class TestRegistryCoverage:
    def test_all_required_scene_types_registered(self) -> None:
        from melosviz.conductor.registry import ADAPTER_REGISTRY

        required = {
            "generative_asset",
            "motion_graphics_beat_sync",
            "assembly_encode",
            "procedural_3d_animation",
            "live_stage",
            "video_export",
        }
        registered = set(ADAPTER_REGISTRY.keys())
        missing = required - registered
        assert not missing, f"Missing scene types in registry: {missing}"

    def test_each_adapter_has_scene_type_attribute(self) -> None:
        from melosviz.conductor.registry import ADAPTER_REGISTRY

        # Only check the adapters we've written (not shims that need runtime deps)
        for scene_type in ("motion_graphics_beat_sync", "assembly_encode", "generative_asset"):
            adapter_cls = ADAPTER_REGISTRY[scene_type]
            inst = adapter_cls()
            assert hasattr(inst, "scene_type"), (
                f"{scene_type} adapter missing scene_type attribute"
            )
            assert inst.scene_type == scene_type or adapter_cls.scene_type == scene_type

    def test_live_stage_adapter_wired(self) -> None:
        from melosviz.conductor.registry import ADAPTER_REGISTRY

        assert "live_stage" in ADAPTER_REGISTRY
        adapter_cls = ADAPTER_REGISTRY["live_stage"]
        inst = adapter_cls()
        assert inst is not None
