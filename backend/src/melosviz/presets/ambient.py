"""Ambient preset: cool, drifting palette with slow evolving motion."""

from __future__ import annotations

from typing import Any, Dict, List

from ..analysis.models import RenderSpec


AMBIENT_PALETTE: List[str] = [
    "#02060F",  # midnight black
    "#042D31",  # deep teal
    "#05384A",  # slate teal
    "#4C2A85",  # distant violet
    "#A39BFF",  # lavender mist
    "#E6F0FF",  # pale dawn
]


def _layers() -> List[Dict[str, Any]]:
    return [
        {
            "name": "field_horizon",
            "type": "gradient",
            "intensity": 0.3,
            "swing_ms": 8000,
            "blend": "soft_light",
        },
        {
            "name": "drifting_motes",
            "type": "particles",
            "count": 64,
            "drift": "noise_field",
            "size_curve": "breathing",
        },
        {
            "name": "soft_halo",
            "type": "shape",
            "geometry": "radial_blob",
            "weight": 0.4,
        },
    ]


def _keyframes() -> List[Dict[str, Any]]:
    return [
        {"time": 0.0, "zoom": 0.7, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.2},
        {"time": 15.0, "zoom": 0.78, "pan_x": 0.03, "pan_y": 0.0, "glow": 0.3},
        {"time": 45.0, "zoom": 0.85, "pan_x": -0.03, "pan_y": 0.02, "glow": 0.35},
        {"time": 90.0, "zoom": 0.8, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.3},
    ]


def apply(spec: RenderSpec) -> RenderSpec:
    """Mutate ``spec`` in place with ambient styling and return it."""
    spec.metadata = {
        **spec.metadata,
        "preset": "ambient",
        "motion_style": "slow_evolution",
        "tempo_target_bpm": (40, 90),
        "contrast": "low",
        "grain": 0.2,
        "vignette": 0.3,
        "particle_density": 0.30,
    }
    spec.palette = list(AMBIENT_PALETTE)
    spec.layers = _layers()
    spec.keyframes = _keyframes()
    spec.timeline = [
        *spec.timeline,
        {"time": 0.0, "type": "section", "data": {"name": "dusk", "mood": "hushed"}},
        {"time": 30.0, "type": "section", "data": {"name": "drift", "mood": "weightless"}},
        {"time": 75.0, "type": "section", "data": {"name": "resolve", "mood": "stillness"}},
    ]
    return spec
