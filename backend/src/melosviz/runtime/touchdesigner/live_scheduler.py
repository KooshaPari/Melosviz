"""Live beat-phase prediction and scene-change scheduler for TouchDesigner.

This module is **spec-level** — it generates a structured TD network spec
(plain dicts, JSON-serialisable) describing the operators and Python callbacks
needed to drive low-latency live sync.  No TouchDesigner runtime is required
to generate or test the spec.

Overview
--------
Beat-phase prediction
~~~~~~~~~~~~~~~~~~~~~
The scheduler maintains a running phase estimate::

    phase(t) = ((t - t_last_beat) * bpm / 60.0) % 1.0

Because audio clock → TD Python callback latency is ~5–20 ms, the bridge
applies a configurable ``lookahead_ms`` offset so scene changes are dispatched
slightly *before* the beat, arriving at the TD network on-beat.

Scene-change scheduling
~~~~~~~~~~~~~~~~~~~~~~~
The composer plan (from :func:`~melosviz.compose.assemble.assemble_render_plan`)
provides a list of ``transitions`` (beat-aligned timestamps).  The scheduler
converts these into a priority queue of upcoming scene-change events.  At each
OSC/WS tick it pops events whose predicted beat-phase arrival (adjusted for
lookahead) is ≤ the current wall-clock time, and emits an OSC ``/scene/change``
message carrying the next segment's ``scene_type``, ``material``, and
``camera_language``.

Arc-aware scheduling
~~~~~~~~~~~~~~~~~~~~
The scheduler tags each ``/scene/change`` with the intensity value from the
composer plan.  The TD Python DAT can consume this to modulate visual
complexity in real time (e.g. drive opacity, particle count, camera shake
amplitude) while staying faithful to the composed arc.

Generated spec shape (top-level keys)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
::

    {
        "version": "live_scheduler/1.0",
        "bpm": <float>,
        "lookahead_ms": <float>,
        "scene_change_events": [
            {
                "beat_time": <float>,       # absolute seconds
                "dispatch_time": <float>,   # beat_time - lookahead
                "scene_type": "<str>",
                "material": "<str>",
                "camera_language": "<str>",
                "intensity": <float>,
                "osc_address": "/scene/change",
                "osc_args": [<scene_type>, <material>, <camera_language>, <intensity>]
            },
            ...
        ],
        "td_network_patch": {
            "operators": [...],
            "python_callbacks": {...}
        }
    }
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "LiveScheduler",
    "build_live_scheduler_spec",
    "DEFAULT_LOOKAHEAD_MS",
]

#: Default lookahead in milliseconds — compensates for OSC → TD latency.
DEFAULT_LOOKAHEAD_MS: float = 30.0


class LiveScheduler:
    """Build a TD live-scheduler spec from a composer plan + BPM.

    Args:
        bpm: Tempo in beats-per-minute.
        lookahead_ms: How many milliseconds before a beat to dispatch the
            scene-change message.
        osc_address: OSC address for scene-change messages.
    """

    def __init__(
        self,
        bpm: float,
        lookahead_ms: float = DEFAULT_LOOKAHEAD_MS,
        osc_address: str = "/scene/change",
    ) -> None:
        if bpm <= 0:
            raise ValueError(f"bpm must be positive; got {bpm}")
        self._bpm = float(bpm)
        self._lookahead_s = float(lookahead_ms) / 1000.0
        self._osc_address = osc_address

    def build_spec(self, assembly_plan: dict[str, Any]) -> dict[str, Any]:
        """Generate the live-scheduler spec from an assembly plan.

        Args:
            assembly_plan: Dict returned by
                :func:`~melosviz.compose.assemble.assemble_render_plan`.

        Returns:
            Structured spec dict (see module docstring for shape).
        """
        transitions: list[float] = list(assembly_plan.get("transitions") or [])
        segments: list[dict[str, Any]] = list(assembly_plan.get("segments") or [])

        # Build a map: beat_time → segment
        seg_by_start: dict[float, dict[str, Any]] = {}
        for seg in segments:
            key = float(seg.get("beat_aligned_start", seg.get("start", 0.0)))
            seg_by_start[key] = seg

        # Build scene-change events for each transition (2nd segment onwards)
        scene_change_events: list[dict[str, Any]] = []
        for beat_time in transitions:
            seg = seg_by_start.get(beat_time)
            if seg is None:
                # Fuzzy match — find nearest segment start
                if seg_by_start:
                    closest = min(
                        seg_by_start.keys(),
                        key=lambda t: abs(t - beat_time),
                    )
                    seg = seg_by_start[closest]
                else:
                    continue

            scene_type = str(seg.get("scene_type", "video_export"))
            material = str(seg.get("material", "neon_glow"))
            camera = str(seg.get("camera_language", "steady_cam"))
            intensity = float(seg.get("intensity", 0.5))
            dispatch_time = max(0.0, beat_time - self._lookahead_s)

            scene_change_events.append(
                {
                    "beat_time": round(beat_time, 4),
                    "dispatch_time": round(dispatch_time, 4),
                    "scene_type": scene_type,
                    "material": material,
                    "camera_language": camera,
                    "intensity": round(intensity, 4),
                    "osc_address": self._osc_address,
                    "osc_args": [scene_type, material, camera, round(intensity, 4)],
                }
            )

        td_patch = self._build_td_network_patch(scene_change_events)

        spec: dict[str, Any] = {
            "version": "live_scheduler/1.0",
            "bpm": self._bpm,
            "lookahead_ms": self._lookahead_s * 1000.0,
            "scene_change_events": scene_change_events,
            "td_network_patch": td_patch,
        }
        logger.info(
            "LiveScheduler.build_spec: %d scene-change events, bpm=%.1f, lookahead=%.0fms",
            len(scene_change_events),
            self._bpm,
            self._lookahead_s * 1000.0,
        )
        return spec

    def predict_phase(self, t_now: float, t_last_beat: float) -> float:
        """Return the current beat phase in [0, 1).

        Args:
            t_now: Wall-clock time in seconds.
            t_last_beat: Time of the most recent confirmed beat in seconds.

        Returns:
            Phase in [0, 1) — 0.0 = on-beat, 0.99 ≈ just before next beat.
        """
        if t_now < t_last_beat:
            return 0.0
        beat_duration = 60.0 / self._bpm
        phase = ((t_now - t_last_beat) / beat_duration) % 1.0
        return phase

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_td_network_patch(
        self, events: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Return a minimal TD network patch spec for the scene scheduler."""
        return {
            "operators": [
                {
                    "op_type": "oscoutDAT",
                    "name": "scene_change_out",
                    "params": {"network_address": "127.0.0.1", "port": 7001},
                    "comment": "Sends /scene/change to TD scene router",
                },
                {
                    "op_type": "scriptDAT",
                    "name": "scene_scheduler",
                    "params": {},
                    "comment": (
                        "Python callback: pops scene_change_events on each cook, "
                        "dispatches OSC when wall_clock >= dispatch_time"
                    ),
                },
                {
                    "op_type": "tableDAT",
                    "name": "scene_event_table",
                    "params": {
                        "rows": len(events),
                        "columns": 7,
                        "header": [
                            "beat_time",
                            "dispatch_time",
                            "scene_type",
                            "material",
                            "camera_language",
                            "intensity",
                            "osc_address",
                        ],
                    },
                    "comment": "Pre-loaded from composer plan; consumed by scene_scheduler",
                },
            ],
            "python_callbacks": {
                "scene_scheduler.onCook": (
                    "# Beat-phase prediction + scene-change dispatch\n"
                    "import time\n"
                    "t = time.monotonic()\n"
                    "tbl = op('scene_event_table')\n"
                    "out = op('scene_change_out')\n"
                    "for row in range(1, tbl.numRows):\n"
                    "    dispatch_t = float(tbl[row, 'dispatch_time'])\n"
                    "    if t >= dispatch_t:\n"
                    "        out.sendOSC(\n"
                    "            tbl[row, 'osc_address'].val,\n"
                    "            [tbl[row, 'scene_type'].val,\n"
                    "             tbl[row, 'material'].val,\n"
                    "             tbl[row, 'camera_language'].val,\n"
                    "             float(tbl[row, 'intensity'])]\n"
                    "        )\n"
                ),
            },
        }


def build_live_scheduler_spec(
    assembly_plan: dict[str, Any],
    *,
    bpm: float | None = None,
    lookahead_ms: float = DEFAULT_LOOKAHEAD_MS,
) -> dict[str, Any]:
    """Convenience wrapper: build a live-scheduler spec from an assembly plan.

    Args:
        assembly_plan: Output of
            :func:`~melosviz.compose.assemble.assemble_render_plan`.
        bpm: Override BPM.  When None, reads from ``assembly_plan`` metadata
            or defaults to 120.
        lookahead_ms: Lookahead in milliseconds.

    Returns:
        Live-scheduler spec dict.
    """
    resolved_bpm: float
    if bpm is not None:
        resolved_bpm = float(bpm)
    else:
        # Try to read from plan metadata
        mir = assembly_plan.get("mir") or {}
        resolved_bpm = float(mir.get("tempo_bpm") or 120.0)

    scheduler = LiveScheduler(bpm=resolved_bpm, lookahead_ms=lookahead_ms)
    return scheduler.build_spec(assembly_plan)
