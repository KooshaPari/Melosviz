"""Scanner evaluator — pure Python, renderer-agnostic.

Given a :class:`~melosviz.scene.models.ScannerSpec` and a time ``t`` plus a
RenderSpec v2 timeline (beats / bpm), this module computes:

1. The scanner's **pose** at time ``t`` — its orbit angle (BPM-locked) and
   any noise/pulse modulation applied to it.
2. The **write-channel mask VALUES** — per-channel float in [0, 1] produced
   by the scanner at that instant.

These outputs are renderer-agnostic: they can feed the Blender adapter, a
TouchDesigner bridge, or a pure-Python preview.

Math
----

BPM-locked orbit angle
~~~~~~~~~~~~~~~~~~~~~~
Given:
  - ``bpm``        — beats per minute (from RenderSpec metadata)
  - ``bpr``        — beats per rotation (ScannerSpec.rotation.beats_per_rotation)
  - ``phase_offset`` — fraction of one rotation, in [0, 1)
  - ``t``          — time in seconds

::

    seconds_per_beat    = 60.0 / bpm
    seconds_per_rotation = bpr * seconds_per_beat
    raw_phase            = (t / seconds_per_rotation) % 1.0
    orbit_angle_rad      = (raw_phase + phase_offset) % 1.0 * 2π

Write-channel values
~~~~~~~~~~~~~~~~~~~~
Each write channel is computed from the orbit angle and beat-proximity:

``reveal_splat``   — how strongly the scanner cone hits the current point.
    For a rotating-cone scanner pointing from angle 0, the "fullness" of
    the cone at a virtual sample point directly ahead decays with angular
    distance from the scanner axis.  Here we use a simplified single-point
    model (no spatial 3D grid) and compute the *global cone influence* as a
    function of how close the current orbit phase is to a reference direction:

    ::

        angular_dist = min(orbit_angle % 2π, 2π - orbit_angle % 2π) / π
        cone_half_rad = cone_angle_deg / 2 * π/180
        cone_influence = falloff(1.0 - angular_dist * π / cone_half_rad)

    clamped to [0, 1].

``hide_photo``     — complement of reveal_splat (1 - reveal_splat).

``boost_wireframe`` — triggered near beat boundaries:
    ::

        beat_proximity = max(0, 1 - dist_to_nearest_beat / (seconds_per_beat * 0.25))
        boost_wireframe = beat_proximity * (1 + beat_pulse_gain * reveal_splat)

``edge_emission``  — edge energy = cone influence × beat proximity × gain.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from melosviz.scene.models import FalloffType, ScannerSpec, ScannerType


# ---------------------------------------------------------------------------
# Output data types
# ---------------------------------------------------------------------------


@dataclass
class ScannerPose:
    """Scanner pose at a single instant in time.

    Attributes:
        t: Time in seconds.
        orbit_angle_rad: Current orbit angle (0 → 2π).
        orbit_phase: Fractional position within one rotation (0 → 1).
        beat_proximity: How close ``t`` is to the nearest beat (0 = far, 1 = on-beat).
        active_channels: Snapshot of write-channel values (channel → float in [0, 1]).
    """

    t: float
    orbit_angle_rad: float
    orbit_phase: float
    beat_proximity: float
    active_channels: dict[str, float] = field(default_factory=dict)


@dataclass
class ChannelMaskFrame:
    """A per-keyframe mask track entry — the scanner's channel output at one time step.

    One of these is produced for each dense-keyframe ``t`` in the RenderSpec.
    """

    t: float
    channels: dict[str, float]  # channel_name → value in [0, 1]


# ---------------------------------------------------------------------------
# Falloff helpers
# ---------------------------------------------------------------------------

_TWO_PI = 2.0 * math.pi


def _falloff(x: float, kind: FalloffType) -> float:
    """Apply a falloff curve to ``x`` in [0, 1] → [0, 1].

    x = 1.0 means the scanner is pointing directly at the sample point.
    x = 0.0 means the sample point is at the edge of the cone.
    """
    x = max(0.0, min(1.0, x))
    if kind == FalloffType.LINEAR:
        return x
    if kind == FalloffType.SMOOTHSTEP:
        return x * x * (3.0 - 2.0 * x)
    if kind == FalloffType.COSINE:
        return (1.0 - math.cos(x * math.pi)) * 0.5
    return x  # pragma: no cover — exhaustive enum


# ---------------------------------------------------------------------------
# Per-instant evaluation
# ---------------------------------------------------------------------------


def _compute_orbit_angle(
    t: float,
    bpm: float,
    beats_per_rotation: float,
    phase_offset: float,
) -> tuple[float, float]:
    """Return (orbit_angle_rad, orbit_phase) for time *t*.

    Args:
        t: Time in seconds.
        bpm: Beats per minute.
        beats_per_rotation: How many beats make one full rotation.
        phase_offset: Additional phase shift in [0, 1).

    Returns:
        Tuple of (orbit_angle_rad, orbit_phase).
    """
    if bpm <= 0.0 or beats_per_rotation <= 0.0:
        return (0.0, 0.0)
    seconds_per_beat = 60.0 / bpm
    seconds_per_rotation = beats_per_rotation * seconds_per_beat
    raw_phase = (t / seconds_per_rotation) % 1.0
    orbit_phase = (raw_phase + phase_offset) % 1.0
    orbit_angle_rad = orbit_phase * _TWO_PI
    return (orbit_angle_rad, orbit_phase)


def _nearest_beat_distance(t: float, beat_times: list[float]) -> float:
    """Return the time-distance to the nearest beat.  Returns ``t`` if no beats."""
    if not beat_times:
        return abs(t)
    # Binary-search-style linear scan over beats (lists are small in practice)
    # For performance on dense beat grids (>1000 beats) a bisect would be
    # better, but clarity wins here given MVP scope.
    lo = beat_times[0]
    hi = beat_times[-1]
    # Quick bounds check
    if t <= lo:
        return lo - t
    if t >= hi:
        return t - hi
    # Walk sorted list to find surrounding pair
    for i in range(len(beat_times) - 1):
        if beat_times[i] <= t <= beat_times[i + 1]:
            return min(t - beat_times[i], beat_times[i + 1] - t)
    return 0.0  # pragma: no cover


def evaluate_pose(
    scanner: ScannerSpec,
    t: float,
    bpm: float,
    beat_times: list[float],
) -> ScannerPose:
    """Evaluate the scanner at time *t* and return a :class:`ScannerPose`.

    This is the core physics of the disco-ball scanner:

    1. Compute orbit angle (BPM-locked).
    2. Compute cone influence (how strongly the scanner illuminates a
       canonical "sample point" at angle 0 — a simplification for the MVP
       that avoids a full spatial grid).
    3. Apply beat-proximity modulation.
    4. Emit write-channel values.

    Args:
        scanner: Scanner specification.
        t: Time in seconds.
        bpm: Beats per minute from the RenderSpec timeline.
        beat_times: Sorted list of beat timestamps in seconds.

    Returns:
        :class:`ScannerPose` with all write-channel values populated.
    """
    rot = scanner.rotation
    if rot.bpm_locked:
        orbit_angle_rad, orbit_phase = _compute_orbit_angle(
            t, bpm, rot.beats_per_rotation, rot.phase_offset
        )
    else:
        # Non-locked: constant angular velocity at 1 rotation/s
        orbit_angle_rad = (t * _TWO_PI) % _TWO_PI
        orbit_phase = orbit_angle_rad / _TWO_PI

    # ---- Cone influence at the canonical sample point (angle 0) ----------
    # Angular distance from scanner axis to sample point (wrap around 2π)
    angular_dist = min(orbit_angle_rad, _TWO_PI - orbit_angle_rad)
    cone_half_rad = math.radians(scanner.cone_angle_deg / 2.0)

    if cone_half_rad <= 0.0:
        cone_raw = 0.0
    else:
        # x = 1 when scanner points directly at sample, 0 at cone boundary
        x = 1.0 - (angular_dist / cone_half_rad)
        cone_raw = _falloff(x, scanner.falloff)

    # ---- Beat proximity modulation ---------------------------------------
    seconds_per_beat = 60.0 / bpm if bpm > 0 else 1.0
    beat_dist = _nearest_beat_distance(t, beat_times)
    # Window: within 25% of a beat duration counts as "near beat"
    beat_window = seconds_per_beat * 0.25
    beat_proximity = max(0.0, 1.0 - beat_dist / beat_window) if beat_window > 0 else 0.0

    # Apply edge-wobble noise (deterministic pseudo-noise based on t)
    if scanner.noise.edge_wobble > 0.0:
        wobble = math.sin(t * 37.13 + orbit_phase * 6.1) * scanner.noise.edge_wobble
        cone_raw = max(0.0, min(1.0, cone_raw + wobble * 0.5))

    # Beat pulse: the cone briefly brightens on beat hits
    pulse_boost = beat_proximity * scanner.noise.beat_pulse_gain
    reveal_splat = min(1.0, cone_raw + pulse_boost * cone_raw)

    # ---- Write channels --------------------------------------------------
    channels: dict[str, float] = {}
    if "reveal_splat" in scanner.write_channels:
        channels["reveal_splat"] = reveal_splat
    if "hide_photo" in scanner.write_channels:
        channels["hide_photo"] = reveal_splat  # photo hides where splat reveals
    if "boost_wireframe" in scanner.write_channels:
        # Wireframe blooms at beat transitions
        channels["boost_wireframe"] = min(
            1.0, beat_proximity * (1.0 + scanner.noise.beat_pulse_gain * reveal_splat)
        )
    if "edge_emission" in scanner.write_channels:
        channels["edge_emission"] = min(1.0, cone_raw * beat_proximity)

    # Emit any other declared channels as the raw cone influence
    for ch in scanner.write_channels:
        if ch not in channels:
            channels[ch] = cone_raw

    return ScannerPose(
        t=t,
        orbit_angle_rad=orbit_angle_rad,
        orbit_phase=orbit_phase,
        beat_proximity=beat_proximity,
        active_channels=channels,
    )


# ---------------------------------------------------------------------------
# Timeline evaluation (RenderSpec integration)
# ---------------------------------------------------------------------------


def evaluate_scanner(
    scanner: ScannerSpec,
    render_spec: Any,  # RenderSpec — typed via Any to avoid circular import
) -> list[ChannelMaskFrame]:
    """Evaluate the scanner over a full RenderSpec v2 timeline.

    Produces one :class:`ChannelMaskFrame` per dense keyframe ``t`` in the
    spec.  This is the primary entry point for the Blender adapter.

    If the spec has no dense keyframes, falls back to 30 fps sampling across
    the full duration.

    Args:
        scanner: Scanner specification.
        render_spec: RenderSpec v2 instance (pydantic model or dict).

    Returns:
        List of :class:`ChannelMaskFrame`, one per sampled time step.
    """
    # --- Extract bpm and beat timestamps from the spec --------------------
    if hasattr(render_spec, "metadata"):
        metadata: dict[str, Any] = render_spec.metadata or {}
    elif isinstance(render_spec, dict):
        metadata = render_spec.get("metadata", {})
    else:
        metadata = {}

    bpm: float = float(metadata.get("estimated_bpm", 120.0))
    duration: float = float(metadata.get("duration", 0.0))
    fps: int = int(metadata.get("fps", 30))

    # Beat timestamps from timeline_events
    if hasattr(render_spec, "timeline_events"):
        raw_events = render_spec.timeline_events or []
    elif isinstance(render_spec, dict):
        raw_events = render_spec.get("timeline_events", [])
    else:
        raw_events = []

    beat_times: list[float] = sorted(
        float(ev["t"] if isinstance(ev, dict) else ev.t)
        for ev in raw_events
        if (ev["type"] if isinstance(ev, dict) else ev.type) in ("beat", "downbeat")
    )

    # Dense keyframe timestamps
    if hasattr(render_spec, "dense_keyframes"):
        raw_kf = render_spec.dense_keyframes or []
    elif isinstance(render_spec, dict):
        raw_kf = render_spec.get("dense_keyframes", [])
    else:
        raw_kf = []

    if raw_kf:
        times = [
            float(kf["t"] if isinstance(kf, dict) else kf.t) for kf in raw_kf
        ]
    else:
        # Fallback: sample at fps over full duration
        if duration <= 0.0:
            return []
        n = max(1, int(duration * fps))
        times = [i / fps for i in range(n)]

    frames: list[ChannelMaskFrame] = []
    for t in times:
        pose = evaluate_pose(scanner, t, bpm, beat_times)
        frames.append(ChannelMaskFrame(t=t, channels=dict(pose.active_channels)))

    return frames
