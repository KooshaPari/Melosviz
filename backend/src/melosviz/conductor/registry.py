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


def _lazy(module: str, cls: str, *, scene_type: str | None = None) -> Any:
    """Return a lazy-loading proxy that imports ``module.cls`` on first call.

    If ``scene_type`` is given, the proxy exposes it as ``scene_type`` so
    registry consumers can read the key without paying the import cost.
    """
    proxy_attrs: dict[str, Any] = {}
    if scene_type is not None:
        proxy_attrs["scene_type"] = scene_type

    class _Proxy:
        _real: Any = None

        def __init__(self) -> None:
            for k, v in proxy_attrs.items():
                object.__setattr__(self, k, v)

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            if self._real is None:
                import importlib

                mod = importlib.import_module(module)
                self._real = getattr(mod, cls)
            return self._real(*args, **kwargs)  # type: ignore[misc]

        def __getattr__(self, name: str) -> Any:
            if name in proxy_attrs:
                return proxy_attrs[name]
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
    # ---- GOLD tier — ComfyUI (image / video diffusion) --------------------
    "comfyui_image": _lazy("melosviz.render.comfyui_adapter", "ComfyUIAdapter",
                            scene_type="comfyui_image"),
    "comfyui_video": _lazy("melosviz.render.comfyui_adapter", "ComfyUIAdapter",
                            scene_type="comfyui_video"),
    # ---- GOLD tier — generative / composition -----------------------------
    "generative_asset": _lazy("melosviz.render.comfyui_adapter", "ComfyUIAdapter",
                              scene_type="generative_asset"),
    # ---- WBS-101..106 — Character-consistent ComfyUI workflows -------------
    # These route to the same ComfyUIAdapter instance but the adapter
    # picks the ``ipadapter_character.json`` / ``pulid_character.json``
    # template based on the engine recorded on the resolved character
    # sheet (see ``comfyui_adapter._resolve_workflow_for_scene``).
    "ipadapter_character": _lazy("melosviz.render.comfyui_adapter", "ComfyUIAdapter",
                                  scene_type="comfyui_image"),
    "pulid_character": _lazy("melosviz.render.comfyui_adapter", "ComfyUIAdapter",
                              scene_type="comfyui_video"),
    # ---- WBS-107..109 — Native-audio video workflows ----------------------
    # ``comfyui_audio_video_wan`` → wan_s2v_audio.json  (Wan S2V)
    # ``comfyui_audio_video_seedance`` → seedance_a2v.json  (Seedance A2V)
    "comfyui_audio_video_wan": _lazy("melosviz.render.comfyui_adapter",
                                       "ComfyUIAdapter",
                                       scene_type="comfyui_audio_video_wan"),
    "comfyui_audio_video_seedance": _lazy("melosviz.render.comfyui_adapter",
                                             "ComfyUIAdapter",
                                             scene_type="comfyui_audio_video_seedance"),
    # ---- GOLD tier — Cinema 4D (high-end 3D scenes) -----------------------
    "c4d_3d": _lazy("melosviz.render.cinema4d_adapter", "C4DAdapter",
                    scene_type="c4d_3d"),
    # ---- GOLD tier — Unreal Engine (real-time cinematic) ------------------
    "unreal_cinematic": _lazy("melosviz.render.unreal_adapter", "UEAdapter",
                              scene_type="unreal_cinematic"),
    # ---- GOLD tier — After Effects (motion graphics + beat sync) ----------
    "motion_graphics_beat_sync": _lazy(
        "melosviz.render.aftereffects_adapter", "AEAdapter",
        scene_type="motion_graphics_beat_sync",
    ),
    # ---- GOLD tier — DaVinci Resolve (final edit + color + master) -------
    "davinci_master": _lazy("melosviz.render.davinci_adapter", "ResolveAdapter",
                            scene_type="davinci_master"),
    "davinci_finish": _lazy("melosviz.render.davinci_adapter", "ResolveAdapter",
                            scene_type="davinci_finish"),
    # ---- GOLD tier — final assembly + encode ------------------------------
    "assembly_encode": _lazy("melosviz.render.mediaencoder_adapter", "MEAdapter",
                             scene_type="assembly_encode"),
    # ---- GOLD tier — headless Blender 3-D animation -----------------------
    "procedural_3d_animation": _lazy(
        "melosviz.conductor.registry", "_BlenderAdapterShim",
        scene_type="procedural_3d_animation",
    ),
    # ---- GOLD tier — TouchDesigner live-stage runtime ---------------------
    "live_stage": _lazy("melosviz.runtime.touchdesigner.adapter", "TDAdapter",
                        scene_type="live_stage"),
    # ---- SILVER tier — always-available FFmpeg video export ---------------
    "video_export": _lazy("melosviz.conductor.registry", "_VideoExportAdapter",
                          scene_type="video_export"),
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
