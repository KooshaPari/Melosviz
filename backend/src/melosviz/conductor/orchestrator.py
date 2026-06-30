"""Orchestrator — RenderSpec → per-segment route → dispatch → collect outputs.

Entry point: ``orchestrate(spec, output_dir, ...)``

Pipeline:
  1. ``route_spec(spec)`` → list of ``(segment, SceneType)`` pairs.
  2. For each pair, look up the registered adapter via ``get_adapter()``.
  3. Dispatch ``adapter.render(segment, spec, output_dir)``.
     - If the adapter raises ``NotImplementedError`` and ``skip_unimplemented``
       is ``True``, the segment is recorded as skipped.
     - Otherwise ``NotImplementedError`` propagates — no silent fallback.
  4. Collect per-segment results into a ``RenderPlan`` / ``RenderResult``.
  5. Hand assembled outputs to the assembly step (ffmpeg concat for now).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .adapters import get_adapter
from .router import SceneType, route_spec

logger = logging.getLogger(__name__)


@dataclass
class SegmentResult:
    """Outcome of dispatching a single segment to its adapter."""

    segment_index: int
    scene_type: SceneType
    output_path: Path | None
    skipped: bool = False
    skip_reason: str = ""
    error: Exception | None = None


@dataclass
class RenderPlan:
    """Routing plan — produced by ``build_plan``; does not execute renders."""

    spec: Any
    routes: list[tuple[Any, SceneType]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"RenderPlan: {len(self.routes)} segment(s)"]
        for seg, st in self.routes:
            label = seg.get("label") if isinstance(seg, dict) else getattr(seg, "label", "?")
            lines.append(f"  [{label}] → {st.value}")
        return "\n".join(lines)


@dataclass
class RenderResult:
    """Aggregate outcome of a full orchestration run."""

    output_dir: Path
    segment_results: list[SegmentResult] = field(default_factory=list)
    final_output: Path | None = None

    @property
    def success(self) -> bool:
        return all(r.error is None for r in self.segment_results)

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.segment_results if r.skipped)

    @property
    def rendered_paths(self) -> list[Path]:
        return [r.output_path for r in self.segment_results if r.output_path is not None]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_plan(spec: Any) -> RenderPlan:
    """Route every segment in ``spec`` and return a ``RenderPlan``.

    No I/O is performed; this is the ``viz build`` step.
    """
    routes = route_spec(spec)
    return RenderPlan(spec=spec, routes=routes)


def orchestrate(
    spec: Any,
    output_dir: Path | str,
    *,
    skip_unimplemented: bool = False,
    export_format: str = "mp4",
) -> RenderResult:
    """Dispatch all segments in ``spec`` to their adapters and collect results.

    Args:
        spec:               ``RenderSpec`` (Pydantic model or dict).
        output_dir:         Root directory for all segment outputs.  Created
                            if it does not exist.
        skip_unimplemented: When ``True``, segments whose adapter raises
                            ``NotImplementedError`` are skipped and recorded
                            (not propagated).  When ``False`` (default),
                            ``NotImplementedError`` propagates — no silent
                            fallback.
        export_format:      Passed to adapters that accept it (e.g.
                            ``VideoExportAdapter``).

    Returns:
        A ``RenderResult`` collecting per-segment outcomes.

    Raises:
        NotImplementedError: If a stub adapter is encountered and
            ``skip_unimplemented`` is ``False``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    routes = route_spec(spec)
    result = RenderResult(output_dir=output_dir)

    for idx, (segment, scene_type) in enumerate(routes):
        seg_dir = output_dir / f"segment_{idx:04d}_{scene_type.value}"
        seg_dir.mkdir(parents=True, exist_ok=True)

        adapter = get_adapter(scene_type)

        label = (
            segment.get("label") if isinstance(segment, dict)
            else getattr(segment, "label", "?")
        )
        logger.info(
            "orchestrate: segment=%d label=%r scene_type=%s adapter=%s",
            idx,
            label,
            scene_type.value,
            type(adapter).__name__,
        )

        try:
            output_path = adapter.render(
                segment=segment,
                spec=spec,
                output_dir=seg_dir,
                export_format=export_format,
            )
            result.segment_results.append(
                SegmentResult(
                    segment_index=idx,
                    scene_type=scene_type,
                    output_path=output_path,
                )
            )
        except NotImplementedError as exc:
            if skip_unimplemented:
                logger.warning(
                    "orchestrate: skipping segment=%d scene_type=%s — %s",
                    idx,
                    scene_type.value,
                    exc,
                )
                result.segment_results.append(
                    SegmentResult(
                        segment_index=idx,
                        scene_type=scene_type,
                        output_path=None,
                        skipped=True,
                        skip_reason=str(exc),
                    )
                )
            else:
                raise
        except Exception as exc:  # noqa: BLE001 — capture non-adapter errors
            logger.error(
                "orchestrate: segment=%d scene_type=%s FAILED — %s",
                idx,
                scene_type.value,
                exc,
                exc_info=True,
            )
            result.segment_results.append(
                SegmentResult(
                    segment_index=idx,
                    scene_type=scene_type,
                    output_path=None,
                    error=exc,
                )
            )

    # Assembly step: concat rendered outputs (ffmpeg concat) if >1 segment
    rendered = result.rendered_paths
    if len(rendered) == 1:
        result.final_output = rendered[0]
    elif len(rendered) > 1:
        result.final_output = _concat_segments(rendered, output_dir, export_format)

    return result


def _concat_segments(
    segment_paths: list[Path],
    output_dir: Path,
    export_format: str,
) -> Path | None:
    """Concatenate rendered segment files via ffmpeg concat demuxer.

    Returns the path to the concatenated output, or ``None`` if ffmpeg is
    unavailable (in which case the caller can iterate ``rendered_paths``
    directly).
    """
    import shutil
    import subprocess
    import tempfile

    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg-full")
    if not ffmpeg:
        logger.warning("_concat_segments: ffmpeg not found; skipping concat")
        return None

    ext = "webm" if export_format.lower() == "webm" else "mp4"
    out = output_dir / f"melosviz-final.{ext}"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fh:
        for p in segment_paths:
            fh.write(f"file '{p}'\n")
        concat_list = fh.name

    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", str(out)]
    logger.debug("_concat_segments: cmd=%s", cmd)

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        logger.error("_concat_segments: ffmpeg concat failed: %s", proc.stderr)
        return None

    return out
