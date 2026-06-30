"""Tests for P4 hybrid-scene MVP.

TDD protocol:
- (a) ScannerSpec bpm-locked orbit produces expected pose at beat boundaries
- (b) Write-channel mask values respond to beats
- (c) Transition mappings resolve domain opacities correctly given mask values
- (d) Multi-domain scene assembly produces per-segment domain switches
- (e) Flash-safety still applied
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest

from melosviz.scene.blender_scene import (
    HybridDomainAssembly,
    assemble_multi_domain_scene,
    build_hybrid_bpy_segment,
)
from melosviz.scene.models import (
    ChannelCondition,
    Domain,
    DomainMaterialLook,
    DomainOpacityRule,
    FalloffType,
    MaterialSpec,
    ScannerNoise,
    ScannerRotation,
    ScannerSpec,
    ScannerType,
    SceneSpec,
    TransitionSpec,
)
from melosviz.scene.scanner import (
    _compute_orbit_angle,
    evaluate_pose,
)

# ---------------------------------------------------------------------------
# (a) BPM-locked orbit: correct pose at beat boundaries
# ---------------------------------------------------------------------------

class TestScannerOrbitBpmLocked:
    def _spec(self, beats_per_rotation: float = 4.0, phase_offset: float = 0.0) -> ScannerSpec:
        return ScannerSpec(
            scanner_id="test",
            type=ScannerType.ROTATING_CONE,
            rotation=ScannerRotation(
                bpm_locked=True,
                beats_per_rotation=beats_per_rotation,
                phase_offset=phase_offset,
            ),
            noise=ScannerNoise(edge_wobble=0.0, beat_pulse_gain=0.0),  # noise off for math
            write_channels=["reveal_splat"],
        )

    def test_at_t0_angle_is_phase_offset_only(self):
        angle, phase = _compute_orbit_angle(0.0, bpm=120.0, beats_per_rotation=4.0, phase_offset=0.0)
        assert angle == pytest.approx(0.0)
        assert phase == pytest.approx(0.0)

    def test_one_full_rotation_at_4_beats_120bpm(self):
        """At 120 BPM, 4 beats per rotation → rotation period = 2 s."""
        bpm = 120.0
        beats_per_rotation = 4.0
        seconds_per_beat = 60.0 / bpm  # 0.5 s
        period = beats_per_rotation * seconds_per_beat  # 2.0 s

        angle_0, phase_0 = _compute_orbit_angle(0.0, bpm, beats_per_rotation, 0.0)
        angle_period, phase_period = _compute_orbit_angle(period, bpm, beats_per_rotation, 0.0)

        # After one full period, phase should wrap back to 0
        assert phase_period == pytest.approx(0.0, abs=1e-9)
        assert angle_period == pytest.approx(0.0, abs=1e-9)

    def test_half_rotation_at_beat_2(self):
        """At 120 BPM, 4 bpr → half rotation at t=1.0 s (beat 2)."""
        bpm = 120.0
        beats_per_rotation = 4.0
        seconds_per_beat = 60.0 / bpm  # 0.5 s
        t_half = 2 * seconds_per_beat  # t = 1.0 s

        angle, phase = _compute_orbit_angle(t_half, bpm, beats_per_rotation, 0.0)
        assert phase == pytest.approx(0.5, abs=1e-9)
        assert angle == pytest.approx(math.pi, abs=1e-9)

    def test_phase_offset_shifts_starting_angle(self):
        angle, phase = _compute_orbit_angle(0.0, bpm=120.0, beats_per_rotation=4.0, phase_offset=0.25)
        assert phase == pytest.approx(0.25)
        assert angle == pytest.approx(0.25 * 2 * math.pi)

    def test_degeneracy_zero_bpm_returns_zero(self):
        angle, phase = _compute_orbit_angle(10.0, bpm=0.0, beats_per_rotation=4.0, phase_offset=0.0)
        assert angle == 0.0 and phase == 0.0


# ---------------------------------------------------------------------------
# (b) Write-channel mask values respond to beats
# ---------------------------------------------------------------------------

class TestScannerChannelValues:
    def _beat_list(self, bpm: float, n: int = 8) -> list[float]:
        spb = 60.0 / bpm
        return [i * spb for i in range(n)]

    def _spec_with_all_channels(self) -> ScannerSpec:
        return ScannerSpec(
            scanner_id="test",
            cone_angle_deg=60.0,  # wide cone so cone_raw > 0 at angle 0
            rotation=ScannerRotation(bpm_locked=True, beats_per_rotation=4.0, phase_offset=0.0),
            noise=ScannerNoise(edge_wobble=0.0, beat_pulse_gain=0.5),
            falloff=FalloffType.LINEAR,
            write_channels=["reveal_splat", "hide_photo", "boost_wireframe", "edge_emission"],
        )

    def test_channels_are_in_range(self):
        spec = self._spec_with_all_channels()
        beats = self._beat_list(120.0)
        pose = evaluate_pose(spec, t=0.0, bpm=120.0, beat_times=beats)
        for ch, val in pose.active_channels.items():
            assert 0.0 <= val <= 1.0, f"{ch}={val} out of [0,1]"

    def test_boost_wireframe_elevated_on_beat(self):
        """boost_wireframe should be elevated very close to a beat."""
        spec = self._spec_with_all_channels()
        bpm = 120.0
        beats = self._beat_list(bpm)
        # t=0 is exactly beat 0
        pose_on = evaluate_pose(spec, t=0.0, bpm=bpm, beat_times=beats)
        # t=0.499 is half-beat away (far from next beat)
        pose_off = evaluate_pose(spec, t=0.499, bpm=bpm, beat_times=beats)
        assert pose_on.active_channels["boost_wireframe"] > pose_off.active_channels["boost_wireframe"]

    def test_beat_proximity_is_one_at_exact_beat(self):
        spec = self._spec_with_all_channels()
        bpm = 120.0
        beats = self._beat_list(bpm)
        pose = evaluate_pose(spec, t=0.0, bpm=bpm, beat_times=beats)
        assert pose.beat_proximity == pytest.approx(1.0)

    def test_reveal_splat_positive_when_cone_covers_sample(self):
        """A wide cone (180°) at t=0 should have reveal_splat > 0."""
        spec = ScannerSpec(
            cone_angle_deg=180.0,
            rotation=ScannerRotation(bpm_locked=False),
            noise=ScannerNoise(edge_wobble=0.0, beat_pulse_gain=0.0),
            falloff=FalloffType.LINEAR,
            write_channels=["reveal_splat"],
        )
        pose = evaluate_pose(spec, t=0.0, bpm=120.0, beat_times=[])
        assert pose.active_channels["reveal_splat"] > 0.0

    def test_reveal_splat_zero_when_cone_misses(self):
        """A narrow cone pointing away (half-rotation later) misses the sample."""
        bpm = 120.0
        beats_per_rotation = 2.0
        # After half rotation the scanner axis = π rad away from sample at 0
        spb = 60.0 / bpm
        t_half = beats_per_rotation * spb * 0.5  # half rotation

        spec = ScannerSpec(
            cone_angle_deg=5.0,  # very narrow cone
            rotation=ScannerRotation(bpm_locked=True, beats_per_rotation=beats_per_rotation, phase_offset=0.0),
            noise=ScannerNoise(edge_wobble=0.0, beat_pulse_gain=0.0),
            falloff=FalloffType.LINEAR,
            write_channels=["reveal_splat"],
        )
        pose = evaluate_pose(spec, t=t_half, bpm=bpm, beat_times=[])
        assert pose.active_channels["reveal_splat"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# (c) Transition mappings resolve domain opacities given mask values
# ---------------------------------------------------------------------------

class TestTransitionMappings:
    def _make_transition(self) -> TransitionSpec:
        """reveal_splat > 0.5 → photo fades out, splat fades in."""
        return TransitionSpec(
            transition_id="splat_reveal",
            conditions=[ChannelCondition(channel="reveal_splat", threshold=0.5)],
            opacity_rules=[
                DomainOpacityRule(domain=Domain.PHOTO, channel="reveal_splat", base=1.0, scale=-1.0),
                DomainOpacityRule(domain=Domain.SPLAT, channel="reveal_splat", base=0.0, scale=1.0),
            ],
            fx_edge_channel="edge_emission",
            fx_edge_gain=1.4,
        )

    def test_conditions_active_above_threshold(self):
        tr = self._make_transition()
        assert tr.conditions_active({"reveal_splat": 0.6}) is True

    def test_conditions_inactive_below_threshold(self):
        tr = self._make_transition()
        assert tr.conditions_active({"reveal_splat": 0.4}) is False

    def test_photo_fades_as_splat_reveals(self):
        tr = self._make_transition()
        # At reveal_splat = 0.8: photo = 1 - 0.8 = 0.2, splat = 0.8
        opacities = tr.evaluate_opacities({"reveal_splat": 0.8})
        assert opacities[Domain.PHOTO] == pytest.approx(0.2)
        assert opacities[Domain.SPLAT] == pytest.approx(0.8)

    def test_opacity_clamped_to_0_1(self):
        tr = self._make_transition()
        # reveal_splat = 1.5 (out of range at channel level, but clamped by model)
        opacities = tr.evaluate_opacities({"reveal_splat": 1.5})
        for v in opacities.values():
            assert 0.0 <= v <= 1.0

    def test_missing_channel_defaults_to_zero(self):
        tr = self._make_transition()
        opacities = tr.evaluate_opacities({})  # no channels at all
        assert opacities[Domain.PHOTO] == pytest.approx(1.0)
        assert opacities[Domain.SPLAT] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# (d) Multi-domain scene assembly: per-segment domain switches
# ---------------------------------------------------------------------------

def _make_minimal_render_spec(
    bpm: float = 120.0,
    duration: float = 4.0,
    fps: int = 30,
    n_beats: int = 8,
    segments: list[dict] | None = None,
) -> MagicMock:
    """Build a minimal RenderSpec-like object for testing without librosa."""
    spb = 60.0 / bpm
    beats = [{"t": i * spb, "type": "beat"} for i in range(n_beats)]

    if segments is None:
        segments = [
            {"index": 0, "label": "intro", "start": 0.0, "end": 2.0,
             "energy_mean": 0.3, "brightness_mean": 0.4,
             "mood": {"valence": 0.5, "arousal": 0.4}, "dominant_stem": "other"},
            {"index": 1, "label": "drop", "start": 2.0, "end": 4.0,
             "energy_mean": 0.9, "brightness_mean": 0.8,
             "mood": {"valence": 0.7, "arousal": 0.9}, "dominant_stem": "drums"},
        ]

    # Dense keyframes at fps
    n_frames = int(duration * fps)
    dense_kf = [
        {
            "t": i / fps,
            "energy": 0.5 + 0.4 * math.sin(i / fps * 2 * math.pi / spb),
            "brightness": 0.5,
            "valence": 0.5,
            "arousal": 0.6,
            "beat_strength": 1.0 if i % round(fps * spb) == 0 else 0.0,
            "onset_strength": 0.3,
            "spectral_centroid": 3000.0,
            "stems": {"drums": 0.5, "bass": 0.3, "vocals": 0.2, "other": 0.2},
            "easing": "ease_in_out",
        }
        for i in range(n_frames)
    ]

    spec = MagicMock()
    spec.metadata = {
        "estimated_bpm": bpm,
        "duration": duration,
        "fps": fps,
        "source_audio": "test.wav",
    }
    spec.timeline_events = beats
    spec.scene_segments = segments
    spec.dense_keyframes = dense_kf
    return spec


class TestMultiDomainAssembly:
    def _make_scanner(self) -> ScannerSpec:
        return ScannerSpec(
            cone_angle_deg=60.0,
            rotation=ScannerRotation(bpm_locked=True, beats_per_rotation=2.0, phase_offset=0.0),
            noise=ScannerNoise(edge_wobble=0.0, beat_pulse_gain=0.2),
            falloff=FalloffType.SMOOTHSTEP,
            write_channels=["reveal_splat", "hide_photo", "boost_wireframe", "edge_emission"],
        )

    def _make_transitions(self) -> list[TransitionSpec]:
        return [
            TransitionSpec(
                transition_id="splat_reveal",
                conditions=[ChannelCondition(channel="reveal_splat", threshold=0.3)],
                opacity_rules=[
                    DomainOpacityRule(domain=Domain.PHOTO, channel="reveal_splat", base=1.0, scale=-1.0),
                    DomainOpacityRule(domain=Domain.SPLAT, channel="reveal_splat", base=0.0, scale=1.0),
                    DomainOpacityRule(domain=Domain.FX, channel="edge_emission", base=0.0, scale=1.0),
                ],
                fx_edge_gain=1.4,
            )
        ]

    def _make_materials(self) -> list[MaterialSpec]:
        return [
            MaterialSpec(domain=Domain.PHOTO, default_look=DomainMaterialLook.RAW, beat_pulse_look=DomainMaterialLook.HIGH_CONTRAST_MONO),
            MaterialSpec(domain=Domain.MESH, default_look=DomainMaterialLook.WIREFRAME_EMISSIVE),
            MaterialSpec(domain=Domain.SPLAT, default_look=DomainMaterialLook.MONO_CLOUD, drop_look=DomainMaterialLook.POINT_HALO),
            MaterialSpec(domain=Domain.PERFORMER, default_look=DomainMaterialLook.PHOTOREAL),
            MaterialSpec(domain=Domain.FX, default_look=DomainMaterialLook.EDGE_GLOW),
        ]

    def test_assembly_produces_one_entry_per_dense_keyframe(self):
        spec = _make_minimal_render_spec(fps=10, duration=2.0)
        scanner = self._make_scanner()
        assemblies = assemble_multi_domain_scene(
            scanner=scanner,
            scene_spec=SceneSpec(),
            transitions=self._make_transitions(),
            materials=self._make_materials(),
            render_spec=spec,
            fps=10,
        )
        assert len(assemblies) == 20  # 2s × 10 fps

    def test_all_domain_opacities_in_range(self):
        spec = _make_minimal_render_spec(fps=10, duration=2.0)
        scanner = self._make_scanner()
        assemblies = assemble_multi_domain_scene(
            scanner=scanner,
            scene_spec=SceneSpec(),
            transitions=self._make_transitions(),
            materials=self._make_materials(),
            render_spec=spec,
            fps=10,
        )
        for asm in assemblies:
            for domain, opacity in asm.opacities.items():
                assert 0.0 <= opacity <= 1.0, f"t={asm.t} domain={domain} opacity={opacity}"

    def test_scanner_angle_advances_over_time(self):
        spec = _make_minimal_render_spec(fps=10, duration=2.0)
        scanner = self._make_scanner()
        assemblies = assemble_multi_domain_scene(
            scanner=scanner,
            scene_spec=SceneSpec(),
            transitions=self._make_transitions(),
            materials=self._make_materials(),
            render_spec=spec,
            fps=10,
        )
        # Scanner angle at t=1.0 should differ from t=0.0
        a0 = assemblies[0].scanner_angle_rad
        a10 = assemblies[10].scanner_angle_rad  # t=1.0
        assert a0 != pytest.approx(a10), "Scanner should advance over time"

    def test_drop_segment_activates_drop_material(self):
        """In the drop segment (t=2..4), splat domain should use drop_look."""
        spec = _make_minimal_render_spec(fps=10, duration=4.0, n_beats=16)
        scanner = self._make_scanner()
        assemblies = assemble_multi_domain_scene(
            scanner=scanner,
            scene_spec=SceneSpec(),
            transitions=self._make_transitions(),
            materials=self._make_materials(),
            render_spec=spec,
            fps=10,
        )
        # Find frames in the drop segment (t >= 2.0)
        drop_frames = [a for a in assemblies if a.t >= 2.0]
        assert drop_frames, "Expected frames in drop segment"
        # At least some drop frames should use the drop_look for splat
        drop_looks = {a.material_looks.get(Domain.SPLAT) for a in drop_frames}
        assert DomainMaterialLook.POINT_HALO in drop_looks, (
            f"Expected POINT_HALO (drop_look) in splat looks during drop, got {drop_looks}"
        )

    def test_domain_switch_occurs_over_scene(self):
        """Photo and splat opacities should vary — not a static single value."""
        spec = _make_minimal_render_spec(fps=10, duration=4.0, n_beats=16)
        scanner = self._make_scanner()
        assemblies = assemble_multi_domain_scene(
            scanner=scanner,
            scene_spec=SceneSpec(),
            transitions=self._make_transitions(),
            materials=self._make_materials(),
            render_spec=spec,
            fps=10,
        )
        photo_values = {a.opacities[Domain.PHOTO] for a in assemblies}
        splat_values = {a.opacities[Domain.SPLAT] for a in assemblies}
        # More than one distinct opacity = switching is happening
        assert len(photo_values) > 1, "Photo domain should vary over time"
        assert len(splat_values) > 1, "Splat domain should vary over time"


# ---------------------------------------------------------------------------
# (e) Flash-safety still applied
# ---------------------------------------------------------------------------

class TestFlashSafetyInHybridScene:
    """The flash-safety post-pass should clamp large opacity spikes."""

    def test_flash_safety_limits_rapid_transitions(self):
        """Verify apply_flash_safety caps the transition rate to ≤ 3 Hz."""
        from melosviz.render.blender_exporter import (
            FLASH_SAFETY_MAX_HZ,
            apply_flash_safety,
        )

        fps = 30
        # Create an adversarial sequence: fully alternating 0.0 / 1.0 at 15 Hz
        seq = [float(i % 2) for i in range(fps * 4)]  # 4 s, flips at 15 Hz

        clamped = apply_flash_safety(seq, fps=fps, max_hz=FLASH_SAFETY_MAX_HZ)

        # Count transitions (abs delta > 0.5) in the clamped sequence
        transitions = sum(
            1 for a, b in zip(clamped, clamped[1:], strict=False) if abs(b - a) > 0.5
        )
        max_allowed = FLASH_SAFETY_MAX_HZ * (len(clamped) / fps)
        assert transitions <= max_allowed, (
            f"Flash safety failed: {transitions} transitions > {max_allowed} allowed"
        )

    def test_hybrid_assembly_passes_flash_safe_opacities(self):
        """assemble_multi_domain_scene must not produce rapid large opacity swings."""
        fps = 30
        # Artificially high beat_pulse_gain to stress the safety net
        scanner = ScannerSpec(
            cone_angle_deg=120.0,
            rotation=ScannerRotation(bpm_locked=True, beats_per_rotation=0.5),  # very fast
            noise=ScannerNoise(edge_wobble=0.0, beat_pulse_gain=2.0),
            falloff=FalloffType.LINEAR,
            write_channels=["reveal_splat", "hide_photo", "edge_emission"],
        )
        transitions = [
            TransitionSpec(
                opacity_rules=[
                    DomainOpacityRule(domain=Domain.PHOTO, channel="reveal_splat", base=1.0, scale=-1.0),
                    DomainOpacityRule(domain=Domain.SPLAT, channel="reveal_splat", base=0.0, scale=1.0),
                ],
            )
        ]
        materials = [
            MaterialSpec(domain=Domain.PHOTO),
            MaterialSpec(domain=Domain.SPLAT),
        ]
        spec = _make_minimal_render_spec(fps=fps, duration=2.0, n_beats=16, bpm=240.0)
        assemblies = assemble_multi_domain_scene(
            scanner=scanner,
            scene_spec=SceneSpec(),
            transitions=transitions,
            materials=materials,
            render_spec=spec,
            fps=fps,
        )
        from melosviz.render.blender_exporter import FLASH_SAFETY_MAX_HZ

        for domain in (Domain.PHOTO, Domain.SPLAT):
            opacities = [a.opacities[domain] for a in assemblies]
            transitions_count = sum(
                1 for a, b in zip(opacities, opacities[1:], strict=False) if abs(b - a) > 0.5
            )
            max_allowed = FLASH_SAFETY_MAX_HZ * (len(opacities) / fps)
            assert transitions_count <= max_allowed, (
                f"Flash-safety breach in {domain}: {transitions_count} transitions > {max_allowed}"
            )


# ---------------------------------------------------------------------------
# Blender bpy script generation
# ---------------------------------------------------------------------------

class TestHybridBpyScript:
    def test_build_script_nonempty_on_assemblies(self):
        assemblies = [
            HybridDomainAssembly(
                t=0.0,
                opacities={d: 0.5 for d in Domain},
                material_looks={d: DomainMaterialLook.CLEAN_PBR for d in Domain},
                edge_energy=0.3,
                scanner_angle_rad=0.0,
            )
        ]
        script = build_hybrid_bpy_segment(assemblies, fps=30)
        assert "import bpy" in script
        assert "melo_photo" in script
        assert "melo_scanner" in script
        assert "HYBRID_FRAMES" in script

    def test_build_script_empty_on_no_assemblies(self):
        script = build_hybrid_bpy_segment([], fps=30)
        assert "No hybrid domain assemblies" in script

    def test_script_contains_all_domain_objects(self):
        assemblies = [
            HybridDomainAssembly(
                t=0.033,
                opacities={d: 0.5 for d in Domain},
                material_looks={d: DomainMaterialLook.CLEAN_PBR for d in Domain},
                edge_energy=0.2,
                scanner_angle_rad=1.0,
            )
        ]
        script = build_hybrid_bpy_segment(assemblies, fps=30)
        for name in ("melo_photo", "melo_mesh", "melo_splat", "melo_performer", "melo_fx_edge", "melo_scanner"):
            assert name in script, f"Missing domain object {name!r} in generated script"

    def test_scanner_angle_encoded_in_frames_literal(self):
        assemblies = [
            HybridDomainAssembly(
                t=0.0,
                opacities={d: 0.0 for d in Domain},
                material_looks={d: DomainMaterialLook.CLEAN_PBR for d in Domain},
                edge_energy=0.0,
                scanner_angle_rad=1.5708,  # π/2
            )
        ]
        script = build_hybrid_bpy_segment(assemblies, fps=30)
        assert "1.5708" in script
