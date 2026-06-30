"""Scene-type router — maps each SceneSegment to a renderer scene_type tag.

Routing table (ADR 0003):
  procedural_3d_animation   — high-energy drops, chorus, heavy drums stem
  motion_graphics_beat_sync — verse/bridge, moderate energy, beat-locked
  generative_asset          — intro/outro, low energy, ambient mood
  live_stage                — breakdown, bright, high arousal
  experimental_code_gen     — unknown/bridge with low brightness, edge cases

The router is pure-function: it takes a ``SceneSegment`` (or a plain dict
shaped like one) and returns one of the five ``SceneType`` literals.  No I/O,
no side effects.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class SceneType(str, Enum):
    """Canonical scene_type tags used by the conductor routing table."""

    PROCEDURAL_3D_ANIMATION = "procedural_3d_animation"
    MOTION_GRAPHICS_BEAT_SYNC = "motion_graphics_beat_sync"
    GENERATIVE_ASSET = "generative_asset"
    LIVE_STAGE = "live_stage"
    EXPERIMENTAL_CODE_GEN = "experimental_code_gen"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(segment: Any, field: str, default: Any = None) -> Any:
    """Attribute or dict key access; returns ``default`` on miss."""
    if isinstance(segment, dict):
        return segment.get(field, default)
    return getattr(segment, field, default)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def route_segment(segment: Any) -> SceneType:
    """Return the ``SceneType`` for a single ``SceneSegment`` (or dict).

    Decision tree (priority order):
    1. label in {intro, outro}  → generative_asset
    2. label == drop            → procedural_3d_animation (always high-energy)
    3. dominant_stem == drums AND energy_mean >= 0.55
                                → procedural_3d_animation
    4. label in {chorus}        → procedural_3d_animation (high-energy section)
    5. label == breakdown       → live_stage (bright + arousal is high)
    6. label in {verse, bridge, pre_chorus}
                                → motion_graphics_beat_sync
    7. label == unknown AND brightness_mean < 0.3
                                → experimental_code_gen
    8. fallback                 → motion_graphics_beat_sync
    """
    label: str = str(_get(segment, "label", "unknown")).lower()
    energy: float = float(_get(segment, "energy_mean", 0.0))
    dominant_stem: str = str(_get(segment, "dominant_stem", "other")).lower()
    brightness: float = float(_get(segment, "brightness_mean", 0.0))

    # Mood is either a MoodVector object or a dict
    mood_raw = _get(segment, "mood", {})
    if isinstance(mood_raw, dict):
        _arousal = float(mood_raw.get("arousal", 0.5))
    else:
        _arousal = float(getattr(mood_raw, "arousal", 0.5))

    if label in {"intro", "outro"}:
        return SceneType.GENERATIVE_ASSET

    if label == "drop":
        return SceneType.PROCEDURAL_3D_ANIMATION

    if dominant_stem == "drums" and energy >= 0.55:
        return SceneType.PROCEDURAL_3D_ANIMATION

    if label == "chorus":
        return SceneType.PROCEDURAL_3D_ANIMATION

    if label == "breakdown":
        return SceneType.LIVE_STAGE

    if label in {"verse", "bridge", "pre_chorus"}:
        return SceneType.MOTION_GRAPHICS_BEAT_SYNC

    if label == "unknown" and brightness < 0.3:
        return SceneType.EXPERIMENTAL_CODE_GEN

    return SceneType.MOTION_GRAPHICS_BEAT_SYNC


def route_spec(spec: Any) -> list[tuple[Any, SceneType]]:
    """Route every segment in a ``RenderSpec`` and return ``(segment, SceneType)`` pairs.

    ``spec`` may be a ``RenderSpec`` object or a plain dict.  The
    ``scene_segments`` field is expected to be a list of dicts or
    ``SceneSegment`` objects.
    """
    if isinstance(spec, dict):
        segments = spec.get("scene_segments", [])
    else:
        segments = getattr(spec, "scene_segments", [])

    return [(seg, route_segment(seg)) for seg in segments]
