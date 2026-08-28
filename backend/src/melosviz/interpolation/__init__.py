"""Interpolation engine — fluid scene-to-scene cuts via RIFE / FILM / FlowMatching + ffmpeg minterpolate fallback."""
from .engine import (
    INTERPOLATION_PRIORITY,
    InterpolationBackend,
    InterpolationEngine,
    InterpolationMethod,
    InterpolationSchedule,
    ScenePair,
    build_interpolation_bridge_for_assemble,
    build_interpolation_schedule,
    detect_backend,
    interpolate_pair,
    list_backends,
)

__all__ = [
    "INTERPOLATION_PRIORITY",
    "InterpolationBackend",
    "InterpolationEngine",
    "InterpolationMethod",
    "InterpolationSchedule",
    "ScenePair",
    "build_interpolation_bridge_for_assemble",
    "build_interpolation_schedule",
    "detect_backend",
    "interpolate_pair",
    "list_backends",
]
