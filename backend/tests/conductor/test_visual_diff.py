"""Tests for the deterministic visual-diff builder."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from melosviz.conductor.visual_diff import (
    build_visual_diff,
    compute_visual_diff,
    extract_preview_frame,
)


def test_visual_diff_hashes_artifact_and_prompt(tmp_path: Path) -> None:
    artifact = tmp_path / "scene.mp4"
    artifact.write_bytes(b"rendered-bytes")
    payload = build_visual_diff(
        artifact_path=artifact,
        scene_dir=tmp_path,
        job_dir=tmp_path,
        scene_name="intro",
        prompt="neon & rain",
        start_seconds=1.0,
        end_seconds=5.0,
        beat_seconds=[1.0, 3.0, 5.0],
        palette=["#112233"],
        frame_extractor=lambda source, target: False,
    )
    assert payload["rendered"]["sha256"] == hashlib.sha256(
        b"rendered-bytes"
    ).hexdigest()
    assert payload["prompt"]["sha256"] == hashlib.sha256(
        b"neon & rain"
    ).hexdigest()
    # No preview was extracted -> preview_* keys are None.
    assert payload["rendered"]["preview_path"] is None
    assert payload["rendered"]["preview_sha256"] is None


def test_visual_diff_fallback_svg_is_deterministic_and_escaped(tmp_path: Path) -> None:
    kwargs = dict(
        artifact_path=tmp_path / "missing.mp4",
        scene_dir=tmp_path,
        job_dir=tmp_path,
        scene_name='<intro & "drop">',
        prompt="neon < rain & thunder",
        start_seconds=0.0,
        end_seconds=8.0,
        beat_seconds=[0.0, 4.0, 8.0],
        palette=["#ff00aa"],
        frame_extractor=lambda source, target: False,
    )
    first = build_visual_diff(**kwargs)
    first_bytes = (tmp_path / "visual-diff.svg").read_bytes()
    second = build_visual_diff(**kwargs)
    assert (tmp_path / "visual-diff.svg").read_bytes() == first_bytes
    assert first == second
    svg = first_bytes.decode()
    assert "&lt;intro &amp; &quot;drop&quot;&gt;" in svg
    assert "neon &lt; rain &amp; thunder" in svg
    assert "<script" not in svg
    assert 'href="http://' not in svg and 'href="https://' not in svg


def test_visual_diff_records_extracted_preview(tmp_path: Path) -> None:
    artifact = tmp_path / "scene.mov"
    artifact.write_bytes(b"movie")

    def extractor(source: Path, target: Path) -> bool:
        assert source == artifact
        target.write_bytes(b"png")
        return True

    payload = build_visual_diff(
        artifact_path=artifact,
        scene_dir=tmp_path,
        job_dir=tmp_path,
        scene_name="chorus",
        prompt="wide hero",
        start_seconds=2.0,
        end_seconds=6.0,
        beat_seconds=[2.0, 4.0],
        palette=[],
        frame_extractor=extractor,
    )
    assert payload["rendered"]["preview_path"] == "visual-diff-frame.png"
    assert payload["rendered"]["preview_sha256"] == hashlib.sha256(
        b"png"
    ).hexdigest()
    # SVG references the preview file when extraction succeeded.
    assert 'href="visual-diff-frame.png"' in (tmp_path / "visual-diff.svg").read_text()


def test_compute_visual_diff_writes_manifest_and_uses_defaults(tmp_path: Path) -> None:
    artifact = tmp_path / "scene_0001.png"
    artifact.write_bytes(b"rendered")
    payload = compute_visual_diff(artifact, "a bright city", start_seconds=2.0)
    assert payload["prompt"]["text"] == "a bright city"
    assert payload["rendered"]["sha256"] == hashlib.sha256(b"rendered").hexdigest()
    # Default end_seconds is start + 8
    assert payload["timeline_thumbnail"]["start_seconds"] == 2.0
    assert payload["timeline_thumbnail"]["end_seconds"] == 10.0
    assert (artifact.parent / "visual-diff.svg").exists()


def test_compute_visual_diff_zero_length_clip_preserves_zero_end(
    tmp_path: Path,
) -> None:
    """Regression: ``end_seconds=0.0`` was treated as falsy and widened to
    ``start + 8``. A truly zero-length clip (e.g. a 1-frame scene at the
    song's last beat) must keep ``end_seconds == 0.0``."""

    artifact = tmp_path / "scene.png"
    artifact.write_bytes(b"x")
    payload = compute_visual_diff(
        artifact, "test", start_seconds=0.0, end_seconds=0.0
    )
    assert payload["timeline_thumbnail"]["start_seconds"] == 0.0
    assert payload["timeline_thumbnail"]["end_seconds"] == 0.0


def test_extract_preview_frame_handles_subprocess_timeout(tmp_path: Path) -> None:
    """Regression: a hanging ffmpeg used to raise subprocess.TimeoutExpired
    and crash the orchestrator. Now we degrade silently to ``False``."""

    source = tmp_path / "clip.mp4"
    source.write_bytes(b"not really video")
    target = tmp_path / "frame.png"

    def hang(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=0.01)

    # Inject the throwing extractor into build_visual_diff so we exercise
    # the same call site the orchestrator uses.
    build_visual_diff(
        artifact_path=source,
        scene_dir=tmp_path,
        job_dir=tmp_path,
        scene_name="scene",
        prompt="test",
        start_seconds=0.0,
        end_seconds=8.0,
        beat_seconds=[],
        palette=[],
        frame_extractor=hang,
    )
    assert not target.exists()


def test_extract_preview_frame_handles_oserror(tmp_path: Path) -> None:
    """Regression: OSError (permission denied, binary vanished, …) used to
    propagate out of the orchestrator. Now we degrade silently to False."""

    source = tmp_path / "clip.mp4"
    source.write_bytes(b"not really video")
    target = tmp_path / "frame.png"

    def os_explode(*_args, **_kwargs):
        raise OSError("fake permission denied")

    build_visual_diff(
        artifact_path=source,
        scene_dir=tmp_path,
        job_dir=tmp_path,
        scene_name="scene",
        prompt="test",
        start_seconds=0.0,
        end_seconds=8.0,
        beat_seconds=[],
        palette=[],
        frame_extractor=os_explode,
    )
    assert not target.exists()
