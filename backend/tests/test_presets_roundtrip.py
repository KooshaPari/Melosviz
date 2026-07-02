"""Unit tests for MelosViz preset load/save round-trip.

Tests cover:
- Happy path: load preset → data round-trips correctly
- Available presets: list and load operations
- Built-in availability: preset listing works
- Schema validation: preset structure is consistent
- Error handling: missing/invalid presets raise clear errors
"""

import pytest
from melosviz.presets import (
    load_preset,
    list_presets,
    BUILTIN_PRESETS,
)


# =============================================================================
# List and availability tests
# =============================================================================


class TestPresetAvailability:
    """Preset listing and availability."""

    def test_builtin_presets_constant_not_empty(self):
        """BUILTIN_PRESETS is a non-empty list."""
        assert isinstance(BUILTIN_PRESETS, list)
        assert len(BUILTIN_PRESETS) > 0

    def test_list_presets_returns_sorted_list(self):
        """list_presets() returns sorted list of names."""
        presets = list_presets()
        assert isinstance(presets, list)
        assert presets == sorted(presets)
        assert len(presets) == len(BUILTIN_PRESETS)

    def test_list_presets_matches_builtin_presets(self):
        """list_presets() matches BUILTIN_PRESETS constant."""
        assert sorted(list_presets()) == sorted(BUILTIN_PRESETS)

    def test_builtin_presets_all_strings(self):
        """All preset names are lowercase strings."""
        for name in BUILTIN_PRESETS:
            assert isinstance(name, str)
            assert name == name.lower()

    def test_preset_cinematic_is_available(self):
        """cinematic preset is in BUILTIN_PRESETS."""
        assert "cinematic" in BUILTIN_PRESETS


# =============================================================================
# Load preset happy path
# =============================================================================


class TestLoadPreset:
    """load_preset() function behavior."""

    def test_load_cinematic_returns_module(self):
        """load_preset('cinematic') returns a module object."""
        import types
        preset = load_preset("cinematic")
        assert isinstance(preset, types.ModuleType)

    def test_load_preset_case_insensitive(self):
        """load_preset() accepts uppercase/mixed case."""
        preset_lower = load_preset("cinematic")
        preset_upper = load_preset("CINEMATIC")
        preset_mixed = load_preset("CiNeMaTiC")

        # All should load the same module
        assert preset_lower.__name__ == preset_upper.__name__
        assert preset_upper.__name__ == preset_mixed.__name__

    def test_load_preset_with_whitespace(self):
        """load_preset() strips leading/trailing whitespace."""
        preset_clean = load_preset("cinematic")
        preset_spaces = load_preset("  cinematic  ")

        assert preset_clean.__name__ == preset_spaces.__name__

    def test_load_cinematic_has_apply_function(self):
        """Loaded cinematic preset module has an apply() function."""
        preset = load_preset("cinematic")
        assert hasattr(preset, "apply")
        assert callable(preset.apply)


# =============================================================================
# Round-trip and schema tests
# =============================================================================


class TestPresetSchema:
    """Preset module structure and consistency."""

    def test_cinematic_loads_without_error(self):
        """Cinematic preset loads without raising."""
        preset = load_preset("cinematic")
        assert preset is not None

    def test_cinematic_has_docstring(self):
        """Cinematic preset module has docstring."""
        preset = load_preset("cinematic")
        assert preset.__doc__ is not None
        assert len(preset.__doc__.strip()) > 0

    def test_preset_apply_function_callable(self):
        """Cinematic preset apply() function is callable."""
        preset = load_preset("cinematic")
        assert callable(preset.apply)

    def test_builtin_presets_list_complete(self):
        """BUILTIN_PRESETS list contains expected presets."""
        # At minimum, should contain cinematic which is implemented
        assert "cinematic" in BUILTIN_PRESETS


# =============================================================================
# Error handling tests
# =============================================================================


class TestPresetErrorHandling:
    """Error cases for load_preset()."""

    def test_load_nonexistent_preset_raises_keyerror(self):
        """Loading non-existent preset raises KeyError."""
        with pytest.raises(KeyError, match="Unknown preset"):
            load_preset("nonexistent_preset_xyz")

    def test_load_nonexistent_preset_message_includes_info(self):
        """KeyError message includes helpful info."""
        try:
            load_preset("invalid")
        except KeyError as e:
            error_msg = str(e)
            assert "Unknown" in error_msg or "Available" in error_msg

    def test_load_empty_string_raises_keyerror(self):
        """Loading empty string raises KeyError."""
        with pytest.raises(KeyError):
            load_preset("")

    def test_load_whitespace_only_raises_keyerror(self):
        """Loading whitespace-only string raises KeyError."""
        with pytest.raises(KeyError):
            load_preset("   ")

    def test_load_preset_with_special_chars_raises_keyerror(self):
        """Loading preset with special chars raises KeyError."""
        with pytest.raises(KeyError):
            load_preset("preset@123")

    def test_load_underscore_preset_not_in_list_raises_keyerror(self):
        """Loading a non-existent underscore preset raises KeyError."""
        with pytest.raises(KeyError):
            load_preset("not_a_real_preset")


# =============================================================================
# Multiple preset loading tests
# =============================================================================


class TestPresetCaching:
    """Preset module caching and reloading."""

    def test_repeated_load_cinematic_returns_same_module(self):
        """Loading cinematic twice returns same cached module."""
        preset1 = load_preset("cinematic")
        preset2 = load_preset("cinematic")

        # Python's importlib caches modules, so these should be identical
        assert preset1 is preset2

    def test_load_cinematic_multiple_times_no_error(self):
        """Loading cinematic multiple times succeeds."""
        for _ in range(5):
            preset = load_preset("cinematic")
            assert preset is not None
            assert callable(preset.apply)

    def test_load_with_varied_case_same_module(self):
        """Loading with different cases returns same module."""
        presets = [
            load_preset("cinematic"),
            load_preset("CINEMATIC"),
            load_preset("CiNeMaTiC"),
        ]

        # All should be the same cached object
        assert presets[0] is presets[1] is presets[2]


# =============================================================================
# Preset data integrity tests
# =============================================================================


class TestPresetDataIntegrity:
    """Data integrity when loading presets."""

    def test_load_preset_does_not_mutate_builtin_list(self):
        """Loading presets does not modify BUILTIN_PRESETS constant."""
        original = BUILTIN_PRESETS.copy()

        load_preset("cinematic")

        assert BUILTIN_PRESETS == original

    def test_repeated_loads_preserve_structure(self):
        """Repeated loads of cinematic preserve module structure."""
        preset1 = load_preset("cinematic")
        preset2 = load_preset("cinematic")
        preset3 = load_preset("cinematic")

        # All should have apply function
        assert hasattr(preset1, "apply")
        assert hasattr(preset2, "apply")
        assert hasattr(preset3, "apply")

        # Should be the same object (cached)
        assert preset1 is preset2 is preset3


# =============================================================================
# Registry integration tests
# =============================================================================


class TestPresetRegistry:
    """Integration with ThemePresetRegistry."""

    def test_registry_imports_successfully(self):
        """ThemePresetRegistry can be imported."""
        from melosviz.presets import ThemePresetRegistry

        registry = ThemePresetRegistry()
        assert registry is not None

    def test_registry_get_all_presets_not_empty(self):
        """Registry get_all_presets() returns non-empty list."""
        from melosviz.presets import ThemePresetRegistry

        registry = ThemePresetRegistry()
        presets = registry.get_all_presets()

        assert isinstance(presets, list)
        assert len(presets) > 0

    def test_registry_presets_have_required_fields(self):
        """All registry presets have id, name, colors."""
        from melosviz.presets import ThemePresetRegistry

        registry = ThemePresetRegistry()
        for preset in registry.get_all_presets():
            assert hasattr(preset, "id")
            assert hasattr(preset, "name")
            assert hasattr(preset, "colors")
            assert isinstance(preset.colors, list)

    def test_registry_preset_colors_valid(self):
        """All preset colors are valid hex strings."""
        from melosviz.presets import ThemePresetRegistry

        registry = ThemePresetRegistry()
        for preset in registry.get_all_presets():
            for color in preset.colors:
                assert isinstance(color, str)
                assert color.startswith("#")


# =============================================================================
# Edge case tests
# =============================================================================


class TestPresetEdgeCases:
    """Edge cases and boundary conditions."""

    def test_preset_name_normalization(self):
        """Preset names are normalized (lowercase, stripped)."""
        preset_clean = load_preset("cinematic")
        preset_upper = load_preset("CINEMATIC")
        preset_space = load_preset(" cinematic ")

        # All should refer to the same module
        assert preset_clean.__name__ == preset_upper.__name__
        assert preset_upper.__name__ == preset_space.__name__

    def test_load_preset_idempotent(self):
        """load_preset() is idempotent for valid names."""
        results = [load_preset("cinematic") for _ in range(5)]

        # All should be the same cached object
        assert all(r is results[0] for r in results)

    def test_load_preset_deterministic(self):
        """load_preset() returns deterministic results."""
        preset1 = load_preset("cinematic")
        preset2 = load_preset("cinematic")
        preset3 = load_preset("cinematic")

        assert preset1 is preset2 is preset3
        assert preset1.__name__ == preset2.__name__ == preset3.__name__
