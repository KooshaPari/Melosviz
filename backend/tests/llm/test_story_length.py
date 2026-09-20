"""WBS-23: Story length enforcement tests.

Verifies that the Director handles edge cases around segment count,
duration extremes, and scene-type diversity regardless of input length.
"""

from __future__ import annotations

import pytest

from melosviz.llm.director import (
    DIRECTOR_SCENE_TYPES,
    Director,
    DirectorRequest,
)


def _make_segments(count: int, total_duration: float = 120.0) -> list[dict]:
    """Generate *count* synthetic segments spanning *total_duration* seconds."""
    step = total_duration / max(1, count)
    labels = ["intro", "verse", "chorus", "bridge", "outro", "verse", "chorus", "breakdown"]
    segs = []
    for i in range(count):
        start = i * step
        end = (i + 1) * step if i < count - 1 else total_duration
        segs.append(
            {
                "index": i,
                "label": labels[i % len(labels)],
                "start": start,
                "end": end,
                "energy_mean": 0.3 + 0.05 * (i % 10),
            }
        )
    return segs


class TestStoryLengthEnforcement:
    """Edge cases for segment count and duration."""

    def test_single_segment_produces_one_scene(self) -> None:
        """A 1-segment input yields exactly 1 scene."""
        director = Director(seed=42)
        req = DirectorRequest(
            concept="underwater cathedral",
            duration_s=30.0,
            bpm=90.0,
            key="D major",
            segments=_make_segments(1, total_duration=30.0),
        )
        board = director.storyboard(req)
        assert len(board.scenes) == 1
        assert board.scenes[0].start == 0.0
        assert board.scenes[0].end == pytest.approx(30.0)

    def test_many_segments_produce_one_scene_each(self) -> None:
        """A 40-segment input yields exactly 40 scenes (no silent truncation)."""
        director = Director(seed=7)
        req = DirectorRequest(
            concept="festival parade through neon streets",
            duration_s=300.0,
            bpm=128.0,
            key="A minor",
            segments=_make_segments(40, total_duration=300.0),
        )
        board = director.storyboard(req)
        assert len(board.scenes) == 40

    def test_no_adjacent_duplicate_scene_types(self) -> None:
        """Even with many segments, no two adjacent scenes share a scene_type."""
        director = Director(seed=99)
        req = DirectorRequest(
            concept="desert storm, dust and light",
            duration_s=240.0,
            bpm=110.0,
            key="G minor",
            segments=_make_segments(20, total_duration=240.0),
        )
        board = director.storyboard(req)
        for i in range(1, len(board.scenes)):
            prev = board.scenes[i - 1].scene_type
            curr = board.scenes[i].scene_type
            assert prev != curr, f"adjacent duplicate at scenes {i - 1}/{i}: {prev}"

    def test_all_scene_types_are_valid(self) -> None:
        """Every generated scene_type must be in the DIRECTOR_SCENE_TYPES set."""
        director = Director(seed=0)
        req = DirectorRequest(
            concept="city at night",
            duration_s=60.0,
            bpm=120.0,
            key="E minor",
            segments=_make_segments(8, total_duration=60.0),
        )
        board = director.storyboard(req)
        for scene in board.scenes:
            assert scene.scene_type in DIRECTOR_SCENE_TYPES, (
                f"invalid scene_type {scene.scene_type!r} at index {scene.index}"
            )

    def test_timing_covers_full_duration(self) -> None:
        """Scene timing must be contiguous and cover the full duration."""
        director = Director(seed=11)
        total = 90.0
        req = DirectorRequest(
            concept="slow motion rain",
            duration_s=total,
            bpm=72.0,
            key="C minor",
            segments=_make_segments(6, total_duration=total),
        )
        board = director.storyboard(req)
        assert board.scenes[0].start == 0.0
        assert board.scenes[-1].end == pytest.approx(total)
        for i in range(1, len(board.scenes)):
            assert board.scenes[i].start == pytest.approx(board.scenes[i - 1].end)

    def test_synthetic_segments_fallback(self) -> None:
        """When no segments are supplied, synthetic segments are generated."""
        director = Director(seed=55)
        req = DirectorRequest(
            concept="space walk",
            duration_s=120.0,
            bpm=100.0,
            key="B minor",
            # segments omitted → None → synthetic
        )
        board = director.storyboard(req)
        assert len(board.scenes) >= 2  # at least intro + verse + outro
        assert len(board.scenes) <= 10  # not unbounded

    def test_zero_duration_yields_no_scenes(self) -> None:
        """A zero-duration input with explicit empty segments yields no scenes."""
        director = Director(seed=1)
        req = DirectorRequest(
            concept="silence",
            duration_s=0.0,
            bpm=60.0,
            key="A minor",
            segments=[],
        )
        board = director.storyboard(req)
        assert len(board.scenes) == 0

    def test_very_short_segments_still_produce_scenes(self) -> None:
        """Sub-second segments should still produce valid scenes."""
        director = Director(seed=33)
        # 10 segments of 0.5s each = 5s total
        segs = _make_segments(10, total_duration=5.0)
        req = DirectorRequest(
            concept="flash cuts",
            duration_s=5.0,
            bpm=180.0,
            key="F minor",
            segments=segs,
        )
        board = director.storyboard(req)
        assert len(board.scenes) == 10
        for scene in board.scenes:
            assert scene.duration > 0
