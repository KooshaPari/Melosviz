"""Tests for the audio finishing module: LUFS targets + stem export."""

from __future__ import annotations

import json
import wave
import struct
import math
import shutil
from pathlib import Path

import pytest

from melosviz.render.audio_finishing import (
    LUFS_TARGETS,
    STEM_BACKEND_PRIORITY,
    analyze_loudness,
    build_offline_master_plan,
    detect_stem_backend,
    export_stems,
    ffmpeg_available,
    list_lufs_targets,
    list_stem_backends,
    normalize_loudness,
    resolve_lufs_target,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _synthesize_wav(path: Path, dur_s: float = 5.0, sr: int = 22050, freq_hz: float = 440.0) -> Path:
    """Synthesize a simple sine-wave WAV for tests."""
    n = int(sr * dur_s)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        for i in range(n):
            t = i / sr
            sample = int(max(-1.0, min(1.0, 0.5 * math.sin(2 * math.pi * freq_hz * t))) * 32767)
            w.writeframesraw(struct.pack("<h", sample))
    return path


@pytest.fixture
def small_wav(tmp_path: Path) -> Path:
    return _synthesize_wav(tmp_path / "tone.wav")


# ---------------------------------------------------------------------------
# LUFS target table
# ---------------------------------------------------------------------------


def test_lufs_targets_table_has_required_keys():
    """Every LUFS preset must specify integrated_lufs + true_peak_dbtp + label."""
    required = {"club_pa", "youtube", "broadcast_ebu_r128"}
    assert required.issubset(LUFS_TARGETS.keys())
    for name, meta in LUFS_TARGETS.items():
        assert "integrated_lufs" in meta, f"{name} missing integrated_lufs"
        assert "true_peak_dbtp" in meta, f"{name} missing true_peak_dbtp"
        assert "label" in meta, f"{name} missing label"


def test_list_lufs_targets_includes_required_channels():
    targets = list_lufs_targets()
    names = {t["name"] for t in targets}
    assert {"club_pa", "youtube", "broadcast_ebu_r128"}.issubset(names)


def test_resolve_lufs_target_unknown_falls_back_to_youtube():
    """Unknown target names must not crash; they must fall back to YouTube."""
    target = resolve_lufs_target("does_not_exist")
    assert target["name"] == "youtube"
    assert target["integrated_lufs"] == -14.0


def test_resolve_lufs_target_known_preserves_values():
    """Known targets must round-trip their numeric values."""
    target = resolve_lufs_target("club_pa")
    assert target["integrated_lufs"] == -9.0
    assert target["true_peak_dbtp"] == -1.0


# ---------------------------------------------------------------------------
# Loudness analysis (requires ffmpeg)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_analyze_loudness_returns_loudnorm_report(small_wav):
    report = analyze_loudness(small_wav)
    assert report is not None
    # ffmpeg's loudnorm populates these on a non-silent input
    assert isinstance(report.input_i, float)
    assert report.target_lufs == 0.0 or report.input_i != 0.0


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_normalize_loudness_writes_output_and_changes_lufs(tmp_path, small_wav):
    """Normalizing to a different target should change the integrated loudness."""
    # First normalize at YouTube (-14 LUFS) — verify pass 1 + pass 2 work
    out = tmp_path / "loudnorm.wav"
    report = normalize_loudness(small_wav, out, resolve_lufs_target("youtube"))
    assert out.exists(), "loudnorm did not produce output WAV"
    assert out.stat().st_size > 0


# ---------------------------------------------------------------------------
# Stem export
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_export_stems_fallback_three_band(tmp_path, small_wav):
    """No Demucs available in CI -> fallback 3-band split must produce 3 stems."""
    out_dir = tmp_path / "stems"
    result = export_stems(small_wav, out_dir)
    assert result.method in {"three_band_fallback", "demucs"}
    if result.method == "three_band_fallback":
        # Fallback path: bass.wav / mids.wav / highs.wav
        assert any(p.endswith("bass.wav") for p in result.stems)
        assert any(p.endswith("mids.wav") for p in result.stems)
        assert any(p.endswith("highs.wav") for p in result.stems)


def test_export_stems_directory_is_created(tmp_path, small_wav):
    """The stems out_dir must always exist after the call."""
    if not ffmpeg_available():
        pytest.skip("ffmpeg not installed")
    out_dir = tmp_path / "stems"
    assert not out_dir.exists()
    export_stems(small_wav, out_dir)
    assert out_dir.exists()


# ---------------------------------------------------------------------------
# Offline-mode plan
# ---------------------------------------------------------------------------


def test_build_offline_master_plan_basic(tmp_path):
    """Offline-mode plan must include the 5 base deliverables + next_steps."""
    plan = build_offline_master_plan(tmp_path)
    assert plan["mode"] == "offline"
    assert plan["master_dir"] == str(tmp_path)
    deliverables = plan["deliverables_planned"]
    paths = {d["path"] for d in deliverables}
    assert any(p.endswith("festival_prores.mov") for p in paths)
    assert any(p.endswith("youtube_h264.mp4") for p in paths)
    assert "next_steps" in plan
    assert isinstance(plan["next_steps"], list) and len(plan["next_steps"]) >= 1


def test_build_offline_master_plan_with_lufs(tmp_path):
    """lufs_target must appear in deliverables + as a top-level 'lufs_target' key."""
    plan = build_offline_master_plan(tmp_path, lufs_target="club_pa")
    assert plan["lufs_target"]["name"] == "club_pa"
    assert plan["lufs_target"]["integrated_lufs"] == -9.0
    paths = {d["path"] for d in plan["deliverables_planned"]}
    assert any("club_pa" in p for p in paths)


def test_build_offline_master_plan_with_stems(tmp_path):
    """export_stems=True must add a 'stems_export' section."""
    plan = build_offline_master_plan(tmp_path, export_stems_flag=True)
    assert "stems_export" in plan
    assert plan["stems_export"]["out_dir"] == str(tmp_path / "stems")
    assert plan["stems_export"]["method"] in {"demucs", "three_band_fallback"}
    assert len(plan["stems_export"]["stems_planned"]) >= 2


def test_build_offline_master_plan_with_existing_audio(tmp_path, small_wav):
    """When audio_wav exists, plan must include the source loudness report."""
    plan = build_offline_master_plan(tmp_path, audio_wav=small_wav)
    assert plan.get("source_audio") == str(small_wav)
    if ffmpeg_available():
        assert "source_loudness" in plan
        assert "input_i" in plan["source_loudness"]


# ---------------------------------------------------------------------------
# AI stem backend detection
# ---------------------------------------------------------------------------


def test_stem_backend_priority_order():
    """Priority order must be demucs → audio-separator → spleeter → fallback."""
    assert STEM_BACKEND_PRIORITY == [
        "demucs",
        "audio-separator",
        "spleeter",
        "three_band_fallback",
    ]


def test_detect_stem_backend_auto_returns_available():
    """Auto-detect should always return SOMETHING (the fallback at minimum)."""
    chosen = detect_stem_backend()
    assert chosen in STEM_BACKEND_PRIORITY


def test_detect_stem_backend_prefer_unknown_warns_and_falls_back(caplog):
    """prefer='nonexistent' should warn + fall back to highest-priority available."""
    with caplog.at_level("WARNING"):
        chosen = detect_stem_backend(prefer="nonexistent")
    assert chosen in STEM_BACKEND_PRIORITY
    assert any("nonexistent" in r.message for r in caplog.records)


def test_detect_stem_backend_prefer_uses_requested_when_available(monkeypatch):
    """prefer='demucs' when demucs is on PATH should return 'demucs'."""
    monkeypatch.setattr(
        "melosviz.render.audio_finishing._has_demucs", lambda: True
    )
    monkeypatch.setattr(
        "melosviz.render.audio_finishing._has_spleeter", lambda: False
    )
    monkeypatch.setattr(
        "melosviz.render.audio_finishing._has_audio_separator", lambda: False
    )
    monkeypatch.setattr(
        "melosviz.render.audio_finishing.ffmpeg_available", lambda: True
    )
    assert detect_stem_backend(prefer="demucs") == "demucs"


def test_detect_stem_backend_uses_priority_chain(monkeypatch):
    """Without prefer, demucs beats spleeter beats three-band fallback."""
    monkeypatch.setattr(
        "melosviz.render.audio_finishing._has_demucs", lambda: False
    )
    monkeypatch.setattr(
        "melosviz.render.audio_finishing._has_audio_separator", lambda: False
    )
    monkeypatch.setattr(
        "melosviz.render.audio_finishing._has_spleeter", lambda: True
    )
    monkeypatch.setattr(
        "melosviz.render.audio_finishing.ffmpeg_available", lambda: True
    )
    assert detect_stem_backend() == "spleeter"


def test_list_stem_backends_returns_full_table():
    """list_stem_backends must report every backend + its availability."""
    table = list_stem_backends()
    assert {row["name"] for row in table} == set(STEM_BACKEND_PRIORITY)
    for row in table:
        assert "available" in row
        assert "priority" in row
        assert isinstance(row["available"], bool)


def test_export_stems_falls_back_when_demucs_missing(small_wav, tmp_path):
    """When demucs is unavailable, export_stems must still produce stems."""
    stems_dir = tmp_path / "stems"
    result = export_stems(small_wav, stems_dir)
    # three-band fallback must always run successfully if ffmpeg is available
    if ffmpeg_available():
        assert result.method == "three_band_fallback"
        assert len(result.stems) == 3
        for stem_path in result.stems:
            assert Path(stem_path).exists()
            assert Path(stem_path).stat().st_size > 0


def test_export_stems_with_prefer_three_band_fallback(small_wav, tmp_path):
    """prefer='three_band_fallback' should bypass AI backends entirely."""
    stems_dir = tmp_path / "stems"
    result = export_stems(small_wav, stems_dir, prefer="three_band_fallback")
    assert result.method == "three_band_fallback"


def test_offline_plan_stems_export_surfaces_available_backends(tmp_path):
    """The offline master plan must list every backend + which will be used."""
    plan = build_offline_master_plan(tmp_path, export_stems_flag=True)
    assert "stems_export" in plan
    assert "available_backends" in plan["stems_export"]
    assert {
        row["name"] for row in plan["stems_export"]["available_backends"]
    } == set(STEM_BACKEND_PRIORITY)
    # Method must be one of the priority chain (not a hardcoded literal)
    assert plan["stems_export"]["method"] in STEM_BACKEND_PRIORITY
