"""Preset pipeline: load a preset by name and apply it to a ``RenderSpec``."""

from __future__ import annotations

from ..analysis.models import RenderSpec

from . import load_preset


def preset_pipeline(spec: RenderSpec, name: str) -> RenderSpec:
    """Apply the preset named ``name`` to ``spec`` and return the spec.

    The preset is looked up via :func:`melosviz.presets.load_preset` and
    its ``apply`` function is invoked. The spec is mutated in place and
    also returned for convenience.
    """
    preset_module = load_preset(name)
    return preset_module.apply(spec)


__all__ = ["preset_pipeline"]
