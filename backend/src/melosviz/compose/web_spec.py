"""Build browser-facing shot keyframes from RenderSpec v2 scene_segments.

The web R3F renderer consumes sparse shot keyframes (``spec.keyframes``) with
``scene`` labels and ``scene_template`` ids plus optional ``scene_segments``.
This module derives those fields from MIR-backed segments so analyze/build
produce wholly unique multi-scene compositions — not a single look with
palette tweaks.
"""

from __future__ import annotations

from typing import Any

from melosviz.analysis.models import RenderSpec
from melosviz.presets.scene_families import (
    TEMPLATE_DISPLAY_NAMES,
    family_for_preset,
    remap_scene_segments,
)

__all__ = [
    "enrich_render_spec_for_web",
    "build_shot_keyframes",
    "tag_dense_keyframes_with_scenes",
    "CAMERA_BY_TEMPLATE",
    "TRANSITION_FRACTION",
]

# Normalised crossfade window at each segment boundary (fraction of segment length).
TRANSITION_FRACTION: float = 0.12

# Base camera language per template — web renderer lerps with keyframe offsets.
CAMERA_BY_TEMPLATE: dict[str, dict[str, float]] = {
    "wire_orb": {"distance": 9.0, "azimuth": 0.0, "elevation": 0.2},
    "torus_flow": {"distance": 6.0, "azimuth": 0.45, "elevation": 0.12},
    "crystal_burst": {"distance": 4.0, "azimuth": -0.35, "elevation": 0.32},
    "ring_drift": {"distance": 8.0, "azimuth": 0.0, "elevation": 0.05},
    "grid_depth": {"distance": 7.0, "azimuth": 0.25, "elevation": -0.08},
    "octa_pulse": {"distance": 5.0, "azimuth": 0.6, "elevation": 0.22},
}


def _palette_from_spec(spec_dict: dict[str, Any]) -> list[str]:
    palette = list(spec_dict.get("palette") or [])
    if palette:
        return palette
    return ["#7c6af7", "#22d3ee", "#f97316", "#0ea5e9", "#6366f1"]


def _colors_for_segment(
    seg: dict[str, Any],
    palette: list[str],
    index: int,
) -> dict[str, Any]:
    """Derive primary/secondary/brightness from segment MIR means + palette."""
    em = float(seg.get("energy_mean") or 0.5)
    bm = float(seg.get("brightness_mean") or 0.5)
    primary = palette[index % len(palette)]
    secondary = palette[(index + 1) % len(palette)]
    brightness = min(1.0, max(0.2, 0.35 + 0.45 * em + 0.2 * bm))
    return {"primary": primary, "secondary": secondary, "brightness": round(brightness, 3)}


def _camera_for_segment(seg: dict[str, Any], template: str) -> dict[str, float]:
    base = dict(CAMERA_BY_TEMPLATE.get(template, CAMERA_BY_TEMPLATE["torus_flow"]))
    em = float(seg.get("energy_mean") or 0.5)
    # High-energy sections pull camera closer and raise elevation slightly.
    base["distance"] = round(base["distance"] * (1.1 - 0.25 * em), 3)
    base["elevation"] = round(base["elevation"] + 0.08 * em, 3)
    return base


def build_shot_keyframes(
    scene_segments: list[dict[str, Any]],
    duration_sec: float,
    palette: list[str] | None = None,
) -> list[dict[str, Any]]:
    """One sparse shot keyframe per segment boundary for the R3F renderer."""
    if not scene_segments or duration_sec <= 0:
        return []

    colors_palette = palette or ["#7c6af7", "#22d3ee", "#f97316", "#0ea5e9"]
    keyframes: list[dict[str, Any]] = []

    for i, seg in enumerate(scene_segments):
        start = float(seg.get("start", 0.0))
        template = str(seg.get("scene_template", "torus_flow"))
        scene_name = str(
            seg.get("scene")
            or TEMPLATE_DISPLAY_NAMES.get(template, seg.get("label", "Scene"))
        )
        t_norm = min(1.0, max(0.0, start / duration_sec))
        seg_len = max(
            0.001,
            float(seg.get("end", start + 1.0)) - start,
        )
        transition_secs = seg_len * TRANSITION_FRACTION

        keyframes.append(
            {
                "t": round(t_norm, 5),
                "scene": scene_name,
                "scene_template": template,
                "camera": _camera_for_segment(seg, template),
                "color": _colors_for_segment(seg, colors_palette, i),
                "transition_secs": round(transition_secs, 3),
                "segment_index": int(seg.get("index", i)),
                "label": str(seg.get("label", "unknown")),
            }
        )

    # Terminal keyframe at t=1 for outro hold / final crossfade target.
    last = scene_segments[-1]
    if keyframes and keyframes[-1]["t"] < 0.999:
        template = str(last.get("scene_template", "wire_orb"))
        keyframes.append(
            {
                "t": 1.0,
                "scene": str(
                    last.get("scene")
                    or TEMPLATE_DISPLAY_NAMES.get(template, "Outro")
                ),
                "scene_template": template,
                "camera": _camera_for_segment(last, template),
                "color": _colors_for_segment(
                    last, colors_palette, len(scene_segments) - 1
                ),
                "transition_secs": 0.0,
                "segment_index": int(last.get("index", len(scene_segments) - 1)),
                "label": str(last.get("label", "outro")),
            }
        )

    return keyframes


def tag_dense_keyframes_with_scenes(
    dense_keyframes: list[dict[str, Any]],
    scene_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Annotate each dense keyframe with the active segment label + template."""
    if not dense_keyframes or not scene_segments:
        return dense_keyframes

    tagged: list[dict[str, Any]] = []
    seg_idx = 0
    for kf in dense_keyframes:
        t = float(kf.get("t", 0.0))
        while (
            seg_idx < len(scene_segments) - 1
            and t >= float(scene_segments[seg_idx].get("end", 0.0))
        ):
            seg_idx += 1
        seg = scene_segments[seg_idx]
        kf_copy = dict(kf)
        kf_copy["scene"] = seg.get("scene") or seg.get("label", "unknown")
        kf_copy["scene_template"] = seg.get("scene_template", "torus_flow")
        kf_copy["segment_index"] = seg.get("index", seg_idx)
        tagged.append(kf_copy)
    return tagged


def enrich_render_spec_for_web(
    spec: RenderSpec | dict[str, Any],
    *,
    preset_name: str | None = None,
) -> dict[str, Any]:
    """Populate web-facing fields on a RenderSpec v2 dict in place."""
    if hasattr(spec, "model_dump"):
        data: dict[str, Any] = spec.model_dump()
    else:
        data = dict(spec)

    meta = dict(data.get("metadata") or {})
    preset = preset_name or meta.get("preset")
    duration = float(meta.get("duration") or meta.get("duration_sec") or 0.0)
    if duration <= 0 and data.get("scene_segments"):
        duration = float(data["scene_segments"][-1].get("end", 0.0))

    segments = list(data.get("scene_segments") or [])
    if not segments:
        return data

    family = family_for_preset(str(preset) if preset else None)
    remapped = remap_scene_segments(segments, family=family)
    data["scene_segments"] = remapped

    palette = _palette_from_spec(data)
    data["keyframes"] = build_shot_keyframes(remapped, duration, palette)

    dense = list(data.get("dense_keyframes") or [])
    if dense:
        data["dense_keyframes"] = tag_dense_keyframes_with_scenes(dense, remapped)

    # Convenience top-level fields for the web hook.
    mir = dict(data.get("mir") or {})
    data["duration_sec"] = duration
    data["durationSecs"] = duration
    if not data.get("bpm"):
        data["bpm"] = mir.get("tempo_bpm") or meta.get("estimated_bpm")
    if not data.get("beat_times") and data.get("timeline_events"):
        data["beat_times"] = sorted(
            float(ev["t"])
            for ev in data["timeline_events"]
            if ev.get("type") == "beat"
        )

    meta["web_spec_version"] = 1
    meta["transition_fraction"] = TRANSITION_FRACTION
    data["metadata"] = meta
    return data
