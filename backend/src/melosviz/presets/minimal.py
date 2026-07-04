"""Minimalist preset: monochrome palette with slow, deliberate keyframes.

Designed for minimalist, post-classical, and ambient drone material:
pure black and white with controlled grey mid-tones, long unhurried
transitions, and maximum negative space. Every frame has a purpose.
Evokes concrete poetry, clean architecture, and the space between notes.
"""

from __future__ import annotations

from typing import Any

from ..analysis.models import RenderSpec

MINIMAL_PALETTE: list[str] = [
    "#000000",  # pure black
    "#1A1A1A",  # near black
    "#4D4D4D",  # dark grey
    "#999999",  # mid grey
    "#CCCCCC",  # light grey
    "#FFFFFF",  # pure white
]


def _layers() -> list[dict[str, Any]]:
    return [
        {
            "name": "void_field",
            "type": "shape",
            "geometry": "rectangle",
            "fill": "#000000",
            "weight": 1.0,
        },
        {
            "name": "breath_gradient",
            "type": "gradient",
            "intensity": 0.3,
            "swing_ms": 8000,
            "blend": "normal",
        },
        {
            "name": "single_line",
            "type": "shape",
            "geometry": "line",
            "weight": 0.5,
            "stroke_width": 1.0,
        },
        {
            "name": "sparse_dots",
            "type": "particles",
            "count": 6,
            "drift": "still",
            "size_curve": "constant",
        },
    ]


def _keyframes() -> list[dict[str, Any]]:
    return [
        {"time": 0.0, "zoom": 1.0, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.0},
        {"time": 12.0, "zoom": 1.01, "pan_x": 0.0, "pan_y": -0.005, "glow": 0.1},
        {"time": 30.0, "zoom": 1.0, "pan_x": 0.005, "pan_y": 0.0, "glow": 0.15},
        {"time": 50.0, "zoom": 0.99, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.05},
    ]


def apply(spec: RenderSpec) -> RenderSpec:
    """Mutate ``spec`` in place with minimalist styling and return it."""
    spec.metadata = {
        **spec.metadata,
        "preset": "minimal",
        "motion_style": "still",
        "tempo_target_bpm": (40, 80),
        "contrast": "absolute",
        "grain": 0.0,
        "vignette": 0.1,
        "particle_density": 0.05,
        "saturation": 0.0,
        "negative_space": True,
    }
    spec.palette = list(MINIMAL_PALETTE)
    spec.layers = _layers()
    spec.keyframes = _keyframes()
    spec.timeline = [
        *spec.timeline,
        {
            "time": 0.0,
            "type": "section",
            "data": {"name": "silence", "mood": "sparse"},
        },
        {"time": 15.0, "type": "section", "data": {"name": "emergence", "mood": "deliberate"}},
        {"time": 38.0, "type": "section", "data": {"name": "resolution", "mood": "still"}},
    ]
    return spec
