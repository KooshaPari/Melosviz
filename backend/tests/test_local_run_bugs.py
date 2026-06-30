"""Regression tests for bugs found during local run validation (2026-06-30).

Bug 1: viz build CLI calls spec_from_wav (v1) instead of spec_from_wav_rich (v2),
       causing assemble_render_plan to fail with empty scene_segments.
Bug 2: audioop segment alignment crash — segment_size not aligned to sample_width,
       causing audioop.rms to raise 'not a whole number of frames'.
Bug 3: Flat amplitude_envelope (all 0.5) without librosa — stdlib fallback must
       compute real RMS per window via the wave module.
"""

from __future__ import annotations

import array
import math
import struct
import wave
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_mono_wav(path: Path, duration_sec: float = 5.0, sr: int = 44100) -> Path:
    """Write a 16-bit mono sine-wave WAV with varying amplitude (not flat)."""
    n_frames = int(duration_sec * sr)
    path.parent.mkdir(parents=True, exist_ok=True)
    samples: list[int] = []
    for i in range(n_frames):
        t = i / sr
        # Amplitude envelope: quiet first quarter, loud second half
        amp = 2000 if t < duration_sec / 4 else 16000
        val = int(amp * math.sin(2 * math.pi * 440.0 * t))
        samples.append(val)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return path


def _write_stereo_wav(path: Path, duration_sec: float = 5.0, sr: int = 44100) -> Path:
    """Write a 16-bit stereo WAV — needed to exercise audioop.tomono path."""
    n_frames = int(duration_sec * sr)
    path.parent.mkdir(parents=True, exist_ok=True)
    samples_arr = array.array("h")
    for i in range(n_frames):
        t = i / sr
        val = int(16000 * math.sin(2 * math.pi * 440.0 * t))
        samples_arr.append(val)  # left
        samples_arr.append(val)  # right
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples_arr.tobytes())
    return path


# ---------------------------------------------------------------------------
# Bug 1: viz build uses spec_from_wav_rich (v2 path)
# ---------------------------------------------------------------------------


class TestVizBuildUsesRichSpec:
    """viz build must call spec_from_wav_rich, not spec_from_wav (v1)."""

    def test_cmd_build_returns_non_empty_plan(self, tmp_path: Path) -> None:
        """_cmd_build produces a plan with at least one segment (not empty)."""
        import types

        from melosviz.cli.main import _cmd_build

        wav = _write_mono_wav(tmp_path / "tone.wav")
        args = types.SimpleNamespace(wav=str(wav), out=None, real=False)
        rc = _cmd_build(args)  # type: ignore[arg-type]
        assert rc == 0, "_cmd_build should exit 0"

    def test_cmd_build_plan_has_segments(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """The plan JSON printed by _cmd_build must have segment_count > 0."""
        import json
        import types

        from melosviz.cli.main import _cmd_build

        wav = _write_mono_wav(tmp_path / "tone.wav")
        args = types.SimpleNamespace(wav=str(wav), out=None, real=False)
        rc = _cmd_build(args)  # type: ignore[arg-type]
        assert rc == 0
        captured = capsys.readouterr()
        plan = json.loads(captured.out)
        assert plan["segment_count"] > 0, (
            f"segment_count is 0 — CLI is using v1 spec_from_wav which has no scene_segments. "
            f"plan={plan}"
        )

    def test_cmd_analyze_produces_v2_fields(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """viz analyze should produce scene_segments in its output (v2 path)."""
        import json
        import types

        from melosviz.cli.main import _cmd_analyze

        wav = _write_mono_wav(tmp_path / "tone.wav")
        args = types.SimpleNamespace(wav=str(wav))
        rc = _cmd_analyze(args)  # type: ignore[arg-type]
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "scene_segments" in data, (
            "viz analyze must output scene_segments (v2 fields). "
            "It is still calling spec_from_wav (v1)."
        )
        assert len(data["scene_segments"]) > 0, "scene_segments must be non-empty"


# ---------------------------------------------------------------------------
# Bug 2: audioop segment alignment — must not raise 'not a whole number of frames'
# ---------------------------------------------------------------------------


class TestAudioopFrameAlignment:
    """analyze_wav with audioop-lts must not crash on odd segment sizes."""

    def test_analyze_wav_with_audioop_does_not_crash(self, tmp_path: Path) -> None:
        """analyze_wav must succeed when audioop is available (no alignment error)."""
        # Import the real audioop-lts if present, else skip (test proves the fix)
        try:
            import audioop as _ao  # noqa: F401
            has_audioop = True
        except ImportError:
            has_audioop = False

        from melosviz.analysis.audio import analyze_wav

        wav = _write_mono_wav(tmp_path / "tone.wav", duration_sec=10.0, sr=44100)
        # This would crash with 'not a whole number of frames' before the fix
        result = analyze_wav(str(wav), bucket_count=120)
        assert result is not None
        assert result.duration_sec > 0
        assert len(result.rms_envelope) > 0

    def test_analyze_wav_audioop_segment_is_frame_aligned(self, tmp_path: Path) -> None:
        """With a mocked audioop, segment passed to rms() is always frame-aligned."""
        call_args: list[tuple[bytes, int]] = []

        class FakeAudioop:
            @staticmethod
            def rms(data: bytes, width: int) -> int:
                call_args.append((data, width))
                if len(data) % width != 0:
                    raise Exception("not a whole number of frames")
                return 1000

            @staticmethod
            def tomono(data: bytes, width: int, lfac: float, rfac: float) -> bytes:
                return data[::2]  # naively halve for test purposes

        wav = _write_mono_wav(tmp_path / "tone.wav", duration_sec=10.0, sr=44100)

        import melosviz.analysis.audio as _audio_mod

        orig_has = _audio_mod._HAS_AUDIOOP
        orig_mod = _audio_mod._audioop
        try:
            _audio_mod._HAS_AUDIOOP = True
            _audio_mod._audioop = FakeAudioop  # type: ignore[assignment]
            result = _audio_mod.analyze_wav(str(wav), bucket_count=120)
        finally:
            _audio_mod._HAS_AUDIOOP = orig_has
            _audio_mod._audioop = orig_mod

        # Every segment passed to rms must be frame-aligned (width=2)
        for data, width in call_args:
            assert len(data) % width == 0, (
                f"Segment size {len(data)} is not a multiple of sample_width {width}. "
                "The alignment fix is not working."
            )
        assert result is not None


# ---------------------------------------------------------------------------
# Bug 3: dep-light amplitude_envelope must not be all-0.5
# ---------------------------------------------------------------------------


class TestDepLightAmplitudeEnvelope:
    """Without librosa, amplitude_envelope must be real RMS (not flat 0.5)."""

    def test_analyze_wav_no_audioop_returns_real_rms(self, tmp_path: Path) -> None:
        """When audioop is unavailable, envelope must vary (not all 0.5)."""
        from melosviz.analysis.audio import analyze_wav

        # Write a WAV with clearly different amplitudes in first vs second half
        wav = _write_mono_wav(tmp_path / "varied.wav", duration_sec=4.0, sr=44100)

        with patch("melosviz.analysis.audio._HAS_AUDIOOP", False):
            result = analyze_wav(str(wav), bucket_count=40)

        envelope = result.rms_envelope
        assert len(envelope) > 0
        # If all values are exactly 0.5, the stdlib fallback is still flat
        unique_values = set(round(v, 4) for v in envelope)
        assert len(unique_values) > 1, (
            f"amplitude_envelope is flat: {envelope[:8]}… — "
            "the dep-light path must compute real RMS, not return [0.5]*n"
        )

    def test_segment_energy_varies_across_segments_dep_light(self, tmp_path: Path) -> None:
        """test_segment_energy_varies_across_segments must pass WITHOUT librosa."""
        from melosviz.analysis.audio import analyze_wav_rich

        # Varied WAV: quiet first quarter, loud rest
        wav = _write_mono_wav(tmp_path / "varied.wav", duration_sec=60.0, sr=22050)

        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
            patch("melosviz.analysis.audio._HAS_AUDIOOP", False),
        ):
            spec = analyze_wav_rich(str(wav))

        energies = [seg["energy_mean"] for seg in spec.scene_segments]
        assert len(set(energies)) > 1, (
            f"All segments have same energy {energies} — "
            "dep-light amplitude_envelope is still flat."
        )
