"""Conductor adapter registry.

Maps scene-type string keys to adapter *classes*.  Instances are created
on-demand by the orchestrator to keep startup cost zero.

To register a new adapter, import its class and add it to ``ADAPTER_REGISTRY``.
Each class must expose:
  - ``scene_type: str`` — class attribute matching the registry key.
  - ``render(render_spec, *, output_path, **kwargs)`` — returns a result object.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Lazy imports — avoid heavy transitive imports at registry-load time.
# Each adapter is only imported when the registry entry is accessed.
# ---------------------------------------------------------------------------


def _lazy(module: str, cls: str) -> Any:
    """Return a lazy-loading proxy that imports ``module.cls`` on first call."""

    class _Proxy:
        _real: Any = None

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            if self._real is None:
                import importlib

                mod = importlib.import_module(module)
                self._real = getattr(mod, cls)
            return self._real(*args, **kwargs)  # type: ignore[misc]

        def __getattr__(self, name: str) -> Any:
            if self._real is None:
                import importlib

                mod = importlib.import_module(module)
                self._real = getattr(mod, cls)
            return getattr(self._real, name)

    return _Proxy()


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

#: Maps scene-type key → adapter class (or lazy proxy).
#: The orchestrator instantiates adapters on demand.
ADAPTER_REGISTRY: dict[str, Any] = {
    # GOLD tier — generative / composition
    "generative_asset": _lazy(
        "melosviz.render.firefly_adapter", "FireflyAdapter"
    ),
    # GOLD tier — AE motion-graphics beat sync
    "motion_graphics_beat_sync": _lazy(
        "melosviz.render.aftereffects_adapter", "AEAdapter"
    ),
    # GOLD tier — final assembly + encode
    "assembly_encode": _lazy(
        "melosviz.render.mediaencoder_adapter", "MEAdapter"
    ),
    # GOLD tier — headless Blender 3-D animation
    "procedural_3d_animation": _lazy(
        "melosviz.conductor.registry", "_BlenderAdapterShim"
    ),
    # GOLD tier — TouchDesigner live-stage runtime
    "live_stage": _lazy(
        "melosviz.runtime.touchdesigner.adapter", "TDAdapter"
    ),
    # SILVER tier — always-available FFmpeg video export
    "video_export": _lazy(
        "melosviz.conductor.registry", "_VideoExportAdapter"
    ),
}


# ---------------------------------------------------------------------------
# Shim adapters — thin wrappers so the registry has a uniform interface
# ---------------------------------------------------------------------------


class _BlenderAdapterShim:
    """GOLD-tier Blender headless render shim."""

    scene_type: str = "procedural_3d_animation"

    def render(self, render_spec: Any, *, output_path: Any = None, **_: Any) -> Any:
        import pathlib

        from melosviz.render.blender_exporter import (
            BlenderNotFoundError,
            export_blender,
        )

        out_dir = pathlib.Path(str(output_path)) if output_path is not None else None
        try:
            return export_blender(render_spec, output_dir=out_dir)
        except BlenderNotFoundError:
            raise  # caller decides fallback


class _VideoExportAdapter:
    """SILVER-tier FFmpeg video-export shim (always available)."""

    scene_type: str = "video_export"

    def render(self, render_spec: Any, *, output_path: Any = None, **_: Any) -> Any:
        from melosviz.render.video_exporter import export_video

        if output_path is not None:
            import pathlib

            return export_video(render_spec, output_dir=pathlib.Path(str(output_path)))
        return export_video(render_spec)
