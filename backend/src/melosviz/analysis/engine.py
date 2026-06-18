"""Audio analysis engine for Melosviz."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import librosa
import numpy as np
import soundfile as sf

from melosviz.analysis.models import (
    AnalysisResult,
    AnalyzeRequest,
    AnalysisType,
    BPMResult,
    DetectResult,
    FrequencyResult,
    NoteStream,
    WaveformResult,
)

logger = logging.getLogger(__name__)


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
            raise AudioDecodeError(f"Error opening '{source}': {exc}") from None
        if audio.size == 0:
            raise AudioDecodeError(f"Error opening '{source}': empty audio file")
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


    def detect(self, source: NoteStream | list[int]) -> DetectResult:
        """Detect chord and scale from MIDI note input.

        Accepts either a :class:`NoteStream` (notes extracted from a MIDI file)
        or a plain list of MIDI note numbers.  Returns a :class:`DetectResult`
        containing the unique ``note_set``, the detected ``chord_set``, and the
        detected ``scale_set``.
        """
        if isinstance(source, NoteStream):
            note_numbers = sorted({n.pitch for n in source.notes})
        else:
            note_numbers = sorted({int(n) for n in source})
        return DetectResult(
            note_set=note_numbers,
            chord_set=detect_chord(note_numbers),
            scale_set=detect_scale(note_numbers),
        )


# ---------------------------------------------------------------------------
# Note / chord / scale helpers
# ---------------------------------------------------------------------------

# A4 = 440 Hz, MIDI note 69
_A4_MIDI: int = 69
_A4_FREQ: float = 440.0

# Semitone offsets for common chord qualities (relative to root)
_CHORD_TEMPLATES: dict[str, tuple[int, ...]] = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "diminished": (0, 3, 6),
    "augmented": (0, 4, 8),
    "major7": (0, 4, 7, 11),
    "minor7": (0, 3, 7, 10),
    "dominant7": (0, 4, 7, 10),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
}

# Semitone offsets for common scales (relative to root)
_SCALE_TEMPLATES: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "natural_minor": (0, 2, 3, 5, 7, 8, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
    "melodic_minor": (0, 2, 3, 5, 7, 9, 11),
    "pentatonic_major": (0, 2, 4, 7, 9),
    "pentatonic_minor": (0, 3, 5, 7, 10),
    "blues": (0, 3, 5, 6, 7, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
    "chromatic": (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
}

# Note name lookup (0 = C, 1 = C#, 2 = D, ...)
_NOTE_NAMES: tuple[str, ...] = (
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"
)


def freq_to_note_number(freq_hz: float) -> int:
    """Return the nearest MIDI note number for a given frequency in Hz.

    Uses the standard 12-tone equal temperament formula:
    ``note = 69 + 12 * log2(freq / 440)``.
    """
    if freq_hz <= 0.0:
        return 0
    return int(round(_A4_MIDI + 12.0 * np.log2(freq_hz / _A4_FREQ)))


def note_number_to_freq(note_number: int) -> float:
    """Return the frequency in Hz for a given MIDI note number."""
    return _A4_FREQ * (2.0 ** ((note_number - _A4_MIDI) / 12.0))


def note_name_from_number(note_number: int) -> str:
    """Return the canonical note name (e.g. ``"C#4"``) for a MIDI note number."""
    note_number = int(np.clip(note_number, 0, 127))
    octave = (note_number // 12) - 1
    return f"{_NOTE_NAMES[note_number % 12]}{octave}"


def detect_chord(notes: list[int]) -> str | None:
    """Return a chord name (e.g. ``"C major"``) from a list of MIDI note numbers.

    The implementation normalises notes to pitch classes (0-11), then uses the
    *lowest* note in the input as the primary root candidate (musically, the
    root of a chord is usually the lowest sounding note). If no template fits
    with the lowest note as root, the algorithm falls back to scanning every
    other root and picks the chord with the most matched pitch classes and
    fewest spurious extras. Returns ``None`` if no template has at least
    three required notes in the input.
    """
    if not notes:
        return None
    pitch_classes = {n % 12 for n in notes}
    if len(pitch_classes) < 3:
        return None
    lowest_root = min(n % 12 for n in notes)
    qualities = list(_CHORD_TEMPLATES.keys())

    def _score_candidate(root: int, quality_idx: int) -> tuple[int, int] | None:
        template = qualities[quality_idx]
        required = {(root + interval) % 12 for interval in _CHORD_TEMPLATES[template]}
        if not required.issubset(pitch_classes):
            return None
        matched = len(required)
        extras = len(pitch_classes - required)
        # Bonus for using the lowest note as root (musical convention).
        root_bonus = 1 if root == lowest_root else 0
        return (matched + root_bonus, -extras)

    best: tuple[int, int] | None = None
    best_score: tuple[int, int] = (0, 0)
    # Pass 1: try lowest note as root, scanning all qualities.
    for quality_idx in range(len(qualities)):
        score = _score_candidate(lowest_root, quality_idx)
        if score is not None and score > best_score:
            best_score = score
            best = (lowest_root, quality_idx)
    # Pass 2: scan every (root, quality) pair, skipping the already-tested
    # (lowest_root, *) combinations to find enharmonically correct inversions.
    for root in range(12):
        for quality_idx in range(len(qualities)):
            if root == lowest_root:
                continue
            score = _score_candidate(root, quality_idx)
            if score is not None and score > best_score:
                best_score = score
                best = (root, quality_idx)
    if best is None or best_score[0] < 3:
        return None
    root, quality_idx = best
    return f"{_NOTE_NAMES[root]} {qualities[quality_idx]}"


def detect_scale(notes: list[int]) -> str | None:
    """Return a scale name (e.g. ``"C major"``) from a list of MIDI note numbers.

    The implementation normalises notes to pitch classes, uses the *lowest*
    note as the root candidate (so the reported name is the one a musician
    would call the scale), and accepts the first scale template that fits
    as a subset of the input. Returns ``None`` if the input has fewer than
    three pitch classes or no template is a subset of the input.
    """
    if not notes:
        return None
    pitch_classes = {n % 12 for n in notes}
    if len(pitch_classes) < 3:
        return None
    lowest_root = min(notes) % 12
    # Iterate templates from most specific (largest) to least, so that a
    # full chromatic scale is not reported as a C major scale, and a full
    # blues scale is not reported as C pentatonic minor.
    for scale_name, template in sorted(
        _SCALE_TEMPLATES.items(), key=lambda kv: -len(kv[1])
    ):
        required = {(lowest_root + interval) % 12 for interval in template}
        if required.issubset(pitch_classes):
            return f"{_NOTE_NAMES[lowest_root]} {scale_name}"
    return None


def notes_from_frequency_result(
    result: FrequencyResult, *, tolerance_hz: float = 20.0
) -> list[int]:
    """Extract unique MIDI note numbers from the dominant bins of a frequency result.

    Each dominant bin key is a string like ``"440.00"`` representing a frequency
    in Hz. The function converts each frequency to a MIDI note number and returns
    a sorted list of unique notes.
    """
    notes: set[int] = set()
    for freq_label in result.dominant_bins:
        try:
            freq_hz = float(freq_label)
        except ValueError:
            continue
        note = freq_to_note_number(freq_hz)
        if note > 0:
            notes.add(note)
    return sorted(notes)


def notes_from_waveform(
    audio: np.ndarray, sr: int, *, threshold: float = 0.01
) -> list[int]:
    """Extract note candidates from a time-domain audio signal using autocorrelation.

    This is a simple, robust pitch estimator suitable for unit testing. A more
    sophisticated implementation would use YIN or FFT-based pitch tracking.
    """
    if audio.size < 2:
        return []
    # Normalise
    audio = audio.astype(np.float64)
    peak = np.max(np.abs(audio))
    if peak < threshold:
        return []
    audio = audio / peak
    # Autocorrelation
    corr = np.correlate(audio, audio, mode="full")
    corr = corr[len(corr) // 2 :]
    # Find first peak after the zero-lag trough
    if corr.size < 2:
        return []
    # Skip the first few lags to avoid the zero-lag peak
    min_lag = max(1, int(sr / 4000))  # max 4 kHz
    max_lag = min(len(corr), int(sr / 20))  # min 20 Hz
    if max_lag <= min_lag:
        return []
    peak_idx = int(np.argmax(corr[min_lag:max_lag])) + min_lag
    if peak_idx <= 0:
        return []
    freq_hz = float(sr) / peak_idx
    if freq_hz <= 0:
        return []
    note = freq_to_note_number(freq_hz)
    return [note] if 0 <= note <= 127 else []
