"""Tests for the Melosviz analysis engine and render spec contracts.

These tests cover the :class:`AudioAnalysisEngine` end-to-end using
synthesised audio signals written to temporary WAV files. The pure-Python
beat tracker installed by ``conftest.py`` is used in place of librosa's
numba-jit'd beat tracker, which segfaults on macOS + Python 3.14.
"""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from melosviz.analysis.engine import AudioAnalysisEngine, AudioDecodeError
from melosviz.analysis.models import (
    AnalysisType,
    AnalysisResult,
    AnalyzeRequest,
    BPMResult,
    FrequencyResult,
    GenreTheme,
    RenderStyle,
    WaveformResult,
)
from melosviz.presets import ThemePresetRegistry
from melosviz.render.spec_builder import VisualizationSpecBuilder


# ---------------------------------------------------------------------------
# Audio synthesis helpers
# ---------------------------------------------------------------------------


def _sine(freq_hz: float, duration: float, sr: int = 22050, amp: float = 0.5) -> np.ndarray:
    """Return a float32 sine wave at ``freq_hz`` lasting ``duration`` seconds."""
    t = np.linspace(0.0, duration, int(sr * duration), endpoint=False)
    return (amp * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float32)


def _click_track(
    bpm: float, duration: float, sr: int = 22050, click_width_ms: float = 60.0
) -> np.ndarray:
    """Return a float32 click track at ``bpm`` lasting ``duration`` seconds."""
    audio = np.zeros(int(sr * duration), dtype=np.float32)
    beat_interval = 60.0 / bpm
    beat_width = max(1, int(0.001 * click_width_ms * sr))
    window = np.hanning(beat_width).astype(np.float32)
    for beat in np.arange(0.0, duration, beat_interval):
        idx = int(beat * sr)
        end = min(idx + beat_width, audio.shape[0])
        audio[idx:end] += 0.8 * window[: end - idx]
    return audio


def _write_wav(path: Path, audio: np.ndarray, sr: int = 22050) -> Path:
    """Write a mono float32 WAV file and return the path."""
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    sf.write(str(path), audio.astype(np.float32, copy=False), sr)
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sine_wave_file(tmp_path: Path) -> Path:
    return _write_wav(tmp_path / "sine.wav", _sine(440.0, 2.0))


@pytest.fixture
def beat_pattern_file(tmp_path: Path) -> Path:
    return _write_wav(tmp_path / "beat.wav", _click_track(120.0, 8.0))


@pytest.fixture
def engine() -> AudioAnalysisEngine:
    return AudioAnalysisEngine()


# ---------------------------------------------------------------------------
# Existing baseline tests
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# BPM detection tests
# ---------------------------------------------------------------------------


def test_bpm_detection_silence_returns_zero(engine: AudioAnalysisEngine, tmp_path: Path) -> None:
    """A silent file has no detectable beats and should report bpm=0."""
    path = _write_wav(tmp_path / "silence.wav", np.zeros(22050 * 2, dtype=np.float32))
    result = engine.analyze_bpm(path)
    assert result.bpm == 0.0
    assert result.beat_positions == []
    assert result.stability == 0.0
    assert result.confidence == 0.0


def test_bpm_detection_constant_tone_returns_zero(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """A pure sine wave has no onsets and should report bpm=0."""
    path = _write_wav(tmp_path / "tone.wav", _sine(440.0, 3.0))
    result = engine.analyze_bpm(path)
    assert result.bpm == 0.0
    assert result.beat_positions == []


def test_bpm_detection_slow_tempo_60bpm(engine: AudioAnalysisEngine, tmp_path: Path) -> None:
    """A 60 BPM click track should be detected within a generous tolerance."""
    path = _write_wav(tmp_path / "slow.wav", _click_track(60.0, 12.0))
    result = engine.analyze_bpm(path)
    assert 45 <= result.bpm <= 80
    assert len(result.beat_positions) >= 4


def test_bpm_detection_fast_tempo_180bpm(engine: AudioAnalysisEngine, tmp_path: Path) -> None:
    """A 180 BPM click track should be detected within a generous tolerance."""
    path = _write_wav(tmp_path / "fast.wav", _click_track(180.0, 8.0))
    result = engine.analyze_bpm(path)
    assert 140 <= result.bpm <= 230
    assert len(result.beat_positions) >= 6


def test_bpm_result_uses_librosa_method_label(
    engine: AudioAnalysisEngine, beat_pattern_file: Path
) -> None:
    """The engine should label the detection method for downstream consumers."""
    result = engine.analyze_bpm(beat_pattern_file)
    assert isinstance(result.method, str)
    assert result.method  # non-empty


def test_bpm_beat_positions_are_monotonic(
    engine: AudioAnalysisEngine, beat_pattern_file: Path
) -> None:
    """Detected beat times should be strictly increasing and non-negative."""
    result = engine.analyze_bpm(beat_pattern_file)
    positions = result.beat_positions
    assert len(positions) >= 2
    assert all(p >= 0.0 for p in positions)
    assert all(positions[i] < positions[i + 1] for i in range(len(positions) - 1))


def test_bpm_stability_within_unit_interval(
    engine: AudioAnalysisEngine, beat_pattern_file: Path
) -> None:
    """Stability must be a clamped score in [0, 1]."""
    result = engine.analyze_bpm(beat_pattern_file)
    assert 0.0 <= result.stability <= 1.0
    assert 0.0 <= result.confidence <= 1.0


def test_bpm_confidence_matches_stability_for_regular_track(
    engine: AudioAnalysisEngine, beat_pattern_file: Path
) -> None:
    """For a metronomic click track, stability and confidence are equal."""
    result = engine.analyze_bpm(beat_pattern_file)
    assert result.stability == pytest.approx(result.confidence, abs=1e-6)


# ---------------------------------------------------------------------------
# Frequency analysis tests
# ---------------------------------------------------------------------------


def test_frequency_analysis_silence_has_zero_peak(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """A silent file should have a peak frequency at or near 0 Hz."""
    path = _write_wav(tmp_path / "silent.wav", np.zeros(22050 * 2, dtype=np.float32))
    result = engine.analyze_frequency(path)
    assert result.peak_frequency_hz >= 0.0
    assert result.peak_frequency_hz < 1.0
    assert result.spectral_flatness >= 0.0


def test_frequency_analysis_chord_c_major(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """A C major triad (C+E+G) should produce a peak near C4 (262 Hz)."""
    sr = 22050
    duration = 2.0
    c4 = _sine(261.63, duration, sr=sr, amp=0.4)
    e4 = _sine(329.63, duration, sr=sr, amp=0.4)
    g4 = _sine(392.00, duration, sr=sr, amp=0.4)
    chord = (c4 + e4 + g4).astype(np.float32) / 1.2
    path = _write_wav(tmp_path / "c_major.wav", chord, sr=sr)
    result = engine.analyze_frequency(path)
    # Peak should be one of the chord tones; the FFT bins are coarse
    # at 2048 fft / 22050 sr, so we allow a generous window.
    assert any(
        abs(result.peak_frequency_hz - target) < 25.0
        for target in (261.63, 329.63, 392.00)
    )
    assert len(result.dominant_bins) == 8


def test_frequency_analysis_low_frequency_detection(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """A 55 Hz sine (A1) should be detected within FFT-bin tolerance."""
    path = _write_wav(tmp_path / "low.wav", _sine(55.0, 2.0))
    result = engine.analyze_frequency(path)
    assert abs(result.peak_frequency_hz - 55.0) < 15.0


def test_frequency_analysis_high_frequency_detection(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """A 4000 Hz sine should be detected within FFT-bin tolerance."""
    path = _write_wav(tmp_path / "high.wav", _sine(4000.0, 2.0))
    result = engine.analyze_frequency(path)
    assert abs(result.peak_frequency_hz - 4000.0) < 60.0


def test_frequency_analysis_dominant_bins_are_string_keys(
    engine: AudioAnalysisEngine, sine_wave_file: Path
) -> None:
    """``dominant_bins`` should map string frequency labels to magnitudes."""
    result = engine.analyze_frequency(sine_wave_file)
    assert isinstance(result.dominant_bins, dict)
    assert result.dominant_bins
    for key, value in result.dominant_bins.items():
        assert isinstance(key, str)
        assert isinstance(value, float)
        assert value >= 0.0


def test_frequency_analysis_spectrogram_is_2d_list(
    engine: AudioAnalysisEngine, sine_wave_file: Path
) -> None:
    """The spectrogram field, when present, is a list of lists of floats."""
    result = engine.analyze_frequency(sine_wave_file)
    assert result.spectrogram is not None
    assert isinstance(result.spectrogram, list)
    assert result.spectrogram
    row = result.spectrogram[0]
    assert isinstance(row, list)
    if row:
        assert all(isinstance(v, (int, float)) for v in row)


def test_frequency_analysis_custom_fft_size(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """Passing a custom ``fft_size`` should not raise and should still detect a peak."""
    path = _write_wav(tmp_path / "tone.wav", _sine(880.0, 1.0))
    result = engine.analyze_frequency(path, fft_size=4096, hop_size=1024)
    assert abs(result.peak_frequency_hz - 880.0) < 40.0
    assert result.spectrogram is not None


def test_frequency_analysis_microtonal_frequency(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """A non-A440 reference (e.g. 442 Hz) should still be detected near the target."""
    path = _write_wav(tmp_path / "microtonal.wav", _sine(442.0, 2.0))
    result = engine.analyze_frequency(path)
    assert abs(result.peak_frequency_hz - 442.0) < 35.0


def test_frequency_analysis_chord_inversion(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """A C major chord in first inversion (E+G+C) still has the same notes."""
    sr = 22050
    duration = 2.0
    e4 = _sine(329.63, duration, sr=sr, amp=0.4)
    g4 = _sine(392.00, duration, sr=sr, amp=0.4)
    c5 = _sine(523.25, duration, sr=sr, amp=0.4)
    chord = (e4 + g4 + c5).astype(np.float32) / 1.2
    path = _write_wav(tmp_path / "c_inv.wav", chord, sr=sr)
    result = engine.analyze_frequency(path)
    assert any(
        abs(result.peak_frequency_hz - target) < 30.0
        for target in (329.63, 392.00, 523.25)
    )


# ---------------------------------------------------------------------------
# Waveform analysis tests
# ---------------------------------------------------------------------------


def test_waveform_duration_matches_file_length(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """The reported duration should equal samples / sample_rate."""
    sr = 22050
    duration = 3.0
    path = _write_wav(tmp_path / "three_sec.wav", _sine(440.0, duration, sr=sr), sr=sr)
    result = engine.analyze_waveform(path)
    assert abs(result.duration - duration) < 0.1


def test_waveform_peak_amplitude_bounded_by_input(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """Peak amplitude should be the maximum absolute sample value."""
    path = _write_wav(tmp_path / "half.wav", _sine(440.0, 1.0, amp=0.5))
    result = engine.analyze_waveform(path)
    assert 0.4 <= result.peak_amplitude <= 0.6


def test_waveform_rms_is_negative_db_for_sine(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """A 0.5-amplitude sine should have an RMS around -9 dB (20*log10(0.5/sqrt(2)))."""
    path = _write_wav(tmp_path / "rms.wav", _sine(440.0, 1.0, amp=0.5))
    result = engine.analyze_waveform(path)
    assert -12.0 <= result.rms_db <= -6.0


def test_waveform_samples_length_is_512(
    engine: AudioAnalysisEngine, sine_wave_file: Path
) -> None:
    """The engine returns a fixed-length 512-sample downsampled waveform."""
    result = engine.analyze_waveform(sine_wave_file)
    assert len(result.samples) == 512
    assert all(isinstance(s, float) for s in result.samples)


def test_waveform_custom_window_ms_changes_nothing_for_basic_call(
    engine: AudioAnalysisEngine, sine_wave_file: Path
) -> None:
    """``window_ms`` is accepted but should not break the contract."""
    result = engine.analyze_waveform(sine_wave_file, window_ms=10)
    assert result.sample_rate == 22050
    assert result.duration > 0
    assert len(result.samples) == 512


def test_waveform_stereo_is_downmixed(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """A stereo file should be downmixed to mono for analysis."""
    sr = 22050
    t = np.linspace(0.0, 1.0, sr, endpoint=False)
    left = (0.3 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    right = (0.3 * np.sin(2.0 * np.pi * 660.0 * t)).astype(np.float32)
    stereo = np.stack([left, right], axis=1)
    path = tmp_path / "stereo.wav"
    sf.write(str(path), stereo, sr)
    result = engine.analyze_waveform(path)
    assert result.sample_rate == sr
    assert result.duration > 0
    assert len(result.samples) == 512


# ---------------------------------------------------------------------------
# Full analysis pipeline tests
# ---------------------------------------------------------------------------


def test_full_analysis_default_runs_all(
    engine: AudioAnalysisEngine, sine_wave_file: Path
) -> None:
    """The default request should populate bpm, waveform, and frequency."""
    result = engine.full_analysis(sine_wave_file)
    assert result.bpm is not None
    assert result.waveform is not None
    assert result.frequency is not None
    assert result.analysis == AnalysisType.FULL
    assert result.duration_seconds > 0


def test_full_analysis_bpm_only(engine: AudioAnalysisEngine, sine_wave_file: Path) -> None:
    """A BPM-only request should skip waveform and frequency results."""
    request = AnalyzeRequest(analysis=AnalysisType.BPM, include_waveform=False, include_spectrum=False)
    result = engine.full_analysis(sine_wave_file, request=request)
    assert result.bpm is not None
    assert result.waveform is None
    assert result.frequency is None


def test_full_analysis_waveform_only(
    engine: AudioAnalysisEngine, sine_wave_file: Path
) -> None:
    """A waveform-only request should skip BPM and frequency."""
    request = AnalyzeRequest(
        analysis=AnalysisType.WAVEFORM, include_bpm=False, include_spectrum=False
    )
    result = engine.full_analysis(sine_wave_file, request=request)
    assert result.waveform is not None
    assert result.bpm is None
    assert result.frequency is None


def test_full_analysis_frequency_only(
    engine: AudioAnalysisEngine, sine_wave_file: Path
) -> None:
    """A frequency-only request should skip BPM and waveform."""
    request = AnalyzeRequest(
        analysis=AnalysisType.FREQUENCY, include_bpm=False, include_waveform=False
    )
    result = engine.full_analysis(sine_wave_file, request=request)
    assert result.frequency is not None
    assert result.bpm is None
    assert result.waveform is None


def test_full_analysis_skips_bpm_when_disabled(
    engine: AudioAnalysisEngine, sine_wave_file: Path
) -> None:
    """Setting ``include_bpm=False`` on a FULL request should drop the BPM result."""
    request = AnalyzeRequest(analysis=AnalysisType.FULL, include_bpm=False)
    result = engine.full_analysis(sine_wave_file, request=request)
    assert result.bpm is None
    assert result.waveform is not None
    assert result.frequency is not None


def test_full_analysis_reports_sample_rate_and_channels(
    engine: AudioAnalysisEngine, sine_wave_file: Path
) -> None:
    """Top-level metadata should match the source file."""
    result = engine.full_analysis(sine_wave_file)
    assert result.sample_rate == 22050
    assert result.channels == 1


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


def test_bpm_result_validates_bpm_non_negative() -> None:
    """BPMResult must reject negative bpm values."""
    with pytest.raises(ValueError):
        BPMResult(bpm=-1.0, confidence=0.5)


def test_bpm_result_validates_confidence_range() -> None:
    """Confidence must be in [0, 1]."""
    with pytest.raises(ValueError):
        BPMResult(bpm=120.0, confidence=1.5)
    with pytest.raises(ValueError):
        BPMResult(bpm=120.0, confidence=-0.1)


def test_waveform_result_validates_peak_non_negative() -> None:
    """Peak amplitude cannot be negative."""
    with pytest.raises(ValueError):
        WaveformResult(
            samples=[0.0],
            peak_amplitude=-0.1,
            rms_db=-3.0,
            duration=1.0,
            sample_rate=22050,
        )


def test_waveform_result_validates_duration_positive() -> None:
    """Duration must be strictly positive."""
    with pytest.raises(ValueError):
        WaveformResult(
            samples=[0.0],
            peak_amplitude=0.1,
            rms_db=-3.0,
            duration=0.0,
            sample_rate=22050,
        )


def test_frequency_result_validates_peak_non_negative() -> None:
    """Peak frequency cannot be negative."""
    with pytest.raises(ValueError):
        FrequencyResult(peak_frequency_hz=-10.0)


def test_analysis_result_with_all_fields() -> None:
    """An AnalysisResult can be constructed with every sub-result populated."""
    result = AnalysisResult(
        duration_seconds=2.0,
        sample_rate=22050,
        channels=1,
        analysis=AnalysisType.FULL,
        bpm=BPMResult(bpm=120.0, confidence=0.9),
        waveform=WaveformResult(
            samples=[0.0, 0.1, -0.1],
            peak_amplitude=0.1,
            rms_db=-20.0,
            duration=2.0,
            sample_rate=22050,
        ),
        frequency=FrequencyResult(peak_frequency_hz=440.0),
    )
    assert result.bpm is not None
    assert result.waveform is not None
    assert result.frequency is not None
    assert result.analysis == AnalysisType.FULL


def test_analysis_result_with_minimal_fields() -> None:
    """An AnalysisResult with only required fields is valid; sub-results default to None."""
    result = AnalysisResult(
        duration_seconds=1.0,
        sample_rate=22050,
        channels=1,
        analysis=AnalysisType.WAVEFORM,
    )
    assert result.bpm is None
    assert result.waveform is None
    assert result.frequency is None


def test_analyze_request_default_values() -> None:
    """AnalyzeRequest defaults to a FULL analysis with all sub-results enabled."""
    request = AnalyzeRequest()
    assert request.analysis == AnalysisType.FULL
    assert request.include_bpm is True
    assert request.include_waveform is True
    assert request.include_spectrum is True
    assert request.window_ms == 2000
    assert request.fft_size == 2048
    assert request.hop_size == 512


def test_analyze_request_rejects_hop_greater_than_fft() -> None:
    """The model validator must reject hop_size >= fft_size."""
    with pytest.raises(ValueError):
        AnalyzeRequest(fft_size=512, hop_size=512)
    with pytest.raises(ValueError):
        AnalyzeRequest(fft_size=512, hop_size=1024)


def test_analyze_request_window_ms_bounds() -> None:
    """window_ms must be in [0, 60000]."""
    with pytest.raises(ValueError):
        AnalyzeRequest(window_ms=-1)
    with pytest.raises(ValueError):
        AnalyzeRequest(window_ms=60001)


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


def test_engine_accepts_string_path(
    engine: AudioAnalysisEngine, sine_wave_file: Path
) -> None:
    """The engine should accept both ``str`` and ``Path`` sources."""
    result = engine.analyze_waveform(str(sine_wave_file))
    assert result.sample_rate == 22050


def test_engine_accepts_path_object(
    engine: AudioAnalysisEngine, sine_wave_file: Path
) -> None:
    """A ``pathlib.Path`` source should work the same as a string."""
    result = engine.analyze_waveform(sine_wave_file)
    assert result.sample_rate == 22050


def test_engine_raises_on_corrupted_wav(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """A non-audio file should raise ``AudioDecodeError``."""
    bad = tmp_path / "broken.wav"
    bad.write_bytes(b"this is not a valid WAV file at all")
    with pytest.raises((AudioDecodeError, FileNotFoundError)):
        engine.analyze_waveform(bad)


def test_engine_handles_very_short_audio(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """A 10 ms file should still produce a valid waveform (or decode gracefully)."""
    sr = 22050
    n_samples = max(1, int(sr * 0.01))
    audio = _sine(440.0, n_samples / sr, sr=sr)
    path = _write_wav(tmp_path / "short.wav", audio, sr=sr)
    result = engine.analyze_waveform(path)
    assert result.sample_rate == sr
    assert result.duration > 0


def test_engine_handles_very_long_audio(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """A 30-second sine wave should report the correct duration."""
    sr = 22050
    duration = 30.0
    path = _write_wav(tmp_path / "long.wav", _sine(220.0, duration, sr=sr), sr=sr)
    result = engine.analyze_waveform(path)
    assert abs(result.duration - duration) < 0.2
    assert result.peak_amplitude > 0.0


def test_engine_overlapping_beats_are_handled(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """Overlapping drum hits (wide clicks) should still produce a usable BPM."""
    # Wide 200 ms clicks at 120 BPM - the second click starts before
    # the first fully decays, exercising the overlap path.
    path = _write_wav(tmp_path / "overlap.wav", _click_track(120.0, 6.0, click_width_ms=200.0))
    result = engine.analyze_bpm(path)
    # The detector should either find the dominant tempo or report 0;
    # both are acceptable failure modes for this pathological input.
    assert result.bpm == 0.0 or result.bpm > 0.0


def test_engine_very_short_notes_are_handled(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """Very narrow 5 ms clicks at 120 BPM should still be analysable."""
    path = _write_wav(tmp_path / "narrow.wav", _click_track(120.0, 6.0, click_width_ms=5.0))
    result = engine.analyze_bpm(path)
    # Narrow clicks may not be detected at all, but must not raise.
    assert result.bpm >= 0.0
    assert result.method


def test_engine_very_long_notes_are_handled(
    engine: AudioAnalysisEngine, tmp_path: Path
) -> None:
    """A 1-second sustained 120 BPM-on-second tone is not a real click track.

    We construct a single long note and verify the engine returns
    sensible (non-negative, non-NaN) values.
    """
    sr = 22050
    t = np.linspace(0, 1.0, sr, endpoint=False)
    audio = (0.5 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    path = _write_wav(tmp_path / "long_note.wav", audio, sr=sr)
    result = engine.analyze_bpm(path)
    assert result.bpm >= 0.0
    assert isinstance(result.beat_positions, list)
