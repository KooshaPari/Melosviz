"""Tests for the partial-scene re-render policy.

Pure-function tests — no fixtures, no orchestrator, no network. Proves the
policy returns the right scene indices given a target + the env-controlled
neighbor expansion.
"""
from __future__ import annotations

import pytest

from melosviz.cli.partial_rerender import (
    MAX_NEIGHBORS,
    DEFAULT_NEIGHBORS,
    expand_scene_indices_with_neighbors,
    parse_neighbor_policy,
    resolve_only_scenes,
)


# ----------------------------------------------------------------------------
# parse_neighbor_policy
# ----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, DEFAULT_NEIGHBORS),    # unset -> default
        ("",   DEFAULT_NEIGHBORS),    # empty  -> default
        ("auto", DEFAULT_NEIGHBORS),
        ("1",  1),
        ("true", 1),
        ("yes", 1),
        ("on",  1),
        ("0",  0),
        ("false", 0),
        ("no",  0),
        ("off", 0),
        ("2",  2),
        ("3",  3),
        ("max", MAX_NEIGHBORS),
        ("999", MAX_NEIGHBORS),       # clamp to MAX_NEIGHBORS
        ("-5", 0),                    # clamp negative -> 0
        ("abc", DEFAULT_NEIGHBORS),   # unknown -> default
    ],
)
def test_parse_neighbor_policy(raw, expected):
    assert parse_neighbor_policy(raw) == expected


# ----------------------------------------------------------------------------
# expand_scene_indices_with_neighbors
# ----------------------------------------------------------------------------

def test_expand_target_only_when_neighbor_zero():
    assert expand_scene_indices_with_neighbors(5, 10, 0) == [5]


def test_expand_one_neighbor_each_side():
    assert expand_scene_indices_with_neighbors(5, 10, 1) == [4, 5, 6]


def test_expand_two_neighbors_each_side():
    assert expand_scene_indices_with_neighbors(5, 10, 2) == [3, 4, 5, 6, 7]


def test_expand_clamps_to_start():
    # Scene 0 with 1 neighbor should NOT wrap to a negative index.
    assert expand_scene_indices_with_neighbors(0, 10, 1) == [0, 1]


def test_expand_clamps_to_end():
    # Scene 9 (last) with 1 neighbor should NOT exceed total_scenes - 1.
    assert expand_scene_indices_with_neighbors(9, 10, 1) == [8, 9]


def test_expand_clamps_target_above_total():
    assert expand_scene_indices_with_neighbors(99, 5, 1) == [3, 4]


def test_expand_clamps_target_below_zero():
    assert expand_scene_indices_with_neighbors(-5, 10, 1) == [0, 1]


def test_expand_single_scene_storyboard_returns_only_target():
    assert expand_scene_indices_with_neighbors(0, 1, 5) == [0]


def test_expand_empty_storyboard_falls_back_to_target_clamped():
    # total_scenes=0 -> fallback to 1 -> just the target.
    assert expand_scene_indices_with_neighbors(7, 0, 2) == [0]


def test_expand_deduplicates():
    # With max neighbors + target 0, no duplicates.
    result = expand_scene_indices_with_neighbors(0, 3, 5)
    assert result == [0, 1, 2]
    assert len(result) == len(set(result))


# ----------------------------------------------------------------------------
# resolve_only_scenes — env-driven policy
# ----------------------------------------------------------------------------

def test_resolve_only_scenes_default_neighbor_policy():
    out = resolve_only_scenes(
        target_scene_index=3,
        total_scenes=10,
        env=[("MELOSVIZ_DIRECT_NEIGHBORS", "2")],
    )
    assert out == [1, 2, 3, 4, 5]


def test_resolve_only_scenes_disabled():
    out = resolve_only_scenes(
        target_scene_index=3,
        total_scenes=10,
        env=[("MELOSVIZ_DIRECT_NEIGHBORS", "0")],
    )
    assert out == [3]


def test_resolve_only_scenes_no_env_returns_default():
    out = resolve_only_scenes(target_scene_index=3, total_scenes=10, env=[])
    assert out == [2, 3, 4]   # default = +1 neighbor each side


def test_resolve_only_scenes_max_neighbors():
    out = resolve_only_scenes(
        target_scene_index=4,
        total_scenes=10,
        env=[("MELOSVIZ_DIRECT_NEIGHBORS", "max")],
    )
    # 4 +/- 5 clamped -> [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert out == list(range(10))


def test_resolve_only_scenes_single_scene_storyboard():
    out = resolve_only_scenes(
        target_scene_index=0,
        total_scenes=1,
        env=[("MELOSVIZ_DIRECT_NEIGHBORS", "max")],
    )
    assert out == [0]
