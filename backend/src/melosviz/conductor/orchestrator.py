"""Conductor orchestrator — routes a RenderSpec to pro-tool adapters.

The orchestrator:
1. Identifies which scene types appear in ``spec.scene_segments``.
2. Dispatches each scene type to the corresponding adapter from
   :data:`~melosviz.conductor.registry.ADAPTER_REGISTRY`.
3. Collects per-adapter render results.
4. Triggers the final ``assembly_encode`` step (MediaEncoder or ffmpeg
   fallback) with the collected per-segment output paths.

Failure policy
--------------
* Missing adapter for a scene type raises :class:`ConductorError` (loud, not silent).
* Adapter render failures propagate their own exceptions; the orchestrator
  wraps them with scene-type context.
* The final assembly step is always attempted last; failure is also loud.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from melosviz.analysis.models import RenderSpec

logger = logging.getLogger(__name__)

__all__ = ["Orchestrator", "ConductorError", "OrchestratorResult"]


class ConductorError(RuntimeError):
    """Raised when the conductor cannot route or dispatch a render."""


class OrchestratorResult:
    """Aggregated result from a full :meth:`Orchestrator.render` run.

    Attributes:
        per_scene_results: ``{scene_type: adapter_result}`` for each dispatched type.
        assembly_result: Result from the final ``assembly_encode`` step.
        output_dir: Base directory used for all outputs.
    """

    def __init__(
        self,
        per_scene_results: dict[str, Any],
        assembly_result: Any | None,
        output_dir: Path | None,
    ) -> None:
        self.per_scene_results = per_scene_results
        self.assembly_result = assembly_result
        self.output_dir = output_dir


class Orchestrator:
    """Multi-tool render orchestrator.

    Dispatches a :class:`~melosviz.analysis.models.RenderSpec` to all
    registered adapters, then runs the final assembly step.

    Args:
        output_dir: Base directory for all adapter outputs.
            Defaults to ``/tmp/melosviz-conductor``.
        skip_assembly: When True, skip the final ``assembly_encode`` step
            (useful for per-adapter unit tests).
    """

    def __init__(
        self,
        output_dir: Path | str | None = None,
        skip_assembly: bool = False,
    ) -> None:
        self._output_dir = Path(output_dir) if output_dir is not None else Path("/tmp/melosviz-conductor")
        self._skip_assembly = skip_assembly

    def render(
        self,
        render_spec: RenderSpec,
        *,
        scene_types: list[str] | None = None,
        segment_paths: list[str | Path] | None = None,
    ) -> OrchestratorResult:
        """Dispatch the render spec to all relevant adapters.

        Args:
            render_spec: RenderSpec v2 instance.
            scene_types: Override the list of scene types to dispatch.
                When None, derives them from ``spec.scene_segments``.
            segment_paths: Pre-existing per-segment clip paths to pass to
                the assembly step.  When None, collected from per-adapter results.

        Returns:
            :class:`OrchestratorResult` with all adapter results.

        Raises:
            ConductorError: When a required adapter is missing.
        """
        from melosviz.conductor.registry import ADAPTER_REGISTRY

        self._output_dir.mkdir(parents=True, exist_ok=True)

        # ---- Resolve scene types from spec ---------------------------------
        if scene_types is None:
            spec_dict = (
                render_spec.model_dump()
                if hasattr(render_spec, "model_dump")
                else render_spec
            )
            segs = spec_dict.get("scene_segments") or []
            # Deduplicate while preserving order
            seen: set[str] = set()
            _types: list[str] = []
            for seg in segs:
                st = str(seg.get("scene_type", "video_export"))
                if st not in seen:
                    seen.add(st)
                    _types.append(st)
            # If no scene_segments, fall back to video_export
            if not _types:
                _types = ["video_export"]
        else:
            _types = list(scene_types)

        # ---- Dispatch per scene type ----------------------------------------
        per_scene_results: dict[str, Any] = {}
        collected_paths: list[str | Path] = list(segment_paths or [])

        for scene_type in _types:
            if scene_type == "assembly_encode":
                # Assembly is always the final step; skip inline dispatch.
                continue

            adapter_cls = ADAPTER_REGISTRY.get(scene_type)
            if adapter_cls is None:
                raise ConductorError(
                    f"Orchestrator: no adapter registered for scene_type={scene_type!r}. "
                    f"Registered types: {list(ADAPTER_REGISTRY.keys())}. "
                    "Register an adapter in melosviz.conductor.registry.ADAPTER_REGISTRY."
                )

            scene_out_dir = self._output_dir / scene_type
            scene_out_dir.mkdir(parents=True, exist_ok=True)

            logger.info("Orchestrator: dispatching scene_type=%r → %s", scene_type, adapter_cls)
            try:
                adapter = adapter_cls()
                result = adapter.render(render_spec, output_path=scene_out_dir)
            except Exception as exc:
                raise ConductorError(
                    f"Orchestrator: adapter for scene_type={scene_type!r} failed: {exc}"
                ) from exc

            per_scene_results[scene_type] = result

        # ---- Final assembly step -------------------------------------------
        assembly_result: Any = None
        if not self._skip_assembly:
            me_cls = ADAPTER_REGISTRY.get("assembly_encode")
            if me_cls is None:
                raise ConductorError(
                    "Orchestrator: 'assembly_encode' adapter missing from registry. "
                    "Wiring error — MEAdapter must be registered."
                )
            assembly_out = self._output_dir / "assembly"
            assembly_out.mkdir(parents=True, exist_ok=True)
            logger.info(
                "Orchestrator: running final assembly_encode step → %s "
                "(segment_paths=%d, ffmpeg fallback if AME absent)",
                assembly_out,
                len(collected_paths),
            )
            try:
                me_adapter = me_cls()
                assembly_result = me_adapter.render(
                    render_spec,
                    output_path=assembly_out,
                    segment_paths=collected_paths,
                )
            except Exception as exc:
                raise ConductorError(
                    f"Orchestrator: final assembly_encode step failed: {exc}"
                ) from exc

        return OrchestratorResult(
            per_scene_results=per_scene_results,
            assembly_result=assembly_result,
            output_dir=self._output_dir,
        )
