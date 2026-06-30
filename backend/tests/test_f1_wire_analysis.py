"""F1: wire computed-but-ignored analysis into the pipeline.

Tests verify:

1. ``analyze_wav`` now populates ``onset_times`` (non-empty for a click-track
   WAV with peaks above the detection threshold).
2. ``AudioAnalysis.harmonic`` contains a :class:`~melosviz.analysis.models.HarmonicResult`
   with ``note_numbers`` populated from the spectral analysis.
3. ``spec_from_wav`` surfaces ``onset_times``, ``chord``, and ``scale`` in
   ``RenderSpec.metadata``.
4. ``spec_from_wav`` emits one ``"onset"`` timeline event per detected onset,
   with ``time`` matching the onset position.
5. ``detect_chord`` and ``detect_scale`` in :mod:`melosviz.analysis.audio`
   return correct labels for known pitch-class sets.
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest

from melosviz.analysis.audio import (
    analyze_wav,
    detect_chord,
    detect_scale,
    spec_from_wav,
)
from melosviz.analysis.models import HarmonicResult, RenderSpec

# ---------------------------------------------------------------------------
# WAV synthesis helpers (stdlib only — no numpy)
# ---------------------------------------------------------------------------


def _sine_samples(freq_hz: float, duration_sec: float, sample_rate: int = 22050) -> list[int]:
    """Return 16-bit signed PCM samples for a sine wave."""
    import math

    n = int(duration_sec * sample_rate)
    return [
        int(32767 * math.sin(2.0 * math.pi * freq_hz * i / sample_rate))
        for i in range(n)
    ]


def _click_samples(
    bpm: float, duration_sec: float, sample_rate: int = 22050, click_ms: float = 20.0
) -> list[int]:
    """Return 16-bit signed PCM samples for a click track at *bpm*."""
    import math

    n = int(duration_sec * sample_rate)
    samples = [0] * n
    beat_interval = 60.0 / bpm
    click_width = max(1, int(click_ms / 1000.0 * sample_rate))
    t = 0.0
    while t < duration_sec:
        idx = int(t * sample_rate)
        for offset in range(click_width):
            if idx + offset < n:
                # Hanning window for a soft click
                w = math.sin(math.pi * offset / click_width) ** 2
                samples[idx + offset] = int(32767 * 0.9 * w)
        t += beat_interval
    return samples


def _write_wav(path: Path, samples: list[int], sample_rate: int = 22050) -> Path:
    """Write a mono 16-bit WAV file from *samples* and return *path*."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        packed = struct.pack(f"<{len(samples)}h", *samples)
        wf.writeframes(packed)
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def click_wav(tmp_path: Path) -> Path:
    """A 120-BPM click track lasting 8 s — should produce detectable onsets."""
    return _write_wav(tmp_path / "click.wav", _click_samples(120.0, 8.0))


@pytest.fixture
def sine_wav(tmp_path: Path) -> Path:
    """A pure 440 Hz sine wave lasting 2 s — few or no onsets expected."""
    return _write_wav(tmp_path / "sine.wav", _sine_samples(440.0, 2.0))


# ---------------------------------------------------------------------------
# 1. onset_times populated for rhythmic audio
# ---------------------------------------------------------------------------


def test_analyze_wav_onsets_non_empty_for_click_track(click_wav: Path) -> None:
    """A click track must produce at least one onset."""
    result = analyze_wav(click_wav)
    assert isinstance(result.onset_times, list), "onset_times must be a list"
    assert len(result.onset_times) > 0, "onset_times must be non-empty for a click track"


def test_analyze_wav_onset_times_are_non_negative_and_bounded(click_wav: Path) -> None:
    """All onset times must lie within [0, duration_sec]."""
    result = analyze_wav(click_wav)
    for t in result.onset_times:
        assert t >= 0.0, f"onset time {t} is negative"
        assert t <= result.duration_sec, f"onset time {t} exceeds duration {result.duration_sec}"


def test_analyze_wav_onset_times_monotonically_increasing(click_wav: Path) -> None:
    """Onset times must be in ascending order (no duplicates going backwards)."""
    result = analyze_wav(click_wav)
    times = result.onset_times
    if len(times) >= 2:
        assert all(times[i] < times[i + 1] for i in range(len(times) - 1)), (
            "onset_times must be strictly increasing"
        )


# ---------------------------------------------------------------------------
# 2. harmonic field populated
# ---------------------------------------------------------------------------


def test_analyze_wav_harmonic_field_is_harmonic_result(click_wav: Path) -> None:
    """harmonic must be a HarmonicResult instance."""
    result = analyze_wav(click_wav)
    assert isinstance(result.harmonic, HarmonicResult)


def test_analyze_wav_harmonic_note_numbers_for_tonal_audio(sine_wav: Path) -> None:
    """A 440 Hz sine wave should produce at least one MIDI note number."""
    result = analyze_wav(sine_wav)
    assert isinstance(result.harmonic.note_numbers, list)
    assert len(result.harmonic.note_numbers) > 0, (
        "note_numbers must be non-empty for tonal audio (440 Hz sine)"
    )


def test_analyze_wav_harmonic_note_numbers_are_valid_midi(sine_wav: Path) -> None:
    """All note numbers must be in [0, 127]."""
    result = analyze_wav(sine_wav)
    for note in result.harmonic.note_numbers:
        assert 0 <= note <= 127, f"note number {note} out of MIDI range"


# ---------------------------------------------------------------------------
# 3 & 4. spec_from_wav surfaces onset_times, chord, scale in metadata
#         and emits onset timeline events
# ---------------------------------------------------------------------------


def test_spec_from_wav_metadata_contains_onset_times(click_wav: Path) -> None:
    """metadata['onset_times'] must exist and be a list."""
    spec = spec_from_wav(click_wav)
    assert isinstance(spec, RenderSpec)
    assert "onset_times" in spec.metadata, "onset_times key missing from metadata"
    assert isinstance(spec.metadata["onset_times"], list)


def test_spec_from_wav_metadata_onset_times_non_empty_for_click_track(click_wav: Path) -> None:
    """onset_times in metadata must be non-empty for rhythmic input."""
    spec = spec_from_wav(click_wav)
    assert len(spec.metadata["onset_times"]) > 0


def test_spec_from_wav_metadata_has_chord_and_scale_keys(click_wav: Path) -> None:
    """chord and scale keys must be present in metadata (value may be None)."""
    spec = spec_from_wav(click_wav)
    assert "chord" in spec.metadata, "chord key missing from metadata"
    assert "scale" in spec.metadata, "scale key missing from metadata"


def test_spec_from_wav_timeline_contains_onset_events(click_wav: Path) -> None:
    """timeline must include at least one entry with type=='onset'."""
    spec = spec_from_wav(click_wav)
    onset_events = [e for e in spec.timeline if e.get("type") == "onset"]
    assert len(onset_events) > 0, "No onset events found in spec.timeline"


def test_spec_from_wav_timeline_onset_times_match_metadata(click_wav: Path) -> None:
    """Timeline onset event times must exactly match metadata onset_times."""
    spec = spec_from_wav(click_wav)
    timeline_times = sorted(
        e["time"] for e in spec.timeline if e.get("type") == "onset"
    )
    metadata_times = sorted(spec.metadata["onset_times"])
    assert timeline_times == metadata_times, (
        "Timeline onset times do not match metadata onset_times"
    )


def test_spec_from_wav_onset_events_have_strength(click_wav: Path) -> None:
    """Each onset timeline event must carry a 'strength' value in its data dict."""
    spec = spec_from_wav(click_wav)
    for event in spec.timeline:
        if event.get("type") == "onset":
            assert "data" in event, "onset event missing 'data' key"
            assert "strength" in event["data"], "onset event data missing 'strength'"


# ---------------------------------------------------------------------------
# 5. detect_chord / detect_scale correctness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "note_numbers,expected_substring",
    [
        # C major triad (C=0, E=4, G=7 mod 12)
        ([60, 64, 67], "major"),
        # A minor triad (A=69, C=60, E=64 → pcs 9,0,4)
        ([69, 60, 64], "minor"),
        # C diminished (C=60, Eb=63, Gb=66 → pcs 0,3,6)
        ([60, 63, 66], "diminished"),
    ],
)
def test_detect_chord_known_triads(
    note_numbers: list[int], expected_substring: str
) -> None:
    chord = detect_chord(note_numbers)
    assert chord is not None, f"detect_chord returned None for {note_numbers}"
    assert expected_substring in chord, f"Expected '{expected_substring}' in chord '{chord}'"


def test_detect_chord_returns_none_for_fewer_than_three_notes() -> None:
    assert detect_chord([]) is None
    assert detect_chord([60]) is None
    assert detect_chord([60, 64]) is None


@pytest.mark.parametrize(
    "note_numbers,expected_substring",
    [
        # C major scale pitch classes: 0,2,4,5,7,9,11
        ([60, 62, 64, 65, 67, 69, 71], "major"),
        # C natural minor: C=60,D=62,Eb=63,F=65,G=67,Ab=68,Bb=70
        # pcs: {0,2,3,5,7,8,10}; from root 0: (0,2,3,5,7,8,10) = minor
        ([60, 62, 63, 65, 67, 68, 70], "minor"),
    ],
)
def test_detect_scale_known_scales(
    note_numbers: list[int], expected_substring: str
) -> None:
    scale = detect_scale(note_numbers)
    assert scale is not None, f"detect_scale returned None for {note_numbers}"
    assert expected_substring in scale, f"Expected '{expected_substring}' in scale '{scale}'"


def test_detect_scale_returns_none_for_fewer_than_three_notes() -> None:
    assert detect_scale([]) is None
    assert detect_scale([60, 62]) is None
