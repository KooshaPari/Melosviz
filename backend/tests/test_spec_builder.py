"""Tests for the Melosviz backend render spec builder.

Exercises :mod:`melosviz.render.spec_builder` end-to-end:

* The high level :func:`build_spec` convenience entry point that returns a
  fully validated :class:`RenderSpec`.
* The :class:`VisualizationSpecBuilder` low-level API used by callers that
  want to control style, preset, fps, dimensions, duration, and seed.
* :func:`render_spec_to_json` / :func:`render_spec_from_json` round-tripping.

Cases cover empty inputs, traditional scales (C major, blues), complex chord
progressions, JSON round-tripping, zero-note / long-piece edge cases, custom
time signatures, color palette generation per pitch class, and scene
composition defaults.
"""

from __future__ import annotations

import json
import math
from typing import List, Tuple

import pytest

from melosviz.analysis.models import (
    AnalysisResult,
    AnalysisType,
    BPMResult,
    FrequencyResult,
    GenreTheme,
    RenderSpec,
    RenderStyle,
    ShotSpec,
    ThemePreset,
    TimelineEvent,
    WaveformResult,
)
from melosviz.presets import ThemePresetRegistry
from melosviz.render.spec_builder import (
    VisualizationSpecBuilder,
    build_spec,
    render_spec_from_json,
    render_spec_to_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _waveform_with_amplitude(samples: int, amplitude: float = 0.5) -> List[float]:
    """Build a synthetic alternating waveform of ``samples`` length."""
    return [
        amplitude if index % 2 == 0 else -amplitude
        for index in range(samples)
    ]


def _beat_positions(bpm: float, duration_sec: float) -> List[float]:
    """Return evenly spaced beat positions for ``bpm`` over ``duration_sec``."""
    if bpm <= 0:
        return []
    period = 60.0 / bpm
    beats: List[float] = []
    time = 0.0
    while time < duration_sec:
        beats.append(round(time, 4))
        time += period
    return beats


def _downbeats_from_beats(beat_positions: List[float]) -> List[float]:
    """Treat every fourth beat as a downbeat."""
    return [beat_positions[i] for i in range(0, len(beat_positions), 4)]


def _make_analysis(
    duration_sec: float,
    *,
    bpm: float = 120.0,
    waveform: List[float] | None = None,
    key_pcs: Tuple[int, ...] | None = None,
    include_bpm: bool = True,
    include_waveform: bool = True,
    include_frequency: bool = True,
) -> AnalysisResult:
    """Construct an :class:`AnalysisResult` from compact musical descriptors.

    ``key_pcs`` is an optional tuple of pitch class indices (0-11) used to
    synthesise a sparse ``dominant_bins`` frequency table.
    """
    beats = _beat_positions(bpm, duration_sec) if include_bpm else []
    downbeats = _downbeats_from_beats(beats) if include_bpm else []
    onsets = beats  # 1:1 onset/beat is fine for testing
    bpm_result = (
        BPMResult(
            bpm=bpm,
            confidence=0.9,
            beat_positions=beats,
            downbeat_positions=downbeats,
            onset_positions=onsets,
            stability=0.85,
            method="test",
        )
        if include_bpm
        else None
    )
    samples = (
        list(waveform)
        if waveform is not None
        else _waveform_with_amplitude(max(8, int(duration_sec * 30)))
    )
    waveform_result = (
        WaveformResult(
            samples=samples,
            peak_amplitude=max((abs(s) for s in samples), default=0.0) or 0.0001,
            rms_db=-12.0,
            duration=duration_sec if duration_sec > 0 else 0.001,
            sample_rate=22050,
        )
        if include_waveform
        else None
    )
    dominant_bins: dict[str, float] = {}
    if key_pcs:
        for idx, pc in enumerate(key_pcs):
            # Distribute amplitude across the 12 pitch classes.
            dominant_bins[str(110.0 * (2 ** ((pc + 36) / 12.0)))] = round(
                0.2 + (idx % 5) * 0.15, 4
            )
    frequency_result = (
        FrequencyResult(
            peak_frequency_hz=440.0,
            spectral_centroid=1500.0,
            spectral_rolloff=3000.0,
            spectral_flatness=0.12,
            dominant_bins=dominant_bins,
            spectrogram=None,
        )
        if include_frequency
        else None
    )
    return AnalysisResult(
        duration_seconds=duration_sec,
        sample_rate=22050,
        channels=1,
        analysis=AnalysisType.FULL,
        bpm=bpm_result,
        waveform=waveform_result,
        frequency=frequency_result,
    )


@pytest.fixture
def registry() -> ThemePresetRegistry:
    return ThemePresetRegistry()


@pytest.fixture
def dark_street_preset(registry: ThemePresetRegistry) -> ThemePreset:
    return registry.get_preset(GenreTheme.DARK_STREET)


@pytest.fixture
def builder() -> VisualizationSpecBuilder:
    return VisualizationSpecBuilder()


# ---------------------------------------------------------------------------
# Core build_spec behavior
# ---------------------------------------------------------------------------


def test_build_spec_with_empty_analysis_returns_valid_render_spec(
    builder: VisualizationSpecBuilder,
    dark_street_preset: ThemePreset,
) -> None:
    analysis = AnalysisResult(
        duration_seconds=0.0,
        sample_rate=22050,
        channels=1,
        analysis=AnalysisType.FULL,
    )
    spec = builder.build_spec(
        analysis=analysis,
        style=RenderStyle(),
        preset=dark_street_preset,
        fps=30,
        width=1920,
        height=1080,
        duration_sec=0.0,
        seed=0,
    )
    assert isinstance(spec, dict)
    assert spec["shots"] == []
    # Frame count is clamped to a minimum of 1, so at least one keyframe exists.
    assert len(spec["keyframes"]) == 1
    # No beats/onsets/downbeats => empty timeline.
    assert spec["timeline"] == []
    # When style has no colors we still emit the preset palette.
    assert spec["palette"] == dark_street_preset.colors


def test_build_spec_module_helper_returns_render_spec(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(duration_sec=2.0, bpm=120.0)
    spec = build_spec(analysis)
    assert isinstance(spec, RenderSpec)
    # At least intro/verse/chorus/etc. sections => multiple shots.
    assert spec.shots, "expected non-empty shots for a 2 second analysis"
    assert spec.keyframes, "expected keyframes for a 2 second analysis"
    assert spec.palette == dark_street_preset.colors
    assert spec.metadata["width"] == 1920
    assert spec.metadata["height"] == 1080
    assert spec.metadata["fps"] == 30
    assert spec.metadata["style"] == "modern"
    assert spec.metadata["geometry"] == dark_street_preset.geometry


# ---------------------------------------------------------------------------
# Scale / chord progression coverage
# ---------------------------------------------------------------------------


def test_build_spec_with_c_major_scale(
    dark_street_preset: ThemePreset,
) -> None:
    # C major: C D E F G A B => pitch classes 0,2,4,5,7,9,11
    c_major_pcs = (0, 2, 4, 5, 7, 9, 11)
    analysis = _make_analysis(
        duration_sec=4.0,
        bpm=120.0,
        key_pcs=c_major_pcs,
    )
    spec = build_spec(analysis)
    assert spec.shots, "expected at least one shot for a 4s C major analysis"
    # Timeline should include beat and downbeat events for a full analysis.
    timeline_types = {event.type for event in spec.timeline}
    assert "beat" in timeline_types
    assert "downbeat" in timeline_types
    # First shot should be the intro.
    assert spec.shots[0].section == "intro"
    # Final shot should be outro.
    assert spec.shots[-1].section == "outro"


def test_build_spec_with_blues_scale(
    dark_street_preset: ThemePreset,
) -> None:
    # A minor blues: A C D D#(Eb) E G => pitch classes 9, 0, 2, 3, 4, 7
    blues_pcs = (9, 0, 2, 3, 4, 7)
    analysis = _make_analysis(
        duration_sec=6.0,
        bpm=92.0,
        key_pcs=blues_pcs,
    )
    spec = build_spec(analysis)
    assert spec.shots, "expected at least one shot for a 6s blues analysis"
    # Downbeats are present for a typical 4/4 phrase.
    assert any(event.type == "downbeat" for event in spec.timeline)
    # Color hue is derived from the palette colors, which must be valid.
    for keyframe in spec.keyframes[:5]:
        assert 0.0 <= keyframe["hue"] <= 360.0


def test_build_spec_with_complex_chord_progression(
    dark_street_preset: ThemePreset,
) -> None:
    # I - vi - IV - V in C: C Am F G => pitch classes
    # C=(0,4,7), Am=(9,0,4), F=(5,9,0), G=(7,11,2)
    progression = (0, 4, 7, 9, 0, 4, 5, 9, 0, 7, 11, 2)
    analysis = _make_analysis(
        duration_sec=8.0,
        bpm=140.0,
        key_pcs=progression,
        waveform=_waveform_with_amplitude(240, amplitude=0.7),
    )
    spec = build_spec(analysis)
    assert spec.shots
    # Sections differ across the song structure.
    sections = {shot.section for shot in spec.shots}
    assert len(sections) >= 2
    # Shots are in non-decreasing start time order.
    starts = [shot.start_time for shot in spec.shots]
    assert starts == sorted(starts)
    # Camera state zoom always non-negative.
    for shot in spec.shots:
        assert shot.camera.zoom >= 0
    # Transition intensities stay within the [0, 1] unit interval.
    for shot in spec.shots:
        intensity = shot.transition_in.get("intensity")
        if intensity is not None:
            assert 0.0 <= float(intensity) <= 1.0


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_json_round_trip_preserves_shots() -> None:
    analysis = _make_analysis(duration_sec=2.0, bpm=120.0)
    spec = build_spec(analysis)
    payload = render_spec_to_json(spec)
    restored = render_spec_from_json(payload)
    assert isinstance(restored, RenderSpec)
    assert len(restored.shots) == len(spec.shots)
    for original, copy in zip(spec.shots, restored.shots):
        assert original.id == copy.id
        assert original.section == copy.section
        assert original.start_time == copy.start_time
        assert original.end_time == copy.end_time
        assert original.camera == copy.camera
        assert original.transition_in == copy.transition_in
        assert original.transition_out == copy.transition_out
        assert original.overlay == copy.overlay
        assert original.palette_shift == copy.palette_shift


def test_json_round_trip_preserves_timeline() -> None:
    analysis = _make_analysis(duration_sec=2.0, bpm=120.0)
    spec = build_spec(analysis)
    payload = render_spec_to_json(spec)
    restored = render_spec_from_json(payload)
    assert len(restored.timeline) == len(spec.timeline)
    for original, copy in zip(spec.timeline, restored.timeline):
        assert original.time == copy.time
        assert original.type == copy.type
        assert original.data == copy.data


def test_json_round_trip_preserves_keyframes() -> None:
    analysis = _make_analysis(duration_sec=2.0, bpm=120.0)
    spec = build_spec(analysis)
    payload = render_spec_to_json(spec)
    restored = render_spec_from_json(payload)
    assert len(restored.keyframes) == len(spec.keyframes)
    assert restored.keyframes[0] == spec.keyframes[0]


def test_json_round_trip_preserves_palette_and_layers() -> None:
    analysis = _make_analysis(duration_sec=2.0, bpm=120.0)
    spec = build_spec(analysis)
    payload = render_spec_to_json(spec)
    restored = render_spec_from_json(payload)
    assert restored.palette == spec.palette
    assert restored.layers == spec.layers
    assert restored.metadata == spec.metadata


def test_render_spec_to_json_rejects_non_spec() -> None:
    with pytest.raises(TypeError):
        render_spec_to_json({"metadata": {}})  # type: ignore[arg-type]


def test_render_spec_from_json_rejects_non_string() -> None:
    with pytest.raises(TypeError):
        render_spec_from_json({"metadata": {}})  # type: ignore[arg-type]


def test_render_spec_from_json_round_trip_with_external_json() -> None:
    analysis = _make_analysis(duration_sec=1.5, bpm=128.0)
    spec = build_spec(analysis)
    payload = render_spec_to_json(spec)
    parsed = json.loads(payload)
    # JSON should be valid and contain the expected top-level keys.
    assert set(parsed.keys()) == {
        "metadata",
        "palette",
        "layers",
        "shots",
        "timeline",
        "keyframes",
    }
    # Re-validate using pydantic.
    restored = render_spec_from_json(payload)
    assert isinstance(restored, RenderSpec)


def test_build_spec_module_helper_rejects_non_analysis() -> None:
    with pytest.raises(TypeError):
        build_spec({"duration_seconds": 1.0})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_build_spec_with_zero_notes_waveform() -> None:
    analysis = _make_analysis(
        duration_sec=1.0,
        bpm=120.0,
        waveform=[],
    )
    spec = build_spec(analysis)
    # All keyframes should have zero amplitude and bounded energy.
    for keyframe in spec.keyframes:
        assert keyframe["amplitude"] == 0.0
        assert 0.0 <= keyframe["energy"] <= 1.0
        assert 0.0 <= keyframe["intensity"] <= 1.0


def test_build_spec_with_very_long_piece(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(
        duration_sec=300.0,
        bpm=128.0,
        key_pcs=(0, 2, 4, 5, 7, 9, 11),
    )
    builder = VisualizationSpecBuilder()
    spec = builder.build_spec(
        analysis=analysis,
        style=RenderStyle(),
        preset=dark_street_preset,
        fps=30,
        width=1920,
        height=1080,
        duration_sec=300.0,
        seed=7,
    )
    # 300 seconds at 30fps = 9000 frames
    assert len(spec["keyframes"]) == 9000
    # Each section is represented across the long piece.
    section_set = {shot.section for shot in spec["shots"]}
    assert {"intro", "verse", "chorus", "bridge", "outro"}.issubset(section_set)


def test_build_spec_with_zero_bpm_keeps_bpm_curve_flat(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(
        duration_sec=2.0,
        bpm=0.0,
        include_bpm=True,
    )
    spec = build_spec(analysis)
    # With bpm=0, every keyframe's bpm_sync is 0.
    assert all(keyframe["bpm_sync"] == 0.0 for keyframe in spec.keyframes)


def test_build_spec_with_custom_fps_60(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(duration_sec=2.0, bpm=120.0)
    builder = VisualizationSpecBuilder()
    spec = builder.build_spec(
        analysis=analysis,
        style=RenderStyle(),
        preset=dark_street_preset,
        fps=60,
        width=1920,
        height=1080,
        duration_sec=2.0,
        seed=1,
    )
    # 2 seconds at 60fps = 120 frames.
    assert len(spec["keyframes"]) == 120
    assert spec["metadata"]["fps"] == 60


def test_build_spec_with_custom_fps_120(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(duration_sec=1.0, bpm=140.0)
    builder = VisualizationSpecBuilder()
    spec = builder.build_spec(
        analysis=analysis,
        style=RenderStyle(),
        preset=dark_street_preset,
        fps=120,
        width=1920,
        height=1080,
        duration_sec=1.0,
        seed=2,
    )
    assert len(spec["keyframes"]) == 120
    assert spec["metadata"]["fps"] == 120


def test_build_spec_with_4k_dimensions(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(duration_sec=1.0, bpm=120.0)
    spec = build_spec(analysis)
    # Default dimensions are 1920x1080.
    assert spec.metadata["width"] == 1920
    assert spec.metadata["height"] == 1080
    # Custom dimensions flow through the low-level API.
    builder = VisualizationSpecBuilder()
    spec_4k = builder.build_spec(
        analysis=analysis,
        style=RenderStyle(),
        preset=dark_street_preset,
        fps=30,
        width=3840,
        height=2160,
        duration_sec=1.0,
        seed=3,
    )
    assert spec_4k["metadata"]["width"] == 3840
    assert spec_4k["metadata"]["height"] == 2160


def test_build_spec_with_3_4_time_signature_feel(
    dark_street_preset: ThemePreset,
) -> None:
    """Custom time signatures surface through downbeat distribution."""
    # 3/4 feel => downbeat every 3 beats instead of 4.
    duration_sec = 6.0
    bpm = 120.0
    period = 60.0 / bpm
    beat_times = [round(i * period, 4) for i in range(int(duration_sec / period))]
    downbeats = beat_times[::3]
    analysis = AnalysisResult(
        duration_seconds=duration_sec,
        sample_rate=22050,
        channels=1,
        analysis=AnalysisType.FULL,
        bpm=BPMResult(
            bpm=bpm,
            confidence=0.9,
            beat_positions=beat_times,
            downbeat_positions=downbeats,
            onset_positions=beat_times,
            stability=0.9,
            method="test",
        ),
        waveform=WaveformResult(
            samples=_waveform_with_amplitude(int(duration_sec * 30)),
            peak_amplitude=0.6,
            rms_db=-12.0,
            duration=duration_sec,
            sample_rate=22050,
        ),
        frequency=FrequencyResult(peak_frequency_hz=440.0),
    )
    spec = build_spec(analysis)
    downbeat_events = [e for e in spec.timeline if e.type == "downbeat"]
    # Every downbeat position should appear as a downbeat event.
    assert {round(e.time, 4) for e in downbeat_events} == set(downbeats)


def test_build_spec_with_7_8_time_signature_odd_division(
    dark_street_preset: ThemePreset,
) -> None:
    """7/8 produces an odd downbeat spacing; verify keyframes stay well-formed."""
    duration_sec = 7.0
    # 7/8 with 120bpm quarter notes => ~7 beats per 2 seconds.
    bpm = 168.0  # faster so we have multiple downbeats in 7s
    period = 60.0 / bpm
    beat_times = [round(i * period, 4) for i in range(int(duration_sec / period))]
    downbeats = beat_times[::7]
    analysis = AnalysisResult(
        duration_seconds=duration_sec,
        sample_rate=22050,
        channels=1,
        analysis=AnalysisType.FULL,
        bpm=BPMResult(
            bpm=bpm,
            confidence=0.9,
            beat_positions=beat_times,
            downbeat_positions=downbeats,
            onset_positions=beat_times,
            stability=0.9,
            method="test",
        ),
        waveform=WaveformResult(
            samples=_waveform_with_amplitude(int(duration_sec * 30)),
            peak_amplitude=0.5,
            rms_db=-12.0,
            duration=duration_sec,
            sample_rate=22050,
        ),
        frequency=FrequencyResult(peak_frequency_hz=440.0),
    )
    spec = build_spec(analysis)
    # Keyframes still cover the full duration at 30 fps.
    assert len(spec.keyframes) == 210
    # Hue is always in the canonical 0-360 range.
    for keyframe in spec.keyframes:
        assert 0.0 <= keyframe["hue"] <= 360.0


# ---------------------------------------------------------------------------
# Color palette generation per pitch class / preset
# ---------------------------------------------------------------------------


def test_palette_for_every_genre_preset(
    registry: ThemePresetRegistry,
) -> None:
    """Every registered preset must yield a non-empty color palette."""
    for theme in GenreTheme:
        preset = registry.get_preset(theme)
        analysis = _make_analysis(duration_sec=2.0, bpm=120.0, key_pcs=(0, 4, 7))
        builder = VisualizationSpecBuilder()
        spec = builder.build_spec(
            analysis=analysis,
            style=RenderStyle(),
            preset=preset,
            fps=30,
            width=1920,
            height=1080,
            duration_sec=2.0,
            seed=11,
        )
        # Style has no colors => palette comes from the preset.
        assert spec["palette"]
        # All palette entries are hex strings.
        for color in spec["palette"]:
            assert isinstance(color, str)
            assert color.startswith("#")


def test_palette_hue_per_pitch_class_distinct(
    builder: VisualizationSpecBuilder,
) -> None:
    """Distinct palette colors must produce distinct hues."""
    distinct_palette = [
        "#FF0000",  # red
        "#00FF00",  # green
        "#0000FF",  # blue
        "#FFFF00",  # yellow
        "#FF00FF",  # magenta
        "#00FFFF",  # cyan
    ]
    style = RenderStyle(template="modern", colors=distinct_palette)
    preset = ThemePreset(
        id="test",
        name="Test",
        colors=[],
        glow_color="#000000",
        geometry="",
        mood="",
        notes="",
    )
    analysis = _make_analysis(duration_sec=1.0, bpm=120.0)
    spec = builder.build_spec(
        analysis=analysis,
        style=style,
        preset=preset,
        fps=30,
        width=640,
        height=360,
        duration_sec=1.0,
        seed=0,
    )
    hues = {kf["hue"] for kf in spec["keyframes"]}
    # At least 4 of the 6 distinct hue values should appear at 30fps in 1s.
    assert len(hues) >= 4


def test_palette_falls_back_to_glow_color_when_empty(
    builder: VisualizationSpecBuilder,
) -> None:
    preset = ThemePreset(
        id="minimal",
        name="Minimal",
        colors=[],
        glow_color="#ABCDEF",
        geometry="",
        mood="",
        notes="",
    )
    analysis = _make_analysis(duration_sec=1.0, bpm=120.0)
    spec = builder.build_spec(
        analysis=analysis,
        style=RenderStyle(template="t", colors=[]),
        preset=preset,
        fps=30,
        width=640,
        height=360,
        duration_sec=1.0,
        seed=0,
    )
    # Both style and preset colors are empty => palette is [glow_color].
    assert spec["palette"] == ["#ABCDEF"]


# ---------------------------------------------------------------------------
# Scene composition defaults and determinism
# ---------------------------------------------------------------------------


def test_scene_composition_default_layers(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(duration_sec=1.0, bpm=120.0)
    spec = build_spec(analysis)
    layer_types = [layer["type"] for layer in spec.layers]
    # Default layer order is fixed.
    assert layer_types == ["background", "shapes", "particles", "text"]
    # Every layer has the required structure.
    for layer in spec.layers:
        assert "visible" in layer
        assert "opacity" in layer
        assert "transform" in layer
        assert set(layer["transform"].keys()) == {"scale", "rotation", "offset"}


def test_shot_ids_are_sequential(dark_street_preset: ThemePreset) -> None:
    analysis = _make_analysis(duration_sec=4.0, bpm=120.0)
    spec = build_spec(analysis)
    assert spec.shots
    expected_ids = [f"shot-{i + 1}" for i in range(len(spec.shots))]
    assert [shot.id for shot in spec.shots] == expected_ids


def test_first_shot_is_intro_and_last_shot_is_outro(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(duration_sec=8.0, bpm=120.0)
    spec = build_spec(analysis)
    assert spec.shots[0].section == "intro"
    assert spec.shots[-1].section == "outro"


def test_deterministic_with_same_seed(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(duration_sec=2.0, bpm=120.0)
    builder = VisualizationSpecBuilder()
    spec_a = builder.build_spec(
        analysis=analysis,
        style=RenderStyle(),
        preset=dark_street_preset,
        fps=30,
        width=1280,
        height=720,
        duration_sec=2.0,
        seed=42,
    )
    spec_b = builder.build_spec(
        analysis=analysis,
        style=RenderStyle(),
        preset=dark_street_preset,
        fps=30,
        width=1280,
        height=720,
        duration_sec=2.0,
        seed=42,
    )
    # Random layer transforms must be identical for the same seed.
    assert spec_a["layers"] == spec_b["layers"]
    # The whole payload should be byte-for-byte equal.
    assert spec_a == spec_b


def test_different_seeds_produce_different_layer_transforms(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(duration_sec=2.0, bpm=120.0)
    builder = VisualizationSpecBuilder()
    spec_a = builder.build_spec(
        analysis=analysis,
        style=RenderStyle(),
        preset=dark_street_preset,
        fps=30,
        width=1280,
        height=720,
        duration_sec=2.0,
        seed=42,
    )
    spec_b = builder.build_spec(
        analysis=analysis,
        style=RenderStyle(),
        preset=dark_street_preset,
        fps=30,
        width=1280,
        height=720,
        duration_sec=2.0,
        seed=43,
    )
    # The 'shapes' layer is the only one driven by the random number generator.
    assert spec_a["layers"][1] != spec_b["layers"][1]
    # Camera/keyframe/shot data is deterministic regardless of seed.
    assert spec_a["shots"] == spec_b["shots"]


def test_timeline_events_are_sorted_by_time_and_priority(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(duration_sec=4.0, bpm=120.0)
    spec = build_spec(analysis)
    times = [event.time for event in spec.timeline]
    assert times == sorted(times)
    # Events at the same time should be in priority order.
    priority = {
        "shot_change": 0,
        "section_start": 1,
        "camera_move": 2,
        "palette_shift": 3,
        "downbeat": 4,
        "beat": 5,
        "onset": 6,
    }
    for prev, current in zip(spec.timeline, spec.timeline[1:]):
        if prev.time == current.time:
            assert priority[prev.type] <= priority[current.type]


def test_beat_and_onset_strengths(dark_street_preset: ThemePreset) -> None:
    analysis = _make_analysis(duration_sec=2.0, bpm=120.0)
    spec = build_spec(analysis)
    beat_events = [e for e in spec.timeline if e.type == "beat"]
    onset_events = [e for e in spec.timeline if e.type == "onset"]
    # Beats and onsets are emitted with their canonical strengths.
    assert all(event.data["strength"] == 1.0 for event in beat_events)
    assert all(event.data["strength"] == 0.75 for event in onset_events)
    # Beat events should match the number of input beat positions.
    assert len(beat_events) == len(analysis.bpm.beat_positions)


def test_shot_energies_are_within_unit_interval(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(duration_sec=4.0, bpm=120.0)
    spec = build_spec(analysis)
    # ``ShotSpec`` exposes the energy envelope via overlay text payloads
    # (e.g. ``audio_signature`` carries an ``energy`` and ``intensity`` field).
    for shot in spec.shots:
        for overlay in shot.overlay:
            if "energy" in overlay:
                assert 0.0 <= float(overlay["energy"]) <= 1.0
            if "intensity" in overlay:
                assert 0.0 <= float(overlay["intensity"]) <= 1.0
        # Transition intensities are also unit-interval bounded.
        for transition in (shot.transition_in, shot.transition_out):
            intensity = transition.get("intensity")
            if intensity is not None:
                assert 0.0 <= float(intensity) <= 1.0


def test_keyframe_camera_zoom_non_negative(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(duration_sec=2.0, bpm=120.0)
    spec = build_spec(analysis)
    for keyframe in spec.keyframes:
        assert keyframe["camera"]["zoom"] >= 0
        # Rotation can be any sign.
        assert isinstance(keyframe["camera"]["rotation"], float)


def test_metadata_matches_request_dimensions_and_seed(
    dark_street_preset: ThemePreset,
) -> None:
    analysis = _make_analysis(duration_sec=2.0, bpm=120.0)
    builder = VisualizationSpecBuilder()
    spec = builder.build_spec(
        analysis=analysis,
        style=RenderStyle(template="dynamic"),
        preset=dark_street_preset,
        fps=30,
        width=1280,
        height=720,
        duration_sec=2.0,
        seed=99,
    )
    metadata = spec["metadata"]
    assert metadata["width"] == 1280
    assert metadata["height"] == 720
    assert metadata["fps"] == 30
    assert metadata["duration"] == 2.0
    assert metadata["seed"] == 99
    assert metadata["style"] == "dynamic"
    assert metadata["geometry"] == dark_street_preset.geometry


def test_render_spec_exposes_pydantic_models_for_shots_and_timeline() -> None:
    """``RenderSpec.shots`` and ``timeline`` should be ``BaseModel`` lists."""
    analysis = _make_analysis(duration_sec=2.0, bpm=120.0)
    spec = build_spec(analysis)
    assert spec.shots and all(isinstance(s, ShotSpec) for s in spec.shots)
    assert spec.timeline and all(
        isinstance(e, TimelineEvent) for e in spec.timeline
    )
