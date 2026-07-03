"""Regression tests for the numba/cp314 SIGSEGV fix in beat tracking.

Covers:
1. ``_numpy_beat_fallback`` — pure-numpy estimator, synthetic click-track.
2. ``_safe_beat_track`` — subprocess-isolation wrapper (mocked child crash path
   and successful path).
3. ``spec_from_wav_rich`` end-to-end against the real k.wav fixture — regression
   guard that the build path completes without exit 139 and returns a plausible
   tempo.
4. ``_cmd_build`` integration — mirrors the Desktop "Render Video" invocation.

These tests must pass under CPython 3.14 (the crash environment) as well as
3.12/3.13.  They do NOT require numba to be healthy — the whole point is that
the fix survives a broken numba.
"""
from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"
K_WAV = FIXTURES / "k.wav"


def _make_click_track(
    bpm: float,
    duration_sec: float,
    sample_rate: int = 44100,
    amplitude: float = 0.8,
    tmp_path: Path | None = None,
) -> "tuple[Any, int]":  # noqa: F821
    """Return (y_np, sr) numpy float32 array with a metronome click-track.

    Each beat is represented by a single-sample impulse at the correct
    position.  We use numpy internally so the return value is ready for
    _numpy_beat_fallback / _safe_beat_track.
    """
    import numpy as np

    n_samples = int(duration_sec * sample_rate)
    y = np.zeros(n_samples, dtype=np.float32)
    beat_period = sample_rate * 60.0 / bpm
    idx = 0.0
    while idx < n_samples:
        pos = int(round(idx))
        if pos < n_samples:
            y[pos] = amplitude
        idx += beat_period
    return y, sample_rate


# ---------------------------------------------------------------------------
# 1.  Pure-numpy fallback estimator
# ---------------------------------------------------------------------------

class TestNumpyBeatFallback:
    """Unit tests for _numpy_beat_fallback — no librosa/numba involved."""

    @pytest.mark.parametrize("bpm", [60.0, 90.0, 120.0, 140.0])
    def test_click_track_tempo_within_tolerance(self, bpm: float) -> None:
        """Estimated BPM must be within ±20% of the ground-truth click-track BPM."""
        from melosviz.analysis.audio import _numpy_beat_fallback

        y, sr = _make_click_track(bpm=bpm, duration_sec=10.0)
        estimated_bpm, beat_times = _numpy_beat_fallback(y, sr)

        tolerance = 0.20 * bpm  # 20 % — autocorrelation may find a harmonic
        # Accept the estimate OR half/double (harmonic octave errors are common)
        acceptable = any(
            abs(estimated_bpm * mult - bpm) <= tolerance
            for mult in (0.5, 1.0, 2.0)
        )
        assert acceptable, (
            f"estimated {estimated_bpm:.1f} BPM (×0.5={estimated_bpm*0.5:.1f}, "
            f"×2={estimated_bpm*2:.1f}) not within 20% of {bpm} BPM"
        )

    def test_output_bpm_clamped_to_range(self) -> None:
        """BPM output must always fall in [40, 240]."""
        import numpy as np
        from melosviz.analysis.audio import _numpy_beat_fallback

        # DC signal — no beats, forces the fallback branch
        y = np.ones(44100, dtype=np.float32)
        bpm, _ = _numpy_beat_fallback(y, 44100)
        assert 40.0 <= bpm <= 240.0

    def test_returns_list_of_floats(self) -> None:
        from melosviz.analysis.audio import _numpy_beat_fallback

        y, sr = _make_click_track(bpm=120.0, duration_sec=5.0)
        bpm, beat_times = _numpy_beat_fallback(y, sr)
        assert isinstance(bpm, float)
        assert isinstance(beat_times, list)
        assert all(isinstance(t, float) for t in beat_times)

    def test_beat_times_monotonically_increasing(self) -> None:
        from melosviz.analysis.audio import _numpy_beat_fallback

        y, sr = _make_click_track(bpm=120.0, duration_sec=8.0)
        _, beat_times = _numpy_beat_fallback(y, sr)
        for a, b in zip(beat_times, beat_times[1:]):
            assert b > a, f"non-monotonic: {a} then {b}"

    def test_silence_does_not_crash(self) -> None:
        import numpy as np
        from melosviz.analysis.audio import _numpy_beat_fallback

        y = np.zeros(44100, dtype=np.float32)
        bpm, _ = _numpy_beat_fallback(y, 44100)
        assert 40.0 <= bpm <= 240.0

    def test_very_short_signal(self) -> None:
        """Short signals (< 1 hop) must not crash."""
        import numpy as np
        from melosviz.analysis.audio import _numpy_beat_fallback

        y = np.array([0.1, -0.1, 0.2], dtype=np.float32)
        bpm, _ = _numpy_beat_fallback(y, 44100)
        assert isinstance(bpm, float)

    def test_never_imports_numba(self) -> None:
        """The fallback must not trigger numba — block the import and confirm."""
        import sys
        from melosviz.analysis.audio import _numpy_beat_fallback
        import numpy as np

        y, sr = _make_click_track(bpm=120.0, duration_sec=4.0)

        # Patch numba so any attempt to import raises ImportError
        with mock.patch.dict(sys.modules, {"numba": None}):
            bpm, _ = _numpy_beat_fallback(y, sr)
        assert isinstance(bpm, float)


# ---------------------------------------------------------------------------
# 2.  Subprocess-isolation wrapper
# ---------------------------------------------------------------------------

class TestSafeBeatTrack:
    """Tests for _safe_beat_track — the subprocess-isolation wrapper."""

    def _get_y_sr(self) -> "tuple[Any, int]":  # noqa: F821
        import numpy as np
        return _make_click_track(bpm=120.0, duration_sec=6.0)

    def _get_librosa(self) -> object:
        from melosviz.analysis.audio import _try_import_librosa
        librosa = _try_import_librosa()
        if librosa is None:
            pytest.skip("librosa not installed")
        return librosa

    def test_success_path_returns_plausible_result(self) -> None:
        """When the child succeeds, result must be a plausible (tempo, beats) pair."""
        from melosviz.analysis.audio import _safe_beat_track

        y, sr = self._get_y_sr()
        librosa = self._get_librosa()
        tempo, beats = _safe_beat_track(y, sr, librosa)
        assert isinstance(tempo, float)
        assert 40.0 <= tempo <= 240.0
        assert isinstance(beats, list)

    def test_crash_falls_back_to_numpy(self) -> None:
        """Simulate child crash (exitcode != 0) → parent must use numpy fallback."""
        import numpy as np
        from melosviz.analysis.audio import _safe_beat_track, _numpy_beat_fallback

        y, sr = self._get_y_sr()
        librosa = self._get_librosa()

        # Patch multiprocessing.Process to simulate a SIGSEGV (exitcode = -11)
        class _CrashingProcess:
            def __init__(self, *a: object, **kw: object) -> None:
                pass

            def start(self) -> None:
                pass

            def join(self, timeout: float | None = None) -> None:
                pass

            exitcode = -11  # SIGSEGV

        import multiprocessing
        with mock.patch("multiprocessing.get_context") as mock_ctx:
            mock_ctx.return_value.Process = _CrashingProcess
            tempo, beats = _safe_beat_track(y, sr, librosa)

        # Result must come from the numpy fallback
        expected_tempo, _ = _numpy_beat_fallback(y, sr)
        assert tempo == pytest.approx(expected_tempo, rel=0.01)

    def test_timeout_falls_back_to_numpy(self) -> None:
        """Simulate child timeout (None exitcode) → fall back to numpy."""
        import numpy as np
        from melosviz.analysis.audio import _safe_beat_track, _numpy_beat_fallback

        y, sr = self._get_y_sr()
        librosa = self._get_librosa()

        class _TimedOutProcess:
            def __init__(self, *a: object, **kw: object) -> None:
                pass

            def start(self) -> None:
                pass

            def join(self, timeout: float | None = None) -> None:
                pass

            exitcode = None  # timed out

        import multiprocessing
        with mock.patch("multiprocessing.get_context") as mock_ctx:
            mock_ctx.return_value.Process = _TimedOutProcess
            tempo, beats = _safe_beat_track(y, sr, librosa)

        expected_tempo, _ = _numpy_beat_fallback(y, sr)
        assert tempo == pytest.approx(expected_tempo, rel=0.01)

    def test_exception_in_wrapper_falls_back(self) -> None:
        """An exception inside _safe_beat_track itself must not propagate."""
        import numpy as np
        from melosviz.analysis.audio import _safe_beat_track

        y, sr = self._get_y_sr()
        librosa = self._get_librosa()

        # Patch multiprocessing.get_context in the stdlib (used by the function
        # via a local `import multiprocessing` — patching the module dict works
        # because Python's import cache is shared).
        import multiprocessing as _mp
        with mock.patch.object(_mp, "get_context", side_effect=RuntimeError("mock error")):
            tempo, beats = _safe_beat_track(y, sr, librosa)

        assert isinstance(tempo, float)
        assert isinstance(beats, list)


# ---------------------------------------------------------------------------
# 3.  End-to-end regression guard (spec_from_wav_rich on k.wav)
# ---------------------------------------------------------------------------

class TestSpecFromWavRichRegression:
    """Regression test — the actual crash path that produced exit 139."""

    @pytest.mark.skipif(not K_WAV.exists(), reason="k.wav fixture not found")
    def test_spec_from_wav_rich_exit_0(self) -> None:
        """spec_from_wav_rich must complete (no SIGSEGV) and return a valid spec."""
        from melosviz.analysis.audio import spec_from_wav_rich

        spec = spec_from_wav_rich(K_WAV)
        assert spec is not None

    @pytest.mark.skipif(not K_WAV.exists(), reason="k.wav fixture not found")
    def test_spec_from_wav_rich_plausible_tempo(self) -> None:
        """spec_from_wav_rich must return a tempo in [40, 240] BPM."""
        from melosviz.analysis.audio import spec_from_wav_rich

        spec = spec_from_wav_rich(K_WAV)
        mir = spec.model_dump().get("mir", {})
        tempo = mir.get("tempo_bpm")
        # With librosa available, tempo must be populated
        from melosviz.analysis.audio import _try_import_librosa
        if _try_import_librosa() is not None:
            assert tempo is not None, "tempo_bpm must be populated when librosa is installed"
            assert 40.0 <= tempo <= 240.0, f"tempo {tempo} out of [40, 240]"

    @pytest.mark.skipif(not K_WAV.exists(), reason="k.wav fixture not found")
    def test_spec_from_wav_rich_has_keyframes_and_segments(self) -> None:
        """spec must have dense_keyframes and scene_segments populated."""
        from melosviz.analysis.audio import spec_from_wav_rich

        spec = spec_from_wav_rich(K_WAV)
        assert len(spec.dense_keyframes) > 0, "dense_keyframes must not be empty"
        assert len(spec.scene_segments) > 0, "scene_segments must not be empty"


# ---------------------------------------------------------------------------
# 4.  _cmd_build integration (mirrors Desktop "Render Video")
# ---------------------------------------------------------------------------

class TestCmdBuildIntegration:
    """Integration test for _cmd_build — mirrors the Desktop 'Render Video' path."""

    @pytest.mark.skipif(not K_WAV.exists(), reason="k.wav fixture not found")
    def test_cmd_build_returns_0(self, tmp_path: Path) -> None:
        """_cmd_build must return exit code 0 for k.wav."""
        import argparse
        from melosviz.cli.main import _cmd_build

        args = argparse.Namespace(wav=str(K_WAV), out=str(tmp_path), real=False)
        result = _cmd_build(args)
        assert result == 0, f"_cmd_build returned {result}, expected 0"

    @pytest.mark.skipif(not K_WAV.exists(), reason="k.wav fixture not found")
    def test_cmd_build_emits_valid_json(self, tmp_path: Path) -> None:
        """_cmd_build must write a parseable render_plan.json."""
        import argparse
        from melosviz.cli.main import _cmd_build

        args = argparse.Namespace(wav=str(K_WAV), out=str(tmp_path), real=False)
        _cmd_build(args)
        plan_path = tmp_path / "render_plan.json"
        assert plan_path.exists(), "render_plan.json not written"
        plan = json.loads(plan_path.read_text())
        assert isinstance(plan, dict), "render_plan must be a JSON object"
        # Must have at least version and segments keys (assemble_render_plan output)
        assert "segments" in plan or "version" in plan, (
            f"render_plan missing expected keys; got: {list(plan.keys())}"
        )
