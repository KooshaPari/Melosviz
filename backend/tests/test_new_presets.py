"""Tests for the three new built-in presets: lofi, synthwave, minimal."""

from __future__ import annotations

import pytest

from melosviz.analysis.models import RenderSpec
from melosviz.presets import list_presets, load_preset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_spec() -> RenderSpec:
    """Return a bare RenderSpec suitable for preset application."""
    return RenderSpec(
        metadata={},
        palette=[],
        layers=[],
        keyframes=[],
        timeline=[],
    )


# ---------------------------------------------------------------------------
# Lo-fi preset
# ---------------------------------------------------------------------------

class TestLofiPreset:
    def test_apply_sets_preset_metadata(self) -> None:
        spec = _fresh_spec()
        result = load_preset("lofi").apply(spec)
        assert result.metadata["preset"] == "lofi"

    def test_palette_has_at_least_four_colors(self) -> None:
        spec = _fresh_spec()
        result = load_preset("lofi").apply(spec)
        assert len(result.palette) >= 4

    def test_layers_non_empty(self) -> None:
        spec = _fresh_spec()
        result = load_preset("lofi").apply(spec)
        assert len(result.layers) > 0

    def test_keyframes_non_empty(self) -> None:
        spec = _fresh_spec()
        result = load_preset("lofi").apply(spec)
        assert len(result.keyframes) > 0


# ---------------------------------------------------------------------------
# Synthwave preset
# ---------------------------------------------------------------------------

class TestSynthwavePreset:
    def test_apply_sets_preset_metadata(self) -> None:
        spec = _fresh_spec()
        result = load_preset("synthwave").apply(spec)
        assert result.metadata["preset"] == "synthwave"

    def test_palette_has_at_least_four_colors(self) -> None:
        spec = _fresh_spec()
        result = load_preset("synthwave").apply(spec)
        assert len(result.palette) >= 4

    def test_layers_non_empty(self) -> None:
        spec = _fresh_spec()
        result = load_preset("synthwave").apply(spec)
        assert len(result.layers) > 0

    def test_keyframes_non_empty(self) -> None:
        spec = _fresh_spec()
        result = load_preset("synthwave").apply(spec)
        assert len(result.keyframes) > 0


# ---------------------------------------------------------------------------
# Minimal preset
# ---------------------------------------------------------------------------

class TestMinimalPreset:
    def test_apply_sets_preset_metadata(self) -> None:
        spec = _fresh_spec()
        result = load_preset("minimal").apply(spec)
        assert result.metadata["preset"] == "minimal"

    def test_palette_has_at_least_four_colors(self) -> None:
        spec = _fresh_spec()
        result = load_preset("minimal").apply(spec)
        assert len(result.palette) >= 4

    def test_layers_non_empty(self) -> None:
        spec = _fresh_spec()
        result = load_preset("minimal").apply(spec)
        assert len(result.layers) > 0

    def test_keyframes_non_empty(self) -> None:
        spec = _fresh_spec()
        result = load_preset("minimal").apply(spec)
        assert len(result.keyframes) > 0


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

class TestPresetsRegistry:
    def test_list_presets_includes_lofi(self) -> None:
        assert "lofi" in list_presets()

    def test_list_presets_includes_synthwave(self) -> None:
        assert "synthwave" in list_presets()

    def test_list_presets_includes_minimal(self) -> None:
        assert "minimal" in list_presets()

    def test_load_unknown_preset_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            load_preset("does_not_exist")
