"""Jazz preset: warm low-light club palette with smoky, syncopated motion."""

from __future__ import annotations

from typing import Any, Dict, List

from ..analysis.models import RenderSpec


JAZZ_PALETTE: List[str] = [
    "#1A0E08",  # deep walnut shadow
    "#3B1F0F",  # smoky amber
    "#8C5A2B",  # brass
    "#D4A24C",  # warm spotlight
    "#F2D399",  # candle glow
    "#FFE9C4",  # ivory highlight
]


def _layers() -> List[Dict[str, Any]]:
    return [
        {
            "name": "stage_lighting",
            "type": "gradient",
            "intensity": 0.65,
            "swing_ms": 480,
            "blend": "screen",
        },
        {
            "name": "brass_orbs",
            "type": "particles",
            "count": 32,
            "drift": "lateral",
            "size_curve": "soft_swell",
        },
        {
            "name": "saxophone_silhouette",
            "type": "shape",
            "geometry": "spline",
            "weight": 0.8,
        },
    ]


def _keyframes() -> List[Dict[str, Any]]:
    return [
        {"time": 0.0, "zoom": 0.85, "pan_x": -0.05, "pan_y": 0.0, "glow": 0.4},
        {"time": 4.0, "zoom": 0.92, "pan_x": 0.05, "pan_y": -0.02, "glow": 0.55},
        {"time": 12.0, "zoom": 1.0, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.7},
        {"time": 20.0, "zoom": 0.95, "pan_x": 0.04, "pan_y": 0.02, "glow": 0.6},
    ]


def apply(spec: RenderSpec) -> RenderSpec:
    """Mutate ``spec`` in place with jazz styling and return it."""
    spec.metadata = {
        **spec.metadata,
        "preset": "jazz",
        "motion_style": "syncopated_sway",
        "tempo_target_bpm": (90, 140),
        "contrast": "low",
        "grain": 0.35,
        "vignette": 0.55,
        "particle_density": 0.25,
    }
    spec.palette = list(JAZZ_PALETTE)
    spec.layers = _layers()
    spec.keyframes = _keyframes()
    spec.timeline = [
        *spec.timeline,
        {"time": 0.0, "type": "section", "data": {"name": "intro", "mood": "hushed"}},
        {"time": 8.0, "type": "section", "data": {"name": "head", "mood": "walking_bass"}},
        {"time": 24.0, "type": "section", "data": {"name": "solo", "mood": "improvised"}},
    ]
    return spec
