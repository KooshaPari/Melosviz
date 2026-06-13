"""Tests for the melosviz preset library (WP-8 + WP-17).

WP-8 covers the package-level ``list_presets`` / ``load_preset`` registry,
the ``apply(spec)`` mutation contract for each built-in preset (jazz,
classical, edm, ambient, world), and the ``preset_pipeline`` helper.

WP-17 adds a glob-driven smoke test that scans ``presets/*.py`` and
asserts every preset module:
  1. imports cleanly (no syntax / import errors);
  2. exposes a callable ``apply(spec)`` that accepts a ``RenderSpec``;
  3. mutates the spec in place and returns it;
  4. populates the contract fields (palette, layers, keyframes,
     motion_style, timeline sections).

The glob approach locks down the *shape* of every preset file in
``presets/`` so that future additions (e.g. ``cinematic.py``) cannot
silently bypass the contract.
"""

from __future__ import annotations

import importlib
from glob import glob
from pathlib import Path
from types import ModuleType
from typing import Iterable, List

import pytest

from melosviz.analysis.models import RenderSpec
from melosviz.presets import (
    BUILTIN_PRESETS,
    list_presets,
    load_preset,
)
from melosviz.presets.pipeline import preset_pipeline


EXPECTED_PRESETS = ("jazz", "classical", "edm", "ambient", "world")

# Helper / non-preset modules that live in the presets package but are
# NOT genre presets. They are skipped by the glob-driven smoke test.
_PRESET_PACKAGE_FILES = {"__init__.py", "registry.py", "pipeline.py"}


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


# ---------------------------------------------------------------------------
# WP-17 — glob-driven smoke test of every presets/*.py module
# ---------------------------------------------------------------------------
#
# The contract below ensures that any preset module dropped into
# ``presets/`` (genre preset, style preset, experimental preset, etc.) is
# importable, exposes a callable ``apply(spec)``, and produces a valid
# mutation of :class:`RenderSpec`. If a new file does not satisfy these
# invariants, the test fails fast and surfaces the regression at the
# file responsible.


def _preset_package_dir() -> Path:
    """Locate the ``melosviz/presets`` package on disk."""
    return Path(__file__).resolve().parents[1] / "src" / "melosviz" / "presets"


def _discover_preset_files() -> List[Path]:
    """Return every ``presets/*.py`` file except the package helpers."""
    package_dir = _preset_package_dir()
    all_py = sorted(package_dir.glob("*.py"))
    return [p for p in all_py if p.name not in _PRESET_PACKAGE_FILES]


@pytest.fixture(scope="module")
def discovered_preset_files() -> List[Path]:
    """Module-scoped list of preset files on disk."""
    return _discover_preset_files()


@pytest.fixture(scope="module")
def discovered_preset_modules(discovered_preset_files: List[Path]) -> dict[str, ModuleType]:
    """Import every discovered preset file once and cache the modules."""
    package = "melosviz.presets"
    modules: dict[str, ModuleType] = {}
    for path in discovered_preset_files:
        name = path.stem
        modules[name] = importlib.import_module(f".{name}", package=package)
    return modules


def test_glob_finds_at_least_one_preset(discovered_preset_files: List[Path]) -> None:
    """Sanity check: the glob must not return an empty list."""
    assert discovered_preset_files, (
        "glob(presets/*.py) returned no preset files; "
        "check the package layout or update the helper-skip list"
    )


def test_glob_finds_only_existing_presets(
    discovered_preset_files: List[Path],
) -> None:
    """Every entry in ``BUILTIN_PRESETS`` must have a matching .py file."""
    on_disk = {p.stem for p in discovered_preset_files}
    missing = set(BUILTIN_PRESETS) - on_disk
    assert not missing, f"BUILTIN_PRESETS references missing files: {missing}"


def test_builtin_presets_have_matching_files(
    discovered_preset_files: List[Path],
) -> None:
    """Every ``presets/*.py`` file should be exposed via ``BUILTIN_PRESETS``."""
    on_disk = {p.stem for p in discovered_preset_files}
    unregistered = on_disk - set(BUILTIN_PRESETS)
    assert not unregistered, (
        f"Preset files exist on disk but are not in BUILTIN_PRESETS: "
        f"{sorted(unregistered)}"
    )


def test_discovered_presets_match_builtin_list(
    discovered_preset_files: List[Path],
) -> None:
    """Disk-driven and registry-driven preset lists must agree exactly."""
    on_disk = sorted(p.stem for p in discovered_preset_files)
    registry = sorted(BUILTIN_PRESETS)
    assert on_disk == registry, (
        f"Preset mismatch — disk={on_disk}, registry={registry}"
    )


@pytest.mark.parametrize(
    "preset_path",
    _discover_preset_files(),
    ids=lambda p: p.stem,
)
def test_preset_module_imports_cleanly(preset_path: Path) -> None:
    """Every ``presets/*.py`` must be importable without raising."""
    name = preset_path.stem
    module = importlib.import_module(f".{name}", package="melosviz.presets")
    assert module is not None
    assert module.__file__ is not None


@pytest.mark.parametrize(
    "preset_path",
    _discover_preset_files(),
    ids=lambda p: p.stem,
)
def test_preset_module_exposes_apply(preset_path: Path) -> None:
    """Every preset module must define a callable ``apply(spec)``."""
    name = preset_path.stem
    module = importlib.import_module(f".{name}", package="melosviz.presets")
    assert hasattr(module, "apply"), (
        f"Preset module {name!r} does not define an `apply` symbol"
    )
    assert callable(module.apply), (
        f"Preset module {name!r} defines `apply` but it is not callable"
    )


@pytest.mark.parametrize(
    "preset_path",
    _discover_preset_files(),
    ids=lambda p: p.stem,
)
def test_preset_apply_returns_render_spec(preset_path: Path) -> None:
    """``apply(spec)`` must return the spec object (mutation contract)."""
    name = preset_path.stem
    module = importlib.import_module(f".{name}", package="melosviz.presets")
    spec = RenderSpec()
    result = module.apply(spec)
    assert isinstance(result, RenderSpec)
    assert result is spec, (
        f"Preset {name!r} returned a different spec object; "
        f"expected in-place mutation"
    )


@pytest.mark.parametrize(
    "preset_path",
    _discover_preset_files(),
    ids=lambda p: p.stem,
)
def test_preset_apply_populates_palette(preset_path: Path) -> None:
    """Every preset must populate ``spec.palette`` with at least one color."""
    name = preset_path.stem
    module = importlib.import_module(f".{name}", package="melosviz.presets")
    spec = RenderSpec()
    module.apply(spec)
    assert spec.palette, f"Preset {name!r} left palette empty"
    for color in spec.palette:
        assert isinstance(color, str), (
            f"Preset {name!r} produced non-string palette entry: {color!r}"
        )
        assert color.startswith("#"), (
            f"Preset {name!r} produced non-hex color: {color!r}"
        )


@pytest.mark.parametrize(
    "preset_path",
    _discover_preset_files(),
    ids=lambda p: p.stem,
)
def test_preset_apply_sets_layers(preset_path: Path) -> None:
    """Every preset must populate ``spec.layers`` with at least one entry."""
    name = preset_path.stem
    module = importlib.import_module(f".{name}", package="melosviz.presets")
    spec = RenderSpec()
    module.apply(spec)
    assert spec.layers, f"Preset {name!r} left layers empty"
    for layer in spec.layers:
        assert isinstance(layer, dict), (
            f"Preset {name!r} produced non-dict layer: {layer!r}"
        )
        assert layer.get("name"), (
            f"Preset {name!r} produced a layer without a `name`: {layer!r}"
        )
        assert layer.get("type"), (
            f"Preset {name!r} produced a layer without a `type`: {layer!r}"
        )


@pytest.mark.parametrize(
    "preset_path",
    _discover_preset_files(),
    ids=lambda p: p.stem,
)
def test_preset_apply_sets_keyframes(preset_path: Path) -> None:
    """Every preset must populate ``spec.keyframes`` with at least one entry."""
    name = preset_path.stem
    module = importlib.import_module(f".{name}", package="melosviz.presets")
    spec = RenderSpec()
    module.apply(spec)
    assert spec.keyframes, f"Preset {name!r} left keyframes empty"
    for keyframe in spec.keyframes:
        assert isinstance(keyframe, dict), (
            f"Preset {name!r} produced non-dict keyframe: {keyframe!r}"
        )
        assert "time" in keyframe, (
            f"Preset {name!r} produced a keyframe without `time`: {keyframe!r}"
        )


@pytest.mark.parametrize(
    "preset_path",
    _discover_preset_files(),
    ids=lambda p: p.stem,
)
def test_preset_apply_sets_motion_style(preset_path: Path) -> None:
    """Every preset must set ``motion_style`` in ``spec.metadata``."""
    name = preset_path.stem
    module = importlib.import_module(f".{name}", package="melosviz.presets")
    spec = RenderSpec()
    module.apply(spec)
    assert "motion_style" in spec.metadata, (
        f"Preset {name!r} did not set motion_style in metadata"
    )
    motion_style = spec.metadata["motion_style"]
    assert isinstance(motion_style, str)
    assert motion_style, f"Preset {name!r} set an empty motion_style"


@pytest.mark.parametrize(
    "preset_path",
    _discover_preset_files(),
    ids=lambda p: p.stem,
)
def test_preset_apply_appends_timeline_sections(preset_path: Path) -> None:
    """Every preset must append at least one ``section`` event to the timeline."""
    name = preset_path.stem
    module = importlib.import_module(f".{name}", package="melosviz.presets")
    spec = RenderSpec()
    pre_count = len(spec.timeline)
    module.apply(spec)
    appended = spec.timeline[pre_count:]
    assert appended, f"Preset {name!r} did not append any timeline events"
    assert all(event.get("type") == "section" for event in appended), (
        f"Preset {name!r} appended non-section timeline events: {appended!r}"
    )


@pytest.mark.parametrize(
    "preset_path",
    _discover_preset_files(),
    ids=lambda p: p.stem,
)
def test_preset_apply_is_idempotent_under_repeated_calls(preset_path: Path) -> None:
    """Calling ``apply`` twice must not raise and must not lose the contract."""
    name = preset_path.stem
    module = importlib.import_module(f".{name}", package="melosviz.presets")
    spec = RenderSpec()
    module.apply(spec)
    first_palette = list(spec.palette)
    first_motion = spec.metadata["motion_style"]
    # Second invocation — must not raise.
    module.apply(spec)
    assert spec.palette == first_palette, (
        f"Preset {name!r} changed palette across repeated apply() calls"
    )
    assert spec.metadata["motion_style"] == first_motion, (
        f"Preset {name!r} changed motion_style across repeated apply() calls"
    )
