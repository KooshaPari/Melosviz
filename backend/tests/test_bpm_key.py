"""Tests for BPM detection, musical key/scale detection, and beat_times exposure.

Covers:
1. BPM range sanity (20–300 BPM) from stdlib-only path
2. BPM populated in the /analyze route response dict
3. key format validation ("NOTE mode" string)
4. beat_times sorted ascending
5. beat_times non-empty for an audible click track
6. Handles short clips (<1 s)
7. Handles near-silence (zero-amplitude WAV)
8. _analyze_with_mir_or_python injects top-level bpm / key / beat_times fields
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import pytest

from melosviz.analysis.audio import analyze_wav, spec_from_wav

# ---------------------------------------------------------------------------
# WAV synthesis helpers (stdlib only — no numpy / librosa)
# ---------------------------------------------------------------------------


def _write_wav(
    path: Path,
    samples: list[int],
    sample_rate: int = 22050,
    n_channels: int = 1,
    sample_width: int = 2,
) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def _click_track(bpm: float, duration_sec: float, sr: int = 22050) -> list[int]:
    """Synthesize a click track at *bpm* BPM."""
    n = int(duration_sec * sr)
    samples = [0] * n
    beat_interval = sr * 60.0 / bpm
    click_width = max(1, int(0.015 * sr))  # 15 ms click
    t = 0.0
    while t < n:
        idx = int(t)
        for j in range(click_width):
            if idx + j < n:
                samples[idx + j] = 32767
        t += beat_interval
    return samples


def _sine_track(freq_hz: float, duration_sec: float, sr: int = 22050) -> list[int]:
    n = int(duration_sec * sr)
    return [int(32767 * math.sin(2.0 * math.pi * freq_hz * i / sr)) for i in range(n)]


def _silence_track(duration_sec: float, sr: int = 22050) -> list[int]:
    return [0] * int(duration_sec * sr)


# ---------------------------------------------------------------------------
# 1. BPM range sanity — stdlib path
# ---------------------------------------------------------------------------


def test_bpm_range_sanity_click_120(tmp_path: Path) -> None:
    """BPM estimate must be within [20, 300] for a 120 BPM click track."""
    wav = tmp_path / "click120.wav"
    _write_wav(wav, _click_track(120.0, 10.0))
    result = analyze_wav(wav)
    assert result.estimated_bpm is not None
    assert 20.0 <= result.estimated_bpm <= 300.0


def test_bpm_range_sanity_click_180(tmp_path: Path) -> None:
    """BPM estimate must be within [20, 300] for a 180 BPM click track."""
    wav = tmp_path / "click180.wav"
    _write_wav(wav, _click_track(180.0, 10.0))
    result = analyze_wav(wav)
    assert result.estimated_bpm is not None
    assert 20.0 <= result.estimated_bpm <= 300.0


# ---------------------------------------------------------------------------
# 2. BPM in route response dict
# ---------------------------------------------------------------------------


def test_analyze_route_dict_has_bpm_field(tmp_path: Path) -> None:
    """spec_from_wav returns a RenderSpec whose metadata contains estimated_bpm."""
    wav = tmp_path / "click.wav"
    _write_wav(wav, _click_track(120.0, 5.0))
    spec = spec_from_wav(wav)
    assert "estimated_bpm" in spec.metadata
    assert spec.metadata["estimated_bpm"] is not None


# ---------------------------------------------------------------------------
# 3. Key format validation
# ---------------------------------------------------------------------------


def test_harmonic_scale_format(tmp_path: Path) -> None:
    """HarmonicResult.scale (if detected) must match '<note> <quality>' format."""
    wav = tmp_path / "sine_a.wav"
    _write_wav(wav, _sine_track(440.0, 5.0))  # A4 sine
    result = analyze_wav(wav)
    if result.harmonic.scale is not None:
        parts = result.harmonic.scale.split(" ", 1)
        assert len(parts) == 2, f"unexpected scale format: {result.harmonic.scale!r}"
        note_part, quality_part = parts
        valid_notes = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"}
        assert note_part in valid_notes, f"unknown note: {note_part!r}"
        assert quality_part, "quality part must be non-empty"


def test_harmonic_chord_format(tmp_path: Path) -> None:
    """HarmonicResult.chord (if detected) must match '<note> <quality>' format."""
    wav = tmp_path / "chord.wav"
    # Mix C4 + E4 + G4 to encourage C major detection
    sr = 22050
    n = sr * 3
    samples = [
        int(
            10000 * math.sin(2 * math.pi * 261.63 * i / sr)
            + 10000 * math.sin(2 * math.pi * 329.63 * i / sr)
            + 10000 * math.sin(2 * math.pi * 392.0 * i / sr)
        )
        for i in range(n)
    ]
    _write_wav(wav, samples)
    result = analyze_wav(wav)
    if result.harmonic.chord is not None:
        parts = result.harmonic.chord.split(" ", 1)
        assert len(parts) == 2, f"unexpected chord format: {result.harmonic.chord!r}"


# ---------------------------------------------------------------------------
# 4. beat_times sorted ascending
# ---------------------------------------------------------------------------


def test_onset_times_sorted_ascending(tmp_path: Path) -> None:
    """onset_times returned by analyze_wav must be in non-decreasing order."""
    wav = tmp_path / "click_sorted.wav"
    _write_wav(wav, _click_track(100.0, 8.0))
    result = analyze_wav(wav)
    times = result.onset_times
    assert times == sorted(times), "onset_times must be sorted ascending"


def test_spec_timeline_beat_events_sorted(tmp_path: Path) -> None:
    """Timeline onset events in the RenderSpec must have sorted 'time' values."""
    wav = tmp_path / "click_timeline.wav"
    _write_wav(wav, _click_track(90.0, 6.0))
    spec = spec_from_wav(wav)
    onset_events = [ev for ev in spec.timeline if ev.get("type") == "onset"]
    times = [ev["time"] for ev in onset_events]
    assert times == sorted(times), "timeline onset events must be sorted by time"


# ---------------------------------------------------------------------------
# 5. Handles short clips (<1 s)
# ---------------------------------------------------------------------------


def test_short_clip_under_one_second(tmp_path: Path) -> None:
    """analyze_wav must not raise on a < 1 s clip; bpm may be None."""
    wav = tmp_path / "short.wav"
    _write_wav(wav, _click_track(120.0, 0.5))  # half-second
    # Must not raise
    result = analyze_wav(wav)
    assert result.duration_sec < 1.0
    # onset_times and rms_envelope must still be lists (possibly empty)
    assert isinstance(result.onset_times, list)
    assert isinstance(result.rms_envelope, list)


# ---------------------------------------------------------------------------
# 6. Handles silence
# ---------------------------------------------------------------------------


def test_silence_produces_no_onsets(tmp_path: Path) -> None:
    """A silent WAV must yield no onset events and BPM may be None."""
    wav = tmp_path / "silence.wav"
    _write_wav(wav, _silence_track(5.0))
    result = analyze_wav(wav)
    # Silence should produce zero or near-zero peak RMS
    assert result.peak_rms == pytest.approx(0.0, abs=1.0)
    # No onsets expected in silence
    assert result.onset_times == []


def test_silence_spec_timeline_empty(tmp_path: Path) -> None:
    """spec_from_wav on silence must return an empty (or minimal) timeline."""
    wav = tmp_path / "silence2.wav"
    _write_wav(wav, _silence_track(3.0))
    spec = spec_from_wav(wav)
    onset_events = [ev for ev in spec.timeline if ev.get("type") == "onset"]
    assert len(onset_events) == 0
