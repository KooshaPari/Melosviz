"""Adapter registry — one adapter class per scene_type.

All adapters extend ``AdapterBase``.  Only ``VideoExportAdapter`` (for the
existing ``video_exporter`` pipeline) and ``BlenderAdapter`` (P3 stub) are
wired now.  All remaining scene_type adapters are registered stubs that raise
``NotImplementedError`` with a clear message — **no silent fallback**.
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import Any

from .router import SceneType


class AdapterBase(abc.ABC):
    """Abstract base for all renderer adapters."""

    #: scene_type tag this adapter handles.
    scene_type: SceneType

    @abc.abstractmethod
    def render(
        self,
        segment: Any,
        spec: Any,
        output_dir: Path,
        **kwargs: Any,
    ) -> Path | None:
        """Render one segment and return the output path (or ``None`` for stubs).

        Concrete adapters write their output under ``output_dir`` and return
        the file path.  Stub adapters raise ``NotImplementedError``.

        Args:
            segment: The ``SceneSegment`` (or dict) being rendered.
            spec:    The full ``RenderSpec`` for context / keyframe data.
            output_dir: Destination directory (guaranteed to exist by caller).
            **kwargs: Adapter-specific options forwarded from the orchestrator.

        Raises:
            NotImplementedError: For stub adapters that are not yet implemented.
        """


# ---------------------------------------------------------------------------
# Wired adapters (P2 scope)
# ---------------------------------------------------------------------------

class VideoExportAdapter(AdapterBase):
    """Routes generative-asset segments through the existing ``export_video``
    pipeline (ffmpeg-based colour-frame concat).

    This is the only fully-wired adapter in P2.  It delegates to
    ``melosviz.render.video_exporter.export_video``.
    """

    scene_type = SceneType.GENERATIVE_ASSET

    def render(
        self,
        segment: Any,
        spec: Any,
        output_dir: Path,
        export_format: str = "mp4",
        **kwargs: Any,
    ) -> Path | None:
        from melosviz.render.video_exporter import export_video  # local import

        output_path = export_video(spec, format=export_format, output_dir=output_dir)
        return output_path


# ---------------------------------------------------------------------------
# P3 stub — Blender adapter
# ---------------------------------------------------------------------------

class BlenderAdapter(AdapterBase):
    """Stub: Blender Python / bpy render adapter (implemented in P3).

    Handles ``procedural_3d_animation`` segments via a Blender headless
    render pipeline.  Raises ``NotImplementedError`` until P3 lands.
    """

    scene_type = SceneType.PROCEDURAL_3D_ANIMATION

    def render(
        self,
        segment: Any,
        spec: Any,
        output_dir: Path,
        **kwargs: Any,
    ) -> Path | None:
        raise NotImplementedError(
            "BlenderAdapter (procedural_3d_animation) is scheduled for P3. "
            "Pass skip_unimplemented=True to the orchestrator to skip this segment, "
            "or implement the adapter before calling render()."
        )


# ---------------------------------------------------------------------------
# Remaining stubs — one per unimplemented scene_type
# ---------------------------------------------------------------------------

class MotionGraphicsAdapter(AdapterBase):
    """Stub: motion-graphics beat-sync renderer (P4+)."""

    scene_type = SceneType.MOTION_GRAPHICS_BEAT_SYNC

    def render(self, segment: Any, spec: Any, output_dir: Path, **kwargs: Any) -> Path | None:
        raise NotImplementedError(
            "MotionGraphicsAdapter (motion_graphics_beat_sync) is not yet implemented. "
            "Scheduled for a future pillar."
        )


class LiveStageAdapter(AdapterBase):
    """Stub: live-stage renderer (P4+)."""

    scene_type = SceneType.LIVE_STAGE

    def render(self, segment: Any, spec: Any, output_dir: Path, **kwargs: Any) -> Path | None:
        raise NotImplementedError(
            "LiveStageAdapter (live_stage) is not yet implemented. "
            "Scheduled for a future pillar."
        )


class ExperimentalCodeGenAdapter(AdapterBase):
    """Stub: experimental code-gen renderer (P4+)."""

    scene_type = SceneType.EXPERIMENTAL_CODE_GEN

    def render(self, segment: Any, spec: Any, output_dir: Path, **kwargs: Any) -> Path | None:
        raise NotImplementedError(
            "ExperimentalCodeGenAdapter (experimental_code_gen) is not yet implemented. "
            "Scheduled for a future pillar."
        )


# ---------------------------------------------------------------------------
# Registry — keyed by SceneType
# ---------------------------------------------------------------------------

#: Default adapter instances, one per scene_type.  Replace entries to swap
#: implementations (e.g., in tests: ``ADAPTER_REGISTRY[SceneType.GENERATIVE_ASSET]
#: = MyMockAdapter()``).
ADAPTER_REGISTRY: dict[SceneType, AdapterBase] = {
    SceneType.PROCEDURAL_3D_ANIMATION: BlenderAdapter(),
    SceneType.MOTION_GRAPHICS_BEAT_SYNC: MotionGraphicsAdapter(),
    SceneType.GENERATIVE_ASSET: VideoExportAdapter(),
    SceneType.LIVE_STAGE: LiveStageAdapter(),
    SceneType.EXPERIMENTAL_CODE_GEN: ExperimentalCodeGenAdapter(),
}


def get_adapter(scene_type: SceneType) -> AdapterBase:
    """Return the registered adapter for ``scene_type``.

    Raises:
        KeyError: If ``scene_type`` has no registered adapter (should not
            happen as all five types have entries in ``ADAPTER_REGISTRY``).
    """
    try:
        return ADAPTER_REGISTRY[scene_type]
    except KeyError as exc:
        raise KeyError(
            f"No adapter registered for scene_type={scene_type!r}. "
            f"Known types: {list(ADAPTER_REGISTRY)}"
        ) from exc
