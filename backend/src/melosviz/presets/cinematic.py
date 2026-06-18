"""Cinematic preset: letterbox teal-orange palette with dramatic, film-like motion.

Designed for film-score, trailer, and orchestrated-cue material: sweeping
strings, percussion hits, risers, and dramatic low-frequency builds. The
visual language mirrors the "blockbuster color grade" with strong contrast
between cool shadows and warm highlights, slow dolly-zoom camera motion,
and a 2.39:1 letterbox mask.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..analysis.models import RenderSpec


CINEMATIC_PALETTE: List[str] = [
    "#0A0F1A",  # deep blue-black shadow
    "#13344D",  # teal shadow
    "#1F6F8B",  # cyan
    "#C45A1A",  # burnt orange
    "#E89B3C",  # sodium highlight
    "#F5E1B3",  # warm light
]


def _layers() -> List[Dict[str, Any]]:
    return [
        {
            "name": "letterbox_mask",
            "type": "shape",
            "geometry": "letterbox",
            "aspect": 2.39,
            "weight": 1.0,
        },
        {
            "name": "ramp_glow",
            "type": "gradient",
            "intensity": 0.85,
            "swing_ms": 2400,
            "blend": "screen",
        },
        {
            "name": "riser_particles",
            "type": "particles",
            "count": 24,
            "drift": "riser",
            "size_curve": "linear_build",
        },
        {
            "name": "score_arc",
            "type": "shape",
            "geometry": "arc",
            "weight": 0.9,
        },
    ]


def _keyframes() -> List[Dict[str, Any]]:
    return [
        {"time": 0.0, "zoom": 1.0, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.3},
        {"time": 6.0, "zoom": 1.04, "pan_x": -0.03, "pan_y": 0.0, "glow": 0.45},
        {"time": 18.0, "zoom": 1.0, "pan_x": 0.0, "pan_y": -0.02, "glow": 0.7},
        {"time": 32.0, "zoom": 0.96, "pan_x": 0.04, "pan_y": 0.0, "glow": 0.85},
    ]


def apply(spec: RenderSpec) -> RenderSpec:
    """Mutate ``spec`` in place with cinematic styling and return it."""
    spec.metadata = {
        **spec.metadata,
        "preset": "cinematic",
        "motion_style": "dolly_dramatic",
        "tempo_target_bpm": (60, 120),
        "contrast": "high",
        "grain": 0.4,
        "vignette": 0.6,
        "particle_density": 0.35,
        "aspect_ratio": 2.39,
        "letterbox": True,
    }
    spec.palette = list(CINEMATIC_PALETTE)
    spec.layers = _layers()
    spec.keyframes = _keyframes()
    spec.timeline = [
        *spec.timeline,
        {"time": 0.0, "type": "section", "data": {"name": "establishing", "mood": "ominous"}},
        {"time": 10.0, "type": "section", "data": {"name": "build", "mood": "tension"}},
        {"time": 26.0, "type": "section", "data": {"name": "climax", "mood": "impact"}},
    ]
    return spec
