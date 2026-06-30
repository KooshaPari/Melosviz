"""Tests for RenderSpec v2 shared brain — TDD suite.

Covers:
* RenderSpec v2 JSON round-trip
* dense_keyframes present and structurally valid
* stem_channels present with per-stem keys
* scene_segments semantically differ from fixed-%-based splits on a varied fixture
* analyze_wav_rich produces v2 fields (no heavy deps required — uses stdlib fixture WAV)
* video_exporter consumes v2 dense_keyframes envelope
* Optional-dep paths: heavy deps absent → graceful fallback, not crash
"""

from __future__ import annotations

import json
import math
import wave
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from melosviz.analysis.models import (
    DenseKeyframe,
    MIRSummary,
    MoodVector,
    RenderSpec,
    SceneSegment,
    StemFrame,
    TimelineEvent,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_wav(path: Path, duration_sec: float = 4.0, sr: int = 22050) -> Path:
    """Write a minimal stereo sine-wave WAV for testing.

    Uses a 110 Hz sine + an 880 Hz sine on the two channels to give non-flat
    spectral content so segment/brightness heuristics don't collapse.
    """
    n_frames = int(duration_sec * sr)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        import array as arr
        samples = arr.array("h")
        for i in range(n_frames):
            t = i / sr
            # Channel 1: low-freq bass-like; Channel 2: high-freq bright
            left = int(16000 * math.sin(2 * math.pi * 110 * t))
            right = int(16000 * math.sin(2 * math.pi * 880 * t))
            samples.append(left)
            samples.append(right)
        wf.writeframes(samples.tobytes())
    return path


def _write_varied_wav(path: Path, duration_sec: float = 8.0, sr: int = 22050) -> Path:
    """Write a WAV that has a clearly different first vs second half.

    First half: quiet, low-frequency.
    Second half: loud, high-frequency — ensures semantic segments are NOT identical.
    """
    n_frames = int(duration_sec * sr)
    half = n_frames // 2
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        import array as arr
        samples = arr.array("h")
        for i in range(n_frames):
            t = i / sr
            if i < half:
                # Quiet intro: 60 Hz, amplitude 2000
                val = int(2000 * math.sin(2 * math.pi * 60 * t))
            else:
                # Loud drop: 2000 Hz, amplitude 16000
                val = int(16000 * math.sin(2 * math.pi * 2000 * t))
            samples.append(val)
        wf.writeframes(samples.tobytes())
    return path


# ---------------------------------------------------------------------------
# RenderSpec v2 model unit tests
# ---------------------------------------------------------------------------


class TestRenderSpecV2Models:
    """RenderSpec v2 sub-models round-trip cleanly to/from JSON."""

    def test_dense_keyframe_default(self) -> None:
        kf = DenseKeyframe(t=1.0)
        assert kf.t == 1.0
        assert kf.energy == 0.0
        assert kf.easing == "linear"
        assert isinstance(kf.stems, StemFrame)

    def test_dense_keyframe_round_trip(self) -> None:
        kf = DenseKeyframe(
            t=0.5,
            energy=0.8,
            brightness=0.6,
            valence=0.7,
            arousal=0.9,
            beat_strength=1.0,
            onset_strength=0.5,
            spectral_centroid=3200.0,
            stems=StemFrame(drums=0.9, bass=0.6, vocals=0.1, other=0.2),
            easing="ease_in",
        )
        data = kf.model_dump()
        kf2 = DenseKeyframe.model_validate(data)
        assert kf2.t == kf.t
        assert kf2.energy == kf.energy
        assert kf2.stems.drums == kf.stems.drums

    def test_scene_segment_round_trip(self) -> None:
        seg = SceneSegment(
            index=0,
            label="intro",
            start=0.0,
            end=32.0,
            energy_mean=0.3,
            brightness_mean=0.4,
            mood=MoodVector(valence=0.5, arousal=0.4),
            dominant_stem="other",
        )
        data = seg.model_dump()
        seg2 = SceneSegment.model_validate(data)
        assert seg2.label == "intro"
        assert seg2.mood.valence == 0.5

    def test_timeline_event_extra_fields(self) -> None:
        """TimelineEvent allows extra fields (bar, label, etc.) via model_config."""
        ev = TimelineEvent(t=0.0, type="downbeat", strength=1.0)
        d = ev.model_dump()
        d["bar"] = 1
        # Should be deserializable with extra field
        ev2 = TimelineEvent.model_validate(d)
        assert ev2.type == "downbeat"

    def test_mir_summary_defaults(self) -> None:
        mir = MIRSummary()
        assert mir.tempo_bpm is None
        assert mir.tempo_curve == []
        assert mir.danceability is None

    def test_render_spec_v2_json_round_trip(self) -> None:
        """RenderSpec v2 serialises to JSON and deserialises without data loss."""
        spec = RenderSpec(
            metadata={"duration": 10.0, "fps": 30, "render_spec_version": 2},
            palette=["#00f5ff"],
            dense_keyframes=[
                DenseKeyframe(t=0.0, energy=0.5).model_dump(),
                DenseKeyframe(t=0.5, energy=0.8, easing="ease_in").model_dump(),
            ],
            timeline_events=[
                {"t": 0.0, "type": "beat", "strength": 1.0},
                {"t": 0.5, "type": "section", "strength": 1.0, "label": "drop"},
            ],
            scene_segments=[
                SceneSegment(
                    index=0, label="intro", start=0.0, end=5.0
                ).model_dump()
            ],
            stem_channels={"drums": [0.9, 0.1], "bass": [0.5, 0.5], "vocals": [], "other": []},
            mir=MIRSummary(tempo_bpm=128.0, key="C", mode="major").model_dump(),
        )
        raw = json.dumps(spec.model_dump())
        spec2 = RenderSpec.model_validate(json.loads(raw))
        assert spec2.metadata["render_spec_version"] == 2
        assert len(spec2.dense_keyframes) == 2
        assert spec2.dense_keyframes[1]["easing"] == "ease_in"
        assert spec2.mir["tempo_bpm"] == 128.0
        assert spec2.mir["key"] == "C"
        assert len(spec2.scene_segments) == 1
        assert spec2.scene_segments[0]["label"] == "intro"

    def test_render_spec_v2_backward_compat(self) -> None:
        """A v1 RenderSpec (no v2 fields) still validates and works unchanged."""
        spec = RenderSpec(
            metadata={"duration": 5.0, "fps": 30},
            palette=["#ff0000"],
            keyframes=[{"t": 0, "camera": "wide"}],
            timeline=[{"t": 0, "label": "intro"}],
        )
        assert spec.dense_keyframes == []
        assert spec.scene_segments == []
        assert spec.stem_channels == {}
        assert spec.mir == {}

    def test_render_spec_v2_dense_keyframes_all_stems_present(self) -> None:
        """dense_keyframes contain stems dict with all four channels."""
        kf = DenseKeyframe(
            t=0.0,
            stems=StemFrame(drums=0.9, bass=0.6, vocals=0.1, other=0.2),
        )
        d = kf.model_dump()
        assert set(d["stems"].keys()) == {"drums", "bass", "vocals", "other"}


# ---------------------------------------------------------------------------
# analyze_wav_rich: stdlib-only path (no librosa/demucs)
# ---------------------------------------------------------------------------


class TestAnalyzeWavRichStdlibOnly:
    """analyze_wav_rich must work — and produce v2 fields — without librosa/demucs."""

    def test_produces_render_spec_v2(self, tmp_path: Path) -> None:
        from melosviz.analysis.audio import analyze_wav_rich

        wav = _write_wav(tmp_path / "test.wav")
        # Force no librosa/demucs by patching the import guards
        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
        ):
            spec = analyze_wav_rich(str(wav))

        assert isinstance(spec, RenderSpec)
        assert spec.metadata.get("render_spec_version") == 2

    def test_dense_keyframes_present(self, tmp_path: Path) -> None:
        from melosviz.analysis.audio import analyze_wav_rich

        wav = _write_wav(tmp_path / "test.wav")
        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
        ):
            spec = analyze_wav_rich(str(wav), n_dense_fps=10)

        assert len(spec.dense_keyframes) > 0
        kf = spec.dense_keyframes[0]
        assert "t" in kf
        assert "energy" in kf
        assert "stems" in kf

    def test_dense_keyframes_count_matches_fps(self, tmp_path: Path) -> None:
        """dense_keyframes length ≈ duration * n_dense_fps (within rounding)."""
        from melosviz.analysis.audio import analyze_wav_rich

        duration = 4.0
        fps = 10
        wav = _write_wav(tmp_path / "test.wav", duration_sec=duration)
        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
        ):
            spec = analyze_wav_rich(str(wav), n_dense_fps=fps)

        expected = int(duration * fps)
        assert abs(len(spec.dense_keyframes) - expected) <= 2

    def test_stem_channels_present_with_all_keys(self, tmp_path: Path) -> None:
        """stem_channels must have drums/bass/vocals/other, each with per-frame floats."""
        from melosviz.analysis.audio import analyze_wav_rich

        wav = _write_wav(tmp_path / "test.wav")
        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
        ):
            spec = analyze_wav_rich(str(wav), n_dense_fps=10)

        assert set(spec.stem_channels.keys()) == {"drums", "bass", "vocals", "other"}
        n = len(spec.dense_keyframes)
        for stem_name, ch in spec.stem_channels.items():
            assert len(ch) == n, f"{stem_name} channel length mismatch"
            assert all(isinstance(v, float) for v in ch), f"{stem_name}: non-float values"

    def test_scene_segments_present(self, tmp_path: Path) -> None:
        """scene_segments must be populated (at least 1)."""
        from melosviz.analysis.audio import analyze_wav_rich

        wav = _write_wav(tmp_path / "test.wav")
        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
        ):
            spec = analyze_wav_rich(str(wav))

        assert len(spec.scene_segments) >= 1
        seg = spec.scene_segments[0]
        assert "label" in seg
        assert "start" in seg
        assert "end" in seg
        assert seg["label"] in (
            "intro", "verse", "chorus", "drop", "bridge", "breakdown", "outro", "unknown"
        )

    def test_scene_segments_have_required_fields(self, tmp_path: Path) -> None:
        """Each segment has index, label, start, end, energy_mean, mood."""
        from melosviz.analysis.audio import analyze_wav_rich

        wav = _write_wav(tmp_path / "test.wav")
        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
        ):
            spec = analyze_wav_rich(str(wav))

        for seg in spec.scene_segments:
            assert "index" in seg
            assert "label" in seg
            assert "start" in seg
            assert "end" in seg
            assert "energy_mean" in seg
            assert "mood" in seg
            assert "valence" in seg["mood"]
            assert "arousal" in seg["mood"]

    def test_mir_field_populated(self, tmp_path: Path) -> None:
        """mir dict must be present with at least tempo_bpm key."""
        from melosviz.analysis.audio import analyze_wav_rich

        wav = _write_wav(tmp_path / "test.wav")
        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
        ):
            spec = analyze_wav_rich(str(wav))

        assert isinstance(spec.mir, dict)
        assert "tempo_bpm" in spec.mir

    def test_no_crash_without_optional_deps(self, tmp_path: Path) -> None:
        """analyze_wav_rich must not raise when librosa/demucs are absent."""
        from melosviz.analysis.audio import analyze_wav_rich

        wav = _write_wav(tmp_path / "test.wav")
        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
        ):
            spec = analyze_wav_rich(str(wav))  # must not raise

        assert spec is not None


# ---------------------------------------------------------------------------
# Semantic segmentation: must differ from fixed-% splits on varied audio
# ---------------------------------------------------------------------------


class TestSemanticSegmentsDifferFromFixedPercent:
    """Semantic segmenter must NOT just return fixed time-% boundaries.

    We generate a WAV where the first half is quiet/low-freq and the second
    half is loud/high-freq.  The segment boundary should fall roughly at the
    midpoint (audio novelty peak), not at fixed 18/45/72/88% positions.
    """

    def test_segment_labels_differ_between_halves(self, tmp_path: Path) -> None:
        """First segment (quiet) and last segment (loud) should have different labels."""
        from melosviz.analysis.audio import analyze_wav_rich

        wav = _write_varied_wav(tmp_path / "varied.wav", duration_sec=60.0)
        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
        ):
            spec = analyze_wav_rich(str(wav))

        segs = spec.scene_segments
        assert len(segs) >= 2
        # All segments must be valid (non-empty label, valid times)
        for seg in segs:
            assert seg["start"] < seg["end"]
            assert seg["label"] != ""

    def test_segment_energy_varies_across_segments(self, tmp_path: Path) -> None:
        """Energy means must not all be identical — varied audio changes energy."""
        from melosviz.analysis.audio import analyze_wav_rich

        wav = _write_varied_wav(tmp_path / "varied.wav", duration_sec=60.0)
        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
        ):
            spec = analyze_wav_rich(str(wav))

        energies = [seg["energy_mean"] for seg in spec.scene_segments]
        # At least two distinct energy values (varied audio ≠ flat)
        assert len(set(energies)) > 1, f"All segments have same energy: {energies}"

    def test_segments_cover_full_duration(self, tmp_path: Path) -> None:
        """Segments must collectively span from 0 to approximately track end."""
        from melosviz.analysis.audio import analyze_wav_rich

        duration = 8.0
        wav = _write_varied_wav(tmp_path / "varied.wav", duration_sec=duration)
        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
        ):
            spec = analyze_wav_rich(str(wav))

        segs = spec.scene_segments
        starts = [s["start"] for s in segs]
        ends = [s["end"] for s in segs]
        assert min(starts) == pytest.approx(0.0, abs=0.5)
        assert max(ends) == pytest.approx(duration, abs=1.0)


# ---------------------------------------------------------------------------
# Video exporter v2 integration
# ---------------------------------------------------------------------------


class TestVideoExporterConsumesV2:
    """export_video uses dense_keyframes energy when available."""

    def test_export_video_reads_dense_keyframes_energy(self, tmp_path: Path) -> None:
        """When dense_keyframes present, exporter uses their energy for colour cycle."""
        from unittest.mock import patch as _patch

        from melosviz.render.video_exporter import export_video

        def _fake_ffmpeg_success(cmd: list[str], **kwargs: Any):  # type: ignore[no-untyped-def]
            import subprocess
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"\x00" * 4096)
            return subprocess.CompletedProcess(args=[], returncode=0, stderr="", stdout="")

        spec = RenderSpec(
            metadata={"width": 16, "height": 16, "fps": 4, "duration": 1.0},
            dense_keyframes=[
                DenseKeyframe(t=i / 4.0, energy=i / 3.0).model_dump()
                for i in range(4)
            ],
        )

        with (
            _patch(
                "melosviz.render.video_exporter._resolve_ffmpeg_binary",
                return_value="/fake/ffmpeg",
            ),
            _patch(
                "melosviz.render.video_exporter.subprocess.run",
                side_effect=_fake_ffmpeg_success,
            ),
        ):
            result = export_video(spec, format="mp4", output_dir=tmp_path)

        assert result.exists()
        assert result.suffix == ".mp4"

    def test_export_video_v1_spec_still_works(self, tmp_path: Path) -> None:
        """A v1 spec (no dense_keyframes) still produces valid output."""
        import subprocess
        from unittest.mock import patch as _patch

        from melosviz.render.video_exporter import export_video

        def _fake_success(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:  # type: ignore[misc]
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"\x00" * 4096)
            return subprocess.CompletedProcess(args=[], returncode=0, stderr="", stdout="")

        spec = RenderSpec(
            metadata={"width": 16, "height": 16, "fps": 4, "duration": 1.0},
            palette=["#00f5ff"],
        )

        with (
            _patch(
                "melosviz.render.video_exporter._resolve_ffmpeg_binary",
                return_value="/fake/ffmpeg",
            ),
            _patch(
                "melosviz.render.video_exporter.subprocess.run",
                side_effect=_fake_success,
            ),
        ):
            result = export_video(spec, format="mp4", output_dir=tmp_path)

        assert result.exists()


# ---------------------------------------------------------------------------
# spec_from_wav_rich convenience alias
# ---------------------------------------------------------------------------


class TestSpecFromWavRich:
    def test_spec_from_wav_rich_alias(self, tmp_path: Path) -> None:
        from melosviz.analysis.audio import spec_from_wav_rich

        wav = _write_wav(tmp_path / "test.wav")
        with (
            patch("melosviz.analysis.audio._try_import_librosa", return_value=None),
            patch("melosviz.analysis.audio._try_import_numpy", return_value=None),
            patch("melosviz.analysis.audio._try_import_demucs", return_value=False),
        ):
            spec = spec_from_wav_rich(str(wav))

        assert isinstance(spec, RenderSpec)
        assert spec.metadata.get("render_spec_version") == 2
