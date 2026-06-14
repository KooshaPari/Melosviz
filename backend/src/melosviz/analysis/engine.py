"""Audio analysis engine for Melosviz."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
import soundfile as sf

from melosviz.analysis.models import (
    AnalysisResult,
    AnalyzeRequest,
    AnalysisType,
    BPMResult,
    FrequencyResult,
    WaveformResult,
)

logger = logging.getLogger(__name__)

# --- note / chord / scale helpers ---

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_CHORD_INTERVALS = {
    (0, 4, 7): "major",
    (0, 3, 7): "minor",
    (0, 3, 6): "diminished",
    (0, 4, 8): "augmented",
    (0, 4, 7, 11): "major7",
    (0, 3, 7, 10): "minor7",
    (0, 4, 7, 10): "dominant7",
    (0, 2, 7): "sus2",
    (0, 5, 7): "sus4",
}

_SCALE_INTERVALS = {
    (0, 2, 4, 5, 7, 9, 11): "major",
    (0, 2, 3, 5, 7, 8, 10): "minor",
    (0, 2, 3, 5, 7, 8, 11): "harmonic minor",
    (0, 2, 3, 5, 7, 9, 11): "melodic minor",
    (0, 2, 3, 5, 7, 9, 10): "dorian",
    (0, 2, 4, 5, 7, 9, 10): "mixolydian",
    (0, 1, 3, 5, 7, 8, 10): "phrygian",
}


def freq_to_note_number(freq_hz: float) -> int:
    """Convert a frequency in Hz to the nearest MIDI note number."""
    if freq_hz <= 0:
        return 0
    return max(0, round(69.0 + 12.0 * math.log2(freq_hz / 440.0)))


def note_number_to_freq(note_number: int) -> float:
    """Convert a MIDI note number to its frequency in Hz."""
    return 440.0 * (2.0 ** ((note_number - 69) / 12.0))


def note_name_from_number(note_number: int) -> str:
    """Return the canonical note name (e.g. ``C#4``) for a MIDI note number."""
    note_number = max(0, min(127, note_number))
    name = _NOTE_NAMES[note_number % 12]
    octave = (note_number // 12) - 1
    return f"{name}{octave}"


def _pitch_classes(notes: list[int]) -> set[int]:
    return {n % 12 for n in notes}


def _canonical_intervals(pitch_classes: set[int]) -> tuple[int, ...] | None:
    if len(pitch_classes) < 3:
        return None
    for root in sorted(pitch_classes):
        intervals = tuple(sorted((pc - root) % 12 for pc in pitch_classes))
        if intervals in _CHORD_INTERVALS:
            return intervals
        if intervals in _SCALE_INTERVALS:
            return intervals
    return None


def detect_chord(notes: list[int]) -> str | None:
    """Return a chord name (e.g. ``C major``) or ``None``."""
    pcs = _pitch_classes(notes)
    if len(pcs) < 3:
        return None
    for root in sorted(pcs):
        intervals = tuple(sorted((pc - root) % 12 for pc in pcs))
        if intervals in _CHORD_INTERVALS:
            return f"{_NOTE_NAMES[root]} {_CHORD_INTERVALS[intervals]}"
    return None


def detect_scale(notes: list[int]) -> str | None:
    """Return a scale name (e.g. ``C major``) or ``None``."""
    pcs = _pitch_classes(notes)
    if len(pcs) < 3:
        return None
    for root in sorted(pcs):
        intervals = tuple(sorted((pc - root) % 12 for pc in pcs))
        if intervals in _SCALE_INTERVALS:
            return f"{_NOTE_NAMES[root]} {_SCALE_INTERVALS[intervals]}"
    return None


def notes_from_frequency_result(freq_result: FrequencyResult) -> list[int]:
    """Return sorted unique MIDI note numbers extracted from dominant bins."""
    notes: set[int] = set()
    for freq_str in freq_result.dominant_bins:
        try:
            freq = float(freq_str)
        except ValueError:
            continue
        notes.add(freq_to_note_number(freq))
    return sorted(notes)


class AudioDecodeError(RuntimeError):
    """Raised when an uploaded audio file cannot be decoded."""


@dataclass(slots=True)
class _AudioData:
    """Internal container for decoded audio."""

    y: np.ndarray
    sr: int
    channels: int

    @property
    def duration(self) -> float:
        if self.sr > 0:
            return float(self.y.shape[0]) / self.sr
        return 0.0


class AudioAnalysisEngine:
    """Analyze uploaded audio files into structured analysis results."""

    def _load_audio(self, source: str | Path) -> _AudioData:
        """Load and normalise an audio file for analysis."""
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {source}")
        try:
            audio, sample_rate = sf.read(
                str(path), always_2d=True, dtype="float32"
            )
        except (sf.LibsndfileError, RuntimeError, ValueError, OSError, EOFError) as exc:
            raise AudioDecodeError(f"Unable to decode audio file: {exc}") from None
        if audio.size == 0:
            raise AudioDecodeError(f"Unable to decode audio file: empty audio file")
        channels = int(audio.shape[1])
        if channels > 1:
            mono = np.mean(audio, axis=1, dtype=np.float32)
        else:
            mono = audio.astype(np.float32, copy=False).ravel()
        return _AudioData(y=mono, sr=sample_rate, channels=channels)

    def _analysis_window(self, y: np.ndarray, sr: int, window_ms: int = 50) -> int:
        window_size = int(sr * window_ms / 1000.0)
        return max(1, window_size)

    def analyze_waveform(self, source: str | Path, window_ms: int = 50) -> WaveformResult:
        """Extract waveform summary for the given audio file."""
        audio = self._load_audio(source)
        window = self._analysis_window(audio.y, audio.sr, window_ms)
        peak = float(np.max(np.abs(audio.y)))
        rms = np.sqrt(np.mean(np.square(audio.y)))
        rms_db = 20.0 * np.log10(max(rms, 1e-12))
        target_len = 512
        sample_positions = np.linspace(0, len(audio.y) - 1, num=target_len, dtype=np.float32)
        samples = np.interp(sample_positions, np.arange(len(audio.y)), audio.y).astype(np.float32).tolist()
        return WaveformResult(
            samples=samples,
            peak_amplitude=peak,
            rms_db=rms_db,
            duration=audio.duration,
            sample_rate=audio.sr,
        )

    def analyze_frequency(
        self, source: str | Path, fft_size: int = 2048, hop_size: int = 512
    ) -> FrequencyResult:
        """Extract frequency-domain summary for the given audio file."""
        audio = self._load_audio(source)
        y = audio.y
        n_fft = min(len(y), fft_size)
        if n_fft < 256:
            n_fft = min(256, len(y))
        spectrum = np.fft.rfft(y, n=n_fft)
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / audio.sr)
        peak_index = int(np.argmax(np.abs(spectrum)))
        peak_frequency_hz = float(freqs[peak_index])
        spectral_centroid = float(librosa.feature.spectral_centroid(y=y, sr=audio.sr)[0, 0])
        spectral_rolloff = float(librosa.feature.spectral_rolloff(y=y, sr=audio.sr)[0, 0])
        spectral_flatness = float(librosa.feature.spectral_flatness(y=y)[0, 0])
        top_indices = np.argsort(np.abs(spectrum))[-8:][::-1]
        dominant_bins = {
            f"{freqs[idx]:.2f}": float(np.abs(spectrum[idx])) for idx in top_indices
        }
        S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop_size))
        spectrogram_list = S[: n_fft // 8, : n_fft // 8].tolist()
        return FrequencyResult(
            peak_frequency_hz=peak_frequency_hz,
            spectral_centroid=spectral_centroid,
            spectral_rolloff=spectral_rolloff,
            spectral_flatness=spectral_flatness,
            dominant_bins=dominant_bins,
            spectrogram=spectrogram_list,
        )

    def analyze_bpm(self, source: str | Path) -> BPMResult:
        """Extract tempo and beat positions for the given audio file."""
        audio = self._load_audio(source)
        onset_env = librosa.onset.onset_strength(y=audio.y, sr=audio.sr)
        tempo, beat_frames = librosa.beat.beat_track(
            y=audio.y, sr=audio.sr, onset_envelope=onset_env
        )
        tempo_value = float(tempo)
        beat_positions = librosa.frames_to_time(beat_frames, sr=audio.sr).tolist()
        if len(beat_frames) > 1:
            intervals = np.diff(beat_frames) / audio.sr
            mean_interval = float(np.mean(intervals))
            std_interval = float(np.std(intervals))
            stability = float(
                np.clip(1.0 - (std_interval / max(mean_interval, 1e-6)), 0.0, 1.0)
            )
            confidence = float(
                np.clip(1.0 - (std_interval / max(mean_interval, 1e-6)), 0.0, 1.0)
            )
        else:
            mean_interval = 0.0
            std_interval = 0.0
            stability = 0.0
            confidence = 0.0
        return BPMResult(
            bpm=tempo_value,
            confidence=confidence,
            beat_positions=beat_positions,
            downbeat_positions=[],
            onset_positions=[],
            stability=stability,
            method="librosa.beat.beat_track",
        )

    def full_analysis(
        self, source: str | Path, request: AnalyzeRequest | None = None
    ) -> AnalysisResult:
        """Run the full analysis pipeline or a subset based on *request*."""
        audio = self._load_audio(source)
        bpm: Optional[BPMResult] = None
        waveform: Optional[WaveformResult] = None
        frequency: Optional[FrequencyResult] = None
        if request is None:
            request = AnalyzeRequest()
        if request.analysis in (AnalysisType.BPM, AnalysisType.FULL) and request.include_bpm:
            bpm = self.analyze_bpm(source)
        if request.analysis in (AnalysisType.WAVEFORM, AnalysisType.FULL) and request.include_waveform:
            waveform = self.analyze_waveform(source, window_ms=request.window_ms)
        if request.analysis in (AnalysisType.FREQUENCY, AnalysisType.FULL) and request.include_spectrum:
            frequency = self.analyze_frequency(
                source, fft_size=request.fft_size, hop_size=request.hop_size
            )
        return AnalysisResult(
            duration_seconds=audio.duration,
            sample_rate=audio.sr,
            channels=audio.channels,
            analysis=request.analysis,
            bpm=bpm,
            waveform=waveform,
            frequency=frequency,
        )
