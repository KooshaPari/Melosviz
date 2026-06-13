"""EDM preset: high-saturation neon palette with fast, punchy motion."""

from __future__ import annotations

from typing import Any, Dict, List

from ..analysis.models import RenderSpec


EDM_PALETTE: List[str] = [
    "#05010F",  # deep void
    "#1A0044",  # indigo core
    "#FF2D95",  # hot pink
    "#00E5FF",  # electric cyan
    "#FFB347",  # warm strobe
    "#FFFFFF",  # white flash
]


def _layers() -> List[Dict[str, Any]]:
    return [
        {
            "name": "kick_pulse",
            "type": "pulse",
            "intensity": 1.0,
            "swing_ms": 60,
            "blend": "additive",
        },
        {
            "name": "spectrum_bars",
            "type": "spectrum",
            "bins": 64,
            "drift": "vertical",
            "size_curve": "hard_step",
        },
        {
            "name": "laser_grid",
            "type": "shape",
            "geometry": "grid",
            "weight": 1.2,
        },
    ]


def _keyframes() -> List[Dict[str, Any]]:
    return [
        {"time": 0.0, "zoom": 1.0, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.9},
        {"time": 0.5, "zoom": 1.15, "pan_x": 0.0, "pan_y": 0.0, "glow": 1.0},
        {"time": 1.0, "zoom": 1.0, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.9},
        {"time": 8.0, "zoom": 1.25, "pan_x": 0.05, "pan_y": 0.02, "glow": 1.0},
    ]


def apply(spec: RenderSpec) -> RenderSpec:
    """Mutate ``spec`` in place with EDM styling and return it."""
    spec.metadata = {
        **spec.metadata,
        "preset": "edm",
        "motion_style": "four_on_the_floor",
        "tempo_target_bpm": (120, 160),
        "contrast": "very_high",
        "grain": 0.0,
        "vignette": 0.0,
        "particle_density": 0.95,
    }
    spec.palette = list(EDM_PALETTE)
    spec.layers = _layers()
    spec.keyframes = _keyframes()
    spec.timeline = [
        *spec.timeline,
        {"time": 0.0, "type": "section", "data": {"name": "build", "mood": "anticipation"}},
        {"time": 8.0, "type": "section", "data": {"name": "drop", "mood": "explosive"}},
        {"time": 32.0, "type": "section", "data": {"name": "breakdown", "mood": "lush"}},
    ]
    return spec
