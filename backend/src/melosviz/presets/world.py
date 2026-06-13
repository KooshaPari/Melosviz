"""World preset: warm earthen palette with hand-drummed, polyrhythmic motion.

Designed for global / folkloric material: marimba, djembe, mbira, bansuri,
oud, sitar and vocal-driven world fusion. The motion is gestural and
hand-played rather than grid-quantised.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..analysis.models import RenderSpec


WORLD_PALETTE: List[str] = [
    "#2A0E04",  # terracotta shadow
    "#7A2A0E",  # kiln-fired clay
    "#C46A1F",  # saffron
    "#E8B341",  # turmeric
    "#5A6B2E",  # moss
    "#A6C18A",  # palm frond
    "#3B5A6E",  # monsoon sky
    "#E5DCC4",  # raw linen
]


def _layers() -> List[Dict[str, Any]]:
    return [
        {
            "name": "sun_baked_gradient",
            "type": "gradient",
            "intensity": 0.55,
            "swing_ms": 1800,
            "blend": "soft_light",
        },
        {
            "name": "hand_drum_particles",
            "type": "particles",
            "count": 56,
            "drift": "polyrhythmic",
            "size_curve": "earthen_pulse",
        },
        {
            "name": "woven_geometry",
            "type": "shape",
            "geometry": "tessellation",
            "weight": 0.7,
        },
        {
            "name": "wind_ribbon",
            "type": "shape",
            "geometry": "ribbon_path",
            "weight": 0.45,
        },
    ]


def _keyframes() -> List[Dict[str, Any]]:
    return [
        {"time": 0.0, "zoom": 0.9, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.35},
        {"time": 6.0, "zoom": 1.0, "pan_x": -0.04, "pan_y": 0.02, "glow": 0.5},
        {"time": 22.0, "zoom": 1.05, "pan_x": 0.05, "pan_y": -0.03, "glow": 0.65},
        {"time": 48.0, "zoom": 0.95, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.45},
    ]


def apply(spec: RenderSpec) -> RenderSpec:
    """Mutate ``spec`` in place with world-music styling and return it."""
    spec.metadata = {
        **spec.metadata,
        "preset": "world",
        "motion_style": "polyrhythmic_gesture",
        "tempo_target_bpm": (70, 140),
        "contrast": "warm",
        "grain": 0.25,
        "vignette": 0.3,
        "particle_density": 0.45,
    }
    spec.palette = list(WORLD_PALETTE)
    spec.layers = _layers()
    spec.keyframes = _keyframes()
    spec.timeline = [
        *spec.timeline,
        {"time": 0.0, "type": "section", "data": {"name": "call", "mood": "invitation"}},
        {"time": 12.0, "type": "section", "data": {"name": "drone", "mood": "grounded"}},
        {"time": 32.0, "type": "section", "data": {"name": "circle", "mood": "communal"}},
    ]
    return spec
