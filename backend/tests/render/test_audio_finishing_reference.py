"""Tests for reference-matched mastering (``audio_finishing.reference``).

Covers the three-axis signature measurement (integrated loudness, loudness
range, true peak), the convergence loop, the threshold-as-LRA-lever rule, and
graceful degradation when ffmpeg is unavailable or emits no Summary block.
"""

from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path

import pytest

from melosviz.render.audio_finishing import (
    ReferenceMatchResult,
    ReferenceProfile,
    analyze_reference,
    ffmpeg_available,
    match_reference,
    measure_profile,
)
from melosviz.render.audio_finishing import reference as reference_mod

pytestmark = pytest.mark.skipif(
    not ffmpeg_available(), reason="ffmpeg not available for reference mastering"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _synthesize_dynamic_wav(
    path: Path,
    *,
    loud_s: float = 4.0,
    quiet_s: float = 4.0,
    sr: int = 22050,
    freq_hz: float = 220.0,
) -> Path:
    """Synthesize a two-section WAV (loud then quiet) so LRA is meaningful."""
    loud_n = int(sr * loud_s)
    quiet_n = int(sr * quiet_s)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        for i in range(loud_n + quiet_n):
            amp = 0.6 if i < loud_n else 0.05
            sample = int(
                max(-1.0, min(1.0, amp * math.sin(2 * math.pi * freq_hz * i / sr))) * 32767
            )
            w.writeframesraw(struct.pack("<h", sample))
    return path


@pytest.fixture
def dynamic_wav(tmp_path: Path) -> Path:
    return _synthesize_dynamic_wav(tmp_path / "dynamic.wav")


# ---------------------------------------------------------------------------
# Signature measurement
# ---------------------------------------------------------------------------


def test_measure_profile_returns_sane_signature(dynamic_wav: Path):
    """ebur128 measurement must yield a plausible three-axis signature."""
    profile = measure_profile(dynamic_wav)
    assert isinstance(profile, ReferenceProfile)
    assert profile.source == str(dynamic_wav)
    assert -60.0 < profile.integrated_lufs < 0.0
    # Two very different level sections must produce a non-zero range.
    assert profile.lra > 1.0
    assert profile.true_peak_dbtp <= 6.0


def test_analyze_reference_is_measure_profile_alias(dynamic_wav: Path):
    """analyze_reference is the public name for signature measurement."""
    direct = measure_profile(dynamic_wav)
    alias = analyze_reference(dynamic_wav)
    assert alias.integrated_lufs == pytest.approx(direct.integrated_lufs, abs=0.01)
    assert alias.lra == pytest.approx(direct.lra, abs=0.01)


def test_measure_profile_survives_missing_ffmpeg(monkeypatch, dynamic_wav: Path):
    """A 127 return (no ffmpeg) must not raise; defaults are returned."""
    monkeypatch.setattr(reference_mod, "run", lambda *a, **k: (127, "", "not found"))
    profile = measure_profile(dynamic_wav)
    assert isinstance(profile, ReferenceProfile)
    assert profile.integrated_lufs == -14.0  # documented default
    assert profile.true_peak_dbtp == -1.0


def test_measure_profile_survives_missing_summary_block(monkeypatch, dynamic_wav: Path):
    """ffmpeg success without a Summary block must not raise or parse garbage."""
    monkeypatch.setattr(reference_mod, "run", lambda *a, **k: (0, "noise", "still no summary here"))
    profile = measure_profile(dynamic_wav)
    assert profile.integrated_lufs == -14.0


# ---------------------------------------------------------------------------
# Convergence loop
# ---------------------------------------------------------------------------


def test_match_reference_converges_loudness_and_narrows_range(dynamic_wav: Path, tmp_path: Path):
    """Matching a quieter, narrower target must move both axes toward it."""
    source = measure_profile(dynamic_wav)
    target = ReferenceProfile(
        source="synthetic-target",
        integrated_lufs=-14.0,
        lra=max(1.5, source.lra - 4.0),
        true_peak_dbtp=-3.0,
    )
    out = tmp_path / "matched.wav"
    result = match_reference(dynamic_wav, out, target, max_iterations=6, tol_lufs=0.4, tol_lra=0.6)

    assert out.exists() and out.stat().st_size > 0
    assert isinstance(result, ReferenceMatchResult)
    assert result.achieved is not None
    assert result.iterations >= 1
    assert len(result.history) == result.iterations

    # Loudness must land near the target, and be closer than the source was.
    achieved_error = abs(result.achieved.integrated_lufs - target.integrated_lufs)
    source_error = abs(source.integrated_lufs - target.integrated_lufs)
    assert achieved_error <= 1.0
    assert achieved_error < source_error

    # The loop must actually have narrowed the range.
    assert result.achieved.lra < source.lra

    # True peak must respect the target ceiling (small tolerance for ISP).
    assert result.achieved.true_peak_dbtp <= target.true_peak_dbtp + 0.6


def test_match_reference_records_params_and_serializes(dynamic_wav: Path, tmp_path: Path):
    """Result must carry the final parameters and be JSON-serializable."""
    target = ReferenceProfile(integrated_lufs=-16.0, lra=2.0, true_peak_dbtp=-2.0)
    out = tmp_path / "matched.wav"
    result = match_reference(dynamic_wav, out, target, max_iterations=2)

    params = result.params
    assert "compressor_threshold_db" in params
    assert "compressor_ratio" in params
    assert "limiter_ceiling_db" in params
    # ceilling must sit below the requested true peak to absorb inter-sample peaks
    assert params["limiter_ceiling_db"] <= target.true_peak_dbtp

    payload = json.loads(json.dumps(result.to_dict(), default=str))
    assert payload["output_path"] == str(out)
    assert payload["reference"]["integrated_lufs"] == -16.0
    assert isinstance(payload["log"], list) and payload["log"]


def test_match_reference_threshold_is_the_lra_lever(dynamic_wav: Path, tmp_path: Path):
    """A much narrower target must drive the compressor threshold down.

    Regression guard: raising the compressor *ratio* at a fixed threshold
    stalls around LRA 2 LU, because LRA is set by quiet sections sitting below
    the threshold. The threshold is the lever that actually narrows the range.
    """
    source = measure_profile(dynamic_wav)
    narrow = ReferenceProfile(
        integrated_lufs=-14.0,
        lra=max(1.0, source.lra * 0.2),
        true_peak_dbtp=-3.0,
    )
    out = tmp_path / "narrow.wav"
    result = match_reference(dynamic_wav, out, narrow, max_iterations=3)
    assert result.params["compressor_threshold_db"] < reference_mod._THRESHOLD_SEED_DB


def test_match_reference_raises_threshold_when_target_is_wider(dynamic_wav: Path, tmp_path: Path):
    """A wider target than the source must not over-compress."""
    source = measure_profile(dynamic_wav)
    wide = ReferenceProfile(
        integrated_lufs=-20.0,
        lra=source.lra + 6.0,
        true_peak_dbtp=-6.0,
    )
    out = tmp_path / "wide.wav"
    result = match_reference(dynamic_wav, out, wide, max_iterations=2)
    # Never driven below the seed by an over-wide target.
    assert result.params["compressor_threshold_db"] >= reference_mod._THRESHOLD_MIN_DB
    assert result.achieved is not None
    assert result.achieved.lra > 0.0


def test_makeup_compensates_threshold_movement():
    """Makeup gain must rise as the threshold drops, keeping level stable."""
    shallow = reference_mod._makeup_for_threshold(-20.0)
    deep = reference_mod._makeup_for_threshold(-50.0)
    assert deep > shallow
    assert reference_mod._makeup_for_threshold(-24.0) == pytest.approx(10.0)
    assert reference_mod._makeup_for_threshold(-50.0) == pytest.approx(36.0)
    # Clamped at the top end rather than growing without bound.
    assert reference_mod._makeup_for_threshold(-200.0) == reference_mod._MAKEUP_MAX_DB
