"""Synthwave/retrowave preset: neon grid aesthetic with fast BPM pulse.

Designed for synthwave, retrowave, and outrun-style electronic music:
electric pinks and purples against deep night-sky blues, sharp grid
perspective receding to a horizon, and fast strobe-like pulses synced to
the beat. Evokes 1980s arcade cabinets, neon-lit rain-slicked roads, and
chrome chrome chrome.
"""

from __future__ import annotations

from typing import Any

from ..analysis.models import RenderSpec
from ..compose.web_spec import enrich_render_spec_for_web

SYNTHWAVE_PALETTE: list[str] = [
    "#0D0221",  # deep night blue
    "#2D0057",  # dark purple
    "#7B00D4",  # electric violet
    "#FF2D78",  # hot neon pink
    "#00F5FF",  # electric cyan
    "#FFE600",  # laser yellow
]


def _layers() -> list[dict[str, Any]]:
    return [
        {
            "name": "grid_horizon",
            "type": "shape",
            "geometry": "perspective_grid",
            "vanishing_y": 0.55,
            "cell_size": 0.08,
            "weight": 1.0,
        },
        {
            "name": "neon_bloom",
            "type": "gradient",
            "intensity": 0.9,
            "swing_ms": 600,
            "blend": "add",
        },
        {
            "name": "scanlines",
            "type": "texture",
            "pattern": "scanlines",
            "intensity": 0.35,
            "blend": "multiply",
        },
        {
            "name": "star_streaks",
            "type": "particles",
            "count": 40,
            "drift": "streak_forward",
            "size_curve": "exponential_fade",
        },
    ]


def _keyframes() -> list[dict[str, Any]]:
    return [
        {"time": 0.0, "zoom": 1.0, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.6},
        {"time": 2.0, "zoom": 1.06, "pan_x": 0.0, "pan_y": -0.04, "glow": 0.9},
        {"time": 8.0, "zoom": 1.0, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.7},
        {"time": 14.0, "zoom": 1.08, "pan_x": 0.02, "pan_y": -0.05, "glow": 1.0},
    ]


def apply(spec: RenderSpec) -> RenderSpec:
    """Mutate ``spec`` in place with synthwave styling and return it."""
    spec.metadata = {
        **spec.metadata,
        "preset": "synthwave",
        "motion_style": "grid_rush",
        "tempo_target_bpm": (120, 160),
        "contrast": "very_high",
        "grain": 0.15,
        "vignette": 0.3,
        "particle_density": 0.6,
        "glow_intensity": 0.85,
        "chromatic_aberration": 0.25,
        "retro": True,
    }
    spec.palette = list(SYNTHWAVE_PALETTE)
    spec.layers = _layers()
    spec.keyframes = _keyframes()
    spec.timeline = [
        *spec.timeline,
        {
            "time": 0.0,
            "type": "section",
            "data": {"name": "drive", "mood": "charged"},
        },
        {
            "time": 8.0,
            "type": "section",
            "data": {"name": "chorus", "mood": "euphoric"},
        },
        {
            "time": 20.0,
            "type": "section",
            "data": {"name": "breakdown", "mood": "electric"},
        },
    ]
    enriched = enrich_render_spec_for_web(spec, preset_name="synthwave")
    return RenderSpec.model_validate(enriched)
