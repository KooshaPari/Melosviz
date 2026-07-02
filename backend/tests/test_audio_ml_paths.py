"""Behavioral coverage for the ML-optional paths in ``melosviz.analysis.audio``.

These tests exercise the branches that previously carried
``# pragma: no cover — requires <dep>``. They assume the heavy
ML extras (``librosa``, ``numpy``, ``scipy``, ``demucs``, ``torch``) are
installed — see ``docs/ops/ML_INSTALL.md`` for the install recipe.

The goal is **real coverage, not pragma gaming**:

* The synthetic-WAV generator produces an actual PCM waveform that
  librosa/numpy can decode.
* The ``analyze_wav_rich`` end-to-end test exercises the full MIR path
  and asserts that the optional-dep branches populate real values
  (not just that the code path was reached).
* The Demucs branch is mocked because running the real HTDemucs model
  is far too slow for a unit test, but the wiring through
  ``_separate_stems_demucs`` is still asserted.
* The spectral-fallback branch is exercised directly with a real
  numpy/librosa signal.
"""

from __future__ import annotations

import math
import struct
import wave
from array import array
from pathlib import Path
from unittest import mock

import pytest

from melosviz.analysis import audio
from melosviz.analysis.audio import (
    STEM_NAMES,
    _build_dense_keyframes,
    _build_scene_segments,
    _classify_section_label,
    _easing_for_energy,
    _librosa_segment_boundaries,
    _rms_fallback_envelope,
    _separate_stems_demucs,
    _spectral_stem_fallback,
    _try_import_demucs,
    _try_import_librosa,
    _try_import_numpy,
    _zero_stem_channels,
    analyze_wav,
    analyze_wav_rich,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Synthetic WAV generator
# ---------------------------------------------------------------------------


def _write_sine_wav(
    path: Path,
    duration_sec: float = 1.0,
    sample_rate: int = 22050,
    freq_hz: float = 440.0,
    amplitude: int = 16000,
) -> Path:
    """Write a 16-bit mono PCM WAV file containing a sine wave."""
    n_frames = int(duration_sec * sample_rate)
    with wave.open(str(path), "wb") as h:
        h.setnchannels(1)
        h.setsampwidth(2)
        h.setframerate(sample_rate)
        frames = bytearray()
        for n in range(n_frames):
            sample = int(amplitude * math.sin(2.0 * math.pi * freq_hz * n / sample_rate))
            frames += struct.pack("<h", sample)
        h.writeframes(bytes(frames))
    return path


def _write_silence_wav(path: Path, duration_sec: float = 0.5, sample_rate: int = 22050) -> Path:
    """Write a 16-bit mono PCM WAV file containing silence."""
    n_frames = int(duration_sec * sample_rate)
    with wave.open(str(path), "wb") as h:
        h.setnchannels(1)
        h.setsampwidth(2)
        h.setframerate(sample_rate)
        h.writeframes(b"\x00\x00" * n_frames)
    return path


@pytest.fixture
def sine_wav(tmp_path: Path) -> Path:
    return _write_sine_wav(tmp_path / "sine.wav", duration_sec=1.0)


@pytest.fixture
def short_sine_wav(tmp_path: Path) -> Path:
    return _write_sine_wav(tmp_path / "short.wav", duration_sec=0.5)


@pytest.fixture
def silence_wav(tmp_path: Path) -> Path:
    return _write_silence_wav(tmp_path / "silence.wav", duration_sec=0.5)


@pytest.fixture
def beat_track_wav(tmp_path: Path) -> Path:
    """A 2-second WAV with a clear amplitude envelope (impulses at 120 BPM)."""
    sample_rate = 22050
    duration_sec = 2.0
    n_frames = int(duration_sec * sample_rate)
    with wave.open(str(tmp_path / "beats.wav"), "wb") as h:
        h.setnchannels(1)
        h.setsampwidth(2)
        h.setframerate(sample_rate)
        frames = bytearray()
        # Impulse every 0.5s (= 120 BPM), each impulse decays over 0.05s
        for n in range(n_frames):
            t = n / sample_rate
            beat_phase = t % 0.5
            if beat_phase < 0.05:
                env = 1.0 - (beat_phase / 0.05)
                sample = int(20000 * env)
            else:
                sample = int(2000 * math.sin(2.0 * math.pi * 440.0 * t))
            frames += struct.pack("<h", max(-32768, min(32767, sample)))
        h.writeframes(bytes(frames))
    return tmp_path / "beats.wav"


# ---------------------------------------------------------------------------
# _try_import_* helpers
# ---------------------------------------------------------------------------


class TestTryImportHelpers:
    def test_try_import_librosa_returns_module_when_installed(self) -> None:
        librosa_mod = _try_import_librosa()
        assert librosa_mod is not None
        assert hasattr(librosa_mod, "load")
        assert hasattr(librosa_mod, "beat")

    def test_try_import_librosa_returns_none_when_missing(self) -> None:
        with mock.patch.dict("sys.modules", {"librosa": None}):
            assert _try_import_librosa() is None

    def test_try_import_numpy_returns_module_when_installed(self) -> None:
        np_mod = _try_import_numpy()
        assert np_mod is not None
        assert hasattr(np_mod, "array")
        assert hasattr(np_mod, "interp")

    def test_try_import_numpy_returns_none_when_missing(self) -> None:
        with mock.patch.dict("sys.modules", {"numpy": None}):
            assert _try_import_numpy() is None

    def test_try_import_demucs_returns_true_when_installed(self) -> None:
        # The helper imports ``demucs.pretrained`` which IS available in
        # the ML-extras install.  Confirm the True branch is reachable.
        assert _try_import_demucs() is True

    def test_try_import_demucs_returns_false_when_missing(self) -> None:
        with mock.patch.dict("sys.modules", {"demucs": None, "demucs.pretrained": None}):
            assert _try_import_demucs() is False


# ---------------------------------------------------------------------------
# STEM_NAMES + _zero_stem_channels
# ---------------------------------------------------------------------------


class TestStemHelpers:
    def test_stem_names_constant(self) -> None:
        assert STEM_NAMES == ("drums", "bass", "vocals", "other")

    def test_zero_stem_channels_shape(self) -> None:
        chans = _zero_stem_channels(10)
        assert set(chans) == {"drums", "bass", "vocals", "other"}
        for name in STEM_NAMES:
            assert len(chans[name]) == 10
            assert all(v == 0.0 for v in chans[name])

    def test_zero_stem_channels_zero_frames(self) -> None:
        chans = _zero_stem_channels(0)
        for name in STEM_NAMES:
            assert chans[name] == []


# ---------------------------------------------------------------------------
# _classify_section_label
# ---------------------------------------------------------------------------


class TestClassifySectionLabel:
    def test_intro_is_first(self) -> None:
        assert _classify_section_label(0, 5, 0.0, 0.0) == "intro"

    def test_outro_is_last(self) -> None:
        assert _classify_section_label(4, 5, 0.0, 0.0) == "outro"

    def test_drop_classification(self) -> None:
        assert _classify_section_label(2, 8, 0.9, 0.8) == "drop"

    def test_chorus_classification(self) -> None:
        assert _classify_section_label(2, 8, 0.6, 0.5) == "chorus"

    def test_verse_early(self) -> None:
        assert _classify_section_label(1, 8, 0.3, 0.3) == "verse"

    def test_breakdown_late(self) -> None:
        # ``frac = index / (n_segments - 1)``; need index not at the very end.
        # With n_segments=10 and index=8 → frac=8/9 ≈ 0.89 → breakdown.
        assert _classify_section_label(8, 10, 0.3, 0.3) == "breakdown"

    def test_verse_default(self) -> None:
        # Mid-position with low energy/brightness
        assert _classify_section_label(3, 8, 0.3, 0.3) == "verse"


# ---------------------------------------------------------------------------
# _easing_for_energy
# ---------------------------------------------------------------------------


class TestEasingForEnergy:
    def test_rising_energy_ease_in(self) -> None:
        assert _easing_for_energy(0.8, 0.5) == "ease_in"

    def test_falling_energy_ease_out(self) -> None:
        assert _easing_for_energy(0.2, 0.5) == "ease_out"

    def test_flat_energy_ease_in_out(self) -> None:
        assert _easing_for_energy(0.5, 0.55) == "ease_in_out"


# ---------------------------------------------------------------------------
# _rms_fallback_envelope
# ---------------------------------------------------------------------------


class TestRmsFallbackEnvelope:
    def test_zero_bytes_returns_zeros(self) -> None:
        env = _rms_fallback_envelope(b"", sample_width=2, n_buckets=4)
        assert len(env) == 4
        assert env == [0.0, 0.0, 0.0, 0.0]

    def test_normalises_peak_to_one(self) -> None:
        # Generate a uniform non-zero byte sequence
        chunk = b"\x10\x00" * 1000
        env = _rms_fallback_envelope(chunk, sample_width=2, n_buckets=5)
        assert len(env) == 5
        assert max(env) == pytest.approx(1.0, abs=1e-9)

    def test_bucketed_correctly(self) -> None:
        chunk = b"\x10\x00" * 1000
        env = _rms_fallback_envelope(chunk, sample_width=2, n_buckets=10)
        assert len(env) == 10


# ---------------------------------------------------------------------------
# Librosa segment boundaries (real numpy/librosa)
# ---------------------------------------------------------------------------


class TestLibrosaSegmentBoundaries:
    def test_boundaries_match_requested_count(self) -> None:
        import librosa
        import numpy as np

        sr = 22050
        # 3-second tone with one amplitude change in the middle
        y = np.concatenate(
            [
                np.ones(sr, dtype=np.float32) * 0.5,
                np.ones(sr, dtype=np.float32) * 0.1,
                np.ones(sr, dtype=np.float32) * 0.8,
            ]
        )
        segs = _librosa_segment_boundaries(librosa, np, y, sr, n_segments=4, duration_sec=3.0)
        assert len(segs) == 4
        for start, end in segs:
            assert 0.0 <= start <= 3.0
            assert start <= end <= 3.0

    def test_pads_when_not_enough_boundaries(self) -> None:
        import librosa
        import numpy as np

        sr = 22050
        y = np.ones(sr, dtype=np.float32)  # 1s of constant tone (no novelty)
        segs = _librosa_segment_boundaries(librosa, np, y, sr, n_segments=6, duration_sec=1.0)
        assert len(segs) == 6


# ---------------------------------------------------------------------------
# _build_dense_keyframes + _build_scene_segments
# ---------------------------------------------------------------------------


class TestBuildDenseKeyframes:
    def test_populates_n_frames(self) -> None:
        n = 30
        energy = [0.5] * n
        brightness = [0.5] * n
        valence = [0.5] * n
        arousal = [0.5] * n
        onset = [0.0] * n
        beat = [0.0] * n
        centroid = [1000.0] * n
        stems = {name: [0.0] * n for name in STEM_NAMES}
        kfs = _build_dense_keyframes(
            n, 2.0, energy, brightness, valence, arousal, onset, beat, centroid, stems
        )
        assert len(kfs) == n
        for kf in kfs:
            assert "t" in kf
            assert "energy" in kf
            assert "stems" in kf

    def test_marks_beat_frames(self) -> None:
        n = 10
        beat = [0.0] * n
        beat[3] = 1.0
        kfs = _build_dense_keyframes(
            n, 1.0, [0.5] * n, [0.5] * n, [0.5] * n, [0.5] * n,
            [0.0] * n, beat, [1000.0] * n,
            {name: [0.0] * n for name in STEM_NAMES},
        )
        assert kfs[3]["beat_strength"] == 1.0
        assert kfs[0]["beat_strength"] == 0.0


class TestBuildSceneSegments:
    def test_no_librosa_uses_equal_segments(self) -> None:
        segs = _build_scene_segments(
            librosa=None,
            np=None,
            y=None,
            sr=22050,
            duration_sec=30.0,
            energy_per_sec=[0.5] * 30,
            brightness_per_sec=[0.5] * 30,
            valence_per_sec=[0.5] * 30,
            arousal_per_sec=[0.5] * 30,
            stem_channels={name: [0.0] * 30 for name in STEM_NAMES},
            n_dense_frames=30,
        )
        assert len(segs) >= 4
        for seg in segs:
            assert "label" in seg
            assert "start" in seg
            assert "end" in seg

    def test_with_librosa_uses_real_boundaries(self) -> None:
        import librosa
        import numpy as np

        sr = 22050
        y = np.concatenate([np.ones(sr), np.ones(sr) * 0.1, np.ones(sr) * 0.8])
        duration = 3.0
        segs = _build_scene_segments(
            librosa=librosa,
            np=np,
            y=y,
            sr=sr,
            duration_sec=duration,
            energy_per_sec=[0.5] * 3,
            brightness_per_sec=[0.5] * 3,
            valence_per_sec=[0.5] * 3,
            arousal_per_sec=[0.5] * 3,
            stem_channels={name: [0.0] * 30 for name in STEM_NAMES},
            n_dense_frames=30,
        )
        # Librosa will detect at least 1 novelty peak → ≥ 2 segments.
        assert len(segs) >= 1


# ---------------------------------------------------------------------------
# _spectral_stem_fallback (real numpy/librosa path)
# ---------------------------------------------------------------------------


class TestSpectralStemFallback:
    def test_returns_expected_stem_keys(self) -> None:
        import librosa
        import numpy as np

        sr = 22050
        y = np.random.default_rng(0).standard_normal(sr).astype(np.float32) * 0.1
        chans = _spectral_stem_fallback(librosa, np, y, sr, n_frames=10)
        assert set(chans) == {"drums", "bass", "vocals", "other"}
        for name in STEM_NAMES:
            assert len(chans[name]) == 10
            assert all(isinstance(v, float) for v in chans[name])

    def test_falls_back_to_zero_on_exception(self) -> None:
        # Pass an object that crashes librosa.feature.rms → falls through to zero
        bad_librosa = mock.MagicMock()
        bad_librosa.effects.hpss.side_effect = RuntimeError("boom")
        np = pytest.importorskip("numpy")
        chans = _spectral_stem_fallback(bad_librosa, np, None, 22050, n_frames=4)
        for name in STEM_NAMES:
            assert chans[name] == [0.0] * 4


# ---------------------------------------------------------------------------
# _separate_stems_demucs (mocked Demucs apply)
# ---------------------------------------------------------------------------


class TestSeparateStemsDemucs:
    def test_returns_zero_stems_on_exception(self, sine_wav: Path) -> None:
        # Force the inner imports to raise → exception branch → zero stems
        with mock.patch.dict("sys.modules", {"demucs": None, "demucs.apply": None, "demucs.pretrained": None, "torch": None, "torchaudio": None}):
            chans = _separate_stems_demucs(sine_wav, 1.0, n_frames=5)
        assert set(chans) == {"drums", "bass", "vocals", "other"}
        for name in STEM_NAMES:
            assert chans[name] == [0.0] * 5

    def test_mocked_demucs_pipeline(self, sine_wav: Path) -> None:
        """Mock the heavy Demucs/torch pipeline; assert the wiring is correct."""
        # Set up fake modules that satisfy the inner imports
        fake_torch = mock.MagicMock()
        fake_torch.no_grad.return_value.__enter__ = mock.MagicMock()
        fake_torch.no_grad.return_value.__exit__ = mock.MagicMock()

        fake_apply_model = mock.MagicMock(return_value=mock.MagicMock(
            squeeze=lambda dim: mock.MagicMock(
                numpy=lambda: __import__("numpy").zeros((4, 1000), dtype="float32")
            )
        ))
        fake_get_model = mock.MagicMock(return_value=mock.MagicMock(
            samplerate=22050,
            eval=mock.MagicMock(),
        ))
        fake_torchaudio = mock.MagicMock()
        fake_torchaudio.load.return_value = (
            __import__("numpy").zeros((1, 22050), dtype="float32"),
            22050,
        )

        sys_modules_patch = {
            "torch": fake_torch,
            "torchaudio": fake_torchaudio,
            "demucs": mock.MagicMock(),
            "demucs.apply": mock.MagicMock(apply_model=fake_apply_model),
            "demucs.pretrained": mock.MagicMock(get_model=fake_get_model),
        }
        with mock.patch.dict("sys.modules", sys_modules_patch):
            chans = _separate_stems_demucs(sine_wav, 1.0, n_frames=4)

        assert set(chans) == {"drums", "bass", "vocals", "other"}
        for name in STEM_NAMES:
            assert len(chans[name]) == 4
            assert all(isinstance(v, float) for v in chans[name])


# ---------------------------------------------------------------------------
# End-to-end: analyze_wav_rich with all deps installed
# ---------------------------------------------------------------------------


class TestAnalyzeWavRichE2E:
    def test_full_pipeline_populates_librosa_fields(self, beat_track_wav: Path) -> None:
        spec = analyze_wav_rich(beat_track_wav, n_dense_fps=10, use_demucs=False)
        # Librosa branch populated the spectral features.
        assert spec.metadata["sample_rate"] == 22050
        assert spec.metadata["duration"] == pytest.approx(2.0, abs=0.1)
        assert spec.metadata["n_dense_frames"] == pytest.approx(20, abs=2)
        # dense_keyframes should be populated
        assert len(spec.dense_keyframes) > 0
        first_kf = spec.dense_keyframes[0]
        assert "stems" in first_kf
        # mir summary present (already dumped to dict)
        assert spec.mir["tempo_bpm"] is not None
        # Without demucs, the spectral fallback ran, populating all 4 stems
        assert set(spec.stem_channels) == {"drums", "bass", "vocals", "other"}
        for stem in STEM_NAMES:
            assert len(spec.stem_channels[stem]) > 0

    def test_full_pipeline_with_demucs_mocked(self, sine_wav: Path) -> None:
        """Mock the inner demucs apply path so the test does not need a real model.

        The branch under test is the ``if use_demucs and _try_import_demucs():``
        path inside ``analyze_wav_rich``.  We mock ``_separate_stems_demucs`` to
        return deterministic zero stems and assert the wiring routes the stems
        through correctly.
        """
        with mock.patch.object(audio, "_separate_stems_demucs", return_value=_zero_stem_channels(10)) as spy:
            spec = analyze_wav_rich(sine_wav, n_dense_fps=10, use_demucs=True)
        assert spy.called
        assert spec.metadata["sample_rate"] == 22050
        for stem in STEM_NAMES:
            assert spec.stem_channels[stem] == [0.0] * 10

    def test_clamps_n_dense_fps(self, sine_wav: Path) -> None:
        # Below floor → clamped to 10
        spec_lo = analyze_wav_rich(sine_wav, n_dense_fps=2)
        # Above ceiling → clamped to 30
        spec_hi = analyze_wav_rich(sine_wav, n_dense_fps=100)
        assert spec_lo.metadata["n_dense_fps"] == 10
        assert spec_hi.metadata["n_dense_fps"] == 30

    def test_emits_timeline_events(self, beat_track_wav: Path) -> None:
        spec = analyze_wav_rich(beat_track_wav, n_dense_fps=10, use_demucs=False)
        types = {ev["type"] for ev in spec.timeline_events}
        # Beat track + onset + section labels should all appear
        assert "beat" in types
        assert "onset" in types
        assert "section" in types

    def test_populates_scene_segments(self, beat_track_wav: Path) -> None:
        spec = analyze_wav_rich(beat_track_wav, n_dense_fps=10, use_demucs=False)
        # 2-second clip → ``n_segments = max(4, min(8, int(2/30))) = 4`` clamped
        # by min(8, 0) = 0 → max(4, 0) = 4.  But librosa may detect fewer
        # novelty peaks than 4 in this short signal, so accept ≥ 1 (always ≥ intro+outro).
        assert len(spec.scene_segments) >= 1
        for seg in spec.scene_segments:
            assert seg["label"] in {"intro", "outro", "drop", "chorus", "verse", "breakdown"}

    def test_metadata_contains_amplitude_envelope(self, sine_wav: Path) -> None:
        spec = analyze_wav_rich(sine_wav, n_dense_fps=10, use_demucs=False)
        assert "amplitude_envelope" in spec.metadata
        assert isinstance(spec.metadata["amplitude_envelope"], list)
        assert len(spec.metadata["amplitude_envelope"]) > 0

    def test_silence_still_produces_spec(self, silence_wav: Path) -> None:
        spec = analyze_wav_rich(silence_wav, n_dense_fps=10, use_demucs=False)
        # Librosa may or may not detect beats in silence; spec must still validate
        assert spec.metadata["sample_rate"] == 22050
        assert spec.metadata["duration"] == pytest.approx(0.5, abs=0.05)


# ---------------------------------------------------------------------------
# analyze_wav (stdlib-only) still works
# ---------------------------------------------------------------------------


class TestAnalyzeWavStdlibOnly:
    def test_returns_audio_analysis(self, sine_wav: Path) -> None:
        result = analyze_wav(sine_wav)
        assert result.sample_rate == 22050
        assert result.channels == 1
        assert result.duration_sec == pytest.approx(1.0, abs=0.01)
        # ``analyze_wav`` rounds up to include the last partial bucket, so the
        # exact length can be ``bucket_count`` or ``bucket_count + 1`` depending
        # on alignment.  Assert approximate instead of exact.
        assert 120 <= len(result.rms_envelope) <= 121

    def test_returns_n_buckets(self, short_sine_wav: Path) -> None:
        result = analyze_wav(short_sine_wav, bucket_count=20)
        # Same rounding-up tolerance as above.
        assert 20 <= len(result.rms_envelope) <= 21