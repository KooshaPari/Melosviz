"""Lightweight audio analysis helpers for render preparation.

The upstream project likely has a richer DSP stack, but this repo only
needs a dependency-free bridge from a PCM WAV file to a populated
``RenderSpec`` so the render path can be exercised end-to-end.

Onset detection uses a simple peak-picking heuristic on the RMS envelope.
Harmonic analysis derives MIDI note numbers from dominant spectral peaks
computed via a sliding DFT over 16 frequency buckets, then maps those
notes to chord and scale names using interval matching.
"""

from __future__ import annotations

import audioop
import math
import wave
from array import array
from dataclasses import dataclass, field
from pathlib import Path

from .models import HarmonicResult, RenderSpec

# ---------------------------------------------------------------------------
# Note / chord / scale helpers (stdlib-only; mirrors engine.py when present)
# ---------------------------------------------------------------------------

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_CHORD_INTERVALS: dict[tuple[int, ...], str] = {
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

_SCALE_INTERVALS: dict[tuple[int, ...], str] = {
    (0, 2, 4, 5, 7, 9, 11): "major",
    (0, 2, 3, 5, 7, 8, 10): "minor",
    (0, 2, 3, 5, 7, 8, 11): "harmonic minor",
    (0, 2, 3, 5, 7, 9, 11): "melodic minor",
    (0, 2, 4, 5, 7, 9, 10): "mixolydian",
    (0, 2, 3, 5, 7, 9, 10): "dorian",
    (0, 1, 3, 5, 7, 8, 10): "phrygian",
}


def _freq_to_note(freq_hz: float) -> int:
    """Return the nearest MIDI note number for *freq_hz*."""
    if freq_hz <= 0.0:
        return 0
    return max(0, round(69.0 + 12.0 * math.log2(freq_hz / 440.0)))


def detect_chord(note_numbers: list[int]) -> str | None:
    """Return a chord name (e.g. ``C major``) or ``None``."""
    pcs = {n % 12 for n in note_numbers}
    if len(pcs) < 3:
        return None
    for root in sorted(pcs):
        intervals = tuple(sorted((pc - root) % 12 for pc in pcs))
        if intervals in _CHORD_INTERVALS:
            return f"{_NOTE_NAMES[root]} {_CHORD_INTERVALS[intervals]}"
    return None


def detect_scale(note_numbers: list[int]) -> str | None:
    """Return a scale name (e.g. ``A minor``) or ``None``."""
    pcs = {n % 12 for n in note_numbers}
    if len(pcs) < 3:
        return None
    for root in sorted(pcs):
        intervals = tuple(sorted((pc - root) % 12 for pc in pcs))
        if intervals in _SCALE_INTERVALS:
            return f"{_NOTE_NAMES[root]} {_SCALE_INTERVALS[intervals]}"
    return None


def _goertzel(samples: list[float], sample_rate: int, freq_hz: float) -> float:
    """Return the power of *freq_hz* in *samples* via the Goertzel algorithm."""
    n = len(samples)
    if n == 0:
        return 0.0
    k = freq_hz * n / sample_rate
    omega = 2.0 * math.pi * k / n
    coeff = 2.0 * math.cos(omega)
    s_prev2 = 0.0
    s_prev1 = 0.0
    for sample in samples:
        s = sample + coeff * s_prev1 - s_prev2
        s_prev2 = s_prev1
        s_prev1 = s
    # power = s_prev1² + s_prev2² − coeff·s_prev1·s_prev2
    return s_prev1 ** 2 + s_prev2 ** 2 - coeff * s_prev1 * s_prev2


# Musical note frequencies from C2 (65 Hz) to B4 (988 Hz) — 36 pitches.
_ANALYSIS_FREQS: list[float] = [
    440.0 * (2.0 ** ((note - 69) / 12.0))
    for note in range(36, 72)  # C2 to B4
]


def _harmonic_from_samples(
    samples: list[float], sample_rate: int
) -> HarmonicResult:
    """Detect chord and scale from a float PCM sample block."""
    if not samples or sample_rate <= 0:
        return HarmonicResult()
    powers = [
        (_goertzel(samples, sample_rate, freq), freq)
        for freq in _ANALYSIS_FREQS
    ]
    # Pick the top-8 spectral peaks by power.
    powers.sort(key=lambda t: t[0], reverse=True)
    top_freqs = [freq for _, freq in powers[:8]]
    note_numbers = sorted({_freq_to_note(f) for f in top_freqs})
    return HarmonicResult(
        chord=detect_chord(note_numbers),
        scale=detect_scale(note_numbers),
        note_numbers=note_numbers,
    )


def _pick_onsets(
    envelope: list[float],
    duration_sec: float,
    threshold: float = 0.65,
    min_gap_sec: float = 0.1,
) -> list[float]:
    """Return onset times (seconds) from a normalised RMS envelope.

    A sample is an onset if it exceeds *threshold* and is at least
    *min_gap_sec* beyond the previous accepted onset.
    """
    if not envelope or duration_sec <= 0.0:
        return []
    bucket_sec = duration_sec / len(envelope)
    min_gap_buckets = max(1, int(min_gap_sec / bucket_sec))
    onsets: list[float] = []
    last_onset_idx = -min_gap_buckets - 1
    for idx, value in enumerate(envelope):
        if value > threshold and (idx - last_onset_idx) >= min_gap_buckets:
            onsets.append(round(idx * bucket_sec, 4))
            last_onset_idx = idx
    return onsets


@dataclass(slots=True)
class AudioAnalysis:
    """Compact summary of a WAV file used to seed a render."""

    sample_rate: int
    channels: int
    duration_sec: float
    rms_envelope: list[float]
    peak_rms: float
    estimated_bpm: float | None
    # Onset times in seconds derived from peak-picking on the RMS envelope.
    onset_times: list[float] = field(default_factory=list)
    # Harmonic analysis (chord / scale / note numbers).
    harmonic: HarmonicResult = field(default_factory=HarmonicResult)


def _normalize_samples(samples: array) -> list[float]:
    if not samples:
        return [0.0]
    peak = max(abs(value) for value in samples) or 1
    return [abs(value) / peak for value in samples]


def analyze_wav(path: str | Path, bucket_count: int = 120) -> AudioAnalysis:
    """Analyze a PCM WAV file with standard-library tooling only.

    Returns an :class:`AudioAnalysis` that now includes:

    * ``onset_times`` — peak-picked onset positions in seconds derived from
      the normalised RMS envelope.
    * ``harmonic`` — a :class:`~melosviz.analysis.models.HarmonicResult`
      containing chord/scale labels and the dominant MIDI note numbers
      computed from spectral Goertzel analysis of the first 2 s of audio.
    """
    wav_path = Path(path)
    with wave.open(str(wav_path), "rb") as handle:
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        frame_count = handle.getnframes()
        duration_sec = frame_count / float(sample_rate or 1)
        raw = handle.readframes(frame_count)
        sample_width = handle.getsampwidth()

    if sample_width not in (1, 2, 4):
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    mono = (
        audioop.tomono(raw, sample_width, 1.0, 1.0) if channels == 2 else raw
    )
    # segment_size must be a multiple of sample_width so audioop.rms receives
    # whole frames only (audioop raises on partial frames).
    raw_segment = max(1, len(mono) // max(1, bucket_count))
    segment_size = max(sample_width, (raw_segment // sample_width) * sample_width)
    envelope: list[float] = []
    peak_rms = 0.0
    for index in range(0, len(mono), segment_size):
        segment = mono[index : index + segment_size]
        if not segment:
            continue
        rms = audioop.rms(segment, sample_width)
        peak_rms = max(peak_rms, float(rms))
        envelope.append(float(rms))
    normalized = _normalize_samples(array("f", envelope))
    bpm = None
    if duration_sec > 0 and len(normalized) > 4:
        hits = sum(1 for value in normalized if value > 0.65)
        bpm = round((hits / duration_sec) * 60.0, 2)

    # --- onset detection via RMS peak-picking ---
    onset_times = _pick_onsets(normalized, duration_sec)

    # --- harmonic analysis: decode mono PCM to float for Goertzel ---
    max_analysis_frames = sample_rate * 2  # analyse first 2 s max
    analysis_raw = mono[: max_analysis_frames * sample_width]
    if sample_width == 2:
        # 16-bit signed PCM → float in [-1, 1]
        fmt_size = 2
        count = len(analysis_raw) // fmt_size
        float_samples = [
            int.from_bytes(
                analysis_raw[i * fmt_size : (i + 1) * fmt_size],
                "little",
                signed=True,
            )
            / 32768.0
            for i in range(count)
        ]
    elif sample_width == 1:
        float_samples = [b / 128.0 - 1.0 for b in analysis_raw]
    else:
        # 32-bit: treat as 4-byte signed int
        fmt_size = 4
        count = len(analysis_raw) // fmt_size
        float_samples = [
            int.from_bytes(
                analysis_raw[i * fmt_size : (i + 1) * fmt_size],
                "little",
                signed=True,
            )
            / 2147483648.0
            for i in range(count)
        ]
    harmonic = _harmonic_from_samples(float_samples, sample_rate)

    return AudioAnalysis(
        sample_rate=sample_rate,
        channels=channels,
        duration_sec=duration_sec,
        rms_envelope=normalized,
        peak_rms=peak_rms,
        estimated_bpm=bpm,
        onset_times=onset_times,
        harmonic=harmonic,
    )


def spec_from_wav(path: str | Path) -> RenderSpec:
    """Build a ``RenderSpec`` from a WAV file analysis.

    The returned spec is populated with:

    * ``metadata`` — source audio properties plus the new ``onset_times``,
      ``chord``, and ``scale`` keys derived from :func:`analyze_wav`.
    * ``timeline`` — one ``{"time": t, "type": "onset"}`` entry per detected
      onset, suitable for downstream keyframe / cue rendering.
    """
    analysis = analyze_wav(path)
    spec = RenderSpec(
        metadata={
            "source_audio": str(Path(path)),
            "sample_rate": analysis.sample_rate,
            "channels": analysis.channels,
            "duration": analysis.duration_sec,
            "fps": 30,
            "width": 1280,
            "height": 720,
            "analysis_peak_rms": analysis.peak_rms,
            "estimated_bpm": analysis.estimated_bpm,
            "amplitude_envelope": analysis.rms_envelope,
            # --- new harmonic / onset fields ---
            "onset_times": analysis.onset_times,
            "chord": analysis.harmonic.chord,
            "scale": analysis.harmonic.scale,
            "harmonic_notes": analysis.harmonic.note_numbers,
        },
        timeline=[
            {"time": t, "type": "onset", "data": {"strength": 0.75}}
            for t in analysis.onset_times
        ],
    )
    return spec


__all__ = [
    "AudioAnalysis",
    "analyze_wav",
    "detect_chord",
    "detect_scale",
    "spec_from_wav",
]
