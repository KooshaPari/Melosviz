"""Property-based tests for melosviz backend invariants.

Uses `hypothesis` to generate inputs and verify that core functions and
models maintain their contracts across a wide range of edge-cases.
"""

from __future__ import annotations

import math
import tempfile
import wave
import struct
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from melosviz.analysis.engine import (
    AudioAnalysisEngine,
    detect_chord,
    detect_scale,
    freq_to_note_number,
    note_name_from_number,
    note_number_to_freq,
    notes_from_frequency_result,
)
from melosviz.analysis.models import (
    AnalysisResult,
    AnalysisType,
    AnalyzeRequest,
    BPMResult,
    FrequencyResult,
    GenreTheme,
    Note,
    NoteStream,
    RenderSpec,
    RenderStyle,
    WaveformResult,
)
from melosviz.render.spec_builder import build_spec, render_spec_from_json, render_spec_to_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_test_wav(path: Path, sample_rate: int, duration: float, frequency: float) -> None:
    """Write a simple sine-wave WAV file."""
    total_frames = int(sample_rate * duration)
    amplitude = 0.35
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for i in range(total_frames):
            sample = int(amplitude * 32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
            wav_file.writeframes(struct.pack("<h", sample))


# ---------------------------------------------------------------------------
# Note / frequency invariants
# ---------------------------------------------------------------------------


class TestNoteFrequencyInvariants:
    """Invariants for the note<->frequency conversion helpers."""

    @given(st.floats(min_value=20.0, max_value=20000.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=20)
    def test_freq_to_note_number_is_integer(self, freq_hz: float) -> None:
        """freq_to_note_number always returns an integer (no crash)."""
        note = freq_to_note_number(freq_hz)
        assert isinstance(note, int)
        assert note >= 0

    @given(st.integers(min_value=0, max_value=127))
    @settings(max_examples=20)
    def test_note_number_to_freq_roundtrip(self, note_number: int) -> None:
        """Converting a note -> freq -> note should land within one semitone."""
        freq = note_number_to_freq(note_number)
        back = freq_to_note_number(freq)
        assert abs(back - note_number) <= 1

    @given(st.integers(min_value=0, max_value=127))
    @settings(max_examples=20)
    def test_note_name_is_valid_format(self, note_number: int) -> None:
        """note_name_from_number always returns ``NameOctave`` for valid notes."""
        name = note_name_from_number(note_number)
        assert len(name) >= 2
        # Ends with an octave digit (-1 to 9)
        assert name[-1].isdigit() or name[-2:].isdigit()
        # Starts with a note letter
        assert name[0] in {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"}

    @given(st.integers(min_value=0, max_value=127))
    @settings(max_examples=20)
    def test_note_number_to_freq_is_positive(self, note_number: int) -> None:
        """note_number_to_freq always returns a positive frequency for valid notes."""
        freq = note_number_to_freq(note_number)
        assert freq > 0.0


# ---------------------------------------------------------------------------
# Chord / scale detection invariants
# ---------------------------------------------------------------------------


class TestChordScaleInvariants:
    """Invariants for chord and scale detection."""

    @given(st.lists(st.integers(min_value=0, max_value=127), min_size=0, max_size=20))
    @settings(max_examples=20)
    def test_detect_chord_never_crashes(self, notes: list[int]) -> None:
        """detect_chord must not raise on any valid MIDI note list."""
        result = detect_chord(notes)
        if result is not None:
            # Result should be a note name followed by a quality
            parts = result.split()
            assert len(parts) == 2
            assert parts[0] in {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"}
            assert parts[1] in {
                "major", "minor", "diminished", "augmented",
                "major7", "minor7", "dominant7", "sus2", "sus4",
            }

    @given(st.lists(st.integers(min_value=0, max_value=127), min_size=0, max_size=20))
    @settings(max_examples=20)
    def test_detect_scale_never_crashes(self, notes: list[int]) -> None:
        """detect_scale must not raise on any valid MIDI note list."""
        result = detect_scale(notes)
        if result is not None:
            parts = result.split()
            assert len(parts) >= 2
            assert parts[0] in {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"}

    @given(st.lists(st.integers(min_value=0, max_value=127), min_size=0, max_size=5))
    @settings(max_examples=20)
    def test_detect_chord_returns_none_for_few_pitch_classes(self, notes: list[int]) -> None:
        """Fewer than 3 distinct pitch classes should always return None."""
        pitch_classes = {n % 12 for n in notes}
        if len(pitch_classes) < 3:
            assert detect_chord(notes) is None

    @given(st.lists(st.integers(min_value=0, max_value=127), min_size=0, max_size=5))
    @settings(max_examples=20)
    def test_detect_scale_returns_none_for_few_pitch_classes(self, notes: list[int]) -> None:
        """Fewer than 3 distinct pitch classes should always return None."""
        pitch_classes = {n % 12 for n in notes}
        if len(pitch_classes) < 3:
            assert detect_scale(notes) is None


# ---------------------------------------------------------------------------
# Pydantic model invariants
# ---------------------------------------------------------------------------


class TestModelInvariants:
    """Invariants for Pydantic models used across the API."""

    @given(
        st.integers(min_value=256, max_value=16384),
        st.integers(min_value=128, max_value=8192),
    )
    @settings(max_examples=20)
    def test_analyze_request_validates_fft_hop(self, fft_size: int, hop_size: int) -> None:
        """hop_size must be strictly smaller than fft_size."""
        if hop_size >= fft_size:
            with pytest.raises(ValueError):
                AnalyzeRequest(fft_size=fft_size, hop_size=hop_size)
        else:
            req = AnalyzeRequest(fft_size=fft_size, hop_size=hop_size)
            assert req.hop_size < req.fft_size

    @given(
        st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=20)
    def test_bpm_result_bounds(self, bpm: float, confidence: float, stability: float) -> None:
        """BPMResult enforces confidence and stability in [0, 1]."""
        result = BPMResult(
            bpm=bpm,
            confidence=confidence,
            stability=stability,
            beat_positions=[0.0, 0.5, 1.0],
        )
        assert 0.0 <= result.confidence <= 1.0
        assert 0.0 <= result.stability <= 1.0
        assert result.bpm >= 0.0

    @given(
        st.integers(min_value=0, max_value=127),
        st.floats(min_value=0.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, allow_nan=False, allow_infinity=False),
        st.integers(min_value=0, max_value=127),
    )
    @settings(max_examples=20)
    def test_note_invariants(self, pitch: int, start: float, duration: float, velocity: int) -> None:
        """Note model clamps pitch and velocity to MIDI range [0, 127]."""
        note = Note(pitch=pitch, start=start, duration=duration, velocity=velocity)
        assert 0 <= note.pitch <= 127
        assert 0 <= note.velocity <= 127
        assert note.start >= 0.0
        assert note.duration >= 0.0

    @given(st.lists(st.integers(min_value=0, max_value=127), min_size=0, max_size=50))
    @settings(max_examples=20)
    def test_note_stream_sorts_and_counts(self, pitches: list[int]) -> None:
        """NoteStream should contain exactly the notes we put in."""
        notes = [Note(pitch=p, start=0.0, duration=1.0, velocity=80) for p in pitches]
        stream = NoteStream(notes=notes)
        assert len(stream) == len(pitches)

    @given(st.lists(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False), min_size=0, max_size=5))
    @settings(max_examples=20)
    def test_render_spec_roundtrip(self, colors: list[float]) -> None:
        """RenderSpec should round-trip through JSON without loss."""
        hex_colors = [f"#{int(c * 255):02x}{int(c * 255):02x}{int(c * 255):02x}" for c in colors]
        spec = RenderSpec(
            palette=hex_colors,
            shots=[],
            timeline=[],
            layers=[],
            keyframes=[],
        )
        json_str = render_spec_to_json(spec)
        restored = render_spec_from_json(json_str)
        assert restored.palette == spec.palette


# ---------------------------------------------------------------------------
# Analysis engine invariants
# ---------------------------------------------------------------------------


class TestAnalysisEngineInvariants:
    """Invariants for the AudioAnalysisEngine."""

    @given(
        st.integers(min_value=8000, max_value=48000),
        st.floats(min_value=0.1, max_value=0.5, allow_nan=False, allow_infinity=False),
        st.floats(min_value=200.0, max_value=2000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=3, deadline=5000)
    def test_analyze_waveform_invariants(self, sample_rate: int, duration: float, frequency: float) -> None:
        """Waveform analysis must return non-negative peak amplitude and bounded samples."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "sine.wav"
            _write_test_wav(audio_path, sample_rate, duration, frequency)
            engine = AudioAnalysisEngine()
            result = engine.analyze_waveform(str(audio_path))
            assert result.peak_amplitude >= 0.0
            assert len(result.samples) == 512
            assert all(-1.0 <= s <= 1.0 for s in result.samples)
            assert result.duration > 0.0
            assert result.sample_rate > 0

    @given(
        st.integers(min_value=8000, max_value=48000),
        st.floats(min_value=0.5, max_value=1.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=60.0, max_value=180.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=3, deadline=5000)
    def test_analyze_bpm_invariants(self, sample_rate: int, duration: float, bpm: float) -> None:
        """BPM analysis must return non-negative BPM and sorted beat positions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Generate a click track
            total_frames = int(sample_rate * duration)
            audio = np.zeros(total_frames, dtype=np.float32)
            beat_interval = 60.0 / bpm
            beat_width = max(1, int(0.001 * 60 * sample_rate))
            window = np.hanning(beat_width).astype(np.float32)
            for beat in np.arange(0.0, duration, beat_interval):
                idx = int(beat * sample_rate)
                end = min(idx + beat_width, audio.shape[0])
                audio[idx:end] += 0.8 * window[: end - idx]
            audio_path = Path(tmpdir) / "click.wav"
            import soundfile as sf
            sf.write(str(audio_path), audio, sample_rate)
            engine = AudioAnalysisEngine()
            result = engine.analyze_bpm(str(audio_path))
            assert result.bpm >= 0.0
            assert 0.0 <= result.confidence <= 1.0
            assert 0.0 <= result.stability <= 1.0
            assert result.beat_positions == sorted(result.beat_positions)
            assert all(bp >= 0.0 for bp in result.beat_positions)

    @given(
        st.integers(min_value=8000, max_value=48000),
        st.floats(min_value=0.1, max_value=0.5, allow_nan=False, allow_infinity=False),
        st.floats(min_value=200.0, max_value=2000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=3, deadline=5000)
    def test_analyze_frequency_invariants(self, sample_rate: int, duration: float, frequency: float) -> None:
        """Frequency analysis must return non-negative peak frequency."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "sine.wav"
            _write_test_wav(audio_path, sample_rate, duration, frequency)
            engine = AudioAnalysisEngine()
            result = engine.analyze_frequency(str(audio_path))
            assert result.peak_frequency_hz >= 0.0
            assert result.spectral_centroid >= 0.0
            assert result.spectral_rolloff >= 0.0
            assert result.spectral_flatness >= 0.0
            assert len(result.dominant_bins) <= 8


# ---------------------------------------------------------------------------
# Frequency -> notes invariant
# ---------------------------------------------------------------------------


class TestFrequencyToNotesInvariants:
    """Invariants for notes_from_frequency_result."""

    @given(
        st.dictionaries(
            st.sampled_from([f"{f:.2f}" for f in range(20, 20000, 100)]),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=0,
            max_size=10,
        )
    )
    @settings(max_examples=20)
    def test_notes_from_frequency_result_sorted_unique(self, dominant_bins: dict[str, float]) -> None:
        """notes_from_frequency_result always returns sorted unique MIDI notes."""
        result = FrequencyResult(
            peak_frequency_hz=440.0,
            spectral_centroid=440.0,
            spectral_rolloff=440.0,
            spectral_flatness=0.5,
            dominant_bins=dominant_bins,
        )
        notes = notes_from_frequency_result(result)
        assert notes == sorted(notes)
        assert len(notes) == len(set(notes))


# ---------------------------------------------------------------------------
# Build spec invariant
# ---------------------------------------------------------------------------


class TestSpecBuilderInvariants:
    """Invariants for the render spec builder."""

    @given(
        st.floats(min_value=1.0, max_value=300.0, allow_nan=False, allow_infinity=False),
        st.integers(min_value=1, max_value=8),
        st.integers(min_value=8000, max_value=96000),
    )
    @settings(max_examples=10, deadline=None)
    def test_build_spec_returns_valid_render_spec(self, duration: float, channels: int, sample_rate: int) -> None:
        """build_spec must always return a valid RenderSpec for any AnalysisResult."""
        analysis = AnalysisResult(
            duration_seconds=duration,
            sample_rate=sample_rate,
            channels=channels,
            analysis=AnalysisType.FULL,
            bpm=BPMResult(
                bpm=120.0,
                confidence=0.8,
                beat_positions=[0.0, 0.5, 1.0, 1.5],
                stability=0.9,
            ),
            waveform=WaveformResult(
                samples=[0.0] * 512,
                peak_amplitude=0.5,
                rms_db=-20.0,
                duration=duration,
                sample_rate=sample_rate,
            ),
            frequency=FrequencyResult(
                peak_frequency_hz=440.0,
                spectral_centroid=440.0,
                spectral_rolloff=800.0,
                spectral_flatness=0.5,
            ),
        )
        spec = build_spec(analysis)
        assert isinstance(spec, RenderSpec)
        assert spec.metadata is not None
        assert spec.shots is not None
        assert spec.timeline is not None
        # Shot times must not exceed duration
        for shot in spec.shots:
            assert shot.start_time <= duration + 0.001
            assert shot.end_time <= duration + 0.001

    @given(
        st.floats(min_value=0.1, max_value=300.0, allow_nan=False, allow_infinity=False),
        st.integers(min_value=1, max_value=8),
        st.integers(min_value=8000, max_value=96000),
    )
    @settings(max_examples=10, deadline=None)
    def test_render_spec_json_roundtrip(self, duration: float, channels: int, sample_rate: int) -> None:
        """RenderSpec JSON round-trip should preserve structure."""
        analysis = AnalysisResult(
            duration_seconds=duration,
            sample_rate=sample_rate,
            channels=channels,
            analysis=AnalysisType.FULL,
            bpm=BPMResult(
                bpm=120.0,
                confidence=0.8,
                beat_positions=[0.0, 0.5, 1.0, 1.5],
                stability=0.9,
            ),
            waveform=WaveformResult(
                samples=[0.0] * 512,
                peak_amplitude=0.5,
                rms_db=-20.0,
                duration=duration,
                sample_rate=sample_rate,
            ),
            frequency=FrequencyResult(
                peak_frequency_hz=440.0,
                spectral_centroid=440.0,
                spectral_rolloff=800.0,
                spectral_flatness=0.5,
            ),
        )
        spec = build_spec(analysis)
        json_str = render_spec_to_json(spec)
        restored = render_spec_from_json(json_str)
        assert restored.metadata == spec.metadata
        assert restored.palette == spec.palette
        assert len(restored.shots) == len(spec.shots)
        assert len(restored.timeline) == len(spec.timeline)
