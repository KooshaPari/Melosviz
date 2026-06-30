"""P8 advanced scene tests — TDD suite.

Tests for:
  1. SplatAssetSpec round-trips (Pydantic v2) + Blender wiring references asset.
  2. SemanticScannerSpec + semantic target-rule evaluation
     (vocals→performer-silhouette reveal, hat-onset→reflective boost).
  3. Procedural camera path generation aligned to segments/arc.
  4. Integration: camera + semantic scanner compose without breaking flash-safety.
  5. No regressions against P4 scanner/blender_scene tests.

All imports must succeed BEFORE any implementation exists — tests fail red first.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# 1. SplatAssetSpec — model round-trip + Blender wiring reference
# ---------------------------------------------------------------------------


class TestSplatAssetSpec:
    """SplatAssetSpec: first-class 3DGS / radiance-field representation."""

    def test_minimal_construction(self) -> None:
        from melosviz.scene.models import SplatAssetSpec

        spec = SplatAssetSpec(asset_path="scene.ply")
        assert spec.asset_path == "scene.ply"

    def test_default_fields(self) -> None:
        from melosviz.scene.models import SplatAssetSpec

        spec = SplatAssetSpec(asset_path="env.splat")
        assert spec.format in ("ply", "splat")
        # max_splats must be a positive int
        assert spec.max_splats > 0
        # sh_degree must be non-negative
        assert spec.sh_degree >= 0
        # opacity_threshold in [0, 1]
        assert 0.0 <= spec.opacity_threshold <= 1.0

    def test_full_round_trip(self) -> None:
        from melosviz.scene.models import SplatAssetSpec

        spec = SplatAssetSpec(
            asset_path="club.ply",
            format="ply",
            max_splats=500_000,
            sh_degree=3,
            opacity_threshold=0.05,
            scale_modifier=1.5,
            runtime_params={"sort_method": "depth", "tile_size": 16},
        )
        dumped = spec.model_dump()
        restored = SplatAssetSpec.model_validate(dumped)
        assert restored.asset_path == "club.ply"
        assert restored.format == "ply"
        assert restored.max_splats == 500_000
        assert restored.sh_degree == 3
        assert abs(restored.scale_modifier - 1.5) < 1e-9
        assert restored.runtime_params["sort_method"] == "depth"

    def test_scene_asset_embeds_splat_spec(self) -> None:
        from melosviz.scene.models import SceneAsset, SplatAssetSpec

        splat = SplatAssetSpec(asset_path="env.ply")
        asset = SceneAsset(
            asset_id="env_360",
            label="Club 360",
            splat_spec=splat,
        )
        assert asset.splat_spec is not None
        assert asset.splat_spec.asset_path == "env.ply"

    def test_blender_snippet_references_ply_path(self) -> None:
        """The bpy snippet emitted for the splat domain must reference the .ply path."""
        from melosviz.scene.models import SplatAssetSpec
        from melosviz.scene.blender_scene import build_splat_bpy_snippet

        spec = SplatAssetSpec(asset_path="/data/scene/club.ply", max_splats=200_000)
        snippet = build_splat_bpy_snippet(spec)

        assert "/data/scene/club.ply" in snippet
        assert "splat" in snippet.lower() or "ply" in snippet.lower()
        assert "200000" in snippet or "200_000" in snippet or "max_splats" in snippet

    def test_future_extension_note_in_model(self) -> None:
        """SplatAssetSpec must note 3DGUT / secondary-rays as a future extension."""
        from melosviz.scene.models import SplatAssetSpec

        doc = SplatAssetSpec.__doc__ or ""
        assert "3DGUT" in doc or "secondary" in doc.lower()


# ---------------------------------------------------------------------------
# 2. SemanticScannerSpec + target-rule evaluation
# ---------------------------------------------------------------------------


class TestSemanticScanner:
    """SemanticScannerSpec with per-condition semantic targeting rules."""

    def test_semantic_label_enum_coverage(self) -> None:
        from melosviz.scene.models import SemanticLabel

        values = {e.value for e in SemanticLabel}
        assert "wall" in values
        assert "performer" in values
        assert "reflective" in values

    def test_minimal_target_rule(self) -> None:
        from melosviz.scene.models import SemanticTargetRule, SemanticLabel

        rule = SemanticTargetRule(
            when_stem="vocals",
            prefer=SemanticLabel.PERFORMER,
            effect_channel="reveal_performer",
        )
        assert rule.when_stem == "vocals"
        assert rule.prefer == SemanticLabel.PERFORMER
        assert rule.effect_channel == "reveal_performer"

    def test_target_rule_with_onset_condition(self) -> None:
        from melosviz.scene.models import SemanticTargetRule, SemanticLabel

        rule = SemanticTargetRule(
            when_onset="hat",
            prefer=SemanticLabel.REFLECTIVE,
            effect_channel="boost_reflective",
            effect_gain=1.8,
        )
        assert rule.when_onset == "hat"
        assert rule.prefer == SemanticLabel.REFLECTIVE

    def test_semantic_scanner_spec_construction(self) -> None:
        from melosviz.scene.models import (
            SemanticScannerSpec,
            SemanticTargetRule,
            SemanticLabel,
        )

        spec = SemanticScannerSpec(
            scanner_id="semantic_main",
            target_rules=[
                SemanticTargetRule(
                    when_stem="vocals",
                    prefer=SemanticLabel.PERFORMER,
                    effect_channel="reveal_performer",
                ),
                SemanticTargetRule(
                    when_onset="hat",
                    prefer=SemanticLabel.REFLECTIVE,
                    effect_channel="boost_reflective",
                ),
            ],
        )
        assert len(spec.target_rules) == 2
        assert spec.target_rules[0].prefer == SemanticLabel.PERFORMER

    def test_vocals_rule_fires_on_vocals_stem(self) -> None:
        """When vocal stem energy is high, performer-silhouette reveal fires."""
        from melosviz.scene.scanner import evaluate_semantic_rules
        from melosviz.scene.models import (
            SemanticTargetRule,
            SemanticLabel,
            SemanticScannerSpec,
        )

        spec = SemanticScannerSpec(
            target_rules=[
                SemanticTargetRule(
                    when_stem="vocals",
                    prefer=SemanticLabel.PERFORMER,
                    effect_channel="reveal_performer",
                    stem_threshold=0.3,
                ),
            ]
        )

        audio_ctx = {
            "stems": {"vocals": 0.75, "drums": 0.2, "bass": 0.1, "other": 0.05},
            "onsets": {},
        }
        channels = evaluate_semantic_rules(spec, audio_ctx, base_cone_influence=0.6)
        assert "reveal_performer" in channels
        assert channels["reveal_performer"] > 0.0

    def test_vocals_rule_suppressed_on_low_vocals(self) -> None:
        from melosviz.scene.scanner import evaluate_semantic_rules
        from melosviz.scene.models import (
            SemanticTargetRule,
            SemanticLabel,
            SemanticScannerSpec,
        )

        spec = SemanticScannerSpec(
            target_rules=[
                SemanticTargetRule(
                    when_stem="vocals",
                    prefer=SemanticLabel.PERFORMER,
                    effect_channel="reveal_performer",
                    stem_threshold=0.3,
                ),
            ]
        )

        # vocals = 0.1 — below threshold
        audio_ctx = {
            "stems": {"vocals": 0.1, "drums": 0.8},
            "onsets": {},
        }
        channels = evaluate_semantic_rules(spec, audio_ctx, base_cone_influence=0.6)
        # Rule should not fire — channel absent or zero
        assert channels.get("reveal_performer", 0.0) == pytest.approx(0.0)

    def test_hat_onset_rule_fires(self) -> None:
        """Hi-hat onset produces reflective-material boost."""
        from melosviz.scene.scanner import evaluate_semantic_rules
        from melosviz.scene.models import (
            SemanticTargetRule,
            SemanticLabel,
            SemanticScannerSpec,
        )

        spec = SemanticScannerSpec(
            target_rules=[
                SemanticTargetRule(
                    when_onset="hat",
                    prefer=SemanticLabel.REFLECTIVE,
                    effect_channel="boost_reflective",
                    effect_gain=1.8,
                ),
            ]
        )

        audio_ctx = {
            "stems": {},
            "onsets": {"hat": 0.9, "kick": 0.0},
        }
        channels = evaluate_semantic_rules(spec, audio_ctx, base_cone_influence=0.5)
        assert channels.get("boost_reflective", 0.0) > 0.0

    def test_hat_onset_rule_suppressed_when_no_onset(self) -> None:
        from melosviz.scene.scanner import evaluate_semantic_rules
        from melosviz.scene.models import (
            SemanticTargetRule,
            SemanticLabel,
            SemanticScannerSpec,
        )

        spec = SemanticScannerSpec(
            target_rules=[
                SemanticTargetRule(
                    when_onset="hat",
                    prefer=SemanticLabel.REFLECTIVE,
                    effect_channel="boost_reflective",
                    onset_threshold=0.5,
                ),
            ]
        )

        audio_ctx = {
            "stems": {},
            "onsets": {"hat": 0.1},
        }
        channels = evaluate_semantic_rules(spec, audio_ctx, base_cone_influence=0.5)
        assert channels.get("boost_reflective", 0.0) == pytest.approx(0.0)

    def test_wall_default_rule(self) -> None:
        """Wall-preference rule: fires when neither vocals nor strong onset present."""
        from melosviz.scene.scanner import evaluate_semantic_rules
        from melosviz.scene.models import (
            SemanticTargetRule,
            SemanticLabel,
            SemanticScannerSpec,
        )

        spec = SemanticScannerSpec(
            target_rules=[
                SemanticTargetRule(
                    prefer=SemanticLabel.WALL,
                    effect_channel="hit_wall",
                ),
            ]
        )

        audio_ctx = {
            "stems": {"vocals": 0.0, "drums": 0.0},
            "onsets": {},
        }
        channels = evaluate_semantic_rules(spec, audio_ctx, base_cone_influence=0.7)
        assert channels.get("hit_wall", 0.0) > 0.0

    def test_multiple_rules_can_fire_simultaneously(self) -> None:
        from melosviz.scene.scanner import evaluate_semantic_rules
        from melosviz.scene.models import (
            SemanticTargetRule,
            SemanticLabel,
            SemanticScannerSpec,
        )

        spec = SemanticScannerSpec(
            target_rules=[
                SemanticTargetRule(
                    when_stem="vocals",
                    prefer=SemanticLabel.PERFORMER,
                    effect_channel="reveal_performer",
                    stem_threshold=0.3,
                ),
                SemanticTargetRule(
                    when_onset="hat",
                    prefer=SemanticLabel.REFLECTIVE,
                    effect_channel="boost_reflective",
                    onset_threshold=0.3,
                ),
            ]
        )

        audio_ctx = {
            "stems": {"vocals": 0.9},
            "onsets": {"hat": 0.8},
        }
        channels = evaluate_semantic_rules(spec, audio_ctx, base_cone_influence=0.6)
        assert channels.get("reveal_performer", 0.0) > 0.0
        assert channels.get("boost_reflective", 0.0) > 0.0

    def test_effect_gain_scales_channel(self) -> None:
        from melosviz.scene.scanner import evaluate_semantic_rules
        from melosviz.scene.models import (
            SemanticTargetRule,
            SemanticLabel,
            SemanticScannerSpec,
        )

        spec_low = SemanticScannerSpec(
            target_rules=[
                SemanticTargetRule(
                    when_onset="hat",
                    prefer=SemanticLabel.REFLECTIVE,
                    effect_channel="boost_reflective",
                    effect_gain=1.0,
                ),
            ]
        )
        spec_high = SemanticScannerSpec(
            target_rules=[
                SemanticTargetRule(
                    when_onset="hat",
                    prefer=SemanticLabel.REFLECTIVE,
                    effect_channel="boost_reflective",
                    effect_gain=2.0,
                ),
            ]
        )

        audio_ctx = {"stems": {}, "onsets": {"hat": 0.7}}
        ch_low = evaluate_semantic_rules(spec_low, audio_ctx, base_cone_influence=0.5)
        ch_high = evaluate_semantic_rules(spec_high, audio_ctx, base_cone_influence=0.5)
        assert ch_high.get("boost_reflective", 0.0) > ch_low.get("boost_reflective", 0.0)


# ---------------------------------------------------------------------------
# 3. Procedural camera — path generation
# ---------------------------------------------------------------------------


class TestProceduralCamera:
    """camera.py: ProceduralCameraSpec + generate_camera_path()."""

    def test_camera_keyframe_fields(self) -> None:
        from melosviz.scene.camera import CameraKeyframe

        kf = CameraKeyframe(
            t=0.0,
            position=(0.0, -8.0, 2.0),
            look_at=(0.0, 0.0, 1.0),
            fov_deg=60.0,
            camera_language="slow_reveal",
        )
        assert kf.t == 0.0
        assert kf.fov_deg == pytest.approx(60.0)
        assert kf.camera_language == "slow_reveal"

    def test_generate_camera_path_returns_list(self) -> None:
        from melosviz.scene.camera import generate_camera_path

        segments = [
            {"label": "intro", "start": 0.0, "end": 10.0, "mood": "chill", "dominant_stem": "other"},
            {"label": "drop", "start": 10.0, "end": 25.0, "mood": "intense", "dominant_stem": "drums"},
        ]
        path = generate_camera_path(segments, duration=25.0)
        assert isinstance(path, list)
        assert len(path) >= len(segments)

    def test_path_starts_at_t0(self) -> None:
        from melosviz.scene.camera import generate_camera_path

        segments = [
            {"label": "intro", "start": 0.0, "end": 15.0, "mood": "chill", "dominant_stem": "other"},
        ]
        path = generate_camera_path(segments, duration=15.0)
        assert path[0].t == pytest.approx(0.0, abs=1e-3)

    def test_camera_language_maps_to_intensity(self) -> None:
        """High-energy sections (drop) get cut_frenzy or handheld_push; intros get slow_reveal."""
        from melosviz.scene.camera import generate_camera_path, CAMERA_LANGUAGE_MAP

        # Verify the vocabulary map exists and has the 4 P7 quartile languages
        assert "slow_reveal" in CAMERA_LANGUAGE_MAP
        assert "steady_cam" in CAMERA_LANGUAGE_MAP
        assert "handheld_push" in CAMERA_LANGUAGE_MAP
        assert "cut_frenzy" in CAMERA_LANGUAGE_MAP

    def test_drop_segment_uses_energetic_camera(self) -> None:
        from melosviz.scene.camera import generate_camera_path

        segments = [
            {"label": "drop", "start": 0.0, "end": 10.0, "mood": "intense", "dominant_stem": "drums",
             "energy_mean": 0.9},
        ]
        path = generate_camera_path(segments, duration=10.0)
        # The drop should produce cut_frenzy or handheld_push
        langs = {kf.camera_language for kf in path}
        energetic = {"cut_frenzy", "handheld_push"}
        assert langs & energetic, f"Expected energetic camera for drop, got {langs}"

    def test_intro_segment_uses_slow_reveal(self) -> None:
        from melosviz.scene.camera import generate_camera_path

        segments = [
            {"label": "intro", "start": 0.0, "end": 10.0, "mood": "chill", "dominant_stem": "other",
             "energy_mean": 0.1},
        ]
        path = generate_camera_path(segments, duration=10.0)
        langs = {kf.camera_language for kf in path}
        assert "slow_reveal" in langs

    def test_path_is_temporally_ordered(self) -> None:
        from melosviz.scene.camera import generate_camera_path

        segments = [
            {"label": "intro", "start": 0.0, "end": 8.0, "mood": "chill", "dominant_stem": "other"},
            {"label": "build", "start": 8.0, "end": 16.0, "mood": "building", "dominant_stem": "bass"},
            {"label": "drop", "start": 16.0, "end": 30.0, "mood": "intense", "dominant_stem": "drums"},
        ]
        path = generate_camera_path(segments, duration=30.0)
        times = [kf.t for kf in path]
        assert times == sorted(times)

    def test_camera_positions_are_3d_tuples(self) -> None:
        from melosviz.scene.camera import generate_camera_path

        segments = [
            {"label": "intro", "start": 0.0, "end": 5.0, "mood": "chill", "dominant_stem": "other"},
        ]
        path = generate_camera_path(segments, duration=5.0)
        for kf in path:
            assert len(kf.position) == 3
            assert len(kf.look_at) == 3

    def test_fov_stays_in_valid_range(self) -> None:
        from melosviz.scene.camera import generate_camera_path

        segments = [
            {"label": "drop", "start": 0.0, "end": 20.0, "mood": "intense", "dominant_stem": "drums",
             "energy_mean": 0.95},
        ]
        path = generate_camera_path(segments, duration=20.0)
        for kf in path:
            assert 10.0 <= kf.fov_deg <= 120.0

    def test_with_render_spec_arc(self) -> None:
        """generate_camera_path accepts an optional render_spec for arc context."""
        from melosviz.scene.camera import generate_camera_path

        class _FakeSpec:
            metadata = {"estimated_bpm": 128.0, "duration": 20.0}
            scene_segments = [
                type("S", (), {"label": "drop", "start": 0.0, "end": 20.0,
                               "mood": "intense", "dominant_stem": "drums",
                               "energy_mean": 0.9})()
            ]

        segments = [
            {"label": "drop", "start": 0.0, "end": 20.0, "mood": "intense",
             "dominant_stem": "drums", "energy_mean": 0.9},
        ]
        path = generate_camera_path(segments, duration=20.0, render_spec=_FakeSpec())
        assert len(path) >= 1


# ---------------------------------------------------------------------------
# 4. Integration — no flash-safety regression + e2e compose
# ---------------------------------------------------------------------------


class TestP8Integration:
    """Integration: semantic scanner + camera output composes without flash-safety violations."""

    def _make_minimal_render_spec(self) -> Any:
        """Return a minimal RenderSpec-like object for integration tests."""
        class FakeSpec:
            metadata = {
                "estimated_bpm": 128.0,
                "duration": 10.0,
                "fps": 30,
            }
            timeline_events = [
                {"t": 0.0, "type": "beat"},
                {"t": 0.47, "type": "beat"},
                {"t": 0.94, "type": "beat"},
                {"t": 1.41, "type": "beat"},
            ]
            dense_keyframes = [{"t": i / 30.0} for i in range(30 * 3)]  # 3s
            scene_segments = [
                {"label": "intro", "start": 0.0, "end": 1.5, "mood": "chill",
                 "dominant_stem": "other", "energy_mean": 0.2},
                {"label": "drop", "start": 1.5, "end": 3.0, "mood": "intense",
                 "dominant_stem": "drums", "energy_mean": 0.9},
            ]

        return FakeSpec()

    def test_semantic_rules_do_not_break_blender_scene(self) -> None:
        """assemble_multi_domain_scene still works when semantic scanner is present."""
        from melosviz.scene.models import (
            ScannerSpec,
            SceneSpec,
            TransitionSpec,
            MaterialSpec,
            Domain,
            DomainOpacityRule,
        )
        from melosviz.scene.blender_scene import assemble_multi_domain_scene

        scanner = ScannerSpec()
        scene = SceneSpec()
        transitions = [
            TransitionSpec(
                opacity_rules=[
                    DomainOpacityRule(domain=Domain.PHOTO, channel="reveal_splat", base=1.0, scale=-1.0),
                    DomainOpacityRule(domain=Domain.SPLAT, channel="reveal_splat", base=0.0, scale=1.0),
                ]
            )
        ]
        materials = [MaterialSpec(domain=Domain.PHOTO), MaterialSpec(domain=Domain.MESH)]

        assemblies = assemble_multi_domain_scene(
            scanner, scene, transitions, materials, self._make_minimal_render_spec()
        )
        assert len(assemblies) > 0

    def test_flash_safety_holds_with_semantic_scanner(self) -> None:
        """Opacity changes between consecutive frames must not exceed flash-safety threshold."""
        from melosviz.scene.models import (
            ScannerSpec,
            SceneSpec,
            TransitionSpec,
            MaterialSpec,
            Domain,
            DomainOpacityRule,
        )
        from melosviz.scene.blender_scene import assemble_multi_domain_scene
        from melosviz.render.blender_exporter import FLASH_SAFETY_MAX_HZ

        scanner = ScannerSpec()
        scene = SceneSpec()
        transitions = [
            TransitionSpec(
                opacity_rules=[
                    DomainOpacityRule(domain=Domain.PHOTO, channel="reveal_splat", base=1.0, scale=-1.0),
                    DomainOpacityRule(domain=Domain.SPLAT, channel="reveal_splat", base=0.0, scale=1.0),
                ]
            )
        ]
        materials = [MaterialSpec(domain=Domain.PHOTO), MaterialSpec(domain=Domain.MESH)]
        fps = 30
        assemblies = assemble_multi_domain_scene(
            scanner, scene, transitions, materials, self._make_minimal_render_spec(), fps=fps
        )

        # Count rapid polarity changes (dark→bright→dark) in photo opacity
        photo_opacities = [a.opacities.get(Domain.PHOTO, 0.0) for a in assemblies]
        # A simple flash counter: count full cycles (rise > 0.2 then fall > 0.2) per second
        # Limit is FLASH_SAFETY_MAX_HZ full cycles/second
        transitions_count = 0
        for i in range(1, len(photo_opacities)):
            if abs(photo_opacities[i] - photo_opacities[i - 1]) > 0.4:
                transitions_count += 1
        duration_secs = len(assemblies) / fps
        flash_hz = transitions_count / (2.0 * max(duration_secs, 1.0))  # transitions/2 = cycles
        assert flash_hz <= FLASH_SAFETY_MAX_HZ + 0.5  # 0.5 tolerance for test discretisation

    def test_camera_path_integrates_with_compose_pipeline(self) -> None:
        """generate_camera_path produces keyframes usable in the compose assembler."""
        from melosviz.scene.camera import generate_camera_path

        spec = self._make_minimal_render_spec()
        segments = [
            {"label": s["label"], "start": s["start"], "end": s["end"],
             "mood": s["mood"], "dominant_stem": s["dominant_stem"]}
            for s in spec.scene_segments
        ]
        path = generate_camera_path(segments, duration=3.0)
        assert len(path) >= 2
        # All t values within duration
        for kf in path:
            assert kf.t <= 3.0 + 1e-6

    def test_blender_snippet_for_splat_embeds_in_hybrid_scene(self) -> None:
        """build_splat_bpy_snippet output can be appended to the P4 hybrid bpy script."""
        from melosviz.scene.models import SplatAssetSpec
        from melosviz.scene.blender_scene import build_splat_bpy_snippet, build_hybrid_bpy_segment
        from melosviz.scene.models import (
            ScannerSpec, SceneSpec, TransitionSpec, MaterialSpec, Domain, DomainOpacityRule
        )

        splat_spec = SplatAssetSpec(asset_path="/data/club.ply")
        splat_snippet = build_splat_bpy_snippet(splat_spec)

        # Build a minimal set of assemblies
        scanner = ScannerSpec()
        scene = SceneSpec()
        transitions = [
            TransitionSpec(
                opacity_rules=[
                    DomainOpacityRule(domain=Domain.SPLAT, channel="reveal_splat", base=0.0, scale=1.0),
                ]
            )
        ]
        materials = [MaterialSpec(domain=Domain.SPLAT)]

        from melosviz.scene.blender_scene import assemble_multi_domain_scene
        assemblies = assemble_multi_domain_scene(
            scanner, scene, transitions, materials, self._make_minimal_render_spec()
        )
        hybrid_snippet = build_hybrid_bpy_segment(assemblies)

        # Both are valid non-empty Python strings
        assert isinstance(splat_snippet, str) and len(splat_snippet) > 10
        assert isinstance(hybrid_snippet, str) and len(hybrid_snippet) > 10
        # The splat snippet references the ply file
        assert "/data/club.ply" in splat_snippet


# ---------------------------------------------------------------------------
# 5. Regression — P4 scanner still works post-P8
# ---------------------------------------------------------------------------


class TestP4Regression:
    """Ensure P4 scanner evaluate_scanner / evaluate_pose still work unchanged."""

    def test_evaluate_pose_smoke(self) -> None:
        from melosviz.scene.scanner import evaluate_pose
        from melosviz.scene.models import ScannerSpec

        scanner = ScannerSpec()
        pose = evaluate_pose(scanner, t=1.0, bpm=128.0, beat_times=[0.47, 0.94, 1.41])
        assert 0.0 <= pose.orbit_angle_rad <= 2 * math.pi
        assert "reveal_splat" in pose.active_channels

    def test_evaluate_scanner_smoke(self) -> None:
        from melosviz.scene.scanner import evaluate_scanner
        from melosviz.scene.models import ScannerSpec

        class _RS:
            metadata = {"estimated_bpm": 128.0, "duration": 2.0, "fps": 30}
            timeline_events = [{"t": 0.0, "type": "beat"}, {"t": 0.47, "type": "beat"}]
            dense_keyframes = [{"t": i / 30.0} for i in range(60)]

        frames = evaluate_scanner(ScannerSpec(), _RS())
        assert len(frames) == 60
        for f in frames:
            assert "reveal_splat" in f.channels

    def test_blender_scene_assembly_smoke(self) -> None:
        from melosviz.scene.models import (
            ScannerSpec, SceneSpec, TransitionSpec, MaterialSpec, Domain, DomainOpacityRule
        )
        from melosviz.scene.blender_scene import assemble_multi_domain_scene

        class _RS:
            metadata = {"estimated_bpm": 128.0, "duration": 1.0, "fps": 30}
            timeline_events = [{"t": 0.0, "type": "beat"}]
            dense_keyframes = [{"t": i / 30.0} for i in range(30)]
            scene_segments: list = []

        assemblies = assemble_multi_domain_scene(
            ScannerSpec(),
            SceneSpec(),
            [TransitionSpec(opacity_rules=[
                DomainOpacityRule(domain=Domain.PHOTO, channel="reveal_splat", base=1.0, scale=-1.0),
            ])],
            [MaterialSpec(domain=Domain.PHOTO)],
            _RS(),
        )
        assert len(assemblies) == 30
