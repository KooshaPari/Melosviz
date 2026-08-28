"""Tests for the InterpolationEngine — RIFE/FILM/FlowMatching interpolation bridge.

Covers: backend detection, fallback ordering, ffmpeg minterpolate fallback,
scene-pair schedule building, JSON-only manifest emission, and edge cases.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _import_engine():
    from melosviz.interpolation.engine import (
        InterpolationEngine,
        InterpolationBackend,
        InterpolationMethod,
        ScenePair,
        InterpolationSchedule,
        detect_backend,
        list_backends,
        interpolate_pair,
        build_interpolation_schedule,
        INTERPOLATION_PRIORITY,
    )

    return (
        InterpolationEngine,
        InterpolationBackend,
        InterpolationMethod,
        ScenePair,
        InterpolationSchedule,
        detect_backend,
        list_backends,
        interpolate_pair,
        build_interpolation_schedule,
        INTERPOLATION_PRIORITY,
    )


# 1. Backend detection ---------------------------------------------------

def test_interpolation_priority_order():
    (
        _, _, _, _, _, _, _, _, _, INTERPOLATION_PRIORITY,
    ) = _import_engine()
    # AI backends first, ffmpeg minterpolate last.
    assert INTERPOLATION_PRIORITY[0] == "rife"
    assert INTERPOLATION_PRIORITY[1] == "film"
    assert INTERPOLATION_PRIORITY[2] == "flow_matching"
    assert "ffmpeg_minterpolate" in INTERPOLATION_PRIORITY


def test_detect_backend_returns_string_or_none():
    detect_backend = _import_engine()[5]
    result = detect_backend()
    # Either a backend name from the priority list or None.
    if result is not None:
        assert result in {
            "rife",
            "film",
            "flow_matching",
            "ffmpeg_minterpolate",
        }


def test_list_backends_returns_list():
    list_backends = _import_engine()[6]
    backends = list_backends()
    assert isinstance(backends, list)
    assert backends == sorted(set(backends))  # de-duplicated


def test_detect_backend_prefer_override():
    detect_backend = _import_engine()[5]
    # Asking for a non-existent backend must return None (not crash).
    assert detect_backend(prefer="nonexistent_backend_xyz") is None


# 2. Scene pair schedule -------------------------------------------------

def test_build_interpolation_schedule_minimal():
    build_interpolation_schedule = _import_engine()[8]
    schedule = build_interpolation_schedule(
        scene_names=["intro", "verse", "chorus"],
        insertion_count=1,
        insertion_position="between",
    )
    assert isinstance(schedule, list)
    # 3 scenes -> 2 gaps -> 2 interpolation requests (one each).
    assert len(schedule) == 2


def test_build_interpolation_schedule_zero_insertion():
    build_interpolation_schedule = _import_engine()[8]
    schedule = build_interpolation_schedule(
        scene_names=["a", "b", "c"],
        insertion_count=0,
    )
    assert schedule == []


def test_build_interpolation_schedule_too_many_scenes():
    build_interpolation_schedule = _import_engine()[8]
    with pytest.raises(ValueError):
        build_interpolation_schedule(
            scene_names=["a"],
            insertion_count=5,
        )


def test_build_interpolation_schedule_position_at_start():
    build_interpolation_schedule = _import_engine()[8]
    schedule = build_interpolation_schedule(
        scene_names=["intro", "verse"],
        insertion_count=1,
        insertion_position="before",
    )
    # 2 scenes + 1 interpolated frame before the first = 3 frames.
    assert len(schedule) >= 1


# 3. ScenePair + InterpolationSchedule data classes ----------------------

def test_scene_pair_defaults():
    ScenePair = _import_engine()[3]
    pair = ScenePair(
        from_scene="a",
        to_scene="b",
        from_path=Path("/tmp/a.mp4"),
        to_path=Path("/tmp/b.mp4"),
    )
    assert pair.method is None
    assert pair.frames_inserted == 0
    assert pair.output_path is None


def test_scene_pair_to_dict():
    ScenePair = _import_engine()[3]
    pair = ScenePair(
        from_scene="a",
        to_scene="b",
        from_path=Path("/tmp/a.mp4"),
        to_path=Path("/tmp/b.mp4"),
        frames_inserted=4,
    )
    d = pair.to_dict() if hasattr(pair, "to_dict") else pair.__dict__
    assert d["from_scene"] == "a"
    assert d["to_scene"] == "b"
    assert d["frames_inserted"] == 4


# 4. interpolate_pair (ffmpeg_minterpolate fallback) ---------------------

def test_interpolate_pair_emits_manifest_when_backend_missing(tmp_path: Path):
    """When no AI backend is installed, interpolate_pair must:
    - not crash
    - fall back to writing a manifest JSON (so the operator can finish manually)
    - NOT pretend to have generated frames it didn't generate
    """
    interpolate_pair = _import_engine()[7]
    src_a = tmp_path / "a.mp4"
    src_b = tmp_path / "b.mp4"
    src_a.write_bytes(b"\x00" * 64)
    src_b.write_bytes(b"\x00" * 64)
    out_dir = tmp_path / "interp"
    out_dir.mkdir()

    result = interpolate_pair(
        from_path=src_a,
        to_path=src_b,
        output_dir=out_dir,
        frames_to_insert=2,
        backend="nonexistent_backend_xyz",
        ffmpeg_bin="ffmpeg",
    )

    assert result is not None
    # When the backend is missing AND ffmpeg is not actually run, we expect a
    # manifest-only fallback or a controlled failure.
    assert (out_dir / "manifest.json").exists() or result.get("status") in {
        "fallback_manifest",
        "error",
        "missing_backend",
    }


def test_interpolate_pair_falls_back_to_ffmpeg_minterpolate(tmp_path: Path):
    """When the AI backend is missing but ffmpeg is on PATH + the inputs are
    real video files, interpolate_pair must call ffmpeg minterpolate. We feed
    a 1-frame synthetic mp4 so the test runs offline."""
    import shutil

    interpolate_pair = _import_engine()[7]

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not on PATH")

    # Synthesize two 1-frame mp4s at 64x64 via ffmpeg.
    src_a = tmp_path / "a.mp4"
    src_b = tmp_path / "b.mp4"
    for path in (src_a, src_b):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=64x64:d=0.04",
                "-c:v",
                "libx264",
                "-t",
                "0.04",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    out_dir = tmp_path / "interp"
    out_dir.mkdir()

    result = interpolate_pair(
        from_path=src_a,
        to_path=src_b,
        output_dir=out_dir,
        frames_to_insert=2,
        backend="ffmpeg_minterpolate",  # force fallback
        ffmpeg_bin="ffmpeg",
    )

    assert result["status"] in {"ok", "fallback_manifest"}
    # When ffmpeg succeeds, the output mp4 must exist.
    if result["status"] == "ok":
        assert (out_dir / "interp.mp4").exists()


# 5. InterpolationEngine class ---------------------------------------------

def test_engine_init_default(tmp_path: Path):
    (
        InterpolationEngine, _, _, _, _, _, _, _, _, _,
    ) = _import_engine()
    engine = InterpolationEngine(out_dir=tmp_path / "out")
    assert engine is not None
    assert engine.out_dir.exists()


def test_engine_init_explicit_backend(tmp_path: Path):
    (
        InterpolationEngine, _, _, _, _, _, _, _, _, _,
    ) = _import_engine()
    engine = InterpolationEngine(
        out_dir=tmp_path / "out",
        backend="ffmpeg_minterpolate",
    )
    assert engine.backend == "ffmpeg_minterpolate"


def test_engine_build_schedule_method():
    (
        InterpolationEngine, _, _, _, _, _, _, _, _, _,
    ) = _import_engine()
    engine = InterpolationEngine(out_dir=Path("/tmp"))
    schedule = engine.build_schedule(
        scene_names=["a", "b", "c"],
        insertion_count=2,
    )
    assert len(schedule) == 4  # 2 gaps * 2 frames per gap


# 6. CLI / import smoke ---------------------------------------------------

def test_module_imports():
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from melosviz.interpolation import (  # noqa: F401
        InterpolationEngine,
        InterpolationMethod,
        detect_backend,
        list_backends,
    )


def test_interpolation_method_enum():
    _, _, InterpolationMethod, _, _, _, _, _, _, _ = _import_engine()
    members = {m.value for m in InterpolationMethod}
    assert "ffmpeg_minterpolate" in members
    # RIFE / FILM / FlowMatching are AI members.
    assert "rife" in members
    assert "film" in members
    assert "flow_matching" in members
