"""Preset library: mutation-style presets for ``RenderSpec``.

This package exposes a small registry of preset modules. Each module is
named after a musical genre or visual style and exports an ``apply(spec)``
function that mutates a :class:`melosviz.analysis.models.RenderSpec` in
place, then returns it.

The legacy :class:`ThemePresetRegistry` is re-exported here so existing
callers (e.g. ``melosviz.main``) keep working.
"""

from __future__ import annotations

import importlib
import os
import sys
from types import ModuleType

# Ensure ``melosviz`` is importable as a top-level package even when this
# package is loaded via the ``backend.src.melosviz.presets`` path. Several
# existing modules in the codebase use absolute ``from melosviz.X`` style
# imports, so ``backend/src`` must be on ``sys.path`` for those to
# resolve under that loading scheme.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
if _SRC_ROOT not in sys.path:
    sys.path.insert(0, _SRC_ROOT)

# Re-export the legacy registry so ``from melosviz.presets import
# ThemePresetRegistry`` continues to work for the rest of the codebase.
from .registry import ThemePresetRegistry  # noqa: E402,F401

#: Built-in preset module names exposed by this package.
BUILTIN_PRESETS: list[str] = [
    "jazz",
    "classical",
    "edm",
    "ambient",
    "cinematic",
    "world",
]


def list_presets() -> list[str]:
    """Return the sorted list of available preset names."""
    return sorted(BUILTIN_PRESETS)


def load_preset(name: str) -> ModuleType:
    """Import and return the preset module registered under ``name``.

    Raises :class:`KeyError` when no preset is registered under ``name``.
    The preset module is loaded via a relative import so this works
    whether the package is imported as ``melosviz.presets`` or as
    ``backend.src.melosviz.presets``.
    """
    key = name.strip().lower()
    if key not in BUILTIN_PRESETS:
        raise KeyError(f"Unknown preset {name!r}. Available: {list_presets()}")
    return importlib.import_module(f".{key}", package=__name__)


__all__ = [
    "BUILTIN_PRESETS",
    "ThemePresetRegistry",
    "list_presets",
    "load_preset",
]
