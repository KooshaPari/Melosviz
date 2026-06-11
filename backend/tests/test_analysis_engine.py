"""Tests for the Melosviz analysis engine and render spec contracts."""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from melosviz.analysis.engine import AudioAnalysisEngine
from melosviz.analysis.models import (
    AnalysisType,
    AnalysisResult,
    BPMResult,
    FrequencyResult,
    GenreTheme,
    RenderStyle,
    WaveformResult,
)
from melosviz.presets import ThemePresetRegistry
from melosviz.render.spec_builder import VisualizationSpecBuilder


@pytest.fixture
def sine_wave_file(tmp_path: Path) -> Path:
    sample_rate = 22050
    duration = 2.0
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    audio = 0.5 * np.sin(2 * np.pi * 440.0 * t)
    path = tmp_path / "sine.wav"
    sf.write(path, audio, sample_rate)
    return path


@pytest.fixture
def beat_pattern_file(tmp_path: Path) -> Path:
    sample_rate = 22050
    duration = 8.0
    audio = np.zeros(int(sample_rate * duration), dtype=np.float32)
    beat_interval = 0.5
    beat_width = int(0.06 * sample_rate)
    for beat in np.arange(0, duration, beat_interval):
        idx = int(beat * sample_rate)
        window = np.hanning(beat_width)
        audio[idx : idx + beat_width] += 0.8 * window
    path = tmp_path / "beat.wav"
    sf.write(path, audio, sample_rate)
    return path


def test_frequency_analysis_detects_sine_peak(sine_wave_file: Path) -> None:
    engine = AudioAnalysisEngine()
    result = engine.analyze_frequency(sine_wave_file)
    assert abs(result.peak_frequency_hz - 440.0) < 35.0
    assert result.spectral_centroid > 0


def test_waveform_extraction_returns_expected_keys(sine_wave_file: Path) -> None:
    engine = AudioAnalysisEngine()
    result = engine.analyze_waveform(sine_wave_file)
    assert result.sample_rate == 22050
    assert result.duration > 0
    assert isinstance(result.samples, list)
    assert result.samples


def test_bpm_detection_with_known_tempo(beat_pattern_file: Path) -> None:
    engine = AudioAnalysisEngine()
    result = engine.analyze_bpm(beat_pattern_file)
    assert 100 <= result.bpm <= 140
    assert len(result.beat_positions) > 0


def test_error_handling_for_missing_file(tmp_path: Path) -> None:
    engine = AudioAnalysisEngine()
    with pytest.raises(FileNotFoundError):
        engine.analyze_waveform(tmp_path / "does-not-exist.wav")


def test_spec_builder_emits_frontend_keyframe_fields() -> None:
    builder = VisualizationSpecBuilder()
    preset = ThemePresetRegistry().get_preset(GenreTheme.DARK_STREET)

    analysis = AnalysisResult(
        duration_seconds=1.0,
        sample_rate=22050,
        channels=1,
        analysis=AnalysisType.FULL,
        bpm=BPMResult(
            bpm=120.0,
            confidence=0.78,
            beat_positions=[0.0, 0.5],
            stability=0.9,
            method="test",
        ),
        waveform=WaveformResult(
            samples=[0.0, 0.3, -0.6, 0.1, -0.2, 0.4],
            peak_amplitude=0.6,
            rms_db=-9.0,
            duration=1.0,
            sample_rate=22050,
        ),
        frequency=FrequencyResult(
            peak_frequency_hz=440.0,
            spectral_centroid=1400.0,
            spectral_rolloff=3200.0,
            spectral_flatness=0.18,
            dominant_bins={"440": 1.2},
            spectrogram=None,
        ),
    )

    spec = builder.build_spec(
        analysis=analysis,
        style=RenderStyle(),
        preset=preset,
        fps=30,
        width=960,
        height=540,
        duration_sec=1.0,
        seed=42,
    )

    keyframes = spec["keyframes"]
    assert isinstance(keyframes, list)
    assert keyframes, "Expected at least one generated keyframe"

    required = {
        "energy",
        "frequency",
        "amplitude",
        "color_shift",
        "hue",
        "intensity",
        "bpm_sync",
    }
    first = keyframes[0]
    assert required.issubset(first.keys())

    for frame in keyframes[:10]:
        assert 0.0 <= frame["energy"] <= 1.0
        assert 0.0 <= frame["intensity"] <= 1.0
        assert 0.0 <= frame["hue"] <= 360.0
        assert frame["frequency"]["dominant"]
        assert isinstance(frame["color_shift"], str)
        assert isinstance(frame["amplitude"], (int, float))
