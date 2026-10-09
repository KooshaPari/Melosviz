"""Assertion-bearing tests targeting the audio.py mutation-gate survivors.

The gate's own measurement (2026-10-08, see tests/mutation_gate_config.py)
found audio.py killing only 15/50 sampled strict-reachable mutants: the
reachable survivors are an *assertion* gap, not a coverage gap.  Every test
below pins the exact observable behaviour of one survivor site so that the
mutated program and the original cannot produce the same result:

* module-level tables and constants (chord/scale intervals, the analysis
  frequency grid, the audioop flag),
* the stdlib-only ``analyze_wav`` path (envelope reference maths, the exact
  BPM hit threshold, harmonic note selection),
* the MIR-enriched ``analyze_wav_rich`` path (dense-frame floor, onset/beat
  marker placement, per-second energy, valence/danceability, the
  librosa-absent and numpy-absent degradation branches),
* direct calls to the private helpers the survivors live in.

Conventions follow the existing suite: plain asserts, synthetic PCM WAVs
built with the stdlib only, ``pytest.importorskip`` for the optional heavy
deps (librosa/numpy/scipy), and ``unittest.mock`` for the optional-dep
present/absent branches -- see test_audio_ml_paths.py and
test_coverage_gaps.py.  Reference (golden-model) assertions recompute the
expected value inside the test from the same inputs, so they are exact on
the original source and platform-independent (both sides run in one
process against the same libraries).
"""

from __future__ import annotations

import cmath
import math
import struct
import wave
from pathlib import Path
from unittest import mock

import pytest

from melosviz.analysis import audio as audio_mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sine_samples(
    n_samples: int, freq: float = 440.0, amp: int = 16000, sample_rate: int = 22050
) -> list[int]:
    return [int(amp * math.sin(2.0 * math.pi * freq * i / sample_rate)) for i in range(n_samples)]


def _write_wav(
    path: Path,
    samples: list[int],
    sample_rate: int = 22050,
    sample_width: int = 2,
) -> Path:
    if sample_width == 2:
        data = struct.pack(f"<{len(samples)}h", *samples)
    else:
        data = struct.pack(f"<{len(samples)}i", *samples)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(sample_width)
        handle.setframerate(sample_rate)
        handle.writeframes(data)
    return path


def _wav_frames(path: Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        return handle.readframes(handle.getnframes())


def _no_audioop_reference_envelope(
    mono: bytes, sample_width: int, bucket_count: int
) -> list[float]:
    """Independent copy of analyze_wav's pure-Python bucket maths (lines 170-188).

    Exact on the original source (same operations in the same order); any
    arithmetic mutation of that loop diverges from this reference.
    """
    n_samples = len(mono) // sample_width
    bucket_size = max(1, n_samples // bucket_count)
    envelope: list[float] = []
    for bucket in range(bucket_count):
        start = bucket * bucket_size * sample_width
        end = start + bucket_size * sample_width
        chunk = mono[start:end]
        if not chunk:
            envelope.append(0.0)
            continue
        total = 0.0
        n_read = 0
        for off in range(0, len(chunk) - sample_width + 1, sample_width):
            val = int.from_bytes(chunk[off : off + sample_width], "little", signed=True)
            total += val * val
            n_read += 1
        envelope.append(math.sqrt(total / max(1, n_read)))
    peak = max(envelope) or 1.0
    return [v / peak for v in envelope]


# ---------------------------------------------------------------------------
# Module-level tables: _CHORD_INTERVALS (line 53), _SCALE_INTERVALS (line 54)
# ---------------------------------------------------------------------------

# Every entry uses a leading 0 (intervals are always rooted at 0), so a 0->1
# constant flip anywhere in the dict removes that chord from the table and
# detect_chord can no longer return the canonical name.
CHORD_CASES: dict[str, list[int]] = {
    "C major": [0, 4, 7],
    "C minor": [0, 3, 7],
    "C diminished": [0, 3, 6],
    "C augmented": [0, 4, 8],
    "C major7": [0, 4, 7, 11],
    "C minor7": [0, 3, 7, 10],
    "C dominant7": [0, 4, 7, 10],
    "C sus2": [0, 2, 7],
    "C sus4": [0, 5, 7],
}

# The reachable scale entries.  "C major" is deliberately absent: its table
# key (1, 2, 4, ...) can never equal a rooted interval tuple (which always
# starts with 0), so that entry is dead code.  "C phrygian" pins the
# COMMITTED audio.py's phrygian key (0, 1, 3, 5, 7, 8, 10) -- the
# musically-correct interval set, which IS reachable, so these pcs detect as
# C phrygian under the tree CI measures.  (An in-progress uncommitted
# working-tree rewrite of audio.py keys phrygian (0, 0, 3, ...) -- a
# duplicate-0 regression that makes the entry unreachable and detection
# falls through to "D# mixolydian".  A test cannot pin both trees; it pins
# the shipped one, and that rewrite must restore the key before it lands.)
# Pinning the name means a constant flip that makes the key unreachable
# changes this result and fails the test.
SCALE_CASES: dict[str, list[int]] = {
    "C minor": [0, 2, 3, 5, 7, 8, 10],
    "C harmonic minor": [0, 2, 3, 5, 7, 8, 11],
    "C melodic minor": [0, 2, 3, 5, 7, 9, 11],
    "C mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "C dorian": [0, 2, 3, 5, 7, 9, 10],
    "C phrygian": [0, 1, 3, 5, 7, 8, 10],  # committed key, reachable
}


@pytest.mark.parametrize("expect", sorted(CHORD_CASES), ids=sorted(CHORD_CASES))
def test_chord_table_entry_detectable(expect: str) -> None:
    """Each of the nine _CHORD_INTERVALS entries resolves for its own pcs."""
    assert audio_mod.detect_chord(CHORD_CASES[expect]) == expect


@pytest.mark.parametrize("expect", sorted(SCALE_CASES), ids=sorted(SCALE_CASES))
def test_scale_table_entry_detectable(expect: str) -> None:
    """Each reachable _SCALE_INTERVALS entry resolves for its own pcs."""
    assert audio_mod.detect_scale(SCALE_CASES[expect]) == expect


def test_freq_to_note_low_frequency_clamps_to_zero() -> None:
    """_freq_to_note floors at 0 for sub-audible input (line 60 constant)."""
    assert audio_mod._freq_to_note(1.0) == 0
    assert audio_mod._freq_to_note(440.0) == 69


def test_analysis_frequency_table_ordered_and_audible() -> None:
    """_ANALYSIS_FREQS must be 36 strictly rising, audible, A4-anchored bins.

    The grid is computed by (note - 69) / 12.0 at line 99; an arithmetic
    mutation there moves the whole grid out of the audible band or reverses
    its order while still keeping note 69 at 440 Hz, so all three
    properties are asserted.
    """
    freqs = audio_mod._ANALYSIS_FREQS
    assert len(freqs) == 36
    assert all(b > a for a, b in zip(freqs, freqs[1:], strict=False))
    assert all(20.0 <= f <= 5000.0 for f in freqs)
    assert freqs[69 - 36] == pytest.approx(440.0)


def test_audioop_flag_stays_enabled_when_module_importable() -> None:
    """_HAS_AUDIOOP must be True whenever audioop itself imports (line 34).

    The guard imports audioop in the test process (not via the mutated
    module) so an environment without audioop skips instead of failing,
    while a mutation flipping the flag to False still fails here.
    """
    try:
        import audioop  # noqa: F401
    except ImportError:
        pytest.skip("audioop unavailable on this Python build")
    assert audio_mod._HAS_AUDIOOP is True


# ---------------------------------------------------------------------------
# _goertzel / _pick_onsets / _rms_fallback_envelope
# ---------------------------------------------------------------------------


def test_goertzel_empty_input_returns_zero() -> None:
    assert audio_mod._goertzel([], 22050, 440.0) == 0.0


def test_goertzel_single_sample_positive_power() -> None:
    assert audio_mod._goertzel([1.0], 22050, 440.0) > 0.0


def test_goertzel_matches_dft_reference_power() -> None:
    """The Goertzel recurrence must equal the DFT power at the same bin.

    Catches arithmetic mutations of the inner recurrence (line 95): a
    changed update rule produces a power that no longer matches |X(w)|^2.
    """
    sr = 22050
    samples = [
        math.sin(2.0 * math.pi * 440.0 * i / sr) + 0.3 * math.cos(2.0 * math.pi * 1000.0 * i / sr)
        for i in range(64)
    ]
    freq = 1000.0
    got = audio_mod._goertzel(samples, sr, freq)
    omega = 2.0 * math.pi * freq / sr
    acc = sum(x * cmath.exp(-1j * omega * n) for n, x in enumerate(samples))
    assert got == pytest.approx(abs(acc) ** 2, rel=1e-9)


def test_pick_onsets_accepts_the_very_first_bucket() -> None:
    """A full-envelope first sample is an onset (line 122 initial gap)."""
    onsets = audio_mod._pick_onsets([1.0] * 20, 1.0)
    assert onsets == [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def test_rms_fallback_envelope_single_sample_first_bucket() -> None:
    """n < n_buckets keeps a bucket size of 1 (line 381 max() floor)."""
    env = audio_mod._rms_fallback_envelope(b"\x10\x00", sample_width=2, n_buckets=4)
    assert env == [1.0, 0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# analyze_wav (stdlib path)
# ---------------------------------------------------------------------------


def test_no_audioop_envelope_matches_reference(tmp_path: Path) -> None:
    """The pure-Python branch reproduces its reference maths exactly.

    Kills the arithmetic mutants of the bucket loop (line 183 off+width
    read offset) and of the normalisation (line 188 v/peak): either one
    diverges from the independent reference computed here.
    """
    samples = _sine_samples(40)  # 10 samples per bucket, all buckets non-empty
    wav = _write_wav(tmp_path / "vary.wav", samples)
    with (
        mock.patch.object(audio_mod, "_HAS_AUDIOOP", False),
        mock.patch.object(audio_mod, "_audioop", None),
    ):
        result = audio_mod.analyze_wav(wav, bucket_count=4)
    expected = _no_audioop_reference_envelope(_wav_frames(wav), sample_width=2, bucket_count=4)
    assert len(expected) == 4
    assert result.rms_envelope == expected


def test_bpm_counts_samples_above_exact_threshold(tmp_path: Path) -> None:
    """Hits are counted with value > 0.65 exactly, not >= (line 192).

    One bucket sits exactly on 0.65 (650 of a 1000 peak), so the count is
    4, not 5, and the expected BPM is computed from that count directly.
    """
    samples = [1000] * 200 + [1000] * 200 + [1000] * 200 + [650] * 200 + [1000] * 200
    wav = _write_wav(tmp_path / "thresh.wav", samples)
    result = audio_mod.analyze_wav(wav, bucket_count=5)
    assert result.rms_envelope == [1.0, 1.0, 1.0, 0.65, 1.0]
    duration = 1000 / 22050
    assert result.estimated_bpm == round(4 / duration * 60.0, 2)


def test_analyze_wav_a4_tone_harmonic_notes(tmp_path: Path) -> None:
    """A 440 Hz tone must yield note 69 inside the designed 36-71 grid.

    Guards the analysis-window slicing (line 200), the reverse=True sort in
    _harmonic_from_samples (line 106) and the empty-input guard feeding it
    (line 87): each mutation drops 69 or pushes notes outside the grid.
    """
    wav = _write_wav(tmp_path / "a4.wav", _sine_samples(11025))  # 0.5 s
    result = audio_mod.analyze_wav(wav)
    notes = result.harmonic.note_numbers
    assert 69 in notes
    assert all(36 <= n <= 71 for n in notes)


def test_analyze_wav_32bit_notes_match_16bit(tmp_path: Path) -> None:
    """32-bit PCM must harmonically agree with the 16-bit rendition.

    Pins the sample_width==4 float conversion (line 206): a change to the
    scaling arithmetic perturbs the Goertzel powers enough to move the
    top-8 note set for this shared waveform.
    """
    samples = _sine_samples(11025, amp=1_000_000_000)
    wav32 = _write_wav(tmp_path / "tone32.wav", samples, sample_width=4)
    wav16 = _write_wav(tmp_path / "tone16.wav", _sine_samples(11025))
    notes32 = audio_mod.analyze_wav(wav32).harmonic.note_numbers
    notes16 = audio_mod.analyze_wav(wav16).harmonic.note_numbers
    assert notes32 == notes16
    assert 69 in notes32


def test_no_audioop_envelope_alignment_length(tmp_path: Path) -> None:
    """audioop segments count = ceil(len / segment_size) (lines 157-167).

    A 1.0 s sine at bucket_count=120 has segment_size 366 bytes, so the
    audioop branch yields 121 buckets while the pure-Python branch yields
    exactly 120.  The flag itself is asserted too (see the dedicated test).
    """
    wav = _write_wav(tmp_path / "sine1s.wav", _sine_samples(22050))
    result = audio_mod.analyze_wav(wav, bucket_count=120)
    mono_len = 22050 * 2
    raw_size = mono_len // 120
    segment_size = max(2, raw_size // 2 * 2)
    assert math.ceil(mono_len / segment_size) == 121
    assert len(result.rms_envelope) == 121


# ---------------------------------------------------------------------------
# analyze_wav_rich: shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rich_spec(tmp_path_factory: pytest.TempPathFactory):
    """One non-stationary 2 s tone sequence analysed with deterministic beats.

    ``_safe_beat_track`` is patched so no child process is spawned, and
    ``librosa.onset.onset_strength`` is patched to a known 20-frame pattern
    ([9, 1] * 10) whose length equals n_dense_frames (int(2.0 * 10) = 20),
    making onset interpolation exactly predictable.
    """
    pytest.importorskip("librosa")
    import librosa
    import numpy as np

    path = tmp_path_factory.mktemp("rich") / "seg_tone.wav"
    sr = 22050
    freqs = (261.63, 329.63, 392.00, 523.25)  # four tones, 0.5 s each -> non-stationary
    block = int(0.5 * sr)
    samples: list[int] = []
    for k, freq in enumerate(freqs):
        amp = 14000 - 2000 * k
        samples.extend(_sine_samples(block, freq=freq, amp=amp, sample_rate=sr))
    _write_wav(path, samples, sample_rate=sr)

    onset_strength = np.array([9.0, 1.0] * 10)
    with (
        mock.patch.object(
            audio_mod, "_safe_beat_track", return_value=(120.0, [0.0, 0.5, 1.0, 1.5])
        ),
        mock.patch.object(librosa.onset, "onset_strength", return_value=onset_strength),
    ):
        spec = audio_mod.analyze_wav_rich(path, n_dense_fps=10, use_demucs=False)
    return spec, path, sr


def test_rich_tiny_wav_keeps_at_least_one_dense_frame(tmp_path: Path) -> None:
    """duration * fps < 1 still floors to 1 dense frame (line 607 max())."""
    pytest.importorskip("librosa")
    wav = _write_wav(tmp_path / "micro.wav", _sine_samples(1103))  # 0.05 s
    with mock.patch.object(audio_mod, "_safe_beat_track", return_value=(120.0, [0.0, 0.02])):
        spec = audio_mod.analyze_wav_rich(wav, n_dense_fps=10, use_demucs=False)
    assert spec.metadata["n_dense_frames"] >= 1
    assert len(spec.dense_keyframes) >= 1


def test_rich_onset_strength_matches_reference(rich_spec) -> None:
    """Dense onset strength is the reference-normalised envelope (lines 644/653).

    The patched envelope is [9, 1] * 10, so the reference normalisation is
    [1.0, 1/9, ...] and every keyframe must carry it unchanged.  A changed
    divisor (line 644 or/and logic) or a changed interpolation grid
    (line 653 linspace) shifts those values.
    """
    import numpy as np

    spec, _path, _sr = rich_spec
    raw = np.array([9.0, 1.0] * 10)
    expected = [round(float(v), 4) for v in raw / raw.max()]
    actual = [kf["onset_strength"] for kf in spec.dense_keyframes]
    assert actual == expected
    assert all(0.0 <= v <= 1.0 for v in actual)


def test_rich_beat_markers_on_exact_frames(rich_spec) -> None:
    """Beats at [0, .5, 1, 1.5] land on dense frames 0/4/9/14 (line 657)."""
    spec, _path, _sr = rich_spec
    marks = [i for i, kf in enumerate(spec.dense_keyframes) if kf["beat_strength"] == 1.0]
    assert marks == [0, 4, 9, 14]
    assert spec.dense_keyframes[0]["beat_strength"] == 1.0


def test_rich_energy_trajectory_is_finite_and_chunked(rich_spec) -> None:
    """Per-second energy is the first-chunk mean of normalised RMS (line 662).

    With duration 2.0 the trajectory has two entries; a mutated chunk index
    turns the second one into NaN (empty-slice mean).
    """
    import librosa

    spec, path, sr = rich_spec
    y, _sr = librosa.load(str(path), sr=None, mono=True)
    n_frames = spec.metadata["n_dense_frames"]
    hop = max(1, len(y) // n_frames)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms_norm = rms / (rms.max() or 1.0)
    n_secs = max(1, int(len(y) / sr))
    sec_frames = max(1, len(rms_norm) // n_secs)
    expected_first = round(float(rms_norm[0:sec_frames].mean()), 4)
    traj = spec.mir["energy_trajectory"]
    assert len(traj) == n_secs
    assert all(v == v for v in traj), "energy trajectory must be finite"
    assert traj[0] == expected_first


def test_rich_valence_matches_mfcc_reference(rich_spec) -> None:
    """Dense valence is mfcc[1] normalised, offset and resampled (lines 666/667).

    Recomputed from the same file and hop parameters, so it is exact on the
    original source and diverges for any mutation of the coefficient index,
    the clip bounds or the interpolation grid.
    """
    import librosa
    import numpy as np

    spec, path, _sr = rich_spec
    y, sr = librosa.load(str(path), sr=None, mono=True)
    n_frames = spec.metadata["n_dense_frames"]
    hop = max(1, len(y) // n_frames)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop)
    valence_raw = np.clip(mfcc[1] / (np.abs(mfcc[1]).max() or 1.0) * 0.5 + 0.5, 0, 1)
    n_vals = len(valence_raw)
    resampled = np.interp(np.linspace(0, n_vals - 1, n_frames), np.arange(n_vals), valence_raw)
    expected = [round(float(v), 4) for v in resampled]
    # The fixture signal must be non-stationary or the grid mutations below
    # would be indistinguishable from a constant trajectory.
    assert max(expected) - min(expected) > 1e-3
    actual = [kf["valence"] for kf in spec.dense_keyframes]
    assert actual == expected


def test_rich_danceability_in_unit_interval(rich_spec) -> None:
    """danceability = min(1, 0.5*mean_rms + 0.5*regularity) is in [0.5, 1].

    The fixture beats are perfectly regular (regularity 1.0), so the
    original value is 0.5*mean + 0.5; an operator mutation of that
    combination (line 680) falls below 0.5.
    """
    spec, _path, _sr = rich_spec
    danceability = spec.mir["danceability"]
    assert danceability is not None
    assert 0.5 <= danceability <= 1.0


def test_rich_energy_fallback_without_librosa(tmp_path: Path) -> None:
    """With librosa absent, line 717 still yields one per-second energy value."""
    wav = _write_wav(tmp_path / "tiny_tone.wav", _sine_samples(11026))  # ~0.5 s
    with mock.patch.object(audio_mod, "_try_import_librosa", return_value=None):
        spec = audio_mod.analyze_wav_rich(wav, n_dense_fps=10, use_demucs=False)
    traj = spec.mir["energy_trajectory"]
    assert traj, "energy trajectory must not be empty when librosa is absent"
    assert len(traj) == 1  # int(0.5) == 0 floors to exactly one bucket


def test_rich_no_beat_timeline_without_numpy(tmp_path: Path) -> None:
    """With numpy unavailable the whole MIR block is skipped (line 631 and).

    The original never enters the block, so the timeline carries no beat
    events; an or-condition enters it, beats are tracked, and the missing
    numpy then aborts the block *after* beat_times is populated -- the
    timeline gains beat events and this assertion fails.
    """
    pytest.importorskip("librosa")
    wav = _write_wav(tmp_path / "tone2s.wav", _sine_samples(44100))
    with (
        mock.patch.object(audio_mod, "_try_import_numpy", return_value=None),
        mock.patch.object(
            audio_mod, "_safe_beat_track", return_value=(120.0, [0.0, 0.5, 1.0, 1.5])
        ),
    ):
        spec = audio_mod.analyze_wav_rich(wav, n_dense_fps=10, use_demucs=False)
    types = {ev["type"] for ev in spec.timeline_events}
    assert "beat" not in types


# ---------------------------------------------------------------------------
# Direct helper calls used by analyze_wav_rich
# ---------------------------------------------------------------------------


def test_librosa_segment_boundaries_match_reference() -> None:
    """Boundaries equal an independent novelty-peak computation exactly.

    Pins the sum axis (line 430) and the boundary slice width (line 437):
    a changed axis yields frequency-axis "peaks" at different times, and a
    widened slice appends a boundary short of the duration, so the last
    segment would no longer end at duration either.
    """
    librosa = pytest.importorskip("librosa")
    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")
    from scipy.signal import find_peaks

    sr = 22050
    duration = 48.0
    block = int(4.0 * sr)
    amps = [0.9 if i % 2 == 0 else 0.05 for i in range(12)]
    y = np.concatenate([np.full(block, amp, dtype=np.float32) for amp in amps]).astype(np.float32)
    n_segments = 4

    got = audio_mod._librosa_segment_boundaries(
        librosa, np, y, sr, n_segments=n_segments, duration_sec=duration
    )

    # Independent replication of the novelty pipeline (source order preserved).
    hop_length = 512
    s = np.abs(librosa.stft(y, hop_length=hop_length)) ** 2
    log_s = librosa.power_to_db(s, ref=np.max)
    novelty = np.diff(np.sum(log_s, axis=0), prepend=0)
    novelty = np.maximum(novelty, 0)
    novelty_smooth = np.convolve(novelty, np.ones(16) / 16, mode="same")
    min_dist = max(1, int(sr * 8 / hop_length))
    peaks, _ = find_peaks(novelty_smooth, distance=min_dist)
    times_all = librosa.frames_to_time(peaks, sr=sr, hop_length=hop_length)
    bounds = sorted(times_all[: n_segments - 1].tolist())
    edges = [0.0] + bounds + [duration]
    expected = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]
    while len(expected) < n_segments:
        expected.append((duration, duration))
    expected = expected[:n_segments]

    flat_got = [c for seg in got for c in seg]
    flat_expected = [c for seg in expected for c in seg]
    assert flat_got == pytest.approx(flat_expected, abs=1e-9)
    assert len(got) == n_segments
    assert got[0][0] == 0.0
    assert got[-1][1] == pytest.approx(duration)


def test_spectral_stem_fallback_matches_reference() -> None:
    """Stem envelopes equal an independent resample/normalise (lines 502/513).

    The rms frame count (9 for a 1 s signal at n_frames=10) differs from
    n_frames, so a changed interpolation endpoint grid moves every interior
    value away from the reference.
    """
    librosa = pytest.importorskip("librosa")
    np = pytest.importorskip("numpy")

    sr = 22050
    n_frames = 10
    rng = np.random.default_rng(0)
    y = rng.standard_normal(sr).astype(np.float32) * 0.1

    chans = audio_mod._spectral_stem_fallback(librosa, np, y, sr, n_frames=n_frames)

    hop = max(1, len(y) // n_frames)
    y_harmonic, y_percussive = librosa.effects.hpss(y)
    for signal, name in ((y_percussive, "drums"), (y_harmonic, "other")):
        rms = librosa.feature.rms(y=signal, frame_length=hop * 2, hop_length=hop)[0]
        ref = np.interp(np.linspace(0, len(rms) - 1, n_frames), np.arange(len(rms)), rms)
        ref = (ref / (float(ref.max()) or 1.0)).tolist()
        assert len(rms) != n_frames  # grid endpoints must actually matter
        assert chans[name] == pytest.approx(ref, abs=1e-9)

    s = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    for mask, name in (
        (freqs < 300, "bass"),
        ((freqs >= 300) & (freqs < 4000), "vocals"),
    ):
        band = s.copy()
        band[~mask, :] = 0
        rms = np.sqrt(np.mean(band**2, axis=0))
        ref = np.interp(np.linspace(0, len(rms) - 1, n_frames), np.arange(len(rms)), rms)
        ref = (ref / (float(ref.max()) or 1.0)).tolist()
        assert chans[name] == pytest.approx(ref, abs=1e-9)


def test_separate_stems_demucs_repeats_mono_to_stereo(tmp_path: Path) -> None:
    """A mono waveform is repeated to 2 channels before apply_model (line 470).

    The fake apply_model asserts the stereo shape and returns non-zero
    per-stem constants; if the repeat is skipped, the assertion fires, the
    helper's exception path returns zero-filled stems, and the exact-value
    assertion below fails.
    """
    np = pytest.importorskip("numpy")

    class _Tensor:
        """Minimal torch-tensor facade over a numpy array."""

        def __init__(self, arr) -> None:
            self._a = np.asarray(arr)

        @property
        def shape(self):
            return self._a.shape

        def repeat(self, *reps):
            return _Tensor(np.tile(self._a, reps))

        def unsqueeze(self, dim):
            return _Tensor(np.expand_dims(self._a, dim))

    class _Sources:
        def __init__(self, data) -> None:
            self._data = data

        def squeeze(self, _dim):
            return self

        def numpy(self):
            return self._data

    def fake_apply_model(_model, waveform, device="cpu", progress=False):  # noqa: ARG001
        assert waveform.shape[1] == 2, "demucs expects (batch, channels, time)"
        width = int(waveform.shape[2])
        data = np.ones((4, 2, width), dtype=np.float32) * np.arange(1, 5).reshape(4, 1, 1)
        return _Sources(data)

    fake_torch = mock.MagicMock()
    fake_torchaudio = mock.MagicMock()
    fake_torchaudio.load.return_value = (_Tensor(np.full((1, 2205), 0.5)), 22050)
    fake_model = mock.MagicMock(samplerate=22050, eval=mock.MagicMock())
    modules = {
        "torch": fake_torch,
        "torchaudio": fake_torchaudio,
        "demucs": mock.MagicMock(),
        "demucs.apply": mock.MagicMock(apply_model=fake_apply_model),
        "demucs.pretrained": mock.MagicMock(get_model=mock.MagicMock(return_value=fake_model)),
    }
    wav = _write_wav(tmp_path / "mono_tone.wav", _sine_samples(4410))
    with mock.patch.dict("sys.modules", modules):
        chans = audio_mod._separate_stems_demucs(wav, duration_sec=0.2, n_frames=5)

    # Each stem envelope is normalised to its own peak, so a constant
    # per-stem signal yields an all-ones channel (and proves the mocked
    # apply_model actually ran: the exception path would return zeros).
    assert chans["drums"] == pytest.approx([1.0] * 5)
    assert chans["bass"] == pytest.approx([1.0] * 5)
    assert chans["vocals"] == pytest.approx([1.0] * 5)
    assert chans["other"] == pytest.approx([1.0] * 5)


def test_scene_segments_zero_dense_frames_yields_zero_dominant_stem() -> None:
    """_mean_in_range guards total <= 0 before dividing (line 555).

    With n_dense_frames=0 the dominant-stem probe passes total=0; the
    guard must return 0.0 rather than dividing by zero.
    """
    segs = audio_mod._build_scene_segments(
        librosa=None,
        np=None,
        y=None,
        sr=22050,
        duration_sec=1.0,
        energy_per_sec=[0.6] * 4,
        brightness_per_sec=[0.4] * 4,
        valence_per_sec=[0.5] * 4,
        arousal_per_sec=[0.5] * 4,
        stem_channels={
            "drums": [0.5, 0.5],
            "bass": [0.2, 0.2],
            "vocals": [0.1, 0.1],
            "other": [0.9, 0.9],
        },
        n_dense_frames=0,
    )
    assert len(segs) == 4
    assert all(seg["dominant_stem"] == "other" for seg in segs)
    assert all(seg["energy_mean"] == pytest.approx(0.6) for seg in segs)
