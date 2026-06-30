"""Procedural camera choreography — P8 advanced scene.

Generates a camera path from a list of scene segments and optional RenderSpec
arc context.  Each segment maps to one or more :class:`CameraKeyframe` objects
whose ``camera_language`` is drawn from the four P7 quartile archetypes:

  - ``slow_reveal``   — wide pull-back, locked-off; low energy / intro.
  - ``steady_cam``    — gentle orbit; medium-low energy / verse / breakdown.
  - ``handheld_push`` — handheld push-in with FOV tighten; medium-high / build.
  - ``cut_frenzy``    — rapid Dutch/tilt cuts, extreme FOV; peak energy / drop.

The energy quartile boundary is computed across all segments' ``energy_mean``
values, then each segment is assigned the matching archetype.  Segments without
``energy_mean`` default to the mid-energy archetype (``steady_cam``).

Design
------
- Pure Python, no renderer import.
- Deterministic given the same segment list + seed.
- Positions and look-at targets are analytically derived from the segment index
  and archetype — no solver, no external deps.
- FOV varies per archetype within the valid range [10°, 120°].
- Output is a time-ordered list of :class:`CameraKeyframe` (one per segment
  boundary + one at t=0).

Usage::

    from melosviz.scene.camera import generate_camera_path

    path = generate_camera_path(segments, duration=120.0)
    for kf in path:
        print(kf.t, kf.camera_language, kf.fov_deg)
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "CameraKeyframe",
    "generate_camera_path",
    "CAMERA_LANGUAGE_MAP",
]

# ---------------------------------------------------------------------------
# Camera language vocabulary — 4 P7 quartile archetypes
# ---------------------------------------------------------------------------

#: Mapping of camera-language name → human-readable description.
CAMERA_LANGUAGE_MAP: dict[str, str] = {
    "slow_reveal": "Wide locked-off pull-back; minimal motion; low energy / intro.",
    "steady_cam": "Gentle orbit around subject; smooth; medium-low energy / verse.",
    "handheld_push": "Handheld push-in with FOV tighten; organic shake; build sections.",
    "cut_frenzy": "Rapid Dutch-angle / tilt cuts; extreme wide FOV; peak energy / drop.",
}

# ---------------------------------------------------------------------------
# Per-archetype camera parameters
# ---------------------------------------------------------------------------

_ARCHETYPE_PARAMS: dict[str, dict[str, Any]] = {
    "slow_reveal": {
        "fov_deg": 75.0,
        "radius": 9.0,     # distance from origin
        "height": 2.5,     # camera height
        "orbit_speed": 0.05,  # radians per second (very slow)
    },
    "steady_cam": {
        "fov_deg": 60.0,
        "radius": 7.0,
        "height": 1.8,
        "orbit_speed": 0.15,
    },
    "handheld_push": {
        "fov_deg": 45.0,
        "radius": 4.5,
        "height": 1.5,
        "orbit_speed": 0.3,
    },
    "cut_frenzy": {
        "fov_deg": 28.0,
        "radius": 2.5,
        "height": 1.2,
        "orbit_speed": 0.6,
    },
}

# ---------------------------------------------------------------------------
# CameraKeyframe data class
# ---------------------------------------------------------------------------


@dataclass
class CameraKeyframe:
    """A single camera pose keyframe on the procedural camera path.

    Attributes:
        t: Time in seconds.
        position: Camera world position as (x, y, z).
        look_at: World position the camera points toward as (x, y, z).
        fov_deg: Horizontal field-of-view in degrees [10, 120].
        camera_language: Archetype name from :data:`CAMERA_LANGUAGE_MAP`.
        roll_deg: Camera roll in degrees (Dutch-angle for cut_frenzy; else 0).
    """

    t: float
    position: tuple[float, float, float]
    look_at: tuple[float, float, float]
    fov_deg: float
    camera_language: str
    roll_deg: float = 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _quartile_breakpoints(values: list[float]) -> tuple[float, float, float]:
    """Return (q25, q50, q75) of *values*.  Falls back to (0.33, 0.5, 0.67) if empty."""
    if not values:
        return (0.33, 0.5, 0.67)
    s = sorted(values)
    n = len(s)

    def _pct(p: float) -> float:
        idx = p * (n - 1)
        lo, frac = int(idx), idx - int(idx)
        hi = min(lo + 1, n - 1)
        return s[lo] + frac * (s[hi] - s[lo])

    return (_pct(0.25), _pct(0.50), _pct(0.75))


def _energy_to_language(energy: float, q25: float, q50: float, q75: float) -> str:
    """Map an energy value to a camera-language archetype via quartile bucketing.

    When all quartile boundaries collapse to the same value (single-segment case),
    the archetype is determined by the absolute energy level rather than relative
    quartile position, so a high-energy drop always maps to an energetic language.
    """
    # Degenerate case: all quartiles equal → use absolute thresholds
    if q25 == q75:
        if energy >= 0.75:
            return "cut_frenzy"
        if energy >= 0.5:
            return "handheld_push"
        if energy >= 0.25:
            return "steady_cam"
        return "slow_reveal"

    if energy <= q25:
        return "slow_reveal"
    if energy <= q50:
        return "steady_cam"
    if energy <= q75:
        return "handheld_push"
    return "cut_frenzy"


def _camera_position(
    archetype: str,
    t: float,
    segment_index: int,
) -> tuple[float, float, float]:
    """Derive a camera position analytically for the given archetype at time *t*."""
    params = _ARCHETYPE_PARAMS[archetype]
    radius: float = params["radius"]
    height: float = params["height"]
    speed: float = params["orbit_speed"]

    # Phase offset per segment so consecutive segments don't start at the same angle
    phase_offset = segment_index * math.pi * 0.618  # golden-angle stepping

    angle = t * speed + phase_offset
    x = radius * math.cos(angle)
    y = radius * math.sin(angle)
    z = height

    # cut_frenzy: add a slight Dutch-angle push (camera dips slightly lower)
    if archetype == "cut_frenzy":
        z *= 0.85

    return (round(x, 4), round(y, 4), round(z, 4))


def _camera_roll(archetype: str, t: float) -> float:
    """Return a roll angle in degrees.  Only cut_frenzy uses non-zero roll."""
    if archetype != "cut_frenzy":
        return 0.0
    # Oscillate between ±8° at ~0.5 Hz
    return round(8.0 * math.sin(t * math.pi), 2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_camera_path(
    segments: Sequence[dict[str, Any]],
    duration: float,
    *,
    render_spec: Any = None,
    fps: int = 24,
) -> list[CameraKeyframe]:
    """Generate a procedural camera path from a list of scene segments.

    Each segment contributes at least one :class:`CameraKeyframe` at its start
    time.  A trailing keyframe is added at ``duration`` if it doesn't coincide
    with the last segment boundary.

    Energy quartiles are computed across all segments' ``energy_mean`` fields.
    Segments without ``energy_mean`` are assumed to have 0.5 (mid-energy).

    The look-at target is always the world origin (0, 0, 1.0) — the notional
    stage centre.  Renderers may override this via the scene spec.

    Args:
        segments: List of segment dicts, each with at minimum ``label``,
            ``start``, ``end``, and optionally ``energy_mean``,
            ``mood``, ``dominant_stem``.
        duration: Total clip duration in seconds.
        render_spec: Optional RenderSpec v2 instance (used for BPM context;
            not required for path generation itself).
        fps: Frames per second (informational; not used in this implementation).

    Returns:
        Time-ordered list of :class:`CameraKeyframe`, one per segment start
        plus a terminal keyframe at *duration*.
    """
    look_at = (0.0, 0.0, 1.0)  # notional stage centre

    # Gather energy values for quartile computation
    energies: list[float] = []
    for seg in segments:
        e = seg.get("energy_mean")
        if e is not None:
            energies.append(float(e))

    q25, q50, q75 = _quartile_breakpoints(energies)

    keyframes: list[CameraKeyframe] = []

    for idx, seg in enumerate(segments):
        t_start = float(seg.get("start", 0.0))
        energy = float(seg.get("energy_mean", 0.5))
        language = _energy_to_language(energy, q25, q50, q75)

        params = _ARCHETYPE_PARAMS[language]
        fov = float(params["fov_deg"])
        # Clamp FOV to valid range
        fov = max(10.0, min(120.0, fov))

        position = _camera_position(language, t_start, idx)
        roll = _camera_roll(language, t_start)

        keyframes.append(
            CameraKeyframe(
                t=t_start,
                position=position,
                look_at=look_at,
                fov_deg=fov,
                camera_language=language,
                roll_deg=roll,
            )
        )

    # Terminal keyframe at duration (use last segment's archetype if available)
    if keyframes:
        last_language = keyframes[-1].camera_language
        last_idx = len(segments)
        term_pos = _camera_position(last_language, duration, last_idx)
        term_fov = max(10.0, min(120.0, _ARCHETYPE_PARAMS[last_language]["fov_deg"]))
        if not keyframes or abs(keyframes[-1].t - duration) > 1e-3:
            keyframes.append(
                CameraKeyframe(
                    t=duration,
                    position=term_pos,
                    look_at=look_at,
                    fov_deg=term_fov,
                    camera_language=last_language,
                    roll_deg=_camera_roll(last_language, duration),
                )
            )

    # Ensure temporal order (should already be, but guard against caller mis-ordering)
    keyframes.sort(key=lambda kf: kf.t)

    return keyframes
