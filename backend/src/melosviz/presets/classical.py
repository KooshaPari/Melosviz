"""Classical preset: formal, symmetrical palette with sweeping orchestral motion."""

from __future__ import annotations

from typing import Any, Dict, List

from ..analysis.models import RenderSpec


CLASSICAL_PALETTE: List[str] = [
    "#0A0F1F",  # midnight blue
    "#1A2A4F",  # royal navy
    "#3E5C8A",  # dusk
    "#B5A268",  # gilded gold
    "#E8D8A4",  # parchment
    "#F6EFD9",  # ivory
]


def _layers() -> List[Dict[str, Any]]:
    return [
        {
            "name": "concert_hall_curtain",
            "type": "gradient",
            "intensity": 0.4,
            "swing_ms": 1200,
            "blend": "multiply",
        },
        {
            "name": "string_section_flow",
            "type": "particles",
            "count": 96,
            "drift": "radial_outward",
            "size_curve": "crescendo",
        },
        {
            "name": "fugue_lines",
            "type": "shape",
            "geometry": "bezier",
            "weight": 0.5,
        },
    ]


def _keyframes() -> List[Dict[str, Any]]:
    return [
        {"time": 0.0, "zoom": 0.7, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.3},
        {"time": 10.0, "zoom": 0.85, "pan_x": 0.0, "pan_y": -0.05, "glow": 0.5},
        {"time": 30.0, "zoom": 1.1, "pan_x": 0.02, "pan_y": 0.0, "glow": 0.8},
        {"time": 60.0, "zoom": 1.0, "pan_x": -0.02, "pan_y": 0.02, "glow": 0.6},
    ]


def apply(spec: RenderSpec) -> RenderSpec:
    """Mutate ``spec`` in place with classical styling and return it."""
    spec.metadata = {
        **spec.metadata,
        "preset": "classical",
        "motion_style": "sweeping_orchestral",
        "tempo_target_bpm": (60, 120),
        "contrast": "medium",
        "grain": 0.15,
        "vignette": 0.25,
        "particle_density": 0.55,
    }
    spec.palette = list(CLASSICAL_PALETTE)
    spec.layers = _layers()
    spec.keyframes = _keyframes()
    spec.timeline = [
        *spec.timeline,
        {"time": 0.0, "type": "section", "data": {"name": "overture", "mood": "grand"}},
        {"time": 18.0, "type": "section", "data": {"name": "adagio", "mood": "tender"}},
        {"time": 45.0, "type": "section", "data": {"name": "allegro", "mood": "driving"}},
    ]
    return spec
