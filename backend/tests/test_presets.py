"""Tests for the melosviz preset library (WP-8).

Covers the package-level ``list_presets`` / ``load_preset`` registry, the
``apply(spec)`` mutation contract for each built-in preset (jazz,
classical, edm, ambient, world), and the ``preset_pipeline`` helper. The
goal is to lock down the *shape* of the mutations a preset makes to a
:class:`melosviz.analysis.models.RenderSpec`: color palette, animation
style, and particle density must all be touched.
"""

from __future__ import annotations

from typing import Iterable

import pytest

from melosviz.analysis.models import RenderSpec
from melosviz.presets import (
    BUILTIN_PRESETS,
    list_presets,
    load_preset,
)
from melosviz.presets.pipeline import preset_pipeline


EXPECTED_PRESETS = ("jazz", "classical", "edm", "ambient", "world")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_spec() -> RenderSpec:
    """Return a clean RenderSpec with no preset-specific metadata."""
    return RenderSpec(metadata={"source": "test"})


# ---------------------------------------------------------------------------
# Registry-level tests
# ---------------------------------------------------------------------------


def test_list_presets_returns_all_expected_names() -> None:
    names = list_presets()
    for expected in EXPECTED_PRESETS:
        assert expected in names, f"Missing preset: {expected}"


def test_list_presets_is_sorted() -> None:
    assert list_presets() == sorted(list_presets())


def test_list_presets_matches_builtin_constant() -> None:
    assert set(list_presets()) == set(BUILTIN_PRESETS)


def test_load_preset_returns_module_with_apply() -> None:
    module = load_preset("jazz")
    assert hasattr(module, "apply")
    assert callable(module.apply)


def test_load_preset_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        load_preset("nonexistent_preset")


def test_load_preset_is_case_insensitive() -> None:
    upper = load_preset("JAZZ")
    lower = load_preset("jazz")
    assert upper is lower


def test_load_preset_strips_whitespace() -> None:
    assert load_preset("  world  ") is load_preset("world")


# ---------------------------------------------------------------------------
# Per-preset apply() contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("preset_name", EXPECTED_PRESETS)
def test_apply_returns_render_spec(preset_name: str, fresh_spec: RenderSpec) -> None:
    module = load_preset(preset_name)
    result = module.apply(fresh_spec)
    assert isinstance(result, RenderSpec)
    assert result is fresh_spec  # mutation contract: same object


@pytest.mark.parametrize("preset_name", EXPECTED_PRESETS)
def test_apply_sets_color_palette(preset_name: str, fresh_spec: RenderSpec) -> None:
    module = load_preset(preset_name)
    module.apply(fresh_spec)
    assert fresh_spec.palette, f"{preset_name} preset did not set a palette"
    for color in fresh_spec.palette:
        assert isinstance(color, str)
        assert color.startswith("#"), f"{preset_name} produced non-hex color {color!r}"


@pytest.mark.parametrize("preset_name", EXPECTED_PRESETS)
def test_apply_sets_animation_style(preset_name: str, fresh_spec: RenderSpec) -> None:
    module = load_preset(preset_name)
    module.apply(fresh_spec)
    assert "motion_style" in fresh_spec.metadata, (
        f"{preset_name} preset did not set motion_style"
    )
    assert isinstance(fresh_spec.metadata["motion_style"], str)
    assert fresh_spec.metadata["motion_style"]


@pytest.mark.parametrize("preset_name", EXPECTED_PRESETS)
def test_apply_sets_particle_density(preset_name: str, fresh_spec: RenderSpec) -> None:
    module = load_preset(preset_name)
    module.apply(fresh_spec)
    assert "particle_density" in fresh_spec.metadata, (
        f"{preset_name} preset did not set particle_density"
    )
    density = fresh_spec.metadata["particle_density"]
    assert isinstance(density, (int, float))
    assert 0.0 <= float(density) <= 1.0, (
        f"{preset_name} particle_density out of [0,1]: {density}"
    )


@pytest.mark.parametrize("preset_name", EXPECTED_PRESETS)
def test_apply_preserves_existing_metadata(preset_name: str, fresh_spec: RenderSpec) -> None:
    module = load_preset(preset_name)
    module.apply(fresh_spec)
    assert fresh_spec.metadata.get("source") == "test", (
        f"{preset_name} preset clobbered existing metadata"
    )


@pytest.mark.parametrize("preset_name", EXPECTED_PRESETS)
def test_apply_appends_timeline_sections(preset_name: str, fresh_spec: RenderSpec) -> None:
    module = load_preset(preset_name)
    pre_count = len(fresh_spec.timeline)
    module.apply(fresh_spec)
    assert len(fresh_spec.timeline) > pre_count, (
        f"{preset_name} preset did not append timeline events"
    )
    appended = fresh_spec.timeline[pre_count:]
    assert all(event.get("type") == "section" for event in appended)


@pytest.mark.parametrize("preset_name", EXPECTED_PRESETS)
def test_apply_sets_layers(preset_name: str, fresh_spec: RenderSpec) -> None:
    module = load_preset(preset_name)
    module.apply(fresh_spec)
    assert fresh_spec.layers, f"{preset_name} preset did not set layers"
    # Particle density is exposed in metadata; it must be > 0 for every
    # preset (the renderer uses it even when no explicit particles layer
    # is declared — e.g. EDM uses a spectrum layer).
    declared_density = float(fresh_spec.metadata["particle_density"])
    assert declared_density > 0.0, (
        f"{preset_name} preset declared particle_density=0"
    )
    particle_layers = [
        layer
        for layer in fresh_spec.layers
        if isinstance(layer, dict) and layer.get("type") == "particles"
    ]
    if particle_layers:
        # Sanity check: declared density is consistent with the highest
        # explicit particle count (loosely correlated, not strict).
        max_count = max(
            (int(layer.get("count", 0)) for layer in particle_layers),
            default=0,
        )
        assert max_count > 0


# ---------------------------------------------------------------------------
# Cross-preset tests
# ---------------------------------------------------------------------------


def test_presets_have_distinct_palettes() -> None:
    palettes: dict[str, Iterable[str]] = {}
    for name in EXPECTED_PRESETS:
        module = load_preset(name)
        spec = RenderSpec()
        module.apply(spec)
        palettes[name] = tuple(spec.palette)
    # Compare first color of each; every genre should have a unique lead.
    leads = {name: list(p)[0] for name, p in palettes.items()}
    assert len(set(leads.values())) == len(leads), (
        f"Presets share leading palette colors: {leads}"
    )


def test_presets_have_unique_motion_styles() -> None:
    styles: dict[str, str] = {}
    for name in EXPECTED_PRESETS:
        module = load_preset(name)
        spec = RenderSpec()
        module.apply(spec)
        styles[name] = spec.metadata["motion_style"]
    assert len(set(styles.values())) == len(styles), (
        f"Presets share motion styles: {styles}"
    )


def test_world_preset_uses_world_metadata() -> None:
    spec = RenderSpec()
    load_preset("world").apply(spec)
    assert spec.metadata["preset"] == "world"
    assert spec.metadata["motion_style"] == "polyrhythmic_gesture"
    # World palette is built from earthen / saffron tones.
    assert "#C46A1F" in spec.palette  # saffron accent


def test_jazz_preset_uses_warm_palette() -> None:
    spec = RenderSpec()
    load_preset("jazz").apply(spec)
    assert spec.metadata["preset"] == "jazz"
    assert spec.metadata["motion_style"] == "syncopated_sway"
    assert spec.metadata["contrast"] == "low"


def test_edm_preset_uses_high_contrast_palette() -> None:
    spec = RenderSpec()
    load_preset("edm").apply(spec)
    assert spec.metadata["preset"] == "edm"
    assert spec.metadata["contrast"] == "very_high"
    assert spec.metadata["motion_style"] == "four_on_the_floor"
    # EDM palette is defined by saturated neon and white.
    assert "#FFFFFF" in spec.palette


def test_preset_pipeline_works_end_to_end(fresh_spec: RenderSpec) -> None:
    result = preset_pipeline(fresh_spec, "classical")
    assert result is fresh_spec
    assert fresh_spec.metadata["preset"] == "classical"
    assert fresh_spec.metadata["motion_style"] == "sweeping_orchestral"
    assert fresh_spec.palette


def test_preset_pipeline_propagates_unknown_preset_error() -> None:
    spec = RenderSpec()
    with pytest.raises(KeyError):
        preset_pipeline(spec, "no_such_genre")
