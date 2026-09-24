"""Tests for :mod:`melosviz.presets.aspect_ratios`.

The module is a frozen dataclass table plus two trivial accessors::

    DELIVERY_ASPECT_RATIOS: tuple[AspectRatioPreset, ...]
    aspect_ratio_by_name(name) -> AspectRatioPreset       # case-insensitive, falls back to youtube_1080
    list_aspect_ratio_names() -> list[str]

These tests existed in the original `presets` package but were dropped during
the WBS-P3.1 split that refactored ``presets/`` into its own subpackage.
QGate coverage reports this file at 0%, which blocks re-enabling the
per-module coverage floor. Restore the tests so the gate has something
real to measure against.
"""

from __future__ import annotations

import pytest

from melosviz.presets import aspect_ratios as ar
from melosviz.presets.aspect_ratios import (
    DELIVERY_ASPECT_RATIOS,
    AspectRatioPreset,
    aspect_ratio_by_name,
    list_aspect_ratio_names,
)

# ---------------------------------------------------------------------------
# Shape / freeze invariants
# ---------------------------------------------------------------------------


def test_delivery_aspect_ratios_is_non_empty_tuple_of_frozen_presets() -> None:
    """``DELIVERY_ASPECT_RATIOS`` must be a non-empty, order-stable tuple."""
    assert isinstance(DELIVERY_ASPECT_RATIOS, tuple)
    assert len(DELIVERY_ASPECT_RATIOS) >= 5
    for preset in DELIVERY_ASPECT_RATIOS:
        assert isinstance(preset, AspectRatioPreset)
        # frozen=True means mutating attributes must raise FrozenInstanceError
        with pytest.raises((AttributeError, Exception)) as exc_info:
            preset.label = "mutated"  # type: ignore[misc]
        # ``FrozenInstanceError`` from dataclasses subclasses AttributeError; its
        # message format is "cannot assign to field 'label'", so we accept
        # either AttributeError itself or that exact substring.
        assert isinstance(exc_info.value, AttributeError)
        assert "assign to field" in str(exc_info.value)


def test_each_preset_has_dimension_positive_integers_and_fps_positive() -> None:
    """Every preset must have positive integer width/height/fps."""
    for preset in DELIVERY_ASPECT_RATIOS:
        assert isinstance(preset.width, int) and preset.width > 0
        assert isinstance(preset.height, int) and preset.height > 0
        assert isinstance(preset.fps, int) and preset.fps > 0
        assert isinstance(preset.name, str) and preset.name
        assert isinstance(preset.label, str) and preset.label
        assert isinstance(preset.notes, str) and preset.notes


def test_preset_names_are_unique() -> None:
    """Duplicate names would make ``aspect_ratio_by_name`` order-dependent."""
    names = [p.name for p in DELIVERY_ASPECT_RATIOS]
    assert len(names) == len(set(names)), f"duplicate preset names: {names}"


def test_default_fallback_youtube_1080_present_in_table() -> None:
    """``aspect_ratio_by_name`` falls back to ``youtube_1080`` for unknown names.

    The fallback is only safe if the default is actually in the table. The
    assert in the source's RuntimeError branch is a real guard.
    """
    assert any(p.name == "youtube_1080" for p in DELIVERY_ASPECT_RATIOS)


# ---------------------------------------------------------------------------
# aspect_ratio_by_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [p.name for p in DELIVERY_ASPECT_RATIOS])
def test_aspect_ratio_by_name_returns_exact_match(name: str) -> None:
    preset = aspect_ratio_by_name(name)
    assert preset.name == name


@pytest.mark.parametrize("variant", ["YouTube_4K", "YOUTUBE_4K", "youtube_4k ", "  youtube_4k"])
def test_aspect_ratio_by_name_is_case_and_whitespace_insensitive(variant: str) -> None:
    preset = aspect_ratio_by_name(variant)
    assert preset.name == "youtube_4k"


def test_aspect_ratio_by_name_unknown_returns_youtube_1080_fallback() -> None:
    """Unknown names fall back to the default rather than raising."""
    preset = aspect_ratio_by_name("not_a_real_preset_42")
    assert preset.name == "youtube_1080"
    assert preset.width == 1920
    assert preset.height == 1080
    assert preset.fps == 24


def test_aspect_ratio_by_name_empty_string_returns_fallback() -> None:
    """An empty name also falls back -- the .strip().lower() handles it."""
    preset = aspect_ratio_by_name("")
    assert preset.name == "youtube_1080"


# ---------------------------------------------------------------------------
# list_aspect_ratio_names
# ---------------------------------------------------------------------------


def test_list_aspect_ratio_names_returns_all_table_names_in_order() -> None:
    names = list_aspect_ratio_names()
    assert names == [p.name for p in DELIVERY_ASPECT_RATIOS]


def test_list_aspect_ratio_names_returns_list_not_tuple() -> None:
    """The docstring promises ``list[str]`` -- enforce the type."""
    assert isinstance(list_aspect_ratio_names(), list)
    for name in list_aspect_ratio_names():
        assert isinstance(name, str)


# ---------------------------------------------------------------------------
# __all__ export contract
# ---------------------------------------------------------------------------


def test_module_exposes_expected_public_surface() -> None:
    assert set(ar.__all__) == {
        "AspectRatioPreset",
        "DELIVERY_ASPECT_RATIOS",
        "aspect_ratio_by_name",
        "list_aspect_ratio_names",
    }
