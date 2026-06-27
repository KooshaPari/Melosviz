"""Lightweight audio analysis helpers for render preparation.

The upstream project likely has a richer DSP stack, but this repo only
needs a dependency-free bridge from a PCM WAV file to a populated
``RenderSpec`` so the render path can be exercised end-to-end.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import audioop
import math
import wave

from .models import RenderSpec


@dataclass(slots=True)
class AudioAnalysis:
    """Compact summary of a WAV file used to seed a render."""

    sample_rate: int
    channels: int
    duration_sec: float
    rms_envelope: list[float]
    peak_rms: float
    estimated_bpm: float | None


def _normalize_samples(samples: array) -> list[float]:
    if not samples:
        return [0.0]
    peak = max(abs(value) for value in samples) or 1
    return [abs(value) / peak for value in samples]


def analyze_wav(path: str | Path, bucket_count: int = 120) -> AudioAnalysis:
    """Analyze a PCM WAV file with standard-library tooling only."""

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

    mono = audioop.tomono(
        raw,
        sample_width,
        1.0,
        1.0,
    ) if channels == 2 else raw
    segment_size = max(1, len(mono) // max(1, bucket_count))
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
    return AudioAnalysis(
        sample_rate=sample_rate,
        channels=channels,
        duration_sec=duration_sec,
        rms_envelope=normalized,
        peak_rms=peak_rms,
        estimated_bpm=bpm,
    )


def spec_from_wav(path: str | Path) -> RenderSpec:
    """Build a small ``RenderSpec`` from a WAV file analysis."""

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
        }
    )
    return spec


__all__ = ["AudioAnalysis", "analyze_wav", "spec_from_wav"]
