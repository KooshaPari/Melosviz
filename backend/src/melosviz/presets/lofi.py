"""Lo-fi hip hop preset: warm, vintage aesthetic with slow BPM cues.

Designed for lo-fi hip hop, chill beats, and relaxed study music: warm
browns and oranges reminiscent of cassette tape aesthetics, vintage film
grain, and slow deliberate motion. Evokes dusty record players, late-night
rain, and cozy solitude.
"""

from __future__ import annotations

from typing import Any

from ..analysis.models import RenderSpec
from ..compose.web_spec import enrich_render_spec_for_web

LOFI_PALETTE: list[str] = [
    "#1A1008",  # near-black warm brown
    "#3D2B1F",  # dark espresso
    "#7A4F2E",  # warm saddle brown
    "#C48A3F",  # golden amber
    "#E8C07D",  # soft butter yellow
    "#F5E6C8",  # cream highlight
]


def _layers() -> list[dict[str, Any]]:
    return [
        {
            "name": "film_grain",
            "type": "texture",
            "pattern": "grain",
            "intensity": 0.6,
            "blend": "overlay",
        },
        {
            "name": "vhs_blur",
            "type": "blur",
            "radius": 1.8,
            "blend": "soft_light",
        },
        {
            "name": "vinyl_glow",
            "type": "gradient",
            "intensity": 0.4,
            "swing_ms": 4800,
            "blend": "multiply",
        },
        {
            "name": "dust_particles",
            "type": "particles",
            "count": 18,
            "drift": "slow_float",
            "size_curve": "gentle_pulse",
        },
    ]


def _keyframes() -> list[dict[str, Any]]:
    return [
        {"time": 0.0, "zoom": 1.0, "pan_x": 0.0, "pan_y": 0.0, "glow": 0.2},
        {"time": 8.0, "zoom": 1.02, "pan_x": 0.01, "pan_y": -0.01, "glow": 0.3},
        {"time": 20.0, "zoom": 1.01, "pan_x": -0.01, "pan_y": 0.0, "glow": 0.35},
        {"time": 36.0, "zoom": 1.0, "pan_x": 0.0, "pan_y": 0.01, "glow": 0.25},
    ]


def apply(spec: RenderSpec) -> RenderSpec:
    """Mutate ``spec`` in place with lo-fi styling and return it."""
    spec.metadata = {
        **spec.metadata,
        "preset": "lofi",
        "motion_style": "gentle_drift",
        "tempo_target_bpm": (60, 90),
        "contrast": "low",
        "grain": 0.65,
        "vignette": 0.5,
        "particle_density": 0.2,
        "saturation": 0.7,
        "warmth": 0.8,
        "vintage": True,
    }
    spec.palette = list(LOFI_PALETTE)
    spec.layers = _layers()
    spec.keyframes = _keyframes()
    spec.timeline = [
        *spec.timeline,
        {
            "time": 0.0,
            "type": "section",
            "data": {"name": "intro", "mood": "nostalgic"},
        },
        {"time": 12.0, "type": "section", "data": {"name": "groove", "mood": "mellow"}},
        {"time": 28.0, "type": "section", "data": {"name": "outro", "mood": "wistful"}},
    ]
    enriched = enrich_render_spec_for_web(spec, preset_name="lofi")
    return RenderSpec.model_validate(enriched)
