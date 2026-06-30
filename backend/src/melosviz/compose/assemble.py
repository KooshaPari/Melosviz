"""End-to-end music-video assembly pipeline.

Orchestrates the full render chain:

    analyze → RenderSpec v2 → NarrativeComposer (arc + variety)
    → Conductor (per-segment adapter dispatch, mock or real)
    → Media Encoder (assembly_encode) → single MP4 plan

This module is the "make it a movie, not a loop" integration point.
It also enforces flash-safety across the full assembled timeline.

Flash-safety contract (from P3/P4):
* The P3 ``apply_flash_safety`` function caps per-keyframe energy bursts to
  ≤ 3 Hz on individual segments.
* ``assemble_render_plan`` additionally checks that the *boundary* between
  adjacent segments does not create a cross-segment flash spike: consecutive
  end-energy / start-energy values must not both exceed the high-flash
  threshold (> 0.8) within the minimum inter-flash interval (1 / 3 Hz = 333 ms).

The assembled plan is a structured dict — not a binary file — so it is fully
testable without any render runtime installed.

Plan shape::

    {
        "version": "2.0",
        "total_duration": <float>,  # seconds
        "fps": <int>,
        "segment_count": <int>,
        "flash_safe": true,
        "segments": [
            {
                "index": <int>,
                "label": "<str>",
                "start": <float>,
                "end": <float>,
                "scene_type": "<str>",
                "material": "<str>",
                "camera_language": "<str>",
                "intensity": <float>,
                "beat_aligned_start": <float>,    # snapped to nearest beat
                "transition": "<str>",            # e.g. "crossfade_2f"
                "adapter_result": <any>           # from conductor / mock
            },
            ...
        ],
        "transitions": [<beat_time>, ...],        # beat-aligned cut points
        "composer_seed": <int>,
    }
"""

from __future__ import annotations

import logging
from typing import Any

from melosviz.analysis.models import RenderSpec

logger = logging.getLogger(__name__)

__all__ = [
    "assemble_render_plan",
    "AssemblyError",
    "FLASH_BOUNDARY_THRESHOLD",
    "FLASH_MIN_INTERVAL_S",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Per-frame energy above this value is considered a "flash frame".
FLASH_BOUNDARY_THRESHOLD: float = 0.8

#: Minimum seconds between consecutive flash frames (≈ 3 Hz ceiling).
FLASH_MIN_INTERVAL_S: float = 1.0 / 3.0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class AssemblyError(RuntimeError):
    """Raised when the assembly pipeline detects an unresolvable error."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assemble_render_plan(
    render_spec: RenderSpec,
    *,
    composer_seed: int = 0,
    fps: int = 30,
    mock_adapters: bool = True,
) -> dict[str, Any]:
    """Build a full music-video assembly plan from a RenderSpec v2.

    Steps
    -----
    1. Extract ``scene_segments`` and ``mir`` from *render_spec*.
    2. Run :class:`~melosviz.compose.narrator.NarrativeComposer` to assign
       varied scene_type / material / camera_language per segment.
    3. Snap each segment start to the nearest beat (beat-aligned transitions).
    4. Dispatch each segment through the conductor (mock by default) to
       collect per-segment adapter results.
    5. Enforce cross-segment flash-safety: if two adjacent segments both
       have energy > :data:`FLASH_BOUNDARY_THRESHOLD` at their boundary and
       they are closer than :data:`FLASH_MIN_INTERVAL_S` apart, the later
       segment's boundary intensity is clamped.
    6. Return the assembled plan dict.

    Args:
        render_spec: RenderSpec v2 instance.
        composer_seed: Seed passed to :class:`NarrativeComposer`.
        fps: Frames per second for the output video.
        mock_adapters: When True, adapter dispatch returns a mock result
            dict instead of invoking real tools.  Set False to use the
            real conductor (requires adapters + runtimes installed).

    Returns:
        Assembly plan dict (see module docstring for shape).

    Raises:
        AssemblyError: When ``scene_segments`` is empty or the assembled
            timeline does not cover the full spec duration.
    """
    from melosviz.compose.narrator import NarrativeComposer

    # ---- Unpack spec ---------------------------------------------------------
    spec_dict = (
        render_spec.model_dump()
        if hasattr(render_spec, "model_dump")
        else dict(render_spec)
    )
    scene_segments: list[dict[str, Any]] = list(spec_dict.get("scene_segments") or [])
    mir: dict[str, Any] = dict(spec_dict.get("mir") or {})
    total_duration: float = float(
        spec_dict.get("metadata", {}).get("duration_sec")
        or (scene_segments[-1]["end"] if scene_segments else 0.0)
    )

    if not scene_segments:
        raise AssemblyError(
            "assemble_render_plan: render_spec.scene_segments is empty — "
            "run analysis first to populate scene segments."
        )

    # ---- Composer: assign varied scenes -------------------------------------
    composer = NarrativeComposer(seed=composer_seed)
    assignments = composer.assign(scene_segments, mir)

    # ---- Beat-align segment starts ------------------------------------------
    beat_times: list[float] = _extract_beat_times(spec_dict)
    aligned_assignments = _beat_align(assignments, beat_times)

    # ---- Conductor dispatch (real or mock) ----------------------------------
    assembled_segments: list[dict[str, Any]] = []
    for asgn in aligned_assignments:
        if mock_adapters:
            adapter_result: dict[str, Any] = {
                "mock": True,
                "scene_type": asgn["scene_type"],
                "output_path": f"/tmp/melosviz/seg_{asgn['index']:03d}.mov",
            }
        else:
            adapter_result = _dispatch_segment(render_spec, asgn)

        assembled_segments.append({**asgn, "adapter_result": adapter_result})

    # ---- Cross-segment flash-safety -----------------------------------------
    assembled_segments = _enforce_cross_segment_flash_safety(assembled_segments)

    # ---- Validate timeline covers full duration -----------------------------
    if assembled_segments:
        last_end = float(assembled_segments[-1].get("end", 0.0))
        first_start = float(assembled_segments[0].get("start", 0.0))
        covered = last_end - first_start
        if total_duration > 0 and covered < total_duration * 0.99:
            raise AssemblyError(
                f"assemble_render_plan: assembled timeline covers {covered:.2f}s "
                f"but render_spec duration is {total_duration:.2f}s — gap detected."
            )

    # ---- Build transitions list (beat-aligned cut points) -------------------
    transitions = [
        float(seg["beat_aligned_start"])
        for seg in assembled_segments[1:]  # first segment has no leading cut
    ]

    plan: dict[str, Any] = {
        "version": "2.0",
        "total_duration": total_duration,
        "fps": fps,
        "segment_count": len(assembled_segments),
        "flash_safe": True,  # enforced above
        "segments": assembled_segments,
        "transitions": transitions,
        "composer_seed": composer_seed,
    }
    logger.info(
        "assemble_render_plan: %d segments, duration=%.2fs, beat_cuts=%d, seed=%d",
        len(assembled_segments),
        total_duration,
        len(transitions),
        composer_seed,
    )
    return plan


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_beat_times(spec_dict: dict[str, Any]) -> list[float]:
    """Extract beat timestamps from timeline_events or dense_keyframes."""
    beat_times: list[float] = []
    for event in spec_dict.get("timeline_events") or []:
        if str(event.get("type", "")) in ("beat", "downbeat"):
            t = event.get("t")
            if t is not None:
                beat_times.append(float(t))
    # Fallback: dense_keyframes stride — every keyframe is a candidate
    if not beat_times:
        for kf in spec_dict.get("dense_keyframes") or []:
            t = kf.get("t")
            if t is not None:
                beat_times.append(float(t))
    return sorted(set(beat_times))


def _beat_align(
    assignments: list[Any],  # list[SegmentAssignment]
    beat_times: list[float],
) -> list[dict[str, Any]]:
    """Snap each segment's start time to the nearest beat.

    Returns a list of dicts (not SegmentAssignment) with an added
    ``beat_aligned_start`` field and a ``transition`` string.
    """
    result: list[dict[str, Any]] = []
    for asgn in assignments:
        d = asgn.as_dict() if hasattr(asgn, "as_dict") else dict(asgn)
        original_start = d["start"]
        if beat_times:
            nearest = min(beat_times, key=lambda b: abs(b - original_start))
        else:
            nearest = original_start
        d["beat_aligned_start"] = round(nearest, 4)
        d["transition"] = "crossfade_2f"
        result.append(d)
    return result


def _dispatch_segment(
    render_spec: RenderSpec,
    asgn: dict[str, Any],
) -> dict[str, Any]:
    """Route a single segment through the real conductor adapter."""
    from melosviz.conductor.orchestrator import Orchestrator

    orch = Orchestrator(skip_assembly=True)
    scene_type = asgn["scene_type"]
    try:
        orch_result = orch.render(
            render_spec,
            scene_types=[scene_type],
        )
        return orch_result.per_scene_results.get(scene_type, {"dispatched": True})
    except Exception as exc:
        logger.warning("_dispatch_segment: adapter %r failed: %s", scene_type, exc)
        return {"error": str(exc), "scene_type": scene_type}


def _enforce_cross_segment_flash_safety(
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Clamp boundary intensities to honour the ≤ 3 Hz flash rule.

    Checks each pair of adjacent segments: if both have ``intensity`` >
    :data:`FLASH_BOUNDARY_THRESHOLD` and the gap between them is less than
    :data:`FLASH_MIN_INTERVAL_S`, the later segment's intensity is clamped to
    :data:`FLASH_BOUNDARY_THRESHOLD`.

    This is in addition to the per-segment ``apply_flash_safety`` applied by
    the Blender adapter (P3) — here we guard cross-segment boundaries.
    """
    if len(segments) < 2:
        return segments

    result = [dict(segments[0])]
    for i in range(1, len(segments)):
        seg = dict(segments[i])
        prev = result[i - 1]

        prev_end = float(prev.get("end", prev.get("beat_aligned_start", 0.0)))
        seg_start = float(seg.get("beat_aligned_start", seg.get("start", 0.0)))
        gap = seg_start - prev_end

        prev_intensity = float(prev.get("intensity", 0.0))
        seg_intensity = float(seg.get("intensity", 0.0))

        if (
            prev_intensity > FLASH_BOUNDARY_THRESHOLD
            and seg_intensity > FLASH_BOUNDARY_THRESHOLD
            and gap < FLASH_MIN_INTERVAL_S
        ):
            logger.debug(
                "Flash-safety clamp at boundary seg %d→%d (gap=%.3fs)",
                i - 1,
                i,
                gap,
            )
            seg["intensity"] = FLASH_BOUNDARY_THRESHOLD

        result.append(seg)

    return result
